"""Tests for the KG query engine.

Fixture graph (6 nodes, 5 edges):

    patch_antenna (COMPONENT_TYPE, layer=1, conf=1.0)
        --REQUIRES, conf=0.90--> matching_network (COMPONENT_TYPE, layer=2)
        --REQUIRES, conf=0.85--> RF_connector   (COMPONENT_TYPE, layer=2)
        --MUST_BE_NEAR, conf=0.88--> keepout_zone (PLACEMENT_RULE)
    matching_network
        --HAS_PROPERTY, conf=0.92--> 50_ohm_impedance (ELECTRICAL_PROPERTY)
    RF_design (DESIGN_METHODOLOGY, layer=5)

Expected product path-confidences:
    patch_antenna      = 1.0
    matching_network   = 1.0 × 0.90 = 0.90
    RF_connector       = 1.0 × 0.85 = 0.85
    keepout_zone       = 1.0 × 0.88 = 0.88
    50_ohm_impedance   = 0.90 × 0.92 = 0.828
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.knowledge_graph import KnowledgeGraph, query_graph
from src.knowledge_graph.query.goal_mapper import map_goal_to_nodes
from src.knowledge_graph.query.methodology_filter import apply_methodology_filter
from src.knowledge_graph.query.traversal import TRAVERSAL_RELATIONS, bfs_traverse
from src.schemas.datasheet import ExtractionMethod
from src.schemas.intent import DesignMethodology, FrequencySpec, IntentDict
from src.schemas.kg import KGEdge, KGNode, KGNodeType, KGRelation


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _node(
    node_id: str,
    node_type: KGNodeType,
    layer: int,
    label: str,
    confidence: float = 1.0,
    properties: dict | None = None,
) -> KGNode:
    return KGNode(
        id=node_id,
        node_type=node_type,
        layer=layer,
        label=label,
        properties=properties or {},
        source="test",
        confidence=confidence,
        extraction_method=ExtractionMethod.MANUAL,
        created_at="2026-01-01T00:00:00Z",
    )


def _edge(
    source_id: str,
    relation: KGRelation,
    target_id: str,
    confidence: float,
    constraints: dict | None = None,
    layer: int = 2,
) -> KGEdge:
    return KGEdge(
        source_id=source_id,
        relation=relation,
        target_id=target_id,
        constraints=constraints or {},
        source_document="test",
        confidence=confidence,
        layer=layer,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fixture graph
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fixture_graph() -> KnowledgeGraph:
    """Build the 6-node, 5-edge test graph described in the module docstring."""
    g = KnowledgeGraph()

    patch_antenna = _node("component_type:patch_antenna", KGNodeType.COMPONENT_TYPE, 1, "patch_antenna")
    matching_network = _node("component_type:matching_network", KGNodeType.COMPONENT_TYPE, 2, "matching_network")
    rf_connector = _node("component_type:RF_connector", KGNodeType.COMPONENT_TYPE, 2, "RF_connector")
    keepout_zone = _node(
        "placement_rule:keepout_zone", KGNodeType.PLACEMENT_RULE, 4, "keepout_zone",
        properties={"constraint_type": "keepout"},
    )
    impedance_50 = _node("property:50_ohm_impedance", KGNodeType.ELECTRICAL_PROPERTY, 2, "50_ohm_impedance")
    rf_design = _node(
        "design_methodology:RF_highfreq", KGNodeType.DESIGN_METHODOLOGY, 5, "RF_highfreq",
        properties={
            "active_constraint_types": ["proximity"],
            "suppressed_constraint_types": [],
        },
    )

    for n in [patch_antenna, matching_network, rf_connector, keepout_zone, impedance_50, rf_design]:
        g.add_node(n)

    g.add_edge(_edge("component_type:patch_antenna", KGRelation.REQUIRES, "component_type:matching_network", 0.90))
    g.add_edge(_edge("component_type:patch_antenna", KGRelation.REQUIRES, "component_type:RF_connector", 0.85))
    g.add_edge(_edge("component_type:patch_antenna", KGRelation.MUST_BE_NEAR, "placement_rule:keepout_zone", 0.88, layer=4))
    g.add_edge(_edge("component_type:matching_network", KGRelation.HAS_PROPERTY, "property:50_ohm_impedance", 0.92))
    return g


@pytest.fixture
def mock_config() -> MagicMock:
    cfg = MagicMock()
    cfg.kg_traversal_max_depth = 4
    cfg.kg_min_edge_confidence = 0.60
    return cfg


def _make_intent(
    goal: str,
    methodology: DesignMethodology = DesignMethodology.RF_HIGHFREQ,
    frequency: FrequencySpec | None = None,
) -> IntentDict:
    return IntentDict(
        goal=goal,
        frequency=frequency,
        application="test",
        design_methodology=methodology,
        board_type="2-layer FR4",
        raw_prompt=goal,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. goal_mapper – Strategy 1: exact label match
# ─────────────────────────────────────────────────────────────────────────────

def test_goal_exact_match(fixture_graph: KnowledgeGraph) -> None:
    """goal 'patch_antenna' maps to the patch_antenna COMPONENT_TYPE node."""
    nodes = map_goal_to_nodes("patch_antenna", fixture_graph)

    assert len(nodes) >= 1
    assert any(n.id == "component_type:patch_antenna" for n in nodes)


# ─────────────────────────────────────────────────────────────────────────────
# 2. goal_mapper – Strategy 2: all words present
# ─────────────────────────────────────────────────────────────────────────────

def test_goal_strategy2_space_separated(fixture_graph: KnowledgeGraph) -> None:
    """goal 'patch antenna' matches via all-words-present strategy."""
    nodes = map_goal_to_nodes("patch antenna", fixture_graph)

    assert len(nodes) >= 1
    assert any(n.id == "component_type:patch_antenna" for n in nodes)


# ─────────────────────────────────────────────────────────────────────────────
# 3. goal_mapper – no match → empty list, no exception
# ─────────────────────────────────────────────────────────────────────────────

def test_goal_unknown_returns_empty(fixture_graph: KnowledgeGraph) -> None:
    """Unknown goal returns [] without raising."""
    nodes = map_goal_to_nodes("xyz_unknown_frobnicator", fixture_graph)

    assert nodes == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. BFS reaches depth-1 nodes
# ─────────────────────────────────────────────────────────────────────────────

def test_bfs_reaches_depth1_nodes(fixture_graph: KnowledgeGraph) -> None:
    """BFS traversal reaches matching_network and RF_connector at depth 1."""
    start = [fixture_graph.get_node("component_type:patch_antenna")]
    path_confidences, _ = bfs_traverse(start, fixture_graph, max_depth=4, min_edge_confidence=0.60)

    assert "component_type:matching_network" in path_confidences
    assert "component_type:RF_connector" in path_confidences


# ─────────────────────────────────────────────────────────────────────────────
# 5. BFS reaches depth-2 nodes
# ─────────────────────────────────────────────────────────────────────────────

def test_bfs_reaches_depth2_nodes(fixture_graph: KnowledgeGraph) -> None:
    """BFS traversal reaches 50_ohm_impedance at depth 2."""
    start = [fixture_graph.get_node("component_type:patch_antenna")]
    path_confidences, _ = bfs_traverse(start, fixture_graph, max_depth=4, min_edge_confidence=0.60)

    assert "property:50_ohm_impedance" in path_confidences


# ─────────────────────────────────────────────────────────────────────────────
# 6. BFS respects max_depth
# ─────────────────────────────────────────────────────────────────────────────

def test_bfs_stops_at_max_depth_1(fixture_graph: KnowledgeGraph) -> None:
    """With max_depth=1, 50_ohm_impedance (depth 2) is NOT in path_confidences."""
    start = [fixture_graph.get_node("component_type:patch_antenna")]
    path_confidences, _ = bfs_traverse(start, fixture_graph, max_depth=1, min_edge_confidence=0.60)

    assert "component_type:matching_network" in path_confidences  # depth 1 — present
    assert "property:50_ohm_impedance" not in path_confidences    # depth 2 — absent


# ─────────────────────────────────────────────────────────────────────────────
# 7. Path confidence is a product (depth 1)
# ─────────────────────────────────────────────────────────────────────────────

def test_path_confidence_product_depth1(fixture_graph: KnowledgeGraph) -> None:
    """matching_network path confidence = 1.0 × 0.90 = 0.90."""
    start = [fixture_graph.get_node("component_type:patch_antenna")]
    path_confidences, _ = bfs_traverse(start, fixture_graph, max_depth=4, min_edge_confidence=0.60)

    assert pytest.approx(path_confidences["component_type:matching_network"], rel=1e-6) == 0.90


# ─────────────────────────────────────────────────────────────────────────────
# 8. Path confidence is a product (depth 2)
# ─────────────────────────────────────────────────────────────────────────────

def test_path_confidence_product_depth2(fixture_graph: KnowledgeGraph) -> None:
    """50_ohm_impedance path confidence = 1.0 × 0.90 × 0.92 = 0.828."""
    start = [fixture_graph.get_node("component_type:patch_antenna")]
    path_confidences, _ = bfs_traverse(start, fixture_graph, max_depth=4, min_edge_confidence=0.60)

    assert pytest.approx(path_confidences["property:50_ohm_impedance"], rel=1e-6) == 0.828


# ─────────────────────────────────────────────────────────────────────────────
# 9. Edges with non-empty constraints appear in design_rules
# ─────────────────────────────────────────────────────────────────────────────

def test_design_rules_requires_non_empty_constraints(fixture_graph: KnowledgeGraph) -> None:
    """Edges with non-empty constraints dict appear in DesignSubgraph.design_rules."""
    # Add an edge with constraints to the fixture graph
    constraint_edge = _edge(
        "component_type:patch_antenna",
        KGRelation.REQUIRES,
        "component_type:RF_connector",
        0.85,
        constraints={"max_impedance_ohm": "50", "unit": "ohm"},
    )
    # Replace the existing edge (same source/target) with a constrained version
    # Add a fresh graph to avoid modifying the shared fixture
    g = KnowledgeGraph()
    patch_antenna = _node("component_type:patch_antenna", KGNodeType.COMPONENT_TYPE, 1, "patch_antenna")
    rf_connector  = _node("component_type:RF_connector", KGNodeType.COMPONENT_TYPE, 2, "RF_connector")
    g.add_node(patch_antenna)
    g.add_node(rf_connector)
    g.add_edge(constraint_edge)

    start = [patch_antenna]
    path_confidences, traversed_edges = bfs_traverse(start, g, max_depth=4, min_edge_confidence=0.60)

    from src.knowledge_graph.query.result_builder import build_subgraph
    subgraph = build_subgraph(path_confidences, traversed_edges, g, None, "test", 4)

    assert len(subgraph.design_rules) == 1
    assert subgraph.design_rules[0].constraints["unit"] == "ohm"


# ─────────────────────────────────────────────────────────────────────────────
# 10. PLACEMENT_RULE ends up in placement_rules, not component_types
# ─────────────────────────────────────────────────────────────────────────────

def test_placement_rule_in_placement_rules(fixture_graph: KnowledgeGraph) -> None:
    """keepout_zone PLACEMENT_RULE node appears in placement_rules, not component_types."""
    start = [fixture_graph.get_node("component_type:patch_antenna")]
    path_confidences, traversed_edges = bfs_traverse(start, fixture_graph, max_depth=4, min_edge_confidence=0.60)

    from src.knowledge_graph.query.result_builder import build_subgraph
    subgraph = build_subgraph(path_confidences, traversed_edges, fixture_graph, None, "RF_highfreq", 4)

    placement_ids = [n.id for n in subgraph.placement_rules]
    component_ids = [n.id for n in subgraph.component_types]

    assert "placement_rule:keepout_zone" in placement_ids
    assert "placement_rule:keepout_zone" not in component_ids


# ─────────────────────────────────────────────────────────────────────────────
# 11. methodology_filter removes keepout when only "proximity" is active
# ─────────────────────────────────────────────────────────────────────────────

def test_methodology_filter_removes_keepout_when_not_active(fixture_graph: KnowledgeGraph) -> None:
    """RF_highfreq node (active=proximity only) removes the keepout_zone rule."""
    methodology_node = fixture_graph.get_node("design_methodology:RF_highfreq")
    # The fixture's RF_highfreq has active_constraint_types=["proximity"]
    keepout_node = fixture_graph.get_node("placement_rule:keepout_zone")
    # keepout_node.properties["constraint_type"] == "keepout"

    result = apply_methodology_filter([keepout_node], methodology_node)

    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 12. methodology_filter keeps keepout when "keepout" is active
# ─────────────────────────────────────────────────────────────────────────────

def test_methodology_filter_keeps_keepout_when_active() -> None:
    """A methodology with active_constraint_types=['keepout'] keeps the keepout rule."""
    methodology_node = _node(
        "design_methodology:RF_highfreq_v2", KGNodeType.DESIGN_METHODOLOGY, 5, "RF_highfreq_v2",
        properties={"active_constraint_types": ["keepout", "proximity"], "suppressed_constraint_types": []},
    )
    keepout_node = _node(
        "placement_rule:keepout_zone", KGNodeType.PLACEMENT_RULE, 4, "keepout_zone",
        properties={"constraint_type": "keepout"},
    )

    result = apply_methodology_filter([keepout_node], methodology_node)

    assert len(result) == 1
    assert result[0].id == "placement_rule:keepout_zone"


# ─────────────────────────────────────────────────────────────────────────────
# 13. Empty graph returns DesignSubgraph with all empty lists
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_graph_returns_empty_subgraph(mock_config: MagicMock) -> None:
    """Querying an empty graph returns DesignSubgraph with all empty lists."""
    empty_graph = KnowledgeGraph()
    intent = _make_intent("patch_antenna")

    subgraph = query_graph(intent, empty_graph, mock_config)

    assert subgraph.component_types == []
    assert subgraph.component_instances == []
    assert subgraph.placement_rules == []
    assert subgraph.routing_hints == []
    assert subgraph.design_rules == []


# ─────────────────────────────────────────────────────────────────────────────
# 14. Full integration: query_graph returns DesignSubgraph
# ─────────────────────────────────────────────────────────────────────────────

def test_query_graph_integration(fixture_graph: KnowledgeGraph, mock_config: MagicMock) -> None:
    """query_graph returns a DesignSubgraph with nodes from the fixture graph."""
    intent = _make_intent("patch_antenna", DesignMethodology.RF_HIGHFREQ)

    subgraph = query_graph(intent, fixture_graph, mock_config)

    # Should be a DesignSubgraph (not raise, not None)
    assert subgraph is not None
    assert subgraph.design_methodology == "RF_highfreq"

    # patch_antenna itself + matching_network + RF_connector are COMPONENT_TYPE
    comp_type_ids = [n.id for n in subgraph.component_types]
    assert "component_type:patch_antenna" in comp_type_ids
    assert "component_type:matching_network" in comp_type_ids
    assert "component_type:RF_connector" in comp_type_ids

    # path_confidences must be populated
    assert len(subgraph.path_confidences) > 0
