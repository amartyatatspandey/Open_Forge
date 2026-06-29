"""Gate tests for embedding ingestion pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import psycopg2
import pytest

from src.config import Config
from src.retrieval.embedding_ingestor import (
    EMBEDDING_MODEL_NAME,
    build_embedding_text,
    ingest_datasheet_embedding,
    run_embedding_ingestion,
)
from src.schemas.datasheet import (
    ComponentDatasheet,
    ElectricalParameter,
    ExtractionMethod,
    ExtractedValue,
    TableSectionType,
)


def make_datasheet(**kwargs) -> ComponentDatasheet:
    defaults = dict(
        component_id="TPS62933",
        manufacturer="Texas Instruments",
        description="3A step-down converter",
        package="SOT-23-6",
        source_pdf_hash="abc123",
        extraction_method=ExtractionMethod.P1_VECTOR,
        electrical_parameters=[],
        absolute_max_ratings=[],
        pins=[],
        layout_constraints=[],
        extraction_confidence=0.95,
        review_required=False,
        review_flags=[],
        pipeline_version="1.0",
        created_at="2026-06-27T00:00:00Z",
    )
    defaults.update(kwargs)
    return ComponentDatasheet(**defaults)


def _make_param(
    name: str,
    *,
    typ: float | None = None,
    min_val: float | None = None,
    max_val: float | None = None,
    unit: str = "V",
) -> ElectricalParameter:
    return ElectricalParameter(
        parameter_name=name,
        value=ExtractedValue(
            raw_text=f"{name} test",
            typ_val=typ,
            min_val=min_val,
            max_val=max_val,
            unit=unit,
            confidence=0.9,
        ),
        section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
        source_page=1,
        source_table_index=0,
    )


def _mock_kb(
    *,
    component_row: dict | None = None,
    execute_side_effect=None,
) -> MagicMock:
    kb = MagicMock()
    kb.get_component_by_part_number.return_value = component_row
    if execute_side_effect is not None:
        kb.execute.side_effect = execute_side_effect
    else:
        kb.execute.return_value = []
    return kb


def _mock_encoder(dim: int = 4096) -> MagicMock:
    encoder = MagicMock()
    encoder.encode.return_value = np.ones(dim, dtype=np.float32)
    return encoder


def test_build_embedding_text_full_datasheet() -> None:
    ds = make_datasheet(
        electrical_parameters=[_make_param("Vin", typ=3.3, unit="V")],
    )
    text = build_embedding_text(ds)

    assert "TPS62933" in text
    assert "Texas Instruments" in text
    assert "3A step-down converter" in text
    assert "Vin" in text
    assert len(text) > 10


def test_build_embedding_text_empty_optional_fields() -> None:
    ds = make_datasheet(manufacturer="", description="", package="")
    text = build_embedding_text(ds)

    assert text.strip() != ""
    assert "TPS62933" in text


def test_build_embedding_text_at_most_ten_parameters() -> None:
    ds = make_datasheet(
        electrical_parameters=[
            _make_param(f"P{i}", typ=float(i), unit="V") for i in range(15)
        ],
    )
    text = build_embedding_text(ds)
    param_mentions = sum(1 for i in range(15) if f"P{i}" in text)

    assert param_mentions <= 10


def test_ingest_datasheet_embedding_happy_path() -> None:
    kb = _mock_kb(component_row={"id": "uuid-1234"})
    encoder = _mock_encoder()

    result = ingest_datasheet_embedding(make_datasheet(), kb, encoder)

    assert result is True
    kb.execute.assert_called_once()


def test_ingest_datasheet_embedding_component_not_found() -> None:
    kb = _mock_kb(component_row=None)
    encoder = _mock_encoder()

    result = ingest_datasheet_embedding(make_datasheet(), kb, encoder)

    assert result is False
    kb.execute.assert_not_called()


def test_ingest_datasheet_embedding_wrong_dimension() -> None:
    kb = _mock_kb(component_row={"id": "uuid-1234"})
    encoder = _mock_encoder(dim=128)

    result = ingest_datasheet_embedding(make_datasheet(), kb, encoder)

    assert result is False


def test_ingest_datasheet_embedding_db_error() -> None:
    kb = _mock_kb(
        component_row={"id": "uuid-1234"},
        execute_side_effect=psycopg2.OperationalError("connection lost"),
    )
    encoder = _mock_encoder()

    result = ingest_datasheet_embedding(make_datasheet(), kb, encoder)

    assert result is False


def test_run_embedding_ingestion_counts() -> None:
    ds1 = make_datasheet(component_id="TPS62933")
    ds2 = make_datasheet(component_id="MISSING")
    ds3 = make_datasheet(component_id="FAILME")

    mock_kb = MagicMock()
    mock_kb.close = MagicMock()

    def lookup(part_number: str):
        if part_number == "MISSING":
            return None
        return {"id": f"uuid-{part_number}"}

    def execute_side_effect(*_args, **_kwargs):
        if mock_kb.get_component_by_part_number.call_args[0][0] == "FAILME":
            raise psycopg2.OperationalError("connection lost")
        return []

    mock_kb.get_component_by_part_number.side_effect = lookup
    mock_kb.execute.side_effect = execute_side_effect

    mock_encoder = _mock_encoder()
    config = Config()

    with (
        patch(
            "src.retrieval.embedding_ingestor.KBClient",
            return_value=mock_kb,
        ),
        patch(
            "src.retrieval.embedding_ingestor.SentenceTransformer",
            return_value=mock_encoder,
        ),
    ):
        result = run_embedding_ingestion(
            [ds1, ds2, ds3],
            "postgresql://localhost/openforge",
            config,
        )

    assert result.total == 3
    assert result.written == 1
    assert result.skipped == 1
    assert result.failed == 1
    mock_kb.close.assert_called_once()


def test_run_embedding_ingestion_model_name() -> None:
    config = Config()
    mock_kb = MagicMock()
    mock_kb.get_component_by_part_number.return_value = {"id": "uuid-1234"}
    mock_kb.execute.return_value = []
    mock_kb.close = MagicMock()

    with (
        patch(
            "src.retrieval.embedding_ingestor.KBClient",
            return_value=mock_kb,
        ),
        patch(
            "src.retrieval.embedding_ingestor.SentenceTransformer",
            return_value=_mock_encoder(),
        ),
    ):
        result = run_embedding_ingestion(
            [make_datasheet()],
            "postgresql://localhost/openforge",
            config,
        )

    assert result.model_name == EMBEDDING_MODEL_NAME


def test_build_embedding_text_parameters_sorted_alphabetically() -> None:
    ds = make_datasheet(
        electrical_parameters=[
            _make_param("Vin", typ=3.3, unit="V"),
            _make_param("Amps", typ=1.0, unit="A"),
        ],
    )
    text = build_embedding_text(ds)

    assert text.index("Amps") < text.index("Vin")
