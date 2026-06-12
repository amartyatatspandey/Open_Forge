# DRDO P1 — Project Context (Living Document)

> **Purpose:** Single attachable context file for Claude Projects, Cursor, and handoffs.
> **Update rule:** Edit this file at the end of every phase completion (see §2).
> **Do not duplicate** the full assessment spec here — link to it.

---

## 1. Snapshot

| Field | Value |
|-------|-------|
| **Last updated** | 2026-06-12 |
| **Updated by** | Phase 4 validation + KiCad export implemented (FPR/FNR eval deferred) |
| **Current phase** | Phase 4 — **implemented**; pipeline orchestrator + review queue pending |
| **Active work** | GPU lab Phase 2 eval; grid-level golden GT; `pipeline.py` + review queue |
| **Repo root** | `DRDO/` |
| **Code root** | `drdo-p1-parser/` |

### Phase dashboard

| Phase | Name | Status | Exit criteria met? |
|-------|------|--------|-------------------|
| **0** | Spike & Tooling | 🟡 Substantially complete | Partial — see §5 |
| **1** | DLA Implementation | ✅ Complete | Yes — 5/5 golden PASS |
| **2** | TSR Implementation | 🟡 Implemented | No — metrics deferred |
| **3** | Extraction | 🟡 Implemented | No — golden eval deferred |
| **4** | Validation + Integration | 🟡 Implemented | No — FPR/FNR eval deferred |
| **5** | Docker + Delivery | ⬜ Not started | — |

**Legend:** ✅ Complete · 🟡 In progress / partial · ⬜ Not started

---

## 2. Phase completion update protocol

When a phase is **declared complete**, update the following sections in order:

1. **§1 Snapshot** — `Last updated`, `Current phase`, `Active work`, phase dashboard row
2. **§5 Phase detail** — mark phase checklist items `[x]`, record measured metrics vs targets
3. **§6 Code inventory** — list new modules/files added
4. **§7 Model & corpus status** — if weights or corpus changed
5. **§9 Blockers** — remove resolved items; add new ones
6. **§11 Changelog** — one row: date, phase, summary, who/what triggered update

### Phase sign-off checklist (copy per phase)

```markdown
### Phase N sign-off — YYYY-MM-DD
- [ ] All module files implemented per assessment §6
- [ ] Unit/integration tests pass (`pytest`)
- [ ] Exit metrics measured on golden set (record in §5)
- [ ] README.md phase status updated
- [ ] PROJECT_CONTEXT.md §1, §5, §6, §11 updated
- [ ] SPIKE_RESULTS.md or eval reports updated (if applicable)
```

---

## 3. Mission & scope

**Problem 1 (P1):** Extract tabular data — electrical characteristics, absolute maximum ratings, pinouts — from heterogeneous Texas Instruments PDF datasheets into validated, machine-readable JSON for downstream KiCad MCP consumption.

| In scope | Out of scope (P1) |
|----------|-------------------|
| DLA → TSR → extraction → physics validation | Problems 2–6 (pin normalization, block diagrams, KG, netlisting, MCP server) |
| Pinouts + abs-max ratings | Package/mechanical dimensions |
| Air-gapped / on-prem deployment | Cloud APIs (Gemini, etc.) |
| Analog/power IC datasheets | MCUs, DSPs, FPGAs (254-page DSP corpus archived) |
| Output contract JSON (`<component_id>_parsed.json`) | KiCad MCP integration code |

**Deployment:** Air-gapped. All model weights baked into Docker image (Phase 5).

---

## 4. Documentation authority

Read in this order when implementing:

