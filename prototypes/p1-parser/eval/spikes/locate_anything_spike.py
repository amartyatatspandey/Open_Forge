#!/usr/bin/env python3
"""LocateAnything-3B spike: evaluate VLM layout detection vs YOLOv8n-DocLayNet for Phase 1.

Standalone evaluation script — does not import from src/.

Dependencies (install manually; not in pyproject.toml yet):
    pip install pdf2image pillow opencv-python-headless transformers==4.57.1 peft torchvision

Usage (from p1-parser project root):
    python eval/spikes/locate_anything_spike.py
    python eval/spikes/locate_anything_spike.py --pdf-dir corpus/golden/
    python eval/spikes/locate_anything_spike.py --download-only
    python eval/spikes/locate_anything_spike.py --single-pdf corpus/golden/TPS62933.pdf
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)

MODEL_ID = "nvidia/LocateAnything-3B"
DEFAULT_PDF_DIR = Path("corpus/golden")
DEFAULT_OUTPUT_DIR = Path("eval/spikes/locate_anything_results")
RASTER_DPI = 300

QUERY_SET: dict[str, str] = {
    "electrical_characteristics_table": (
        "electrical characteristics table with min typ max columns"
    ),
    "absolute_maximum_ratings_table": "absolute maximum ratings table",
    "pinout_table": "pin configuration or pin descriptions table",
    "layout_recommendations_section": (
        "pcb layout recommendations or layout guidelines section"
    ),
    "footnote_block": "footnote text block with superscript number markers",
    "section_heading": "section heading or table title text",
}

# BGR colors for OpenCV annotation (one per query key)
QUERY_COLORS: dict[str, tuple[int, int, int]] = {
    "electrical_characteristics_table": (0, 180, 0),
    "absolute_maximum_ratings_table": (0, 0, 220),
    "pinout_table": (220, 140, 0),
    "layout_recommendations_section": (180, 0, 180),
    "footnote_block": (0, 200, 200),
    "section_heading": (120, 120, 120),
}

DISTINCTION_IOU_FAILURE = 0.5
DISTINCTION_IOU_SUCCESS = 0.1

GOLDEN_PDF_EXCLUDE = frozenset({"TI_TMS320F28003x_v1.pdf"})

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def prepare_inference_image(
    image: Image.Image, max_side: int
) -> tuple[Image.Image, tuple[int, int]]:
    """Downscale page image so the longest edge fits within max_side pixels."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image, (width, height)

    scale = max_side / longest
    new_size = (int(width * scale), int(height * scale))
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    logger.info(
        "  Resized page %dx%d -> %dx%d for inference (max_side=%d)",
        width,
        height,
        new_size[0],
        new_size[1],
        max_side,
    )
    return resized, (width, height)


def default_max_side(device: str) -> int:
    """Pick a safe default max image side length per device."""
    if device == "cuda":
        return 4096
    if device == "mps":
        return 1280
    return 1536


# ---------------------------------------------------------------------------
# LocateAnythingWorker (from nvidia/LocateAnything-3B model card)
# ---------------------------------------------------------------------------


