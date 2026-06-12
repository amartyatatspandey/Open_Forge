"""Unit tests for Phase 1 detector."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.phase1_dla.detect import Detection, PageDetections, TableDetector, crop_region
from src.schemas.pipeline import BoundingBox
from src.utils.exceptions import DLAError

GOLDEN_PDF = Path("corpus/golden/TI_TLV7021_v1.pdf")
MODEL_PATH = Path("models/yolov8_doclaynets.pt")


def _make_page_png() -> bytes:
    """Create a minimal white page PNG for testing."""
    image = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_crop_region_returns_png_bytes() -> None:
    """Crop helper returns valid PNG bytes."""
    page = _make_page_png()
    bbox = BoundingBox(x1=10, y1=20, x2=200, y2=300)
    cropped = crop_region(page, bbox)
    assert cropped[:8] == b"\x89PNG\r\n\x1a\n"


def test_table_detector_missing_weights_raises() -> None:
    """Missing model weights should raise DLAError."""
    with pytest.raises(DLAError, match="weights not found"):
        TableDetector(model_path=Path("models/nonexistent.pt"))


@patch("ultralytics.YOLO")
@pytest.mark.skipif(not MODEL_PATH.exists(), reason="YOLO weights not present")
def test_detect_page_filters_tables_and_footnotes(mock_yolo_cls: MagicMock) -> None:
    """Mock YOLO and verify table/footnote filtering."""
    mock_model = MagicMock()
    mock_model.names = {0: "Table", 1: "Footnote", 2: "Text"}
    mock_boxes = MagicMock()
    mock_box_table = MagicMock()
    mock_box_table.conf = [0.95]
    mock_box_table.cls = [0]
    mock_xyxy_table = MagicMock()
    mock_xyxy_table.tolist.return_value = [10.0, 20.0, 200.0, 300.0]
    mock_box_table.xyxy = [mock_xyxy_table]
    mock_box_fn = MagicMock()
    mock_box_fn.conf = [0.88]
    mock_box_fn.cls = [1]
    mock_xyxy_fn = MagicMock()
    mock_xyxy_fn.tolist.return_value = [10.0, 400.0, 400.0, 450.0]
    mock_box_fn.xyxy = [mock_xyxy_fn]
    mock_boxes.__iter__ = MagicMock(return_value=iter([mock_box_table, mock_box_fn]))
    mock_result = MagicMock()
    mock_result.boxes = mock_boxes
    mock_model.predict.return_value = [mock_result]
    mock_yolo_cls.return_value = mock_model

    detector = TableDetector(model_path=MODEL_PATH)
    detections = detector.detect_page(_make_page_png())

    assert isinstance(detections, PageDetections)
    assert len(detections.tables) == 1
    assert len(detections.footnotes) == 1
    assert detections.tables[0].label == "Table"
    assert isinstance(detections.tables[0], Detection)


@pytest.mark.integration
@pytest.mark.skipif(not GOLDEN_PDF.exists() or not MODEL_PATH.exists(), reason="Needs PDF+model")
def test_detect_real_page_finds_tables() -> None:
    """Integration: real YOLO on one rasterized page."""
    from src.phase1_dla.rasterize import rasterize_pdf

    pages = rasterize_pdf(GOLDEN_PDF)
    detector = TableDetector()
    detections = detector.detect_page(pages[0])
    assert len(detections.tables) >= 1
