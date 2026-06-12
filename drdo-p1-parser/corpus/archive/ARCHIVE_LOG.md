# Corpus Archive Log

Removed components are archived here with rationale. Files are moved, not deleted.

---

## TI_TMS320F280039C — Archived 2025-06-12

**Reason:** Out of P1 scope. 254-page DSP microcontroller with 100-pin × 16 mux
position pinout (1600+ configurations) and 20+ subsystem electrical tables.
P1 pipeline targets analog/power ICs with clean, single electrical characteristics
tables (< 30 pins, < 5 pages of specs).

**Replacement:** TI_TPS62933 (sync buck converter)

**Note:** No ground-truth JSON file was present in `corpus/golden/` at archive time;
this entry documents the corpus selection decision only.
