TASK
====
Implement PaddleOCRImageTableBackend — a concrete ImageTableBackend
that uses PaddleOCR PPStructure for table extraction from cropped images.

This is a net-new implementation. No existing code to wrap.

CONTEXT FILES TO READ
=====================
src/parsing/backends/_interfaces.py       ← ImageTableBackend to implement
src/parsing/backends/_schemas.py          ← GridMatrix, GridCell types
src/parsing/backends/_registry.py         ← where to register
configs/default.yaml                      ← config structure

FILES TO CREATE
===============
src/parsing/backends/image_table/__init__.py
src/parsing/backends/image_table/paddleocr_backend.py
src/parsing/backends/image_table/_html_to_grid.py

FILES TO MODIFY
===============
src/parsing/backends/_registry.py         ← register "paddleocr" key
configs/default.yaml                      ← add paddleocr config block

DO NOT MODIFY
=============
Any existing src/datasheet/ files
Any existing test files

---

## BACKGROUND — HOW PADDLEOCR PPSTRUCTURE WORKS

Think of PPStructure like a specialist reader:
- It looks at a table image
- It finds every cell boundary
- It reads the text in each cell
- It returns an HTML string like <table><tr><td>...</td></tr></table>

Your job is to parse that HTML into GridMatrix/GridCell objects.

PPStructure usage pattern:

    from paddleocr import PPStructure
    engine = PPStructure(table=True, ocr=True, show_log=False)

    import numpy as np
    import cv2
    img_array = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)

    result = engine(img_array)
    # result is a list of region dicts
    # Each dict has: result["type"], result["res"]
    # For table regions: result["type"] == "table"
    #                    result["res"]["html"] == "<html>...</html>" string
    #                    result["res"]["cell_bbox"] == list of bounding boxes

---

## src/parsing/backends/image_table/_html_to_grid.py

Purpose: Parse PPStructure HTML output into GridMatrix.

Think of this like reading a spreadsheet from its source code.
The HTML table has rows (<tr>) and cells (<td> or <th>).
Each cell may have colspan or rowspan attributes for merged cells.

Function: parse_html_to_grid(html: str, backend_used: str) -> GridMatrix

Algorithm:

    Step 1: Parse HTML with Python's built-in html.parser (no external deps)
            Use html.parser.HTMLParser subclass to walk the tree.

    Step 2: Track a 2D grid of (row, col) positions.
            Use a dict: occupied = set() to track cells already filled by spans.

    Step 3: For each <tr>, increment row counter.
            For each <td>/<th>:
                - Read colspan (default 1) and rowspan (default 1)
                - Find next unoccupied col in current row
                - Mark all (row+r, col+c) for r in rowspan, c in colspan as occupied
                - Extract inner text, strip whitespace
                - Create GridCell(
                    row=current_row,
                    col=current_col,
                    row_span=rowspan,
                    col_span=colspan,
                    text=cleaned_text,
                    confidence=0.85   ← fixed base confidence for OCR path
                  )

    Step 4: Compute overall GridMatrix confidence:
            If no cells: return empty GridMatrix with confidence=0.0
            Mean of all cell confidences (will be 0.85 for pure OCR).

    Step 5: Return GridMatrix(
                cells=cells,
                confidence=mean_confidence,
                backend_used=backend_used,
                extraction_method="image"
            )

    Error handling:
        If HTML is empty or malformed: return GridMatrix with empty cells,
        confidence=0.0, backend_used=backend_used, extraction_method="image"
        Never raise.

---

## src/parsing/backends/image_table/paddleocr_backend.py

Class: PaddleOCRImageTableBackend(ImageTableBackend)

Constructor: __init__(self, config: Config)
    Reads from config:
        parsing.image_table_config.lang (default: "en")
        parsing.image_table_config.use_gpu (default: False)
    Does NOT instantiate PPStructure here — lazy load on first extract() call
    self._engine = None

