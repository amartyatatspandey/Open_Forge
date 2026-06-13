# P1 Parser: Project Bootstrap Guide
**Follow these steps to set up a clean, maintainable codebase from scratch.**

---

## Step 1: Create Directory Structure

```bash
# Navigate to your workspace
cd /path/to/workspace

# Create project root
mkdir p1-parser
cd p1-parser

# Create all directories
mkdir -p src/{phase1_dla,phase2_tsr,phase3_extract,phase4_validate,utils}
mkdir -p tests/{unit,integration,fixtures}
mkdir -p models configs corpus/{golden,test} eval docker output logs

# Create initial placeholder files
touch src/__init__.py
touch src/phase1_dla/__init__.py
touch src/phase2_tsr/__init__.py
touch src/phase3_extract/__init__.py
touch src/phase4_validate/__init__.py
touch src/utils/__init__.py
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
touch tests/fixtures/__init__.py

# Marker files for large directories
echo "# Downloaded model weights go here (not in git)" > models/.gitkeep
echo "# Test PDFs and ground truth JSON" > corpus/.gitkeep
echo "# Generated outputs" > output/.gitkeep
echo "# Logs go here" > logs/.gitkeep
```

**Result:** Clean directory structure ready for code.

---

## Step 2: Create pyproject.toml (Project Metadata)

This file tells Python (and other tools) what your project is and what it depends on.

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "p1-parser"
version = "0.1.0"
description = "Automated datasheet parsing pipeline for air-gapped defense EDA"
authors = [{name = "Open Forge Team", email = "contributors@openforge.dev"}]
readme = "README.md"
requires-python = ">=3.9"

dependencies = [
    # PDF processing
    "pdf2image>=1.16.0",
    "pdfplumber>=0.9.0",
    "camelot-py>=0.10.1",
    
    # Data validation & structuring
    "pydantic>=2.0.0",
    "instructor>=1.2.0",
    
    # ML/Vision (offline)
    "torch>=2.0.0",
    "torchvision>=0.15.0",
    "ultralytics>=8.0.0",  # YOLOv8
    "transformers>=4.30.0",  # Qwen2-VL, LLMs
    
    # Utilities
    "opencv-python>=4.8.0",
    "numpy>=1.24.0",
    "pillow>=10.0.0",
    "pyyaml>=6.0",
    
    # Development
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "black>=23.0.0",
    "pylint>=2.17.0",
    "mypy>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "black>=23.0.0",
    "pylint>=2.17.0",
    "mypy>=1.0.0",
    "ipython>=8.0.0",  # Interactive testing
]

[project.urls]
Repository = "https://github.com/amartyatatspandey/Open_Forge"
Documentation = "https://github.com/amartyatatspandey/Open_Forge/blob/main/README.md"

[tool.black]
line-length = 100
target-version = ["py39", "py310", "py311"]

[tool.pylint.messages_control]
disable = [
    "C0111",  # missing-docstring (we handle this with explicit docs)
    "R0913",  # too-many-arguments (can be necessary)
]

[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short --strict-markers"
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
]
```

**Install dependencies:**
```bash
pip install -e ".[dev]"  # Installs project in editable mode + dev tools
```

---

## Step 3: Create config.py (Single Source of Truth)

This is the first real Python file. **Everything** configuration-related goes here.

```python
# src/config.py
"""Global configuration for P1 datasheet parser.

This module centralizes all settings, thresholds, and constants.
Any part of the pipeline imports from here—never hardcode values elsewhere.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple, Literal
import yaml
import logging

logger = logging.getLogger(__name__)


@dataclass
class CanonicalUnits:
    """Standard units for all electrical parameters.
    
    Every datasheet uses different units (mV vs V, µA vs mA).
    This class ensures outputs always use these canonical forms.
    """
    voltage: str = "V"
    current: str = "mA"
    resistance: str = "Ω"
    capacitance: str = "pF"
    frequency: str = "MHz"
    temperature: str = "°C"
    time: str = "ns"


@dataclass
class SanityRanges:
    """Physical plausibility bounds for electrical parameters.
    
    During Phase 4 validation, any value outside these ranges
    is flagged as suspicious (possible OCR/VLM error).
    
    Format: {param_name_pattern: (unit_type, min_safe, max_safe)}
    """
    ranges: Dict[str, Tuple[str, float, float]] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize with sensible defaults if not provided."""
        if not self.ranges:
            self.ranges = {
                "V_CC": ("voltage", 0.5, 40.0),        # Supply voltage: 0.5V–40V
                "V_GND": ("voltage", -0.5, 0.5),       # Ground reference
                "V_DD": ("voltage", 0.5, 40.0),        # Alternative to V_CC
                "I_CC": ("current", 0.001, 5000.0),    # Supply current: 1µA–5A
                "I_DD": ("current", 0.001, 5000.0),    # Alternative to I_CC
                "T_J": ("temperature", -55.0, 175.0),  # Junction temp: -55°C–175°C
                "T_A": ("temperature", -40.0, 85.0),   # Ambient temp: -40°C–85°C
            }


