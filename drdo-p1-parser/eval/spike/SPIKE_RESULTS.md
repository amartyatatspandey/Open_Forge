# Model Spike Results

Phase 0 spike: YOLOv8-DocLayNet vs Surya for Phase 1 DLA.

## PDFs Processed

- `TI_TLV7021_v1.pdf`
- `TI_TPS62933_v1.pdf`
- `TI_LM5176_v1.pdf`

## Metrics

| Metric | YOLOv8-DocLayNet | Surya | Target |
|--------|------------------|-------|--------|
| Table detection recall | 0.833 | 0.000 | >= 0.92 |
| Footnote detection recall | 0.806 | 0.000 | >= 0.85 |
| Inference time / page (ms) | 79.333 | 0.000 | record |
| ONNX exportable | yes | check | yes |

## Decision

**Locked choice:** YOLOv8n-DocLayNet (Surya not available for comparison)

## Notes

- Detected 16 tables, 17 footnote-like regions
- Detected 10 tables, 13 footnote-like regions
- Detected 10 tables, 11 footnote-like regions
- surya-ocr not installed (optional spike dependency)
- surya-ocr not installed (optional spike dependency)
- surya-ocr not installed (optional spike dependency)
- Spike rasterizes first 5 pages at min(150, config DPI); production uses full doc at 300 DPI
