# Few-Shot and Chain-of-Thought Prompting in OpenForge

## Application Analysis and Architecture Assessment

**Purpose:** Defines where few-shot prompting and chain-of-thought reasoning apply within the existing OpenForge pipeline, what improvements they produce, and whether they constitute viable architectural alternatives.

**Conclusion upfront:** These are not architectural alternatives. They are precision instruments that improve specific stages of the existing architecture without replacing any of its structural components.

---

## 1. Few-Shot Prompting

### What it is

Few-shot prompting provides the LLM with 2–5 worked examples before asking it to perform a task. The model learns the expected input-output format from the examples rather than from schema description alone. In structured extraction tasks — which is what most of our LLM calls do — few-shot examples consistently raise precision and recall without any code changes.

---

### Application 1 — P1 Phase 3: Semantic Extraction

**Current state:** The Phase 3 extraction prompt describes the `ElectricalParameter` schema and asks Qwen2.5-7B to extract values from grid text. The model understands the schema intellectually but has no demonstration of edge cases: min/typ/max splits, unit aliases, null values, footnote references.

**Few-shot improvement:**

```python
FEW_SHOT_EXTRACTION_EXAMPLES = """
EXAMPLE 1 — Standard min/typ/max row:
Grid cell text: "VCC  Supply Voltage  2.7  4.5  5.5  V"
Correct output:
{
  "parameter_name": "Supply Voltage",
  "symbol": "VCC",
  "value": {
    "min_val": 2.7,
    "typ_val": 4.5,
    "max_val": 5.5,
    "unit": "V",
    "raw_text": "VCC  Supply Voltage  2.7  4.5  5.5  V"
  }
}

EXAMPLE 2 — Typ and max only, no min:
Grid cell text: "IQ  Quiescent Current  —  55  85  µA"
Correct output:
{
  "parameter_name": "Quiescent Current",
  "symbol": "IQ",
  "value": {
    "min_val": null,
    "typ_val": 55.0,
    "max_val": 85.0,
    "unit": "uA",
    "raw_text": "IQ  Quiescent Current  —  55  85  µA"
  }
}

EXAMPLE 3 — Single value, condition qualifier:
Grid cell text: "VOS  Input Offset Voltage  ±0.5  mV  TA = 25°C"
Correct output:
{
  "parameter_name": "Input Offset Voltage",
  "symbol": "VOS",
  "conditions": "TA = 25°C",
  "value": {
    "min_val": -0.5,
    "typ_val": null,
    "max_val": 0.5,
    "unit": "mV",
    "raw_text": "VOS  Input Offset Voltage  ±0.5  mV  TA = 25°C"
  }
}

EXAMPLE 4 — OCR alias for µ:
Grid cell text: "en  Voltage Noise Density  4.5  nV/uHz"
Correct output:
{
  "parameter_name": "Voltage Noise Density",
  "symbol": "en",
  "value": {
    "typ_val": 4.5,
    "unit": "nV/rtHz",
    "raw_text": "en  Voltage Noise Density  4.5  nV/uHz"
  }
}
"""

```

**Expected improvement:** F1 +5–8% on ambiguous cells. The largest gains are on rows with OCR artifacts, unusual unit strings, and asymmetric min/max notation. These are exactly the cases the Phase 4 validator catches as errors — fewer Phase 4 failures means fewer items in the human review queue.

**Implementation:** Add `FEW_SHOT_EXTRACTION_EXAMPLES` as a constant to `src/datasheet/phase3_extract/prompt_templates.py`and prepend it to every section-type-specific system prompt. Zero architectural change required.

---

### Application 2 — P1 Phase 5: Layout Section Extraction

**Current state:** The Phase 5 prompt instructs the model to recognize spatial language patterns and output `PlacementConstraint` objects. Without examples, the model applies inconsistent judgment about what constitutes a hard constraint vs a soft recommendation.

**Few-shot improvement:**

