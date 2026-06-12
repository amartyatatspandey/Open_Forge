# CURSOR_PROMPT_PHASE3_EXTRACTION.md

## Context

You are implementing **Phase 3: Constrained Semantic Extraction** for the DRDO P1 Datasheet Parser. Your goal is to transform structured grids (from Phase 2) into validated, normalized, machine-readable electrical component data.

**Authority documents:**
- `documents/p1_assessment_filled.md` — full spec (§2b schema, §3 unit normalization, §3 table-type prompts)
- `documents/PROJECT_CONTEXT.md` — project status
- `documents/CODING_STANDARDS_P1.md` — coding standards
- `documents/QUICK_REFERENCE_PATTERNS.md` — code patterns

**Current status:** Phase 1 ✅ complete (5/5 PASS), Phase 2 ✅ complete (73 tests pass, modules done). Phase 3 scaffolding ready.

**Task:** Write Phase 3 code. **No GPU needed.** All tests pass locally using mock Phase 2 outputs.

---

## Phase 3 Architecture

### Input → Output

```
Phase 2 Output (Phase2Output)
  • grids: list[GridMatrix]
  • metadata: dict (pdf_path, component_id, footnote_map)
  
         │ (GridMatrix for each section type)
         ▼
         
 Section-Aware Extraction
 ┌─────────────────────────────────────────────────────┐
 │ For electrical_characteristics grid:                │
 │  → extract_electrical_parameters(grid)              │
 │  → list[ElectricalParameter]                        │
 │                                                     │
 │ For pinout grid:                                    │
 │  → extract_pins(grid)                               │
 │  → list[PinDefinition]                              │
 │                                                     │
 │ For absolute_maximum_ratings grid:                  │
 │  → extract_absolute_max_ratings(grid)               │
 │  → list[AbsoluteMaximumRating]                      │
 │                                                     │
 │ Across all grids:                                   │
 │  → resolve_footnotes(grids, footnote_map)           │
 │  → Attach footnote text to ExtractedValue objects   │
 └─────────────────────────────────────────────────────┘
         │
         ▼
 Unit Normalizer
  (mV → V, µA → mA, kΩ → Ω, etc.)
         │
         ▼
 Instructor + Qwen2.5-7B
  (structured JSON extraction with Pydantic)
         │
         ▼
 Validation Layer
  (check required fields, detect malformed data)
         │
         ▼
Phase 3 Output (ComponentDatasheet)
  • component_id: str
  • manufacturer: str
  • package: str (optional)
  • sections: list[DatasheetSection]
  • pins: list[PinDefinition] (flattened)
  • validation: ValidationResult
```

### Key Components

1. **ExtractedValue** (already in schema, you use it)
   ```python
   class ExtractedValue(BaseModel):
       raw_text: str           # Original cell text
       value: float            # Normalized numeric
       unit: str               # Canonical unit
       confidence: float       # 0.0–1.0
       source: str             # "vector_path_A", "vlm_path_B", "mock"
       footnote: Optional[str] # Linked footnote text
   ```

2. **ElectricalParameter** (already in schema, you extract these)
   ```python
   class ElectricalParameter(BaseModel):
       name: str
       parameter_type: str              # infer from name
       min_value: Optional[ExtractedValue]
       typ_value: Optional[ExtractedValue]
       max_value: Optional[ExtractedValue]
       conditions: Optional[str]
   ```

3. **PinDefinition** (already in schema, you extract these)
   ```python
   class PinDefinition(BaseModel):
       pin_number: str
       pin_name: str
       pin_type: Literal[...]
       alternate_functions: list[str]
       description: Optional[str]
   ```

4. **AbsoluteMaximumRating** (already in schema, you extract these)
   ```python
   class AbsoluteMaximumRating(BaseModel):
       name: str
       max_value: ExtractedValue
       conditions: Optional[str]
   ```

---

## Implementation Order

### 0. Setup: Import mock data in tests

```python
# tests/unit/test_phase3_*.py (all Phase 3 tests)

from tests.fixtures.phase2_mock_outputs import (
    all_golden_phase2_outputs,
    mock_sn74_phase2_output,
    mock_tlv7021_phase2_output,
    # etc.
)

# Mock Phase 2 output for testing
phase2_out = mock_tlv7021_phase2_output()
# phase2_out.grids contains GridMatrix objects
# phase2_out.metadata contains pdf_path, component_id, footnote_map
```

