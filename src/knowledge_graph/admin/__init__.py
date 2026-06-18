"""Knowledge graph admin package.

Provides CLI and API for manually managing KG-5 DesignMethodology nodes.

Public API:
    add_methodology(graph, name, triggers, ...)
    list_methodologies(graph)
    get_methodology(graph, name)
    seed_default_methodologies(graph, config)

CLI Usage:
    $ python -m src.knowledge_graph.admin list
    $ python -m src.knowledge_graph.admin show RF_highfreq
    $ python -m src.knowledge_graph.admin seed
    $ python -m src.knowledge_graph.admin add --name custom --triggers "a,b,c"
"""

from src.knowledge_graph.admin.methodologies import (
    DEFAULT_METHODOLOGIES,
    add_methodology,
    get_methodology,
    list_methodologies,
    seed_default_methodologies,
)

__all__ = [
    "add_methodology",
    "list_methodologies",
    "get_methodology",
    "seed_default_methodologies",
    "DEFAULT_METHODOLOGIES",
]
