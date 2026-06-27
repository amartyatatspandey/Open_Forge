TASK
====
Implement ModularPipeline — a new pipeline orchestrator that routes every
processing stage through the BackendRegistry instead of calling phase
functions directly.

The existing src/datasheet/pipeline.py is NOT touched.
This is a parallel entry point: same output contract (ComponentDatasheet),
fully swappable backends.

Think of it like this:
  pipeline.py        = hardwired circuit board
  modular_pipeline.py = same board, but every chip is socketed

CONTEXT FILES TO READ
=====================
src/parsing/backends/_interfaces.py         ← five interface contracts
src/parsing/backends/_schemas.py            ← shared types
src/parsing/backends/_registry.py           ← BackendRegistry
src/parsing/backends/__init__.py            ← all exports
src/datasheet/pipeline.py                   ← existing orchestrator to mirror
src/datasheet/phase1_dla/__init__.py        ← phase1 process() signature
src/datasheet/phase1_dla/_schemas.py        ← Phase1Output, TableCrop
src/datasheet/phase2_tsr/_schemas.py        ← Phase2Output, GridMatrix
src/datasheet/phase3_extract/__init__.py    ← phase3 process() signature
src/datasheet/phase4_validate/__init__.py   ← validate(), apply_verdict()
src/datasheet/phase5_layout/__init__.py     ← extract_layout_constraints()
src/schemas/datasheet.py                    ← ComponentDatasheet
configs/default.yaml                        ← config structure

FILES TO CREATE
===============
src/parsing/modular_pipeline.py
src/parsing/__init__.py

DO NOT MODIFY
=============
src/datasheet/pipeline.py
src/parsing/backends/  (any file)
Any existing test files

---

## ARCHITECTURE

The modular pipeline has three responsibilities:

1. PHASE 1 (Layout Detection) — use LayoutDetectorBackend
   Replace: phase1_dla(pdf_path, config)
   With:    registry.get_layout_detector().detect(page_image, page_number)
            called per-page after rasterization

2. PHASE 2 (Table Extraction) — use VectorTableBackend + ImageTableBackend
   Replace: phase2_tsr(phase1_output, config)
   With:    For each DetectedRegion:
              Try VectorTableBackend first (fast, deterministic)
              If confidence < threshold → fall back to ImageTableBackend
              Pick winner by confidence

3. PHASE 3 (Semantic Extraction) — use LLMBackend
   Replace: phase3_extract(phase2_output, config)
   With:    registry.get_llm().extract(table_text, system_prompt, schema)
            per GridMatrix

Phases 4 and 5 are deterministic — they do NOT use backends.
They are called identically to the existing pipeline.py.

---

## src/parsing/modular_pipeline.py

### Helper: _rasterize_pdf(pdf_path: Path) -> list[tuple[int, bytes]]

    Use pdf2image.convert_from_path at 300 DPI.
    Return list of (page_number, png_bytes) — 0-indexed page numbers.
    On failure: raise RuntimeError with message.

---

### Helper: _run_phase1(pdf_path, registry, config) -> Phase1Output

    Step 1: Rasterize all pages via _rasterize_pdf()

    Step 2: For each (page_number, png_bytes):
        regions = registry.get_layout_detector().detect(png_bytes, page_number)

    Step 3: Translate DetectedRegion list → TableCrop list
        Only keep regions where region_type in ("table", "caption")
        For each kept region:
            from src.datasheet.phase1_dla._schemas import TableCrop
            from src.schemas.datasheet import TableSectionType

            TableCrop(
                page_number=region.bbox.page_number,
                section_type=TableSectionType.OTHER,   ← modular pipeline
                                                         does not classify;
                                                         Phase 3 LLM does it
                image_bytes=region.crop_image or b"",
                bounding_box=(
                    region.bbox.x1,
                    region.bbox.y1,
                    region.bbox.x2,
                    region.bbox.y2,
                ),
                heading_text=None,
                is_multipage_continuation=False,
                detection_confidence=region.bbox.confidence,
            )

    Step 4: Extract footnote regions separately
        Keep regions where region_type == "footnote"
        Store as raw DetectedRegion list — footnote linkage is not
        implemented in modular pipeline yet (deferred).
        Pass empty footnote_maps to Phase1Output.

    Step 5: Return Phase1Output(
        pdf_path=pdf_path,
        source_pdf_hash=_compute_hash(pdf_path),  ← sha256 of file bytes
        total_pages=len(pages),
        table_crops=table_crops,
        footnote_maps=[],
        processing_time_ms=elapsed_ms,
    )

---