Method: extract(self, crop_image: bytes) -> GridMatrix

    Step 1: Lazy-load PPStructure engine
        If self._engine is None:
            from paddleocr import PPStructure
            self._engine = PPStructure(
                table=True,
                ocr=True,
                show_log=False,
                lang=self._lang,
                use_gpu=self._use_gpu,
            )

    Step 2: Decode PNG bytes to numpy array
        import numpy as np, cv2
        arr = cv2.imdecode(np.frombuffer(crop_image, np.uint8), cv2.IMREAD_COLOR)
        If arr is None: return empty GridMatrix, confidence=0.0

    Step 3: Run PPStructure
        result = self._engine(arr)

    Step 4: Find first table region
        table_res = next(
            (r for r in result if r.get("type") == "table"), None
        )
        If none found: return empty GridMatrix, confidence=0.0

    Step 5: Extract HTML and parse
        html = table_res["res"].get("html", "")
        Return parse_html_to_grid(html, backend_used="paddleocr")

    Error handling:
        Engine load failure → log, return empty GridMatrix confidence=0.0
        Any runtime error → log, return empty GridMatrix confidence=0.0
        Never raise from extract()

---

## src/parsing/backends/image_table/__init__.py

Export PaddleOCRImageTableBackend only.

---

## _registry.py modification

In IMAGE_TABLE_REGISTRY add:
    "paddleocr": "src.parsing.backends.image_table.paddleocr_backend.PaddleOCRImageTableBackend"

---

## configs/default.yaml addition

Under parsing block add:

    image_table_config:
      lang: "en"
      use_gpu: false

---

GATE TESTS
==========
File: tests/unit/parsing/test_paddleocr_backend.py

All tests mock paddleocr — do not import or instantiate real PPStructure.

Test 1: PaddleOCRImageTableBackend implements ImageTableBackend
    isinstance check passes

Test 2: Engine is None at construction time
    self._engine is None after __init__

Test 3: parse_html_to_grid — simple 2x2 table
    html = "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"
    result = parse_html_to_grid(html, "paddleocr")
    Assert: len(result.cells) == 4
    Assert: cell at row=0,col=0 has text="A"
    Assert: cell at row=0,col=1 has text="B"
    Assert: cell at row=1,col=0 has text="C"
    Assert: cell at row=1,col=1 has text="D"
    Assert: result.extraction_method == "image"
    Assert: result.backend_used == "paddleocr"

Test 4: parse_html_to_grid — colspan handling
    html = "<table><tr><td colspan='2'>MERGED</td></tr><tr><td>X</td><td>Y</td></tr></table>"
    result = parse_html_to_grid(html, "paddleocr")
    merged = next(c for c in result.cells if c.text == "MERGED")
    Assert: merged.col_span == 2
    Assert: merged.row == 0
    Assert: merged.col == 0

Test 5: parse_html_to_grid — empty HTML returns empty GridMatrix
    result = parse_html_to_grid("", "paddleocr")
    Assert: result.cells == []
    Assert: result.confidence == 0.0

Test 6: extract() with mocked PPStructure returning valid table HTML
    Mock PPStructure constructor and __call__:
        __call__ returns [{"type": "table", "res": {"html": "<table><tr><td>V</td></tr></table>"}}]
    Call extract(b"fake_png_bytes")
    Assert: returns GridMatrix
    Assert: len(cells) == 1
    Assert: cells[0].text == "V"

Test 7: extract() when no table region found returns empty GridMatrix
    Mock PPStructure.__call__ returns [{"type": "figure", "res": {}}]
    result = extract(b"fake_png")
    Assert: result.cells == []
    Assert: result.confidence == 0.0

Test 8: extract() on engine load failure returns empty GridMatrix
    Mock PPStructure constructor to raise ImportError
    result = extract(b"fake_png")
    Assert: result.cells == []
    Assert no exception raised

Test 9: BackendRegistry with image_table="paddleocr" returns
    PaddleOCRImageTableBackend from get_image_table()

CONSTRAINTS
===========
- html.parser only for HTML parsing — no BeautifulSoup, no lxml
- All paddleocr, cv2, numpy imports inside methods (lazy) — never at module top level
- Never raise from extract() or parse_html_to_grid()
- Python 3.11+, Pydantic v2