@dataclass
class ConfidenceThresholds:
    """Thresholds for data quality flags.
    
    Confidence scores inherit from Phase 2 (TSR) and determine
    whether data is passed downstream or flagged for review.
    """
    block_extraction: float = 0.70     # Phase 3: block if below
    warn_downstream: float = 0.85      # Phase 4: flag if below
    require_approval: float = 0.60     # Critical params need OK


@dataclass
class ModelConfig:
    """Paths and settings for offline ML models."""
    # Document Layout Analysis (Phase 1)
    dla_model_path: Path = Path("models/yolov8_doclaynets.pt")
    dla_model_name: str = "yolov8_doclaynets"
    
    # Table Structure Recognition Path B (Phase 2)
    qwen2_vl_path: Path = Path("models/Qwen2-VL-7B-Instruct")
    qwen2_vl_model_name: str = "Qwen2-VL-7B-Instruct"
    
    # Semantic Extraction (Phase 3)
    local_llm_path: Path = Path("models/Qwen2.5-7B-Instruct")
    local_llm_model_name: str = "Qwen2.5-7B-Instruct"
    
    # Inference settings
    device: Literal["cuda", "cpu"] = "cuda"
    torch_dtype: str = "float16"  # "float16" for 24GB VRAM, "float32" for safety
    batch_size: int = 4
    num_workers: int = 4


@dataclass
class PipelineConfig:
    """Paths and settings for pipeline I/O."""
    phase1_output_dir: Path = Path("output/phase1")
    phase2_output_dir: Path = Path("output/phase2")
    phase3_output_dir: Path = Path("output/phase3")
    phase4_output_dir: Path = Path("output/phase4")
    
    log_file: Path = Path("logs/pipeline.log")
    log_level: str = "INFO"
    
    # Rasterization settings (Phase 1)
    pdf_dpi: int = 300  # Higher DPI = better OCR but slower
    pdf_fmt: str = "png"


