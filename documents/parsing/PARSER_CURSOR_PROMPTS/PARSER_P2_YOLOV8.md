TASK
====
Implement YOLOv8LayoutDetector — the first concrete backend for the
LayoutDetectorBackend interface defined in PARSER_P1.

This is a WRAPPER, not a rewrite. The existing detection logic lives in
src/datasheet/phase1_dla/detector.py and must not be touched.
This prompt creates a thin adapter that translates the existing API
into the LayoutDetectorBackend interface contract.

CONTEXT FILES TO READ (read these before writing anything)
==========================================================
src/parsing/backends/_interfaces.py       ← interface to implement
src/parsing/backends/_schemas.py          ← BoundingBox, DetectedRegion types
src/parsing/backends/_registry.py         ← where to register this backend
src/datasheet/phase1_dla/detector.py      ← existing logic to wrap
src/datasheet/phase1_dla/__init__.py      ← existing phase1 public API
configs/default.yaml                      ← config structure

FILES TO CREATE
===============
src/parsing/backends/layout/__init__.py
src/parsing/backends/layout/yolov8_backend.py

FILES TO MODIFY
===============
src/parsing/backends/_registry.py        ← register "yolov8" key
configs/default.yaml                     ← confirm layout_detector: "yolov8"

DO NOT MODIFY
=============
src/datasheet/phase1_dla/detector.py
src/datasheet/phase1_dla/__init__.py
Any existing test files

---

## src/parsing/backends/layout/yolov8_backend.py

Class: YOLOv8LayoutDetector(LayoutDetectorBackend)

Constructor:
    __init__(self, config: Config)
    - Reads model path from config.get_model_path("yolov8n_doclaynet")
    - Reads confidence threshold from config:
        parsing.layout_detector_config.confidence_min (default: 0.55)
    - Does NOT load the YOLO model here — lazy load on first detect() call
    - Stores model as self._model = None initially

Method: detect(self, page_image: bytes, page_number: int) -> list[DetectedRegion]

    Step 1: Lazy-load model
        If self._model is None:
            Import _load_yolo_model from src.datasheet.phase1_dla.detector
            Call it with self._config
            Store result in self._model

    Step 2: Convert input
        page_image is PNG bytes
        Convert to PIL.Image via io.BytesIO

    Step 3: Call existing detection
        Import _detect_tables from src.datasheet.phase1_dla.detector
        Call: raw_detections = _detect_tables(pil_image, self._model, self._confidence_min)

    Step 4: Translate output
        raw_detections is list[dict] with keys:
            "bounding_box": (x1, y1, x2, y2)
            "confidence": float
            "class_id": int (3=table, 4=footnote, 2=caption)

        Map class_id to region_type string:
            3 → "table"
            4 → "footnote"
            2 → "caption"
            anything else → "unknown"

        For each raw detection, produce one DetectedRegion:
            region_type = mapped string above
            bbox = BoundingBox(
                x1, y1, x2, y2 from bounding_box tuple,
                page_number=page_number,
                confidence=detection["confidence"]
            )
            crop_image = call _crop_region(pil_image, bounding_box)
                         Import _crop_region from src.datasheet.phase1_dla.detector

        Return list[DetectedRegion]

    Error handling:
        If model load fails: log error, return []
        If detection raises: log error, return []
        Never raise from detect() — caller must always get a list back

---

## src/parsing/backends/layout/__init__.py

Export YOLOv8LayoutDetector only.

---

## _registry.py modification

In LAYOUT_DETECTOR_REGISTRY add:
    "yolov8": "src.parsing.backends.layout.yolov8_backend.YOLOv8LayoutDetector"

The registry uses importlib to load this class string lazily.
Constructor signature expected by registry: __init__(self, config: Config)

---

## configs/default.yaml modification

Under parsing block, add backend-specific config:

parsing:
  layout_detector: "yolov8"
  vector_table: "pdfplumber_camelot"
  image_table: "paddleocr"
  vlm: "qwen2_vl"
  llm: "qwen25_7b"
  layout_detector_config:
    confidence_min: 0.55

---

GATE TESTS
==========
File: tests/unit/parsing/test_yolov8_backend.py

Test 1: YOLOv8LayoutDetector implements LayoutDetectorBackend
    isinstance check passes

Test 2: Model is not loaded at construction time
    After __init__, self._model is None

Test 3: detect() with mocked _detect_tables returns correct DetectedRegion types
    Mock _detect_tables to return one table (class_id=3) and one footnote (class_id=4)
    Mock _load_yolo_model to return a sentinel object
    Mock _crop_region to return b"fake_png"
    Call detect(fake_png_bytes, page_number=0)
    Assert: returns 2 DetectedRegion objects
    Assert: first has region_type="table"
    Assert: second has region_type="footnote"
    Assert: both have page_number=0
    Assert: both have crop_image=b"fake_png"

Test 4: detect() returns [] on model load failure
    Mock _load_yolo_model to raise FileNotFoundError
    Call detect(fake_png_bytes, 0)
    Assert: returns []
    Assert: no exception raised

Test 5: detect() returns [] on detection failure
    Model loads fine (mocked)
    Mock _detect_tables to raise RuntimeError
    Call detect(fake_png_bytes, 0)
    Assert: returns []

Test 6: BackendRegistry with config layout_detector="yolov8" returns
    YOLOv8LayoutDetector instance from get_layout_detector()
    Mock Config to return "yolov8" for parsing.layout_detector
    Assert isinstance(registry.get_layout_detector(), YOLOv8LayoutDetector)

Test 7: Second call to get_layout_detector() returns same instance (cache)
    Call twice, assert result1 is result2

CONSTRAINTS
===========
- All tests mock heavy dependencies (ultralytics, PIL, model weights)
- No real PDFs, no real model inference in tests
- Wrapper only — zero detection logic duplicated from phase1_dla
- Python 3.11+, Pydantic v2