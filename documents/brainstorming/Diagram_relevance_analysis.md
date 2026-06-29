# Datasheet Diagrams — PCB Design Relevance Analysis

> **Question:** Across all datasheet types, which diagram categories matter for PCB design,
>               and which can be safely skipped?
> **Purpose:** Decide extraction strategy before redesigning the parser around Baidu OCR
> **Downstream consumers:** Schematic synthesizer, layout engine, BOM generator, NIR builder
> **Reviewed by:** GLM-5 Turbo (independent technical review, June 2026)
> **Status:** Refined — incorporates GLM pushbacks on A2, bad datasheet long tail,
>             test circuit disambiguation, and schema additions

---

## What PCB Design Actually Needs

Before evaluating diagrams, establish the ground truth: what does OpenForge's
downstream pipeline actually consume from a `ComponentDatasheet`?

| Consumer | Fields consumed | Source in datasheet |
|---|---|---|
| Schematic synthesizer | `pins` (normalized), voltage levels, protocol assignments | Pin table, electrical characteristics table |
| Layout engine | `layout_constraints` (Phase 5 output), thermal resistance, decoupling values | Layout section text, thermal table, app circuit |
| BOM generator | `description`, `package`, key electrical params | Header, ordering table, electrical table |
| Pin normalizer (P2) | `pins.raw_name` | Pin table |
| NIR builder | All of the above | All of the above |

**The question is: which diagram types contain information for these consumers
that is NOT already available in tables?**

---

## Complete Taxonomy of Datasheet Diagram Types

Every diagram type that appears across all component categories:

### Category A — Functional / Architectural Diagrams

**A1. Block diagram (functional architecture)**

What it shows: Internal blocks of the IC — ADC, DAC, reference, oscillator,
comparator, control logic — and how they connect internally.

PCB relevance: LOW. The block diagram shows internal architecture, not external
connections. A PCB designer does not need to know that the LDO has an internal
bandgap reference — they need to know the output voltage and enable pin behavior.

Exception: For ICs with complex enable/shutdown sequencing (power management ICs,
PMICs), the block diagram sometimes reveals the sequencing order of internal
stages that affects external capacitor placement. But this information is almost
always duplicated in the application section as text.

Verdict: **SKIP.** No unique PCB-relevant information.

---

**A2. Application circuit diagram (typical application schematic)**

What it shows: A complete circuit showing how to connect the IC in its most
common use case — power supply connections, decoupling capacitors, feedback
resistors, external passive values, filter components, output load.

PCB relevance: **CRITICAL.** This is the single most PCB-relevant figure in
any datasheet. It shows:
- Which pins need decoupling capacitors and what value
- Which pins need pull-up/pull-down resistors and what value
- Feedback network component values (resistor dividers for adjustable regulators)
- External component connections that are mandatory for correct operation
- Net topology (which passive goes between which pins)

This information is partially in text (application section) and partially
only in the figure. The figure is the authoritative source for passive values
and connectivity.

Current OpenForge handling: Phase 5 extracts layout constraints from text.
The application circuit figure itself is not parsed. This is a genuine gap
that means decoupling cap values and feedback resistor values are missed when
they are only in the figure.

**Critical distinction — BOM vs topology (GLM review):**
Text extraction (captions, adjacent text) reliably yields the component BOM:
"C1 = 10µF, R1 = 100kΩ." It does NOT reliably yield wiring topology: text
rarely says "L1 connects between SW pin and VOUT via D1." It says "L1 is a
4.7µH inductor." For OpenForge's schematic synthesizer, KG-3 `connects_to`
rules already encode standard topologies (buck converter, LDO, op-amp buffer),
so text BOM extraction is sufficient for known topologies. VLM fallback is
only required when the topology is novel or the component is not in KG-3.
The `connection_topology` field is populated only by VLM, never from text.

**Critical distinction — application circuit vs test circuit (GLM review):**
Datasheets frequently contain two similar schematics: the Typical Application
Circuit and the Test/Measurement Circuit. The test circuit shows how the IC
was bench-tested — it may include 50Ω coaxial terminations, specific test
loads, or evaluation board artifacts that are irrelevant to a real design.
Extracting a 50Ω test load into the BOM causes silent synthesis errors.
Detection rule: if figure caption contains "test", "measurement", "evaluation",
"bench", or "test circuit" → flag all extracted components as
`is_test_setup_component=True` and exclude from BOM generation.

Verdict: **EXTRACT.** Highest-value figure type for PCB design.
Primary path: text/caption extraction. VLM fallback only for novel topologies
or when text yields zero component references (bad datasheet long tail).

---

**A3. Pin configuration diagram (pinout figure)**

