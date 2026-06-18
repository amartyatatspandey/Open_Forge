# OpenForge — Scientific Prompt Analysis Log

**Purpose:** Every time a scientist or engineer submits a design prompt, this document records what the system can handle, what it cannot, and what needs to be built. This is a living document. Append a new entry every time a new prompt is received and analysed.

**Maintained by:** TPM / Lead Architect
**Update rule:** Add a new entry at the bottom. Never edit past entries. Mark gaps as RESOLVED when the corresponding capability is built and gated.

---

## How to Read This Document

Each entry has four sections:

- **PROMPT** — the exact prompt as received
- **CAN HANDLE** — what the current system processes correctly end-to-end
- **GAPS** — specific missing capabilities, each tagged as one of:
  - `[DATA GAP]` — the pipeline exists but the required data is not ingested
  - `[OUTPUT GAP]` — the NIR is correct but no serializer produces this format
  - `[ANALYSIS GAP]` — requires computation or simulation not in the pipeline
  - `[SCOPE GAP]` — outside PCB design entirely (software, firmware, mechanical)
  - `[COMPONENT GAP]` — specific part not in KG-3 or golden corpus
  - `[TOPOLOGY GAP]` — circuit topology not in KG-2 design recipes
- **BUILD REQUIREMENTS** — what needs to be designed and built to close each gap

---

## Entry 001 — Libbrecht-Hall Precision Current Source

**Date received:** 2026-06-19
**Received from:** DRDO Scientist
**Status:** PARTIALLY PROCESSABLE — data and analysis gaps block full execution

### PROMPT

> Design a ultra low noise and highly stable current source for 100mA current range using libbrecht hall design. Use ultra precision resistors. Include the power supply for all components and generate all required voltage and polarities. And use zero drift opamps. The circuit should work from single dc input. Include the required ldos. It should have capability to adjust the current using a potentiometer. Provide me list of components. Estimate the current noise.

---

### CAN HANDLE

| Capability | Status | Notes |
|-----------|--------|-------|
| Intent parsing | ✅ | `goal=current_source`, `methodology=mixed_signal` |
| Single DC input constraint extraction | ✅ | Extracted as explicit constraint |
| LDO requirement extraction | ✅ | Mapped to `power_management` sub-requirement |
| Potentiometer / adjustable current extraction | ✅ | Extracted as explicit constraint |
| LDO datasheet parsing | ✅ | If LDO part is in KG-3 |
| LDO selection and BOM entry | ✅ | If LDO design recipes in KG-2 |
| Schematic synthesis for LDO + power section | ✅ | Standard power topology |
| PCB layout spec generation | ✅ | Mixed-signal board spec selected |
| NIR generation | ✅ | Full pipeline runs to completion |
| KiCad output | ✅ | Serializer produces valid files |
| tscircuit output + 3D model | ✅ | Serializer produces valid files |

---

### GAPS

#### GAP-001-A `[TOPOLOGY GAP]`
**The Libbrecht-Hall current source topology is not in KG-2.**

The Libbrecht-Hall design (from Libbrecht & Hall, Rev. Sci. Instrum. 64, 2133, 1993) is a specific feedback-stabilized current source architecture used in atomic physics and precision measurement. It is not covered by any TI or ADI application note currently ingested. The query engine traverses the graph for `current_source` and finds no design recipe with the required feedback topology, sense resistor configuration, or op-amp selection criteria. The BOM generator returns empty with `review_required=True`.

**Impact:** System cannot generate a correct BOM or schematic without this topology in KG-2.

**Sources needed for ingestion:**
- Libbrecht & Hall 1993 paper (Rev. Sci. Instrum. 64, 2133)
- TI application note SBOA327 — Precision Current Source Design
- TI application note SBOA273 — Low-Noise Current Source Techniques
- ADI application note AN-1357 — Precision Current Sources and Sinks

---

#### GAP-001-B `[COMPONENT GAP]`
**Zero-drift op-amps are not in KG-3.**

