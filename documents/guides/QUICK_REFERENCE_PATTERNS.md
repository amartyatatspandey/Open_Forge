# Quick Reference: Good vs Bad Patterns in P1 Parser
**Bookmark this. Reference it while coding.**

---

## 1. NAMING THINGS

| Bad ❌ | Good ✅ | Why |
|--------|---------|-----|
| `def p1(pdf)` | `def extract_tables_from_pdf(pdf_path: str) -> list[bytes]` | Clear what it does + input/output types |
| `x = 3.3` | `supply_voltage = 3.3` | Can't forget what x meant |
| `CONFIDENCE = 0.85` | `confidence = 0.85` or `MIN_CONFIDENCE_THRESHOLD = 0.85` | Constants are ALL_CAPS; variables are lowercase |
| `result = fn(data)` | `normalized_value = normalize_unit(raw_value, raw_unit)` | Function name describes transformation |

---

## 2. TYPE HINTS (Your IDE's Superpowers)

| Bad ❌ | Good ✅ | Benefit |
|--------|---------|---------|
| `def extract(grid):` | `def extract(grid: list[list[str]]) -> list[ElectricalParameter]:` | IDE auto-completes, type checker catches bugs before runtime |
| `confidence = 0.9` | `confidence: float = 0.9` | Type is explicit—no guessing |
| `return (3.3, "V")` | `return tuple[float, str]: (3.3, "V")` | Caller knows exactly what to expect |

---

## 3. DOCSTRINGS (Document Why, Not What)

| Bad ❌ | Good ✅ |
|--------|---------|
| `def normalize(v, u): return v * 1000` | **`def normalize_unit(raw_value: str, raw_unit: str, param_type: str) -> tuple[float, str]:`**<br>**`"""Convert any unit to canonical form.`**<br>**`Example: normalize_unit("3300", "mV", "voltage") → (3.3, "V")`**<br>**`Args:`**<br>**`  raw_value: Numeric string from datasheet.`**<br>**`  param_type: Must be in CANONICAL_UNITS.`**<br>**`Raises: ValueError if unit unrecognized.`**<br>**`"""`** |

---

## 4. CONFIGURATION (One Source of Truth)

| Bad ❌ | Good ✅ |
|--------|---------|
| **Phase 1:** `threshold = 0.7` | **config.py:**<br>`CONFIDENCE_THRESHOLDS = {`<br>`  "block_extraction": 0.70,`<br>`  "warn_downstream": 0.85`<br>`}`<br><br>**Phase 2 uses same:**<br>`from src.config import CONFIDENCE_THRESHOLDS`<br>`if confidence < CONFIDENCE_THRESHOLDS["block"]:`<br>&nbsp;&nbsp;`block_and_review()` |
| **Phase 2:** `threshold = 0.75` (different!) | | Everyone uses the same threshold ✅ |
| **Phase 3:** `threshold = 0.8` (different!) | | |

**Result of bad:** Component passes Phase 1 but blocks at Phase 2. Chaos.

---

## 5. SCHEMAS (All Data Models in One Place)

| Bad ❌ | Good ✅ |
|--------|---------|
| **Phase 1:** `class Value: pass`<br>**Phase 2:** `class Value: pass` (different)<br>**Phase 3:** Uses Phase 1 Value, breaks | **schemas.py:**<br>`class ExtractedValue(BaseModel):`<br>`  raw_text: str`<br>`  value: float`<br>`  confidence: float`<br><br>**Every phase imports:**<br>`from src.schemas import ExtractedValue`<br><br>Change once → everywhere updates |

---

## 6. ERROR HANDLING (Fail Loud, Fail Clear)

| Bad ❌ | Good ✅ |
|--------|---------|
| `try:`<br>`  result = float(row[99])`<br>`except: pass` | `try:`<br>`  if len(row) < 3:`<br>`    raise ValueError(f"Row too short: {len(row)}")`<br>`  result = float(row[2])`<br>`except ValueError as e:`<br>`  logger.error(f"Row {row_num}: {e}")`<br>`  raise` |
| **Result:** Silent failure. PCB wrong. | **Result:** Clear error message. Can debug. |

---

## 7. TESTING (Catch Bugs Early)

| Bad ❌ | Good ✅ |
|--------|---------|
| `# Hope it works` | **tests/unit/test_unit_normalizer.py:**<br>`def test_mv_to_v():`<br>`  value, unit = normalize_unit("3300", "mV", "voltage")`<br>`  assert value == 3.3`<br>`  assert unit == "V"`<br><br>`pytest tests/unit/`  |
| Code ships to DRDO untested | Every change verified before commit ✅ |

---

## 8. LOGGING (Debugging Without the Debugger)

| Bad ❌ | Good ✅ |
|--------|---------|
| `print("done")` | `logger.info(f"Phase 1 complete: {table_count} tables extracted")`<br>`logger.warning(f"Confidence {conf:.2f} < threshold")`<br>`logger.error(f"Table crop failed: {e}")` |
| Printed messages disappear | Messages go to file + console. Air-gapped troubleshooting ✅ |

---

## 9. CONSTANTS vs MAGIC NUMBERS

