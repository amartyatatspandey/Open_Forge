# OpenForge Parser — Full-Scope Datasheet Gap Analysis

> **Scope:** What is missing to process all component types, not just analog/power ICs
> **Current baseline:** Pipeline designed and tested against TI analog/power ICs
>                       with tabular data and pinouts under ~30 pins
> **Target:** All datasheet types — MCU, digital IC, FPGA, RF, sensor, power, analog

---

## Component Type Coverage Matrix

| Component Type | Example Parts | Pin Count | Key Content Types | Current Support |
|---|---|---|---|---|
| Analog IC (op-amp, comparator) | LM358, OPA2134 | 5–16 | Elec chars, pinout, abs-max | ✅ Designed for this |
| Power IC (LDO, DCDC) | TPS62933, LM5176 | 5–20 | Elec chars, pinout, layout | ✅ Designed for this |
| Sensor (I2C/SPI) | INA219, MPU6050 | 8–24 | Elec chars, pinout, register map | 🟡 Tables yes, register map no |
| Logic IC (gate, buffer) | SN74LVC1G04 | 5–16 | Elec chars, pinout, timing table | ✅ Already in golden corpus |
| MCU (small, ARM Cortex-M0) | STM32F030, ATTINY85 | 20–48 | Elec chars, pinout, timing table | 🟡 Tables yes, alt functions partial |
| MCU (large, ARM Cortex-M4+) | STM32F4, RP2040 | 64–216 | All of above + dense pin tables | ⚠️ Pin count and multi-page gaps |
| Interface IC (UART, USB, CAN) | CH340, MCP2515 | 16–32 | Elec chars, pinout, timing table | 🟡 Mostly ok, timing table gaps |
| RF IC (transceiver, PA) | CC1101, nRF24L01 | 20–32 | Elec chars, RF specs, pinout | ⚠️ RF parameter units not handled |
| FPGA (small) | ICE40, ECP5 | 64–256+ | Elec chars, I/O standards, config | ❌ Not designed for this |
| Power MOSFET | IRLZ44N, AO3400 | 3–7 | Elec chars, thermal, gate charge | 🟡 Mostly ok |
| Diode / BJT | 1N4148, BC547 | 2–3 | Minimal tables | ✅ Trivially handled |
| Crystal / Oscillator | ABM8, SG-210 | 4–6 | Frequency, stability, ESR | ⚠️ Frequency parameter units |
| Connector | JST, Molex | N/A | Mechanical, ratings | ⚠️ Mechanical data not extracted |
| Passive (R, C, L) | Generic | 2 | Basic ratings | ✅ Trivially handled |

---

## Gap 1 — Large Pin Count Tables (MCU pinouts)

**Severity: HIGH**

**Problem:**
Current pipeline is designed around pinouts under ~30 pins. A large MCU like
STM32F407 has 144 pins. The pin function table spans multiple pages, has
complex alternate function columns (AF0–AF15), and uses dense abbreviations.

**Specific failures:**
- Multi-page pin table merge logic exists for simple cases but not for
  tables with 10+ columns and 100+ rows
- `PinDefinition.alternate_functions: list[str]` stores alternate functions
  but Phase 3 extraction prompt only extracts simple alternate functions —
  not the AF0–AF15 column format used by STM32
- Phase 3 LLM prompt window may not fit a 144-row pinout table without chunking

**What needs to be built:**
- Pin table chunking: split large pin tables into N-row chunks, extract per
  chunk, merge results by pin_number deduplication
- AF column parser: detect and parse AF0–AF15 style columns specifically
- Pin count heuristic in section classifier: if PINOUT table > 50 rows,
  activate large-pin-count extraction path

**Files affected:**
- `src/datasheet/phase3_extract/prompt_templates.py` — PINOUT_PROMPT needs
  AF column variant
- `src/datasheet/phase3_extract/extractor.py` — add chunking logic
- `src/schemas/datasheet.py` — `PinDefinition.alternate_functions` stays
  `list[str]` but needs richer content

---

## Gap 2 — Alternate Function / Pin Mux Extraction

**Severity: HIGH**