The prompt specifically requires zero-drift op-amps. Candidate parts include OPA189 (TI), ADA4522-2 (ADI), AD8628 (ADI), OPA2188 (TI). None of these datasheets have been ingested through P1. The BOM generator cannot suggest a specific part — it can only output `component_type=zero_drift_op_amp` with `specific_part=None`, triggering a human review gate.

**Impact:** BOM will not contain specific op-amp part numbers. Engineer must manually select.

**Datasheets needed:**
- OPA189 (TI) — 0.1µV/°C max drift, rail-to-rail
- ADA4522-2 (ADI) — 2.5µV max offset, zero-drift
- AD8628 (ADI) — chopper-stabilized, single supply
- OPA2188 (TI) — dual, 0.03µV/°C drift

---

#### GAP-001-C `[COMPONENT GAP]`
**Ultra-precision resistors are not in KG-3.**

The prompt requires ultra-precision resistors for the sense element. Candidate parts include Vishay VSR series, Susumu RG series, and Caddock MP series. None are in the component database. The system will output `component_type=precision_resistor` with `specific_part=None`.

**Impact:** BOM will not contain specific resistor part numbers.

**Datasheets needed:**
- Vishay VSR 0.01% tolerance series
- Susumu RG2012N-xxx precision chip resistors
- Caddock MP915 precision power resistors

---

#### GAP-001-D `[ANALYSIS GAP]`
**Current noise estimation is not in the pipeline.**

The prompt asks to "estimate the current noise." This requires:
1. Johnson noise calculation: `V_noise = sqrt(4kTRΔf)` from resistor values
2. Op-amp input voltage noise density from datasheet (nV/√Hz) integrated over bandwidth
3. Op-amp input current noise density (pA/√Hz) integrated over bandwidth
4. Total output current noise calculation combining all sources
5. Spectral noise density plot (1/f corner + flat band)

None of this computation exists in the current pipeline. The NIR has no simulation or analysis layer. The DocumentationGenerator produces a design report but has no noise analysis section.

**Impact:** System cannot produce a noise estimate. This output is completely missing.

**What needs to be built:**
- `src/analysis/noise_estimator.py` — takes a `NIR` + list of `ComponentDatasheet` objects, reads electrical parameters (voltage noise density, current noise density, resistor values), applies noise analysis formulas, returns a `NoiseAnalysisResult` object
- `NoiseAnalysisResult` schema: total_current_noise_pA_rtHz, spectral_breakdown_by_source, dominant_noise_source, estimated_1f_corner_hz
- Documentation generator must be extended to include noise analysis section when `NoiseAnalysisResult` is present

---

#### GAP-001-E `[COMPONENT GAP]`
**Potentiometer for current adjustment not in KG-3.**

A wirewound or cermet potentiometer appropriate for precision current adjustment (e.g. Bourns 3590S, Vishay P11 series) is not in the component database. The system knows what a potentiometer is conceptually (KG-1 physics layer) but cannot recommend a specific part.

**Impact:** BOM entry for potentiometer will have `specific_part=None`.

---

### BUILD REQUIREMENTS FOR ENTRY 001

| ID | What to Build | Type | Priority |
|----|--------------|------|---------|
| BR-001-1 | Ingest Libbrecht-Hall paper + 3 precision current source app notes into KG-2 | Data ingestion run | HIGH — blocks full execution |
| BR-001-2 | Ingest 4 zero-drift op-amp datasheets through P1 into KG-3 | Data ingestion run | HIGH — blocks specific part selection |
| BR-001-3 | Ingest precision resistor datasheets through P1 into KG-3 | Data ingestion run | MEDIUM |
| BR-001-4 | Ingest precision potentiometer datasheets through P1 into KG-3 | Data ingestion run | LOW |
| BR-001-5 | Build `src/analysis/noise_estimator.py` module | New module | HIGH — prompt explicitly requests this |
| BR-001-6 | Add `NoiseAnalysisResult` to `src/schemas/` | New schema | Prerequisite for BR-001-5 |
| BR-001-7 | Extend DocumentationGenerator to include noise analysis section | Module extension | Depends on BR-001-5 |

