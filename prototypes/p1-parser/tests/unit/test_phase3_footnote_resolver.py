"""Unit tests for footnote resolution."""

from src.phase3_extract.footnote_resolver import (
    extract_footnote_marker,
    resolve_footnotes_in_extraction,
)
from src.schemas.datasheet import ElectricalParameter, ExtractedValue


def test_extract_footnote_marker() -> None:
    assert extract_footnote_marker("3.3 (1)") == "(1)"
    assert extract_footnote_marker("value*") == "*"


def test_resolve_footnotes_in_extraction() -> None:
    param = ElectricalParameter(
        name="V_OUT",
        parameter_type="voltage",
        typ_value=ExtractedValue(
            raw_text="3.3 (1)",
            value=3.3,
            unit="V",
            confidence=0.9,
            source="manual_review",
        ),
    )
    resolve_footnotes_in_extraction(
        [param], [], [], {"(1)": "Programmable via divider"}
    )
    assert param.typ_value is not None
    assert param.typ_value.footnote == "Programmable via divider"