**Problem:**
MCU pins are multiplexed. Pin 42 might be GPIO_B5, SPI2_MOSI, TIM3_CH2, or
I2C1_SMBA depending on register configuration. The current `alternate_functions`
field stores these as a flat list of strings. The pin normalizer (P2) has no
way to disambiguate which function is the default vs which requires register config.

**Current state:**
```python
PinDefinition.alternate_functions: list[str] = ["SPI2_MOSI", "TIM3_CH2", "I2C1_SMBA"]
PinDefinition.normalized_function: Optional[str] = None  # set by P2
```

P2 normalizer picks one canonical function. For MCU pins this is wrong — the
pin has multiple equally valid functions.

**What needs to be built:**
- `PinDefinition.default_function: Optional[str]` — the reset-state function
- `PinDefinition.alternate_functions` stays but needs structured type:
  `list[AlternateFunction]` where `AlternateFunction` has `name`, `af_index`,
  `peripheral` fields
- P2 normalizer update: for MCU pins, normalize all functions, not just one
- Schema version bump required (breaking change to PinDefinition)

**Files affected:**
- `src/schemas/datasheet.py` — PinDefinition schema change (breaking)
- `src/knowledge_graph/pin_normalizer/` — multi-function normalization
- `db/migrations/` — new migration for pins table alternate_functions column

---

## Gap 3 — RF Parameter Units and Section Types

**Severity: MEDIUM**

**Problem:**
RF ICs (transceivers, PAs, LNAs) use parameter units and section names that
the current pipeline does not handle:

- Units: dBm, dBc, dB, ppm, Ω (impedance), VSWR, S-parameters (S11, S21)
- Section types: not in current `TableSectionType` enum
  - "RF Characteristics" → maps to ELECTRICAL_CHARACTERISTICS, fine
  - "Spurious Emissions" → no section type
  - "Phase Noise" → no section type
  - "Port Characteristics" → no section type

**Current state:**
`unit_normalizer.py` handles V, A, W, Hz, Ω, F, H. Does not handle dBm, dBc, ppm.
Phase 3 extraction prompt has no knowledge of RF-specific parameter names.

**What needs to be built:**
- Add dBm, dBc, dB, ppm to `unit_normalizer.py`
- Add RF section keywords to `section_classifier.py` pattern dict
  (map to ELECTRICAL_CHARACTERISTICS for now — no new enum value needed)
- Add RF parameter names to Phase 3 prompt context for methodology=RF_highfreq

**Files affected:**
- `src/datasheet/phase3_extract/unit_normalizer.py`
- `src/datasheet/phase1_dla/section_classifier.py`
- `src/datasheet/phase3_extract/prompt_templates.py`

---

## Gap 4 — Timing Tables vs Timing Diagrams (Detection Split)

**Severity: MEDIUM**

**Problem:**
The current `TableSectionType.TIMING` applies to both:
- Timing characteristics **tables** (rows of min/typ/max — extractable)
- Timing **diagrams** (waveform figures — not extractable, should skip)

Both get classified as TIMING. The pipeline currently extracts both,
which fails on the diagram (no tabular data to extract from a figure).

**What needs to be built:**
- In Phase 1, after DLA classifies a region as TIMING, check if the region
  bbox contains a figure (Baidu OCR returns `type=figure` for waveform regions)
  vs a table (`type=table`)
- Figure regions with TIMING context → add to `review_flags` as skipped diagram
- Table regions with TIMING context → extract normally
- This split is already partially supported by Baidu OCR's region type output

**Files affected:**
- `src/datasheet/phase1_dla/__init__.py` — figure vs table split
- `src/datasheet/phase1_dla/section_classifier.py` — no change needed

---

## Gap 5 — Thermal and Package Data for Power Devices

**Severity: MEDIUM**

**Problem:**
Power MOSFETs, gate drivers, and power modules have thermal tables that the
current pipeline technically classifies as OTHER (no match) and skips.

These tables contain:
- θJA (junction-to-ambient thermal resistance) in °C/W
- θJC (junction-to-case) in °C/W
- Maximum power dissipation vs temperature
- Derating curves (figure — skip)

