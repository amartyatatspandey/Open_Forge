TASK
====
Implement Qwen2VLImageTableBackend — a second concrete ImageTableBackend
that wraps the existing Qwen2-VL extraction logic in path_b_vlm.py.

This proves the plug-and-play swap works: two backends implementing the
same ImageTableBackend interface, switchable via one config line.

CONTEXT FILES TO READ
=====================
src/parsing/backends/_interfaces.py              ← ImageTableBackend to implement
src/parsing/backends/_schemas.py                 ← GridMatrix, GridCell types
src/parsing/backends/_registry.py               ← where to register
src/parsing/backends/image_table/paddleocr_backend.py  ← pattern to follow
src/datasheet/phase2_tsr/path_b_vlm.py          ← existing logic to wrap
src/datasheet/phase2_tsr/_schemas.py            ← internal GridMatrix, CellValue
configs/default.yaml                            ← config structure

FILES TO CREATE
===============
src/parsing/backends/image_table/qwen2_vl_backend.py

FILES TO MODIFY
===============
src/parsing/backends/_registry.py              ← register "qwen2_vl" key
src/parsing/backends/image_table/__init__.py   ← export Qwen2VLImageTableBackend
configs/default.yaml                           ← add qwen2_vl config block

DO NOT MODIFY
=============
src/datasheet/phase2_tsr/path_b_vlm.py
src/parsing/backends/image_table/paddleocr_backend.py
Any existing test files

---

## TRANSLATION PROBLEM

Same translation as PARSER_P4 — internal types to shared types:

path_b_vlm.py produces:  src.datasheet.phase2_tsr._schemas.GridMatrix
                         cells are CellValue objects

This backend must produce: src.parsing.backends._schemas.GridMatrix
                           cells are GridCell objects

Additionally, path_b_vlm.py requires a TableCrop as input.
This backend receives only PNG bytes (crop_image: bytes).
The wrapper must construct a minimal TableCrop from the bytes.

---

## src/parsing/backends/image_table/qwen2_vl_backend.py

Class: Qwen2VLImageTableBackend(ImageTableBackend)

Constructor: __init__(self, config: Config)
    Reads from config:
        parsing.qwen2_vl_config.model_key (default: "qwen2_vl_7b")
            ← this is the key passed to config.get_model_path()
    Stores config. No model loading here — path_b_vlm handles lazy loading
    internally via its own model cache.

Method: extract(self, crop_image: bytes) -> GridMatrix

    Step 1: Build minimal TableCrop from PNG bytes
        The existing extract_table_vlm_path() needs a TableCrop.
        Only image_bytes and page_number are actually used by path_b_vlm.

        from src.datasheet.phase1_dla._schemas import TableCrop
        from src.schemas.datasheet import TableSectionType

        table_crop = TableCrop(
            page_number=0,
            section_type=TableSectionType.OTHER,
            image_bytes=crop_image,
            bounding_box=(0, 0, 0, 0),
            heading_text=None,
            is_multipage_continuation=False,
            detection_confidence=1.0,
        )

    Step 2: Call existing logic
        from src.datasheet.phase2_tsr.path_b_vlm import extract_table_vlm_path
        from pathlib import Path

        internal_grid = extract_table_vlm_path(
            pdf_path=Path(""),        ← not used by VLM path (uses image_bytes)
            table_crop=table_crop,
            table_index=0,
            config=self._config,
        )

    Step 3: Handle None (model unavailable or parse failed)
        If internal_grid is None:
            Return GridMatrix(
                cells=[],
                confidence=0.0,
                backend_used="qwen2_vl",
                extraction_method="image"
            )

    Step 4: Translate internal GridMatrix → shared GridMatrix
        internal_grid.cells is list[CellValue]
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
            backend_used="qwen2_vl",
            extraction_method="image"
        )

    Error handling:
        Any exception → log, return empty GridMatrix confidence=0.0
        Never raise from extract()

---

## _registry.py modification

In IMAGE_TABLE_REGISTRY add:
    "qwen2_vl": "src.parsing.backends.image_table.qwen2_vl_backend.Qwen2VLImageTableBackend"

IMAGE_TABLE_REGISTRY should now have two entries:
    "paddleocr": "src.parsing.backends.image_table.paddleocr_backend.PaddleOCRImageTableBackend"
    "qwen2_vl":  "src.parsing.backends.image_table.qwen2_vl_backend.Qwen2VLImageTableBackend"

---

## src/parsing/backends/image_table/__init__.py modification

Add Qwen2VLImageTableBackend to exports alongside PaddleOCRImageTableBackend.

---

## configs/default.yaml addition

Under parsing block add:

    qwen2_vl_config:
      model_key: "qwen2_vl_7b"

---

GATE TESTS
==========
File: tests/unit/parsing/test_qwen2_vl_backend.py

All tests mock extract_table_vlm_path — no real model weights loaded.

Test 1: Qwen2VLImageTableBackend implements ImageTableBackend
    isinstance check passes

Test 2: extract() when internal returns None → empty GridMatrix
    Mock extract_table_vlm_path to return None
    result = backend.extract(b"fake_png")
    Assert: result.cells == []
    Assert: result.confidence == 0.0
    Assert: result.backend_used == "qwen2_vl"
    Assert: result.extraction_method == "image"

Test 3: extract() translates CellValue list correctly
    Build fake internal GridMatrix with 2 CellValue objects:
        CellValue(text="Min", row=0, col=0, rowspan=1, colspan=1, is_header=True)
        CellValue(text="1.8", row=1, col=0, rowspan=1, colspan=1, is_header=False)
    Mock extract_table_vlm_path to return this
    result = backend.extract(b"fake_png")
    Assert: len(result.cells) == 2
    Assert: result.cells[0].text == "Min"
    Assert: result.cells[1].text == "1.8"
    Assert: result.backend_used == "qwen2_vl"
    Assert: result.extraction_method == "image"

Test 4: extract() on exception returns empty GridMatrix
    Mock extract_table_vlm_path to raise RuntimeError
    result = backend.extract(b"fake_png")
    Assert: result.cells == []
    Assert no exception raised

Test 5: TableCrop passed to extract_table_vlm_path has correct image_bytes
    Capture the TableCrop via mock
    input_bytes = b"real_table_image_data"
    backend.extract(input_bytes)
    Assert: captured table_crop.image_bytes == input_bytes

Test 6: BackendRegistry with image_table="qwen2_vl" returns
    Qwen2VLImageTableBackend from get_image_table()
    Assert isinstance check passes

Test 7: SWAP TEST — proves plug-and-play works
    Create two registries:
        registry_paddle with config image_table="paddleocr"
        registry_qwen   with config image_table="qwen2_vl"
    Assert: isinstance(registry_paddle.get_image_table(), PaddleOCRImageTableBackend)
    Assert: isinstance(registry_qwen.get_image_table(),   Qwen2VLImageTableBackend)
    Both implement ImageTableBackend:
    Assert: isinstance(registry_paddle.get_image_table(), ImageTableBackend)
    Assert: isinstance(registry_qwen.get_image_table(),   ImageTableBackend)

CONSTRAINTS
===========
- Zero duplication of VLM logic from path_b_vlm.py
- Never import transformers, torch, or PIL at module top level
- Python 3.11+, Pydantic v2
- Test 7 is the most important — it must pass to prove the system works