@dataclass
class Config:
    """Root configuration object.
    
    Instantiate once at startup and pass to all pipeline phases.
    Example:
        config = Config.load("configs/default.yaml")
        result = pipeline.run_full_pipeline(pdf_path, config)
    """
    canonical_units: CanonicalUnits = field(default_factory=CanonicalUnits)
    sanity_ranges: SanityRanges = field(default_factory=SanityRanges)
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    models: ModelConfig = field(default_factory=ModelConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    
    @classmethod
    def load(cls, config_path: str = "configs/default.yaml") -> "Config":
        """Load configuration from YAML file.
        
        Args:
            config_path: Path to YAML config file.
            
        Returns:
            Initialized Config object.
            
        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If YAML is malformed.
        """
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config not found at {config_path}, using defaults")
            return cls()
        
        try:
            with open(config_file) as f:
                data = yaml.safe_load(f)
            logger.info(f"Loaded config from {config_path}")
            return cls(**data) if data else cls()
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse {config_path}: {e}") from e
    
    def validate(self):
        """Sanity-check configuration values.
        
        Raises:
            ValueError: If any setting is invalid.
        """
        if self.thresholds.block_extraction > self.thresholds.warn_downstream:
            raise ValueError(
                "block_extraction threshold must be <= warn_downstream threshold"
            )
        if self.models.device not in ("cuda", "cpu"):
            raise ValueError(f"Invalid device: {self.models.device}")
        logger.info("Configuration validation passed")


# Singleton pattern: Load config once at module import
_default_config = None

def get_config() -> Config:
    """Get global config object (lazy-load on first use)."""
    global _default_config
    if _default_config is None:
        _default_config = Config.load("configs/default.yaml")
        _default_config.validate()
    return _default_config
```

**Usage everywhere:**
```python
# In any module
from src.config import get_config

config = get_config()
print(config.canonical_units.voltage)  # "V"
print(config.thresholds.warn_downstream)  # 0.85
```

---

## Step 4: Create schemas.py (Data Model Definitions)

All Pydantic models in one place.

```python
# src/schemas.py
"""Data schemas for P1 datasheet parser.

Every piece of data flowing through the pipeline has a schema defined here.
This is the single source of truth for data structure.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime
import json


# ===== PHASE 1 OUTPUT =====

class FootnoteLink(BaseModel):
    """Mapping of superscript marker to footnote text."""
    marker: str  # "(1)", "(2)", "*"
    text: str    # "Guaranteed by design. Not tested in production."
    page_number: int


class Phase1Output(BaseModel):
    """Output from Phase 1: Document Layout Analysis."""
    pdf_path: str
    tables: list[bytes] = Field(default_factory=list)  # PNG bytes
    footnotes: list[FootnoteLink] = Field(default_factory=list)
    section_type: Literal[
        "electrical_characteristics",
        "absolute_maximum_ratings",
        "timing",
        "pinout",
        "other"
    ] = "other"


# ===== PHASE 2 OUTPUT =====

class GridMatrix(BaseModel):
    """Structured grid of cell text with confidence."""
    rows: list[list[str]]  # 2D array of cell content
    num_rows: int  # Convenience field
    num_cols: int  # Convenience field
    confidence: float  # [0.0, 1.0] from TSR scorer
    source: Literal["vector_path_A", "vlm_path_B"]
    
    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be [0, 1], got {v}")
        return v
    
    @field_validator("num_rows", "num_cols", mode="before")
    @classmethod
    def compute_dimensions(cls, v, info):
        """Auto-compute dimensions from rows if not provided."""
        if v is not None:
            return v
        if "rows" in info.data:
            rows = info.data["rows"]
            if "num_rows" in info.field_name:
                return len(rows)
            elif "num_cols" in info.field_name:
                return len(rows[0]) if rows else 0
        return 0


class Phase2Output(BaseModel):
    """Output from Phase 2: Table Structure Recognition."""
    grids: list[GridMatrix]
    num_tables: int = Field(default=0)
    
    def __post_init__(self):
        self.num_tables = len(self.grids)


# ===== PHASE 3 INPUT/OUTPUT =====

class ExtractedValue(BaseModel):
    """Single extracted measurement value."""
    raw_text: str  # "3.3V", "500mA"—what OCR/VLM saw
    value: float   # 3.3, 500.0—normalized number
    unit: str      # "V", "mA"—canonical unit
    confidence: float  # [0.0, 1.0]—inherited from Phase 2
    source: Literal["vector_path_A", "vlm_path_B"]
    footnote: Optional[FootnoteLink] = None
    
    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be [0, 1], got {v}")
        return v


class ElectricalParameter(BaseModel):
    """Electrical characteristic: V_CC, I_CC, V_IL, etc."""
    name: str                              # "V_CC", "I_CC"
    parameter_type: str                    # "voltage", "current", "threshold"
    min_value: Optional[ExtractedValue] = None
    typ_value: Optional[ExtractedValue] = None
    max_value: Optional[ExtractedValue] = None
    conditions: Optional[str] = None       # "T_A = 25°C, V_CC = 3.3V"
    
    def avg_confidence(self) -> float:
        """Average confidence across min/typ/max."""
        values = [v for v in [self.min_value, self.typ_value, self.max_value] if v]
        return sum(v.confidence for v in values) / len(values) if values else 0.0


class PinDefinition(BaseModel):
    """Pinout definition: pin number → electrical properties."""
    pin_number: str  # "1", "A14", "GND"
    pin_name: str    # "V_CC", "DATA_OUT" (raw from datasheet)
    pin_type: Literal["power", "ground", "I/O", "analog", "NC"]
    alternate_functions: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class AbsoluteMaximumRating(BaseModel):
    """Absolute maximum rating constraint."""
    name: str  # "V_CC", "T_J"
    max_value: ExtractedValue
    conditions: Optional[str] = None


class DatasheetSection(BaseModel):
    """Logical group of related data within a datasheet."""
    section_type: Literal[
        "electrical_characteristics",
        "absolute_maximum_ratings",
        "pinout",
        "timing",
        "other"
    ]
    page_range: tuple[int, int]
    parameters: list[ElectricalParameter] = Field(default_factory=list)
    pins: list[PinDefinition] = Field(default_factory=list)
    abs_max: list[AbsoluteMaximumRating] = Field(default_factory=list)


class ComponentDatasheet(BaseModel):
    """Complete extracted datasheet structure (Phase 3 output)."""
    component_id: str  # "TI_OPA2134"
    manufacturer: str  # "Texas Instruments"
    package: Optional[str] = None  # "DIP-8", "SOIC-14"
    sections: list[DatasheetSection] = Field(default_factory=list)
    pins: list[PinDefinition] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


# ===== PHASE 4 OUTPUT =====

class ValidationError(BaseModel):
    """Single validation error or warning."""
    level: Literal["CRITICAL", "WARNING"]
    param_name: str
    message: str
    remediation: Optional[str] = None


class ValidationResult(BaseModel):
    """Phase 4 validation verdict."""
    component_id: str
    passed: bool
    errors: list[ValidationError] = Field(default_factory=list)
    review_required: bool  # Confidence too low?
    confidence_score: float  # Aggregate [0.0, 1.0]
    timestamp: str  # ISO 8601


# ===== ROOT OUTPUT =====

class PipelineOutput(BaseModel):
    """Final deliverable from full pipeline."""
    datasheet: ComponentDatasheet
    validation: ValidationResult
    
    def to_json_file(self, path: str):
        """Serialize to JSON file."""
        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)
    
    @classmethod
    def from_json_file(cls, path: str) -> "PipelineOutput":
        """Deserialize from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)
