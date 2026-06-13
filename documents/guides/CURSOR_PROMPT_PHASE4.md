# CURSOR_PROMPT_PHASE4_VALIDATION_KICAD.md

## Context

You are implementing **Phase 4: Physics Validation & KiCad Export** for the Open Forge P1 Datasheet Parser. Your goal is to validate extracted electrical data against physical plausibility rules, flag anomalies, and export to KiCad-compatible JSON format.

**Authority documents:**
- `documents/p1_assessment_filled.md` — full spec (§4 Phase 4, cross-param rules, abs-max rules, sanity ranges, routing logic)
- `documents/PROJECT_CONTEXT.md` — project status
- `documents/CODING_STANDARDS_P1.md` — coding standards
- `documents/QUICK_REFERENCE_PATTERNS.md` — code patterns

**Current status:** Phase 1 ✅ (5/5 PASS), Phase 2 ✅ (73 tests), Phase 3 ✅ (53 tests, 124 total). Phase 4 scaffolding ready.

**Task:** Write Phase 4 code. **No GPU needed.** All tests pass locally using mock Phase 3 outputs.

---

## Phase 4 Architecture

### Input → Output

```
Phase 3 Output (ComponentDatasheet)
  • component_id: str
  • manufacturer: str
  • sections: list[DatasheetSection]
    ├─ electrical_characteristics: list[ElectricalParameter]
    ├─ absolute_maximum_ratings: list[AbsoluteMaximumRating]
    └─ pinout: list[PinDefinition]
  
         │ (validate electrical plausibility)
         ▼
         
    Rule Engine
    ┌──────────────────────────────────┐
    │ 1. Min/Typ/Max Ordering          │
    │    min ≤ typ ≤ max               │
    │                                  │
    │ 2. Cross-Parameter Rules         │
    │    V_CC > V_IL, V_IH < V_CC      │
    │    V_OL < V_IL, V_OH > V_IH      │
    │                                  │
    │ 3. Sanity Range Checks           │
    │    V_CC ∈ [0.5V, 40V]            │
    │    T_J ∈ [-55°C, 175°C]          │
    │                                  │
    │ 4. Abs-Max Specific Rules        │
    │    abs_max > operating_max       │
    └──────────────────────────────────┘
         │
         ├─ CRITICAL errors → block downstream
         ├─ WARNING issues → flag for review
         └─ All pass → proceed to export
         │
         ▼
    Routing Logic
    ┌──────────────────────────────────┐
    │ If passed:                       │
    │  → Export to KiCad JSON          │
    │                                  │
    │ If warnings:                     │
    │  → Export + mark review_required │
    │                                  │
    │ If CRITICAL errors:              │
    │  → BLOCKED (return error report) │
    └──────────────────────────────────┘
         │
         ▼
Phase 4 Output
  • ValidationResult: passed, errors, warnings, review_required
  • KiCadExport (JSON): component_id, pins, symbols, connections
```

### Key Data Structures

**ValidationError (already in schema):**
```python
class ValidationError(BaseModel):
    level: Literal["CRITICAL", "WARNING"]
    param_name: str
    message: str
    remediation: Optional[str]
```

**ValidationResult (already in schema):**
```python
class ValidationResult(BaseModel):
    component_id: str
    passed: bool
    errors: list[ValidationError]
    warnings: list[ValidationError]
    review_required: bool
    confidence_score: float
    timestamp: str
```

**KiCadExport (new, to design):**
```python
class KiCadExport(BaseModel):
    """KiCad-compatible component export."""
    component_id: str
    manufacturer: str
    package: Optional[str]
    datasheet_url: Optional[str]
    pins: list[KiCadPin]  # For schematic symbol generation
    electrical_specs: dict  # For validation/annotation
    validation_status: str  # "PASS", "WARN", "BLOCKED"
```

---

## Implementation Order

### 1. `src/phase4_validate/ordering_rules.py`

**Why first:** Simplest rules, pure logic, no dependencies.