| Bad ❌ | Good ✅ |
|--------|---------|
| `confidence = grid_score / 0.7` | **config.py:**<br>`MIN_BLOCK_CONFIDENCE = 0.70`<br><br>`confidence = grid_score / MIN_BLOCK_CONFIDENCE`<br><br>**Change once, everywhere updates** |
| `if x > 300:  # why 300?` | `MIN_DPI_FOR_OCR = 300`<br>`if dpi > MIN_DPI_FOR_OCR:` |

---

## 10. PHASE BOUNDARIES (Data Flows Like Electricity)

```
Phase 1 Output
    ↓
Phase1Output(
  tables: list[bytes],        ← bytes only, not file paths
  footnotes: list[FootnoteLink]
)
    ↓
Phase 2 Input
    ↓
Phase2Output(
  grids: list[GridMatrix]      ← structured, ready for Phase 3
)
    ↓
Phase 3 Input ← must match Phase 2 Output schema
```

**Bad:** Phase 2 returns raw dict with `{"grid": ...}`. Phase 3 expects `GridMatrix`. Crash.

**Good:** Define schema once, phase uses it ✅

---

## 11. ORCHESTRATION (The Conductor)

```python
# src/pipeline.py — ONE PLACE where phases talk to each other

def run_full_pipeline(pdf_path: str, config: Config) -> PipelineOutput:
    """Orchestrate all 4 phases. No phase knows about others."""
    
    # Phase 1
    logger.info(f"Phase 1: Extracting layout from {pdf_path}")
    phase1_result = dla.process(pdf_path, config)
    assert isinstance(phase1_result, Phase1Output)
    
    # Phase 2
    logger.info(f"Phase 2: Recognizing table structure")
    phase2_result = tsr.process(phase1_result, config)
    assert isinstance(phase2_result, Phase2Output)
    
    # Phase 3
    logger.info(f"Phase 3: Extracting semantics")
    phase3_result = extract.process(phase2_result, config)
    assert isinstance(phase3_result, ComponentDatasheet)
    
    # Phase 4
    logger.info(f"Phase 4: Validating physics")
    validation = validate.check(phase3_result, config)
    
    return PipelineOutput(datasheet=phase3_result, validation=validation)

# Usage:
result = run_full_pipeline("corpus/golden/TI_OPA2134.pdf", config)
result.to_json_file("output/TI_OPA2134.json")
```

**Each phase is independent. Swap Phase 2 VLM? Just change one file.**

---

## 12. GIT COMMITS (Tell the Story)

| Bad ❌ | Good ✅ |
|--------|---------|
| `git commit -m "fixes"` | `git commit -m "Phase 3: Add unit normalization for mV→V conversion`<br><br>`- Implement normalize_unit() function`<br>`- Add unit_normalizer.py module`<br>`- Add unit tests (test_unit_normalizer.py)`<br>`- Handle OCR error: 'u' parsed as 'µ'`<br>`- Closes issue #42"` |
| Future you: "What changed?" | Future you: Clear history of decisions |

---

## 13. PROJECT STRUCTURE AT A GLANCE

```
src/
├── config.py              ← ALL settings (canonical units, thresholds, model paths)
├── schemas.py             ← ALL data models (ExtractedValue, ElectricalParameter, etc.)
├── pipeline.py            ← Phases 1→2→3→4 orchestrator
├── phase1_dla/            ← Self-contained, imports only config + schemas
├── phase2_tsr/            ← Ditto
├── phase3_extract/        ← Ditto
└── phase4_validate/       ← Ditto

tests/
├── unit/                  ← Fast, isolated tests per module
└── integration/           ← Full pipeline on golden corpus

configs/
└── default.yaml           ← Human-readable config file
```

**Rule:** Each phase is an island. It only knows about config, schemas, and its own code.

---

## 14. BEFORE YOU COMMIT

```bash
# 1. Format code
black src/

# 2. Check style
pylint src/

# 3. Type check
mypy src/

# 4. Run tests
pytest tests/

# 5. Commit
git commit -m "..."
```

**Checklist:**
- [ ] All tests pass
- [ ] No hardcoded values (use config.py)
- [ ] Functions have type hints
- [ ] Functions have docstrings
- [ ] Error handling is specific (not bare `except:`)
- [ ] Logging at INFO and WARNING levels for key steps
- [ ] Schema changes → update schemas.py only

---

## 15. COMMON BEGINNER MISTAKES

| Mistake | Fix | Impact |
|---------|-----|--------|
| Hardcoding thresholds in Phase 2, Phase 3, Phase 4 | Put all in `config.py` | One config change everywhere |
| Defining `ElectricalParameter` in Phase 3 only | Define in `schemas.py` | All phases use same schema |
| `except: pass` swallowing errors silently | Specific exception + logging | Errors are debuggable |
| No docstrings | Add docstring to every function | 3 months later, you know what it does |
| Testing manually with `print()` | Write pytest unit tests | Tests run automatically |
| Model loaded in every function | Load once at startup, reuse | 1000x faster |

---

**Golden Rule:** If you're copy-pasting code, you're doing it wrong. Use a shared function or config.

**Iron Rule:** If you can't explain a line in plain English, rewrite it.

---

*Bookmark this. Print it. Reference it daily until these patterns become automatic.* 🚀
