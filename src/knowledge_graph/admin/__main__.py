"""Entry point for `python -m src.knowledge_graph.admin`."""

from __future__ import annotations

import sys

from src.knowledge_graph.admin.cli import main

if __name__ == "__main__":
    sys.exit(main())