**Functionality:**
```python
def validate_min_typ_max_ordering(
    parameters: list[ElectricalParameter]
) -> list[ValidationError]:
    """
    Check min ≤ typ ≤ max for all parameters.
    
    Logic:
    - If min_value exists and typ_value exists and min > typ → CRITICAL error
    - If typ_value exists and max_value exists and typ > max → CRITICAL error
    - If min_value exists and max_value exists and min > max → CRITICAL error
    
    Args:
        parameters: List of ElectricalParameter
        
    Returns:
        list[ValidationError] (empty if all valid)
    
    Examples:
        V_CC: min=1.8, typ=3.3, max=5.5 → ✅ OK
        V_IL: min=0.8, typ=1.5, max=2.0 → ✅ OK
        V_OUT: min=5.0, typ=3.3, max=0.5 → ❌ min > max (CRITICAL)
    """
    errors = []
    
    for param in parameters:
        # min ≤ typ check
        if param.min_value and param.typ_value:
            if param.min_value.value > param.typ_value.value:
                errors.append(ValidationError(
                    level="CRITICAL",
                    param_name=param.name,
                    message=f"min ({param.min_value.value}) > typ ({param.typ_value.value})",
                    remediation="Check datasheet table structure — may be inverted or malformed"
                ))
        
        # typ ≤ max check
        if param.typ_value and param.max_value:
            if param.typ_value.value > param.max_value.value:
                errors.append(ValidationError(
                    level="CRITICAL",
                    param_name=param.name,
                    message=f"typ ({param.typ_value.value}) > max ({param.max_value.value})",
                    remediation="Check datasheet table structure"
                ))
        
        # min ≤ max check (if min and max but no typ)
        if param.min_value and param.max_value and not param.typ_value:
            if param.min_value.value > param.max_value.value:
                errors.append(ValidationError(
                    level="CRITICAL",
                    param_name=param.name,
                    message=f"min ({param.min_value.value}) > max ({param.max_value.value})",
                    remediation="Columns may be swapped"
                ))
    
    return errors
```

**Tests:**
```python
def test_valid_ordering():
    """Valid min ≤ typ ≤ max passes."""
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        min_value=ExtractedValue(1.8, "V", 0.95, "mock"),
        typ_value=ExtractedValue(3.3, "V", 0.95, "mock"),
        max_value=ExtractedValue(5.5, "V", 0.95, "mock")
    )
    errors = validate_min_typ_max_ordering([param])
    assert len(errors) == 0

def test_inverted_min_max():
    """min > max fails (CRITICAL)."""
    param = ElectricalParameter(
        name="V_OUT",
        parameter_type="voltage",
        min_value=ExtractedValue(5.0, "V", 0.95, "mock"),
        max_value=ExtractedValue(0.5, "V", 0.95, "mock")
    )
    errors = validate_min_typ_max_ordering([param])
    assert len(errors) == 1
    assert errors[0].level == "CRITICAL"
```

---

### 2. `src/phase4_validate/sanity_ranges.py`

**Plausibility checks: Does the value make physical sense?**