---

### 1. `src/phase3_extract/unit_normalizer.py`

**Why first:** Pure logic, no ML, no dependencies, TDD-friendly.

**Functionality:**
```python
CANONICAL_UNITS = {
    "voltage": "V",
    "current": "mA",
    "resistance": "Ω",
    "capacitance": "pF",
    "inductance": "nH",
    "frequency": "MHz",
    "temperature": "°C",
    "time": "ns",
    "power": "mW",
}

# All unit variants → (multiplier, canonical_unit)
UNIT_CONVERSION_TABLE = {
    # Voltage
    "uv": (1e-6, "V"), "µv": (1e-6, "V"),
    "mv": (1e-3, "V"), "v": (1.0, "V"), "kv": (1e3, "V"),
    # Current
    "ua": (1e-3, "mA"), "µa": (1e-3, "mA"),
    "ma": (1.0, "mA"), "a": (1e3, "mA"),
    # ... (see spec in p1_assessment_filled.md §3)
}

def normalize_unit(
    raw_value: str,
    raw_unit: str,
    param_type: str
) -> tuple[float, str]:
    """
    Convert any unit to canonical form.
    
    Examples:
        ("3300", "mV", "voltage")    → (3.3, "V")
        ("0.5", "A", "current")      → (500.0, "mA")
        ("1.5", "kΩ", "resistance")  → (1500.0, "Ω")
        ("100", "pF", "capacitance") → (100.0, "pF")
    
    Args:
        raw_value: Numeric string from cell
        raw_unit: Unit string (may have typos, case variations)
        param_type: Parameter category (voltage, current, etc.)
                    Must be in CANONICAL_UNITS
    
    Returns:
        (normalized_value: float, canonical_unit: str)
    
    Raises:
        ValueError: If unit not recognized or param_type unknown
    
    Notes:
        - Strips whitespace and normalizes case
        - Handles OCR errors: 'u' → 'µ'
        - Raises if normalized value is unphysical (e.g., negative voltage)
    """
```

**Tests:**
```python
def test_voltage_mv_to_v():
    val, unit = normalize_unit("3300", "mV", "voltage")
    assert val == 3.3
    assert unit == "V"

def test_current_a_to_ma():
    val, unit = normalize_unit("0.5", "A", "current")
    assert val == 500.0
    assert unit == "mA"

def test_ocr_error_u_to_micro():
    val, unit = normalize_unit("100", "uA", "current")
    assert val == 0.1  # 100 µA = 0.1 mA
    assert unit == "mA"

def test_unknown_unit_raises():
    with pytest.raises(ValueError, match="Unknown unit"):
        normalize_unit("3.3", "XYZ", "voltage")

def test_case_insensitive():
    val1, _ = normalize_unit("1000", "mV", "voltage")
    val2, _ = normalize_unit("1000", "MV", "voltage")
    assert val1 == val2  # Should normalize case

def test_whitespace_handling():
    val1, _ = normalize_unit("1000", "mV", "voltage")
    val2, _ = normalize_unit("1000", " m V ", "voltage")
    assert val1 == val2

def test_empty_value_raises():
    with pytest.raises(ValueError):
        normalize_unit("", "V", "voltage")
```

---

### 2. `src/phase3_extract/parameter_extractor.py`

**Why second:** Extracts electrical parameters from grids. Pure logic (no VLM).

