"""Unit tests for Phase 4 master validator."""

from src.phase4_validate.validator import run_full_validation
from tests.fixtures.phase3_mock_outputs import (
    mock_component_with_inverted_values,
    mock_component_with_low_confidence,
    mock_tlv7021_component_datasheet,
)


def test_validation_passes_clean_data() -> None:
    datasheet = mock_tlv7021_component_datasheet()
    result = run_full_validation(datasheet)
    assert result.passed is True
    assert result.component_id == "TLV7021"


def test_validation_catches_inverted_min_max() -> None:
    datasheet = mock_component_with_inverted_values()
    result = run_full_validation(datasheet)
    assert result.passed is False
    assert any(e.level == "CRITICAL" for e in result.errors)


def test_validation_warns_on_low_confidence() -> None:
    datasheet = mock_component_with_low_confidence()
    result = run_full_validation(datasheet)
    assert result.confidence_score < 0.85
    assert result.review_required is True


def test_validation_has_timestamp() -> None:
    result = run_full_validation(mock_tlv7021_component_datasheet())
    assert result.timestamp.endswith("Z")