| Priority | File | Role |
|----------|------|------|
| 1 | `documents/assessments/p1_assessment_filled.md` | **Authoritative** — schema, models, metrics, phased plan, output contract |
| 2 | `documents/architecture/PROJECT_CONTEXT.md` | **This file** — current status only |
| 3 | `documents/guides/CODING_STANDARDS_P1.md` | Code style, TDD, config patterns |
| 4 | `documents/guides/QUICK_REFERENCE_PATTERNS.md` | Good/bad patterns cheat sheet |
| 5 | `documents/architecture/problem_1_solution.md` | 4-phase architecture narrative |
| 6 | `documents/guides/PROJECT_BOOTSTRAP_GUIDE.md` | Scaffolding templates |
| 7 | `documents/objectives.md` | Six formal DRDO problem statements |
| 8 | `documents/phase1/PHASE1_CORPUS_EVAL_TUNING_LOG.md` | Golden corpus eval tuning history |

**Superseded:** `documents/assessments/p1_assessment.md` — use `_filled` instead.

**Index:** `documents/README.md`

---

## 5. Phase detail

### Phase 0 — Spike & Tooling

**Target exit criteria:** Model choices locked; golden corpus annotation ≥ 60% complete.

| Task | Status | Notes |
|------|--------|-------|
| Project scaffold (`pyproject.toml`, dirs, venv) | ✅ | `drdo-p1-parser/` |
| `src/config.py` + `configs/default.yaml` | ✅ | Locked model paths, thresholds |
| `src/schemas/datasheet.py` (output contract) | ✅ | `ComponentDatasheet`, etc. |
| `src/schemas/pipeline.py` (inter-phase models) | ✅ | `GridMatrix`, `Phase1Output`, … |
| `src/logging_config.py`, `src/utils/exceptions.py` | ✅ | |
| Unit tests (`test_schemas.py`, `test_config.py`) | ✅ | 26 tests passing |
| `scripts/download_models.py` | ✅ | HF download + shard resume |
| Golden corpus 5/5 annotated | ✅ | See §7 |
| Model spike (YOLOv8 vs Surya) | 🟡 | Ran without weights; **re-run required** |
| Qwen2-VL download | ✅ | 20.23 GB verified (2026-06-12) |
| Qwen2.5-7B download | 🟡 | Shard download in progress |
| Test corpus (25 PDFs) | ⬜ | `corpus/test/` empty |

**Phase 0 metrics (spike — stale):**

| Metric | YOLOv8 | Surya | Target |
|--------|--------|-------|--------|
| Table detection recall | 0.000 | N/A | ≥ 0.92 |
| Footnote detection recall | 0.000 | N/A | ≥ 0.85 |

**Locked model choice (pre-spike):** YOLOv8n-DocLayNet. Re-run spike at `eval/spike/run_spike.py` → `eval/spike/SPIKE_RESULTS.md`.

---

### Phase 1 — DLA Implementation ✅

**Target exit criteria:** Table recall ≥ 0.92, precision ≥ 0.90, footnote recall ≥ 0.85, section acc ≥ 0.85 on golden set.

| Module | Status |
|--------|--------|
| `src/phase1_dla/rasterize.py` | ✅ |
| `src/phase1_dla/detect.py` | ✅ |
| `src/phase1_dla/classify_section.py` | ✅ |
| `src/phase1_dla/footnote_linker.py` | ✅ |
| `src/phase1_dla/multipage_merge.py` | ✅ |
| `src/phase1_dla/pdf_offset.py` | ✅ |
| `src/phase1_dla/runner.py` | ✅ |
| `eval/phase1/run_eval.py` | ✅ |

**Measured metrics (2026-06-12, all 5 golden components):**

| Component | Recall | Precision | Footnote | Section Acc |
|-----------|--------|-----------|----------|-------------|
| SN74LVC1G04 | 100% | 100% | 100% | 100% |
| TLV7021 | 100% | 100% | 100% | 100% |
| INA219 | 100% | 100% | 100% | 100% |
| LM5176 | 100% | 100% | 100% | 100% |
| TPS62933 | 100% | 100% | 100% | 100% |

Report: `drdo-p1-parser/eval/phase1/PHASE1_RESULTS.md`

---

### Phase 2 — TSR Implementation 🟡

