# CURSOR_PROMPT_PHASE2_TSR.md

## Context

You are implementing **Phase 2: Table Structure Recognition (TSR)** for the DRDO P1 Datasheet Parser. Your goal is to extract table grid structure (cell coordinates, row/column boundaries) from cropped table images.

**Authority documents (read these first):**
- `documents/p1_assessment_filled.md` — full spec
- `documents/PROJECT_CONTEXT.md` — project status
- `documents/CODING_STANDARDS_P1.md` — coding standards
- `documents/QUICK_REFERENCE_PATTERNS.md` — code patterns

**Current status:** Phase 1 complete (5/5 PASS). Phase 2 scaffolding ready.

**Task:** Write Phase 2 code. **Do NOT run Phase 2** (no GPU available). Unit tests pass locally.

---

## Phase 2 Architecture

### Input → Output

```
Phase 1 Output (Phase1Output)
  • detected_tables: list of Table with:
    - image: PNG bytes
    - bbox: (x, y, w, h)
    - section_type: str
    - page_number: int
    - footnote_map: dict
    
         │ (crop image)
         ▼
         
    Dual-path TSR
    ┌────────────────────────────┐
    │ Path A (Deterministic)     │
    │ pdfplumber + Camelot       │
    │ → GridMatrix | None        │
    └──────────┬─────────────────┘
               │
               ├─ Path B (VLM)
               │  Qwen2-VL-7B
               │  → GridMatrix
               │
               ▼
    Confidence Scorer
    (pick A or B)
         │
         ▼
    Merged Cell Handler
    (normalize merged cells)
         │
         ▼
    Phase 2 Output (Phase2Output)
      • grids: list[GridMatrix]
      • metadata: dict
```

### Key Components

1. **GridMatrix** (schema in `src/schemas/pipeline.py`)
   ```python
   class GridMatrix(BaseModel):
       rows: list[list[str]]       # 2D array of cell text
       num_rows: int               # Number of rows
       num_cols: int               # Number of columns
       section_type: str           # electrical_characteristics, pinout, etc.
       confidence: float           # 0.0–1.0 (how confident this is correct)
       source: str                 # "vector_path_A", "vlm_path_B", "mock_for_testing"
   ```

2. **Path A (pdfplumber + Camelot)** — Deterministic
   - Input: PDF bytes + table bbox (from Phase 1)
   - Extract table with pdfplumber.Table → grid
   - Camelot lattice mode for additional structure detection
   - Return GridMatrix if table has clear borders, else None

3. **Path B (Qwen2-VL)** — VLM
   - Input: Cropped table image
   - Prompt: "Extract this table as markdown"
   - Parse markdown into rows
   - Return GridMatrix (may hallucinate on clean tables)

4. **Confidence Scorer** — Heuristics
   - Score both grids (A and B)
   - Heuristics: cell count, consistency, empty cells, border detection
   - Return best grid

5. **Merged Cell Handler** — Normalize
   - Handle colspan/rowspan (indicated as `→→` or `↓↓` in rows)
   - Flatten to consistent column count
   - Return normalized GridMatrix

6. **Runner** — Orchestrator
   - Run Path A + B in parallel (ThreadPoolExecutor)
   - Score + pick winner
   - Normalize merged cells
   - Return Phase2Output

---

## Implementation Order

### 1. `src/phase2_tsr/merged_cell_handler.py`

**Why first:** Pure logic, no ML, TDD-friendly.

**Functions:**
```python
def normalise_merged_cells(
    rows: list[list[str]],
    target_col_count: int | None = None
) -> list[list[str]]:
    """
    Normalize rows to consistent column count.
    
    Input rows may have:
    - Varying lengths (ragged arrays)
    - Merged cell indicators (→→ for colspan, ↓↓ for rowspan)
    - Empty cells
    
    Output: All rows have same length, merged cells expanded,
            consistent filling with empty string "".
    
    Examples:
    
    # Ragged input
    [["A", "B"], ["C"]]
    → [["A", "B"], ["C", ""]]
    
    # Colspan indicator
    [["Name →→→", "Value"], ["Unit", ""]]
    → [["Name", "Name", "Name", "Value"], ["Unit", "", "", ""]]
    
    Args:
        rows: 2D list of cell strings
        target_col_count: If None, infer from longest row
        
    Returns:
        Normalized rows, all same length
    """
```

