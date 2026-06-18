#!/usr/bin/env python3
"""Team B Gate - Knowledge graph validation checks."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

results: list[tuple[int, str, bool, str]] = []


def check(num: int, name: str, passed: bool, error: str = "") -> None:
    results.append((num, name, passed, error))
    status = "PASS" if passed else "FAIL"
    print(f"CHECK {num} — {name}: {status}")
    if error:
        print(f"  Error: {error}")


print("=" * 60)
print("TEAM B GATE - Knowledge Graph")
print("=" * 60)

from src.config import get_config

config = get_config()

# CHECK 1 — All Team B modules import without error
print("\n" + "-" * 60)
try:
    from src.knowledge_graph import KnowledgeGraph, query_graph, search_components
    from src.knowledge_graph.admin import seed_default_methodologies, list_methodologies
    from src.knowledge_graph.importers.p1_importer import import_datasheet, import_batch
    from src.knowledge_graph.ingestion.triple_extractor import extract_triples
    from src.knowledge_graph.ingestion.kg1_aac import scrape_aac_chapters, ingest_aac_into_graph
    from src.knowledge_graph.ingestion.kg2_appnotes import scrape_app_notes, ingest_app_note
    from src.knowledge_graph.pin_normalizer import normalize_pins
    from src.knowledge_graph.query import query_graph as qg_direct
    from src.knowledge_graph.query.traversal import TRAVERSAL_RELATIONS
    from src.knowledge_graph.semantic_search import build_search_index, search_components as sc_direct

    check(1, "All Team B modules import without error", True)
except ImportError as e:
    check(1, "All Team B modules import without error", False, str(e))

# CHECK 2 — GOVERNED_BY is in TRAVERSAL_RELATIONS
print("\n" + "-" * 60)
try:
    from src.schemas.kg import KGRelation

    if KGRelation.GOVERNED_BY not in TRAVERSAL_RELATIONS:
        check(
            2,
            "GOVERNED_BY is in TRAVERSAL_RELATIONS",
            False,
            "GOVERNED_BY missing — placement rules will never reach query results",
        )
    else:
        check(2, "GOVERNED_BY is in TRAVERSAL_RELATIONS", True)
except Exception as e:
    check(2, "GOVERNED_BY is in TRAVERSAL_RELATIONS", False, f"{type(e).__name__}: {e}")

# CHECK 3 — KnowledgeGraph round-trip save/load
print("\n" + "-" * 60)
try:
    from src.schemas.datasheet import ExtractionMethod
    from src.schemas.kg import KGEdge, KGNode, KGNodeType, KGRelation

    node_a = KGNode(
        id="physics_concept:resistor",
        node_type=KGNodeType.PHYSICS_CONCEPT,
        layer=1,
        label="resistor",
        source="test",
        confidence=0.9,
        extraction_method=ExtractionMethod.MANUAL,
        created_at="2026-01-01T00:00:00Z",
    )
    node_b = KGNode(
        id="component_type:fixed_resistor",
        node_type=KGNodeType.COMPONENT_TYPE,
        layer=2,
        label="fixed_resistor",
        source="test",
        confidence=0.85,
        extraction_method=ExtractionMethod.MANUAL,
        created_at="2026-01-01T00:00:00Z",
    )
    edge = KGEdge(
        source_id="physics_concept:resistor",
        relation=KGRelation.IS_A,
        target_id="component_type:fixed_resistor",
        constraints={},
        source_document="test",
        confidence=0.9,
        layer=1,
    )

    graph = KnowledgeGraph()
    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_edge(edge)

    with tempfile.NamedTemporaryFile(suffix=".graphml", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        graph.save(tmp_path)
        loaded = KnowledgeGraph.load(tmp_path)
        stats = loaded.stats()

        errors = []
        if stats["node_count"] != 2:
            errors.append(f"node_count={stats['node_count']}, expected 2")
        if stats["edge_count"] != 1:
            errors.append(f"edge_count={stats['edge_count']}, expected 1")

        loaded_node = loaded.get_node("physics_concept:resistor")
        if loaded_node is None or loaded_node.label != "resistor":
            label = loaded_node.label if loaded_node else None
            errors.append(f"loaded node label={label!r}, expected 'resistor'")

        if errors:
            check(3, "KnowledgeGraph round-trip save/load", False, "; ".join(errors))
        else:
            check(3, "KnowledgeGraph round-trip save/load", True)
    finally:
        tmp_path.unlink(missing_ok=True)
except Exception as e:
    check(3, "KnowledgeGraph round-trip save/load", False, f"{type(e).__name__}: {e}")

# CHECK 4 — seed_default_methodologies creates exactly 5 nodes
print("\n" + "-" * 60)
try:
    graph = KnowledgeGraph()
    seed_default_methodologies(graph, config)
    nodes = list_methodologies(graph)

    errors = []
    if len(nodes) != 5:
        errors.append(f"expected 5 methodology nodes, got {len(nodes)}")
    if any(n.layer != 5 for n in nodes):
        errors.append("not all methodology nodes have layer=5")
    if any(n.confidence != 1.0 for n in nodes):
        errors.append("not all methodology nodes have confidence=1.0")

    names = [n.label for n in nodes]
    print(f"  Methodology names found: {names}")

    if errors:
        check(4, "seed_default_methodologies creates exactly 5 nodes", False, "; ".join(errors))
    else:
        check(4, "seed_default_methodologies creates exactly 5 nodes", True)
except Exception as e:
    check(4, "seed_default_methodologies creates exactly 5 nodes", False, f"{type(e).__name__}: {e}")

# CHECK 5 — p1_importer edge direction is correct
print("\n" + "-" * 60)
try:
    from src.schemas.datasheet import (
        ComponentDatasheet,
        ElectricalParameter,
        ExtractedValue,
        ExtractionMethod,
        PinDefinition,
        PlacementConstraint,
        TableSectionType,
    )

    fixture = ComponentDatasheet(
        component_id="TEST001",
        manufacturer="TI",
        description="Test IC",
        package="SOT-23-5",
        source_pdf_hash="abc123",
        extraction_method=ExtractionMethod.P1_VECTOR,
        extraction_confidence=0.92,
        created_at="2026-01-01T00:00:00Z",
        pins=[
            PinDefinition(pin_number="1", raw_name="VCC", pin_type="power", source_page=1),
        ],
        electrical_parameters=[
            ElectricalParameter(
                parameter_name="Supply Voltage",
                symbol="VCC",
                value=ExtractedValue(raw_text="3.3V", confidence=0.95),
                section_type=TableSectionType.ELECTRICAL_CHARACTERISTICS,
                source_page=2,
                source_table_index=0,
            )
        ],
        layout_constraints=[
            PlacementConstraint(
                constraint_type="proximity",
                subject="C1",
                relative_to="TEST001.VCC",
                relative_to_type="pin",
                hard=True,
                source_sentence="Place C1 near VCC pin",
                confidence=0.85,
            )
        ],
    )

    graph = KnowledgeGraph()
    import_datasheet(fixture, graph, config)

    instance_id = "component_instance:TEST001"
    errors = []
    if not graph.node_exists(instance_id):
        errors.append(f"node missing: {instance_id}")
    if not graph.node_exists("pin:TEST001:1"):
        errors.append("node missing: pin:TEST001:1")

    governed_edges = graph.get_edges_from(instance_id, KGRelation.GOVERNED_BY)
    if len(governed_edges) == 0:
        errors.append(
            "No GOVERNED_BY edges from ComponentInstance — placement rules unreachable"
        )
    elif not governed_edges[0].target_id.startswith("placement_rule:"):
        errors.append(
            f"GOVERNED_BY target={governed_edges[0].target_id!r}, "
            "expected placement_rule: prefix"
        )

    if errors:
        check(5, "p1_importer edge direction is correct", False, "; ".join(errors))
    else:
        check(5, "p1_importer edge direction is correct", True)
except Exception as e:
    check(5, "p1_importer edge direction is correct", False, f"{type(e).__name__}: {e}")

# CHECK 6 — query_graph returns DesignSubgraph on empty graph
print("\n" + "-" * 60)
try:
    from src.schemas.intent import DesignMethodology, IntentDict
    from src.schemas.kg import DesignSubgraph

    graph = KnowledgeGraph()
    seed_default_methodologies(graph, config)
    intent = IntentDict(
        goal="ldo_regulator",
        application="test",
        design_methodology=DesignMethodology.POWER_MANAGEMENT,
        board_type="standard_SMD",
        raw_prompt="test",
    )
    result = query_graph(intent, graph, config)

    errors = []
    if not isinstance(result, DesignSubgraph):
        errors.append(f"expected DesignSubgraph, got {type(result).__name__}")
    if result.component_types is None:
        errors.append("component_types is None")
    if result.placement_rules is None:
        errors.append("placement_rules is None")

    print(f"  Returned subgraph with {len(result.component_types)} component types")

    if errors:
        check(6, "query_graph returns DesignSubgraph on empty graph", False, "; ".join(errors))
    else:
        check(6, "query_graph returns DesignSubgraph on empty graph", True)
except Exception as e:
    check(6, "query_graph returns DesignSubgraph on empty graph", False, f"{type(e).__name__}: {e}")

# CHECK 7 — pin normalizer returns new objects, never mutates
print("\n" + "-" * 60)
try:
    def _make_pin_ds(component_id: str, pins: list[tuple[str, str]]) -> ComponentDatasheet:
        return ComponentDatasheet(
            component_id=component_id,
            manufacturer="TI",
            description="Test",
            package="SOIC-8",
            source_pdf_hash="hash",
            extraction_method=ExtractionMethod.P1_VECTOR,
            extraction_confidence=0.9,
            created_at="2026-01-01T00:00:00Z",
            pins=[
                PinDefinition(
                    pin_number=num,
                    raw_name=name,
                    normalized_function=None,
                    pin_type="io",
                )
                for num, name in pins
            ],
        )

    ds1 = _make_pin_ds("IC1", [("1", "VCC"), ("2", "GND")])
    ds2 = _make_pin_ds("IC2", [("1", "SDA"), ("2", "SCL")])

    results_list = normalize_pins([ds1, ds2], config)

    errors = []
    if results_list is ds1 or results_list is ds2:
        errors.append("returned list is same object as input datasheet")
    if any(r is ds for r, ds in zip(results_list, [ds1, ds2])):
        errors.append("returned datasheet is same object as input")
    if any(
        rpin is opin
        for r, ds in zip(results_list, [ds1, ds2])
        for rpin, opin in zip(r.pins, ds.pins)
    ):
        errors.append("returned pin is same object as input pin")

    if errors:
        check(7, "pin normalizer returns new objects, never mutates", False, "; ".join(errors))
    else:
        print("  All pins are new objects: PASS")
        check(7, "pin normalizer returns new objects, never mutates", True)
except Exception as e:
    check(7, "pin normalizer returns new objects, never mutates", False, f"{type(e).__name__}: {e}")

# CHECK 8 — mypy on src/knowledge_graph/
print("\n" + "-" * 60)
try:
    mypy_result = subprocess.run(
        ["mypy", "src/knowledge_graph/", "--ignore-missing-imports"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    output = (mypy_result.stdout + mypy_result.stderr).strip()
    error_lines = [
        line for line in output.split("\n") if line.strip() and "error:" in line.lower()
    ]

    if mypy_result.returncode != 0 or error_lines:
        check(
            8,
            "mypy on src/knowledge_graph/",
            False,
            "\n  ".join([""] + error_lines[:25]),
        )
    else:
        check(8, "mypy on src/knowledge_graph/", True)
except Exception as e:
    check(8, "mypy on src/knowledge_graph/", False, f"{type(e).__name__}: {e}")

print("\n" + "=" * 60)
passed = sum(1 for _, _, p, _ in results if p)
total = len(results)

if passed == total:
    print(f"Team B: PASS ({passed}/{total} checks passed)")
else:
    print(f"Team B: FAIL ({passed}/{total} checks passed)")
    print("\nFailed checks:")
    for num, name, p, error in results:
        if not p:
            print(f"  CHECK {num} — {name}")
            if error:
                print(f"    {error}")

print("=" * 60)
sys.exit(0 if passed == total else 1)