```python
FEW_SHOT_LAYOUT_EXAMPLES = """
EXAMPLE 1 — Proximity constraint, hard:
Source sentence: "Place C_IN within 2mm of the VIN pin."
Correct output:
{
  "constraint_type": "proximity",
  "subject": "C_IN",
  "relative_to": "U1.VIN",
  "relative_to_type": "pin",
  "max_distance_mm": 2.0,
  "hard": true,
  "confidence": 0.96
}

EXAMPLE 2 — Keepout constraint:
Source sentence: "Maintain a copper pour keepout of at least 5mm around the RF output pin."
Correct output:
{
  "constraint_type": "keepout",
  "subject": "RF_OUT",
  "relative_to": "U1.RF_OUT",
  "relative_to_type": "pin",
  "min_distance_mm": 5.0,
  "hard": true,
  "confidence": 0.94
}

EXAMPLE 3 — Soft recommendation:
Source sentence: "It is recommended to place the decoupling capacitor near the supply pin."
Correct output:
{
  "constraint_type": "proximity",
  "subject": "C_BYPASS",
  "relative_to": "supply_pin",
  "relative_to_type": "pin",
  "hard": false,
  "confidence": 0.82
}

EXAMPLE 4 — Routing constraint:
Source sentence: "Keep the SW node trace as short as possible."
Correct output:
{
  "constraint_type": "routing",
  "subject": "SW_NODE",
  "relative_to": "board",
  "relative_to_type": "board_edge",
  "hard": false,
  "confidence": 0.88
}
"""

```

**Expected improvement:** Recall +10% on spatial language. The largest gains are on soft recommendations — the model currently over-classifies `hard=true` on sentences using "should" rather than "must." Examples demonstrating the hard vs soft distinction calibrate this correctly.

---

### Application 3 — Pin Normalizer LLM Fallback

**Current state:** The Tier 2 LLM fallback in `pin_normalizer/llm_fallback.py` provides the canonical vocabulary as a list and asks the model to select the best match. Ambiguous cases — `CLK`, `OUT`, `IN+`, `DATA` — are inconsistently handled.

**Few-shot improvement:**

```python
FEW_SHOT_PIN_EXAMPLES = """
EXAMPLE 1: "SCLK" → SPI_CLOCK (confidence: 1.0)
Reasoning: SCLK is a standard abbreviation for SPI Serial CLock.

EXAMPLE 2: "CLK" with adjacent pins ["SDA", "SCL"] → I2C_CLOCK (confidence: 0.92)
Reasoning: Context of SDA and SCL pins indicates I2C protocol. CLK in I2C context = SCL.

EXAMPLE 3: "CLK" with adjacent pins ["MOSI", "MISO", "CS"] → SPI_CLOCK (confidence: 0.94)
Reasoning: MOSI/MISO/CS are SPI-specific. CLK here is the SPI clock.

EXAMPLE 4: "OUT" on op-amp → ANALOG_OUTPUT (confidence: 0.90)
Reasoning: Single output pin on op-amp is the analog output.

EXAMPLE 5: "!CS" → SPI_CHIP_SELECT (confidence: 0.97)
Reasoning: Active-low prefix (!) does not change function. CS = Chip Select.

EXAMPLE 6: "AGND" → POWER_GROUND (confidence: 1.0)
Reasoning: AGND (Analog Ground) normalizes to POWER_GROUND, same net as DGND.
"""

```

**Expected improvement:** Accuracy +8% on ambiguous pin names in the LLM fallback path. This directly reduces the count of `normalized_function=None` pins that reach the schematic synthesizer as unresolved.

---

## 2. Chain-of-Thought Prompting

### What it is

Chain-of-thought prompting instructs the LLM to articulate its reasoning step by step before committing to an answer. For tasks that require multi-step inference — which are common in electronics domain reasoning — CoT significantly improves accuracy because the model catches its own errors mid-chain and the intermediate steps are visible for verification.

---

### Application 1 — Stage 2: Requirement Completion Engine

**This is the highest-value CoT application in the entire system.**

**Current state:** The completion engine receives an `ImprovedIntentDict` and outputs implied requirements. Without CoT, the model produces inferences in a single pass. The reasoning is implicit and the model has no opportunity to self-correct on domain-specific reasoning chains.

**CoT improvement:**

The Stage 2 system prompt is extended with an explicit reasoning instruction:

```
Before listing implied requirements, reason through the circuit topology
step by step. For each implied requirement:

Step 1: State the specific explicit constraint that triggers this inference.
Step 2: Describe the circuit-level mechanism that creates the dependency.
Step 3: State the implied requirement.
Step 4: Assign confidence based on how universal this dependency is.
Step 5: Only then commit to including it in the output.

Show all four steps explicitly in a "reasoning" field before writing
the final requirement. This reasoning chain becomes part of the output
and must be traceable to a specific engineering principle.

```

