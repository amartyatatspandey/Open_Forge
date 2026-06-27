# OpenForge — What's Left

> **Last updated:** 2026-06-27
> **Updated by:** Claude
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

These must be done before the system can produce any output end-to-end.

| # | Task | Status | Blocks | Notes |
|---|------|--------|--------|-------|
| 1.1 | Run PARSER_P1–P8 in Cursor (gate test each) | 🟡 In progress | Everything downstream | Prompts written, execution pending |
| 1.2 | E2E orchestrator — wire all team pipelines into single prompt→files entry point | ⬜ Not started | First real E2E run | One Cursor prompt needed |
| 1.3 | ImprovedIntentDict v2 migration — wire Stage 2 into main intent pipeline | ⬜ Not started | Stage 2 activation | Prompt already written; not executed |
| 1.4 | Embedding ingestion pipeline — write ComponentDatasheet embeddings to PostgreSQL component_embeddings | ⬜ Not started | Vector search | Schema ready; no writer exists |
| 1.5 | Wire RetrievalEngine into BOM/synthesis orchestrator | ⬜ Not started | Retrieval-grounded BOM | RetrievalEngine built; not connected |

---

## Tier 2 — Parsing System (modular backend)

Parser prompts written. Must be executed and gate-tested in Cursor sequentially.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | PARSER_P1 — Backend interfaces + registry | 🟡 In progress | Prompt in parsing/PARSER_CURSOR_PROMPTS/ |
| 2.2 | PARSER_P2 — YOLOv8 LayoutDetectorBackend | ⬜ Not started | Depends on P1 gate pass |
| 2.3 | PARSER_P3 — PaddleOCR ImageTableBackend | ⬜ Not started | Depends on P1 gate pass |
| 2.4 | PARSER_P4 — pdfplumber+Camelot VectorTableBackend | ⬜ Not started | Depends on P1 gate pass |
| 2.5 | PARSER_P5 — Qwen2-VL ImageTableBackend (swap proof) | ⬜ Not started | Depends on P1 gate pass |
| 2.6 | PARSER_P6 — Qwen2.5-7B LLMBackend | ⬜ Not started | Depends on P1 gate pass |
| 2.7 | PARSER_P7 — Modular pipeline orchestrator | ⬜ Not started | Depends on P2–P6 gate pass |
| 2.8 | PARSER_P8 — PostgreSQL ComponentDatasheet writer | ⬜ Not started | Depends on P7 gate pass |
| 2.9 | GPU lab validation — Phase 2 VLM + Phase 3 LLM with real weights | ⬜ Not started | vlm_enabled: true run on lab GPU |
| 2.10 | Phase 3 eval harness — field_f1 ≥ 0.93 gate on 5 golden datasheets | ⬜ Not started | Needs grid-level ground truth annotation |

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
| 4.1 | Curate 25-datasheet test corpus in corpus/test/ | ⬜ Not started | Currently 0/25 |
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
| 2026-06-27 | PARSER_P1 through P8 prompts written | All 8 prompts designed by Claude; execution in Cursor pending |
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
| 2026-06-27 | CREATED | Initial version of WHATS_LEFT.md | First creation during document reorganisation |
