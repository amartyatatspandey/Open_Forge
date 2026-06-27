# Q2 — Requirement Completion Engine

## Purpose

The intent parser (Stage 1) extracts what the engineer explicitly stated. The requirement completion engine (Stage 2) reasons about what they did not state but must be true given what they did state. It uses domain knowledge to fill gaps, detect contradictions, and surface implied engineering requirements before the design pipeline runs.

This is the difference between a system that returns "I cannot find a zero-drift op-amp with these specs" and one that proactively tells you "your design also requires a precision voltage reference, low-noise LDOs, and Kelvin-connected sense resistors — here is why."

---

## Architecture

```
Stage 1 Output (ImprovedIntentDict v2)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 2: Requirement Completion Engine                  │
│                                                         │
│  Input:  ImprovedIntentDict v2                          │
│  Model:  Qwen 3.5 397B (cloud) / Qwen2.5-72B (local)  │
│  Method: Structured prompting + Instructor enforcement   │
│                                                         │
│  Substeps:                                              │
│  1. Domain knowledge injection                          │
│  2. Implication reasoning                               │
│  3. Contradiction detection                             │
│  4. Quantification of vague specs                       │
│  5. Missing spec identification                         │
│  6. Confidence scoring per inferred requirement         │
│                                                         │
│  Output: RequirementCompletionResult                    │
└─────────────────────────────────────────────────────────┘
        │
        ▼
Merged ImprovedIntentDict v2
(implied_requirements populated, missing_critical_specs filled)
```

---

## System Prompt Design

The system prompt for Stage 2 has four sections:

### Section 1 — Role and scope
```
You are a senior electronics design engineer with deep expertise in precision
analog circuits, low-noise design, RF systems, and power electronics.

Your task is to analyze a structured PCB design intent and:
1. Identify all implied engineering requirements not explicitly stated
2. Quantify vague specifications into engineering values where possible
3. Detect contradictions between stated requirements
4. Identify missing specifications that are critical for design completion
5. Assign confidence scores to all inferences

You reason from first principles and domain knowledge, not pattern matching.
Every inference must have a traceable reasoning chain.
```

### Section 2 — Domain knowledge injection (dynamic, based on goal_topology)

For `goal_topology = "libbrecht_hall"`:
```
Relevant domain knowledge for Libbrecht-Hall current source design:

TOPOLOGY: The Libbrecht-Hall current source uses a high-gain feedback loop
with a precision sense resistor to regulate current. Key circuit elements:
- Error amplifier (op-amp) comparing setpoint to voltage across sense resistor
- Power transistor (BJT or MOSFET) as the current-passing element
- Precision sense resistor (determines noise floor and accuracy)
- Voltage setpoint reference (determines absolute accuracy)
- Compensation network (determines stability and bandwidth)

NOISE SOURCES in order of typical dominance:
1. Sense resistor Johnson noise: V_n = sqrt(4kTRΔf)
2. Op-amp input voltage noise (e_n): referred to output as e_n/R_sense
3. Op-amp input current noise (i_n): directly adds to output noise
4. Reference voltage noise: appears at output 1:1
5. Power supply noise: appears at output through PSRR

IMPLIED REQUIREMENTS for any Libbrecht-Hall design:
- Precision voltage reference (for setpoint) — accuracy determines output accuracy
- Low-noise LDO for op-amp supply (supply noise → output noise via PSRR)
- Kelvin connection on sense resistor (eliminates lead resistance error)
- Matched resistor pairs for voltage dividers (eliminates tempco mismatch)
- Guard ring on PCB around sense node (eliminates leakage)
- Low-inductance bypass capacitors on supply rails
```

This section is loaded dynamically from a domain knowledge YAML file keyed by `goal_topology`. This is the most important part of the system — the quality of inferences is only as good as the domain knowledge injected.

### Section 3 — Output schema instruction