**Functionality:**
```python
SANITY_RANGES = {
    # (param_name_pattern, param_type, min_sane, max_sane)
    "V_CC": ("voltage", 0.5, 40.0),        # 0.5V–40V
    "V_GND": ("voltage", -0.5, 0.5),       # ≈0V
    "V_DD": ("voltage", 0.5, 40.0),
    "I_CC": ("current", 0.001, 5000.0),    # 1µA–5A (in mA)
    "I_DD": ("current", 0.001, 5000.0),
    "T_J": ("temperature", -55.0, 175.0),  # -55°C–175°C
    "T_A": ("temperature", -40.0, 85.0),   # -40°C–85°C
}


def validate_sanity_ranges(
    parameters: list[ElectricalParameter],
    abs_max_ratings: list[AbsoluteMaximumRating] | None = None
) -> list[ValidationError]:
    """
    Check if values fall within physically plausible ranges.
    
    Examples:
        V_CC = 0.001V → ❌ WARNING (too low, possible OCR error)
        T_J = 200°C → ❌ WARNING (exceeds typical max of 175°C)
        I_CC = 50A → ❌ WARNING (unrealistic for most ICs)
    
    Args:
        parameters: List of ElectricalParameter
        abs_max_ratings: Optional, for additional context
        
    Returns:
        list[ValidationError] (level="WARNING")
    """
    errors = []
    
    for param in parameters:
        # Get expected range for this parameter
        range_spec = None
        for pattern, spec in SANITY_RANGES.items():
            if pattern.lower() in param.name.lower():
                range_spec = spec
                break
        
        if not range_spec:
            continue  # No range defined, skip
        
        param_type, min_sane, max_sane = range_spec
        
        # Check all three values
        for value_field, value_obj in [
            ("min", param.min_value),
            ("typ", param.typ_value),
            ("max", param.max_value)
        ]:
            if value_obj is None:
                continue
            
            if not (min_sane <= value_obj.value <= max_sane):
                errors.append(ValidationError(
                    level="WARNING",
                    param_name=param.name,
                    message=f"{value_field} value {value_obj.value} {value_obj.unit} outside expected range [{min_sane}, {max_sane}]",
                    remediation=f"Check datasheet; possible OCR/extraction error or unusual component spec"
                ))
    
    return errors
```

**Tests:**
```python
def test_voltage_in_range():
    """Normal voltage is sane."""
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        typ_value=ExtractedValue(3.3, "V", 0.95, "mock")
    )
    errors = validate_sanity_ranges([param])
    assert len(errors) == 0

def test_voltage_too_low_warns():
    """Suspiciously low voltage triggers WARNING."""
    param = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        typ_value=ExtractedValue(0.001, "V", 0.70, "mock")
    )
    errors = validate_sanity_ranges([param])
    assert len(errors) == 1
    assert errors[0].level == "WARNING"

def test_temperature_out_of_range():
    """Junction temp > 175°C is unusual."""
    param = ElectricalParameter(
        name="T_J",
        parameter_type="temperature",
        max_value=ExtractedValue(200.0, "°C", 0.85, "mock")
    )
    errors = validate_sanity_ranges([param])
    assert len(errors) == 1
```

---

### 3. `src/phase4_validate/cross_parameter_rules.py`

**Cross-field validation: Relationships between parameters.**

**Functionality:**
```python
# Rule database (from spec)
ELECTRICAL_RULES = [
    {
        "rule": "V_CC > V_IL_max",
        "params": ["V_CC", "V_IL"],
        "check": lambda vcc, vil: vcc.typ_value.value > vil.max_value.value,
        "severity": "CRITICAL",
        "message": "Supply voltage must exceed logic-low threshold"
    },
    {
        "rule": "V_IH_min < V_CC_min",
        "params": ["V_IH", "V_CC"],
        "check": lambda vih, vcc: vih.max_value.value < vcc.min_value.value,
        "severity": "CRITICAL",
        "message": "Logic-high threshold must be less than supply voltage"
    },
    {
        "rule": "V_IL_max < V_IH_min",
        "params": ["V_IL", "V_IH"],
        "check": lambda vil, vih: vil.max_value.value < vih.min_value.value,
        "severity": "CRITICAL",
        "message": "Logic-low max must be less than logic-high min"
    },
    {
        "rule": "V_OL_max < V_IL_max",
        "params": ["V_OL", "V_IL"],
        "check": lambda vol, vil: vol.max_value.value < vil.max_value.value,
        "severity": "WARNING",
        "message": "Output-low voltage should be less than input-low threshold (noise margin)"
    },
    {
        "rule": "V_OH_min > V_IH_min",
        "params": ["V_OH", "V_IH"],
        "check": lambda voh, vih: voh.min_value.value > vih.min_value.value,
        "severity": "WARNING",
        "message": "Output-high voltage should exceed input-high threshold (noise margin)"
    },
]


def validate_cross_parameter_rules(
    parameters: list[ElectricalParameter]
) -> list[ValidationError]:
    """
    Check electrical relationships between parameters.
    
    Examples:
        V_CC=3.3V, V_IL_max=2.0V → ✅ V_CC > V_IL (OK)
        V_CC=3.3V, V_IL_max=4.0V → ❌ V_CC < V_IL (CRITICAL, no valid logic window)
        V_OL_max=0.8V, V_IL_max=0.5V → ⚠️ output too high for low threshold (WARNING)
    
    Args:
        parameters: List of ElectricalParameter
        
    Returns:
        list[ValidationError]
    """
    errors = []
    
    # Build lookup: param name → ElectricalParameter
    param_lookup = {p.name: p for p in parameters}
    
    # Check each rule
    for rule in ELECTRICAL_RULES:
        param_names = rule["params"]
        
        # Get the two parameters involved
        params_found = [param_lookup.get(name) for name in param_names]
        
        # Skip if either parameter not found
        if any(p is None for p in params_found):
            continue
        
        # Check if rule passes
        try:
            rule_passes = rule["check"](*params_found)
        except (AttributeError, TypeError):
            # Missing required fields (min/max/typ)
            continue
        
        if not rule_passes:
            errors.append(ValidationError(
                level=rule["severity"],
                param_name=f"{param_names[0]} vs {param_names[1]}",
                message=f"Rule '{rule['rule']}' failed: {rule['message']}",
                remediation="Check parameter extraction and datasheet structure"
            ))
    
    return errors
```

