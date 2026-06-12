# Coding Standards & Practices for P1 Datasheet Parser
**For clean, maintainable, high-quality, efficient code**

---

## 1. Project Structure (The Blueprint)

### Why Structure Matters
**Analogy:** Imagine a car factory. If engines are in the back, wheels in the front, batteries scattered randomly—the assembly line breaks. Structure lets everyone know where to find things.

### Recommended Layout
```
drdo-p1-parser/
├── src/
│   ├── __init__.py                 # Package marker (always include)
│   ├── config.py                   # ⭐ SINGLE SOURCE OF TRUTH for settings
│   ├── schemas.py                  # ⭐ ALL Pydantic models (no scattered definitions)
│   ├── phase1_dla/
│   │   ├── __init__.py
│   │   ├── rasterizer.py          # PDF → images
│   │   ├── object_detector.py      # Table/footnote detection
│   │   └── footnote_linker.py      # Superscript matching
│   ├── phase2_tsr/
│   │   ├── __init__.py
│   │   ├── vector_path.py          # pdfplumber + Camelot
│   │   ├── vlm_path.py             # Local Qwen2-VL inference
│   │   └── confidence_scorer.py     # pick_best_grid logic
│   ├── phase3_extract/
│   │   ├── __init__.py
│   │   ├── unit_normalizer.py      # mV → V, µA → mA conversions
│   │   ├── llm_extractor.py        # Instructor + local LLM
│   │   └── footnote_injector.py    # Connect Phase 1 footnotes
│   ├── phase4_validate/
│   │   ├── __init__.py
│   │   ├── rule_engine.py          # Min/max ordering, cross-param rules
│   │   └── sanity_checker.py       # Range validation
│   ├── pipeline.py                 # ⭐ ORCHESTRATOR (Phase 1→2→3→4)
│   ├── logging_config.py           # Centralized logging
│   └── utils/
│       ├── __init__.py
│       ├── pdf_helpers.py          # pdf2image, cleanup
│       └── io_helpers.py           # JSON read/write
├── tests/
│   ├── unit/                       # Phase-by-phase unit tests
│   │   ├── test_phase1_rasterizer.py
│   │   ├── test_phase2_vector_path.py
│   │   └── ...
│   ├── integration/                # Full pipeline tests
│   │   └── test_end_to_end.py
│   └── fixtures/                   # Sample PDFs, ground truth JSON
├── models/
│   ├── .gitkeep                    # Placeholder—weights go here (gitignore this)
│   └── README.md                   # Instructions for offline weight transfer
├── corpus/
│   ├── golden/                     # 5 golden datasheets (manually verified)
│   │   ├── TI_OPA2134_v1.pdf
│   │   └── TI_OPA2134_v1_ground_truth.json
│   └── test/                       # 25 test datasheets
│       ├── TI_LM358_v1.pdf
│       └── ...
├── configs/
│   ├── default.yaml                # Canonical units, sanity ranges, thresholds
│   └── air_gapped.yaml             # Offline-specific settings
├── eval/
│   ├── evaluate.py                 # Compare output vs ground truth
│   ├── metrics.py                  # Precision/recall/F1 per phase
│   └── reports/                    # Results storage
├── docker/
│   ├── Dockerfile                  # Air-gapped image with baked weights
│   └── requirements-offline.txt    # No cloud deps
├── pyproject.toml                  # ⭐ Single source for dependencies, version
├── README.md                       # Project onboarding
├── DEVELOPMENT.md                  # This document + setup instructions
└── .gitignore                      # Weights, large PDFs, temp files
```

**Key principle:** Every concept lives in exactly **one place**. No copy-pasting schemas, configs, or utility functions across files.

---

## 2. Code Style & Naming (Communication)

### Why It Matters
**Analogy:** If you label a box "miscellaneous," no one knows what's inside. If you label it "Phase 1 table crops," it's clear.

### Python Standards (PEP 8 + Extensions)

