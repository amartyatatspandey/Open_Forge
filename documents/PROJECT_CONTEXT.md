# DRDO P1 — Project Context (Living Document)

> **Purpose:** Single attachable context file for Claude Projects, Cursor, and handoffs.
> **Update rule:** Edit this file at the end of every phase completion (see §2).
> **Do not duplicate** the full assessment spec here — link to it.

---

## 1. Snapshot

| Field | Value |
|-------|-------|
| **Last updated** | 2026-06-12 |
| **Updated by** | All model weights verified |
| **Current phase** | Phase 0 — substantially complete; **Phase 1 DLA is next** |
| **Active work** | Model spike re-run; Phase 1 implementation |
| **Repo root** | `DRDO/` |
| **Code root** | `drdo-p1-parser/` |

### Phase dashboard

| Phase | Name | Status | Exit criteria met? |
|-------|------|--------|-------------------|
| **0** | Spike & Tooling | 🟡 Substantially complete | Partial — see §5 |
| **1** | DLA Implementation | ⬜ Not started | — |
| **2** | TSR Implementation | ⬜ Not started | — |
| **3** | Extraction | ⬜ Not started | — |
| **4** | Validation + Integration | ⬜ Not started | — |
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
| 1 | `documents/p1_assessment_filled.md` | **Authoritative** — schema, models, metrics, phased plan, output contract |
| 2 | `documents/PROJECT_CONTEXT.md` | **This file** — current status only |
| 3 | `documents/CODING_STANDARDS_P1.md` | Code style, TDD, config patterns |
| 4 | `documents/QUICK_REFERENCE_PATTERNS.md` | Good/bad patterns cheat sheet |
| 5 | `documents/problem_1_solution.md` | 4-phase architecture narrative |
| 6 | `documents/PROJECT_BOOTSTRAP_GUIDE.md` | Scaffolding templates |
| 7 | `documents/objectives.md` | Six formal DRDO problem statements |

**Superseded:** `documents/p1_assessment.md` — use `_filled` instead.

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
| Qwen2.5-7B download | ✅ | 15.24 GB verified (2026-06-12) |
| Test corpus (25 PDFs) | ⬜ | `corpus/test/` empty |

**Phase 0 metrics (spike — stale):**

| Metric | YOLOv8 | Surya | Target |
|--------|--------|-------|--------|
| Table detection recall | 0.000 | N/A | ≥ 0.92 |
| Footnote detection recall | 0.000 | N/A | ≥ 0.85 |

**Locked model choice (pre-spike):** YOLOv8n-DocLayNet. Re-run spike at `eval/spike/run_spike.py` → `eval/spike/SPIKE_RESULTS.md`.

---

### Phase 1 — DLA Implementation *(next)*

**Target exit criteria:** Table recall ≥ 0.92, precision ≥ 0.90, footnote recall ≥ 0.85 on golden set.

| Module | Status |
|--------|--------|
| `src/phase1_dla/rasterize.py` | ⬜ |
| `src/phase1_dla/detect.py` | ⬜ |
| `src/phase1_dla/classify_section.py` | ⬜ |
| `src/phase1_dla/footnote_linker.py` | ⬜ |
| `src/phase1_dla/multipage_merge.py` | ⬜ |

**Measured metrics:** — *(not run)*

---

### Phase 2 — TSR Implementation

**Target exit criteria:** Cell accuracy ≥ 0.95, merged-cell accuracy ≥ 0.90 on golden set.

| Module | Status |
|--------|--------|
| `src/phase2_tsr/path_a_vector.py` | ⬜ |
| `src/phase2_tsr/path_b_vlm.py` | ⬜ |
| `src/phase2_tsr/confidence_scorer.py` | ⬜ |
| `src/phase2_tsr/merged_cell_handler.py` | ⬜ |

**Measured metrics:** — *(not run)*

---

### Phase 3 — Extraction

**Target exit criteria:** Field F1 ≥ 0.93, unit normalization accuracy = 1.0 on golden set.

| Module | Status |
|--------|--------|
| `src/phase3_extract/unit_normalizer.py` | ⬜ |
| `src/phase3_extract/prompt_templates.py` | ⬜ |
| `src/phase3_extract/extractor.py` | ⬜ |
| Wire `footnote_map` from Phase 1 | ⬜ |

**Measured metrics:** — *(not run)*

---

### Phase 4 — Validation + Integration

**Target exit criteria:** FPR ≤ 0.02, FNR ≤ 0.01; end-to-end on 30-datasheet corpus.

| Module | Status |
|--------|--------|
| `src/phase4_validate/ordering_rules.py` | ⬜ |
| `src/phase4_validate/cross_param_rules.py` | ⬜ |
| `src/phase4_validate/sanity_ranges.py` | ⬜ |
| `src/phase4_validate/abs_max_rules.py` | ⬜ |
| `src/phase4_validate/router.py` | ⬜ |
| `src/pipeline.py` | ⬜ |
| `src/review/queue.py`, `src/review/cli.py` | ⬜ |

**Measured metrics:** — *(not run)*

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
├── schemas/
│   ├── __init__.py
│   ├── datasheet.py      # Output contract (Pydantic)
│   └── pipeline.py       # Inter-phase transport models
└── utils/
    └── exceptions.py
```

### Scaffolded (empty — awaiting implementation)

```
src/phase1_dla/
src/phase2_tsr/
src/phase3_extract/
src/phase4_validate/
src/review/
src/pipeline.py           # Not yet created
```

### Tests

```
tests/unit/test_schemas.py   # 26 tests
tests/unit/test_config.py
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
| Qwen2.5-7B-Instruct | `Qwen2.5-7B-Instruct/` | ✅ Verified | ~15.2 GB |

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
Phase 3 — Extraction (Qwen2.5 + Instructor → Pydantic)
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

1. **Model spike re-run** — YOLO weights now present; metrics still 0.000 in `SPIKE_RESULTS.md`

### Immediate next steps (ordered)

1. Re-run `python eval/spike/run_spike.py` → update `SPIKE_RESULTS.md`
2. Implement Phase 1 modules in `src/phase1_dla/`
3. Add Phase 1 eval against golden corpus (table + footnote recall)

---

## 10. Key paths

```
DRDO/
├── documents/
│   ├── PROJECT_CONTEXT.md          ← this file (attach to Claude Projects)
│   ├── p1_assessment_filled.md     ← authoritative spec
│   ├── problem_1_solution.md
│   ├── CODING_STANDARDS_P1.md
│   └── objectives.md
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
| 2026-06-12 | 0 | All model weights verified: YOLO (~6 MB), Qwen2-VL (~20 GB), Qwen2.5 (~15 GB). `download_models.py --all` exit 0. |

---

*When in doubt: implement against `p1_assessment_filled.md`; report status here.*