**Tests:**
```python
def test_valid_logic_levels():
    """Valid V_CC > V_IL passes."""
    params = [
        ElectricalParameter(
            name="V_CC",
            parameter_type="voltage",
            typ_value=ExtractedValue(3.3, "V", 0.95, "mock")
        ),
        ElectricalParameter(
            name="V_IL",
            parameter_type="voltage",
            max_value=ExtractedValue(0.8, "V", 0.95, "mock")
        )
    ]
    errors = validate_cross_parameter_rules(params)
    # Rule "V_CC > V_IL_max" should pass
    assert not any(e.rule == "V_CC > V_IL_max" for e in errors)

def test_invalid_logic_window():
    """Invalid logic window: V_IL_max >= V_IH_min fails (CRITICAL)."""
    params = [
        ElectricalParameter(
            name="V_IL",
            parameter_type="voltage",
            max_value=ExtractedValue(2.0, "V", 0.95, "mock")
        ),
        ElectricalParameter(
            name="V_IH",
            parameter_type="voltage",
            min_value=ExtractedValue(1.5, "V", 0.95, "mock")
        )
    ]
    errors = validate_cross_parameter_rules(params)
    rule_errors = [e for e in errors if "V_IL_max < V_IH_min" in e.message]
    assert len(rule_errors) == 1
    assert rule_errors[0].level == "CRITICAL"
```

---

### 4. `src/phase4_validate/absolute_max_rules.py`

**Abs-max specific validation: Ceiling rules.**