---

---

## Entry 002 — Adjustable Current Source with VCO Bias Tee and USB-C Interface

**Date received:** 2026-06-19
**Received from:** DRDO Scientist
**Status:** PARTIALLY PROCESSABLE — multiple gaps, two are out of PCB scope

### PROMPT

> Design a SPICE schematic file for a adjustable current source with a combined interface to PC, power regulator and output SMA connector. I also need a bias tee where I can add the DC current and RF signal generated from the ZCOM 4596 VCO. I should be able to sweep the tune voltage pin to vary the frequency. The board should have micro connectors and a USB Type-C connector for connecting to PC. A Python GUI would be needed to control the circuit.

---

### CAN HANDLE

| Capability | Status | Notes |
|-----------|--------|-------|
| Intent parsing | ✅ | `goal=current_source`, `methodology=RF_highfreq` |
| RF methodology classification | ✅ | Correct — RF_highfreq activated by VCO/RF context |
| SMA connector selection and placement | ✅ | Standard component, in KiCad/tscircuit libraries |
| Power regulator section | ✅ | LDO selection works if parts are in KG-3 |
| NIR generation for processable subsections | ✅ | Partial NIR possible for power + connector sections |
| KiCad output for partial design | ✅ | Whatever the NIR contains gets serialized |
| tscircuit output + 3D model | ✅ | Same |
| USB-C connector footprint placement | ✅ | Footprint exists in libraries — placement works |
| Micro connector placement | ✅ | Standard footprints available |

---

### GAPS

#### GAP-002-A `[OUTPUT GAP]`
**SPICE netlist output format is not implemented.**

The prompt explicitly requests a SPICE schematic file (`.net` or `.cir` format). The current Team E output layer produces KiCad files and tscircuit files only. The NIR contains everything a SPICE netlist requires — component references, values, net connections, and component types. The serializer does not exist yet.

**Impact:** The system cannot produce the requested output format. KiCad and tscircuit files would be produced instead.

**What needs to be built:**
- `src/output/spice_serializer.py` — converts `NIR.netlist` and `NIR.components` to SPICE `.net` format
- `SpiceOutput` result schema: `net_path`, `validation_result`
- Add `check_version(nir)` call at start (same pattern as KiCad and tscircuit serializers)
- Add to Team E pipeline as a third output option

---

#### GAP-002-B `[COMPONENT GAP]`
**ZCOM 4596 VCO is not in KG-3.**

The ZCOM 4596 is a specific voltage-controlled oscillator from Z-Communications Inc. Its datasheet is not in the corpus. The P1 parser has never processed it. KG-3 has no entry for it. The system cannot generate pinout connections, tuning voltage range constraints, or RF output impedance requirements without this component's data.

**Impact:** The VCO cannot appear in the BOM with a specific part number or correct pinout. The bias tee connection to the VCO RF output cannot be synthesized.

**Datasheets needed:**
- ZCOM 4596 datasheet from Z-Communications
- Key parameters to extract: VTune range, Vtune sensitivity (MHz/V), RF output power, supply voltage, pinout, package

---

#### GAP-002-C `[TOPOLOGY GAP]`
**Bias tee circuit topology is not in KG-2.**

A bias tee combines a DC current path and an RF signal path using a series inductor (DC path, RF block) and a series capacitor (RF path, DC block). This is a standard RF component but the specific design recipe — inductor and capacitor selection criteria for a given frequency range, impedance matching to 50Ω, and connection to the VCO output — is not in KG-2. The schematic synthesizer has no rule that knows how to connect the bias tee elements.

**Impact:** The bias tee section cannot be synthesized. The system does not know what to place or how to connect it.

**Sources needed for ingestion:**
- Mini-Circuits application note on bias tee design
- ADI application note on RF bias tee circuit design
- Any TI RF design guide covering bias tee topologies at the relevant frequency range

---

#### GAP-002-D `[TOPOLOGY GAP]`
**USB-UART bridge design recipe is not in KG-2.**