**Target exit criteria:** Cell accuracy ≥ 0.95, merged-cell accuracy ≥ 0.90 on golden set.

| Module | Status |
|--------|--------|
| `src/phase2_tsr/merged_cell_handler.py` | ✅ |
| `src/phase2_tsr/confidence_scorer.py` | ✅ |
| `src/phase2_tsr/path_a_vector.py` | ✅ |
| `src/phase2_tsr/path_b_vlm.py` | ✅ |
| `src/phase2_tsr/runner.py` | ✅ |
| `eval/phase2/run_eval.py` | ✅ (stub — metrics deferred) |
| `tests/fixtures/phase2_mock_outputs.py` | ✅ |

**Config:** `phase2_tsr` block in `configs/default.yaml` (`vlm_enabled: false` on MacBook).

**Measured metrics:** — *deferred* (no grid-level golden GT; run on GPU lab with `vlm_enabled: true`)

**Blocker for exit gate:** Annotate cell-level grid GT in `corpus/golden/` before `cell_accuracy` / `merged_cell_accuracy` can be measured.

---

### Phase 3 — Extraction 🟡

**Target exit criteria:** Field F1 ≥ 0.93, unit normalization accuracy = 1.0 on golden set.

| Module | Status |
|--------|--------|
| `src/phase3_extract/table_utils.py` | ✅ |
| `src/phase3_extract/unit_normalizer.py` | ✅ |
| `src/phase3_extract/parameter_extractor.py` | ✅ |
| `src/phase3_extract/pinout_extractor.py` | ✅ |
| `src/phase3_extract/absolute_max_extractor.py` | ✅ |
| `src/phase3_extract/footnote_resolver.py` | ✅ |
| `src/phase3_extract/validation.py` | ✅ |
| `src/phase3_extract/runner.py` | ✅ |
| `src/phase3_extract/prompt_templates.py` | ✅ (LLM stub — not wired) |
| `src/phase3_extract/extractor.py` | ✅ (LLM stub — disabled by default) |
| `tests/fixtures/phase2_mock_outputs.py` | ✅ (5-component golden mocks) |

**Config:** `phase3_extract` block in `configs/default.yaml` (`llm_enabled: false` on MacBook).

**Tests:** 53 passing — `pytest tests/unit/test_phase3_*.py tests/integration/test_phase3_e2e.py -v`

**Measured metrics:** — *deferred* (requires `eval/phase3/` harness vs `*_ground_truth.json`)

**Blocker for exit gate:** Golden semantic GT comparison (`field_f1 ≥ 0.93`); Qwen2.5 LLM path optional on GPU lab.

---

### Phase 4 — Validation + KiCad Export 🟡

**Target exit criteria:** FPR ≤ 0.02, FNR ≤ 0.01; end-to-end on 30-datasheet corpus.

| Module | Status |
|--------|--------|
| `src/phase4_validate/ordering_rules.py` | ✅ |
| `src/phase4_validate/sanity_ranges.py` | ✅ |
| `src/phase4_validate/cross_parameter_rules.py` | ✅ |
| `src/phase4_validate/absolute_max_rules.py` | ✅ |
| `src/phase4_validate/validator.py` | ✅ |
| `src/phase4_validate/kicad_exporter.py` | ✅ |
| `src/phase4_validate/runner.py` | ✅ |
| `tests/fixtures/phase3_mock_outputs.py` | ✅ |
| `src/pipeline.py` | ⬜ (deferred) |
| `src/review/queue.py`, `src/review/cli.py` | ⬜ (deferred) |

**Schema:** `ValidationError` + extended `ValidationResult` in `schemas/datasheet.py`; optional `kicad_export` on `PipelineOutput`.

**Tests:** 45 passing — `pytest tests/unit/test_phase4_*.py tests/integration/test_phase4_e2e.py -v`

**Measured metrics:** — *deferred* (requires 30-datasheet corpus FPR/FNR harness)