**Functionality:**
```python
def validate_abs_max_vs_operating(
    abs_max_ratings: list[AbsoluteMaximumRating],
    parameters: list[ElectricalParameter]
) -> list[ValidationError]:
    """
    Key rule: abs-max ceiling must always exceed recommended operating maximum.
    
    Example:
        V_CC operating: min=1.8V, typ=3.3V, max=5.5V
        V_CC abs-max: max=6.0V
        Check: abs_max (6.0V) > operating_max (5.5V) → ✅ OK
        
        If abs_max (6.0V) < operating_max (5.5V) → ❌ CRITICAL
        (Indicates tables are swapped or data is corrupted)
    
    Args:
        abs_max_ratings: List of absolute maximum ratings
        parameters: List of operating parameters
        
    Returns:
        list[ValidationError]
    """
    errors = []
    
    # Build lookup: base param name → operating max value
    operating_max = {}
    for param in parameters:
        base_name = param.name.replace("_ABS", "").replace("_MAX", "")
        if param.max_value:
            operating_max[base_name] = param.max_value.value
    
    # Check each abs-max rating
    for rating in abs_max_ratings:
        base_name = rating.name.replace("_ABS", "").replace("_MAX", "")
        
        if base_name in operating_max:
            op_max = operating_max[base_name]
            abs_val = rating.max_value.value
            
            if abs_val <= op_max:
                errors.append(ValidationError(
                    level="CRITICAL",
                    param_name=rating.name,
                    message=f"abs-max ({abs_val}) ≤ operating_max ({op_max}) — tables may be swapped",
                    remediation="Verify absolute maximum ratings table is not confused with operating range"
                ))
    
    return errors


def validate_abs_max_sanity(
    abs_max_ratings: list[AbsoluteMaximumRating]
) -> list[ValidationError]:
    """Basic sanity: abs-max values must be positive and within physical bounds."""
    
    errors = []
    ABS_MAX_BOUNDS = {
        "voltage": (0.0, 200.0),        # V
        "current": (0.0, 100_000.0),    # mA
        "temperature": (-65.0, 300.0),  # °C
    }
    
    for rating in abs_max_ratings:
        param_type = infer_param_type(rating.name)
        
        if param_type in ABS_MAX_BOUNDS:
            lo, hi = ABS_MAX_BOUNDS[param_type]
            val = rating.max_value.value
            
            if not (lo <= val <= hi):
                errors.append(ValidationError(
                    level="WARNING",
                    param_name=rating.name,
                    message=f"abs-max {val} {rating.max_value.unit} outside plausible range [{lo}, {hi}]",
                    remediation="Check extraction; possible OCR error"
                ))
    
    return errors
```

**Tests:**
```python
def test_abs_max_exceeds_operating():
    """Valid: abs-max ceiling > operating max."""
    operating = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        max_value=ExtractedValue(5.5, "V", 0.95, "mock")
    )
    abs_max = AbsoluteMaximumRating(
        name="V_CC_ABS",
        max_value=ExtractedValue(6.0, "V", 0.95, "mock")
    )
    errors = validate_abs_max_vs_operating([abs_max], [operating])
    assert len(errors) == 0

def test_abs_max_below_operating_fails():
    """Invalid: abs-max < operating (CRITICAL)."""
    operating = ElectricalParameter(
        name="V_CC",
        parameter_type="voltage",
        max_value=ExtractedValue(5.5, "V", 0.95, "mock")
    )
    abs_max = AbsoluteMaximumRating(
        name="V_CC_ABS",
        max_value=ExtractedValue(5.0, "V", 0.95, "mock")  # Less than operating!
    )
    errors = validate_abs_max_vs_operating([abs_max], [operating])
    assert len(errors) == 1
    assert errors[0].level == "CRITICAL"
```

---

### 5. `src/phase4_validate/validator.py`

**Master validator: Orchestrate all rules, produce ValidationResult.**

