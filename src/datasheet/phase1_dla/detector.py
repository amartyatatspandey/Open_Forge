"""YOLOv8n-DocLayNet table and footnote detection for Phase 1 DLA.

Performs inference using the YOLOv8n model fine-tuned on DocLayNet dataset.
Detects table regions, section headings, and footnote markers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image
from ultralytics import YOLO  # type: ignore[attr-defined]

from src.config import get_config

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# DocLayNet class indices (YOLO model output)
# These map to the classes in the DocLayNet dataset
CLASS_TABLE: int = 3  # Table region
CLASS_FOOTNOTE: int = 4  # Footnote marker
CLASS_CAPTION: int = 2  # Table caption/heading


def _load_yolo_model(config: Config) -> YOLO:
    """Load YOLOv8n-DocLayNet model from configured path.

    Args:
        config: Application configuration

    Returns:
        Loaded YOLO model

    Raises:
        FileNotFoundError: If model file does not exist at configured path
    """
    model_path = config.get_model_path("yolov8n_doclaynet")

    if not model_path.exists():
        raise FileNotFoundError(
            f"YOLOv8 model not found at: {model_path}\n"
            f"Expected path from config: {model_path}\n"
            f"Please download the model or update the configuration."
        )

    logger.info(f"Loading YOLO model from {model_path}")
    return YOLO(str(model_path))


def _detect_tables(
    image: Image.Image,
    model: YOLO,
    confidence_threshold: float = 0.25,
) -> list[dict[str, Any]]:
    """Detect table regions in a rasterized PDF page.

    Args:
        image: PIL Image of the PDF page
        model: Loaded YOLO model
        confidence_threshold: Minimum detection confidence

    Returns:
        List of detection dicts with keys:
        - bounding_box: (x1, y1, x2, y2) in pixels
        - confidence: detection confidence score
        - class_id: YOLO class index
    """
    results = model(image, verbose=False)
    detections = []

    for result in results:
        if result.boxes is None:
            continue

        boxes = result.boxes.cpu().numpy()
        for box in boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])

            if confidence < confidence_threshold:
                continue

            # Only include table, caption, and footnote classes
            if class_id not in (CLASS_TABLE, CLASS_FOOTNOTE, CLASS_CAPTION):
                continue

            x1, y1, x2, y2 = box.xyxy[0].astype(int)

            detections.append({
                "bounding_box": (int(x1), int(y1), int(x2), int(y2)),
                "confidence": confidence,
                "class_id": class_id,
            })

    logger.debug(f"Detected {len(detections)} regions on page")
    return detections


def _crop_region(
    image: Image.Image,
    bounding_box: tuple[int, int, int, int],
) -> bytes:
    """Crop a region from an image and return as PNG bytes.

    Args:
        image: Source PIL Image
        bounding_box: (x1, y1, x2, y2) crop coordinates

    Returns:
        Cropped image as PNG-encoded bytes
    """
    x1, y1, x2, y2 = bounding_box
    cropped = image.crop((x1, y1, x2, y2))

    import io

    buffer = io.BytesIO()
    cropped.save(buffer, format="PNG")
    return buffer.getvalue()


def _detect_all_pages(
    pages: list[tuple[int, Image.Image]],
    model: YOLO,
    confidence_threshold: float = 0.25,
) -> dict[int, list[dict[str, Any]]]:
    """Detect regions on all rasterized pages.

    Args:
        pages: List of (page_number, PIL.Image) tuples
        model: Loaded YOLO model
        confidence_threshold: Minimum detection confidence

    Returns:
        Dictionary mapping page_number -> list of detections
    """
    all_detections: dict[int, list[dict[str, Any]]] = {}

    for page_num, image in pages:
        detections = _detect_tables(image, model, confidence_threshold)
        all_detections[page_num] = detections
        logger.debug(f"Page {page_num}: {len(detections)} detections")

    return all_detections
