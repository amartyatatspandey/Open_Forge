# MASTER GUIDE: Phases 2, 3, 4 — Code-First, Mock-Driven Development

## The Plan (One Page)

You will **write code for Phase 2, 3, 4** on your MacBook **without running Phase 2**. Later, when you have access to a GPU system in your lab, you'll run Phase 2 once, get the outputs, and wire everything together.

```
NOW (MacBook)                          LATER (Lab GPU)
├─ Phase 2: Write code                 └─ Phase 2: Run once → outputs
├─ Phase 3: Write + test (mock data)       Phase 3: Wire to real data
└─ Phase 4: Write + test (mock data)       Phase 4: Wire to real data
                                           Full pipeline: run tests
```

**Why this works:** Phases 3 and 4 don't care *how* Phase 2 outputs are made. They only care that the data follows the `GridMatrix` schema. Mock data follows that schema perfectly.

---

## Your Files (Everything You Need)

1. **`DEVELOPMENT_WORKFLOW_PHASES_2_3_4.md`** ← READ FIRST
   - Complete step-by-step workflow
   - Why mocks won't break Phase 3 + 4
   - Integration instructions for later

2. **`CURSOR_PROMPT_PHASE2_TSR.md`** ← USE FOR CODING
   - Phase 2 implementation spec
   - 5 modules to write in order
   - Unit test examples
   - Do's and don'ts

3. **`phase2_mock_outputs.py`** ← USE FOR TESTING PHASE 3 + 4
   - Mock Phase2Output for all 5 golden components
   - Realistic data (from real datasheets)
   - Import: `from tests.fixtures.phase2_mock_outputs import all_golden_phase2_outputs`

---

## Your Roadmap

### Week 1: Phase 2 (Code Writing)

**Task:** Write 5 modules. Do NOT run.

**File locations:**
```
src/phase2_tsr/
├── merged_cell_handler.py  ← Write first (no ML, pure logic)
├── confidence_scorer.py    ← Write second (no ML, pure logic)
├── path_a_vector.py        ← Write third (deterministic extraction)
├── path_b_vlm.py           ← Write fourth (VLM, mock imports)
└── runner.py               ← Write fifth (orchestrator)
```