**Functionality:**
```python
def run_full_validation(
    datasheet: ComponentDatasheet,
    config: Config = None
) -> ValidationResult:
    """
    Run all validation rules (ordering, sanity, cross-param, abs-max).
    
    Produces:
    - List of CRITICAL errors (block downstream use)
    - List of WARNINGs (flag for review)
    - Aggregate confidence score
    - Final passed/review_required flags
    
    Args:
        datasheet: ComponentDatasheet from Phase 3
        config: Config with thresholds
        
    Returns:
        ValidationResult
    """
    
    config = config or get_config()
    
    all_errors = []
    all_warnings = []
    
    # Extract parameters and ratings
    parameters = datasheet.all_parameters
    pins = datasheet.all_pins
    abs_max_ratings = datasheet.all_abs_max
    
    logger.info(f"Phase 4: Validating {datasheet.component_id}")
    logger.debug(f"  {len(parameters)} parameters, {len(pins)} pins, {len(abs_max_ratings)} abs-max")
    
    # Rule 1: Ordering
    ordering_errors = validate_min_typ_max_ordering(parameters)
    all_errors.extend(ordering_errors)
    
    # Rule 2: Sanity ranges
    sanity_errors = validate_sanity_ranges(parameters, abs_max_ratings)
    all_warnings.extend(sanity_errors)
    
    # Rule 3: Cross-parameter
    cross_errors = validate_cross_parameter_rules(parameters)
    for err in cross_errors:
        if err.level == "CRITICAL":
            all_errors.append(err)
        else:
            all_warnings.append(err)
    
    # Rule 4: Abs-max
    abs_max_errors = validate_abs_max_vs_operating(abs_max_ratings, parameters)
    all_errors.extend(abs_max_errors)
    
    abs_max_sanity = validate_abs_max_sanity(abs_max_ratings)
    all_warnings.extend(abs_max_sanity)
    
    # Compute aggregate confidence
    confidence_score = compute_aggregate_confidence(
        parameters, pins, abs_max_ratings
    )
    
    # Routing logic
    passed = len(all_errors) == 0
    review_required = (len(all_warnings) > 0) or (confidence_score < config.thresholds.warn_downstream)
    
    result = ValidationResult(
        component_id=datasheet.component_id,
        passed=passed,
        errors=all_errors,
        warnings=all_warnings,
        review_required=review_required,
        confidence_score=confidence_score,
        timestamp=datetime.now().isoformat()
    )
    
    logger.info(
        f"Validation: passed={passed}, "
        f"errors={len(all_errors)}, "
        f"warnings={len(all_warnings)}, "
        f"confidence={confidence_score:.2%}"
    )
    
    return result


def compute_aggregate_confidence(
    parameters: list[ElectricalParameter],
    pins: list[PinDefinition],
    abs_max_ratings: list[AbsoluteMaximumRating]
) -> float:
    """Weighted average confidence across all extracted values."""
    
    all_confidences = []
    
    # Parameters
    for param in parameters:
        for val in [param.min_value, param.typ_value, param.max_value]:
            if val:
                all_confidences.append(val.confidence)
    
    # Pins (extracted in Phase 3, have confidence from grid)
    # Abs-max ratings
    for rating in abs_max_ratings:
        all_confidences.append(rating.max_value.confidence)
    
    if not all_confidences:
        return 0.0
    
    return sum(all_confidences) / len(all_confidences)
```

**Tests:**
```python
def test_validation_passes_clean_data():
    """Valid extracted data passes all validation."""
    datasheet = mock_tlv7021_component_datasheet()  # Mock from Phase 3
    result = run_full_validation(datasheet)
    assert result.passed == True
    assert len(result.errors) == 0

def test_validation_catches_inverted_min_max():
    """Inverted min/max caught and blocks."""
    datasheet = mock_component_with_inverted_values()
    result = run_full_validation(datasheet)
    assert result.passed == False
    assert any(e.level == "CRITICAL" for e in result.errors)

def test_validation_warns_on_low_confidence():
    """Low confidence triggers review flag."""
    datasheet = mock_component_with_low_confidence()
    result = run_full_validation(datasheet)
    # Passed (no CRITICAL), but review_required=True
    assert result.confidence_score < 0.85
    assert result.review_required == True
```

---

### 6. `src/phase4_validate/kicad_exporter.py`

**Export to KiCad JSON format (for schematic symbol generation, netlisting, etc.)**

