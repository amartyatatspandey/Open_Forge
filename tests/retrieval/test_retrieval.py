"""Gate tests for Stage 3 retrieval engine — mocked DB, no live PostgreSQL."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.retrieval.engine import RetrievalEngine
from src.retrieval.freshness import DatasheetFreshnessChecker
from src.retrieval.planner import build_retrieval_plan
from src.retrieval.qa_gate import QAGate
from src.retrieval.schemas import ComponentCandidate, ComponentQuery
from src.retrieval.search_layers import fuse_results, parametric_search
from src.schemas.common import ImpliedRequirement, TopologyGuess
from src.schemas.intent import DesignMethodology, ImprovedIntentDict

_VALID_INTENT = ImprovedIntentDict(
    goal="current_source",
    application="lab",
    design_methodology=DesignMethodology.MIXED_SIGNAL,
    board_type="double_sided_SMD",
    raw_prompt="libbrecht hall current source 100mA ultra low noise",
    goal_topologies=[
        TopologyGuess(name="libbrecht_hall", confidence=0.95, evidence=["libbrecht hall"])
    ],
    implied_requirements=[
        ImpliedRequirement(
            requirement="Low-noise LDO for op-amp supply",
            component_implication="low_noise_ldo",
            reasoning="PSRR coupling",
            confidence=0.95,
            source_constraint="ultra low noise",
            priority="CRITICAL",
        ),
        ImpliedRequirement(
            requirement="Precision voltage reference",
            component_implication="precision_voltage_reference",
            reasoning="Libbrecht-Hall topology",
            confidence=0.98,
            source_constraint="libbrecht hall design",
            priority="CRITICAL",
        ),
        ImpliedRequirement(
            requirement="Kelvin sensing on sense resistor",
            component_implication="pcb_layout_constraint",
            reasoning="Lead resistance error",
            confidence=0.97,
            source_constraint="100mA current",
            priority="CRITICAL",
        ),
    ],
)


def test_planner_generates_component_queries():
    plan = build_retrieval_plan(_VALID_INTENT)
    assert len(plan.component_queries) >= 2
    types = {cq.component_type for cq in plan.component_queries}
    assert "low_noise_ldo" in types
    assert "precision_voltage_reference" in types
    assert "pcb_layout_constraint" not in types
    assert plan.topology_slugs == ["libbrecht_hall"]


def test_planner_priority_order_is_critical_first():
    plan = build_retrieval_plan(_VALID_INTENT)
    ranks = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    priorities = [ranks[cq.priority] for cq in plan.component_queries]
    assert priorities == sorted(priorities)


def test_planner_document_queries_generated():
    plan = build_retrieval_plan(_VALID_INTENT)
    query_types = {dq.query_type for dq in plan.document_queries}
    assert "paper" in query_types
    assert "app_note" in query_types


def test_parametric_search_filters_approved_only():
    kb = MagicMock()
    kb.execute.return_value = [
        {
            "component_id": "cid-1",
            "part_number": "OPA189",
            "lifecycle_status": "active",
            "manufacturer_name": "TI",
            "category_name": "op_amp",
        }
    ]
    kb.get_electrical_parameters.return_value = [
        {
            "symbol": "Vn",
            "value_typ": 5.0,
            "parameter_name": "noise",
            "extraction_status": "approved",
        },
        {
            "symbol": "Vn",
            "value_typ": 99.0,
            "parameter_name": "noise_bad",
            "extraction_status": "needs_review",
        },
    ]

    query = ComponentQuery(
        component_type="low_noise_ldo",
        required_attributes={"noise_uVrms": "<10"},
        source="test",
        priority="CRITICAL",
    )
    results = parametric_search(query, kb)

    assert len(results) == 1
    sql_called = kb.execute.call_args[0][0]
    assert "extraction_status = 'approved'" in sql_called
    assert "valid_to IS NULL" in sql_called
    assert results[0].matched_attributes.get("noise_uVrms") == "5.0"


def test_fuse_results_rrf_scoring():
    cand_a_param = ComponentCandidate(
        component_id="A",
        part_number="A",
        manufacturer="M",
        matched_query_type="t",
        scores={"parametric": 1.0},
        final_score=0.0,
        matched_attributes={},
        missing_attributes=[],
        lifecycle_status="active",
        source_layers=["parametric"],
    )
    cand_a_fts = cand_a_param.model_copy(
        update={"scores": {"fts": 0.5}, "source_layers": ["fts"]}
    )
    cand_b = ComponentCandidate(
        component_id="B",
        part_number="B",
        manufacturer="M",
        matched_query_type="t",
        scores={"vector": 0.9},
        final_score=0.0,
        matched_attributes={},
        missing_attributes=[],
        lifecycle_status="active",
        source_layers=["vector"],
    )

    fused = fuse_results([cand_a_param], [cand_a_fts], [cand_b], [])
    by_id = {c.component_id: c for c in fused}
    assert by_id["A"].final_score > by_id["B"].final_score


def test_qa_gate_fails_on_low_confidence():
    result = QAGate().run(
        [{"parameter_name": "noise", "confidence": 0.50, "symbol": "en"}]
    )
    assert result.passed is False
    assert "noise" in result.failed_parameters


def test_qa_gate_fails_on_impossible_range():
    result = QAGate().run(
        [
            {
                "parameter_name": "range_bad",
                "confidence": 0.9,
                "value_min": 10.0,
                "value_max": 5.0,
            }
        ]
    )
    assert result.passed is False


def test_qa_gate_warns_on_implausible_value():
    result = QAGate().run(
        [
            {
                "parameter_name": "noise_high",
                "confidence": 0.9,
                "symbol": "en",
                "value_typ": 9999.0,
            }
        ]
    )
    assert result.passed is True
    assert "noise_high" in result.warnings


@patch("src.retrieval.freshness.httpx.Client")
def test_freshness_checker_uses_etag_first(mock_client_cls):
    mock_response = MagicMock()
    mock_response.headers = {"ETag": "new-etag"}
    mock_client_cls.return_value.__enter__.return_value.head.return_value = mock_response

    result = DatasheetFreshnessChecker().check_for_updates(
        component_id="c1",
        url="https://example.com/ds.pdf",
        stored_etag="old-etag",
        stored_content_length=100,
        stored_cover_sha256="abc",
    )
    assert result.signal_used == "etag"
    assert result.is_stale is True


@patch("src.retrieval.freshness.httpx.Client")
def test_freshness_checker_falls_back_to_content_length(mock_client_cls):
    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": "99999"}
    mock_client_cls.return_value.__enter__.return_value.head.return_value = mock_response

    result = DatasheetFreshnessChecker().check_for_updates(
        component_id="c1",
        url="https://example.com/ds.pdf",
        stored_etag=None,
        stored_content_length=12345,
        stored_cover_sha256=None,
    )
    assert result.signal_used == "content_length"
    assert result.is_stale is True


@patch("src.retrieval.freshness.httpx.Client")
def test_freshness_checker_unknown_when_no_signals(mock_client_cls):
    mock_response = MagicMock()
    mock_response.headers = {}
    mock_client_cls.return_value.__enter__.return_value.head.return_value = mock_response

    result = DatasheetFreshnessChecker().check_for_updates(
        component_id="c1",
        url="https://example.com/ds.pdf",
        stored_etag=None,
        stored_content_length=None,
        stored_cover_sha256=None,
    )
    assert result.signal_used == "unknown"
    assert result.is_stale is False


@patch.object(RetrievalEngine, "_route_to_review_queue")
@patch("src.retrieval.engine.parametric_search", return_value=[])
@patch("src.retrieval.engine.fts_search", return_value=[])
@patch("src.retrieval.engine.vector_search", return_value=[])
@patch("src.retrieval.engine.kg_traversal", return_value=[])
@patch("src.retrieval.engine.KBClient")
def test_retrieval_engine_routes_missing_to_review_queue(
    mock_kb_cls,
    _kg,
    _vec,
    _fts,
    _param,
    mock_route,
):
    mock_kb = MagicMock()
    mock_kb.get_design_pattern.return_value = None
    mock_kb.execute.return_value = []
    mock_kb_cls.return_value = mock_kb
    config = SimpleNamespace(air_gapped=True)
    engine = RetrievalEngine("postgresql://test", config)
    result = engine.run_retrieval(_VALID_INTENT)
    assert "low_noise_ldo" in result.missing_components
    mock_route.assert_called()
    calls = [c.kwargs.get("component_type") for c in mock_route.call_args_list]
    assert "low_noise_ldo" in calls


@patch("src.retrieval.engine.parametric_search", return_value=[])
@patch("src.retrieval.engine.fts_search", return_value=[])
@patch("src.retrieval.engine.vector_search", return_value=[])
@patch("src.retrieval.engine.kg_traversal", return_value=[])
@patch("src.retrieval.engine.KBClient")
def test_retrieval_result_excludes_pcb_layout_constraints(
    mock_kb_cls, _kg, _vec, _fts, _param
):
    mock_kb = MagicMock()
    mock_kb.get_design_pattern.return_value = None
    mock_kb.execute.return_value = []
    mock_kb_cls.return_value = mock_kb
    config = SimpleNamespace(air_gapped=False)
    engine = RetrievalEngine("postgresql://test", config)
    result = engine.run_retrieval(_VALID_INTENT)
    assert "pcb_layout_constraint" not in result.missing_components


def test_query_expander_expands_synonyms():
    from src.retrieval.query_expander import expand_query
    result = expand_query("chopper stabilized amplifier")
    assert "zero drift op amp" in result, \
        "Synonym expansion failed: 'zero drift op amp' not in expanded query"
    assert "auto zero amplifier" in result, \
        "Synonym expansion failed: 'auto zero amplifier' not in expanded query"


def test_query_expander_no_false_expansion():
    from src.retrieval.query_expander import expand_query
    result = expand_query("ceramic capacitor 100nF")
    # No synonym group should match — result should be unchanged
    assert result == "ceramic capacitor 100nF", \
        "Query expander added unexpected synonyms for unrecognized component type"


def test_vector_search_validates_embedding_dimension():
    """
    vector_search must reject embeddings that are not 4096-dim
    and return empty list with an error log.
    """
    import numpy as np
    from src.retrieval.search_layers import vector_search
    from src.retrieval.schemas import ComponentQuery

    mock_encoder = MagicMock()
    # Return wrong dimension (384 instead of 4096)
    mock_encoder.encode.return_value = np.zeros(384)

    mock_kb = MagicMock()
    cq = ComponentQuery(
        component_type="zero_drift_op_amp",
        required_attributes={"noise_nV_rtHz": "<5"},
        source="test",
        priority="CRITICAL",
    )

    result = vector_search(cq, mock_kb, mock_encoder)
    assert result == [], \
        "vector_search must return empty list on dimension mismatch, not raise"
    # KB should not have been queried (encoder failed before DB call)
    mock_kb.execute.assert_not_called()


def test_coverage_reporter_returns_report():
    from src.retrieval.coverage_reporter import get_coverage_report

    mock_kb = MagicMock()
    mock_kb.execute.side_effect = [
        [{"total": 500}],    # total active components
        [{"covered": 320}],  # components with symbol extracted
    ]

    report = get_coverage_report("zero_drift_op_amp", "VOS_drift", mock_kb)
    assert report.total_active_components == 500
    assert report.components_with_symbol_extracted == 320
    assert report.components_missing_symbol == 180
    assert abs(report.coverage_fraction - 0.64) < 0.01
