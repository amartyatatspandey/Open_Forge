"""Mock Phase 3 outputs for Phase 4 validation tests."""

from __future__ import annotations

from src.phase3_extract.runner import run_phase3
from src.schemas.datasheet import (
    ComponentDatasheet,
    DatasheetSection,
    ElectricalParameter,
    ExtractedValue,
)
from tests.fixtures.phase2_mock_outputs import (
    all_golden_phase2_outputs,
    mock_tlv7021_phase2_output,
)


def mock_tlv7021_component_datasheet() -> ComponentDatasheet:
    """TLV7021 ComponentDatasheet from Phase 3 mock pipeline."""
    return run_phase3(mock_tlv7021_phase2_output())


def all_golden_phase3_outputs() -> dict[str, ComponentDatasheet]:
    """Run Phase 3 on all 5 golden Phase 2 mocks."""
    return {
        component_id: run_phase3(phase2_output)
        for component_id, phase2_output in all_golden_phase2_outputs().items()
    }


def mock_component_with_inverted_values() -> ComponentDatasheet:
    """Synthetic datasheet with min > max (CRITICAL ordering failure)."""
    base = mock_tlv7021_component_datasheet()
    bad_param = ElectricalParameter(
        name="V_OUT",
        parameter_type="voltage",
        min_value=ExtractedValue(
            raw_text="5.0",
            value=5.0,
            unit="V",
            confidence=0.95,
            source="manual_review",
        ),
        max_value=ExtractedValue(
            raw_text="0.5",
            value=0.5,
            unit="V",
            confidence=0.95,
            source="manual_review",
        ),
    )
    sections = list(base.sections)
    for section in sections:
        if section.section_type == "electrical_characteristics":
            section.parameters.append(bad_param)
            break
    else:
        sections.append(
            DatasheetSection(
                section_type="electrical_characteristics",
                page_range=(1, 1),
                table_confidence=0.9,
                parameters=[bad_param],
            )
        )
    return base.model_copy(update={"sections": sections})


def mock_component_with_low_confidence() -> ComponentDatasheet:
    """Synthetic datasheet with confidence below warn_downstream threshold."""
    low_param = ElectricalParameter(
        name="I_CC",
        parameter_type="current",
        typ_value=ExtractedValue(
            raw_text="0.8",
            value=0.8,
            unit="mA",
            confidence=0.50,
            source="manual_review",
        ),
    )
    return ComponentDatasheet(
        component_id="LOW_CONF",
        manufacturer="Texas Instruments",
        extraction_timestamp="2026-06-12T00:00:00Z",
        sections=[
            DatasheetSection(
                section_type="electrical_characteristics",
                page_range=(1, 1),
                table_confidence=0.9,
                parameters=[low_param],
            ),
        ],
    )