**Functionality:**
```python
class KiCadPin(BaseModel):
    """Pin for KiCad symbol."""
    pin_number: str
    pin_name: str
    pin_type: str  # "power", "ground", "input", "output", "io", etc.
    net_name: Optional[str] = None  # Will be auto-assigned by netlister


class KiCadExport(BaseModel):
    """KiCad-compatible component export."""
    component_id: str
    manufacturer: str
    package: Optional[str]
    pins: list[KiCadPin]
    electrical_specs: dict  # {param_name: {min, typ, max, unit}}
    validation_status: Literal["PASS", "WARN", "BLOCKED"]
    validation_message: Optional[str]


def export_to_kicad(
    datasheet: ComponentDatasheet,
    validation_result: ValidationResult
) -> KiCadExport:
    """
    Convert ComponentDatasheet → KiCad export format.
    
    Strategy:
    1. Extract pins from datasheet
    2. Map pin types to KiCad convention (power → VCC, ground → GND, etc.)
    3. Build electrical specs dict
    4. Determine status (PASS / WARN / BLOCKED)
    
    Args:
        datasheet: From Phase 3
        validation_result: From validator
        
    Returns:
        KiCadExport ready for symbol generation
    """
    
    # Convert pins
    kicad_pins = []
    for pin in datasheet.all_pins:
        kicad_pin = KiCadPin(
            pin_number=pin.pin_number,
            pin_name=pin.pin_name,
            pin_type=pin.pin_type,
            net_name=infer_net_name(pin)  # Power → V_CC, Ground → GND, etc.
        )
        kicad_pins.append(kicad_pin)
    
    # Build electrical specs
    electrical_specs = {}
    for param in datasheet.all_parameters:
        electrical_specs[param.name] = {
            "parameter_type": param.parameter_type,
            "min": param.min_value.value if param.min_value else None,
            "typ": param.typ_value.value if param.typ_value else None,
            "max": param.max_value.value if param.max_value else None,
            "unit": param.min_value.unit if param.min_value else "—",
            "confidence": param.avg_confidence(),
        }
    
    # Determine status
    if validation_result.passed:
        status = "PASS"
        msg = None
    elif validation_result.review_required:
        status = "WARN"
        msg = f"{len(validation_result.warnings)} warnings; see review queue"
    else:
        status = "BLOCKED"
        msg = f"{len(validation_result.errors)} critical errors"
    
    export = KiCadExport(
        component_id=datasheet.component_id,
        manufacturer=datasheet.manufacturer or "Unknown",
        package=datasheet.package,
        pins=kicad_pins,
        electrical_specs=electrical_specs,
        validation_status=status,
        validation_message=msg
    )
    
    return export


def infer_net_name(pin: PinDefinition) -> str:
    """Auto-assign net names based on pin type and name."""
    
    if pin.pin_type == "power":
        if "3.3" in pin.pin_name or "V33" in pin.pin_name:
            return "V_3V3"
        elif "5" in pin.pin_name:
            return "V_5V"
        else:
            return "V_CC"
    elif pin.pin_type == "ground":
        return "GND"
    elif pin.pin_type == "clock":
        return "CLK"
    elif pin.pin_type == "reset":
        return "RST"
    else:
        return pin.pin_name.upper()
```

**Tests:**
```python
def test_kicad_export_from_valid_datasheet():
    """Export valid datasheet to KiCad format."""
    datasheet = mock_tlv7021_component_datasheet()
    validation = ValidationResult(
        component_id="TLV7021",
        passed=True,
        errors=[],
        warnings=[],
        review_required=False,
        confidence_score=0.95
    )
    export = export_to_kicad(datasheet, validation)
    
    assert export.component_id == "TLV7021"
    assert len(export.pins) == 8
    assert export.validation_status == "PASS"
    assert "V_CC" in [p.pin_name for p in export.pins]

def test_kicad_export_status_warn():
    """Export with warnings shows WARN status."""
    datasheet = mock_tlv7021_component_datasheet()
    validation = ValidationResult(
        component_id="TLV7021",
        passed=True,
        errors=[],
        warnings=[ValidationError(level="WARNING", param_name="I_CC", message="Low confidence")],
        review_required=True,
        confidence_score=0.80
    )
    export = export_to_kicad(datasheet, validation)
    assert export.validation_status == "WARN"

def test_kicad_export_status_blocked():
    """Export with critical errors shows BLOCKED status."""
    datasheet = mock_tlv7021_component_datasheet()
    validation = ValidationResult(
        component_id="TLV7021",
        passed=False,
        errors=[ValidationError(level="CRITICAL", param_name="V_CC", message="min > max")],
        warnings=[],
        review_required=True,
        confidence_score=0.50
    )
    export = export_to_kicad(datasheet, validation)
    assert export.validation_status == "BLOCKED"
```

---

### 7. `src/phase4_validate/runner.py`

