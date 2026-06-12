# 🎯 Cursor Prompt: Phase 1 DLA Implementation
**For:** P1 Datasheet Parser  
**Status:** Phase 0 ✅ → Phase 1 ⬜  
**Date:** 2026-06-12  
**Author:** Claude (design) → Cursor (implementation)

---

## 📌 QUICK SUMMARY (Read This First!)

You're implementing **Phase 1: Document Layout Analysis (DLA)**.

**Simple analogy:**
- **Input:** A PDF of an electronic component datasheet (messy, with tables, images, text mixed)
- **Job:** Find all the tables, label them (electrical specs? pins? power limits?), extract footnotes
- **Output:** Organized JSON with table crops, footnote links, section labels
- **Success:** 92%+ accuracy on 5 golden test datasheets

---

## 🏗️ What You're Building

### Module Structure (all in `src/phase1_dla/`)

```
src/phase1_dla/
├── __init__.py
├── rasterize.py          ← Convert PDF pages to PNG images (300 DPI)
├── detect.py             ← YOLOv8 finds tables & footnotes in images
├── classify_section.py    ← Label: "electrical characteristics" or "pinout" etc.
├── footnote_linker.py    ← Match superscript (1) in cells to footnote text below
└── multipage_merge.py    ← Stitch tables that span 2+ pages
```

### High-Level Flow

```
PDF file
  ↓
[rasterize.py] → convert each page to PNG at 300 DPI
  ↓ PNG images
[detect.py] → find table + footnote regions with YOLOv8
  ↓ (table_crops, footnote_crops)
[classify_section.py] → label each table (electrical_characteristics / pinout / abs_max / other)
  ↓ (with section_type label)
[footnote_linker.py] → find "(1)" superscripts in cells, match to footnote text
  ↓ (footnote_map: {"(1)": "Guaranteed by design..."})
[multipage_merge.py] → if table continues on next page, stitch it together
  ↓
Phase1Output JSON
  {
    "pdf_path": "path/to/datasheet.pdf",
    "tables": [PNG bytes...],
    "footnotes": [{"marker": "(1)", "text": "...", "page": 3}...],
    "section_types": ["electrical_characteristics", "pinout", ...]
  }
```

---

## 📚 Authority & Reference

**Start here for requirements:**
- **`documents/assessments/p1_assessment_filled.md` §3, Phase 1 checklist** — exact module specs
- **`documents/architecture/problem_1_solution.md` Phase 1** — architecture + reasoning

**Code style & patterns:**
- **`documents/guides/CODING_STANDARDS_P1.md` §1–4** — project structure, naming, docstrings
- **`documents/guides/QUICK_REFERENCE_PATTERNS.md`** — good/bad code examples (bookmark this!)
- **`documents/guides/PROJECT_BOOTSTRAP_GUIDE.md` §3–4** — config & schema patterns

**Existing code to reference:**
- **`src/config.py`** — how to load settings (already done, reuse!)
- **`src/schemas/datasheet.py`** — output data structures (already defined)
- **`src/logging_config.py`** — logging setup (already done, import & use)

---

## 🎯 PHASE 1 IMPLEMENTATION CHECKLIST

### Module 1: `rasterize.py`

**Purpose:** Convert PDF pages to PNG images so ML models can see them.

**Input:** Path to PDF file  
**Output:** List of PNG bytes (one per page), 300 DPI

**Pseudocode:**
```python
def rasterize_pdf(pdf_path: str) -> list[bytes]:
    """
    Convert PDF to images.
    
    Args:
        pdf_path: path to .pdf file
        
    Returns:
        List of PNG bytes, one per page
        
    Raises:
        FileNotFoundError: if PDF doesn't exist
        ValueError: if Poppler not installed
    """
    # 1. Load config (see config.py — already done)
    # 2. Use pdf2image.convert_from_path(pdf_path, dpi=300)
    # 3. Convert PIL images to PNG bytes
    # 4. Log progress: logger.info(f"Rasterized {num_pages} pages")
    # 5. Return list[bytes]
```

**Key decisions:**
- Use `pdf2image` (already in `pyproject.toml`)
- DPI = 300 (from config: `config.pipeline.pdf_dpi`)
- Return **bytes**, not file paths (keeps data in memory for Phase 2)

**Test:**
- Load 1 golden PDF, rasterize, verify 5–10 PNG bytes
- Write unit test: `tests/unit/test_phase1_rasterizer.py`

---

### Module 2: `detect.py`

**Purpose:** Find tables and footnotes in the rasterized images using YOLOv8.

**Input:** PNG bytes + model path  
**Output:** Bounding boxes + labels for each detected region

