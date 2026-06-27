TASK
====
Implement PdfplumberCamelotVectorTableBackend — a concrete VectorTableBackend
that wraps the existing pdfplumber + Camelot extraction logic.

This is a WRAPPER. All extraction logic already exists in
src/datasheet/phase2_tsr/path_a_vector.py — do not duplicate it.

CONTEXT FILES TO READ
=====================
src/parsing/backends/_interfaces.py              ← VectorTableBackend to implement
src/parsing/backends/_schemas.py                 ← BoundingBox, GridMatrix, GridCell
src/parsing/backends/_registry.py               ← where to register
src/datasheet/phase2_tsr/path_a_vector.py       ← existing logic to wrap
src/datasheet/phase2_tsr/_schemas.py            ← existing GridMatrix/CellValue types
configs/default.yaml                            ← config structure

FILES TO CREATE
===============
src/parsing/backends/vector_table/__init__.py
src/parsing/backends/vector_table/pdfplumber_camelot_backend.py

FILES TO MODIFY
===============
src/parsing/backends/_registry.py              ← register "pdfplumber_camelot" key
configs/default.yaml                           ← add vector_table_config block

DO NOT MODIFY
=============
src/datasheet/phase2_tsr/path_a_vector.py
Any existing test files

---

## TRANSLATION PROBLEM

The existing path_a_vector.py uses internal types:
  - Input:  pdf_path (Path), table_crop (TableCrop), table_index (int), config (Config)
  - Output: src.datasheet.phase2_tsr._schemas.GridMatrix (internal type)

The VectorTableBackend interface uses:
  - Input:  pdf_path (str), page_number (int), bbox (BoundingBox)
  - Output: src.parsing.backends._schemas.GridMatrix (shared type)

The wrapper's only real job is translating between these two type systems.

---

## src/parsing/backends/vector_table/pdfplumber_camelot_backend.py

Class: PdfplumberCamelotVectorTableBackend(VectorTableBackend)

Constructor: __init__(self, config: Config)
    Store config. No lazy loading needed — pdfplumber and camelot
    are pure function calls, no persistent model state.

Method: extract(self, pdf_path: str, page_number: int, bbox: BoundingBox) -> GridMatrix

    Step 1: Build a minimal TableCrop for the existing API
        The existing extract_table_vector_path() requires a TableCrop object.
        Construct one with only the fields it actually uses:

        from src.datasheet.phase1_dla._schemas import TableCrop
        from src.schemas.datasheet import TableSectionType

        table_crop = TableCrop(
            page_number=page_number,
            section_type=TableSectionType.OTHER,   ← neutral default
            image_bytes=b"",                        ← not used by vector path
            bounding_box=(bbox.x1, bbox.y1, bbox.x2, bbox.y2),
            heading_text=None,
            is_multipage_continuation=False,
            detection_confidence=1.0,
        )

    Step 2: Call existing logic
        from src.datasheet.phase2_tsr.path_a_vector import extract_table_vector_path
        internal_grid = extract_table_vector_path(
            pdf_path=Path(pdf_path),
            table_crop=table_crop,
            table_index=0,
            config=self._config,
        )

    Step 3: Handle None (borderless table — Camelot found no lattice lines)
        If internal_grid is None:
            Return GridMatrix(
                cells=[],
                confidence=0.0,
                backend_used="pdfplumber_camelot",
                extraction_method="vector"
            )

    Step 4: Translate internal GridMatrix → shared GridMatrix
        internal_grid has: cells (list[CellValue]), confidence, num_rows, num_cols

        CellValue has: text, row, col, rowspan, colspan, is_header

        For each CellValue produce one GridCell:
            GridCell(
                row=cell.row,
                col=cell.col,
                row_span=cell.rowspan,
                col_span=cell.colspan,
                text=cell.text,
                confidence=internal_grid.confidence
            )

        Return GridMatrix(
            cells=translated_cells,
            confidence=internal_grid.confidence,
            backend_used="pdfplumber_camelot",
            extraction_method="vector"
        )

    Error handling:
        Any exception → log, return empty GridMatrix confidence=0.0
        Never raise from extract()

---

## src/parsing/backends/vector_table/__init__.py

Export PdfplumberCamelotVectorTableBackend only.

---

## _registry.py modification

In VECTOR_TABLE_REGISTRY add:
    "pdfplumber_camelot": "src.parsing.backends.vector_table.pdfplumber_camelot_backend.PdfplumberCamelotVectorTableBackend"

---

## configs/default.yaml addition

Under parsing block add:

    vector_table_config:
      flavor: "lattice"        ← Camelot mode, kept for future configurability

---

GATE TESTS
==========
File: tests/unit/parsing/test_pdfplumber_camelot_backend.py

All tests mock extract_table_vector_path — no real PDFs, no real Camelot.

Test 1: PdfplumberCamelotVectorTableBackend implements VectorTableBackend
    isinstance check passes

Test 2: extract() when internal returns None → empty GridMatrix
    Mock extract_table_vector_path to return None
    result = backend.extract("fake.pdf", 1, BoundingBox(0,0,100,100,1,0.9))
    Assert: result.cells == []
    Assert: result.confidence == 0.0
    Assert: result.backend_used == "pdfplumber_camelot"
    Assert: result.extraction_method == "vector"

Test 3: extract() translates CellValue list correctly
    Build a fake internal GridMatrix with 2 CellValue objects:
        CellValue(text="Parameter", row=0, col=0, rowspan=1, colspan=1, is_header=True)
        CellValue(text="3.3V",      row=1, col=0, rowspan=1, colspan=1, is_header=False)
    Mock extract_table_vector_path to return this
    result = backend.extract("fake.pdf", 1, BoundingBox(0,0,200,200,1,0.9))
    Assert: len(result.cells) == 2
    Assert: result.cells[0].text == "Parameter"
    Assert: result.cells[0].row == 0
    Assert: result.cells[1].text == "3.3V"
    Assert: result.confidence == internal_grid.confidence
    Assert: result.extraction_method == "vector"

Test 4: extract() propagates rowspan and colspan correctly
    CellValue(text="MERGED", row=0, col=0, rowspan=2, colspan=3, is_header=True)
    result cell at index 0:
    Assert: row_span == 2
    Assert: col_span == 3

Test 5: extract() on exception returns empty GridMatrix
    Mock extract_table_vector_path to raise RuntimeError("camelot failed")
    result = backend.extract("fake.pdf", 1, BoundingBox(0,0,100,100,1,0.9))
    Assert: result.cells == []
    Assert: result.confidence == 0.0
    Assert no exception raised

Test 6: BackendRegistry with vector_table="pdfplumber_camelot" returns
    PdfplumberCamelotVectorTableBackend from get_vector_table()
    Assert isinstance check passes

Test 7: TableCrop constructed inside extract() has correct page_number
    Capture the TableCrop passed to extract_table_vector_path via mock
    Assert: table_crop.page_number == the page_number argument passed in

CONSTRAINTS
===========
- Zero duplication of extraction logic from path_a_vector.py
- Path object constructed inside extract() from the str argument
- All camelot/pdfplumber imports remain inside path_a_vector.py — never imported here
- Python 3.11+, Pydantic v2