class LocateAnythingWorker:
    """Stateful worker that loads the model once and serves perception queries."""

    def __init__(
        self,
        model_path: str,
        device: str = "cuda",
        dtype: torch.dtype = torch.bfloat16,
    ) -> None:
        _ensure_decord_stub()
        from transformers import AutoModel, AutoProcessor, AutoTokenizer

        self.device = device
        self.dtype = dtype

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, trust_remote_code=True
        )
        self.processor = AutoProcessor.from_pretrained(
            model_path, trust_remote_code=True
        )
        self.model = AutoModel.from_pretrained(
            model_path,
            torch_dtype=dtype,
            trust_remote_code=True,
        ).to(device).eval()

    @torch.no_grad()
    def predict(
        self,
        image: Image.Image,
        question: str,
        generation_mode: str = "hybrid",
        max_new_tokens: int = 2048,
        temperature: float = 0.7,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """Run a single perception query on an image."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": question},
                ],
            }
        ]

        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        if text is None and hasattr(self.processor, "py_apply_chat_template"):
            text = self.processor.py_apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        images, videos = self.processor.process_vision_info(messages)
        inputs = self.processor(
            text=[text], images=images, videos=videos, return_tensors="pt"
        ).to(self.device)

        pixel_values = inputs["pixel_values"].to(self.dtype)
        input_ids = inputs["input_ids"]
        image_grid_hws = inputs.get("image_grid_hws", None)

        response = self.model.generate(
            pixel_values=pixel_values,
            input_ids=input_ids,
            attention_mask=inputs["attention_mask"],
            image_grid_hws=image_grid_hws,
            tokenizer=self.tokenizer,
            max_new_tokens=max_new_tokens,
            use_cache=True,
            generation_mode=generation_mode,
            temperature=temperature,
            do_sample=True,
            top_p=0.9,
            repetition_penalty=1.1,
            verbose=verbose,
        )

        result: dict[str, Any] = {
            "answer": response[0] if isinstance(response, tuple) else response
        }
        if isinstance(response, tuple) and len(response) >= 3:
            result["history"] = response[1]
            result["stats"] = response[2]
        return result

    def detect(
        self, image: Image.Image, categories: list[str], **kwargs: Any
    ) -> dict[str, Any]:
        """Object detection / document layout analysis (multi-category)."""
        cats = "</c>".join(categories)
        prompt = (
            f"Locate all the instances that matches the following description: {cats}."
        )
        return self.predict(image, prompt, **kwargs)

    def ground_multi(
        self, image: Image.Image, phrase: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Phrase grounding — multiple instances."""
        prompt = (
            f"Locate all the instances that match the following description: {phrase}."
        )
        return self.predict(image, prompt, **kwargs)

    @staticmethod
    def parse_boxes(
        answer: str, image_width: int, image_height: int
    ) -> list[list[float]]:
        """Parse model output into pixel-coordinate bounding boxes [x1,y1,x2,y2]."""
        boxes: list[list[float]] = []
        pattern = r"<box><(\d+)><(\d+)><(\d+)><(\d+)></box>"
        for match in re.finditer(pattern, answer):
            x1, y1, x2, y2 = (int(g) for g in match.groups())
            boxes.append(
                [
                    x1 / 1000 * image_width,
                    y1 / 1000 * image_height,
                    x2 / 1000 * image_width,
                    y2 / 1000 * image_height,
                ]
            )
        return boxes


# ---------------------------------------------------------------------------
# Device & model helpers
# ---------------------------------------------------------------------------


def select_device() -> tuple[str, torch.dtype]:
    """Select best available torch device and matching dtype."""
    if torch.cuda.is_available():
        return "cuda", torch.bfloat16
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps", torch.float16
    return "cpu", torch.float32


def announce_device(device: str) -> None:
    """Print device selection at startup (user-facing)."""
    print(f"Using device: {device}")


def _ensure_decord_stub() -> None:
    """Register a decord stub when pip wheels are unavailable (macOS arm64).

    LocateAnything lists decord as a dependency for video inputs; this spike
    uses images only, so a minimal stub satisfies the import check.
    """
    import importlib.util
    import types

    try:
        import decord  # noqa: F401
        return
    except ImportError:
        pass

    if "decord" in sys.modules:
        return

    decord_mod = types.ModuleType("decord")
    decord_mod.__version__ = "0.6.0"
    decord_mod.__spec__ = importlib.util.spec_from_loader(
        "decord", loader=None, origin="decord-stub"
    )
    bridge_mod = types.ModuleType("decord.bridge")
    bridge_mod.__spec__ = importlib.util.spec_from_loader(
        "decord.bridge", loader=None, origin="decord-stub"
    )
    torch_bridge = types.ModuleType("decord.bridge.torch")
    torch_bridge.__spec__ = importlib.util.spec_from_loader(
        "decord.bridge.torch", loader=None, origin="decord-stub"
    )
    sys.modules["decord"] = decord_mod
    sys.modules["decord.bridge"] = bridge_mod
    sys.modules["decord.bridge.torch"] = torch_bridge
    logger.info("Using decord stub (image-only spike; video decoding not required)")


def download_model_only() -> None:
    """Download and cache model weights without running inference."""
    _ensure_decord_stub()
    from transformers import AutoModel, AutoProcessor, AutoTokenizer

    logger.info("Downloading %s ...", MODEL_ID)
    AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
    logger.info("Model cached successfully.")


def load_worker() -> LocateAnythingWorker:
    """Load LocateAnything worker or exit with helpful message."""
    try:
        device, dtype = select_device()
        announce_device(device)
        return LocateAnythingWorker(MODEL_ID, device=device, dtype=dtype)
    except Exception as exc:
        logger.error("Failed to load model: %s", exc)
        print(
            "Model not found. Run: python eval/spikes/locate_anything_spike.py "
            "--download-only to cache the model weights first."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# PDF & geometry
# ---------------------------------------------------------------------------


def find_pdfs(pdf_dir: Path, exclude_archived: bool = True) -> list[Path]:
    """Glob PDF files in directory."""
    if not pdf_dir.exists():
        return []
    paths = sorted(pdf_dir.glob("*.pdf"))
    if exclude_archived:
        paths = [p for p in paths if p.name not in GOLDEN_PDF_EXCLUDE]
    return paths


def rasterize_pdf(pdf_path: Path, dpi: int = RASTER_DPI) -> list[Image.Image]:
    """Rasterize all pages of a PDF to PIL RGB images."""
    from pdf2image import convert_from_path

    return convert_from_path(str(pdf_path), dpi=dpi)


def compute_iou(box_a: list[float], box_b: list[float]) -> float:
    """Compute intersection-over-union for two boxes [x1,y1,x2,y2]."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def max_pairwise_iou(
    boxes_a: list[list[float]], boxes_b: list[list[float]]
) -> float:
    """Maximum IoU between any box pair from two lists."""
    if not boxes_a or not boxes_b:
        return 0.0
    return max(compute_iou(a, b) for a in boxes_a for b in boxes_b)


def run_distinction_test(
    electrical_boxes: list[list[float]],
    abs_max_boxes: list[list[float]],
) -> dict[str, Any]:
    """Evaluate whether electrical vs abs-max detections are spatially distinct."""
    both_detected = bool(electrical_boxes) and bool(abs_max_boxes)
    if not both_detected:
        return {
            "both_detected": False,
            "iou": None,
            "result": "N/A",
        }

    iou = max_pairwise_iou(electrical_boxes, abs_max_boxes)
    if iou > DISTINCTION_IOU_FAILURE:
        result = "DISTINCTION_FAILURE"
    elif iou < DISTINCTION_IOU_SUCCESS:
        result = "DISTINCTION_SUCCESS"
    else:
        result = "DISTINCTION_FAILURE"

    return {
        "both_detected": True,
        "iou": round(iou, 4),
        "result": result,
    }


# ---------------------------------------------------------------------------
# Detection pipeline
# ---------------------------------------------------------------------------


@dataclass
class QueryDetection:
    """Detection result for one query on one page."""

    detected: bool
    num_boxes: int
    boxes: list[list[float]]
    inference_ms: float
    used_multi_detect: bool = False


def _empty_detection() -> dict[str, Any]:
    return {"detected": False, "num_boxes": 0, "boxes": []}


def _detection_to_dict(det: QueryDetection) -> dict[str, Any]:
    return {
        "detected": det.detected,
        "num_boxes": det.num_boxes,
        "boxes": [[round(c, 1) for c in box] for box in det.boxes],
        "inference_ms": round(det.inference_ms, 1),
    }


def _try_multi_category_detect(
    worker: LocateAnythingWorker,
    image: Image.Image,
    query_keys: list[str],
) -> tuple[dict[str, QueryDetection], float, bool]:
    """Attempt one forward pass with detect() for all categories."""
    categories = [QUERY_SET[k] for k in query_keys]
    width, height = image.size

    t0 = time.perf_counter()
    try:
        result = worker.detect(image, categories, verbose=False)
    except Exception as exc:
        logger.warning("Multi-category detect() failed: %s", exc)
        return {}, 0.0, False
    elapsed_ms = (time.perf_counter() - t0) * 1000

    answer = result.get("answer", "")
    per_key = _parse_multi_category_answer(answer, query_keys, categories, width, height)

    if per_key and all(per_key.get(k) is not None for k in query_keys):
        detections: dict[str, QueryDetection] = {}
        per_query_ms = elapsed_ms / max(len(query_keys), 1)
        for key in query_keys:
            boxes = per_key.get(key, [])
            detections[key] = QueryDetection(
                detected=len(boxes) > 0,
                num_boxes=len(boxes),
                boxes=boxes,
                inference_ms=per_query_ms,
                used_multi_detect=True,
            )
        return detections, elapsed_ms, True

    logger.info("Multi-category parse incomplete; falling back to sequential queries.")
    return {}, elapsed_ms, False


def _parse_multi_category_answer(
    answer: str,
    query_keys: list[str],
    categories: list[str],
    width: int,
    height: int,
) -> dict[str, list[list[float]]] | None:
    """Try to assign boxes to categories from a multi-detect answer."""
    all_boxes = LocateAnythingWorker.parse_boxes(answer, width, height)
    if not all_boxes:
        return {key: [] for key in query_keys}

    # Strategy 1: split answer by </c> category markers and parse each segment
    segments = re.split(r"</c>", answer)
    if len(segments) >= len(categories):
        result: dict[str, list[list[float]]] = {}
        for key, segment in zip(query_keys, segments, strict=False):
            result[key] = LocateAnythingWorker.parse_boxes(segment, width, height)
        if any(result.values()):
            return result

    # Strategy 2: look for category text anchors in answer
    result = {}
    for key, cat in zip(query_keys, categories, strict=True):
        idx = answer.lower().find(cat.lower()[:30])
        if idx >= 0:
            window = answer[idx : idx + 800]
            result[key] = LocateAnythingWorker.parse_boxes(window, width, height)
        else:
            result[key] = []

    if sum(len(v) for v in result.values()) == len(all_boxes):
        return result

    # Cannot reliably attribute — signal failure
    return None


def _sequential_detect(
    worker: LocateAnythingWorker,
    image: Image.Image,
    query_keys: list[str],
) -> tuple[dict[str, QueryDetection], float]:
    """Run ground_multi per query sequentially."""
    width, height = image.size
    detections: dict[str, QueryDetection] = {}
    total_ms = 0.0

    for key in query_keys:
        phrase = QUERY_SET[key]
        t0 = time.perf_counter()
        result = worker.ground_multi(image, phrase, verbose=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_ms += elapsed_ms

        boxes = LocateAnythingWorker.parse_boxes(result.get("answer", ""), width, height)
        detections[key] = QueryDetection(
            detected=len(boxes) > 0,
            num_boxes=len(boxes),
            boxes=boxes,
            inference_ms=elapsed_ms,
            used_multi_detect=False,
        )
        logger.debug(
            "  %s: %d boxes in %.0f ms", key, len(boxes), elapsed_ms
        )

    return detections, total_ms


def detect_all_queries(
    worker: LocateAnythingWorker,
    image: Image.Image,
) -> tuple[dict[str, QueryDetection], float, str]:
    """Run all queries on one page; return detections, total ms, inference mode."""
    query_keys = list(QUERY_SET.keys())

    multi_dets, multi_ms, multi_ok = _try_multi_category_detect(
        worker, image, query_keys
    )
    if multi_ok:
        return multi_dets, multi_ms, "multi_detect"

    seq_dets, seq_ms = _sequential_detect(worker, image, query_keys)
    return seq_dets, seq_ms, "sequential_ground_multi"


# ---------------------------------------------------------------------------
# Visualization & reporting
# ---------------------------------------------------------------------------


def annotate_page(
    image: Image.Image,
    detections: dict[str, QueryDetection],
    output_path: Path,
) -> None:
    """Draw all query bounding boxes on one annotated PNG."""
    bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    for key, det in detections.items():
        if not det.boxes:
            continue
        color = QUERY_COLORS.get(key, (255, 255, 255))
        for box in det.boxes:
            x1, y1, x2, y2 = (int(v) for v in box)
            cv2.rectangle(bgr, (x1, y1), (x2, y2), color, 2)
            label = key[:28]
            cv2.putText(
                bgr,
                label,
                (x1, max(y1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), bgr)


def _build_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Compute aggregate summary statistics."""
    query_keys = list(QUERY_SET.keys())
    total_pages = 0
    total_inference_ms = 0.0
    query_hits: dict[str, int] = {k: 0 for k in query_keys}
    distinction = {"success": 0, "failure": 0, "na": 0}

    for ds_data in report["datasheets"].values():
        for page_data in ds_data["pages"].values():
            total_pages += 1
            total_inference_ms += page_data.get("inference_ms", 0)

            for key in query_keys:
                if page_data.get(key, {}).get("detected"):
                    query_hits[key] += 1

            dt = page_data.get("distinction_test", {})
            result = dt.get("result", "N/A")
            if result == "DISTINCTION_SUCCESS":
                distinction["success"] += 1
            elif result == "DISTINCTION_FAILURE":
                distinction["failure"] += 1
            else:
                distinction["na"] += 1

    per_query_rate = {
        k: (query_hits[k] / total_pages if total_pages else 0.0) for k in query_keys
    }

    return {
        "per_query_detection_rate": {
            k: round(v, 4) for k, v in per_query_rate.items()
        },
        "distinction_test_results": distinction,
        "avg_inference_time_per_page_ms": round(
            total_inference_ms / total_pages if total_pages else 0.0, 1
        ),
        "total_pages_processed": total_pages,
        "total_inference_time_ms": round(total_inference_ms, 1),
    }


def _recommendation(summary: dict[str, Any]) -> tuple[str, str, str]:
    """Derive YES/NO/CONDITIONAL recommendation from spike results."""
    rates = summary["per_query_detection_rate"]
    dist = summary["distinction_test_results"]
    avg_ms = summary["avg_inference_time_per_page_ms"]

    core_queries = [
        "electrical_characteristics_table",
        "absolute_maximum_ratings_table",
        "pinout_table",
    ]
    core_rate_ok = all(rates.get(q, 0) >= 0.5 for q in core_queries)
    distinction_ok = dist["failure"] == 0 and dist["success"] > 0
    distinction_bad = dist["failure"] > dist["success"] and dist["failure"] > 0

    if distinction_bad:
        return (
            "NO",
            (
                "LocateAnything frequently conflates electrical characteristics "
                "and absolute maximum ratings regions (DISTINCTION_FAILURE), "
                "which is the primary Phase 1 requirement YOLO + classify_section "
                "must satisfy separately today."
            ),
            "",
        )

    if core_rate_ok and distinction_ok and avg_ms < 60_000:
        return (
            "YES",
            (
                "Core table queries detected on most pages, electrical vs abs-max "
                "regions are spatially distinct where both appear, and per-page "
                "latency is acceptable for offline batch processing."
            ),
            "",
        )

    conditions: list[str] = []
    if not core_rate_ok:
        conditions.append("detection rate for core table types must exceed 50% per page")
    if not distinction_ok:
        conditions.append(
            "distinction test must show zero DISTINCTION_FAILURE pages where both "
            "electrical and abs-max tables are detected"
        )
    if avg_ms >= 60_000:
        conditions.append("per-page inference must drop below 60s for production use")

    reason = (
        "Promising open-vocabulary layout detection, but gaps remain in detection "
        "coverage, electrical/abs-max separation, or inference speed."
    )
    return ("CONDITIONAL", reason, "; ".join(conditions) if conditions else "TBD")


def write_report_md(
    report: dict[str, Any],
    output_path: Path,
) -> None:
    """Write human-readable markdown summary."""
    summary = report["summary"]
    dist = summary["distinction_test_results"]
    rec, reason, condition = _recommendation(summary)

    lines = [
        "# LocateAnything-3B Phase 1 Spike Results",
        "",
        f"- **Model:** {report['model']}",
        f"- **Device:** {report['device']}",
        f"- **Total pages:** {summary['total_pages_processed']}",
        f"- **Total runtime:** {report.get('total_runtime_s', 0):.1f}s",
        "",
        "## Detection Rate Per Query",
        "",
        "| Query | Detection Rate |",
        "|-------|----------------|",
    ]

    for key, rate in summary["per_query_detection_rate"].items():
        lines.append(f"| `{key}` | {rate * 100:.1f}% |")

    lines.extend(
        [
            "",
            "## Distinction Test (Electrical vs Abs-Max)",
            "",
            f"- **SUCCESS:** {dist['success']} pages",
            f"- **FAILURE:** {dist['failure']} pages",
            f"- **N/A:** {dist['na']} pages",
            "",
        ]
    )

    failed_pages: list[str] = []
    for ds_name, ds_data in report["datasheets"].items():
        for page_num, page_data in ds_data["pages"].items():
            dt = page_data.get("distinction_test", {})
            if dt.get("result") == "DISTINCTION_FAILURE":
                failed_pages.append(
                    f"- `{ds_name}` page {page_num} (IoU={dt.get('iou')})"
                )

    if failed_pages:
        lines.append("### Failed Pages")
        lines.extend(failed_pages)
        lines.append("")
    else:
        lines.append("No DISTINCTION_FAILURE pages recorded.")
        lines.append("")

    lines.extend(
        [
            "## Inference Speed",
            "",
            f"- **Avg per page:** {summary['avg_inference_time_per_page_ms']:.0f} ms",
            f"- **Total inference:** {summary.get('total_inference_time_ms', 0):.0f} ms",
            "",
        ]
    )

    if report.get("peak_vram_gb") is not None:
        lines.append(f"- **Peak VRAM (CUDA):** {report['peak_vram_gb']:.2f} GB")
        lines.append("")

    lines.extend(
        [
            "## Recommendation",
            "",
            f"**Replaces YOLOv8n for Phase 1:** {rec}",
            f"**Reason:** {reason}",
        ]
    )
    if condition:
        lines.append(f"**Condition (if CONDITIONAL):** {condition}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main spike runner
# ---------------------------------------------------------------------------


def run_spike(
    pdf_paths: list[Path],
    output_dir: Path,
    dpi: int = RASTER_DPI,
    max_side: int | None = None,
) -> dict[str, Any]:
    """Execute the full LocateAnything spike evaluation."""
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    worker = load_worker()
    device, _ = select_device()
    if max_side is None:
        max_side = default_max_side(device)

    report: dict[str, Any] = {
        "model": MODEL_ID,
        "device": device,
        "raster_dpi": dpi,
        "max_side_px": max_side,
        "datasheets": {},
    }

    spike_t0 = time.perf_counter()

    for pdf_path in pdf_paths:
        ds_name = pdf_path.name
        logger.info("Processing %s", ds_name)

        try:
            pages = rasterize_pdf(pdf_path, dpi=dpi)
        except Exception as exc:
            if "poppler" in str(exc).lower() or "pdfinfo" in str(exc).lower():
                print(
                    "Poppler not found. Install with: brew install poppler (macOS) "
                    "or apt install poppler-utils (Linux)"
                )
                sys.exit(1)
            raise

        ds_pages: dict[str, Any] = {}

        for page_idx, page_image in enumerate(pages, start=1):
            page_image = page_image.convert("RGB")
            infer_image, original_size = prepare_inference_image(page_image, max_side)
            logger.info("  Page %d/%d", page_idx, len(pages))

            detections, page_ms, mode = detect_all_queries(worker, infer_image)

            page_result: dict[str, Any] = {
                "inference_mode": mode,
                "inference_ms": round(page_ms, 1),
                "original_size": list(original_size),
                "inference_size": list(infer_image.size),
            }

            for key, det in detections.items():
                page_result[key] = _detection_to_dict(det)

            elec_boxes = detections["electrical_characteristics_table"].boxes
            abs_boxes = detections["absolute_maximum_ratings_table"].boxes
            page_result["distinction_test"] = run_distinction_test(
                elec_boxes, abs_boxes
            )

            ds_pages[str(page_idx)] = page_result

            has_any = any(det.num_boxes > 0 for det in detections.values())
            if has_any:
                annotated_name = f"{pdf_path.stem}_page_{page_idx:03d}_annotated.png"
                annotate_page(
                    infer_image,
                    detections,
                    output_dir / annotated_name,
                )

        report["datasheets"][ds_name] = {"pages": ds_pages}

    report["total_runtime_s"] = round(time.perf_counter() - spike_t0, 2)
    report["summary"] = _build_summary(report)

    if torch.cuda.is_available():
        peak_bytes = torch.cuda.max_memory_allocated()
        report["peak_vram_gb"] = round(peak_bytes / (1024**3), 2)
    else:
        report["peak_vram_gb"] = None

    return report


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="LocateAnything-3B Phase 1 layout detection spike"
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=DEFAULT_PDF_DIR,
        help="Directory containing golden PDF datasheets",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for annotated PNGs and reports",
    )
    parser.add_argument(
        "--single-pdf",
        type=Path,
        default=None,
        help="Run spike on a single PDF file",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download and cache model weights, then exit",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=RASTER_DPI,
        help="PDF rasterization DPI (default: 300)",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=None,
        help="Max page image side in pixels for inference (auto by device if unset)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    args = parse_args()
    os.chdir(PROJECT_ROOT)

    if args.download_only:
        try:
            download_model_only()
        except Exception as exc:
            logger.error("Download failed: %s", exc)
            print(
                "Model not found. Run: python eval/spikes/locate_anything_spike.py "
                "--download-only to cache the model weights first."
            )
            sys.exit(1)
        return

    if args.single_pdf:
        if not args.single_pdf.exists():
            logger.error("PDF not found: %s", args.single_pdf)
            sys.exit(1)
        pdf_paths = [args.single_pdf]
    else:
        pdf_dir = args.pdf_dir
        if not pdf_dir.exists() or not find_pdfs(pdf_dir):
            print(
                "Place the 5 golden datasheet PDFs in corpus/golden/ and re-run."
            )
            sys.exit(1)
        pdf_paths = find_pdfs(pdf_dir)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    report = run_spike(
        pdf_paths,
        output_dir,
        dpi=args.dpi,
        max_side=args.max_side,
    )

    json_path = output_dir / "report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Wrote %s", json_path)

    md_path = output_dir / "report.md"
    write_report_md(report, md_path)
    logger.info("Wrote %s", md_path)

    summary = report["summary"]
    logger.info(
        "Spike complete: %d pages, avg %.0f ms/page, distinction success=%d failure=%d",
        summary["total_pages_processed"],
        summary["avg_inference_time_per_page_ms"],
        summary["distinction_test_results"]["success"],
        summary["distinction_test_results"]["failure"],
    )


if __name__ == "__main__":
    main()