```

**Test it immediately:**
```python
# In Python REPL
from src.schemas import ExtractedValue

val = ExtractedValue(
    raw_text="3.3V",
    value=3.3,
    unit="V",
    confidence=0.95,
    source="vlm_path_B"
)
print(val)  # Prints full object
```

---

## Step 5: Create logging_config.py (Centralized Logging)

```python
# src/logging_config.py
"""Centralized logging configuration for all modules."""

import logging
import logging.handlers
from pathlib import Path
from src.config import get_config


def setup_logging():
    """Configure logging once at startup.
    
    Logs go to both file and console.
    Call this once in main():
        setup_logging()
    """
    config = get_config()
    
    # Create log directory if needed
    log_dir = config.pipeline.log_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Formatter: timestamp - logger_name - level - message
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler: all messages
    file_handler = logging.handlers.RotatingFileHandler(
        config.pipeline.log_file,
        maxBytes=10_000_000,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console handler: important messages only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.pipeline.log_level))
    console_handler.setFormatter(formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized")


# Get logger in any module:
# import logging
# logger = logging.getLogger(__name__)
# logger.info("message")
```

---

## Step 6: Create .gitignore

```
# .gitignore

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Large model weights (not in git, transferred separately)
models/*.pt
models/*.onnx
models/Qwen2-VL-7B-Instruct/
models/Qwen2.5-7B-Instruct/

# Data (PDFs too large)
corpus/**/*.pdf
corpus/**/*.PDF

# Outputs
output/
logs/
*.log

# Evaluation results
eval/reports/

# Temporary
*.tmp
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/
```

---

## Step 7: Create configs/default.yaml

```yaml
# configs/default.yaml

canonical_units:
  voltage: V
  current: mA
  resistance: Ω
  capacitance: pF
  frequency: MHz
  temperature: °C
  time: ns

sanity_ranges:
  V_CC:
    type: voltage
    min: 0.5
    max: 40.0
  I_CC:
    type: current
    min: 0.001
    max: 5000.0
  T_J:
    type: temperature
    min: -55.0
    max: 175.0

confidence_thresholds:
  block_extraction: 0.70
  warn_downstream: 0.85
  require_approval: 0.60

models:
  dla_model_path: models/yolov8_doclaynets.pt
  qwen2_vl_path: models/Qwen2-VL-7B-Instruct
  local_llm_path: models/Qwen2.5-7B-Instruct
  device: cuda
  batch_size: 4

pipeline:
  phase1_output_dir: output/phase1
  phase2_output_dir: output/phase2
  phase3_output_dir: output/phase3
  phase4_output_dir: output/phase4
  log_file: logs/pipeline.log
  log_level: INFO
  pdf_dpi: 300
```

---

## Step 8: Create First Unit Test

```python
# tests/unit/test_schemas.py
"""Test Pydantic schemas."""

import pytest
from src.schemas import ExtractedValue, ElectricalParameter


class TestExtractedValue:
    """Test ExtractedValue schema validation."""
    
    def test_create_valid_value(self):
        """Create a valid ExtractedValue."""
        val = ExtractedValue(
            raw_text="3.3V",
            value=3.3,
            unit="V",
            confidence=0.95,
            source="vlm_path_B"
        )
        assert val.value == 3.3
        assert val.confidence == 0.95
    
    def test_confidence_out_of_range_fails(self):
        """Confidence must be [0.0, 1.0]."""
        with pytest.raises(ValueError, match="confidence must be"):
            ExtractedValue(
                raw_text="3.3V",
                value=3.3,
                unit="V",
                confidence=1.5,  # Invalid!
                source="vlm_path_B"
            )


class TestElectricalParameter:
    """Test ElectricalParameter schema."""
    
    def test_avg_confidence_with_all_values(self):
        """Average confidence across min/typ/max."""
        param = ElectricalParameter(
            name="V_CC",
            parameter_type="voltage",
            min_value=ExtractedValue("1.5V", 1.5, "V", 0.90, "vector_path_A"),
            typ_value=ExtractedValue("3.3V", 3.3, "V", 0.95, "vector_path_A"),
            max_value=ExtractedValue("5.5V", 5.5, "V", 0.92, "vector_path_A"),
        )
        assert param.avg_confidence() == pytest.approx(0.9233, rel=1e-3)
```

**Run test:**
```bash
pytest tests/unit/test_schemas.py -v
```

---

## Step 9: Initialize Git Repository

```bash
# Initialize git
git init

# Create initial commit
git add .
git commit -m "Initial commit: Project structure, config, schemas, logging

- Create project directory structure
- Add pyproject.toml with dependencies
- Implement Config class with YAML loading
- Define all Pydantic schemas (phases 1-4)
- Setup centralized logging
- Add first unit test (schema validation)"

# (Optional) Add remote
git remote add origin https://github.com/amartyatatspandey/Open_Forge.git
```

---

## Step 10: Create README.md (Project Onboarding)

```markdown
# P1 Datasheet Parser
**Automated datasheet parsing for air-gapped PCB design systems.**

## Quick Start

### Prerequisites
- Python 3.9+
- CUDA 11.8+ (for GPU inference) or CPU-only mode

### Installation

```bash
# Clone and navigate
git clone https://github.com/amartyatatspandey/Open_Forge.git
cd p1-parser

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or 'venv\\Scripts\\activate' on Windows

# Install dependencies
pip install -e ".[dev]"

# Set up offline models (see models/README.md)
# Download and extract model weights to models/ directory
```

### First Run

```bash
# Test on sample datasheet
python src/pipeline.py \
  --pdf corpus/test/TI_OPA2134.pdf \
  --output output/

# View result
cat output/TI_OPA2134.json | jq .
```

### Run Tests

```bash
# All tests
pytest tests/

# Only unit tests
pytest tests/unit/

# With coverage
pytest tests/ --cov=src
```

## Architecture

**Phase 1 (DLA):** Extract table crops and footnotes from PDF
**Phase 2 (TSR):** Recognize table structure (rows, columns, merged cells)
**Phase 3 (Extraction):** Parse semantics into normalized JSON
**Phase 4 (Validation):** Check electrical plausibility, flag anomalies

## Configuration

Edit `configs/default.yaml` for:
- Canonical units
- Confidence thresholds
- Model paths
- Output directories

## Project Structure

```
src/
├── config.py          ← All settings (load once)
├── schemas.py         ← All data models
├── pipeline.py        ← Orchestrator
└── phase{1,2,3,4}/    ← Phase implementations

tests/
├── unit/              ← Fast isolated tests
└── integration/       ← Full pipeline tests

corpus/
├── golden/            ← Hand-verified datasheets
└── test/              ← Test datasheets
```

## Contributing

- Format: `black src/`
- Lint: `pylint src/`
- Type check: `mypy src/`
- Test: `pytest tests/`

Before committing, run all four.

## Defense-Grade Quality Standards

This codebase follows:
- Type hints on all functions
- Comprehensive docstrings
- Unit tests for every module
- Centralized configuration
- Explicit error handling
- Audit logging

See [CODING_STANDARDS_P1.md](CODING_STANDARDS_P1.md) for details.
```

---

## Verification: Check Everything Works

```bash
# Verify directory structure
find p1-parser -type f -name "*.py" | head -20

# Verify imports work
python -c "from src.config import Config; from src.schemas import ExtractedValue; print('✅ Imports OK')"

# Run tests
pytest tests/ -v

# Check formatting
black --check src/
```

**If all pass, you're ready to start coding Phase implementations!** 🚀

---

## Next: Write Phase 1 Code

Once this foundation is solid, implement Phase 1:

```python
# src/phase1_dla/rasterizer.py
"""Phase 1: Rasterize PDF to images."""

from src.schemas import Phase1Output
from src.config import get_config
import logging

logger = logging.getLogger(__name__)

def rasterize_pdf(pdf_path: str) -> list[bytes]:
    """Convert PDF pages to PNG bytes.
    
    Args:
        pdf_path: Path to PDF file.
        
    Returns:
        List of PNG bytes, one per page.
    """
    config = get_config()
    logger.info(f"Rasterizing {pdf_path} at {config.pipeline.pdf_dpi} DPI")
    # ... implementation
```

Always follow the patterns in `QUICK_REFERENCE_PATTERNS.md`.

---

**Congratulations!** You now have a clean, maintainable, professional codebase foundation. Every future phase builds on this.
