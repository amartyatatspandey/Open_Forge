"""Gate tests for Stage 2.5 retrieval wiring in run_intent_pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from src.config import Config
from src.knowledge_graph.graph import KnowledgeGraph
from src.retrieval.schemas import ComponentCandidate, RetrievalResult
from src.schemas.common import Ambiguity
from src.schemas.intent import (
    BOMEntry,
    DesignMethodology,
    ImprovedIntentDict,
    ValidatedBOM,
)
from src.schemas.kg import DesignSubgraph

PROMPT = "test prompt"

blocking_ambiguity = Ambiguity(
    field="f",
    description="d",
    blocking=True,
    severity="ERROR",
)


def make_intent(
    clarification_required: bool = False,
    ambiguities: list[Ambiguity] | None = None,
) -> ImprovedIntentDict:
    return ImprovedIntentDict(
        goal="test",
        application="test",
        design_methodology=DesignMethodology.STANDARD_SMD,
        board_type="standard_SMD",
        raw_prompt=PROMPT,
        clarification_required=clarification_required,
        ambiguities=ambiguities or [],
    )


def config_with_db(url: str | None = None) -> Config:
    cfg = Config()
    if url is not None:
        object.__setattr__(cfg, "database_url", url)
    return cfg


def make_retrieval_result(
    n_candidates: int = 2,
    n_missing: int = 0,
) -> RetrievalResult:
    candidates = [
        ComponentCandidate(
            component_id=f"uuid-{i}",
            part_number=f"PART{i}",
            manufacturer="TI",
            matched_query_type="op_amp",
            scores={"vector": 0.9},
            final_score=0.9,
            matched_attributes={},
            missing_attributes=[],
            lifecycle_status="active",
            source_layers=["vector"],
        )
        for i in range(n_candidates)
    ]
    return RetrievalResult(
        component_candidates=candidates,
        document_results=[],
        kb_coverage={},
        missing_components=[f"missing_{i}" for i in range(n_missing)],
        retrieval_metadata={},
    )


def _mock_subgraph() -> DesignSubgraph:
    return DesignSubgraph(
        component_types=[],
        component_instances=[],
        design_rules=[],
        placement_rules=[],
        routing_hints=[],
        design_methodology="standard_SMD",
        path_confidences={},
        query_depth=0,
        query_metadata={},
    )


def _mock_validated_bom(
    intent: ImprovedIntentDict,
    *,
    review_required: bool = False,
) -> ValidatedBOM:
    return ValidatedBOM(
        design_id="d1",
        intent=intent,
        components=[
            BOMEntry(
                ref="U1",
                component_type="regulator",
                specific_part="TPS62933",
                justification="test",
                source="rule",
                confidence=0.9,
            ),
        ],
        total_confidence=0.9,
        review_required=review_required,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


@pytest.fixture
def mock_graph() -> KnowledgeGraph:
    return MagicMock(spec=KnowledgeGraph)


def _happy_path_mocks(intent: ImprovedIntentDict | None = None):
    intent = intent or make_intent(clarification_required=False)
    validated = _mock_validated_bom(intent)
    return intent, _mock_subgraph(), validated


@patch("src.intent.pipeline.validate_bom")
@patch("src.intent.pipeline.generate_bom")
@patch("src.intent.pipeline.query_graph")
@patch("src.intent.pipeline.run_completion_engine")
@patch("src.intent.pipeline.parse_intent")
@patch("src.intent.pipeline.RetrievalEngine")
def test_retrieval_runs_when_database_url_set(
    mock_retrieval_engine,
    mock_parse_intent,
    mock_run_completion_engine,
    mock_query_graph,
    mock_generate_bom,
    mock_validate_bom,
    mock_graph: KnowledgeGraph,
) -> None:
    intent, subgraph, validated = _happy_path_mocks()
    config = config_with_db("postgresql://localhost/openforge")
    mock_parse_intent.return_value = intent
    mock_run_completion_engine.return_value = intent
    mock_query_graph.return_value = subgraph
    mock_generate_bom.return_value = MagicMock()
    mock_validate_bom.return_value = validated

    mock_engine = MagicMock()
    retrieval = make_retrieval_result()
    mock_engine.run_retrieval.return_value = retrieval
    mock_retrieval_engine.return_value = mock_engine

    from src.intent.pipeline import run_intent_pipeline

    _, _, retrieval_result = run_intent_pipeline(PROMPT, mock_graph, config)

    mock_retrieval_engine.assert_called_once_with(
        db_url="postgresql://localhost/openforge",
        config=config,
    )
    mock_engine.run_retrieval.assert_called_once()
    assert retrieval_result is not None
    assert len(retrieval_result.component_candidates) == 2


@patch("src.intent.pipeline.validate_bom")
@patch("src.intent.pipeline.generate_bom")
@patch("src.intent.pipeline.query_graph")
@patch("src.intent.pipeline.run_completion_engine")
@patch("src.intent.pipeline.parse_intent")
@patch("src.intent.pipeline.RetrievalEngine")
def test_retrieval_skipped_when_database_url_absent(
    mock_retrieval_engine,
    mock_parse_intent,
    mock_run_completion_engine,
    mock_query_graph,
    mock_generate_bom,
    mock_validate_bom,
    mock_graph: KnowledgeGraph,
) -> None:
    intent, subgraph, validated = _happy_path_mocks()
    config = Config()
    mock_parse_intent.return_value = intent
    mock_run_completion_engine.return_value = intent
    mock_query_graph.return_value = subgraph
    mock_generate_bom.return_value = MagicMock()
    mock_validate_bom.return_value = validated

    from src.intent.pipeline import run_intent_pipeline

    _, _, retrieval_result = run_intent_pipeline(PROMPT, mock_graph, config)

    mock_retrieval_engine.assert_not_called()
    assert retrieval_result is None


@patch("src.intent.pipeline.validate_bom")
@patch("src.intent.pipeline.generate_bom")
@patch("src.intent.pipeline.query_graph")
@patch("src.intent.pipeline.run_completion_engine")
@patch("src.intent.pipeline.parse_intent")
@patch("src.intent.pipeline.RetrievalEngine")
def test_retrieval_engine_init_failure_continues_pipeline(
    mock_retrieval_engine,
    mock_parse_intent,
    mock_run_completion_engine,
    mock_query_graph,
    mock_generate_bom,
    mock_validate_bom,
    mock_graph: KnowledgeGraph,
) -> None:
    intent, subgraph, validated = _happy_path_mocks()
    config = config_with_db("postgresql://localhost/openforge")
    mock_parse_intent.return_value = intent
    mock_run_completion_engine.return_value = intent
    mock_query_graph.return_value = subgraph
    mock_generate_bom.return_value = MagicMock()
    mock_validate_bom.return_value = validated
    mock_retrieval_engine.side_effect = psycopg2.OperationalError("no connection")

    from src.intent.pipeline import run_intent_pipeline

    _, validated_bom, retrieval_result = run_intent_pipeline(PROMPT, mock_graph, config)

    assert retrieval_result is None
    assert validated_bom is not None
    mock_generate_bom.assert_called_once()


@patch("src.intent.pipeline.validate_bom")
@patch("src.intent.pipeline.generate_bom")
@patch("src.intent.pipeline.query_graph")
@patch("src.intent.pipeline.run_completion_engine")
@patch("src.intent.pipeline.parse_intent")
@patch("src.intent.pipeline.RetrievalEngine")
def test_retrieval_result_passed_to_generate_bom(
    mock_retrieval_engine,
    mock_parse_intent,
    mock_run_completion_engine,
    mock_query_graph,
    mock_generate_bom,
    mock_validate_bom,
    mock_graph: KnowledgeGraph,
) -> None:
    intent, subgraph, validated = _happy_path_mocks()
    config = config_with_db("postgresql://localhost/openforge")
    mock_parse_intent.return_value = intent
    mock_run_completion_engine.return_value = intent
    mock_query_graph.return_value = subgraph
    mock_generate_bom.return_value = MagicMock()
    mock_validate_bom.return_value = validated

    mock_engine = MagicMock()
    retrieval = make_retrieval_result()
    mock_engine.run_retrieval.return_value = retrieval
    mock_retrieval_engine.return_value = mock_engine

    from src.intent.pipeline import run_intent_pipeline

    run_intent_pipeline(PROMPT, mock_graph, config)

    _, kwargs = mock_generate_bom.call_args
    assert "retrieval_result" in kwargs
    assert kwargs["retrieval_result"] is retrieval


@patch("src.intent.pipeline.RetrievalEngine")
@patch("src.intent.pipeline.parse_intent")
def test_gate1_early_return_skips_retrieval(
    mock_parse_intent,
    mock_retrieval_engine,
    mock_graph: KnowledgeGraph,
) -> None:
    intent = make_intent(
        clarification_required=True,
        ambiguities=[blocking_ambiguity],
    )
    mock_parse_intent.return_value = intent
    config = config_with_db("postgresql://localhost/openforge")

    from src.intent.pipeline import run_intent_pipeline

    result_intent, bom, retrieval_result = run_intent_pipeline(
        PROMPT, mock_graph, config
    )

    mock_retrieval_engine.assert_not_called()
    assert retrieval_result is None
    assert bom.review_required is True
    assert result_intent is intent


@patch("src.intent.pipeline.RetrievalEngine")
@patch("src.intent.pipeline.run_completion_engine")
@patch("src.intent.pipeline.parse_intent")
def test_gate2_early_return_skips_retrieval(
    mock_parse_intent,
    mock_run_completion_engine,
    mock_retrieval_engine,
    mock_graph: KnowledgeGraph,
) -> None:
    intent_v1 = make_intent(clarification_required=False)
    intent_v2 = make_intent(
        clarification_required=True,
        ambiguities=[blocking_ambiguity],
    )
    mock_parse_intent.return_value = intent_v1
    mock_run_completion_engine.return_value = intent_v2
    config = config_with_db("postgresql://localhost/openforge")

    from src.intent.pipeline import run_intent_pipeline

    result_intent, bom, retrieval_result = run_intent_pipeline(
        PROMPT, mock_graph, config
    )

    mock_retrieval_engine.assert_not_called()
    assert retrieval_result is None
    assert bom.review_required is True
    assert result_intent is intent_v2


@patch("src.intent.pipeline.validate_bom")
@patch("src.intent.pipeline.generate_bom")
@patch("src.intent.pipeline.query_graph")
@patch("src.intent.pipeline.run_completion_engine")
@patch("src.intent.pipeline.parse_intent")
@patch("src.intent.pipeline.RetrievalEngine")
def test_full_happy_path_returns_triple(
    mock_retrieval_engine,
    mock_parse_intent,
    mock_run_completion_engine,
    mock_query_graph,
    mock_generate_bom,
    mock_validate_bom,
    mock_graph: KnowledgeGraph,
) -> None:
    intent, subgraph, validated = _happy_path_mocks()
    config = config_with_db("postgresql://localhost/openforge")
    mock_parse_intent.return_value = intent
    mock_run_completion_engine.return_value = intent
    mock_query_graph.return_value = subgraph
    mock_generate_bom.return_value = MagicMock()
    mock_validate_bom.return_value = validated

    mock_engine = MagicMock()
    mock_engine.run_retrieval.return_value = make_retrieval_result()
    mock_retrieval_engine.return_value = mock_engine

    from src.intent.pipeline import run_intent_pipeline

    result_intent, result_bom, retrieval_result = run_intent_pipeline(
        PROMPT, mock_graph, config
    )

    assert result_intent is not None
    assert result_bom is not None
    assert retrieval_result is not None


@patch("src.intent.pipeline.validate_bom")
@patch("src.intent.pipeline.generate_bom")
@patch("src.intent.pipeline.query_graph")
@patch("src.intent.pipeline.run_completion_engine")
@patch("src.intent.pipeline.parse_intent")
@patch("src.intent.pipeline.RetrievalEngine")
def test_run_retrieval_failure_continues_pipeline(
    mock_retrieval_engine,
    mock_parse_intent,
    mock_run_completion_engine,
    mock_query_graph,
    mock_generate_bom,
    mock_validate_bom,
    mock_graph: KnowledgeGraph,
) -> None:
    intent, subgraph, validated = _happy_path_mocks()
    config = config_with_db("postgresql://localhost/openforge")
    mock_parse_intent.return_value = intent
    mock_run_completion_engine.return_value = intent
    mock_query_graph.return_value = subgraph
    mock_generate_bom.return_value = MagicMock()
    mock_validate_bom.return_value = validated

    mock_engine = MagicMock()
    mock_engine.run_retrieval.side_effect = RuntimeError("search exploded")
    mock_retrieval_engine.return_value = mock_engine

    from src.intent.pipeline import run_intent_pipeline

    _, _, retrieval_result = run_intent_pipeline(PROMPT, mock_graph, config)

    assert retrieval_result is None
    mock_generate_bom.assert_called_once()