What it shows: A drawing of the IC package with pin numbers and names labeled
around the perimeter or in a grid (for BGA/QFN).

PCB relevance: MEDIUM. The pin names are duplicated in the pin function table.
The package diagram adds spatial information (which pin is in which physical
position) that matters for BGA fanout and QFN thermal pad identification.

For most packages (SOIC, SOT, DIP, TSSOP): the spatial order is already
implied by pin numbering. The table is sufficient.

For BGA and fine-pitch QFP (100+ pins): the spatial diagram is the only place
where the ball/pin map is shown. The table gives function but not position.

Verdict: **SKIP for standard packages. EXTRACT for BGA/QFP100+.**
BGA extraction is a specialized problem (grid coordinate parsing).
Defer to a future pass.

---

### Category B — Electrical Characteristic Curves

**B1. Efficiency vs load current curve**

What it shows: A graph of power efficiency (%) on Y axis vs output current (A)
on X axis for a DC-DC converter or LDO.

PCB relevance: NONE for PCB design. The peak efficiency value and the
efficiency at rated load are already in the electrical characteristics table.
The curve shape tells you nothing that affects component placement, routing,
or passive selection.

Verdict: **SKIP.**

---

**B2. Noise density / spectral density plot**

What it shows: A log-log graph of noise (nV/√Hz or µV/√Hz) vs frequency (Hz).

PCB relevance: NONE directly. The integrated noise figure at a specific
bandwidth is in the electrical characteristics table. The shape of the
1/f corner tells you about flicker noise behavior, which is relevant for
amplifier design but not for PCB layout decisions.

Verdict: **SKIP.**

---

**B3. Output voltage vs temperature curve**

What it shows: How the output voltage drifts with temperature.

PCB relevance: NONE. The temperature coefficient (tempco) number is in the
electrical characteristics table.

Verdict: **SKIP.**

---

**B4. Safe operating area (SOA) diagram**

What it shows: A log-log graph of collector/drain current vs collector/drain
voltage showing the safe operating region for a transistor or MOSFET.

PCB relevance: LOW. Relevant for thermal design but the key constraint
(maximum power dissipation and thermal resistance) is already in tables.
The SOA curve adds nuance for pulsed operation that most PCB designers look
up manually when needed.

Verdict: **SKIP.**

---

**B5. Gate charge curve (for MOSFETs)**

What it shows: Gate voltage vs gate charge (Q_g) — the shape determines
gate driver requirements.

PCB relevance: MEDIUM. Q_g (total gate charge) is in the electrical
characteristics table. The curve shape affects gate driver selection but the
number is sufficient for PCB design. Gate driver design is a separate
calculation done by the engineer.

Verdict: **SKIP.** Q_g is already extracted from the table.

---

**B6. Load transient response plot**

What it shows: Oscilloscope-style waveform showing how output voltage
recovers after a step in load current.

PCB relevance: NONE. The output capacitor recommendation (which drives
transient response) is in the application circuit and application text.

Verdict: **SKIP.**

---

### Category C — Timing and Signal Diagrams

**C1. Timing diagram (waveform figure)**

What it shows: Waveform traces for clock, data, chip select signals with
annotated time intervals (t_setup, t_hold, t_pulse).

PCB relevance: NONE for PCB design. Setup and hold times are in the timing
characteristics table. They are firmware constraints, not PCB constraints.

Exception: Rise/fall time and propagation delay ARE PCB-relevant at high
speeds (>100 MHz) because they affect trace length matching. But these values
are in the AC characteristics table, not only in the timing diagram.

Verdict: **SKIP.** Extract the timing characteristics TABLE, not the diagram.

---

**C2. SPI/I2C/UART protocol timing diagram**

What it shows: Timing waveform specifically for a communication protocol
showing bit timing, start/stop conditions, frame format.

PCB relevance: NONE for PCB. This is firmware territory entirely.
PCB cares about voltage levels and pin assignments, not protocol timing.

Verdict: **SKIP.**

---

### Category D — Layout and Thermal Diagrams

**D1. PCB layout example / recommended layout figure**

What it shows: A top-view drawing of a PCB layout showing:
- Component placement relative to the IC
- Ground plane recommended area
- Via placement for thermal dissipation
- Decoupling capacitor placement (how close to which pin)
- Trace routing suggestions (wide power traces, short feedback traces)
- Keep-out zones

PCB relevance: **CRITICAL.** This is the second most important figure type
for PCB design after the application circuit. The layout example shows spatial
constraints that cannot be expressed in a table:
- "Place C1 within 1mm of pin 3"
- "Ground plane must extend under entire package"
- "Do not route signal traces through the switching node area"
- "Place VIN capacitor on the same side as the IC"