**Blocker for exit gate:** Full pipeline orchestrator; review queue; corpus-scale eval.

---

### Phase 5 — Docker + Delivery

**Target exit criteria:** Air-gapped Docker runs E2E on all 30 datasheets; output contract signed off.

| Deliverable | Status |
|-------------|--------|
| `Dockerfile` | ⬜ |
| `build_airgapped_image.sh` | ⬜ |
| Offline integration test | ⬜ |
| Example output files for KiCad MCP team | ⬜ |

---

## 6. Code inventory

### Implemented (`drdo-p1-parser/src/`)

```
src/
├── config.py
├── logging_config.py
├── phase1_dla/           # DLA — complete, 5/5 golden PASS
├── phase2_tsr/           # TSR — implemented (metrics deferred)
├── phase3_extract/       # Extraction — rule-based (golden eval deferred)
├── phase4_validate/    # Validation + KiCad export (FPR/FNR eval deferred)
├── schemas/
│   ├── __init__.py
│   ├── datasheet.py      # Output contract (Pydantic)
│   └── pipeline.py       # Inter-phase transport models
└── utils/
    └── exceptions.py
```

### Scaffolded (empty — awaiting implementation)

```
src/phase4_validate/
src/review/
src/pipeline.py           # Not yet created
```

### Tests

```
tests/unit/test_schemas.py
tests/unit/test_config.py
tests/unit/test_phase1_*.py
tests/unit/test_phase2_*.py
tests/unit/test_phase3_*.py   # 53 tests
tests/unit/test_phase4_*.py   # 45 tests
tests/integration/test_phase2_e2e.py
tests/integration/test_phase3_e2e.py
tests/integration/test_phase4_e2e.py
tests/fixtures/phase2_mock_outputs.py
tests/fixtures/phase3_mock_outputs.py
```

### Scripts & eval

```
scripts/download_models.py
eval/spike/run_spike.py
eval/spike/SPIKE_RESULTS.md
corpus/golden/validate_ground_truth.py
```

---

## 7. Model & corpus status

### Model weights (`drdo-p1-parser/models/`)

| Model | Path | Status | Size |
|-------|------|--------|------|
| YOLOv8n-DocLayNet | `yolov8_doclaynets.pt` | ✅ Verified | ~6.3 MB |
| Qwen2-VL-7B-Instruct | `Qwen2-VL-7B-Instruct/` | ✅ Verified | ~20.2 GB |
| Qwen2.5-7B-Instruct | `Qwen2.5-7B-Instruct/` | 🟡 Downloading | ~15 GB |

Download: `python scripts/download_models.py --all` · Log: `logs/download.log`

### Golden corpus — 5/5 complete ✅

| # | Component | Ground truth file |
|---|-----------|-------------------|
| 1 | TI_SN74LVC1G04 | `corpus/golden/TI_SN74LVC1G04_v1_ground_truth.json` |
| 2 | TI_TLV7021 | `corpus/golden/TI_TLV7021_v1_ground_truth.json` |
| 3 | TI_INA219 | `corpus/golden/TI_INA219_v1_ground_truth.json` |
| 4 | TI_LM5176 | `corpus/golden/TI_LM5176_v1_ground_truth.json` |
| 5 | TI_TPS62933 | `corpus/golden/TI_TPS62933_v1_ground_truth.json` |

**Archived:** `TI_TMS320F280039C` → `corpus/archive/` (DSP MCU, out of P1 scope). Replaced by TPS62933.

**Manifest:** `corpus/golden/CORPUS_MANIFEST.md`

### Test corpus — 0/25

`corpus/test/` is empty. Curate 25 additional TI datasheets for Phase 4 E2E eval.

---

## 8. Architecture (pipeline)