#### 2.1 File & Function Names
```python
# ✅ GOOD: Clear, descriptive, lowercase with underscores
def extract_electrical_parameters(grid_matrix: list[list[str]]) -> list[ElectricalParameter]:
    """Extract electrical characteristics from a structured grid.
    
    Args:
        grid_matrix: 2D list of cell texts from Phase 2 TSR.
        
    Returns:
        List of parsed ElectricalParameter objects with confidence scores.
        
    Raises:
        ValueError: If grid structure is invalid.
    """

# ❌ BAD: Vague, non-descriptive
def extract(grid):
    return [ElectricalParameter(...) for ... in grid]

# ❌ BAD: SCREAMING_CASE for variables (reserved for constants)
MIN_VOLTAGE = 1.5  # OK (constant)
min_voltage = 1.5  # OK (variable)
MIN_VOLTAGE_VALUE = 1.5  # WRONG (looks like constant but isn't)
```

#### 2.2 Class & Type Hints (Your Safety Net)
```python
# ✅ GOOD: Type hints make errors obvious at dev time, not runtime
from typing import Optional, Literal
from pydantic import BaseModel

class ExtractedValue(BaseModel):
    raw_text: str                    # What OCR/VLM saw
    value: float                     # Normalized numeric
    unit: str                        # Canonical unit ("V", "mA", etc.)
    confidence: float                # 0.0–1.0
    source: Literal["vector_path_A", "vlm_path_B"]  # Explicit options
    footnote: Optional[str] = None   # May not exist

# Later, when you use it:
extracted = ExtractedValue(raw_text="3.3V", value=3.3, unit="V", confidence=0.95, source="vector_path_A")
print(extracted.value)  # IDE auto-completes, type checker catches mistakes

# ❌ BAD: No type hints = silent failures
def extract_value(data):
    return data["value"]  # What if "value" key doesn't exist? Crash at runtime.
```

#### 2.3 Docstrings (Documentation as Code)

Every function needs a **docstring** describing:
- **What** it does (1 sentence)
- **Args** (input types + meaning)
- **Returns** (type + what it contains)
- **Raises** (errors it throws + when)
- **Example** (optional, but highly encouraged for complex logic)

```python
def normalize_unit(raw_value: str, raw_unit: str, param_type: str) -> tuple[float, str]:
    """Convert any unit to the canonical form for a parameter type.
    
    Example:
        >>> normalize_unit("3300", "mV", "voltage")
        (3.3, "V")
        >>> normalize_unit("0.5", "A", "current")
        (500.0, "mA")
    
    Args:
        raw_value: Numeric string from datasheet (e.g., "3300").
        raw_unit: Unit as written (e.g., "mV", "A", "kΩ").
        param_type: Parameter category (e.g., "voltage", "current", "resistance").
            Must be key in CANONICAL_UNITS dict.
    
    Returns:
        Tuple of (normalized_value, canonical_unit).
        Example: (3.3, "V")
    
    Raises:
        ValueError: If raw_unit is not recognized or param_type is unknown.
        ValueError: If conversion would result in an unphysical value (e.g., negative voltage).
        
    Notes:
        - Handles common OCR errors: 'u' → 'µ', 'k' → 'K'
        - Always returns positive values for positive-polarity parameters
    """
```

---

## 3. Configuration Management (Single Source of Truth)

### Why It Matters
**Analogy:** Imagine if each worker on a construction site used different measurements for "a meter." Chaos. One config file means everyone uses the same ruler.