**Functionality:**
```python
def extract_electrical_parameters(
    grid: GridMatrix,
    component_id: str,
    footnote_map: dict[str, str] | None = None,
    config: Config = None
) -> list[ElectricalParameter]:
    """
    Extract electrical parameters from electrical_characteristics GridMatrix.
    
    Strategy:
    1. Identify header row (Parameter, Min, Typ, Max, Unit, Conditions columns)
    2. For each data row:
       a. Extract parameter name (1st column)
       b. Extract min, typ, max values (columns 2–4)
       c. Normalize units
       d. Detect and link footnotes (superscript markers like "(1)", "*")
       e. Build ElectricalParameter with confidence from grid
    3. Return list of extracted parameters
    
    Args:
        grid: GridMatrix with section_type="electrical_characteristics"
        component_id: For logging
        footnote_map: {marker: text} from Phase 1 (optional)
        config: Config object with thresholds
    
    Returns:
        list[ElectricalParameter] with min/typ/max values normalized
    
    Notes:
        - Handles sparse cells (empty cells → None in min/typ/max)
        - Detects footnote markers in cells: (1), (2), *, †, etc.
        - If confidence < threshold, mark for review
        - Parameter names may have spaces/underscores; normalize to lowercase
    """
    
    # Step 1: Identify header
    header_row_idx = identify_header_row(grid.rows)
    if header_row_idx is None:
        logger.warning(f"{component_id}: No header row found in electrical_characteristics")
        return []
    
    # Step 2: Map header columns
    col_map = map_columns(grid.rows[header_row_idx])
    # col_map = {
    #     "parameter": 0,
    #     "min": 1,
    #     "typ": 2,
    #     "max": 3,
    #     "unit": 4,
    #     "conditions": 5,
    # }
    
    # Step 3: Extract parameters
    parameters = []
    for row_idx, row in enumerate(grid.rows[header_row_idx + 1:], start=header_row_idx + 1):
        param = extract_single_parameter(
            row,
            col_map,
            grid.confidence,
            footnote_map,
            component_id,
            row_idx
        )
        if param is not None:
            parameters.append(param)
    
    return parameters


def extract_single_parameter(
    row: list[str],
    col_map: dict[str, int],
    grid_confidence: float,
    footnote_map: dict[str, str] | None = None,
    component_id: str = "",
    row_idx: int = 0
) -> ElectricalParameter | None:
    """Extract one parameter from a single row."""
    
    # Get cells
    param_name = row[col_map["parameter"]].strip()
    min_text = row[col_map["min"]].strip() if "min" in col_map else None
    typ_text = row[col_map["typ"]].strip() if "typ" in col_map else None
    max_text = row[col_map["max"]].strip() if "max" in col_map else None
    unit_text = row[col_map["unit"]].strip() if "unit" in col_map else None
    conditions = row[col_map["conditions"]].strip() if "conditions" in col_map else None
    
    # Skip empty rows
    if not param_name or (not min_text and not typ_text and not max_text):
        return None
    
    # Extract values
    param_type = infer_param_type(param_name)  # "voltage", "current", etc.
    
    min_value = extract_value_cell(min_text, unit_text, param_type, grid_confidence, footnote_map)
    typ_value = extract_value_cell(typ_text, unit_text, param_type, grid_confidence, footnote_map)
    max_value = extract_value_cell(max_text, unit_text, param_type, grid_confidence, footnote_map)
    
    return ElectricalParameter(
        name=param_name,
        parameter_type=param_type,
        min_value=min_value,
        typ_value=typ_value,
        max_value=max_value,
        conditions=conditions if conditions and conditions != "—" else None
    )


def extract_value_cell(
    cell_text: str,
    unit_text: str,
    param_type: str,
    grid_confidence: float,
    footnote_map: dict[str, str] | None = None
) -> ExtractedValue | None:
    """Extract and normalize a single cell (min/typ/max value)."""
    
    if not cell_text or cell_text in ("—", "–", "-", ""):
        return None
    
    # Detect footnote marker
    footnote_text = None
    cell_clean = cell_text
    footnote_match = re.search(r'(\(\d+\)|\*|†|‡)', cell_text)
    if footnote_match:
        footnote_marker = footnote_match.group(1)
        cell_clean = cell_text[:footnote_match.start()].strip()
        if footnote_map and footnote_marker in footnote_map:
            footnote_text = footnote_map[footnote_marker]
    
    # Parse numeric value
    try:
        numeric = float(cell_clean.replace(",", ""))
    except ValueError:
        logger.warning(f"Cannot parse value: {cell_text}")
        return None
    
    # Normalize unit
    if not unit_text or unit_text in ("—", "-"):
        normalized_unit = infer_unit_from_param_type(param_type)
    else:
        try:
            normalized_value, normalized_unit = normalize_unit(
                str(numeric),
                unit_text,
                param_type
            )
            numeric = normalized_value
        except ValueError as e:
            logger.warning(f"Unit normalization failed: {e}")
            normalized_unit = infer_unit_from_param_type(param_type)
    
    return ExtractedValue(
        raw_text=cell_text,
        value=numeric,
        unit=normalized_unit,
        confidence=grid_confidence,
        source=grid.source,  # Inherited from grid
        footnote=footnote_text
    )


def identify_header_row(rows: list[list[str]]) -> int | None:
    """Find the header row in the grid (row with column names)."""
    # Heuristics:
    # - Usually row 0 or 1
    # - Contains keywords: Parameter, Min, Typ, Max, Unit, Value, Conditions
    # - Text is short (2–3 words per cell)
    
    for idx, row in enumerate(rows[:5]):  # Check first 5 rows only
        if is_header_row(row):
            return idx
    return None


def map_columns(header: list[str]) -> dict[str, int]:
    """Map header names to column indices."""
    col_map = {}
    for idx, cell in enumerate(header):
        lower = cell.lower().strip()
        if any(x in lower for x in ["parameter", "name", "part", "description"]):
            col_map["parameter"] = idx
        elif any(x in lower for x in ["min", "minimum"]):
            col_map["min"] = idx
        elif any(x in lower for x in ["typ", "typical"]):
            col_map["typ"] = idx
        elif any(x in lower for x in ["max", "maximum"]):
            col_map["max"] = idx
        elif any(x in lower for x in ["unit", "units"]):
            col_map["unit"] = idx
        elif any(x in lower for x in ["condition", "test"]):
            col_map["conditions"] = idx
    return col_map


def infer_param_type(param_name: str) -> str:
    """Infer parameter type from name (voltage, current, resistance, etc.)."""
    name_lower = param_name.lower()
    
    if any(x in name_lower for x in ["v_cc", "v_dd", "v_ss", "v_in", "v_out", "v_", "voltage"]):
        return "voltage"
    elif any(x in name_lower for x in ["i_cc", "i_dd", "i_", "i out", "current"]):
        return "current"
    elif any(x in name_lower for x in ["r_", "ohm", "resistance"]):
        return "resistance"
    elif any(x in name_lower for x in ["c_", "cap", "capacitance"]):
        return "capacitance"
    elif any(x in name_lower for x in ["l_", "henry", "inductance"]):
        return "inductance"
    elif any(x in name_lower for x in ["f_", "freq", "frequency"]):
        return "frequency"
    elif any(x in name_lower for x in ["t_", "temp", "temperature"]):
        return "temperature"
    elif any(x in name_lower for x in ["time", "delay", "t ", "ns", "ms", "us"]):
        return "time"
    else:
        return "other"
```