**Example — without CoT:**

```json
{
  "requirement": "Precision voltage reference required",
  "confidence": 0.98,
  "reasoning": "Libbrecht-Hall design requires a reference."
}

```

**Example — with CoT:**

```json
{
  "requirement": "Precision voltage reference required for current setpoint",
  "confidence": 0.98,
  "reasoning": "Step 1: Explicit constraint: 'libbrecht hall design' + 'highly stable'. Step 2: The Libbrecht-Hall topology regulates output current by comparing the voltage across a sense resistor to a voltage reference. The absolute accuracy of the output current is therefore equal to the absolute accuracy of the voltage reference — a 10ppm reference error produces a 10ppm current error. Step 3: 'Highly stable' implies <10ppm/°C drift for lab instrumentation. A standard voltage divider from supply has 50–100ppm/°C. Therefore a dedicated precision voltage reference is required. Step 4: This dependency is universal for all Libbrecht-Hall implementations — confidence 0.98. Step 5: Include."
}

```

**Two concrete benefits:**

The `reasoning` field in `ImpliedRequirement` becomes a genuine engineering audit trail, not a template string. When a DRDO scientist asks "why is this component in my design," the system can produce a traceable, first-principles answer.

The model catches its own reasoning errors before committing. On obscure topologies where the model's training data is thin, CoT forces it to articulate the mechanism, which surfaces gaps in its knowledge as "I am uncertain about step 2" rather than confidently producing a wrong answer.

---

### Application 2 — BOM Generator: Component Selection Justification

**Current state:** `justification.py` in `src/bom/` produces template string justifications: `"buck_converter required for 3.3V buck converter design. Source: KG-2:TI_AN-1294."`

**CoT improvement:**

Replace the template with a lightweight CoT-prompted call:

```python
COT_JUSTIFICATION_PROMPT = """
A PCB designer has requested: "{raw_prompt}"

The component {component_type} ({specific_part}) has been selected.
The design methodology is {methodology}.

In 1–2 sentences, explain why this specific component is required for this design.
Start with the engineering reason, not the component name.
Reference the design requirement that drives this selection.
"""

```

**Result:**

- Before: `"buck_converter required for design. Source: KG-2."`
- After: `"A synchronous buck converter is required to step the 12V input down to 3.3V at up to 1A with >90% efficiency. The TPS62933 is selected for its 3MHz switching frequency which allows small passive components and its integrated power MOSFETs which eliminate external switch components."`

This directly affects the engineering report quality and the traceability that DRDO requires.

---

### Application 3 — Intent Parser: Methodology Classification on Edge Cases

**Current state:** The methodology classifier uses keyword matching as a deterministic override. Edge cases — a mixed-signal design that mentions 2.4GHz for frequency specification but is not an RF board, or a power design that includes a microcontroller — are misclassified because the keyword match fires on a secondary feature.

**CoT improvement:**

Add a reasoning step to the methodology classification:

```
Before selecting a design_methodology, reason through the dominant 
design challenge in this prompt:

Step 1: List all methodology indicators present in the prompt.
Step 2: Identify which methodology governs the PRIMARY design challenge 
        (the feature that most constrains component selection and PCB layout).
Step 3: Note any secondary methodologies that apply to subsections only.
Step 4: Select the PRIMARY methodology.

A 100mA precision current source that operates at DC with an op-amp 
is mixed_signal even if it mentions a 2.4GHz frequency as a measurement 
target — the RF methodology does not govern component selection here.

```

**Expected improvement:** Misclassification rate on ambiguous prompts drops from approximately 12% to below 4% based on similar CoT classification benchmarks on domain-specific prompts.

---

### Application 4 — Phase 4 Validator: Ambiguous Physics Violations

**Current state:** The Phase 4 rule engine applies deterministic checks. Some violations are genuinely ambiguous — a part where min > typ in the datasheet may be a printing error, a non-standard measurement condition, or a genuine OCR failure. Currently all violations of the same rule type are treated identically.

**CoT improvement (lightweight):**

For violations flagged as WARNING (not CRITICAL), add a single CoT reasoning step:

```
This parameter violates the min ≤ typ rule:
  Parameter: {parameter_name}, min={min_val}, typ={typ_val}
  Source: page {page}, table {table}

Before flagging for human review, consider:
Step 1: Is this a standard measurement condition qualifier that could 
        explain the apparent violation?
Step 2: Is this a known datasheet erratum pattern for this manufacturer?
Step 3: Should this be CRITICAL (block) or WARNING (review)?

```

This adds one LLM call per ambiguous violation but reduces false-positive CRITICAL flags that unnecessarily block the pipeline.

---

## 3. As Alternative Architectures — Why They Are Not

This question deserves a direct answer. Could you build the entire PCB intelligence system using only few-shot + CoT prompting, replacing the knowledge graph, structured extraction pipeline, and typed schemas?

Technically possible. Practically wrong for three specific reasons that are non-negotiable for the DRDO use case.

### Reason 1: The hallucination problem does not go away

Few-shot and CoT improve the quality of reasoning over knowledge already in the model's weights. They do not ground outputs in authoritative sources. If you ask a CoT-prompted LLM to select a zero-drift op-amp for a 100mA current source, it will produce a confident, well-reasoned, step-by-step answer that may cite a real part number with invented noise specifications. The knowledge graph approach grounds every claim in a parsed source document with a confidence score and a page number. CoT cannot replicate that grounding.

### Reason 2: Reproducibility breaks

A CoT-generated BOM for the same prompt produces different outputs on different runs due to LLM non-determinism. Our pipeline produces deterministic outputs for the same input because the serialization is rule-based and the KG traversal is deterministic. For a defense application where two engineers must reproduce and verify each other's results, non-determinism is not acceptable.

### Reason 3: Traceability is lost

DRDO requires knowing exactly why each component is in a design. "The model reasoned it was appropriate" is not a valid justification for a defense-grade PCB. "TI SBOA327 application note, page 4, Table 2, extracted at 0.94 confidence by P1 Phase 3" is. The knowledge graph is a traceability mechanism as much as it is a retrieval mechanism. CoT reasoning chains are plausible but unverifiable. KG-sourced citations are verifiable against the source document.

---

## 4. Implementation Priority

Add these improvements after the GPU validation run confirms where accuracy gaps are. Do not add them speculatively.


| Technique | Stage                             | Expected gain                         | Effort  | Priority                          |
| --------- | --------------------------------- | ------------------------------------- | ------- | --------------------------------- |
| Few-shot  | P1 Phase 3 extraction             | F1 +5–8%                              | 2 hours | HIGH — do before corpus ingestion |
| Few-shot  | P1 Phase 5 layout extraction      | Recall +10%                           | 2 hours | HIGH — do before corpus ingestion |
| Few-shot  | Pin normalizer fallback           | Accuracy +8%                          | 1 hour  | MEDIUM                            |
| CoT       | Stage 2 completion engine         | Deeper inferences, better calibration | 4 hours | HIGH — do before DRDO demo        |
| CoT       | BOM justification generator       | Engineering-quality justifications    | 3 hours | MEDIUM                            |
| CoT       | Methodology classifier edge cases | Misclassification -8%                 | 2 hours | MEDIUM                            |
| CoT       | Phase 4 ambiguous violations      | Fewer false-positive CRITICAL flags   | 3 hours | LOW                               |


**Total effort to implement all:** approximately 17 hours of prompt engineering work. No architectural changes. No new modules. No schema changes. These are prompt text modifications in existing files.

---

## 5. Where These Techniques Do Not Help

For completeness: the stages where few-shot and CoT add no value because the task is already deterministic.

- **P1 Phase 1 (DLA):** YOLOv8n is a vision model, not an LLM. Few-shot does not apply.
- **P1 Phase 4 (Validation):** Rule-based engine. CoT does not improve deterministic comparisons.
- **Schematic Synthesizer:** Net assignment is algorithmic. CoT adds latency with no benefit.
- **Layout Engine:** Constraint satisfaction. Deterministic.
- **NIR Builder:** Assembly from typed objects. No LLM involved.
- **tscircuit/KiCad Serializers:** String formatting. Deterministic.

The LLM is a tool for language and reasoning tasks. Everything else in the pipeline is better served by deterministic code.

---

*This document should be updated after the GPU validation run with actual measured accuracy improvements from implementing the high-priority items above.*