### `config.py` Structure
```python
# src/config.py
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

@dataclass
class CanonicalUnits:
    """Enforce single standard for all unit conversions."""
    voltage: str = "V"
    current: str = "mA"
    resistance: str = "Ω"
    capacitance: str = "pF"
    frequency: str = "MHz"
    temperature: str = "°C"
    time: str = "ns"

@dataclass
class SanityRanges:
    """Physical plausibility bounds for validation (Phase 4)."""
    # (param_name_pattern, unit_type, min_safe, max_safe)
    ranges: Dict[str, Tuple[str, float, float]] = None
    
    def __post_init__(self):
        if self.ranges is None:
            self.ranges = {
                "V_CC": ("voltage", 0.5, 40.0),        # Supply: 0.5V–40V
                "V_GND": ("voltage", -0.5, 0.5),       # Ground ref
                "I_CC": ("current", 0.001, 5000.0),    # Supply current: 1µA–5A
                "T_J": ("temperature", -55.0, 175.0),  # Junction: -55°C–175°C
            }

@dataclass
class ConfidenceThresholds:
    """When to flag data for human review."""
    block_extraction: float = 0.70   # Phase 2–3: block if below this
    warn_downstream: float = 0.85    # Phase 4: flag for review
    require_approval: float = 0.60   # Critical params need human OK

@dataclass
class ModelConfig:
    """Air-gapped model paths and inference settings."""
    dla_model_path: Path = Path("models/yolov8_doclaynets.pt")
    qwen2_vl_path: Path = Path("models/Qwen2-VL-7B-Instruct")
    local_llm_path: Path = Path("models/Qwen2.5-7B-Instruct")
    device: str = "cuda"  # or "cpu"
    batch_size: int = 4

@dataclass
class Config:
    """Root configuration object."""
    canonical_units: CanonicalUnits
    sanity_ranges: SanityRanges
    thresholds: ConfidenceThresholds
    models: ModelConfig
    phase1_output_dir: Path = Path("output/phase1")
    phase2_output_dir: Path = Path("output/phase2")
    # ... etc

# Usage everywhere in your code:
from src.config import Config
config = Config(...)
print(config.canonical_units.voltage)  # "V"
```

### YAML Config File (Human-readable)
```yaml
# configs/default.yaml
canonical_units:
  voltage: V
  current: mA
  resistance: Ω
  capacitance: pF

sanity_ranges:
  V_CC:
    type: voltage
    min: 0.5
    max: 40.0
  I_CC:
    type: current
    min: 0.001
    max: 5000.0

confidence_thresholds:
  block_extraction: 0.70
  warn_downstream: 0.85
  require_approval: 0.60

models:
  dla_model_path: models/yolov8_doclaynets.pt
  qwen2_vl_path: models/Qwen2-VL-7B-Instruct
  device: cuda
```

**Load it once at startup:**
```python
# src/config.py (continued)
import yaml

def load_config(config_path: str = "configs/default.yaml") -> Config:
    """Load config from YAML file once at program start."""
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return Config(**data)

# In your main pipeline
if __name__ == "__main__":
    config = load_config("configs/default.yaml")
    result = pipeline.run(config)
```

---

## 4. Schemas: Single Point of Truth (Pydantic)

### Why It Matters
**Analogy:** If electricians, plumbers, and carpenters all have different ideas of "which pipes go where," the house breaks. One blueprint (schema) prevents conflicts.