θJA and θJC are PCB-relevant: they determine whether a thermal via or heatsink
is needed. They should be in `ComponentDatasheet`.

**Current state:**
`ElectricalParameter` can store them (unit "°C/W" is valid) but the section
classifier does not route thermal tables to extraction. They land in OTHER
and get a generic extraction that often misses the thermal resistance symbol.

**What needs to be built:**
- Add thermal section keywords to section classifier:
  `r"thermal\s*characteristics"`, `r"thermal\s*resistance"`, `r"package\s*thermal"`
  → new `TableSectionType.THERMAL_CHARACTERISTICS` or route to ELECTRICAL_CHARACTERISTICS
- Add thermal parameter names to Phase 3 prompt (θJA, θJC, RθJA, RθJC)
- Add to unit normalizer: `°C/W`

**Files affected:**
- `src/schemas/datasheet.py` — optionally add THERMAL_CHARACTERISTICS to enum
- `src/datasheet/phase1_dla/section_classifier.py`
- `src/datasheet/phase3_extract/prompt_templates.py`
- `src/datasheet/phase3_extract/unit_normalizer.py`

---

## Gap 6 — Connector and Mechanical Data

**Severity: LOW for PCB design**

**Problem:**
Connector datasheets (JST, Molex, TE) have mechanical dimensions as their
primary data. No electrical characteristics tables exist. The current pipeline
extracts nothing useful from connector datasheets.

**Assessment:**
Connectors are selected by footprint, not by extracted parameters. The KiCad
and tscircuit libraries already contain connector footprints. The BOM generator
selects connectors by type (2-pin JST-PH) not by extracted electrical params.

**Decision:** Out of scope for parser expansion. Connectors are handled by
footprint library lookup, not datasheet extraction.

---

## Gap 7 — FPGA Datasheets

**Severity: LOW — defer**

**Problem:**
FPGA datasheets (ICE40, ECP5, Xilinx Artix-7) are structurally different:
- I/O standard tables (LVCMOS33, LVDS, SSTL) with dozens of configurations
- Configuration interface specs
- Bank-based I/O organization (not a flat pin list)
- Hundreds to thousands of pins

The current pipeline would extract a partial pinout and miss the I/O standard
tables entirely.

**Decision:** Defer. FPGAs require a separate parsing strategy — bank-aware
pin extraction and I/O standard tables. This is a v2 problem. If a FPGA
datasheet is encountered, the pipeline produces a skeleton datasheet with
`review_required=True`.

---

## Summary — Priority Order

| Gap | Severity | Effort | Blocks |
|---|---|---|---|
| Gap 1 — Large pin count / MCU pinout | HIGH | Medium | MCU schematic synthesis |
| Gap 2 — Alternate function extraction | HIGH | High | MCU net assignment |
| Gap 3 — RF parameter units | MEDIUM | Low | RF methodology BOMs |
| Gap 4 — Timing table vs diagram split | MEDIUM | Low | Clean extraction on MCU datasheets |
| Gap 5 — Thermal data for power devices | MEDIUM | Low | Thermal review flags |
| Gap 6 — Connector mechanical data | LOW | — | Skip — not relevant |
| Gap 7 — FPGA datasheets | LOW | Very High | Defer to v2 |

---

## What Baidu OCR / PaddleOCR Changes

Replacing YOLOv8 + pdfplumber with Baidu OCR affects gaps as follows:

| Gap | Impact of Baidu OCR |
|---|---|
| Gap 1 (large pin tables) | ✅ Helps — better table detection on dense tables |
| Gap 2 (alternate functions) | Neutral — extraction prompt issue, not detection |
| Gap 3 (RF units) | Neutral — unit normalizer issue |
| Gap 4 (timing split) | ✅ Helps — Baidu OCR returns figure vs table type natively |
| Gap 5 (thermal data) | Neutral — section classifier issue |
| Gap 6 (connectors) | Neutral — out of scope |
| Gap 7 (FPGA) | Neutral — architectural issue |

Baidu OCR's native figure/table region type output directly solves Gap 4
with no additional code. Everything else requires prompt and schema changes
independent of the OCR backend.