USB-C connectivity to a PC requires a USB-UART or USB-serial bridge IC (candidates: CP2102N, CH340C, FT232RL). The design recipe for this — bridge IC selection, crystal or oscillator requirement, decoupling, USB termination resistors, D+/D- routing rules — is not in KG-2. The system can place a USB-C connector footprint but cannot synthesize the full USB communication subsystem.

**Impact:** USB-C section will be incomplete. BOM will have `component_type=usb_uart_bridge` with `specific_part=None`. USB-C connector placed but not correctly connected.

**Sources needed for ingestion:**
- TI CP2102N datasheet + application note
- WCH CH340C datasheet + application note
- FTDI FT232RL datasheet + application note
- USB 2.0 full-speed PCB layout guidelines (impedance controlled D+/D- traces)

---

#### GAP-002-E `[TOPOLOGY GAP]`
**VTune sweep circuit is not in KG-2.**

The prompt requires sweeping the VCO tuning voltage pin to vary the frequency. This requires either a DAC (digital-to-analog converter) controlled via USB, or a voltage ramp generator. The design recipe for a DAC-to-VTune interface — DAC selection, output filtering, voltage range matching to VCO VTune spec, and digital control interface — is not in KG-2. The intent parser extracts `tune_voltage_controllable=true` as a constraint but the BOM generator cannot resolve it to specific components without a design recipe.

**Impact:** No DAC or tuning circuit appears in the BOM. VTune pin is left unconnected in the schematic.

**Sources needed:**
- TI DAC8562 or similar precision DAC application note
- VCO tuning interface design recipes

---

#### GAP-002-F `[SCOPE GAP]`
**Python GUI is outside PCB design scope.**

The request for a Python GUI to control the circuit is a software deliverable, not a PCB design deliverable. OpenForge produces PCB files — schematics, layouts, Gerbers, BOMs. It does not generate software, firmware, or GUI applications. The intent parser should detect this requirement and flag it explicitly as out-of-scope in the `AmbiguityFlag` list with a message that the GUI must be developed separately.

**Impact:** No Python GUI will be produced. This is not a system gap — it is a scope boundary. The engineer must implement the GUI independently using the USB-C interface that OpenForge designs.

**What needs to be built:**
- Intent parser keyword detection for software-related requirements:
  `["python", "gui", "software", "firmware", "app", "application", "code", "script"]`
- When detected: add `AmbiguityFlag(field="software_requirement", severity="WARNING", description="Python GUI and software development is outside OpenForge scope. PCB design files will be produced. GUI must be implemented separately.")`

---

#### GAP-002-G `[SCOPE GAP]`
**SPICE simulation and schematic validation is outside current scope.**

The prompt implies the SPICE file should be simulatable — implying correct SPICE model assignments for every component. Assigning SPICE models (`.model` statements, subcircuit `.lib` files) to real component part numbers requires a SPICE model database that does not exist in OpenForge. Producing a syntactically valid SPICE netlist (GAP-002-A) is achievable. Producing a simulatable SPICE netlist with correct models is a larger capability gap.

**Impact:** Even with the SPICE serializer built, the output will be a structural netlist, not a simulation-ready file.

**What needs to be built (future):**
- SPICE model database: maps `component_id` → SPICE model file or subcircuit
- SPICE model fetcher: downloads models from manufacturer sites at corpus build time
- SPICE serializer extension: injects `.model` and `.lib` references into output

---

### BUILD REQUIREMENTS FOR ENTRY 002

| ID | What to Build | Type | Priority |
|----|--------------|------|---------|
| BR-002-1 | Build `src/output/spice_serializer.py` — NIR → SPICE netlist | New Team E serializer | HIGH — explicit in prompt |
| BR-002-2 | Ingest ZCOM 4596 datasheet through P1 into KG-3 | Data ingestion run | HIGH — blocks VCO section |
| BR-002-3 | Ingest bias tee design app notes into KG-2 | Data ingestion run | HIGH — blocks bias tee synthesis |
| BR-002-4 | Ingest USB-UART bridge datasheets + app notes into KG-2 and KG-3 | Data ingestion run | HIGH — blocks USB section |
| BR-002-5 | Ingest DAC + VTune interface app notes into KG-2 | Data ingestion run | MEDIUM — blocks sweep circuit |
| BR-002-6 | Add software requirement detection to intent parser | Intent parser extension | LOW — quality of life flag |
| BR-002-7 | SPICE model database + simulatable SPICE output | Future capability | LOW — deferred |