**Tests:**
```python
def test_extract_electrical_parameters_from_mock():
    """Extract parameters from mock electrical_characteristics grid."""
    phase2_out = mock_tlv7021_phase2_output()
    elec_grid = [g for g in phase2_out.grids if g.section_type == "electrical_characteristics"][0]
    
    params = extract_electrical_parameters(elec_grid, "TLV7021")
    assert len(params) > 0
    assert params[0].name == "V_CC"
    assert params[0].min_value.value == 2.0
    assert params[0].typ_value.value == 3.3
    assert params[0].max_value.value == 5.5

def test_extract_with_footnotes():
    """Extract parameters with footnote references."""
    phase2_out = mock_lm5176_phase2_output()
    footnote_map = phase2_out.metadata.get("footnote_map", {})
    elec_grid = [g for g in phase2_out.grids if g.section_type == "electrical_characteristics"][0]
    
    params = extract_electrical_parameters(elec_grid, "LM5176", footnote_map)
    # Find parameter with footnote
    param_with_note = [p for p in params if p.min_value and p.min_value.footnote]
    assert len(param_with_note) > 0

def test_unit_normalization_in_extraction():
    """Ensure units are normalized during extraction."""
    phase2_out = mock_sn74_phase2_output()
    elec_grid = [g for g in phase2_out.grids if g.section_type == "electrical_characteristics"][0]
    
    params = extract_electrical_parameters(elec_grid, "SN74")
    for param in params:
        if param.min_value:
            assert param.min_value.unit in ["V", "mA", "Ω", "pF", "ns", "°C"]

def test_sparse_cells_handled():
    """Extract handles sparse cells (min or max missing)."""
    phase2_out = mock_ina219_phase2_output()
    elec_grid = [g for g in phase2_out.grids if g.section_type == "electrical_characteristics"][0]
    
    params = extract_electrical_parameters(elec_grid, "INA219")
    # Some params may have None for min or max
    sparse_params = [p for p in params if (p.min_value is None or p.max_value is None)]
    assert len(sparse_params) > 0

def test_infer_param_type():
    assert infer_param_type("V_CC") == "voltage"
    assert infer_param_type("I_CC") == "current"
    assert infer_param_type("R_SENSE") == "resistance"
    assert infer_param_type("C_LOAD") == "capacitance"
```