**Pseudocode:**
```python
def detect_tables_and_footnotes(image_bytes: bytes, model_path: str) -> dict:
    """
    Use YOLOv8 to find tables and footnotes.
    
    Args:
        image_bytes: PNG image from rasterize.py
        model_path: path to yolov8_doclaynets.pt
        
    Returns:
        {
            "tables": [{"bbox": (x1,y1,x2,y2), "confidence": 0.92}, ...],
            "footnotes": [{"bbox": (...), "confidence": 0.88}, ...],
        }
        
    Notes:
        - Load model ONCE at startup (see §8, CODING_STANDARDS)
        - YOLOv8 output format: list of detections with class labels
        - Filter by label: keep "table" + "footnote" classes only
    """
```

**Key decisions:**
- Load YOLOv8 model **once at class init**, reuse for all images (performance!)
- Filter detections by class: only "Table" (label 0) and "Footnote" (label ?—check DocLayNet)
- Return bounding boxes in (x1, y1, x2, y2) format

**Test:**
- Load 1 golden PDF, rasterize, run YOLOv8 detect
- Verify: find ≥1 table, ≥1 footnote
- Unit test: `tests/unit/test_phase1_detect.py`

---

### Module 3: `classify_section.py`

**Purpose:** Label each detected table as "electrical_characteristics" vs "pinout" vs "abs_maximum_ratings" vs "timing" vs "other".

**Input:** Table crop (PNG bytes) + heading text from PDF (if available)  
**Output:** Section type label (string)

**Pseudocode:**
```python
def classify_section_type(
    table_crop_bytes: bytes,
    heading_text: Optional[str],
    page_number: int,
    position_on_page: str  # "top" / "middle" / "bottom"
) -> Literal["electrical_characteristics", "pinout", "abs_maximum_ratings", "timing", "other"]:
    """
    Classify which type of table this is.
    
    Heuristic (order matters):
    1. If heading contains "electrical characteristics" → return that
    2. If heading contains "pinout" or "pin definition" → return "pinout"
    3. If heading contains "absolute maximum" → return "abs_maximum_ratings"
    4. If heading contains "timing" → return "timing"
    5. Otherwise → "other"
    
    Falls back to position heuristic if heading_text is None.
    """
```

**Key decisions:**
- Use **heading text extraction** (from PDF or OCR) as primary signal
- Fallback: position heuristic (abs-max usually page 2–3, electrical chars later)
- Keyword matching: regex search in heading
- Don't overthink it—"other" is fine if unsure

**Test:**
- Golden PDF TI_TLV7021: should classify each table correctly
- Unit test: `tests/unit/test_phase1_classify.py`

---

### Module 4: `footnote_linker.py`

**Purpose:** Find superscript markers like "(1)" or "*" in table cells, link them to footnote text below.

**Input:** Grid of cell text + footnote crops (PNG)  
**Output:** Footnote map: `{marker: text, marker: text, ...}`

**Pseudocode:**
```python
def link_footnotes(
    table_cells: list[list[str]],          # 2D grid of cell text
    footnote_crop_images: list[bytes],     # PNG crops of footnote regions
    footnote_crops_bbox: list[tuple]       # Bounding boxes of footnotes
) -> dict[str, str]:
    """
    Extract footnote text from images and link superscripts to them.
    
    Steps:
    1. OCR footnote_crop_images → extract text like "1. Guaranteed by design."
    2. Use regex to extract marker: (1) → "1", * → "*"
    3. Scan table_cells for same markers
    4. Return {"1": "Guaranteed by design.", "*": "Test condition..."}
    
    Returns:
        {marker: footnote_text}
    """
```

**Key decisions:**
- Use **Tesseract OCR or Paddle OCR** for footnote images (local, no cloud)
- Regex to extract marker: `r"^[\(\*\†]+(.+?[\)\.\:])"` (parentheses or asterisk)
- Store as dict for O(1) lookup in Phase 3

**Test:**
- TI_LM5176: has complex footnotes on page 4; verify all linked
- Unit test: `tests/unit/test_phase1_footnote_linker.py`

---

### Module 5: `multipage_merge.py`

**Purpose:** Detect when a table spans 2+ pages (common in big TI datasheets) and stitch them.

**Input:** Multiple GridMatrix objects + their page numbers  
**Output:** Single merged GridMatrix

**Pseudocode:**
```python
def merge_multipage_tables(
    grids: list[GridMatrix],      # All grids from Phase 2
    page_numbers: list[int]        # Which page each grid came from
) -> list[GridMatrix]:
    """
    Detect and merge tables that span multiple pages.
    
    Detection heuristic:
      - Last row of grid N has no bottom border
      - First row of grid N+1 is empty or header-like
      - Column count matches
      → These are the same table
      
    Merge strategy:
      - Drop header row from grid N+1
      - Concatenate row lists
      - Update page_range to span both pages
    """
```