### `schemas.py` Organization
```python
# src/schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from enum import Enum

# ===== PHASE 1 OUTPUT =====
class FootnoteLink(BaseModel):
    """Superscript marker → footnote text mapping."""
    marker: str                    # "(1)", "(2)", "*"
    text: str                      # "Guaranteed by design. Not tested..."
    page_number: int               # For debugging

class Phase1Output(BaseModel):
    """Phase 1 DLA → Phase 2 input."""
    pdf_path: str
    tables: list[bytes]            # Cropped table images (PNG bytes)
    footnotes: list[FootnoteLink]  # Extracted footnotes
    section_type: Literal["electrical_characteristics", "absolute_maximum_ratings", "timing", "other"]

# ===== PHASE 2 OUTPUT =====
class GridMatrix(BaseModel):
    """Structured grid with confidence."""
    rows: list[list[str]]          # 2D cell text
    confidence: float              # Phase 2 scorer result
    source: Literal["vector_path_A", "vlm_path_B"]

class Phase2Output(BaseModel):
    """Phase 2 TSR → Phase 3 input."""
    grids: list[GridMatrix]

# ===== PHASE 3 INPUT/OUTPUT =====
class ExtractedValue(BaseModel):
    """Single measurement: raw text → normalized value."""
    raw_text: str                  # What OCR/VLM saw: "3.3V", "0.5A"
    value: float                   # Normalized: 3.3, 500.0
    unit: str                      # Canonical: "V", "mA"
    confidence: float              # Inherited from Phase 2: 0.0–1.0
    source: Literal["vector_path_A", "vlm_path_B"]
    footnote: Optional[FootnoteLink] = None
    
    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        """Ensure confidence is [0.0, 1.0]."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

class ElectricalParameter(BaseModel):
    """Electrical characteristic: V_CC, I_CC, etc."""
    name: str                      # "V_CC", "I_CC"
    parameter_type: str            # "voltage", "current", "threshold"
    min_value: Optional[ExtractedValue] = None
    typ_value: Optional[ExtractedValue] = None
    max_value: Optional[ExtractedValue] = None
    conditions: Optional[str] = None  # "T_A = 25°C"

class PinDefinition(BaseModel):
    """Pinout entry: pin number → electrical net."""
    pin_number: str                # "1", "A14", "GND"
    pin_name: str                  # Raw: "V_CC", "DATA_OUT"
    pin_type: Literal["power", "ground", "I/O", "analog", "NC"]
    alternate_functions: list[str] = []
    description: Optional[str] = None

class AbsoluteMaximumRating(BaseModel):
    """Abs-max constraint: do not exceed."""
    name: str                      # "V_CC", "T_J"
    max_value: ExtractedValue
    conditions: Optional[str] = None

class DatasheetSection(BaseModel):
    """Logical grouping of related tables."""
    section_type: Literal["electrical_characteristics", "absolute_maximum_ratings", "pinout", "timing", "other"]
    page_range: tuple[int, int]
    parameters: list[ElectricalParameter] = []
    pins: list[PinDefinition] = []
    abs_max: list[AbsoluteMaximumRating] = []

class ComponentDatasheet(BaseModel):
    """Complete extracted datasheet → Phase 4 input."""
    component_id: str              # "TI_OPA2134"
    manufacturer: str              # "Texas Instruments"
    package: Optional[str] = None  # "DIP-8", "SOIC-14"
    sections: list[DatasheetSection]
    pins: list[PinDefinition]      # Flattened for convenience
    validation: Optional[dict] = None  # Filled by Phase 4

# ===== PHASE 4 OUTPUT =====
class ValidationError(BaseModel):
    """Critical issues that block use."""
    level: Literal["CRITICAL", "WARNING"]
    param_name: str
    message: str
    remediation: Optional[str] = None

class ValidationResult(BaseModel):
    """Phase 4 verdict."""
    component_id: str
    passed: bool
    errors: list[ValidationError] = []
    review_required: bool          # Any confidence < threshold?
    confidence_score: float        # Aggregate confidence
    timestamp: str                 # ISO 8601 datetime

# ===== ROOT OUTPUT =====
class PipelineOutput(BaseModel):
    """Final artifact: valid JSON for downstream KiCad MCP."""
    datasheet: ComponentDatasheet
    validation: ValidationResult
    
    def to_json_file(self, path: str):
        """Serialize to disk."""
        import json
        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)
```

**Why all in one file?** Single source of truth. If you need to change how `ExtractedValue` works, you change it once—every module using it automatically gets the update.

---

## 5. Testing (Your Safety Net)

### Why It Matters
**Analogy:** A parachute is free insurance. Before you jump, test it.

### Test Structure
```
tests/
├── unit/
│   ├── test_unit_normalizer.py     # Test unit conversion
│   ├── test_confidence_scorer.py    # Test Phase 2 logic
│   └── test_rule_engine.py          # Test Phase 4 validation
├── integration/
│   └── test_end_to_end.py           # Run all 4 phases on golden corpus
└── fixtures/
    ├── sample_grid.py              # Reusable test data
    └── golden_datasheets.py        # Load ground truth JSON
```

### Example Unit Test
```python
# tests/unit/test_unit_normalizer.py
import pytest
from src.phase3_extract.unit_normalizer import normalize_unit

class TestNormalizeUnit:
    """Test unit conversion to canonical forms."""
    
    def test_voltage_millivolts_to_volts(self):
        """Convert 3300 mV → 3.3 V."""
        value, unit = normalize_unit("3300", "mV", "voltage")
        assert value == 3.3
        assert unit == "V"
    
    def test_current_amps_to_milliamps(self):
        """Convert 0.5 A → 500 mA."""
        value, unit = normalize_unit("0.5", "A", "current")
        assert value == 500.0
        assert unit == "mA"
    
    def test_resistance_kilohms_to_ohms(self):
        """Convert 1.5 kΩ → 1500 Ω."""
        value, unit = normalize_unit("1.5", "kΩ", "resistance")
        assert value == 1500.0
        assert unit == "Ω"
    
    def test_invalid_unit_raises_error(self):
        """Reject unknown units."""
        with pytest.raises(ValueError, match="Unrecognized unit"):
            normalize_unit("3.3", "XYZ", "voltage")
    
    def test_ocr_error_mu_to_micro(self):
        """Handle OCR misread: 'u' → 'µ'."""
        value, unit = normalize_unit("100", "uA", "current")
        assert value == 0.1  # 100 µA → 0.1 mA
        assert unit == "mA"
```