---

---

## Gap Registry — Consolidated View

All open gaps across all entries. Update STATUS when resolved.

| Gap ID | Type | Description | Entry | Status | Blocked By |
|--------|------|-------------|-------|--------|-----------|
| GAP-001-A | TOPOLOGY | Libbrecht-Hall topology not in KG-2 | 001 | OPEN | BR-001-1 |
| GAP-001-B | COMPONENT | Zero-drift op-amps not in KG-3 | 001 | OPEN | BR-001-2 |
| GAP-001-C | COMPONENT | Ultra-precision resistors not in KG-3 | 001 | OPEN | BR-001-3 |
| GAP-001-D | ANALYSIS | Current noise estimation not in pipeline | 001 | OPEN | BR-001-5, BR-001-6 |
| GAP-001-E | COMPONENT | Precision potentiometer not in KG-3 | 001 | OPEN | BR-001-4 |
| GAP-002-A | OUTPUT | SPICE serializer not built | 002 | OPEN | BR-002-1 |
| GAP-002-B | COMPONENT | ZCOM 4596 VCO not in KG-3 | 002 | OPEN | BR-002-2 |
| GAP-002-C | TOPOLOGY | Bias tee topology not in KG-2 | 002 | OPEN | BR-002-3 |
| GAP-002-D | TOPOLOGY | USB-UART bridge recipe not in KG-2 | 002 | OPEN | BR-002-4 |
| GAP-002-E | TOPOLOGY | VTune sweep circuit not in KG-2 | 002 | OPEN | BR-002-5 |
| GAP-002-F | SCOPE | Python GUI is software, not PCB | 002 | SCOPE BOUNDARY | — |
| GAP-002-G | SCOPE | Simulatable SPICE models not in system | 002 | OPEN (DEFERRED) | BR-002-7 |

---

## Build Requirements — Consolidated Backlog

Ordered by cross-entry priority. Items marked SHARED benefit multiple entries.

| ID | Description | Type | Entries | Priority | Status |
|----|-------------|------|---------|---------|--------|
| BR-001-5 | Noise estimator module | New module | 001 | HIGH | OPEN |
| BR-001-6 | NoiseAnalysisResult schema | New schema | 001 | HIGH | OPEN |
| BR-002-1 | SPICE serializer | New serializer | 002 | HIGH | OPEN |
| BR-001-1 | Libbrecht-Hall + current source app notes ingestion | Data | 001 | HIGH | OPEN |
| BR-001-2 | Zero-drift op-amp datasheets ingestion | Data | 001 | HIGH | OPEN |
| BR-002-2 | ZCOM 4596 datasheet ingestion | Data | 002 | HIGH | OPEN |
| BR-002-3 | Bias tee app notes ingestion | Data | 002 | HIGH | OPEN |
| BR-002-4 | USB-UART bridge datasheets + app notes ingestion | Data | 001, 002 | HIGH | OPEN |
| BR-001-7 | Documentation generator noise section | Extension | 001 | MEDIUM | OPEN |
| BR-002-5 | DAC + VTune interface app notes ingestion | Data | 002 | MEDIUM | OPEN |
| BR-001-3 | Precision resistor datasheets ingestion | Data | 001 | MEDIUM | OPEN |
| BR-001-4 | Precision potentiometer datasheets ingestion | Data | 001 | LOW | OPEN |
| BR-002-6 | Software requirement detection in intent parser | Extension | 002 | LOW | OPEN |
| BR-002-7 | SPICE model database + simulatable output | Future | 002 | DEFERRED | OPEN |

---

*Append new entries below this line. Format: Entry NNN — [Title]*