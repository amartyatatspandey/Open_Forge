# OpenForge — What's Left

> **Last updated:** 2026-06-27
> **Updated by:** Cursor
> **Rule:** Update this file whenever a task is completed, added, or reprioritised.
>            Every change must be recorded in the Change Log at the bottom.

---

## How to Use This File

- Tasks are grouped by priority tier
- Each task has a status: ⬜ Not started | 🟡 In progress | ✅ Done | 🚫 Blocked
- When you complete a task: mark ✅, move it to the Completed section, add a Change Log entry
- When you add a new task: add it to the correct tier, add a Change Log entry
- When priority changes: move it, add a Change Log entry

---

## Tier 1 — Critical Path (blocks E2E system from running)

All Tier 1 tasks complete. E2E orchestrator path is wired end-to-end.

---

## Tier 2 — Parsing System (modular backend)

Modular parser backends implemented and gate-tested. Remaining work is GPU validation and Phase 3 eval.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | GPU lab validation — Phase 2 VLM + Phase 3 LLM with real weights | ⬜ Not started | vlm_enabled: true run on lab GPU |
| 2.2 | Phase 3 eval harness — field_f1 ≥ 0.93 gate on 5 golden datasheets | ⬜ Not started | Needs grid-level ground truth annotation |

### Parser full-scope coverage (beyond analog/power ICs)

> Source: [parser_fullscope_gap_analysis.md](improvement_plan/parser_fullscope_gap_analysis.md)
> Baseline: TI analog/power ICs, tabular data, pinouts under ~30 pins.
> Target: MCU, digital IC, RF, sensor, power MOSFET, and related datasheet types.

| # | Task | Status | Severity | Blocks | Notes |
|---|------|--------|----------|--------|-------|
| 2.3 | Gap 1 — Large MCU pinout tables (chunking + AF columns) | ⬜ Not started | HIGH | MCU schematic synthesis | Pin table chunking, AF0–AF15 parser, >50-row heuristic in section classifier; `prompt_templates.py`, `extractor.py` |
| 2.4 | Gap 2 — Structured alternate-function / pin mux extraction | ⬜ Not started | HIGH | MCU net assignment | `PinDefinition` schema bump (`default_function`, `AlternateFunction`); P2 multi-function normalization; DB migration |
| 2.5 | Gap 3 — RF parameter units and section keywords | ⬜ Not started | MEDIUM | RF methodology BOMs | Add dBm, dBc, dB, ppm to `unit_normalizer.py`; RF keywords in `section_classifier.py`; RF prompt context |
| 2.6 | Gap 4 — Timing table vs timing diagram split | ⬜ Not started | MEDIUM | Clean MCU extraction | Phase 1 figure-vs-table split on TIMING regions; skip waveform figures to `review_flags`; Baidu OCR `type=figure` helps |
| 2.7 | Gap 5 — Thermal data for power devices | ⬜ Not started | MEDIUM | Thermal review flags | Thermal section keywords → extraction; θJA/θJC in Phase 3 prompt; `°C/W` in unit normalizer |
| 2.8 | Gap 6 — Connector mechanical data | 🚫 Out of scope | LOW | — | Footprint library lookup, not datasheet extraction |
| 2.9 | Gap 7 — FPGA datasheets | 🚫 Defer v2 | LOW | — | Bank-aware pin extraction + I/O standard tables; skeleton + `review_required=True` until then |

**Coverage gaps not yet in pipeline:** register maps (I2C/SPI sensors), dense timing tables on interface ICs, crystal frequency units (partial), large MCU pin counts (144+).

**Maintenance follow-up:** `tests/unit/intent/test_pipeline_stage2.py` still unpacks 2-tuple from `run_intent_pipeline` — update to triple after Tier 1.5.

---

## Tier 3 — Knowledge Base Population

These populate the KG. System can run without them but will produce poor BOMs.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 3.1 | Book parser (KG-1) — replace spaCy primary with LLM-primary triple extraction | ⬜ Not started | spaCy stays as sentence boundary only |
| 3.2 | Book parser (KG-1) — add chapter classifier to route formula-heavy chapters | ⬜ Not started | Keyword heuristic, no ML needed |
| 3.3 | Nexar batch pre-ingestion CLI — GraphQL client + PDF downloader + batch runner | ⬜ Not started | Three-component build |
| 3.4 | KiCad library file importer (Tier 0) — s-expression parser → KG writer | ⬜ Not started | Deterministic, no ML |
| 3.5 | App note prose extractor — placement rule extraction from app note text | ⬜ Not started | placement_extractor.py is a stub |
| 3.6 | Run KB population — Nexar batch pre-ingestion on 10 priority components | ⬜ Not started | Depends on 3.3 |

---

## Tier 4 — Quality and Evaluation

