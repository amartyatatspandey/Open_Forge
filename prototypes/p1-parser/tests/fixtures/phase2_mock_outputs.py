"""Mock Phase 2 outputs for Phase 3 + integration tests."""

from __future__ import annotations

from src.schemas.pipeline import GridMatrix, Phase2Output, SectionType


def mock_gridmatrix(
    rows: list[list[str]],
    section_type: SectionType = "electrical_characteristics",
    page_number: int = 1,
    confidence: float = 0.95,
    source: str = "mock_for_testing",
) -> GridMatrix:
    """Helper to create a GridMatrix from raw rows."""
    num_rows = len(rows)
    num_cols = max(len(row) for row in rows) if rows else 0
    normalized = [row + [""] * (num_cols - len(row)) for row in rows]
    return GridMatrix(
        rows=normalized,
        num_rows=num_rows,
        num_cols=num_cols,
        section_type=section_type,
        page_number=page_number,
        confidence=confidence,
        source=source,  # type: ignore[arg-type]
    )


def mock_sn74_electrical_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Min", "Typ", "Max", "Unit", "Conditions"],
            ["V_CC", "1.65", "3.3", "5.5", "V", "—"],
            ["I_CC", "—", "0.8", "2.0", "mA", "V_CC = 3.3V"],
            ["V_OL", "—", "0.2", "0.4", "V", "I_OL = 4 mA"],
        ],
        section_type="electrical_characteristics",
        page_number=5,
        confidence=0.98,
        source="vector_path_A",
    )


def mock_sn74_pinout_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Pin", "Name", "Type", "Description"],
            ["1", "1A", "Input", "Logic input"],
            ["2", "GND", "Ground", "Ground reference"],
            ["3", "1Y", "Output", "Logic output"],
            ["4", "V_CC", "Power", "Supply voltage"],
        ],
        section_type="pinout",
        page_number=3,
        confidence=0.99,
        source="vector_path_A",
    )


def mock_sn74_absolute_max() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Max", "Unit"],
            ["V_CC", "6.0", "V"],
            ["T_J", "125", "°C"],
            ["I_O", "±20", "mA"],
        ],
        section_type="absolute_maximum_ratings",
        page_number=4,
        confidence=0.97,
        source="vector_path_A",
    )


def mock_sn74_phase2_output() -> Phase2Output:
    pdf = "corpus/golden/TI_SN74LVC1G04_v1.pdf"
    return Phase2Output(
        pdf_path=pdf,
        grids=[
            mock_sn74_absolute_max(),
            mock_sn74_electrical_grid(),
            mock_sn74_pinout_grid(),
        ],
        metadata={"component_id": "SN74LVC1G04", "pdf_path": pdf},
    )


def mock_tlv7021_electrical_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Min", "Typ", "Max", "Unit", "Conditions"],
            ["V_CC", "2.0", "3.3", "5.5", "V", "—"],
            ["V_IN", "0", "—", "V_CC", "V", "—"],
            ["I_IN", "—", "0.5", "1.0", "µA", "V_IN = 0 or V_CC"],
            ["V_REF", "—", "1.2", "—", "V", "—"],
            ["V_OUT_H", "V_CC - 0.2", "V_CC", "—", "V", "I_OUT = -100 µA"],
            ["V_OUT_L", "—", "0", "0.2", "V", "I_OUT = 100 µA"],
            ["Delay", "—", "3.5", "5.0", "ns", "—"],
        ],
        section_type="electrical_characteristics",
        page_number=5,
        confidence=0.92,
        source="vlm_path_B",
    )


def mock_tlv7021_pinout_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Pin", "Name", "Alt Function", "Type", "Description"],
            ["1", "IN+", "—", "Analog In", "Non-inverting input"],
            ["2", "IN-", "VREF", "Analog In", "Inverting input / ref voltage"],
            ["3", "GND", "—", "Ground", "Ground reference"],
            ["4", "OUT", "GPIO", "Digital Out", "Open-drain output / general I/O"],
            ["5", "V_CC", "—", "Power", "Supply voltage"],
            ["6", "—", "—", "No Connect", "—"],
            ["7", "EN", "—", "Input", "Output enable (active high)"],
            ["8", "NC", "—", "No Connect", "—"],
        ],
        section_type="pinout",
        page_number=3,
        confidence=0.91,
        source="vlm_path_B",
    )


