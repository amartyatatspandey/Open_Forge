TASK
====
Define the pluggable backend interface layer for the OpenForge parsing pipeline.
No implementations. Interfaces and registry only.

CONTEXT
=======
The parser processes multiple document types through a tiered pipeline.
Every processing stage must accept any compliant backend, selected via config.
This is the contract all future backend implementations will implement against.

FILES TO CREATE
===============
src/parsing/backends/__init__.py
src/parsing/backends/_interfaces.py
src/parsing/backends/_registry.py
src/parsing/backends/_schemas.py

DO NOT TOUCH ANY EXISTING FILES.

---

## src/parsing/backends/_schemas.py

Pydantic models that flow between pipeline stages.
All backends consume and produce these types — never raw dicts.

```python
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
import numpy as np

class BoundingBox(BaseModel):
    """Pixel-space bounding box on a rasterized page."""
    x1: int
    y1: int
    x2: int
    y2: int
    page_number: int
    confidence: float = Field(ge=0.0, le=1.0)

class DetectedRegion(BaseModel):
    """One region detected on a page — table, figure, footnote, etc."""
    region_type: str        # "table", "figure", "footnote", "text_block"
    bbox: BoundingBox
    crop_image: Optional[bytes] = None   # PNG bytes of the cropped region

class GridCell(BaseModel):
    """One cell in an extracted table grid."""
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    text: str
    confidence: float = Field(ge=0.0, le=1.0)

class GridMatrix(BaseModel):
    """Full structured grid from a table extraction backend."""
    cells: list[GridCell]
    confidence: float = Field(ge=0.0, le=1.0)
    backend_used: str       # which backend produced this
    extraction_method: str  # "vector" or "image"

class VLMResponse(BaseModel):
    """Free-form structured response from a VLM."""
    raw_text: str
    structured_data: Optional[dict] = None
    confidence: float = Field(ge=0.0, le=1.0)
    backend_used: str

class LLMResponse(BaseModel):
    """Structured JSON response from an LLM extraction call."""
    raw_text: str
    parsed_json: Optional[dict] = None
    confidence: float = Field(ge=0.0, le=1.0)
    backend_used: str
```

---

## src/parsing/backends/_interfaces.py

Five abstract base classes. Each has exactly one primary method.
Use Python abc.ABC and abc.abstractmethod throughout.
All methods are synchronous.

```python
class LayoutDetectorBackend(ABC):
    """Finds regions (tables, figures, footnotes) on a rasterized page image."""

    @abstractmethod
    def detect(self, page_image: bytes, page_number: int) -> list[DetectedRegion]:
        """
        Args:
            page_image: PNG bytes of one full page at 300 DPI
            page_number: 0-indexed page number

        Returns:
            List of DetectedRegion, one per found region.
            Empty list if nothing found — never raises.
        """

class VectorTableBackend(ABC):
    """Extracts table structure from vector PDF data (no image needed)."""

    @abstractmethod
    def extract(self, pdf_path: str, page_number: int, bbox: BoundingBox) -> GridMatrix:
        """
        Args:
            pdf_path: Absolute path to source PDF
            page_number: 0-indexed page number
            bbox: Bounding box of the table region

        Returns:
            GridMatrix. On failure returns GridMatrix with empty cells and confidence=0.0
        """

class ImageTableBackend(ABC):
    """Extracts table structure from a cropped table image (OCR/VLM path)."""

    @abstractmethod
    def extract(self, crop_image: bytes) -> GridMatrix:
        """
        Args:
            crop_image: PNG bytes of the cropped table region

        Returns:
            GridMatrix. On failure returns GridMatrix with empty cells and confidence=0.0
        """

class VLMBackend(ABC):
    """Runs a vision-language model on an image with a text prompt."""

    @abstractmethod
    def query(self, image: bytes, prompt: str) -> VLMResponse:
        """
        Args:
            image: PNG bytes of the image (figure, diagram, etc.)
            prompt: Instruction prompt for the VLM

        Returns:
            VLMResponse with raw text and optionally structured_data
        """

class LLMBackend(ABC):
    """Runs a language model for structured semantic extraction."""

    @abstractmethod
    def extract(self, text: str, system_prompt: str, output_schema: dict) -> LLMResponse:
        """
        Args:
            text: Input text or grid to extract from
            system_prompt: Instruction for the model
            output_schema: JSON Schema dict describing expected output

        Returns:
            LLMResponse with parsed_json matching output_schema when possible
        """
```

---

## src/parsing/backends/_registry.py

```python
BackendRegistry class:

__init__(self, config: Config):
    Reads these config keys:
        parsing.layout_detector: str         # e.g. "yolov8"
        parsing.vector_table: str            # e.g. "pdfplumber_camelot"
        parsing.image_table: str             # e.g. "paddleocr"
        parsing.vlm: str                     # e.g. "qwen2_vl"
        parsing.llm: str                     # e.g. "qwen25_7b"

    Raises ValueError with helpful message if an unknown backend name is given.
    Does NOT instantiate backends here — lazy instantiation only.

get_layout_detector() -> LayoutDetectorBackend
get_vector_table() -> VectorTableBackend
get_image_table() -> ImageTableBackend
get_vlm() -> VLMBackend
get_llm() -> LLMBackend

Each getter:
- Returns the cached instance if already created
- Creates and caches the instance on first call
- Looks up the backend class from a REGISTRY dict keyed by backend name string
- Example REGISTRY structure (classes are imported lazily inside the dict or getter):
    LAYOUT_DETECTOR_REGISTRY = {
        "yolov8": "src.parsing.backends.layout.yolov8_backend.YOLOv8LayoutDetector",
        "surya":  "src.parsing.backends.layout.surya_backend.SuryaLayoutDetector",
    }
  Use importlib.import_module to load the class string — this prevents
  import-time failures when a backend's dependencies aren't installed.
```

---

## src/parsing/backends/__init__.py

Export:
- All five interface classes
- BackendRegistry
- All schema classes (BoundingBox, DetectedRegion, GridCell, GridMatrix, VLMResponse, LLMResponse)

---

## configs/default.yaml additions

Add this block under existing config (do not remove existing keys):

```yaml
parsing:
  layout_detector: "yolov8"
  vector_table: "pdfplumber_camelot"
  image_table: "paddleocr"
  vlm: "qwen2_vl"
  llm: "qwen25_7b"
```

---

GATE TESTS
==========
Write tests in tests/unit/parsing/test_backends_interfaces.py

Test 1: Each interface cannot be instantiated directly (ABC enforcement)
Test 2: A minimal stub implementing each interface can be instantiated
Test 3: BackendRegistry raises ValueError for unknown backend names
Test 4: BackendRegistry returns same instance on two consecutive get_ calls (lazy cache)
Test 5: Config keys map to correct registry keys without error

No real model weights. No file I/O. Pure contract tests only.
Mock all imports that would require heavy dependencies.

CONSTRAINTS
===========
- No implementations of any backend in this prompt
- No changes to any existing src/ files
- Pydantic v2 throughout
- Python 3.11+
- crop_image in DetectedRegion is Optional — not all callers populate it immediately