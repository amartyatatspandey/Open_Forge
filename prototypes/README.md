# Prototypes

This directory holds early standalone experiments that predated the unified OpenForge PCB system.

## p1-parser

The **original standalone P1 prototype** (`drdo-p1-parser`). It implements the four-phase datasheet parsing pipeline (DLA → TSR → extraction → validation) with golden corpus eval harnesses.

**Canonical P1 code** is now at [`src/datasheet/`](../src/datasheet/) in the repo root, which extends the prototype with phase 5 (layout section extraction) and integrates with the full PCB pipeline.

This prototype is kept for:

- Golden corpus and ground-truth JSON
- Phase 1–4 eval history and reference implementation
- Isolated development and comparison

### Run in isolation

```bash
cd prototypes/p1-parser
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -q
```