**Orchestrator: Phase 3 → Validation → KiCad → Output**

**Functionality:**
```python
def run_phase4(
    datasheet: ComponentDatasheet,
    config: Config = None
) -> tuple[ValidationResult, KiCadExport]:
    """
    Full Phase 4 pipeline.
    
    Args:
        datasheet: From Phase 3
        config: Config object
        
    Returns:
        (ValidationResult, KiCadExport)
    """
    
    config = config or get_config()
    
    logger.info(f"Phase 4: Validating & exporting {datasheet.component_id}")
    
    # Run validation
    validation = run_full_validation(datasheet, config)
    logger.info(f"  Validation: {validation.passed}, confidence={validation.confidence_score:.2%}")
    
    # Export to KiCad
    export = export_to_kicad(datasheet, validation)
    logger.info(f"  KiCad export: {export.validation_status}")
    
    return validation, export


def save_validation_result(
    validation: ValidationResult,
    output_path: Path
) -> None:
    """Save validation to JSON file."""
    with open(output_path, "w") as f:
        json.dump(validation.model_dump(), f, indent=2)
    logger.info(f"Validation result saved: {output_path}")


def save_kicad_export(
    export: KiCadExport,
    output_path: Path
) -> None:
    """Save KiCad export to JSON file."""
    with open(output_path, "w") as f:
        json.dump(export.model_dump(), f, indent=2)
    logger.info(f"KiCad export saved: {output_path}")
```

**Tests:**
```python
def test_run_phase4_end_to_end():
    """Full Phase 4 pipeline on mock datasheet."""
    phase3_out = mock_tlv7021_component_datasheet()
    validation, export = run_phase4(phase3_out)
    
    assert validation.component_id == "TLV7021"
    assert export.component_id == "TLV7021"
    assert export.validation_status in ["PASS", "WARN", "BLOCKED"]

def test_run_phase4_all_golden():
    """Phase 4 on all 5 golden components."""
    from tests.fixtures.phase3_mock_outputs import all_golden_phase3_outputs
    
    all_phase3 = all_golden_phase3_outputs()
    for component_id, datasheet in all_phase3.items():
        validation, export = run_phase4(datasheet)
        assert validation is not None
        assert export is not None
        logger.info(f"{component_id}: {export.validation_status}")
```

---

## Exit Criteria

- ✅ All 7 modules implemented (ordering, sanity, cross-param, abs-max, validator, kicad_exporter, runner)
- ✅ 40+ unit tests pass locally
- ✅ Code follows `CODING_STANDARDS_P1.md`
- ✅ Type hints on all functions
- ✅ Docstrings on all public functions
- ✅ Logging on validation steps

---

## Do NOT

- ❌ Run Phase 4 on real PDFs yet (use mocks)
- ❌ Assume all parameters are valid (validate strictly)
- ❌ Skip cross-parameter rules (they catch real errors)
- ❌ Forget abs-max validation (detects swapped tables)
- ❌ Export invalid data (respect BLOCKED status)

---

## Integration Notes (For Later)

When you wire Phase 1→2→3→4 together in `src/pipeline.py`:

```python
def run_full_pipeline(pdf_path: Path, config: Config = None) -> PipelineOutput:
    """End-to-end: Phase 1→2→3→4."""
    
    # Phase 1 (CPU)
    phase1_out = run_phase1(pdf_path, config)
    
    # Phase 2 (GPU or mock)
    phase2_out = run_phase2(phase1_out, config)
    
    # Phase 3 (CPU)
    datasheet = run_phase3(phase2_out, config)
    
    # Phase 4 (CPU)
    validation, export = run_phase4(datasheet, config)
    
    return PipelineOutput(
        datasheet=datasheet,
        validation=validation,
        kicad_export=export
    )
```

---

## Ready?

- Read authority docs first
- Implement in order: 1 → 2 → 3 → 4 → 5 → 6 → 7
- Run tests locally (`pytest tests/unit/test_phase4_*.py`)
- All tests pass on MacBook (no GPU needed)
- Commit to git

**Go!**