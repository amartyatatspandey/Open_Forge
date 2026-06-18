"""CLI for knowledge graph admin operations.

Provides command-line interface for managing KG-5 DesignMethodology nodes.
Callable as: python -m src.knowledge_graph.admin
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence, cast

if TYPE_CHECKING:
    from src.config import Config
    from src.knowledge_graph import KnowledgeGraph

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_graph(graph_path: Path) -> KnowledgeGraph:
    """Load KnowledgeGraph from GraphML file."""
    from src.knowledge_graph import KnowledgeGraph

    if not graph_path.exists():
        # Create new graph
        graph = KnowledgeGraph()
        graph.save(graph_path)
        logger.info(f"Created new graph at {graph_path}")
        return graph

    return KnowledgeGraph.load(graph_path)


def _save_graph(graph: KnowledgeGraph, graph_path: Path) -> None:
    """Save KnowledgeGraph to GraphML file."""
    graph.save(graph_path)
    logger.info(f"Saved graph to {graph_path}")


def _get_config() -> Config:
    """Load application config."""
    from src.config import get_config

    return get_config()


def cmd_list(args: argparse.Namespace) -> int:
    """List all methodology names and trigger counts."""
    from src.knowledge_graph.admin import list_methodologies

    config = _get_config()
    graph_path = config.graph_path

    graph = _load_graph(graph_path)
    methodologies = list_methodologies(graph)

    if not methodologies:
        print("No methodologies found.")
        return 0

    print(f"{'Name':<25} {'Triggers':>10}")
    print("-" * 40)
    for node in methodologies:
        triggers = node.properties.get("triggers", [])
        print(f"{node.label:<25} {len(triggers):>10}")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Show full node properties as formatted JSON."""
    from src.knowledge_graph.admin import get_methodology

    config = _get_config()
    graph_path = config.graph_path

    graph = _load_graph(graph_path)
    node = get_methodology(graph, args.name)

    if node is None:
        logger.error(f"Methodology '{args.name}' not found")
        return 1

    # Output as formatted JSON
    output = {
        "id": node.id,
        "node_type": node.node_type.value,
        "layer": node.layer,
        "label": node.label,
        "properties": node.properties,
        "source": node.source,
        "confidence": node.confidence,
        "extraction_method": node.extraction_method.value if node.extraction_method else None,
        "created_at": node.created_at,
    }

    print(json.dumps(output, indent=2))
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    """Seed default methodologies."""
    from src.knowledge_graph.admin import seed_default_methodologies

    config = _get_config()
    graph_path = config.graph_path

    graph = _load_graph(graph_path)
    count = seed_default_methodologies(graph, config)
    _save_graph(graph, graph_path)

    print(f"Seeded {count} methodologies")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """Add a new methodology."""
    from src.knowledge_graph.admin import add_methodology

    config = _get_config()
    graph_path = config.graph_path

    # Parse comma-separated lists
    triggers = [t.strip() for t in args.triggers.split(",")] if args.triggers else []
    active = [t.strip() for t in args.active.split(",")] if args.active else []
    suppress = [t.strip() for t in args.suppress.split(",")] if args.suppress else []

    # Parse board spec defaults (simple key=value pairs)
    board_specs = {}
    if args.board_specs:
        for spec in args.board_specs.split(","):
            if "=" in spec:
                key, value = spec.split("=", 1)
                # Try to convert to int/float
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass  # Keep as string
                board_specs[key.strip()] = value

    graph = _load_graph(graph_path)
    node = add_methodology(
        graph=graph,
        name=args.name,
        triggers=triggers,
        active_constraint_types=active,
        suppressed_constraint_types=suppress,
        board_spec_defaults=board_specs,
        config=config,
    )
    _save_graph(graph, graph_path)

    print(f"Added methodology: {node.label} ({node.id})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="kg-admin",
        description="Knowledge Graph Admin CLI for managing KG-5 DesignMethodology nodes",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    list_parser = subparsers.add_parser("list", help="List all methodology names + trigger counts")
    list_parser.set_defaults(func=cmd_list)

    # show command
    show_parser = subparsers.add_parser("show", help="Show full node properties as JSON")
    show_parser.add_argument("name", help="Methodology name")
    show_parser.set_defaults(func=cmd_show)

    # seed command
    seed_parser = subparsers.add_parser("seed", help="Populate KG-5 with default methodologies")
    seed_parser.set_defaults(func=cmd_seed)

    # add command
    add_parser = subparsers.add_parser("add", help="Add a new methodology")
    add_parser.add_argument("--name", required=True, help="Methodology name")
    add_parser.add_argument(
        "--triggers", required=True,
        help="Comma-separated trigger keywords (e.g., 'buck,boost,regulator')"
    )
    add_parser.add_argument(
        "--active", default="proximity",
        help="Comma-separated active constraint types (default: proximity)"
    )
    add_parser.add_argument(
        "--suppress", default="",
        help="Comma-separated suppressed constraint types (default: empty)"
    )
    add_parser.add_argument(
        "--board-specs", default="layers=2,material=FR4",
        help="Comma-separated board specs (default: layers=2,material=FR4)"
    )
    add_parser.set_defaults(func=cmd_add)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    handler = cast(Callable[[argparse.Namespace], int], args.func)
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