**Tests:**
```python
def test_normalise_ragged_rows():
    rows = [["A", "B"], ["C"]]
    result = normalise_merged_cells(rows)
    assert all(len(row) == 2 for row in result)
    assert result[1][1] == ""

def test_normalise_colspan():
    rows = [["Name →→→", "Value"]]
    result = normalise_merged_cells(rows, target_col_count=4)
    assert len(result[0]) == 4

def test_normalise_rowspan():
    rows = [["A", "B"], ["↓", "C"]]
    result = normalise_merged_cells(rows, target_col_count=2)
    # ↓ in row 2, col 0 means "use value from row 1, col 0" → "A"
    assert result[1][0] == "A"
```

---

### 2. `src/phase2_tsr/confidence_scorer.py`

**Why second:** Pure logic, heuristics-based scoring.

**Functions:**
```python
def score_grid(grid: GridMatrix) -> float:
    """
    Score a GridMatrix on confidence heuristics.
    
    Heuristics:
    - Consistent column count across all rows (high confidence)
    - No empty rows or columns (high)
    - Source: vector > vlm (vector is deterministic)
    - Cell sparsity: ~20% empty cells is normal, >50% is suspicious
    - Outlier rows (drastically different cell count) reduce score
    
    Args:
        grid: GridMatrix to score
        
    Returns:
        0.0–1.0 confidence score
    """

def pick_best_grid(
    grid_a: GridMatrix | None,
    grid_b: GridMatrix | None
) -> GridMatrix | None:
    """
    Pick the best grid from Path A and Path B.
    
    Logic:
    - If only one is not None, return that one
    - If both, score both and return higher
    - If neither, return None
    
    Args:
        grid_a: From pdfplumber + Camelot (or None if failed)
        grid_b: From Qwen2-VL
        
    Returns:
        Best GridMatrix, or None if both None
    """
```

**Tests:**
```python
def test_score_consistent_grid():
    """Grid with 5 rows × 4 cols, all cells filled."""
    grid = GridMatrix(
        rows=[["A", "B", "C", "D"]] * 5,
        num_rows=5,
        num_cols=4,
        section_type="electrical_characteristics",
        confidence=0.95,
        source="vector_path_A"
    )
    score = score_grid(grid)
    assert score > 0.9

def test_score_sparse_grid():
    """Grid with many empty cells."""
    grid = GridMatrix(
        rows=[["A", "", "", "D"], ["", "B", "", ""], ["C", "", "", "D"]],
        num_rows=3,
        num_cols=4,
        section_type="pinout",
        confidence=0.70,
        source="vlm_path_B"
    )
    score = score_grid(grid)
    assert score < 0.8

def test_pick_best_grid_vector_wins():
    """Vector path with high consistency beats VLM."""
    grid_a = GridMatrix(rows=[["A", "B"]] * 5, num_rows=5, num_cols=2, ...)
    grid_b = GridMatrix(rows=[["A", "B"], ["C", "D", "E"]], num_rows=2, num_cols=3, ...)
    best = pick_best_grid(grid_a, grid_b)
    assert best == grid_a
```

---

### 3. `src/phase2_tsr/path_a_vector.py`

**Why third:** Deterministic, no ML, but requires pdfplumber + Camelot.

**Functions:**
```python
def extract_table_via_vector(
    pdf_path: Path,
    table_bbox: tuple[float, float, float, float],  # (x, y, w, h)
    page_number: int
) -> GridMatrix | None:
    """
    Extract table structure using pdfplumber + Camelot.
    
    Strategy:
    1. Load PDF page via pdfplumber
    2. Extract table from bbox region
    3. Try pdfplumber.Table.extract() → grid
    4. If fails (borderless), return None
    5. Camelot lattice mode for additional structure
    
    Args:
        pdf_path: Path to PDF
        table_bbox: (x, y, width, height) from Phase 1
        page_number: Page index (0-based)
        
    Returns:
        GridMatrix if table extracted successfully, else None
    """
```