---

### 3. `src/phase3_extract/pinout_extractor.py`

**Extract pins from pinout grids.**

**Functions:**
```python
def extract_pins(
    grid: GridMatrix,
    component_id: str,
    config: Config = None
) -> list[PinDefinition]:
    """
    Extract pin definitions from pinout GridMatrix.
    
    Strategy:
    1. Identify header row
    2. Map columns: pin_number, pin_name, pin_type, description
    3. For each data row:
       a. Extract pin number
       b. Extract pin name (raw name from datasheet)
       c. Infer pin type (power, ground, I/O, analog, etc.)
       d. Extract alternate functions if present
    
    Args:
        grid: GridMatrix with section_type="pinout"
        component_id: For logging
        config: Config object
    
    Returns:
        list[PinDefinition]
    """
    
    header_row_idx = identify_header_row(grid.rows)
    if header_row_idx is None:
        logger.warning(f"{component_id}: No header in pinout table")
        return []
    
    col_map = map_pin_columns(grid.rows[header_row_idx])
    
    pins = []
    for row_idx, row in enumerate(grid.rows[header_row_idx + 1:]):
        pin = extract_single_pin(row, col_map, grid.confidence)
        if pin is not None:
            pins.append(pin)
    
    return pins


def extract_single_pin(
    row: list[str],
    col_map: dict[str, int],
    grid_confidence: float
) -> PinDefinition | None:
    """Extract one pin from a row."""
    
    pin_number = row[col_map.get("pin_number", 0)].strip()
    if not pin_number or pin_number in ("—", "-", "NC"):
        return None if pin_number != "NC" else None
    
    pin_name = row[col_map.get("pin_name", 1)].strip() if "pin_name" in col_map else ""
    pin_type_text = row[col_map.get("pin_type", 2)].strip() if "pin_type" in col_map else ""
    description = row[col_map.get("description", 3)].strip() if "description" in col_map else None
    
    # Infer pin type
    pin_type = infer_pin_type(pin_name, pin_type_text)
    
    # Extract alternate functions (e.g., "GPIO0/UART_TX" → ["GPIO0", "UART_TX"])
    alternates = extract_alternate_functions(pin_name)
    
    return PinDefinition(
        pin_number=pin_number,
        pin_name=pin_name,
        pin_type=pin_type,
        alternate_functions=alternates,
        description=description if description and description != "—" else None
    )


def infer_pin_type(pin_name: str, pin_type_text: str) -> str:
    """Infer pin type from name and explicit type field."""
    
    combined = f"{pin_name} {pin_type_text}".lower()
    
    if any(x in combined for x in ["v_cc", "v_dd", "v+", "power", "vdd", "vss_out"]):
        return "power"
    elif any(x in combined for x in ["gnd", "v_ss", "v-", "ground", "vss"]):
        return "ground"
    elif any(x in combined for x in ["gpio", "digital", "i/o", "io", "input/output"]):
        return "digital_io"
    elif any(x in combined for x in ["out", "tx", "txd", "output", "dq"]):
        return "digital_output"
    elif any(x in combined for x in ["in", "rx", "rxd", "input", "clk"]):
        return "digital_input"
    elif any(x in combined for x in ["analog", "adc", "dac", "ain", "aout"]):
        if "out" in combined:
            return "analog_output"
        else:
            return "analog_input"
    elif any(x in combined for x in ["clock", "clk", "osc"]):
        return "clock"
    elif any(x in combined for x in ["reset", "rst", "nreset"]):
        return "reset"
    elif any(x in combined for x in ["no connect", "nc", "—"]):
        return "no_connect"
    else:
        return "other"


def extract_alternate_functions(pin_name: str) -> list[str]:
    """Parse pin name for alternate functions. E.g., 'GPIO0/UART_TX' → ['GPIO0', 'UART_TX']."""
    
    # Split by common separators
    parts = re.split(r'[/,;]', pin_name)
    return [p.strip() for p in parts if p.strip()]
```