### Helper: _run_phase2(phase1_output, pdf_path, registry, config) -> Phase2Output

    Confidence threshold for vector→image fallback:
        Read from config: parsing.phase2_vector_confidence_min (default: 0.80)

    For each TableCrop in phase1_output.table_crops:

        Step 1: Try VectorTableBackend
            bbox = BoundingBox(
                x1=crop.bounding_box[0],
                y1=crop.bounding_box[1],
                x2=crop.bounding_box[2],
                y2=crop.bounding_box[3],
                page_number=crop.page_number,
                confidence=crop.detection_confidence,
            )
            vector_result = registry.get_vector_table().extract(
                pdf_path=str(pdf_path),
                page_number=crop.page_number,
                bbox=bbox,
            )

        Step 2: Decide whether to try ImageTableBackend
            if vector_result.confidence >= threshold:
                winner = vector_result
            else:
                image_result = registry.get_image_table().extract(
                    crop_image=crop.image_bytes
                )
                winner = image_result if image_result.confidence
                         >= vector_result.confidence else vector_result

        Step 3: Translate shared GridMatrix → internal GridMatrix
            The downstream phase3_extract still uses the internal type.
            from src.datasheet.phase2_tsr._schemas import (
                GridMatrix as InternalGridMatrix,
                CellValue,
            )
            InternalGridMatrix(
                cells=[
                    CellValue(
                        text=c.text,
                        row=c.row,
                        col=c.col,
                        rowspan=c.row_span,
                        colspan=c.col_span,
                        is_header=(c.row == 0),
                    )
                    for c in winner.cells
                ],
                num_rows=max((c.row for c in winner.cells), default=0) + 1,
                num_cols=max((c.col for c in winner.cells), default=0) + 1,
                section_type=crop.section_type,
                source_page=crop.page_number,
                source_table_index=idx,
                extraction_path=winner.extraction_method,
                confidence=winner.confidence,
                has_merged_cells=any(
                    c.row_span > 1 or c.col_span > 1
                    for c in winner.cells
                ),
            )

    Return Phase2Output(
        grids=internal_grids,
        footnote_maps=[],
        source_pdf_hash=phase1_output.source_pdf_hash,
        processing_time_ms=elapsed_ms,
    )

---

### Helper: _run_phase3(phase2_output, registry, config) -> ComponentDatasheet

    The LLMBackend returns free-form LLMResponse, but phase3_extract.process()
    expects Phase2Output and returns a full ComponentDatasheet.

    For the modular pipeline, delegate entirely to the existing phase3:
        from src.datasheet.phase3_extract import process as phase3_extract
        return phase3_extract(phase2_output, config)

    Rationale: Phase 3's Instructor-based extraction is tightly coupled to
    Pydantic schemas. Decoupling it fully is a later task (post all backends
    stable). The LLMBackend is used for book parsing and app notes —
    not for the datasheet extraction schema path yet.
    Document this clearly in a comment.

---

### Main function: parse_datasheet_modular

def parse_datasheet_modular(
    component_id: str,
    pdf_path: Path,
    config: Config,
) -> ComponentDatasheet:

    Mirrors parse_datasheet() in pipeline.py exactly:
    - Same FileNotFoundError check
    - Same phase ordering: 1 → 2 → 3 → 4 → 5
    - Same DatasheetPipelineError wrapping
    - Same review queue enqueue on review_required=True
    - Same model_copy pattern for component_id and layout_constraints
    - Same logging at each phase boundary

    Differences from pipeline.py:
    - Instantiates BackendRegistry(config) at start
    - Calls _run_phase1, _run_phase2, _run_phase3 instead of
      phase1_dla, phase2_tsr, phase3_extract directly
    - Phases 4 and 5 called identically to pipeline.py

---

## src/parsing/__init__.py

Export parse_datasheet_modular and nothing else.

---

## configs/default.yaml addition

Under parsing block add:

    phase2_vector_confidence_min: 0.80

---

GATE TESTS
==========
File: tests/unit/parsing/test_modular_pipeline.py

All backends mocked. No real PDFs, no real models, no real file I/O.

Test 1: parse_datasheet_modular raises FileNotFoundError for missing PDF
    Pass a path that does not exist
    Assert FileNotFoundError raised before any backend is called

Test 2: parse_datasheet_modular calls layout detector once per page
    Mock _rasterize_pdf to return 3 pages of fake PNG bytes
    Mock registry.get_layout_detector().detect to return []
    Mock _run_phase2, _run_phase3, phase4, phase5 to return stubs
    Assert detect() called exactly 3 times

Test 3: Vector backend wins when confidence >= threshold
    One table crop, vector_result.confidence = 0.95 (>= 0.80)
    Assert ImageTableBackend.extract NOT called

Test 4: Image backend used when vector confidence < threshold
    One table crop, vector_result.confidence = 0.60 (< 0.80)
    image_result.confidence = 0.82
    Assert ImageTableBackend.extract IS called
    Assert winner is image_result (higher confidence)

Test 5: Vector wins even after image fallback if vector still higher
    vector_result.confidence = 0.70 (triggers fallback)
    image_result.confidence = 0.65 (still lower than vector)
    Assert winner is vector_result

Test 6: Empty detection regions → empty Phase1Output table_crops
    Mock detect() to return [] for all pages
    Assert phase1_output.table_crops == []

Test 7: DatasheetPipelineError raised when _run_phase1 fails
    Mock _rasterize_pdf to raise RuntimeError("poppler not found")
    Assert DatasheetPipelineError raised
    Assert error.phase == "Phase 1"
    Assert no exception leaks as raw RuntimeError

Test 8: BackendRegistry instantiated exactly once per pipeline call
    Spy on BackendRegistry.__init__
    Call parse_datasheet_modular
    Assert BackendRegistry constructed once

Test 9: parse_datasheet_modular and parse_datasheet produce same type
    Both return ComponentDatasheet
    Assert isinstance(result, ComponentDatasheet)

CONSTRAINTS
===========
- DatasheetPipelineError import reused from src.datasheet.pipeline
- _compute_hash is sha256 of raw PDF bytes — implement inline, no import
- Phase 3 delegation to existing phase3_extract clearly commented
- Python 3.11+, Pydantic v2
- Never raise raw exceptions from phase helpers — always wrap as
  DatasheetPipelineError with correct phase name