**Implementation notes:**
- pdfplumber works best on **bordered tables** with clear cell boundaries
- Borderless tables will fail gracefully → return None
- Camelot can detect table structure even without visible borders (lattice mode)
- Coordinate system: pdfplumber uses (x, y) from top-left, with y increasing downward

**Tests:**
```python
def test_extract_bordered_table():
    """Vector extraction on clean bordered table."""
    # Use a real PDF from corpus/golden (no execution, just structure)
    # Later, when you run on GPU, this will test real extraction
    grid = extract_table_via_vector(
        Path("corpus/golden/TI_SN74LVC1G04_v1.pdf"),
        table_bbox=(50, 100, 400, 200),
        page_number=2
    )
    assert grid is not None
    assert grid.num_rows > 0
    assert grid.num_cols > 0

def test_extract_borderless_returns_none():
    """Vector extraction returns None for borderless table."""
    grid = extract_table_via_vector(
        Path("corpus/golden/TI_TLV7021_v1.pdf"),
        table_bbox=(50, 100, 400, 200),
        page_number=4  # Assume page 4 has borderless table
    )
    # Expected: None (will be handled by Path B)
    assert grid is None
```

---

### 4. `src/phase2_tsr/path_b_vlm.py`

**Why fourth:** Requires Qwen2-VL model (not available on MacBook, but code structure is testable).

**Functions:**
```python
class Qwen2VLExtractor:
    """Stateful extractor using Qwen2-VL-7B-Instruct."""
    
    def __init__(self, model_path: Path | str = "models/Qwen2-VL-7B-Instruct"):
        """Load model once (expensive operation)."""
        
    def extract_table_via_vlm(
        self,
        image_bytes: bytes,
        section_type: str
    ) -> GridMatrix:
        """
        Extract table via VLM.
        
        Strategy:
        1. Load image from bytes
        2. Prompt Qwen2-VL: "Extract this table as markdown. Column headers first."
        3. Parse markdown → rows
        4. Return GridMatrix
        
        Args:
            image_bytes: PNG or JPG bytes of cropped table
            section_type: For context in prompt
            
        Returns:
            GridMatrix from VLM extraction
        """
```

**Prompt for VLM:**
```python
prompt = f"""
You are a table extraction expert. Extract the table from this image as clean Markdown.

Output **ONLY** the Markdown table. No explanations. Example:

| Parameter | Min | Max | Unit |
|-----------|-----|-----|------|
| V_CC      | 1.8 | 5.5 | V    |
| I_CC      | — | 2.0 | mA   |

Table to extract (section: {section_type}):
[Image]
"""
```

**Tests:**
```python
def test_vlm_extractor_loads_model():
    """Model loads without error (no inference on MacBook)."""
    extractor = Qwen2VLExtractor(model_path="models/Qwen2-VL-7B-Instruct")
    assert extractor is not None
    # Actual inference will be skipped in unit tests
    # (model is 20GB, doesn't fit in 18GB RAM)

def test_vlm_extraction_parsing():
    """VLM markdown parsing works correctly."""
    markdown = """
| A | B | C |
|---|---|---|
| 1 | 2 | 3 |
| 4 | 5 | 6 |
"""
    grid = parse_markdown_table(markdown)
    assert grid.num_rows == 3  # Header + 2 data rows
    assert grid.num_cols == 3
    assert grid.rows[0] == ["A", "B", "C"]
```

---

### 5. `src/phase2_tsr/runner.py`

**Orchestrator — runs all four modules.**

