# OpenForge — Frontend Experience Design
## Post-Fork Zero-Friction Utility Interface

**Version:** 1.0  
**Status:** Design — not yet implemented  
**Audience:** Open-source contributors, DRDO internal engineers, fork users

---

## 1. Design Philosophy

The frontend is a **utility interface**, not a product. Its job is to make every
interaction that currently requires knowing internal file paths, Python internals,
or CLI command syntax unnecessary. A domain engineer who knows PCB design but has
never read the OpenForge source code should be able to:

1. Fork and clone the repo
2. Run one setup command
3. Submit a design prompt
4. Handle review gates as they appear
5. Receive fabrication-ready files

**Everything else is incidental complexity that the UI must absorb.**

---

## 2. Hard Constraints (Non-Negotiable)

- **Offline-first.** The entire UI must run without internet access. No CDN imports,
  no cloud fonts, no external asset URLs. All assets must be bundled or generated
  locally.
- **Python-only dependency stack.** No Node.js build step. No npm. No webpack.
  `pip install -e .` must be the only installation command the user runs.
- **Air-gap safe.** The UI communicates only with the local machine. No telemetry,
  no analytics, no external API calls from the frontend.
- **GPU-aware.** The UI must reflect model loading state and prevent concurrent
  inference requests (the 24GB GPU runs one model at a time).
- **CLI still works.** The UI is additive. Power users who prefer the existing CLI
  (`python -m src.review.cli`) must not be broken.

---

## 3. Technology Recommendation

