# Golden Corpus Manifest

## Status: 5/5 complete ✅

| # | Component | Type | Status | Pages | Notes |
|---|---|---|---|---|---|
| 1 | TI_SN74LVC1G04 | Logic Gate | ✅ Complete | ~10 | Single inverter |
| 2 | TI_TLV7021 | Comparator | ✅ Complete | ~20 | Simple analog |
| 3 | TI_INA219 | Current Sensor | ✅ Complete | ~30 | I2C interface |
| 4 | TI_LM5176 | Buck-Boost Controller | ✅ Complete | ~45 | Power IC |
| 5 | TI_TPS62933 | Sync Buck Converter | ✅ Complete | ~30 | Replacement for TMS320 |

## Archived

| Component | Reason |
|---|---|
| TI_TMS320F280039C | DSP MCU — out of P1 scope (254 pages, 1600+ pin mux configs) |

## Corpus Selection Criteria

- Analog or power management IC (no MCUs, DSPs, FPGAs)
- Single electrical characteristics table (not 20+ subsystem tables)
- Pinout under 30 pins preferred
- Representative of TI datasheet formatting variety