**Key decisions:**
- Check: last_row(grid_N) + first_row(grid_N+1) column count match
- Drop header row from N+1 to avoid duplicates
- Mark merged grids with `page_range=(start, end)`

**Test:**
- TI_TMS320 (archived) or large MCU: spans many pages
- Use test corpus when ready

---

## ⚙️ Key Implementation Details

### Config Usage (Already Done — Just Import!)

```python
from src.config import get_config

config = get_config()
dpi = config.pipeline.pdf_dpi              # 300
dla_model_path = config.models.dla_model_path  # "models/yolov8_doclaynets.pt"
```

### Logging (Already Set Up — Just Use!)

```python
import logging
logger = logging.getLogger(__name__)

logger.info(f"Processing {pdf_path}...")
logger.warning(f"Low confidence detection: {confidence:.2f}")
logger.error(f"Failed to rasterize: {e}")
```

### Schema Output (Already Defined!)

```python
from src.schemas.datasheet import FootnoteLink, Phase1Output

footnote = FootnoteLink(marker="(1)", text="...", page_number=3)
output = Phase1Output(
    pdf_path=pdf_path,
    tables=[png_bytes1, png_bytes2, ...],
    footnotes=[footnote, ...],
    section_types=["electrical_characteristics", "pinout", ...]
)
```

### Error Handling Pattern

```python
from src.exceptions import Phase1LayoutError
import logging

logger = logging.getLogger(__name__)

try:
    result = rasterize_pdf(pdf_path)
    if len(result) == 0:
        raise Phase1LayoutError(f"Rasterization produced 0 pages for {pdf_path}")
    return result
except FileNotFoundError as e:
    logger.error(f"PDF not found: {pdf_path}")
    raise Phase1LayoutError(f"Cannot read {pdf_path}") from e
except Exception as e:
    logger.error(f"Unexpected rasterization error: {e}")
    raise Phase1LayoutError(f"Rasterization failed: {e}") from e
```

---

## 🧪 Testing Strategy (TDD: Test First!)

### 1. Unit Tests (per module)

```python
# tests/unit/test_phase1_rasterizer.py
import pytest
from src.phase1_dla.rasterize import rasterize_pdf

def test_rasterize_golden_corpus():
    """Rasterize one golden PDF, verify output."""
    result = rasterize_pdf("corpus/golden/TI_TLV7021.pdf")
    assert len(result) > 0
    assert all(isinstance(b, bytes) for b in result)
    # Verify PNG magic bytes
    for png_bytes in result:
        assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'

def test_rasterize_nonexistent_raises():
    """Nonexistent PDF should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        rasterize_pdf("corpus/nonexistent.pdf")
```

### 2. Integration Test (all Phase 1 modules together)

```python
# tests/integration/test_phase1_e2e.py
def test_phase1_end_to_end_golden():
    """Run all Phase 1 on one golden PDF, verify output structure."""
    from src.phase1_dla import (rasterize, detect, classify_section, 
                                 footnote_linker, multipage_merge)
    from src.schemas.datasheet import Phase1Output
    
    # Step 1: Rasterize
    pngs = rasterize.rasterize_pdf("corpus/golden/TI_TLV7021.pdf")
    assert len(pngs) >= 5
    
    # Step 2: Detect
    detections = detect.detect_tables_and_footnotes(pngs[0])
    assert len(detections["tables"]) >= 1
    
    # Step 3: Classify
    section = classify_section.classify_section_type(...)
    assert section in ["electrical_characteristics", "pinout", "abs_maximum_ratings", "timing", "other"]
    
    # ... etc for all modules
    
    # Final: Verify Phase1Output schema is valid
    output = Phase1Output(pdf_path="...", tables=..., footnotes=...)
    assert output.component_id is not None
```

### 3. Run Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# All tests
pytest tests/ --cov=src/phase1_dla --cov-report=html
```

---

## 📊 Exit Metrics (How to Know You're Done)

On the **5 golden datasheets**, measure:

```python
# pseudo-code for eval script
from corpus.golden import GOLDEN_CORPUS
from src.phase1_dla import run_phase1
from eval.metrics import table_detection_metrics

golden_results = {
    "TI_SN74LVC1G04": run_phase1("corpus/golden/TI_SN74LVC1G04.pdf"),
    "TI_TLV7021": run_phase1("corpus/golden/TI_TLV7021.pdf"),
    # ... all 5
}

for component_id, result in golden_results.items():
    ground_truth = load_ground_truth(f"corpus/golden/{component_id}_v1_ground_truth.json")
    metrics = table_detection_metrics(result, ground_truth)
    
    print(f"{component_id}:")
    print(f"  Table recall:     {metrics['table_recall']:.2%}  (target: ≥92%)")
    print(f"  Table precision:  {metrics['table_precision']:.2%} (target: ≥90%)")
    print(f"  Footnote recall:  {metrics['footnote_recall']:.2%} (target: ≥85%)")