**Primary:** [Textual](https://textual.textualize.io/) — Python TUI framework.  
**Secondary:** [FastAPI](https://fastapi.tiangolo.com/) + lightweight HTML
(Jinja2 templates, no JS framework) for users who prefer browser access.

### Why Textual (TUI)

- Pure Python, no build step, ships as a pyproject.toml dependency.
- Works over SSH — critical for the air-gapped lab GPU machine.
- Rich component library: progress bars, tables, forms, panels, modal dialogs.
- Mouse support + keyboard navigation.
- The 4 review gates are naturally modal dialogs in a TUI — exactly the right
  interaction model (present information, require a decision, continue).

### Why FastAPI as secondary

- The same SQLite review queue, same config, same pipeline functions.
- Jinja2 templates render server-side — no JS required.
- The browser UI is a progressive enhancement for users on a workstation
  who can access the GPU server over LAN.

### Launch command (target UX)

```bash
# TUI (primary — air-gap, SSH, GPU lab)
openforge ui

# Browser (secondary — workstation → GPU server over LAN)
openforge serve --port 7860
```

Both launch via the same `openforge` CLI entry point defined in `pyproject.toml`.

---

## 4. View Structure

The UI has five primary views. The TUI uses a sidebar navigation; the browser
version uses tabs.

```
┌─────────────────────────────────────────────────────┐
│  OPENFORGE                                          │
│  ─────────────────────────────────────────────────  │
│  [1] Setup          System status + first-run       │
│  [2] Design         Submit prompts, track pipeline  │
│  [3] Review Queue   Human-in-the-loop gates         │
│  [4] KB Status      Knowledge base coverage         │
│  [5] Population     Run KB population + scraping    │
└─────────────────────────────────────────────────────┘
```

---

## 5. View 1: Setup (First-Run Wizard)

Shown on first launch if models are not downloaded or KB is empty. Guides
the user through every one-time configuration step in order.

### Steps

**Step 1 — Environment check**
Display a checklist of system requirements with live status icons:
```
✅  Python 3.11
✅  CUDA 12.1 detected (24GB VRAM)
✅  Poppler (pdf2image)
✅  Node 20 (tscircuit CLI)
⚠️  PostgreSQL not running — start with: docker compose up -d
❌  Model weights missing — run Step 2
```

**Step 2 — Model download**
Single button: "Download Models". Shows per-model progress bars.
Models are fetched from the paths defined in `config/model_versions.yaml`.
Estimated time shown per model. Download can be resumed if interrupted.
```
Downloading YOLOv8n-DocLayNet    ████████████████░░░░  80%   420 MB / 527 MB
Downloading Qwen2-VL-7B          ██░░░░░░░░░░░░░░░░░░  10%   1.4 GB / 14 GB
Downloading Qwen2.5-7B           ████████████████████ 100% ✅
Downloading Qwen3-Embedding-8B   ░░░░░░░░░░░░░░░░░░░░   0%   queued
```

**Step 3 — Configuration**
Form fields for the configurable settings (pre-populated from `configs/default.yaml`):
- DigiKey API credentials (client ID + secret) — masked input
- Nexar API key — masked input
- Output directory path
- Max GPU VRAM allocation
- Confidence thresholds (BOM total: 0.85, component: 0.75) with sliders

**Step 4 — KB Population**
Single button: "Run Initial Population". Links to View 5 (Population) for
detailed monitoring. Shows a summary status:
```
Population Status
KG-3 components:    0 / ~10,000 estimated
App notes:          0 / 12 planned
Datasheets queued:  0
```

**Step 5 — Ready**
Green banner: "OpenForge is ready."
Links to View 2 (Design).

---

## 6. View 2: Design

The primary use-case view. This is where an engineer submits a design prompt
and monitors the pipeline.

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Design Prompt                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Design a precision current source with 100mA        │   │
│  │ stability using zero-drift op-amps...               │   │
│  └─────────────────────────────────────────────────────┘   │
│  [▶ Run Design]                                             │
├─────────────────────────────────────────────────────────────┤
│  Pipeline Progress                                          │
│                                                             │
│  ✅  Stage 1: Intent Parsing          0.2s                 │
│  ✅  Stage 2: Requirement Completion  1.4s                 │
│  ✅  Stage 3: KB Retrieval            0.3s                 │
│  ✅  Stage 4: BOM Generation          0.8s                 │
│  ⚙️  Stage 5: Datasheet Parsing       [██████░░░░] 61%     │
│  ⏳  Stage 6: Pin Normalization       waiting              │
│  ⏳  Stage 7: Schematic Synthesis     waiting              │
│  ⏳  Stage 8: Layout + NIR            waiting              │
│  ⏳  Stage 9: Output Generation       waiting              │
│                                                             │
│  GPU: Qwen2-VL-7B loaded  ████████████████░░░░  22GB/24GB │
├─────────────────────────────────────────────────────────────┤
│  Search Controller (Stage 7)                                │
│  BOM Candidates: 3  │  ASHA Round: 2/4  │  ERC: 0.82      │
│  SA Polisher: active  │  Steps taken: 12  │  ERC: 0.94     │
└─────────────────────────────────────────────────────────────┘
```

### Search Controller Panel

The unified search controller (ASHA + SA polisher + beam search) runs as part
of Stage 7. This panel shows its live state:
- Current BOM candidate index and total
- ASHA round number and budget
- Current ERC score per candidate (color coded: red < 0.8, yellow 0.8–0.95, green 1.0)
- Which sub-controller is active (ASHA / SA polisher / beam search escalation)
- SA polisher step count when active

### Design History

Below the current run, a scrollable list of recent designs with their final
status (completed / review_required / failed) and output file links.

---

## 7. View 3: Review Queue

This is the most critical view. It replaces the existing CLI review interface
with a form-based interaction that makes the 4 gates approachable for
engineers who are not comfortable with command-line tools.

### Queue Overview Panel

```
Review Queue   3 pending   1 critical

┌──────────┬──────────────────────────────┬──────────┬───────────┐
│ Gate     │ Item                         │ Severity │ Age       │
├──────────┼──────────────────────────────┼──────────┼───────────┤
│ Intent   │ "precision current source"   │ CRITICAL │ 2 min ago │
│ BOM      │ a1b2c3d4 (LDO design)        │ WARNING  │ 5 min ago │
│ NIR      │ f7e8d9c0 (op-amp buffer)     │ CRITICAL │ 12 m ago  │
└──────────┴──────────────────────────────┴──────────┴───────────┘
```

Clicking any row expands the detail panel for that gate.

---

### Gate 1 Detail: Intent Clarification

Triggered when `IntentDict.clarification_required == True`.

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚠️  Gate 1 — Intent Clarification Required                     │
│  ─────────────────────────────────────────────────────────────  │
│  Original prompt:                                               │
│  "Design a precision current source with 100mA stability"       │
│                                                                 │
│  Ambiguities detected (blocking):                               │
│                                                                 │
│  1. operating_environment                                       │
│     "precision current source" without temperature range.       │
│     Required for zero-drift op-amp selection.                   │
│     ┌───────────────────────────────────────────────────────┐  │
│     │  Please specify: ○ -40 to 85°C  ○ 0 to 70°C          │  │
│     │                  ○ 15 to 35°C   ● Custom: [_______]  │  │
│     └───────────────────────────────────────────────────────┘  │
│                                                                 │
│  2. supply_voltage                                              │
│     No supply voltage specified. Affects LDO + op-amp choice.  │
│     ┌───────────────────────────────────────────────────────┐  │
│     │  Supply voltage: [±15V    ▾]                          │  │
│     └───────────────────────────────────────────────────────┘  │
│                                                                 │
│  [Cancel]                          [Re-run with clarifications] │
└─────────────────────────────────────────────────────────────────┘
```

When the user fills in the fields and clicks "Re-run with clarifications",
the form values are appended to the original prompt and the intent parser
is re-called automatically. No manual prompt rewriting required.

---

### Gate 2 Detail: BOM Review

Triggered when `ValidatedBOM.review_required == True`.

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚠️  Gate 2 — BOM Review Required                               │
│  Design ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890               │
│  Total confidence: 0.74  (threshold: 0.85)                      │
│  ─────────────────────────────────────────────────────────────  │
│  Bill of Materials                                              │
│                                                                 │
│  Ref  Type              Part            Conf   Flags            │
│  U1   ldo_regulator     TPS7A20DRVR     0.92   —               │
│  C1   input_capacitor   ⚠️ UNRESOLVED   0.62   No specific part │
│  C2   output_capacitor  ⚠️ UNRESOLVED   0.63   No specific part │
│  R1   feedback_resistor 10kΩ 0402        0.90   —               │
│                                                                 │
│  Flags:                                                         │
│  • C1: No specific part found — please select from suggestions  │
│  • C2: No specific part found — please select from suggestions  │
│                                                                 │
│  C1 suggestions (from KG-3):                                    │
│  ● GRM155R61A106ME11  (Murata, 10µF 0402, $0.08)              │
│  ○ CL05A106MP5NUNC    (Samsung, 10µF 0402, $0.07)              │
│  ○ Enter part number: [_______________________]                 │
│                                                                 │
│  [Reject — re-run BOM]   [Approve with selections]             │
└─────────────────────────────────────────────────────────────────┘
```

The reviewer selects or enters specific parts for unresolved components.
"Approve with selections" writes the corrections and continues the pipeline.
"Reject — re-run BOM" puts the design back to Stage 3 with the current BOM
flagged for the search controller to try alternative candidates.

---

### Gate 3 Detail: Datasheet Extraction Review

Triggered when `ComponentDatasheet.review_required == True` after Phase 4.

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚠️  Gate 3 — Datasheet Extraction Review                       │
│  Component: OPA189IDBVR   Verdict: WARN                         │
│  Extraction confidence: 0.64  (threshold: 0.70)                 │
│  ─────────────────────────────────────────────────────────────  │
│  Flagged extractions:                                           │
│                                                                 │
│  Parameter          Extracted    Confidence   Source page       │
│  ─────────────────  ──────────   ──────────   ──────────────    │
│  Offset voltage     ± 5 µV       0.55         Page 4           │
│  Offset drift       0.005 µV/°C  0.48  ⚠️     Page 4           │
│  Input bias current 200 pA       0.71         Page 5           │
│                                                                 │
│  [View source page 4]  →  opens PDF viewer panel to page 4     │
│                                                                 │
│  Corrections:                                                   │
│  Offset drift:  [0.005    ] [µV/°C ▾]   ← edit extracted value │
│                                                                 │
│  [Reject extraction]   [Approve with corrections]              │
└─────────────────────────────────────────────────────────────────┘
```

Inline PDF viewer panel on the right (rendered as image via pdf2image)
shows the source page for the flagged extraction. The reviewer can correct
values inline without switching to another tool.

---

### Gate 4 Detail: NIR Structural Review

Triggered when `nir.is_review_required() == True`.

```
┌─────────────────────────────────────────────────────────────────┐
│  🔴  Gate 4 — NIR Review Required                               │
│  Design ID: f7e8d9c0   Stage: nir_validation                    │
│  Critical flags: 2                                              │
│  ─────────────────────────────────────────────────────────────  │
│  Critical Issues:                                               │
│                                                                 │
│  1. [CRITICAL] Schematic synthesis — schematic_synthesis        │
│     Unresolved power pin POWER_GROUND on U2 (OPA189)           │
│     → Pin 4 (V-) not connected to any ground net               │
│                                                                 │
│  2. [CRITICAL] NIR validation — nir_validation                  │
│     Net VCC_3V3 references unknown ref U3                       │
│     → U3 appears in netlist but not in BOM                     │
│                                                                 │
│  Structural verifier score: 0.71                                │
│  Layer 1 (ERC):        0.80                                     │
│  Layer 2 (Pin roles):  0.60  ← driver conflict on VCC_3V3     │
│  Layer 3 (Templates):  0.75                                     │
│                                                                 │
│  Actions:                                                       │
│  ○ Approve as-is (manual inspection complete)                   │
│  ● Re-run synthesis (run beam search escalation)               │
│  ○ Reject and return to BOM (fundamental redesign needed)       │
│                                                                 │
│  Notes: [_______________________________________]               │
│                                                                 │
│  [Cancel]                                    [Confirm action]   │
└─────────────────────────────────────────────────────────────────┘
```

The structural verifier layer breakdown gives the reviewer a precise
diagnosis of what is wrong. The three action options map to the
three outcomes: approve and output, re-run the search controller,
or escalate to BOM redesign.

---

### Review Queue Badge

The nav sidebar shows a live badge count on the "Review Queue" item:

```
[3] Review Queue   ← red badge = 3 items pending (1 critical)
```

Badge updates without page refresh (polling or WebSocket for TUI).

---

## 8. View 4: KB Status

Shows the current state of the knowledge base. Helps users understand
what the system knows and what gaps remain.

```
┌─────────────────────────────────────────────────────────────────┐
│  Knowledge Base Status                                          │
│  Last population run: 2026-06-26 14:30  Duration: 4h 12m       │
│  ─────────────────────────────────────────────────────────────  │
│  Knowledge Graph                                                │
│  KG-1 (Physics):       1,247 nodes   3,891 edges               │
│  KG-2 (Recipes):         834 nodes   2,104 edges               │
│  KG-3 (Components):    8,341 nodes  42,817 edges               │
│  KG-4 (Placement):       421 nodes     987 edges               │
│  KG-5 (Methodology):      12 nodes      34 edges               │
│                                                                 │
│  Documents                                                      │
│  Total ingested:    8,341  │  Pending:  143  │  Failed:  7     │
│  Datasheets:        7,104  │  App notes:  12  │  Papers:  4    │
│  KiCad symbols:     8,012  │  KiCad footprints: 29,441         │
│                                                                 │
│  Category Coverage                                              │
│  LDO regulators     ████████████████████ 100%  (847 parts)    │
│  Buck converters    ████████████████░░░░  81%  (412 parts)    │
│  Op-amps           ████████████████████  97%  (1,204 parts)  │
│  ADCs (SAR)         ████████████░░░░░░░░  61%  (289 parts)    │
│  Zero-drift op-amps ████████░░░░░░░░░░░░  40%  (87 parts)    │
│  ─────────────────────────────────────────────────────────────  │
│  Scientist Gap Log Items                                        │
│  GAP-001-A (Libbrecht-Hall)   🔴 MISSING — blocks TASK_011    │
│  GAP-002-B (ZCOM VCO)         🔴 MISSING — blocks TASK_012    │
│  GAP-001-B (Zero-drift parts) 🟡 PARTIAL — 3/8 ingested       │
└─────────────────────────────────────────────────────────────────┘
```

The gap log section links directly to the scientist prompt analysis log and
shows which eval benchmark tasks are blocked by missing KB content.

---

## 9. View 5: Population Run

Controls the KB scraping engine. Run before first use and periodically
to ingest new components.

```
┌─────────────────────────────────────────────────────────────────┐
│  Knowledge Base Population                                      │
│  ─────────────────────────────────────────────────────────────  │
│  Phases to run:                                                 │
│  ☑  Phase 1: MPN Discovery (KiCad + DigiKey)                   │
│  ☑  Phase 2: PDF URL Resolution (Nexar + fallbacks)            │
│  ☑  Phase 3: PDF Download                                       │
│  ☑  Phase 4: Parse + KG Ingest                                 │
│  ☐  Phase 5: Family Expansion (runtime, runs automatically)    │
│                                                                 │
│  [▶ Start Population Run]   [Resume (143 pending remaining)]   │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│  Current Run Progress                                           │
│                                                                 │
│  Phase 1 ✅  MPN discovery complete: 9,247 unique MPNs         │
│  Phase 2 ✅  PDF URLs resolved: 8,412 / 9,247 (91%)           │
│  Phase 3 ⚙️  Downloading PDFs:  ████████████░░░░  6,891/8,412  │
│  Phase 4 ⏳  Waiting for Phase 3                               │
│                                                                 │
│  Download speed: 12 MB/s   │   Estimated remaining: 23 min     │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│  Manual Gap Fill                                                │
│  [+ Add document manually]   ← opens file picker + type select │
│                                                                 │
│  Queued manual items:                                           │
│  • libbrecht_hall_1993.pdf    → RESEARCH_PAPER   ⏳ pending   │
│  • TI_SBOA327.pdf             → APP_NOTE         ✅ ingested  │
└─────────────────────────────────────────────────────────────────┘
```

The "Resume" button is shown when `documents` table has rows with
`ingestion_status = 'pending'` from a previous run that was interrupted.
Checkpoint/resume is automatic.

---

## 10. Output Panel

After a successful design run (all review gates passed), a panel appears
in View 2 showing the output files:

```
┌─────────────────────────────────────────────────────────────────┐
│  ✅  Design Complete — a1b2c3d4                                  │
│  ERC score: 1.0   │   Confidence: 0.92                          │
│  Search controller: ASHA (2 rounds) + SA polisher (14 steps)    │
│  ─────────────────────────────────────────────────────────────  │
│  Output Files                                                   │
│                                                                 │
│  📄 a1b2c3d4_report.pdf          [Open]  [Copy path]           │
│  📐 kicad/a1b2c3d4.kicad_sch    [Open in KiCad]               │
│  📐 kicad/a1b2c3d4.kicad_pcb    [Open in KiCad]               │
│  📦 kicad/a1b2c3d4_gerbers.zip  [Download]                     │
│  🔧 tscircuit/a1b2c3d4.tsx      [Open]  [Copy path]           │
│  📋 a1b2c3d4_bom.csv            [Open]  [Copy path]           │
│                                                                 │
│  Provenance (why each component was selected):                  │
│  U1  TPS7A20DRVR  ← KG-3 (TI datasheet, confidence 0.97)     │
│  C1  GRM155R61A   ← Human selection at Gate 2                  │
│  R1  10kΩ 0402    ← KG-2 (TI SLVA477 LDO design recipe)       │
└─────────────────────────────────────────────────────────────────┘
```

The provenance panel shows exactly which source document drove each
component selection — the implementation of OpenForge's core claim.

---

## 11. Setup Flow (Post-Fork UX)

The complete zero-friction experience from first clone to first design:

```
git clone https://github.com/your-org/openforge
cd openforge
pip install -e .
openforge ui
```

On first launch, View 1 (Setup) is shown automatically. The wizard
walks through every step. No manual config file editing required.
All configuration from the wizard is written to `configs/default.yaml`
(which is in `.gitignore` so it does not contaminate the fork).

**If running on a remote GPU server:**
```bash
openforge serve --port 7860 --host 0.0.0.0
# → access from workstation at http://gpu-server-ip:7860
```

---

## 12. Review Gate Flow Summary

The four gates integrated into the UI flow:

```
[Submit prompt]
      │
      ▼
Gate 1 triggered?  ─── YES ──→ [Intent dialog]
      │                              │ resolve
      │ NO                           ↓
      ▼                         [re-submit]
[BOM generated]
      │
Gate 2 triggered?  ─── YES ──→ [BOM review panel]
      │                              │ approve / reject
      │ NO                           │
      ▼                              ↓ approve
[Datasheets parsed]            [continue pipeline]
      │
Gate 3 triggered?  ─── YES ──→ [Extraction review panel]
      │                              │ approve / correct
      │ NO                           │
      ▼                              ↓ approve
[Schematic + NIR]              [continue pipeline]
      │
Gate 4 triggered?  ─── YES ──→ [NIR review panel]
      │                              │ approve / re-run / reject
      │ NO                           │
      ▼                              ↓ approve
[Output files ready] ←──────────────┘
```

Each gate blocks pipeline execution on the backend (the Python pipeline
is not running while a gate is open). The UI polls the review queue
and shows a "waiting for review" indicator in the pipeline progress bar
when a gate is open.

---

## 13. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Startup time | < 2 seconds to TUI; browser view < 1 second (server-side render) |
| Poll interval for review queue | 2 seconds |
| GPU status refresh | 1 second |
| Pipeline stage progress | Live (sub-second updates via background thread) |
| Max review queue items shown | 50 (paginated beyond) |
| PDF viewer page render time | < 500ms per page (pdf2image at 150 DPI) |
| Offline fonts | Inter/JetBrainsMono bundled in the package, no CDN |
| Minimum terminal size (TUI) | 120×40 |
| Screen reader compatibility | Textual has built-in accessibility; alt text on all panels |

---

## 14. What the Frontend Does NOT Do

- No schematic editor — KiCad handles this; the UI links to KiCad files
- No PCB layout editor — same
- No model training or fine-tuning interface (corrections export is CLI-only)
- No multi-user support in v1 — single engineer session
- No remote design sharing or collaboration
- No cloud sync of review decisions

---

## 15. Implementation Priority

Build in this order after the 3 major backend problems are solved:

| Priority | Component | Reason |
|---|---|---|
| 1 | View 3 (Review Queue) | Replaces the existing CLI — biggest UX improvement |
| 2 | View 2 (Design) with pipeline progress | Core daily-use view |
| 3 | View 1 (Setup wizard) | First-run experience, enables open-source adoption |
| 4 | View 4 (KB Status) | Useful but not blocking |
| 5 | View 5 (Population Run) | Can remain CLI-driven initially |
| 6 | FastAPI browser variant | Progressive enhancement, not MVP |

The Review Queue view (Gate 1–4 panels) is the highest-value UI work
because it is the only part of the existing system with no usable interface
for non-CLI engineers. Everything else has a working but unfriendly CLI.