```
Return your analysis as a JSON object conforming exactly to this schema:
{
  "implied_requirements": [
    {
      "requirement": "string — what is required",
      "component_implication": "string or null — what component this maps to",
      "reasoning": "string — why this is implied (cite the specific constraint)",
      "confidence": 0.0 to 1.0,
      "source_constraint": "string — which explicit constraint implies this",
      "priority": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    }
  ],
  "quantified_specs": [
    {
      "original_text": "string — the vague spec",
      "quantified_value": "string — the engineering value",
      "unit": "string",
      "reasoning": "string",
      "confidence": 0.0 to 1.0
    }
  ],
  "missing_critical_specs": ["list of strings"],
  "contradictions": [
    {
      "constraint_a": "string",
      "constraint_b": "string",
      "description": "string — why they conflict",
      "severity": "CRITICAL" | "WARNING",
      "suggested_resolution": "string or null"
    }
  ],
  "assumptions": [
    {
      "assumption": "string",
      "reasoning": "string",
      "confidence": 0.0 to 1.0
    }
  ]
}
```

### Section 4 — Reasoning instructions
```
For each implied requirement:
- Start from a specific explicit constraint
- Apply domain knowledge to derive the implication
- Assign confidence based on how universal the implication is:
  * 0.95-1.0: always true for this topology (e.g. Kelvin sensing for precision current source)
  * 0.80-0.94: true for most implementations (e.g. low-noise LDO when ultra-low noise specified)
  * 0.60-0.79: likely given context (e.g. thermal management when >500mW dissipation implied)
  * Below 0.60: do not report

Do not report implications you are not confident about.
Fewer high-confidence implications are more useful than many uncertain ones.
```

---

## Example Output for Prompt 1

```json
{
  "implied_requirements": [
    {
      "requirement": "Precision voltage reference required for current setpoint",
      "component_implication": "precision_voltage_reference",
      "reasoning": "Libbrecht-Hall topology uses a voltage reference to set the output current via the sense resistor. Absolute current accuracy = reference accuracy. Ultra-precision requirement implies reference accuracy must be <10ppm.",
      "confidence": 0.98,
      "source_constraint": "libbrecht hall design + highly stable",
      "priority": "CRITICAL"
    },
    {
      "requirement": "Low-noise LDO for op-amp analog supply rail",
      "component_implication": "low_noise_ldo",
      "reasoning": "Ultra-low noise current source output noise is dominated by op-amp supply noise coupled through finite PSRR. Supply noise on op-amp VCC appears at output as V_supply_noise / PSRR. Requires LDO with <10nV/rtHz noise density.",
      "confidence": 0.95,
      "source_constraint": "ultra low noise + zero drift opamps",
      "priority": "CRITICAL"
    },
    {
      "requirement": "Kelvin (4-wire) connection on sense resistor",
      "component_implication": "pcb_layout_constraint",
      "reasoning": "At 100mA output current, even 1mΩ of lead resistance in the sense path introduces 100µV of error. Kelvin sensing eliminates this by separating current and voltage sense paths at the resistor body.",
      "confidence": 0.97,
      "source_constraint": "ultra precision resistors + 100mA current range",
      "priority": "CRITICAL"
    },
    {
      "requirement": "Matched low-tempco resistor pair for voltage divider setpoint",
      "component_implication": "precision_resistor_pair",
      "reasoning": "The potentiometer sets the current magnitude. Absolute stability requires that the voltage divider ratio be stable with temperature. Mismatched tempco between the potentiometer and the fixed resistors introduces drift.",
      "confidence": 0.88,
      "source_constraint": "highly stable + adjustable current using potentiometer",
      "priority": "HIGH"
    },
    {
      "requirement": "Guard ring around sense resistor and op-amp input nodes on PCB",
      "component_implication": "pcb_layout_constraint",
      "reasoning": "At the noise levels implied (ultra-low noise), PCB surface leakage between nearby nodes can introduce currents exceeding the noise floor. Guard rings driven at the local potential eliminate this leakage path.",
      "confidence": 0.85,
      "source_constraint": "ultra low noise",
      "priority": "HIGH"
    },
    {
      "requirement": "Negative voltage rail generation from single DC input",
      "component_implication": "negative_rail_converter",
      "reasoning": "Zero-drift op-amps require a bipolar supply for rail-to-rail output swing at the sense node. Single DC input implies an inverting charge pump or negative LDO to generate the negative rail.",
      "confidence": 0.92,
      "source_constraint": "zero drift opamps + single dc input + generate all required polarities",
      "priority": "CRITICAL"
    },
    {
      "requirement": "Compensation capacitor network for loop stability",
      "component_implication": "passive_compensation_network",
      "reasoning": "High-gain feedback loop driving a power transistor load is conditionally stable. Compensation capacitor across the op-amp feedback resistor sets the gain-bandwidth rolloff and prevents oscillation.",
      "confidence": 0.94,
      "source_constraint": "libbrecht hall design",
      "priority": "HIGH"
    }
  ],
  "quantified_specs": [
    {
      "original_text": "ultra low noise",
      "quantified_value": "< 1",
      "unit": "pA/rtHz at 1kHz",
      "reasoning": "Published Libbrecht-Hall implementations achieve 0.1-1 pA/rtHz. 'Ultra low noise' for 100mA precision current source in lab instrumentation context implies <1 pA/rtHz.",
      "confidence": 0.75
    },
    {
      "original_text": "highly stable",
      "quantified_value": "< 10",
      "unit": "ppm/°C temperature coefficient",
      "reasoning": "Lab-grade precision instruments typically require <10ppm/°C stability. Ultra-precision resistors spec implies same order for the overall circuit.",
      "confidence": 0.70
    }
  ],
  "missing_critical_specs": [
    "Output compliance voltage not specified (minimum headroom for load)",
    "Operating temperature range not specified (critical for tempco budget)",
    "Supply voltage level not specified (determines transistor and LDO selection)",
    "Target current noise floor not specified quantitatively",
    "Current adjustment resolution not specified (potentiometer turns, step size)",
    "Load impedance range not specified"
  ],
  "contradictions": [],
  "assumptions": [
    {
      "assumption": "Operating environment is laboratory (not industrial or military)",
      "reasoning": "Libbrecht-Hall design is predominantly used in AMO physics labs. No environmental spec stated.",
      "confidence": 0.80
    },
    {
      "assumption": "Single DC supply is 15V-24V range",
      "reasoning": "100mA output with compliance voltage and op-amp supply generation from single rail implies minimum ~12V. Standard lab supply is 15V or 24V.",
      "confidence": 0.65
    }
  ]
}
```