**Tests:**
```python
def test_extract_pins_from_mock():
    """Extract pins from mock pinout grid."""
    phase2_out = mock_tlv7021_phase2_output()
    pinout_grid = [g for g in phase2_out.grids if g.section_type == "pinout"][0]
    
    pins = extract_pins(pinout_grid, "TLV7021")
    assert len(pins) == 8
    assert pins[0].pin_number == "1"
    assert pins[0].pin_name == "IN+"

def test_infer_pin_type():
    assert infer_pin_type("V_CC", "Power") == "power"
    assert infer_pin_type("GND", "Ground") == "ground"
    assert infer_pin_type("GPIO0", "I/O") == "digital_io"
    assert infer_pin_type("DATA_OUT", "Output") == "digital_output"

def test_alternate_functions():
    funcs = extract_alternate_functions("GPIO0/UART_TX/SPI_MOSI")
    assert funcs == ["GPIO0", "UART_TX", "SPI_MOSI"]
```

---

### 4. `src/phase3_extract/absolute_max_extractor.py`

**Extract absolute maximum ratings.**

**Functions:**
```python
def extract_absolute_max_ratings(
    grid: GridMatrix,
    component_id: str,
    config: Config = None
) -> list[AbsoluteMaximumRating]:
    """
    Extract absolute maximum ratings from absolute_maximum_ratings GridMatrix.
    
    Strategy:
    1. Identify header row
    2. Map columns: parameter, max, unit
    3. For each data row:
       a. Extract parameter name
       b. Extract max value
       c. Normalize unit
    
    Args:
        grid: GridMatrix with section_type="absolute_maximum_ratings"
        component_id: For logging
        config: Config object
    
    Returns:
        list[AbsoluteMaximumRating]
    """
    
    header_row_idx = identify_header_row(grid.rows)
    if header_row_idx is None:
        return []
    
    col_map = map_abs_max_columns(grid.rows[header_row_idx])
    
    ratings = []
    for row in grid.rows[header_row_idx + 1:]:
        rating = extract_single_abs_max(row, col_map, grid.confidence)
        if rating is not None:
            ratings.append(rating)
    
    return ratings


def extract_single_abs_max(
    row: list[str],
    col_map: dict[str, int],
    grid_confidence: float
) -> AbsoluteMaximumRating | None:
    """Extract one absolute maximum rating from a row."""
    
    param_name = row[col_map.get("parameter", 0)].strip()
    max_text = row[col_map.get("max", 1)].strip()
    unit_text = row[col_map.get("unit", 2)].strip() if "unit" in col_map else None
    conditions = row[col_map.get("conditions", 3)].strip() if "conditions" in col_map else None
    
    if not param_name or not max_text or max_text in ("—", "-"):
        return None
    
    param_type = infer_param_type(param_name)
    
    try:
        numeric = float(max_text.replace(",", ""))
        if not unit_text or unit_text in ("—", "-"):
            normalized_unit = infer_unit_from_param_type(param_type)
        else:
            numeric, normalized_unit = normalize_unit(
                str(numeric),
                unit_text,
                param_type
            )
    except (ValueError, KeyError):
        logger.warning(f"Cannot extract abs max rating: {param_name} = {max_text}")
        return None
    
    return AbsoluteMaximumRating(
        name=param_name,
        max_value=ExtractedValue(
            raw_text=max_text,
            value=numeric,
            unit=normalized_unit,
            confidence=grid_confidence,
            source="extracted"
        ),
        conditions=conditions if conditions and conditions != "—" else None
    )
```

---

### 5. `src/phase3_extract/footnote_resolver.py`

**Resolve footnote references and link to ExtractedValue objects.**

