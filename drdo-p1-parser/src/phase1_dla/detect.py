"""Phase 1: YOLOv8 table and footnote detection."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from src.config import Config, get_config
from src.schemas.pipeline import BoundingBox
from src.utils.exceptions import DLAError

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    """A single detected layout region."""

    bbox: BoundingBox
    confidence: float
    label: str


@dataclass
class PageDetections:
    """All detections on one page."""

    tables: list[Detection] = field(default_factory=list)
    footnotes: list[Detection] = field(default_factory=list)


class TableDetector:
    """YOLOv8 DocLayNet detector — loads model once, reuses for all pages."""

    def __init__(self, model_path: Path | None = None, config: Config | None = None) -> None:
        """Initialize detector and load YOLO weights.

        Args:
            model_path: Override path to YOLO weights.
            config: Optional config override.

        Raises:
            DLAError: If model weights are missing or ultralytics unavailable.
        """
        self._config = config or get_config()
        self._model_path = model_path or self._config.models.dla_model_path
        self._confidence_min = self._config.phase1_dla.detection_confidence_min
        self._model = None

        if not self._model_path.exists():
            raise DLAError(
                f"YOLO model weights not found at {self._model_path}. "
                "Run: python scripts/download_models.py --model yolov8_doclaynets"
            )

        try:
            from ultralytics import YOLO

            self._model = YOLO(str(self._model_path))
            logger.info("Loaded YOLO model from %s", self._model_path)
        except ImportError as exc:
            raise DLAError(f"ultralytics not installed: {exc}") from exc

    def detect_page(self, image_bytes: bytes) -> PageDetections:
        """Detect tables and footnotes on a single page image.

        Args:
            image_bytes: PNG bytes for one page.

        Returns:
            PageDetections with filtered table and footnote regions.
        """
        if self._model is None:
            raise DLAError("YOLO model not loaded")

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        results = self._model.predict(image, verbose=False)

        page_detections = PageDetections()
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                confidence = float(box.conf[0])
                if confidence < self._confidence_min:
                    continue
                cls_id = int(box.cls[0])
                label = self._model.names.get(cls_id, "")
                label_lower = label.lower()
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                detection = Detection(
                    bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    confidence=confidence,
                    label=label,
                )
                if "table" in label_lower:
                    page_detections.tables.append(detection)
                elif "footnote" in label_lower:
                    page_detections.footnotes.append(detection)

        logger.debug(
            "Detected %d tables, %d footnotes",
            len(page_detections.tables),
            len(page_detections.footnotes),
        )
        return page_detections


def crop_region(image_bytes: bytes, bbox: BoundingBox) -> bytes:
    """Crop a region from a page image and return PNG bytes.

    Args:
        image_bytes: Full page PNG bytes.
        bbox: Region to crop.

    Returns:
        PNG bytes of the cropped region.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    x1 = max(0, min(bbox.x1, width))
    y1 = max(0, min(bbox.y1, height))
    x2 = max(0, min(bbox.x2, width))
    y2 = max(0, min(bbox.y2, height))
    if x2 <= x1 or y2 <= y1:
        raise DLAError(f"Invalid crop bbox: ({x1},{y1},{x2},{y2})")
    cropped = image.crop((x1, y1, x2, y2))
    buffer = io.BytesIO()
    cropped.save(buffer, format="PNG")
    return buffer.getvalue()