**Functions:**
```python
def run_phase2(
    phase1_output: Phase1Output,
    config: Config = None
) -> Phase2Output:
    """
    Full Phase 2 pipeline.
    
    For each detected table from Phase 1:
    1. Run Path A (vector, ~1 sec)
    2. Run Path B (VLM, ~30 sec) in parallel
    3. Score both, pick winner
    4. Normalize merged cells
    5. Add metadata
    
    Args:
        phase1_output: From Phase 1
        config: Config object with phase2_tsr settings
        
    Returns:
        Phase2Output with GridMatrix list
    """
    
    grids = []
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        for table in phase1_output.detected_tables:
            # Path A: submit immediately (fast)
            future_a = executor.submit(
                extract_table_via_vector,
                table.pdf_path,
                table.bbox,
                table.page_number
            )
            
            # Path B: submit immediately (slow but parallel)
            future_b = executor.submit(
                vlm_extractor.extract_table_via_vlm,
                table.image_bytes,
                table.section_type
            )
            
            # Wait for both
            grid_a = future_a.result(timeout=5)
            grid_b = future_b.result(timeout=60)
            
            # Score and pick
            best_grid = pick_best_grid(grid_a, grid_b)
            
            if best_grid is None:
                logger.warning(f"Both paths failed for table on page {table.page_number}")
                continue
            
            # Normalize
            best_grid.rows = normalise_merged_cells(
                best_grid.rows,
                target_col_count=best_grid.num_cols
            )
            
            grids.append(best_grid)
    
    return Phase2Output(
        grids=grids,
        metadata={
            "num_tables_input": len(phase1_output.detected_tables),
            "num_tables_success": len(grids),
            "path_a_success_rate": count_path_a / len(grids),
            "path_b_success_rate": count_path_b / len(grids),
        }
    )
```

**Tests:**
```python
def test_runner_with_mocks():
    """Phase 2 runner using mock Phase 1 output."""
    from tests.fixtures.phase1_mock_outputs import mock_phase1_output_tlv7021
    
    phase1_out = mock_phase1_output_tlv7021()
    phase2_out = run_phase2(phase1_out)
    
    assert phase2_out is not None
    assert len(phase2_out.grids) > 0
    assert all(isinstance(g, GridMatrix) for g in phase2_out.grids)
```

---

## Exit Criteria

- ✅ All 5 modules implemented (`path_a_vector.py`, `path_b_vlm.py`, `confidence_scorer.py`, `merged_cell_handler.py`, `runner.py`)
- ✅ All unit tests pass locally (no execution, just structure validation)
- ✅ Code follows `CODING_STANDARDS_P1.md`
- ✅ No hardcoded paths (use `Config`)
- ✅ Logging on every major step
- ✅ Type hints on all functions
- ✅ Docstrings on all public functions

---

## Do NOT

- ❌ Run Phase 2 (no GPU, model doesn't fit in RAM)
- ❌ Hardcode paths like `corpus/golden/TI_SN74LVC1G04_v1.pdf`
- ❌ Use global state (instantiate Qwen2VLExtractor once in runner)
- ❌ Ignore merged cells (they cause column misalignment in Phase 3)
- ❌ Assume all tables extract successfully (return None gracefully)

---

## Testing Strategy

**Local testing (on MacBook):**
1. Unit tests for `merged_cell_handler.py` — real data, no ML
2. Unit tests for `confidence_scorer.py` — real data, no ML
3. Unit tests for `path_a_vector.py` — **mock imports**, no PDF access
4. Unit tests for `path_b_vlm.py` — **mock VLM**, no model loading
5. Integration test for `runner.py` — **mock Phase 1 output**, no execution

**Mock imports example:**
```python
# In tests, mock the expensive dependencies:
from unittest.mock import MagicMock, patch

@patch("src.phase2_tsr.path_a_vector.pdfplumber.open")
def test_extract_table_via_vector(mock_pdf):
    """Test path A logic without loading real PDFs."""
    mock_pdf.return_value = MagicMock()
    grid = extract_table_via_vector(...)
    assert grid is not None
```

---

## Later: On GPU in Lab

When you run Phase 2 on the GPU system:

```bash
# In your lab on GPU machine
cd drdo-p1-parser && source venv/bin/activate
python eval/phase2/run_eval.py --corpus corpus/golden --save-outputs

# Output: eval/phase2/golden_phase2_outputs.json
# Copy this back to MacBook for Phase 3 development
```

---

## Ready?

- Read the authority docs first
- Implement in order: 1 → 2 → 3 → 4 → 5
- Run tests locally (they pass on MacBook)
- Commit to git
- Move on to Phase 3

**Go!**