---

## Confidence Score Calibration

| Range | Meaning | Example |
|-------|---------|---------|
| 0.95 – 1.00 | Physically necessary. Cannot be false. | Kelvin sensing for 100mA precision current source |
| 0.85 – 0.94 | True for virtually all implementations of this topology | Low-noise LDO for ultra-low-noise design |
| 0.70 – 0.84 | True in most contexts given the stated constraints | Guard rings for sub-pA noise floor |
| 0.60 – 0.69 | Likely but context-dependent | Specific tempco budget |
| < 0.60 | Do not report | Too uncertain to be useful |

---

## Model Selection

**Cloud (short-term):** Qwen 3.5 397B via cloud API. The large context window and strong domain reasoning make it appropriate for the injection of domain knowledge documents alongside the intent dict.

**Local (long-term):** Qwen2.5-72B-Instruct is the recommended local fallback when 397B is not available. It achieves ~85% of the implication quality at ~18% of the VRAM cost. The difference is primarily in depth of reasoning for obscure topologies.

**Prompting mode:** Use Instructor with the `RequirementCompletionResult` Pydantic schema for guaranteed structured output. Do not attempt JSON parsing of free-form LLM output.

---

## Integration with the Pipeline

Stage 2 runs after Stage 1 and before the KG query. Its output is merged back into the `ImprovedIntentDict`:

```python
def run_completion_engine(
    intent: ImprovedIntentDict,
    config: Config,
) -> ImprovedIntentDict:
    domain_knowledge = load_domain_knowledge(intent.goal_topology)
    result = call_qwen_completion(intent, domain_knowledge, config)
    return intent.model_copy(update={
        "implied_requirements": result.implied_requirements,
        "missing_critical_specs": result.missing_critical_specs,
        "contradictions_detected": [c.description for c in result.contradictions],
        "inferred_constraints": [r.requirement for r in result.implied_requirements
                                  if r.confidence >= 0.80],
    })
```

The merged intent dict then drives KG queries, BOM generation, and component selection — now enriched with the implied requirements that the engineer did not explicitly state.