**Process:**
1. Open `CURSOR_PROMPT_PHASE2_TSR.md`
2. Copy entire prompt into Cursor
3. Implement in order: 1 → 2 → 3 → 4 → 5
4. Run unit tests locally (tests don't need GPU or Qwen2-VL)
5. All tests pass ✅
6. Commit to git

**Time:** 4–6 hours

**Output:** `src/phase2_tsr/` complete, unit tests passing

---

### Week 2: Phase 3 (Extract Parameters)

**Task:** Write 4 modules using mock Phase 2 data.

**File locations:**
```
src/phase3_extract/
├── parameter_extractor.py   ← Extract electrical parameters
├── pinout_extractor.py      ← Extract pin definitions
├── footnote_resolver.py     ← Resolve footnote references
├── validation.py            ← Check for errors
└── runner.py                ← Orchestrate all
```

**Input:** `from tests.fixtures.phase2_mock_outputs import all_golden_phase2_outputs()`

**Process:**
1. (Cursor prompt for Phase 3 — to be created, similar structure to Phase 2)
2. Implement 5 modules using mock GridMatrix data
3. Unit tests use mock data, all pass
4. No execution needed
5. Commit to git

**Time:** 5–7 hours

**Output:** `src/phase3_extract/` complete, unit tests passing

---

### Week 3: Phase 4 (Validation + KiCad)

**Task:** Write 2 modules using mock Phase 3 data.

**File locations:**
```
src/phase4_validate/
├── validator.py      ← Cross-field validation
├── kicad_generator.py ← Export to KiCad JSON
└── runner.py         ← Orchestrate
```

**Input:** `ComponentDatasheet` from Phase 3 (mocked)

**Process:**
1. (Cursor prompt for Phase 4 — to be created)
2. Implement 3 modules
3. Unit tests use mock data, all pass
4. Commit to git

**Time:** 3–4 hours

**Output:** `src/phase4_validate/` complete, unit tests passing

---

### Week 4+: Lab System (GPU)

**In your lab, on the GPU machine:**

```bash
cd drdo-p1-parser && source venv/bin/activate

# Run Phase 2 once
python eval/phase2/run_eval.py --corpus corpus/golden --save-outputs

# Copy outputs back to MacBook
scp eval/phase2/golden_phase2_outputs.json user@macbook:drdo-p1-parser/eval/phase2/
```

**Back on MacBook:**

```bash
# Update tests to use real Phase 2 outputs (1 line change per test)
# Run full integration test
python eval/phase4/run_eval.py --corpus corpus/golden --full-pipeline

# Success!
```

---

## Key Files to Know

### Authority Documents (Read These)
- `documents/p1_assessment_filled.md` — full spec
- `documents/PROJECT_CONTEXT.md` — project status + phase summary
- `documents/CODING_STANDARDS_P1.md` — code standards
- `documents/QUICK_REFERENCE_PATTERNS.md` — code patterns

### Phase 1 (Already Complete ✅)
- `src/phase1_dla/` — all modules done
- `eval/phase1/run_eval.py` — evaluation script
- `eval/phase1/PHASE1_RESULTS.md` — 5/5 PASS

### Phase 2, 3, 4 (You Will Write)
- `src/phase2_tsr/` ← Write these modules
- `src/phase3_extract/` ← Write these modules
- `src/phase4_validate/` ← Write these modules
- `tests/unit/test_phase2_*.py` ← Write unit tests
- `tests/unit/test_phase3_*.py` ← Write unit tests
- `tests/unit/test_phase4_*.py` ← Write unit tests

### Mock Data (Provided)
- `tests/fixtures/phase2_mock_outputs.py` ← Use for Phase 3 + 4 testing
  ```python
  from tests.fixtures.phase2_mock_outputs import all_golden_phase2_outputs
  phase2_outputs = all_golden_phase2_outputs()  # Dict of 5 components
  ```

---

## Testing Locally (MacBook)

**Phase 2 unit tests:**
```bash
cd drdo-p1-parser && source venv/bin/activate
pytest tests/unit/test_phase2_*.py -v
```

**Phase 3 unit tests (with mocks):**
```bash
pytest tests/unit/test_phase3_*.py -v
```

**Phase 4 unit tests (with mocks):**
```bash
pytest tests/unit/test_phase4_*.py -v
```

**All at once:**
```bash
pytest tests/unit/ -v
```

---

## Integration: Switching from Mock to Real Data (Later)

When you have real Phase 2 outputs from the lab:

**1. Copy outputs:**
```bash
scp user@lab:drdo-p1-parser/eval/phase2/golden_phase2_outputs.json ./eval/phase2/
```

**2. Update test imports (one line per test file):**

**Before (mock data):**
```python
from tests.fixtures.phase2_mock_outputs import all_golden_phase2_outputs
phase2_outputs = all_golden_phase2_outputs()
```

**After (real data):**
```python
import json
with open("eval/phase2/golden_phase2_outputs.json") as f:
    phase2_outputs = json.load(f)
```

**3. Re-run tests:**
```bash
pytest tests/unit/test_phase3_*.py -v
pytest tests/unit/test_phase4_*.py -v
```

**No code changes.** Data source swapped, everything works.

---

## Debugging Notes

### If Phase 3 Extraction Fails Locally
- Check that mock Phase 2 outputs are valid (run `phase2_mock_outputs.py` directly)
- Verify `GridMatrix` schema matches `src/schemas/pipeline.py`
- Errors are usually data shape issues (ragged rows, missing columns)

### If Phase 4 Validation Fails Locally
- Check that Phase 3 outputs are valid `ComponentDatasheet` objects
- Verify all required fields are populated
- Add print statements to debug extraction

### When Real Phase 2 Runs Later
- Real data may differ from mocks (different table shapes, OCR quirks)
- Phase 3 + 4 code will work unchanged
- Extraction accuracy will improve (real data is more varied)
- If Phase 3 fails on real data, debug that phase specifically

---

## Quick Checklist

**Before you start:**
- [ ] Read `DEVELOPMENT_WORKFLOW_PHASES_2_3_4.md`
- [ ] Understand why mocks won't break Phase 3 + 4
- [ ] Confirm `phase2_mock_outputs.py` is in `tests/fixtures/`

**Phase 2 (Week 1):**
- [ ] Copy `CURSOR_PROMPT_PHASE2_TSR.md` to Cursor
- [ ] Implement 5 modules in order
- [ ] Write unit tests (no execution)
- [ ] `pytest tests/unit/test_phase2_*.py` passes
- [ ] Commit to git

**Phase 3 (Week 2):**
- [ ] Use `all_golden_phase2_outputs()` for testing
- [ ] Implement 5 modules (parameter_extractor, pinout_extractor, footnote_resolver, validation, runner)
- [ ] Write unit tests
- [ ] `pytest tests/unit/test_phase3_*.py` passes
- [ ] Commit to git

**Phase 4 (Week 3):**
- [ ] Use mock Phase 3 outputs for testing
- [ ] Implement 3 modules (validator, kicad_generator, runner)
- [ ] Write unit tests
- [ ] `pytest tests/unit/test_phase4_*.py` passes
- [ ] Commit to git

**Lab (Later):**
- [ ] Run Phase 2 on GPU (~30 min)
- [ ] Copy outputs to MacBook
- [ ] Swap data source in tests (1 line per file)
- [ ] Run full integration tests
- [ ] Done ✅

---

## Questions?

**Q: Will the code change when I switch from mock to real Phase 2 data?**

A: No. Only the test data source changes. One-line swap in import statements.

**Q: Why not just run Phase 2 on a cloud GPU now?**

A: You *could*, but then you're waiting 30 minutes for Phase 2 outputs before starting Phase 3. This way, you write in parallel. Phase 3 + 4 are ready to go the moment Phase 2 outputs arrive.

**Q: What if real Phase 2 outputs are different from mocks?**

A: Phase 3 + 4 code handles both. Mocks are *representative* (from real datasheets), not *identical*. Small differences in table shapes won't break the code.

**Q: Do I need to run pytest locally?**

A: Yes, to verify code structure and logic. Pytest will fail on *import* errors or *logic* errors, which you should catch early. You won't run full end-to-end (that needs GPU for Phase 2).

---

## Files Summary

| File | Purpose | Status |
|------|---------|--------|
| `DEVELOPMENT_WORKFLOW_PHASES_2_3_4.md` | Workflow guide | ✅ Ready |
| `CURSOR_PROMPT_PHASE2_TSR.md` | Phase 2 spec | ✅ Ready |
| `phase2_mock_outputs.py` | Mock data | ✅ Ready |
| `CURSOR_PROMPT_PHASE3_*.md` | Phase 3 spec | ⬜ To create |
| `CURSOR_PROMPT_PHASE4_*.md` | Phase 4 spec | ⬜ To create |
| `src/phase2_tsr/*.py` | Phase 2 code | ⬜ You write |
| `src/phase3_extract/*.py` | Phase 3 code | ⬜ You write |
| `src/phase4_validate/*.py` | Phase 4 code | ⬜ You write |

---

## GO!

1. Read `DEVELOPMENT_WORKFLOW_PHASES_2_3_4.md`
2. Copy `CURSOR_PROMPT_PHASE2_TSR.md` to Cursor and start coding Phase 2
3. Week 2: Code Phase 3 (use mocks)
4. Week 3: Code Phase 4 (use mocks)
5. Later: Run Phase 2 on GPU, wire it all together, run full pipeline

**You're unblocked. Go build.** 🚀