## Application Analysis and Architecture Assessment

**Purpose:** Defines where few-shot prompting and chain-of-thought reasoning apply within the existing OpenForge pipeline, what improvements they produce, and whether they constitute viable architectural alternatives.

**Conclusion upfront:** These are not architectural alternatives. They are precision instruments that improve specific stages of the existing architecture without replacing any of its structural components.

---

## 1. Few-Shot Prompting

### What it is

Few-shot prompting provides the LLM with 2–5 worked examples before asking it to perform a task. The model learns the expected input-output format from the examples rather than from schema description alone. In structured extraction tasks — which is what most of our LLM calls do — few-shot examples consistently raise precision and recall without any code changes.

---

### Application 1 — P1 Phase 3: Semantic Extraction

**Current state:** The Phase 3 extraction prompt describes the `ElectricalParameter` schema and asks Qwen2.5-7B to extract values from grid text. The model understands the schema intellectually but has no demonstration of edge cases: min/typ/max splits, unit aliases, null values, footnote references.

**Few-shot improvement:**

```python
FEW_SHOT_EXTRACTION_EXAMPLES = """
EXAMPLE 1 — Standard min/typ/max row:
Grid cell text: "VCC  Supply Voltage  2.7  4.5  5.5  V"
Correct output:
{
  "parameter_name": "Supply Voltage",
  "symbol": "VCC",
  "value": {
    "min_val": 2.7,
    "typ_val": 4.5,
    "max_val": 5.5,
    "unit": "V",
    "raw_text": "VCC  Supply Voltage  2.7  4.5  5.5  V"
  }
}

EXAMPLE 2 — Typ and max only, no min:
Grid cell text: "IQ  Quiescent Current  —  55  85  µA"
Correct output:
{
  "parameter_name": "Quiescent Current",
  "symbol": "IQ",
  "value": {
    "min_val": null,
    "typ_val": 55.0,
    "max_val": 85.0,
    "unit": "uA",
    "raw_text": "IQ  Quiescent Current  —  55  85  µA"
  }
}

EXAMPLE 3 — Single value, condition qualifier:
Grid cell text: "VOS  Input Offset Voltage  ±0.5  mV  TA = 25°C"
Correct output:
{
  "parameter_name": "Input Offset Voltage",
  "symbol": "VOS",
  "conditions": "TA = 25°C",
  "value": {
    "min_val": -0.5,
    "typ_val": null,
    "max_val": 0.5,
    "unit": "mV",
    "raw_text": "VOS  Input Offset Voltage  ±0.5  mV  TA = 25°C"
  }
}

EXAMPLE 4 — OCR alias for µ:
Grid cell text: "en  Voltage Noise Density  4.5  nV/uHz"
Correct output:
{
  "parameter_name": "Voltage Noise Density",
  "symbol": "en",
  "value": {
    "typ_val": 4.5,
    "unit": "nV/rtHz",
    "raw_text": "en  Voltage Noise Density  4.5  nV/uHz"
  }
}
"""
```

**Expected improvement:** F1 +5–8% on ambiguous cells. The largest gains are on rows with OCR artifacts, unusual unit strings, and asymmetric min/max notation. These are exactly the cases the Phase 4 validator catches as errors — fewer Phase 4 failures means fewer items in the human review queue.

**Implementation:** Add `FEW_SHOT_EXTRACTION_EXAMPLES` as a constant to `src/datasheet/phase3_extract/prompt_templates.py` and prepend it to every section-type-specific system prompt. Zero architectural change required.

---

### Application 2 — P1 Phase 5: Layout Section Extraction

**Current state:** The Phase 5 prompt instructs the model to recognize spatial language patterns and output `PlacementConstraint` objects. Without examples, the model applies inconsistent judgment about what constitutes a hard constraint vs a soft recommendation.

**Few-shot improvement:**