Current OpenForge handling: Phase 5 tries to extract placement constraints
from the adjacent text (layout guidelines section). The figure itself is not
parsed. The text often says "refer to Figure 12 for recommended layout" — which
means the text alone is insufficient.

Verdict: **EXTRACT.** This figure directly populates `layout_constraints`
in `ComponentDatasheet`, which feeds the layout engine. It is the ground truth
for placement constraints.

---

**D2. Thermal pad / exposed pad diagram**

What it shows: Package underside showing the exposed thermal pad dimensions,
recommended solder paste pattern, and via array for heat dissipation.

PCB relevance: HIGH. The thermal pad connection to ground plane is a PCB
fabrication requirement. Via count and placement for thermal dissipation
directly affects the PCB layout.

Current handling: Package is stored as a string ("QFN-16"). The thermal pad
dimensions and via recommendation are not extracted.

Verdict: **PARTIALLY EXTRACT.** The key fact is: "this package has an
exposed thermal pad that must connect to GND with N thermal vias."
This is binary information (thermal pad: yes/no, connect to: GND/VCC/float)
that can be extracted from the thermal pad section text, not necessarily
the figure. Add `thermal_pad` field to `ComponentDatasheet`.

---

**D3. Derating curve (power vs temperature)**

What it shows: Maximum power dissipation decreasing with temperature above
a threshold (typically 25°C).

PCB relevance: LOW. The PCB designer needs the thermal resistance (θJA)
from the table, not the full derating curve. The curve shape is determined
by θJA which is already extracted.

Verdict: **SKIP.** θJA from the thermal table is sufficient.

---

### Category E — Mechanical / Package Diagrams

**E1. Package mechanical drawing**

What it shows: Precise dimensional drawing of the IC package — body
dimensions, lead pitch, lead length, standoff height, tolerances.

PCB relevance: HANDLED ELSEWHERE. These dimensions are what the KiCad
footprint library uses to define the land pattern. We do not need to
extract them from the datasheet because the KiCad/tscircuit footprint
lookup already provides them.

Verdict: **SKIP.** Footprint libraries handle this.

---

**E2. Tape and reel diagram**

What it shows: Packaging dimensions for automated assembly (tape width,
reel diameter, carrier pocket dimensions).

PCB relevance: NONE. Manufacturing logistics, not PCB design.

Verdict: **SKIP.**

---

### Category F — Register and Configuration Diagrams

**F1. Register map**

What it shows: Bit-field layout of configuration registers.

PCB relevance: NONE (firmware territory). Already decided in gap analysis.

Verdict: **SKIP.**

---

**F2. Memory map / address map**

What it shows: Address ranges for MCU peripherals, flash, RAM.

PCB relevance: NONE.

Verdict: **SKIP.**

---

## Summary Decision Table

| Diagram Type | PCB Relevance | Decision | Priority |
|---|---|---|---|
| A1 — Block diagram | LOW | SKIP | — |
| **A2 — Application circuit** | **CRITICAL** | **EXTRACT** | **P1** |
| A3 — Pin configuration figure | MEDIUM (BGA only) | SKIP now, defer | Future |
| B1 — Efficiency curve | NONE | SKIP | — |
| B2 — Noise density plot | NONE | SKIP | — |
| B3 — Output vs temperature curve | NONE | SKIP | — |
| B4 — SOA diagram | LOW | SKIP | — |
| B5 — Gate charge curve | LOW | SKIP | — |
| B6 — Load transient plot | NONE | SKIP | — |
| C1 — Timing waveform | NONE (values in table) | SKIP | — |
| C2 — Protocol timing diagram | NONE | SKIP | — |
| **D1 — PCB layout example** | **CRITICAL** | **EXTRACT** | **P1** |
| D2 — Thermal pad diagram | HIGH | PARTIAL | P2 |
| D3 — Derating curve | LOW | SKIP | — |
| E1 — Package mechanical drawing | NONE (footprint libraries) | SKIP | — |
| E2 — Tape and reel | NONE | SKIP | — |
| F1 — Register map | NONE | SKIP | — |
| F2 — Memory map | NONE | SKIP | — |

**Two figures matter for PCB design. Everything else is either in a table or is
firmware/manufacturing territory.**

---

## The Two Figures That Actually Matter

### Application Circuit (A2)

**What we need to extract:**
- Passive component connections (which pin, what value, what net)
- Feedback network topology (resistor divider values for adjustable output)
- Required external components not obvious from pin table alone
- Bootstrap/compensation network values

**Extraction method options:**

