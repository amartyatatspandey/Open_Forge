"""Embedding ingestion pipeline for component_embeddings PostgreSQL table."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel

from src.retrieval.kb_client import KBClient
from src.schemas.datasheet import ComponentDatasheet, ElectricalParameter, PlacementConstraint

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "Qwen/Qwen3-Embedding-8B"
EMBEDDING_DIM = 4096

# Document-side encoding must NOT use QWEN3_QUERY_PREFIX (see search_layers.py).


class IngestionResult(BaseModel):
    total: int
    written: int
    skipped: int
    failed: int
    model_name: str


def _format_param_value(param: ElectricalParameter) -> Optional[str]:
    value = param.value.typ_val
    if value is None:
        value = param.value.min_val
    if value is None:
        value = param.value.max_val
    if value is None:
        return None

    unit = param.value.unit or ""
    if unit:
        return f"{value} {unit}".strip()
    return str(value)


def _format_constraint_value(constraint: PlacementConstraint) -> str:
    if constraint.source_sentence.strip():
        return constraint.source_sentence.strip()

    parts = [f"{constraint.subject} relative to {constraint.relative_to}"]
    if constraint.min_distance_mm is not None:
        parts.append(f"min {constraint.min_distance_mm}mm")
    if constraint.max_distance_mm is not None:
        parts.append(f"max {constraint.max_distance_mm}mm")
    return ", ".join(parts)


def build_embedding_text(datasheet: ComponentDatasheet) -> str:
    parts: list[str] = []

    if datasheet.manufacturer:
        parts.append(f"{datasheet.manufacturer} {datasheet.component_id}.")
    else:
        parts.append(f"{datasheet.component_id}.")

    if datasheet.description:
        parts.append(f"{datasheet.description}.")

    if datasheet.package:
        parts.append(f"Package: {datasheet.package}.")

    sorted_params = sorted(
        datasheet.electrical_parameters,
        key=lambda param: param.parameter_name,
    )
    for param in sorted_params[:10]:
        value_text = _format_param_value(param)
        if value_text is None:
            continue
        parts.append(f"{param.parameter_name}: {value_text}.")

    for constraint in datasheet.layout_constraints[:3]:
        constraint_value = _format_constraint_value(constraint)
        parts.append(f"{constraint.constraint_type}: {constraint_value}.")

    text = " ".join(parts).strip()
    if not text:
        return datasheet.component_id
    return text


def ingest_datasheet_embedding(
    datasheet: ComponentDatasheet,
    kb: KBClient,
    encoder: Any,
) -> bool:
    try:
        row = kb.get_component_by_part_number(datasheet.component_id)
        if row is None:
            logger.warning(
                "component not found in DB, skipping: %s",
                datasheet.component_id,
            )
            return False

        text = build_embedding_text(datasheet)
        # Document side — no query prefix (asymmetric encoding rule).
        vector = encoder.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        if len(vector) != EMBEDDING_DIM:
            logger.error(
                "Embedding dimension mismatch for %s: expected %d, got %d",
                datasheet.component_id,
                EMBEDDING_DIM,
                len(vector),
            )
            return False

        kb.execute(
            """
            INSERT INTO component_embeddings
                (component_id, embedding, embedding_text, model_name, generated_at)
            VALUES (%s, %s::vector, %s, %s, NOW())
            ON CONFLICT (component_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_text = EXCLUDED.embedding_text,
                model_name = EXCLUDED.model_name,
                generated_at = NOW()
            """,
            (
                str(row["id"]),
                vector.tolist(),
                text,
                EMBEDDING_MODEL_NAME,
            ),
        )
        return True
    except Exception as exc:
        logger.error(
            "Failed to ingest embedding for %s: %s",
            datasheet.component_id,
            exc,
        )
        return False


def _resolve_model_name(config: "Config") -> str:
    model_path = config.model_paths.get("qwen3_embedding")
    if model_path:
        return str(model_path)
    return EMBEDDING_MODEL_NAME


def run_embedding_ingestion(
    datasheets: list[ComponentDatasheet],
    database_url: str,
    config: "Config",
) -> IngestionResult:
    if SentenceTransformer is None:
        raise ImportError(
            "sentence-transformers is required for embedding ingestion. "
            "Install with: pip install sentence-transformers"
        )

    model_name_or_path = _resolve_model_name(config)
    device = getattr(config, "embedding_device", "cpu")
    logger.info("Loading embedding model: %s", model_name_or_path)

    encoder = SentenceTransformer(model_name_or_path, device=device)
    kb = KBClient(database_url)

    written = 0
    skipped = 0
    failed = 0

    try:
        for datasheet in datasheets:
            row = kb.get_component_by_part_number(datasheet.component_id)
            if row is None:
                logger.warning(
                    "component not found in DB, skipping: %s",
                    datasheet.component_id,
                )
                skipped += 1
                continue

            if ingest_datasheet_embedding(datasheet, kb, encoder):
                written += 1
            else:
                failed += 1
    finally:
        kb.close()

    return IngestionResult(
        total=len(datasheets),
        written=written,
        skipped=skipped,
        failed=failed,
        model_name=model_name_or_path,
    )


def _load_datasheets_from_dir(corpus_dir: Path) -> list[ComponentDatasheet]:
    datasheets: list[ComponentDatasheet] = []
    for json_path in sorted(corpus_dir.glob("*.json")):
        try:
            datasheets.append(
                ComponentDatasheet.model_validate_json(json_path.read_text())
            )
        except Exception as exc:
            logger.warning("Skipping invalid datasheet JSON %s: %s", json_path, exc)
    return datasheets


def main(argv: list[str] | None = None) -> int:
    from src.config import get_config

    parser = argparse.ArgumentParser(description="Ingest component embeddings into PostgreSQL")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        required=True,
        help="Directory containing ComponentDatasheet JSON files",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL connection URL (overrides config.database_url)",
    )
    args = parser.parse_args(argv)

    config = get_config()
    database_url = args.database_url or getattr(
        config,
        "database_url",
        "postgresql://localhost/openforge",
    )

    datasheets = _load_datasheets_from_dir(args.corpus_dir)
    result = run_embedding_ingestion(datasheets, database_url, config)
    print(result.model_dump_json())
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