```python
FEW_SHOT_LAYOUT_EXAMPLES = """
EXAMPLE 1 — Proximity constraint, hard:
Source sentence: "Place C_IN within 2mm of the VIN pin."
Correct output:
{
  "constraint_type": "proximity",
  "subject": "C_IN",
  "relative_to": "U1.VIN",
  "relative_to_type": "pin",
  "max_distance_mm": 2.0,
  "hard": true,
  "confidence": 0.96
}

EXAMPLE 2 — Keepout constraint:
Source sentence: "Maintain a copper pour keepout of at least 5mm around the RF output pin."
Correct output:
{
  "constraint_type": "keepout",
  "subject": "RF_OUT",
  "relative_to": "U1.RF_OUT",
  "relative_to_type": "pin",
  "min_distance_mm": 5.0,
  "hard": true,
  "confidence": 0.94
}

EXAMPLE 3 — Soft recommendation:
Source sentence: "It is recommended to place the decoupling capacitor near the supply pin."
Correct output:
{
  "constraint_type": "proximity",
  "subject": "C_BYPASS",
  "relative_to": "supply_pin",
  "relative_to_type": "pin",
  "hard": false,
  "confidence": 0.82
}

EXAMPLE 4 — Routing constraint:
Source sentence: "Keep the SW node trace as short as possible."
Correct output:
{
  "constraint_type": "routing",
  "subject": "SW_NODE",
  "relative_to": "board",
  "relative_to_type": "board_edge",
  "hard": false,
  "confidence": 0.88
}
"""
```

**Expected improvement:** Recall +10% on spatial language. The largest gains are on soft recommendations — the model currently over-classifies `hard=true` on sentences using "should" rather than "must." Examples demonstrating the hard vs soft distinction calibrate this correctly.

---

### Application 3 — Pin Normalizer LLM Fallback

**Current state:** The Tier 2 LLM fallback in `pin_normalizer/llm_fallback.py` provides the canonical vocabulary as a list and asks the model to select the best match. Ambiguous cases — `CLK`, `OUT`, `IN+`, `DATA` — are inconsistently handled.

**Few-shot improvement:**

```python
FEW_SHOT_PIN_EXAMPLES = """
EXAMPLE 1: "SCLK" → SPI_CLOCK (confidence: 1.0)
Reasoning: SCLK is a standard abbreviation for SPI Serial CLock.

EXAMPLE 2: "CLK" with adjacent pins ["SDA", "SCL"] → I2C_CLOCK (confidence: 0.92)
Reasoning: Context of SDA and SCL pins indicates I2C protocol. CLK in I2C context = SCL.

EXAMPLE 3: "CLK" with adjacent pins ["MOSI", "MISO", "CS"] → SPI_CLOCK (confidence: 0.94)
Reasoning: MOSI/MISO/CS are SPI-specific. CLK here is the SPI clock.

EXAMPLE 4: "OUT" on op-amp → ANALOG_OUTPUT (confidence: 0.90)
Reasoning: Single output pin on op-amp is the analog output.

EXAMPLE 5: "!CS" → SPI_CHIP_SELECT (confidence: 0.97)
Reasoning: Active-low prefix (!) does not change function. CS = Chip Select.

EXAMPLE 6: "AGND" → POWER_GROUND (confidence: 1.0)
Reasoning: AGND (Analog Ground) normalizes to POWER_GROUND, same net as DGND.
"""
```

**Expected improvement:** Accuracy +8% on ambiguous pin names in the LLM fallback path. This directly reduces the count of `normalized_function=None` pins that reach the schematic synthesizer as unresolved.

---

## 2. Chain-of-Thought Prompting

### What it is

Chain-of-thought prompting instructs the LLM to articulate its reasoning step by step before committing to an answer. For tasks that require multi-step inference — which are common in electronics domain reasoning — CoT significantly improves accuracy because the model catches its own errors mid-chain and the intermediate steps are visible for verification.

---

### Application 1 — Stage 2: Requirement Completion Engine

**This is the highest-value CoT application in the entire system.**

**Current state:** The completion engine receives an `ImprovedIntentDict` and outputs implied requirements. Without CoT, the model produces inferences in a single pass. The reasoning is implicit and the model has no opportunity to self-correct on domain-specific reasoning chains.

**CoT improvement:**

The Stage 2 system prompt is extended with an explicit reasoning instruction:

```
Before listing implied requirements, reason through the circuit topology
step by step. For each implied requirement:

Step 1: State the specific explicit constraint that triggers this inference.
Step 2: Describe the circuit-level mechanism that creates the dependency.
Step 3: State the implied requirement.
Step 4: Assign confidence based on how universal this dependency is.
Step 5: Only then commit to including it in the output.

Show all four steps explicitly in a "reasoning" field before writing
the final requirement. This reasoning chain becomes part of the output
and must be traceable to a specific engineering principle.
```