Option 1 — VLM (Qwen2-VL): Pass the figure image to the VLM with a prompt
asking for component list and connections. Output: list of (component, value,
pin_a, pin_b) tuples. Accuracy: moderate (~70-80% for clean figures).
Problem: VLMs hallucinate component values and pin names.

Option 2 — Circuit diagram parser (dedicated model): Models like
img2circuit or TritonSE were trained specifically on circuit schematics.
Accuracy higher than general VLM. Air-gap compatible if self-hosted.
Problem: They target formal schematics, not the informal hand-like drawings
in datasheets.

Option 3 — Text extraction from adjacent caption/text: Many datasheets
describe the application circuit in the text immediately below the figure
("C1 = 10µF, C2 = 100nF, R1 = 100kΩ for 3.3V output"). Extract from text,
not from figure. Lower coverage but zero VLM cost and high accuracy.

**Recommendation: Option 3 first, Option 1 as fallback.**
The text caption extraction is deterministic and accurate. The VLM fallback
handles cases where values are only in the figure. This is a Phase 5 extension,
not a new phase.

---

### PCB Layout Example (D1)

**What we need to extract:**
- Proximity constraints ("C1 within 1mm of VIN pin")
- Ground plane requirements ("exposed pad must connect to ground plane")
- Keep-out zones ("no signal traces in switching node area")
- Thermal via requirements ("place N vias under exposed pad")

**Extraction method options:**

Option 1 — VLM: Pass the layout figure to VLM asking for placement rules.
Problem: PCB layout figures are technical drawings with small text annotations.
VLM accuracy on these is low (~50-60%).

Option 2 — Text from layout guidelines section: The text in the layout
recommendations section (which Phase 5 already targets) usually describes
the figure in words. "Place the input capacitor as close as possible to the
VIN pin" appears as text near Figure 12.

Option 3 — Hybrid: Phase 5 text extraction (current) + flag when a figure
reference appears in the text ("see Figure 12") so a human reviewer can verify.

**Recommendation: Option 2/3 — extend Phase 5 text extraction.**
Phase 5 already targets the layout section. The gap is that some constraints
are in the figure caption, not the body text. Adding caption extraction to
Phase 5 recovers most of this without VLM cost.

---

## Architectural Implication for Baidu OCR Integration

When Baidu OCR returns regions, classify them as:

```
region.type == "table"  → existing Phase 2/3 pipeline
region.type == "text"   → existing Phase 5 pipeline (layout section text)
region.type == "figure" → new figure handler:
    if section == LAYOUT_RECOMMENDATIONS:
        extract_caption_text(region) → Phase 5 extension
        flag_for_human_review()
    elif section == APPLICATION_CIRCUIT:
        extract_caption_text(region) → passive value extraction
        try_vlm_fallback(region) if caption insufficient
    else:
        skip, log "figure_skipped: {section}"
```

This means **no new phase is needed.** Figure handling is an extension of
Phase 5 (layout) and a new sub-handler in Phase 3 (application circuit
caption extraction). The VLM is used only as a fallback, not as the primary path.

---

## What This Changes in ComponentDatasheet Schema

Two additions needed:

```python
class ApplicationCircuitComponent(BaseModel):
    """A passive component from the typical application circuit."""
    ref_designator: str          # "C1", "R1", "L1"
    component_type: str          # "capacitor", "resistor", "inductor"
    value: Optional[str]         # "100nF", "10kΩ"
    connected_to_pin: Optional[str]  # normalized pin name
    net: Optional[str]           # "VIN", "GND", "FB"
    source: Literal["caption_text", "vlm", "table_text"]
    confidence: float

# Add to ComponentDatasheet:
application_circuit_components: list[ApplicationCircuitComponent] = []
thermal_pad_connect_to: Optional[str] = None  # "GND", "VCC", "float", None
thermal_via_count_recommended: Optional[int] = None
```

Everything else (efficiency curves, timing diagrams, block diagrams, register
maps) requires no schema change because we do not extract them.

---

## Opinion

The conventional assumption is that "figures need VLMs and VLMs are expensive
so we skip all figures." This document shows that assumption is wrong in two ways:

1. Only 2 of 18 diagram types matter at all for PCB design.
2. Both of those 2 types are better handled by text extraction (captions,
   adjacent text) than by VLM on the figure itself.

The VLM is a fallback of last resort, not the primary extraction path.
The primary path is: find the text that describes the figure, extract from that.

This means the parser does not need a new VLM-heavy phase for figures.
It needs Phase 5 to be smarter about caption extraction and figure-adjacent text.

Register maps, timing diagrams, efficiency curves, block diagrams — skip all of
them. Not because figures are hard, but because their PCB-relevant content is
already in tables.