"""Integration tests for Phase 1 end-to-end pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.phase1_dla.runner import run_phase1
from src.schemas.pipeline import Phase1Output

GOLDEN_PDF = Path("corpus/golden/TI_TLV7021_v1.pdf")
MODEL_PATH = Path("models/yolov8_doclaynets.pt")


@pytest.mark.integration
@pytest.mark.skipif(
    not GOLDEN_PDF.exists() or not MODEL_PATH.exists(),
    reason="Requires golden PDF and YOLO weights",
)
def test_phase1_end_to_end_tlv7021() -> None:
    """Run full Phase 1 on TLV7021 and verify output structure."""
    output = run_phase1(GOLDEN_PDF)
    assert isinstance(output, Phase1Output)
    assert len(output.detected_tables) >= 1
    assert len(output.tables) == len(output.detected_tables)
    section_types = {t.section_type for t in output.detected_tables}
    assert "electrical_characteristics" in section_types or "absolute_maximum_ratings" in section_types