**Example — without CoT:**

```json
{
  "requirement": "Precision voltage reference required",
  "confidence": 0.98,
  "reasoning": "Libbrecht-Hall design requires a reference."
}
```

**Example — with CoT:**

```json
{
  "requirement": "Precision voltage reference required for current setpoint",
  "confidence": 0.98,
  "reasoning": "Step 1: Explicit constraint: 'libbrecht hall design' + 'highly stable'. Step 2: The Libbrecht-Hall topology regulates output current by comparing the voltage across a sense resistor to a voltage reference. The absolute accuracy of the output current is therefore equal to the absolute accuracy of the voltage reference — a 10ppm reference error produces a 10ppm current error. Step 3: 'Highly stable' implies <10ppm/°C drift for lab instrumentation. A standard voltage divider from supply has 50–100ppm/°C. Therefore a dedicated precision voltage reference is required. Step 4: This dependency is universal for all Libbrecht-Hall implementations — confidence 0.98. Step 5: Include."
}
```

**Two concrete benefits:**

The `reasoning` field in `ImpliedRequirement` becomes a genuine engineering audit trail, not a template string. When a DRDO scientist asks "why is this component in my design," the system can produce a traceable, first-principles answer.

The model catches its own reasoning errors before committing. On obscure topologies where the model's training data is thin, CoT forces it to articulate the mechanism, which surfaces gaps in its knowledge as "I am uncertain about step 2" rather than confidently producing a wrong answer.

---

### Application 2 — BOM Generator: Component Selection Justification

**Current state:** `justification.py` in `src/bom/` produces template string justifications:
`"buck_converter required for 3.3V buck converter design. Source: KG-2:TI_AN-1294."`

**CoT improvement:**

Replace the template with a lightweight CoT-prompted call:

```python
COT_JUSTIFICATION_PROMPT = """
A PCB designer has requested: "{raw_prompt}"

The component {component_type} ({specific_part}) has been selected.
The design methodology is {methodology}.

In 1–2 sentences, explain why this specific component is required for this design.
Start with the engineering reason, not the component name.
Reference the design requirement that drives this selection.
"""
```

**Result:**

- Before: `"buck_converter required for design. Source: KG-2."`
- After: `"A synchronous buck converter is required to step the 12V input down to 3.3V at up to 1A with >90% efficiency. The TPS62933 is selected for its 3MHz switching frequency which allows small passive components and its integrated power MOSFETs which eliminate external switch components."`

This directly affects the engineering report quality and the traceability that DRDO requires.

---

### Application 3 — Intent Parser: Methodology Classification on Edge Cases

**Current state:** The methodology classifier uses keyword matching as a deterministic override. Edge cases — a mixed-signal design that mentions 2.4GHz for frequency specification but is not an RF board, or a power design that includes a microcontroller — are misclassified because the keyword match fires on a secondary feature.

**CoT improvement:**

Add a reasoning step to the methodology classification:

```
Before selecting a design_methodology, reason through the dominant 
design challenge in this prompt:

Step 1: List all methodology indicators present in the prompt.
Step 2: Identify which methodology governs the PRIMARY design challenge 
        (the feature that most constrains component selection and PCB layout).
Step 3: Note any secondary methodologies that apply to subsections only.
Step 4: Select the PRIMARY methodology.

A 100mA precision current source that operates at DC with an op-amp 
is mixed_signal even if it mentions a 2.4GHz frequency as a measurement 
target — the RF methodology does not govern component selection here.
```

**Expected improvement:** Misclassification rate on ambiguous prompts drops from approximately 12% to below 4% based on similar CoT classification benchmarks on domain-specific prompts.

---

### Application 4 — Phase 4 Validator: Ambiguous Physics Violations

**Current state:** The Phase 4 rule engine applies deterministic checks. Some violations are genuinely ambiguous — a part where min > typ in the datasheet may be a printing error, a non-standard measurement condition, or a genuine OCR failure. Currently all violations of the same rule type are treated identically.

**CoT improvement (lightweight):**

For violations flagged as WARNING (not CRITICAL), add a single CoT reasoning step:

```
This parameter violates the min ≤ typ rule:
  Parameter: {parameter_name}, min={min_val}, typ={typ_val}
  Source: page {page}, table {table}

Before flagging for human review, consider:
Step 1: Is this a standard measurement condition qualifier that could 
        explain the apparent violation?
Step 2: Is this a known datasheet erratum pattern for this manufacturer?
Step 3: Should this be CRITICAL (block) or WARNING (review)?
```

This adds one LLM call per ambiguous violation but reduces false-positive CRITICAL flags that unnecessarily block the pipeline.

---

## 3. As Alternative Architectures — Why They Are Not

This question deserves a direct answer. Could you build the entire PCB intelligence system using only few-shot + CoT prompting, replacing the knowledge graph, structured extraction pipeline, and typed schemas?

Technically possible. Practically wrong for three specific reasons that are non-negotiable for the DRDO use case.

### Reason 1: The hallucination problem does not go away

Few-shot and CoT improve the quality of reasoning over knowledge already in the model's weights. They do not ground outputs in authoritative sources. If you ask a CoT-prompted LLM to select a zero-drift op-amp for a 100mA current source, it will produce a confident, well-reasoned, step-by-step answer that may cite a real part number with invented noise specifications. The knowledge graph approach grounds every claim in a parsed source document with a confidence score and a page number. CoT cannot replicate that grounding.

### Reason 2: Reproducibility breaks

A CoT-generated BOM for the same prompt produces different outputs on different runs due to LLM non-determinism. Our pipeline produces deterministic outputs for the same input because the serialization is rule-based and the KG traversal is deterministic. For a defense application where two engineers must reproduce and verify each other's results, non-determinism is not acceptable.

### Reason 3: Traceability is lost

DRDO requires knowing exactly why each component is in a design. "The model reasoned it was appropriate" is not a valid justification for a defense-grade PCB. "TI SBOA327 application note, page 4, Table 2, extracted at 0.94 confidence by P1 Phase 3" is. The knowledge graph is a traceability mechanism as much as it is a retrieval mechanism. CoT reasoning chains are plausible but unverifiable. KG-sourced citations are verifiable against the source document.

---

## 4. Implementation Priority

Add these improvements after the GPU validation run confirms where accuracy gaps are. Do not add them speculatively.


| Technique | Stage                             | Expected gain                         | Effort  | Priority                          |
| --------- | --------------------------------- | ------------------------------------- | ------- | --------------------------------- |
| Few-shot  | P1 Phase 3 extraction             | F1 +5–8%                              | 2 hours | HIGH — do before corpus ingestion |
| Few-shot  | P1 Phase 5 layout extraction      | Recall +10%                           | 2 hours | HIGH — do before corpus ingestion |
| Few-shot  | Pin normalizer fallback           | Accuracy +8%                          | 1 hour  | MEDIUM                            |
| CoT       | Stage 2 completion engine         | Deeper inferences, better calibration | 4 hours | HIGH — do before DRDO demo        |
| CoT       | BOM justification generator       | Engineering-quality justifications    | 3 hours | MEDIUM                            |
| CoT       | Methodology classifier edge cases | Misclassification -8%                 | 2 hours | MEDIUM                            |
| CoT       | Phase 4 ambiguous violations      | Fewer false-positive CRITICAL flags   | 3 hours | LOW                               |


**Total effort to implement all:** approximately 17 hours of prompt engineering work. No architectural changes. No new modules. No schema changes. These are prompt text modifications in existing files.

---

## 5. Where These Techniques Do Not Help

For completeness: the stages where few-shot and CoT add no value because the task is already deterministic.

- **P1 Phase 1 (DLA):** YOLOv8n is a vision model, not an LLM. Few-shot does not apply.
- **P1 Phase 4 (Validation):** Rule-based engine. CoT does not improve deterministic comparisons.
- **Schematic Synthesizer:** Net assignment is algorithmic. CoT adds latency with no benefit.
- **Layout Engine:** Constraint satisfaction. Deterministic.
- **NIR Builder:** Assembly from typed objects. No LLM involved.
- **tscircuit/KiCad Serializers:** String formatting. Deterministic.

The LLM is a tool for language and reasoning tasks. Everything else in the pipeline is better served by deterministic code.

---

*This document should be updated after the GPU validation run with actual measured accuracy improvements from implementing the high-priority items above.*