These improve accuracy. System runs without them but evaluation is incomplete.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 4.1 | Curate 25-datasheet test corpus in corpus/test/ | ⬜ Not started | Currently 0/25; should span component types in gap analysis matrix (not just analog/power) |
| 4.2 | Few-shot examples for Phase 3 extraction prompts | ⬜ Not started | See brainstorming/FEW_SHOT_PROMPT_ANALYSIS.md |
| 4.3 | Few-shot examples for Phase 5 layout extraction prompts | ⬜ Not started | Same doc |
| 4.4 | Pin normalizer LLM fallback few-shot examples | ⬜ Not started | Same doc |

---

## Tier 5 — Research Paper

| # | Task | Status | Notes |
|---|------|--------|-------|
| 5.1 | Write Section 1 — Introduction | ⬜ Not started | Target: DAC/DATE/ICCAD or NeurIPS/ICLR ML-for-Systems workshop |
| 5.2 | Write Section 2 — Related Work | ⬜ Not started | Start here, parallel with code |
| 5.3 | Design evaluation benchmark for paper | ⬜ Not started | Needs E2E system working |
| 5.4 | Run experiments and collect results | ⬜ Not started | Needs Tier 1 + Tier 2 complete |
| 5.5 | Write remaining sections + submit | ⬜ Not started | 4–6 page workshop format |

---

## Completed Tasks

Record every finished task here with date.

| Date | Task | Notes |
|------|------|-------|
| 2026-06-27 | RetrievalEngine wired into intent pipeline (task 1.5) | Stage 2.5 _run_retrieval; triple return; generate_bom stub kwarg; 8/8 gate tests |
| 2026-06-27 | Stage 2 wired into intent pipeline (task 1.3) | _run_stage2 + Gate 2 in run_intent_pipeline; 7/7 gate tests |
| 2026-06-27 | E2E orchestrator — src/orchestrator.py + 8/8 gate tests | run_e2e() wires Teams A–E; never raises |
| 2026-06-27 | PARSER_P1 — Backend interfaces + registry | Gate-tested in Cursor |
| 2026-06-27 | PARSER_P2 — YOLOv8 LayoutDetectorBackend | Gate-tested in Cursor |
| 2026-06-27 | PARSER_P3 — PaddleOCR ImageTableBackend | Gate-tested in Cursor |
| 2026-06-27 | PARSER_P4 — pdfplumber+Camelot VectorTableBackend | Gate-tested in Cursor |
| 2026-06-27 | PARSER_P5 — Qwen2-VL ImageTableBackend (swap proof) | Gate-tested in Cursor |
| 2026-06-27 | PARSER_P6 — Qwen2.5-7B LLMBackend | Gate-tested in Cursor |
| 2026-06-27 | PARSER_P7 — Modular pipeline orchestrator | Gate-tested in Cursor |
| 2026-06-27 | PARSER_P8 — PostgreSQL ComponentDatasheet writer | Gate-tested in Cursor |
| 2026-06-27 | Run PARSER_P1–P8 in Cursor (gate test each) | All 8 phases executed and gate-tested |
| 2026-06-27 | PARSER_P1 through P8 prompts written | All 8 prompts designed by Claude |
| 2026-06-27 | Modular parser backend architecture designed | BackendRegistry, 5 interfaces, plug-and-play config |
| 2026-06-26 | Stage 05 search/storage/deployment complete | Synonym expansion, coverage reporting, model pinning |
| 2026-06-26 | Retrieval engine (Stage 3) gate pass — 36/36 tests | RetrievalEngine built; not yet wired to BOM |
| 2026-06-21 | Stage 2 completion engine smoke-tested — 12/12 pass | Not yet wired into main intent pipeline |
| Prior | All team gates A–F passing — 699 unit tests | Teams A/B/C/D/E/F all gate-tested |
| Prior | 5/5 golden corpus Phase 1 eval — 100% recall/precision | YOLOv8 DLA validated |
| Prior | PARSING_SCOPE_AND_ARCHITECTURE.md written | Tiered parsing architecture decided |

---

## Change Log

Every change to this file must be recorded here.
Format: `YYYY-MM-DD | action | what changed | why`

| Date | Action | What | Why |
|------|--------|------|-----|
| 2026-06-27 | ADDED | Parser full-scope gaps 2.3–2.9 from gap analysis | Track MCU/RF/thermal coverage beyond analog/power baseline |
| 2026-06-27 | COMPLETED | RetrievalEngine BOM wiring (task 1.5) | tier_1.5_prompt implemented; 8/8 unit gate tests pass; orchestrator triple unpack |
| 2026-06-27 | COMPLETED | Embedding ingestion pipeline (task 1.4) | tier_1.4_prompt implemented; 10/10 unit gate tests pass |
| 2026-06-27 | COMPLETED | Stage 2 intent pipeline wiring (task 1.3) | tier_1.3_prompt implemented; 7/7 unit gate tests pass |
| 2026-06-27 | COMPLETED | E2E orchestrator (task 1.2) — src/orchestrator.py | Tier 1 prompt implemented; 8/8 unit gate tests pass |
| 2026-06-27 | COMPLETED | PARSER_P1–P8 executed and gate-tested in Cursor | User confirmed all 8 parser phases done |
| 2026-06-27 | CREATED | Initial version of WHATS_LEFT.md | First creation during document reorganisation |
