"""Unit tests for electrical parameter extraction."""

from tests.fixtures.phase2_mock_outputs import (
    mock_ina219_phase2_output,
    mock_lm5176_phase2_output,
    mock_sn74_phase2_output,
    mock_tlv7021_phase2_output,
)
from src.phase3_extract.parameter_extractor import (
    extract_electrical_parameters,
    infer_param_type,
)


def _elec_grid(phase2_out):
    return [g for g in phase2_out.grids if g.section_type == "electrical_characteristics"][0]


def test_extract_electrical_parameters_from_mock() -> None:
    phase2_out = mock_tlv7021_phase2_output()
    params = extract_electrical_parameters(_elec_grid(phase2_out), "TLV7021")
    assert len(params) > 0
    v_cc = next(p for p in params if p.name == "V_CC")
    assert v_cc.min_value is not None
    assert v_cc.min_value.value == 2.0
    assert v_cc.typ_value is not None
    assert v_cc.typ_value.value == 3.3
    assert v_cc.max_value is not None
    assert v_cc.max_value.value == 5.5


def test_extract_with_footnotes() -> None:
    phase2_out = mock_lm5176_phase2_output()
    footnote_map = phase2_out.metadata.get("footnote_map", {})
    params = extract_electrical_parameters(
        _elec_grid(phase2_out), "LM5176", footnote_map
    )
    param_with_note = [
        p
        for p in params
        if any(
            v and v.footnote
            for v in (p.min_value, p.typ_value, p.max_value)
        )
    ]
    assert len(param_with_note) > 0


def test_unit_normalization_in_extraction() -> None:
    phase2_out = mock_sn74_phase2_output()
    params = extract_electrical_parameters(_elec_grid(phase2_out), "SN74")
    for param in params:
        for value in (param.min_value, param.typ_value, param.max_value):
            if value:
                assert value.unit in ["V", "mA", "Ω", "pF", "ns", "°C", "dB", "%", "mW", "MHz"]


def test_sparse_cells_handled() -> None:
    phase2_out = mock_ina219_phase2_output()
    params = extract_electrical_parameters(_elec_grid(phase2_out), "INA219")
    sparse_params = [
        p
        for p in params
        if p.min_value is None or p.max_value is None
    ]
    assert len(sparse_params) > 0


def test_infer_param_type() -> None:
    assert infer_param_type("V_CC") == "voltage"
    assert infer_param_type("I_CC") == "current"
    assert infer_param_type("R_SENSE") == "resistance"
    assert infer_param_type("C_LOAD") == "capacitance"