### Integration Test
```python
# tests/integration/test_end_to_end.py
import pytest
from pathlib import Path
from src.pipeline import run_full_pipeline
from src.config import load_config
import json

@pytest.fixture
def golden_corpus():
    """Load golden datasheets for testing."""
    return {
        "TI_OPA2134": {
            "pdf": Path("corpus/golden/TI_OPA2134_v1.pdf"),
            "ground_truth": Path("corpus/golden/TI_OPA2134_v1_ground_truth.json")
        }
    }

def test_end_to_end_golden_datasheet(golden_corpus):
    """Run full pipeline on golden PDF, compare to ground truth."""
    config = load_config()
    
    # Run pipeline
    result = run_full_pipeline(
        golden_corpus["TI_OPA2134"]["pdf"],
        config
    )
    
    # Load ground truth
    with open(golden_corpus["TI_OPA2134"]["ground_truth"]) as f:
        ground_truth = json.load(f)
    
    # Compare key fields
    assert result.datasheet.component_id == ground_truth["component_id"]
    assert len(result.datasheet.pins) == len(ground_truth["pins"])
    assert result.validation.passed == True
```

### Run Tests Locally
```bash
# Install pytest
pip install pytest pytest-cov

# Run all tests
pytest tests/

# Run with coverage report
pytest tests/ --cov=src --cov-report=html

# Run only unit tests
pytest tests/unit/

# Run specific test
pytest tests/unit/test_unit_normalizer.py::TestNormalizeUnit::test_voltage_millivolts_to_volts
```

---

## 6. Logging (Debugging & Monitoring)

### Why It Matters
**Analogy:** A flight recorder on an airplane. If something crashes, you know why.

### Centralized Logging Setup
```python
# src/logging_config.py
import logging
from pathlib import Path

def setup_logging(log_file: str = "output/pipeline.log", level=logging.INFO):
    """Configure logging once at program start."""
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler (all messages)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console handler (important messages)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# Usage in any module:
import logging
logger = logging.getLogger(__name__)

def my_function():
    logger.debug("Starting extraction...")
    logger.info(f"Processed {100} cells")
    logger.warning(f"Confidence below threshold: {0.65}")
    logger.error(f"Failed to normalize unit: {unit}")
```

**Output:**
```
2024-11-23 14:32:15 - src.phase3_extract - INFO - Processed 100 cells
2024-11-23 14:32:16 - src.phase4_validate - WARNING - Confidence below threshold: 0.65
2024-11-23 14:32:17 - src.phase4_validate - ERROR - Failed to normalize unit: XYZ
```

---

## 7. Error Handling (Graceful Failure)

### Why It Matters
**Analogy:** A car's crumple zones absorb crash energy instead of crashing the whole frame. Handle errors instead of letting the program crash.

### Pattern: Fail Loud, Fail Clear
```python
# ❌ BAD: Silent failure
def extract_value(row):
    return float(row[2])  # What if row has <3 elements? Crash. Silent.

# ✅ GOOD: Explicit error with context
def extract_value(row: list[str], row_num: int) -> float:
    """Extract numeric value from row, fail with context."""
    try:
        if len(row) < 3:
            raise ValueError(f"Row has {len(row)} columns, expected ≥3")
        value = float(row[2])
        if value < 0:
            logger.warning(f"Row {row_num}: negative value {value}, possible OCR error")
        return value
    except ValueError as e:
        logger.error(f"Row {row_num} extraction failed: {e}")
        raise  # Re-raise so upstream knows this row failed

# Usage:
try:
    result = extract_value(row, row_num=5)
except ValueError:
    logger.error("Skipping row due to extraction failure")
    continue  # Move to next row
```

