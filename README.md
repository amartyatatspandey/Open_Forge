<p align="center">
  <strong>Open Forge</strong>
</p>

<p align="center">
  <em>Air-gapped, intelligence-driven PCB design — from natural language prompt to fabrication-ready output.</em>
</p>

<p align="center">
  <a href="#the-vision">Vision</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#project-structure">Structure</a> ·
  <a href="#getting-started">Getting Started</a> ·
  <a href="#documentation">Documentation</a>
</p>

---

## The Vision

Electronic design automation still depends on humans manually reading datasheets, selecting components, and wiring schematics by hand. **Open Forge** is an open-source PCB intelligence system that automates this path: parse datasheets, ground decisions in an engineering knowledge graph, generate a validated bill of materials, synthesize schematics, and produce layout-ready specifications — with every value traceable to an authoritative source.

The system is built for **air-gapped, on-prem deployment**. No cloud APIs. All model weights run locally. Deterministic output over probabilistic guesswork.

---

## Architecture

Open Forge implements six interconnected engineering problems (P1–P6) as a unified pipeline:

```
Natural Language Prompt
        ↓
Intent Parser → Knowledge Graph Query → BOM Generator
        ↓
Datasheet Parser (P1) → Pin Normalizer (P2) → Schematic Synthesizer (P5)
        ↓
Layout Engine → NIR → KiCad / tscircuit Export
```

See [`documents/architecture/OPENFORGE_ARCHITECTURE.md`](documents/architecture/OPENFORGE_ARCHITECTURE.md) for the full system design reference.

---

## Project Structure

```
├── documents/                  # Specs, architecture, assessments
│   └── architecture/           # OPENFORGE_*.md — authoritative system design
├── prototypes/
│   └── p1-parser/              # Legacy standalone P1 prototype (reference only)
├── src/                          # Main codebase
│   ├── intent/                   # NL prompt → intent_dict
│   ├── knowledge_graph/          # KG build, query, ingestion
│   ├── bom/                      # BOM generation and validation
│   ├── datasheet/                # P1 parser (canonical — phases 1–5)
│   ├── schematic/                # Schematic synthesis
│   ├── layout/                   # Layout spec generation
│   ├── nir/                      # Netlist Intermediate Representation
│   └── synthesis/                # End-to-end pipeline
├── tests/                        # Unit tests
├── eval/gates/                   # Team acceptance gates (A–F)
├── configs/                      # YAML configuration
├── corpus/golden/                # Hand-verified TI golden corpus
└── pyproject.toml                # Package: openforge-pcb
```

### Key documentation

| Document | Purpose |
|----------|---------|
| [`documents/architecture/OPENFORGE_ARCHITECTURE.md`](documents/architecture/OPENFORGE_ARCHITECTURE.md) | Master system architecture |
| [`documents/architecture/OPENFORGE_SUBSYSTEMS.md`](documents/architecture/OPENFORGE_SUBSYSTEMS.md) | Subsystem specifications |
| [`documents/architecture/OPENFORGE_INTEGRATION.md`](documents/architecture/OPENFORGE_INTEGRATION.md) | KiCad + tscircuit integration |
| [`documents/architecture/PROJECT_CONTEXT.md`](documents/architecture/PROJECT_CONTEXT.md) | Living project status |
| [`prototypes/p1-parser/README.md`](prototypes/p1-parser/README.md) | Legacy P1 prototype setup |

---

## Getting Started

### Prerequisites

- Python 3.10+
- [Poppler](https://poppler.freedesktop.org/) — `brew install poppler` (macOS) or `poppler-utils` (Ubuntu)
- CUDA 11.8+ optional (CPU-only mode supported; VLM inference is slower)

### Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Run unit tests
pytest tests/unit -q

# Run team acceptance gates
python eval/gates/team_a_gate.py
python eval/gates/team_b_gate.py
python eval/gates/team_c_gate.py
python eval/gates/team_d_gate.py
```

### Legacy P1 prototype

The original standalone four-phase parser lives at [`prototypes/p1-parser/`](prototypes/p1-parser/) for golden corpus eval history and reference. Canonical P1 code is at [`src/datasheet/`](src/datasheet/).

---

## Contributing

1. Read [`documents/architecture/OPENFORGE_ARCHITECTURE.md`](documents/architecture/OPENFORGE_ARCHITECTURE.md) for system design
2. Follow [`documents/guides/CODING_STANDARDS_P1.md`](documents/guides/CODING_STANDARDS_P1.md) for code style
3. Run `pytest tests/unit` and relevant team gates before opening a PR
4. Update [`documents/architecture/PROJECT_CONTEXT.md`](documents/architecture/PROJECT_CONTEXT.md) when a milestone is reached

---

## License

Open source. See repository license for details.

---

<p align="center">
  <strong>Open Forge</strong> — structured intelligence for the boards we build.
</p>