def mock_tlv7021_absolute_max() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Max", "Unit"],
            ["V_CC", "6.0", "V"],
            ["V_IN", "V_CC + 0.3", "V"],
            ["T_J", "150", "°C"],
            ["I_OUT", "±50", "mA"],
        ],
        section_type="absolute_maximum_ratings",
        page_number=4,
        confidence=0.96,
        source="vector_path_A",
    )


def mock_tlv7021_phase2_output() -> Phase2Output:
    pdf = "corpus/golden/TI_TLV7021_v1.pdf"
    return Phase2Output(
        pdf_path=pdf,
        grids=[
            mock_tlv7021_absolute_max(),
            mock_tlv7021_electrical_grid(),
            mock_tlv7021_pinout_grid(),
        ],
        metadata={"component_id": "TLV7021", "pdf_path": pdf},
    )


def mock_ina219_electrical_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Min", "Typ", "Max", "Unit", "Conditions"],
            ["V_BUS_MAX", "—", "26", "—", "V", "—"],
            ["V_SH_MAX", "—", "0.32", "—", "V", "—"],
            ["I_SH", "—", "1", "10", "mV", "At max current"],
            ["I_CC", "—", "0.8", "1.5", "mA", "Normal operation"],
            ["I_SLEEP", "—", "10", "20", "µA", "Sleep mode"],
            ["f_I2C", "—", "400", "—", "kHz", "I2C clock"],
            ["t_SETUP", "—", "5", "10", "ns", "SDA setup time"],
            ["t_HOLD", "—", "0", "—", "ns", "SDA hold time"],
            ["T_J", "-40", "25", "125", "°C", "—"],
            ["T_STORATE", "-65", "—", "150", "°C", "—"],
            ["PSRR", "—", "50", "—", "dB", "Supply rejection at 1 kHz"],
            ["THD", "—", "0.1", "0.3", "%", "—"],
        ],
        section_type="electrical_characteristics",
        page_number=6,
        confidence=0.88,
        source="vlm_path_B",
    )


def mock_ina219_pinout_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Pin", "Name", "Type", "Description"],
            ["1", "A0", "Input", "I2C address select bit 0"],
            ["2", "A1", "Input", "I2C address select bit 1"],
            ["3", "GND", "Ground", "Ground"],
            ["4", "SDA", "I/O", "I2C data (open-drain)"],
            ["5", "SCL", "Input", "I2C clock"],
            ["6", "V_IN-", "Analog In", "Shunt minus (current measurement)"],
            ["7", "V_IN+", "Analog In", "Shunt plus (current measurement)"],
            ["8", "V_CC", "Power", "3.3V or 5V supply"],
            ["9-16", "NC", "No Connect", "Not connected"],
        ],
        section_type="pinout",
        page_number=3,
        confidence=0.85,
        source="vlm_path_B",
    )


def mock_ina219_absolute_max() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Max", "Unit"],
            ["V_BUS", "32", "V"],
            ["V_SH", "0.4", "V"],
            ["T_J", "150", "°C"],
        ],
        section_type="absolute_maximum_ratings",
        page_number=4,
        confidence=0.94,
        source="vector_path_A",
    )


def mock_ina219_phase2_output() -> Phase2Output:
    pdf = "corpus/golden/TI_INA219_v1.pdf"
    return Phase2Output(
        pdf_path=pdf,
        grids=[
            mock_ina219_absolute_max(),
            mock_ina219_electrical_grid(),
            mock_ina219_pinout_grid(),
        ],
        metadata={"component_id": "INA219", "pdf_path": pdf},
    )


def mock_lm5176_electrical_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Min", "Typ", "Max", "Unit", "Conditions", "Notes"],
            ["V_IN", "4.5", "—", "20", "V", "—", "—"],
            ["V_OUT", "0.8", "3.3", "18", "V", "Programmable", "(1)"],
            ["I_OUT", "—", "—", "2.0", "A", "See notes", "(2)"],
            ["V_FB", "—", "0.6", "—", "V", "—", "—"],
            ["f_SW", "—", "500", "—", "kHz", "Switching freq", "—"],
            ["I_Q", "—", "1.5", "3.0", "mA", "Running", "—"],
            ["I_SLEEP", "—", "5", "10", "µA", "Shutdown", "—"],
            ["R_SENSE", "—", "—", "—", "mΩ", "External", "(3)"],
        ],
        section_type="electrical_characteristics",
        page_number=6,
        confidence=0.90,
        source="vlm_path_B",
    )