**Functions:**
```python
def resolve_footnotes_in_extraction(
    parameters: list[ElectricalParameter],
    pins: list[PinDefinition],
    abs_max_ratings: list[AbsoluteMaximumRating],
    footnote_map: dict[str, str] | None = None
) -> None:
    """
    Post-process extracted data to link footnote text to ExtractedValue objects.
    
    This function modifies parameters, pins, and abs_max_ratings in-place,
    adding footnote_map lookups to ExtractedValue.footnote fields.
    
    Args:
        parameters: List of ElectricalParameter to process
        pins: List of PinDefinition to process
        abs_max_ratings: List of AbsoluteMaximumRating to process
        footnote_map: {marker: text} from Phase 1
    """
    
    if not footnote_map:
        return
    
    # Process parameters
    for param in parameters:
        for value_field in ["min_value", "typ_value", "max_value"]:
            value = getattr(param, value_field, None)
            if value and value.footnote is None:
                # Check if raw_text contains footnote marker
                marker = extract_footnote_marker(value.raw_text)
                if marker and marker in footnote_map:
                    value.footnote = footnote_map[marker]
        
        # Also check conditions field
        if param.conditions:
            marker = extract_footnote_marker(param.conditions)
            if marker and marker not in param.conditions:
                # Conditions may also have footnote
                pass
    
    # Similar for pins, abs_max_ratings
    # (less common to have footnotes, but possible)


def extract_footnote_marker(text: str) -> str | None:
    """Extract footnote marker from text (e.g., '(1)', '*', '†')."""
    match = re.search(r'(\(\d+\)|\*|†|‡|§)', text)
    return match.group(1) if match else None
```

---

### 6. `src/phase3_extract/validation.py`

**Validate extracted data, check for required fields and anomalies.**

**Functions:**
```python
def validate_extracted_data(
    component_id: str,
    parameters: list[ElectricalParameter],
    pins: list[PinDefinition],
    abs_max_ratings: list[AbsoluteMaximumRating],
    config: Config = None
) -> ValidationResult:
    """
    Validate extracted electrical data.
    
    Checks:
    - No duplicate parameter names
    - Parameters have at least one value (min/typ/max)
    - Pins are non-empty and have pin numbers
    - Confidence thresholds met
    
    Args:
        component_id: Component being validated
        parameters: Electrical parameters
        pins: Pin definitions
        abs_max_ratings: Absolute max ratings
        config: Config with thresholds
    
    Returns:
        ValidationResult with errors and warnings
    """
    
    errors = []
    warnings = []
    
    # Check duplicates
    param_names = [p.name for p in parameters]
    duplicates = [name for name, count in Counter(param_names).items() if count > 1]
    if duplicates:
        errors.append(f"Duplicate parameters: {duplicates}")
    
    # Check empty parameters
    if not parameters:
        warnings.append("No electrical parameters extracted")
    
    # Check confidence
    low_conf = [p for p in parameters if p.avg_confidence() < 0.70]
    if low_conf:
        warnings.append(f"{len(low_conf)} parameters have low confidence")
    
    # Check pins
    if not pins:
        warnings.append("No pins extracted (expected for some components)")
    else:
        pin_numbers = [p.pin_number for p in pins]
        if len(pin_numbers) != len(set(pin_numbers)):
            errors.append("Duplicate pin numbers")
    
    passed = len(errors) == 0
    
    return ValidationResult(
        component_id=component_id,
        passed=passed,
        errors=errors,
        warnings=warnings,
        review_required=(len(warnings) > 0),
        confidence_score=compute_aggregate_confidence(parameters, pins, abs_max_ratings)
    )
```

---

### 7. `src/phase3_extract/runner.py`

**Orchestrate all extraction modules.**