### Custom Exception Classes
```python
# src/exceptions.py
class DatasheetParsingError(Exception):
    """Base exception for all parsing failures."""
    pass

class Phase1LayoutError(DatasheetParsingError):
    """Phase 1 (DLA) failure."""
    pass

class Phase2StructureError(DatasheetParsingError):
    """Phase 2 (TSR) failure."""
    pass

class Phase3ExtractionError(DatasheetParsingError):
    """Phase 3 semantic extraction failure."""
    pass

class Phase4ValidationError(DatasheetParsingError):
    """Phase 4 validation failure."""
    pass

# Usage:
from src.exceptions import Phase2StructureError

def recognize_table_structure(image: bytes) -> GridMatrix:
    try:
        grid = run_table_structure_recognition(image)
        if grid.confidence < 0.5:
            raise Phase2StructureError(
                f"TSR confidence {grid.confidence} below threshold 0.5"
            )
        return grid
    except Phase2StructureError:
        raise  # Re-raise with context
    except Exception as e:
        raise Phase2StructureError(f"Unexpected TSR failure: {e}") from e
```

---

## 8. Performance & Efficiency (Speed Without Sacrifice)

### Why It Matters
**Analogy:** A fast car is useless if it crashes. Speed + correctness = good engineering.

### 8.1 Avoid Redundant Work
```python
# ❌ BAD: Recalculate the same thing multiple times
def process_table(grid: list[list[str]]):
    for row in grid:
        unit_type = infer_unit_type(row)  # Called every iteration
        # ...

# ✅ GOOD: Calculate once, reuse
unit_type = infer_unit_type(grid[0])  # Calculate once
for row in grid:
    # Use unit_type directly
    # ...
```

### 8.2 Batch Processing (Where Applicable)
```python
# For Phase 1 (Rasterization): Process PDFs in batches
from concurrent.futures import ThreadPoolExecutor

def rasterize_batch(pdf_paths: list[str], batch_size: int = 4):
    """Rasterize multiple PDFs in parallel."""
    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        results = executor.map(rasterize_pdf, pdf_paths)
    return list(results)
```

### 8.3 Model Inference: Load Once, Use Many Times
```python
# ❌ BAD: Load model for each datasheet
class Phase1DLA:
    def process_pdf(self, pdf_path):
        model = load_model("models/yolov8.pt")  # SLOW!
        return detect_tables(model, pdf_path)

# ✅ GOOD: Load model once at startup
class Phase1DLA:
    def __init__(self, model_path: str):
        self.model = load_model(model_path)  # Load once
    
    def process_pdf(self, pdf_path):
        return detect_tables(self.model, pdf_path)  # Reuse

# In main:
dla = Phase1DLA("models/yolov8.pt")
for pdf in pdf_list:
    dla.process_pdf(pdf)  # Fast: model already in memory
```

### 8.4 Profiling to Find Bottlenecks
```python
# Use Python's built-in profiler
import cProfile
import pstats

def profile_pipeline():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Run your code
    run_full_pipeline(config)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)  # Print top 20 slowest functions

# Run: python -c "from src import profile_pipeline; profile_pipeline()"
```

---

## 9. Documentation (Your Future Self Will Thank You)

### 9.1 Code Comments (When & Why, Not What)
```python
# ❌ BAD: Restates the obvious
x = y + 1  # Add 1 to y

# ✅ GOOD: Explains non-obvious logic
# Confidence score inherited from Phase 2 TSR.
# If below threshold, flag for human review in Phase 4.
confidence_score = grid.confidence
if confidence_score < config.thresholds.warn_downstream:
    extraction.review_required = True
```

### 9.2 Module Docstring (Top of Every File)
```python
# src/phase2_tsr/confidence_scorer.py
"""Phase 2: Confidence scoring for dual-path Table Structure Recognition.

This module implements the confidence scorer that evaluates both Path A (vector)
and Path B (VLM) grid matrices and selects the best candidate based on structural
agreement, cell count, and parse success rate.

Classes:
    ConfidenceScorer: Evaluates and scores grid candidates.

Functions:
    pick_best_grid: Main entry point—compares two grids and returns winner.
"""
```