def mock_lm5176_pinout_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Pin", "Name", "Alt", "Type", "Description"],
            ["1", "V_IN", "—", "Power", "Input voltage"],
            ["2", "SW", "—", "Switch", "High-side switch node"],
            ["3", "GND", "—", "Ground", "Ground"],
            ["4", "FB", "—", "Analog In", "Feedback for output voltage"],
            ["5", "SS", "RAMP", "Input", "Soft-start / ramp control"],
            ["6", "RT", "CT", "Input", "Oscillator timing"],
            ["7", "EN", "MODE", "Input", "Enable / mode select"],
            ["8", "V_CC", "—", "Power", "Logic supply 5V"],
            ["9-16", "GND/NC", "—", "Ground/NC", "Ground or no connect"],
        ],
        section_type="pinout",
        page_number=3,
        confidence=0.89,
        source="vlm_path_B",
    )


def mock_lm5176_absolute_max() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Max", "Unit"],
            ["V_IN", "25", "V"],
            ["P_DISSIPATION", "2.0", "W"],
            ["T_J", "150", "°C"],
            ["I_SW", "3.0", "A"],
        ],
        section_type="absolute_maximum_ratings",
        page_number=5,
        confidence=0.93,
        source="vector_path_A",
    )


def mock_lm5176_phase2_output() -> Phase2Output:
    pdf = "corpus/golden/TI_LM5176_v1.pdf"
    return Phase2Output(
        pdf_path=pdf,
        grids=[
            mock_lm5176_absolute_max(),
            mock_lm5176_electrical_grid(),
            mock_lm5176_pinout_grid(),
        ],
        metadata={
            "component_id": "LM5176",
            "pdf_path": pdf,
            "footnote_map": {
                "(1)": "Programmable via external resistor divider",
                "(2)": "Thermal limit-dependent; see thermal design section",
                "(3)": "Typical 0.1Ω to 1Ω for current sensing",
            },
        },
    )


def mock_tps62933_electrical_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Min", "Typ", "Max", "Unit", "Conditions"],
            ["V_IN", "2.7", "—", "6.0", "V", "—"],
            ["V_OUT", "0.6", "—", "5.5", "V", "Programmable"],
            ["I_OUT", "—", "—", "3.0", "A", "Continuous"],
            ["I_Q", "—", "50", "100", "µA", "Operating"],
            ["I_SHUTDOWN", "—", "1.0", "2.0", "µA", "—"],
            ["η (Efficiency)", "—", "92", "—", "%", "I_OUT = 1A, V_IN = 5V"],
            ["f_SW", "—", "2.1", "—", "MHz", "High frequency"],
            ["V_RIPPLE", "—", "—", "50", "mV", "Output ripple"],
        ],
        section_type="electrical_characteristics",
        page_number=6,
        confidence=0.91,
        source="vlm_path_B",
    )


def mock_tps62933_pinout_grid() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Pin", "Name", "Function"],
            ["1", "V_IN", "Input voltage"],
            ["2", "SW", "Switch node"],
            ["3", "FB", "Feedback input"],
            ["4", "GND", "Ground"],
            ["5", "VOUT", "Output voltage"],
            ["6", "EN", "Enable"],
        ],
        section_type="pinout",
        page_number=3,
        confidence=0.94,
        source="vector_path_A",
    )


def mock_tps62933_absolute_max() -> GridMatrix:
    return mock_gridmatrix(
        rows=[
            ["Parameter", "Max", "Unit"],
            ["V_IN", "7.0", "V"],
            ["T_J", "150", "°C"],
            ["I_SW", "4.0", "A"],
            ["P_DISSIPATION", "1.5", "W"],
        ],
        section_type="absolute_maximum_ratings",
        page_number=5,
        confidence=0.96,
        source="vector_path_A",
    )


def mock_tps62933_phase2_output() -> Phase2Output:
    pdf = "corpus/golden/TI_TPS62933_v1.pdf"
    return Phase2Output(
        pdf_path=pdf,
        grids=[
            mock_tps62933_absolute_max(),
            mock_tps62933_electrical_grid(),
            mock_tps62933_pinout_grid(),
        ],
        metadata={"component_id": "TPS62933", "pdf_path": pdf},
    )


def all_golden_phase2_outputs() -> dict[str, Phase2Output]:
    """All 5 golden Phase 2 outputs for Phase 3 testing."""
    return {
        "TI_SN74LVC1G04": mock_sn74_phase2_output(),
        "TI_TLV7021": mock_tlv7021_phase2_output(),
        "TI_INA219": mock_ina219_phase2_output(),
        "TI_LM5176": mock_lm5176_phase2_output(),
        "TI_TPS62933": mock_tps62933_phase2_output(),
    }