```
PDF datasheet
    │
    ▼
Phase 1 — DLA (YOLOv8n-DocLayNet)
    │  table crops, footnote_map, section_type labels
    ▼
Phase 2 — TSR (pdfplumber+Camelot ∥ Qwen2-VL → confidence pick)
    │  GridMatrix per table
    ▼
Phase 3 — Extraction (rule-based grid parsers; Qwen2.5 LLM stub optional)
    │  ComponentDatasheet (partial, per section)
    ▼
Phase 4 — Validation (physics rules → pass / warn / block)
    │
    ▼
<component_id>_parsed.json
```

### Locked models (air-gapped)

| Phase | Model | Fallback |
|-------|-------|----------|
| 1 DLA | YOLOv8n-DocLayNet | Surya (if spike recall fails) |
| 2 Path A | pdfplumber + Camelot lattice | — |
| 2 Path B | Qwen2-VL-7B-Instruct | LLaVA-1.6-34B |
| 3 Extract | Qwen2.5-7B-Instruct + Instructor | Llama-3.1-8B |

---

## 9. Blockers & immediate next steps

### Blockers

1. **Grid-level golden GT** — required for Phase 2 `cell_accuracy` / `merged_cell_accuracy` exit gate
2. **GPU lab run** — Phase 2 VLM path needs `vlm_enabled: true` on GPU machine
3. **Qwen2.5-7B** — optional for Phase 3 LLM fallback (`phase3_extract.llm_enabled: true` on GPU lab)

### Immediate next steps (ordered)

1. Run Phase 2 on GPU lab: `python eval/phase2/run_eval.py --corpus corpus/golden --save-outputs`
2. Annotate grid-level golden GT for 5 components
3. Build `eval/phase3/` harness and run golden semantic comparison (`field_f1 ≥ 0.93`)
4. Implement `src/pipeline.py` (Phase 1→2→3→4 orchestrator)
5. Implement `src/review/queue.py` + `src/review/cli.py`

---

## 10. Key paths

```
DRDO/
├── documents/
│   ├── README.md                   ← documents index
│   ├── objectives.md
│   ├── assessments/
│   │   └── p1_assessment_filled.md ← authoritative spec
│   ├── architecture/
│   │   ├── PROJECT_CONTEXT.md      ← this file (attach to Claude Projects)
│   │   └── problem_1_solution.md
│   ├── guides/
│   │   ├── CODING_STANDARDS_P1.md
│   │   └── QUICK_REFERENCE_PATTERNS.md
│   └── phase1/
│       ├── CURSOR_PROMPT_PHASE1.md
│       └── PHASE1_CORPUS_EVAL_TUNING_LOG.md
└── drdo-p1-parser/
    ├── src/
    ├── corpus/golden/              # 5 PDFs + 5 ground_truth JSON
    ├── corpus/test/                # 25 PDFs (TODO)
    ├── corpus/archive/             # TMS320 archived
    ├── models/                     # Offline weights (gitignored)
    ├── configs/default.yaml
    ├── eval/spike/
    └── tests/unit/
```

### Quick commands

```bash
cd drdo-p1-parser && source venv/bin/activate
pytest tests/unit/ -v
python corpus/golden/validate_ground_truth.py
python scripts/download_models.py --all
python eval/spike/run_spike.py
```

---

## 11. Changelog

| Date | Phase | Summary |
|------|-------|---------|
| 2026-06-12 | 0 | Golden corpus 5/5 complete (TPS62933 replaces TMS320). Qwen2-VL verified. Bootstrap + schemas + 26 unit tests done. Spike metrics stale. PROJECT_CONTEXT.md created. |
| 2026-06-12 | 1 | Phase 1 DLA complete. Golden eval 5/5 PASS (100% recall/precision/footnote/section acc on all components). Fixes: merge-before-cap, cover offset detection, classify offset scope correction. |
| 2026-06-12 | 2 | Phase 2 TSR modules implemented (merged_cell_handler, confidence_scorer, path_a_vector, path_b_vlm, runner). 45 unit/integration tests pass. Eval metrics deferred pending grid GT + GPU run. |

---

*When in doubt: implement against `p1_assessment_filled.md`; report status here.*