```

**Success = all metrics meet targets** on all 5 golden PDFs.

---

## 🚀 STARTUP CHECKLIST

Before you write code:

- [ ] Read `documents/assessments/p1_assessment_filled.md` §3 (Phase 1 section)
- [ ] Read `documents/guides/CODING_STANDARDS_P1.md` §1–5 (structure + naming)
- [ ] Review `documents/guides/QUICK_REFERENCE_PATTERNS.md` (bookmark it!)
- [ ] Confirm golden corpus files exist: `corpus/golden/*.pdf` + `*_ground_truth.json`
- [ ] Verify models downloaded: `python scripts/download_models.py --all` (or check `models/`)
- [ ] Test existing code: `pytest tests/unit/ -v` (should pass 26 tests)
- [ ] Create `src/phase1_dla/__init__.py` (empty, just package marker)

---

## 📞 Questions? Rules of Thumb

| Question | Answer |
|----------|--------|
| Where do I get setting values? | `from src.config import get_config; config = get_config()` |
| How do I log? | `import logging; logger = logging.getLogger(__name__); logger.info(...)` |
| What's the output schema? | `src/schemas/datasheet.py` — use `Phase1Output` class |
| My code breaks on edge case X | Add `logger.error()` with context, raise specific exception |
| Should I handle all errors? | Yes. Be specific: `except FileNotFoundError:` not bare `except:` |
| Should I hardcode thresholds? | NO. Put in `configs/default.yaml` or `src/config.py` |
| What test framework? | `pytest` (already in pyproject.toml) |
| Need to validate output? | Pydantic schema auto-validates; catch `ValidationError` |

---

## 📝 Code Template to Start

```python
# src/phase1_dla/rasterize.py
"""Phase 1: Rasterize PDF pages to PNG images.

This module converts PDF files to high-resolution PNG images using pdf2image.
All pages are rasterized at 300 DPI for compatibility with YOLOv8 detection.
"""

from pathlib import Path
from typing import Optional
import logging
from pdf2image import convert_from_path
from PIL import Image
import io

from src.config import get_config
from src.exceptions import Phase1LayoutError

logger = logging.getLogger(__name__)


def rasterize_pdf(pdf_path: str) -> list[bytes]:
    """Convert PDF pages to PNG bytes at 300 DPI.
    
    Args:
        pdf_path: Path to input PDF file.
        
    Returns:
        List of PNG bytes, one per page.
        
    Raises:
        FileNotFoundError: If PDF file doesn't exist.
        Phase1LayoutError: If rasterization fails.
        
    Example:
        >>> pngs = rasterize_pdf("datasheet.pdf")
        >>> len(pngs)  # Number of pages
        8
        >>> pngs[0][:8]  # PNG magic bytes
        b'\\x89PNG\\r\\n\\x1a\\n'
    """
    config = get_config()
    pdf_file = Path(pdf_path)
    
    # Validate input
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    try:
        logger.info(f"Rasterizing {pdf_file.name} at {config.pipeline.pdf_dpi} DPI")
        
        # Convert PDF to images
        images = convert_from_path(
            str(pdf_file),
            dpi=config.pipeline.pdf_dpi,
            fmt=config.pipeline.pdf_fmt  # "png"
        )
        
        # Convert PIL images to PNG bytes
        png_bytes = []
        for i, img in enumerate(images):
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            png_bytes.append(buffer.getvalue())
            logger.debug(f"  Page {i+1}: {len(buffer.getvalue())} bytes")
        
        logger.info(f"✓ Rasterized {len(png_bytes)} pages")
        return png_bytes
        
    except Phase1LayoutError:
        raise  # Re-raise our own errors
    except Exception as e:
        logger.error(f"Rasterization failed: {e}")
        raise Phase1LayoutError(f"Cannot rasterize {pdf_path}: {e}") from e
```

---

## 🎯 Next Steps (in order)

1. **Create module files** → `src/phase1_dla/rasterize.py`, `detect.py`, etc.
2. **Implement `rasterize.py`** → test on one golden PDF
3. **Implement `detect.py`** → test YOLOv8 detections
4. **Implement remaining modules** → classify, link footnotes, merge pages
5. **Write integration test** → run all 5 modules on golden corpus
6. **Measure metrics** → table recall, precision, footnote recall
7. **Update `PROJECT_CONTEXT.md`** → record metrics, mark Phase 1 complete

---

**You've got this! Start with `rasterize.py` — it's the simplest.** 🚀