### 9.3 README (Project Onboarding)
```markdown
# P1 Datasheet Parser

## Quick Start

```bash
# Clone and install
git clone https://github.com/drdo/p1-parser.git
cd p1-parser

# Set up environment
python -m venv venv
source venv/bin/activate  # or 'venv\\Scripts\\activate' on Windows
pip install -r requirements.txt

# Download offline models (see models/README.md)
# Run pipeline
python src/pipeline.py --pdf corpus/test/TI_OPA2134.pdf --output output/

# Run tests
pytest tests/
```

## Architecture

- **Phase 1 (DLA):** Document layout analysis → table crops
- **Phase 2 (TSR):** Dual-path structure recognition
- **Phase 3:** Semantic extraction + unit normalization
- **Phase 4:** Physics validation + rule engine

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed coding standards.
```

---

## 10. Git & Version Control (Tracking Changes)

### 10.1 Meaningful Commit Messages
```bash
# ❌ BAD
git commit -m "fixed stuff"

# ✅ GOOD
git commit -m "Phase 3: Add unit normalization for µA→mA conversion

- Implements normalize_unit() with support for common OCR errors (u vs µ)
- Adds unit conversion tests (test_unit_normalizer.py)
- References issue #42"
```

### 10.2 .gitignore (Never Commit These)
```
# .gitignore
*.pyc
__pycache__/
.venv/
venv/

# Large model weights (too big for git)
models/*.pt
models/*.onnx
models/Qwen2-VL-7B-Instruct/

# Data: test PDFs and corpus
corpus/
output/

# IDE
.vscode/
.idea/
*.swp

# Logs
*.log
logs/
```

---

## 11. Quick Checklist Before Committing Code

Before you `git push`, verify:

- [ ] **Naming:** Functions/variables lowercase_with_underscores, Classes PascalCase
- [ ] **Type hints:** All function parameters and returns have types
- [ ] **Docstrings:** Every function/class has a docstring (what, args, returns, raises)
- [ ] **Tests:** New code has unit tests, all tests pass (`pytest tests/`)
- [ ] **Config:** No hardcoded values—use `config.py` or YAML
- [ ] **Schemas:** All data models in `schemas.py`, not scattered
- [ ] **Logging:** Critical paths have `logger.info()` or `logger.warning()`
- [ ] **Error handling:** Try/except with specific error types, not bare `except:`
- [ ] **No secrets:** No API keys, passwords, or personal data in code
- [ ] **Linting:** Code follows PEP 8 (use `black` auto-formatter or `pylint`)

---

## 12. Tools to Enforce Standards

### Auto-Formatter (Consistency)
```bash
pip install black
black src/  # Automatically formats all Python files
```

### Linter (Catches Errors)
```bash
pip install pylint
pylint src/  # Reports style issues, potential bugs
```

### Type Checker (Finds Type Errors Early)
```bash
pip install mypy
mypy src/  # Checks type consistency without running code
```

### All Together
```bash
# Add to your Makefile or run before commit:
black src/ && pylint src/ && mypy src/ && pytest tests/
```

---

## Summary: The Three Pillars

| Pillar | Why | How |
|--------|-----|-----|
| **Structure** | Clear file layout = easy navigation | One concept = one place (schemas.py, config.py) |
| **Clarity** | Future you is a stranger | Type hints, docstrings, meaningful names |
| **Safety** | Bugs hide in shadows | Unit tests, logging, explicit error handling |

---

**Remember:** Good code is not clever code. It's code that:
1. ✅ **Works** (passes tests)
2. ✅ **Lasts** (readable in 6 months)
3. ✅ **Fails gracefully** (errors are clear, not silent)

---

## Next Steps

1. Create the project directory structure above
2. Set up `config.py` and `schemas.py` first
3. Write unit tests *before* implementing logic (Test-Driven Development)
4. Establish a CI/CD pipeline (GitHub Actions to run tests on every commit)
5. Review code in pull requests before merging

**Good luck! Questions? Re-read the analogy section — coding is just clear communication with your future self.** 🚀