**Functions:**
```python
def run_phase3(
    phase2_output: Phase2Output,
    config: Config = None
) -> ComponentDatasheet:
    """
    Full Phase 3 extraction pipeline.
    
    For each GridMatrix in Phase2Output:
    1. Identify section type
    2. Route to appropriate extractor
    3. Normalize units
    4. Resolve footnotes
    5. Validate
    6. Return ComponentDatasheet
    
    Args:
        phase2_output: From Phase 2
        config: Config object
    
    Returns:
        ComponentDatasheet with extracted data
    """
    
    config = config or get_config()
    
    pdf_path = phase2_output.metadata.get("pdf_path", "unknown")
    component_id = phase2_output.metadata.get("component_id", "unknown")
    footnote_map = phase2_output.metadata.get("footnote_map", {})
    
    logger.info(f"Phase 3: Extracting {component_id} from {pdf_path}")
    
    # Route grids by section type
    parameters = []
    pins = []
    abs_max_ratings = []
    sections = []
    
    for grid in phase2_output.grids:
        logger.debug(f"  Processing {grid.section_type} table ({grid.num_rows}r × {grid.num_cols}c)")
        
        if grid.section_type == "electrical_characteristics":
            params = extract_electrical_parameters(grid, component_id, footnote_map, config)
            parameters.extend(params)
            sections.append(DatasheetSection(
                section_type="electrical_characteristics",
                page_range=grid.page_range,
                parameters=params,
                pins=[],
                abs_max_ratings=[]
            ))
        
        elif grid.section_type == "pinout":
            pins_list = extract_pins(grid, component_id, config)
            pins.extend(pins_list)
            sections.append(DatasheetSection(
                section_type="pinout",
                page_range=grid.page_range,
                parameters=[],
                pins=pins_list,
                abs_max_ratings=[]
            ))
        
        elif grid.section_type == "absolute_maximum_ratings":
            abs_max = extract_absolute_max_ratings(grid, component_id, config)
            abs_max_ratings.extend(abs_max)
            sections.append(DatasheetSection(
                section_type="absolute_maximum_ratings",
                page_range=grid.page_range,
                parameters=[],
                pins=[],
                abs_max_ratings=abs_max
            ))
    
    # Resolve footnotes
    resolve_footnotes_in_extraction(parameters, pins, abs_max_ratings, footnote_map)
    
    # Validate
    validation = validate_extracted_data(component_id, parameters, pins, abs_max_ratings, config)
    
    # Build ComponentDatasheet
    datasheet = ComponentDatasheet(
        component_id=component_id,
        manufacturer="Texas Instruments",  # TODO: extract from metadata
        sections=sections,
        pins=pins,
        validation=validation
    )
    
    logger.info(f"Phase 3 complete: {len(parameters)} params, {len(pins)} pins")
    
    return datasheet
```

**Tests:**
```python
def test_run_phase3_with_mock():
    """Run full Phase 3 on mock Phase 2 output."""
    phase2_out = mock_tlv7021_phase2_output()
    datasheet = run_phase3(phase2_out)
    
    assert datasheet.component_id == "TLV7021"
    assert len(datasheet.pins) > 0
    assert datasheet.validation.passed == True

def test_run_phase3_all_golden():
    """Run Phase 3 on all 5 golden components."""
    all_phase2 = all_golden_phase2_outputs()
    
    for component_id, phase2_out in all_phase2.items():
        datasheet = run_phase3(phase2_out)
        assert datasheet.component_id == component_id
        assert datasheet.validation is not None
```

---

## Exit Criteria

- ✅ All 7 modules implemented
- ✅ 50+ unit tests pass locally (no GPU, VLM disabled)
- ✅ Code follows `CODING_STANDARDS_P1.md`
- ✅ No hardcoded paths (use `Config`)
- ✅ Type hints on all functions
- ✅ Docstrings on all public functions
- ✅ Logging on extraction steps

---

## Do NOT

- ❌ Run Phase 3 on real PDFs (Phase 2 outputs don't exist yet)
- ❌ Load Qwen2.5-7B model locally (mock it in tests)
- ❌ Assume all tables extract successfully (handle None, empty lists)
- ❌ Skip footnote resolution (they contain critical constraints)
- ❌ Forget unit normalization (1000x errors possible without it)

---

## Testing Strategy

**Import mock data in all tests:**
```python
from tests.fixtures.phase2_mock_outputs import (
    all_golden_phase2_outputs,
    mock_tlv7021_phase2_output,
    mock_ina219_phase2_output,
)

def test_extract_from_mock():
    phase2_out = mock_tlv7021_phase2_output()
    datasheet = run_phase3(phase2_out)
    assert datasheet is not None
```

**All tests pass locally:**
```bash
pytest tests/unit/test_phase3_*.py -v
```

---

## Schema Reminder

You already have all schemas in `src/schemas/datasheet.py` and `src/schemas/pipeline.py`. Reference:

- `GridMatrix` — input from Phase 2
- `ElectricalParameter`, `PinDefinition`, `AbsoluteMaximumRating` — outputs
- `ComponentDatasheet` — final Phase 3 output
- `ExtractedValue` — atomic value with provenance

---

## Ready?

- Read authority docs first
- Implement in order: 1 → 2 → 3 → 4 → 5 → 6 → 7
- Run tests locally (`pytest tests/unit/test_phase3_*.py`)
- All tests pass on MacBook
- Commit to git

**Go!**