# Golden Corpus

Five hand-verified datasheets for evaluation. Each pair:

- `TI_<part>_v1.pdf` — source PDF (gitignored, download from TI)
- `TI_<part>_v1_ground_truth.json` — `ComponentDatasheet` ground truth

## Download Links

| File | URL |
|------|-----|
| TI_SN74LVC1G04_v1.pdf | https://www.ti.com/lit/ds/symlink/sn74lvc1g04.pdf |
| TI_TLV7021_v1.pdf | https://www.ti.com/lit/ds/symlink/tlv7021.pdf |
| TI_INA219_v1.pdf | https://www.ti.com/lit/ds/symlink/ina219.pdf |
| TI_LM5176_v1.pdf | https://www.ti.com/lit/ds/symlink/lm5176.pdf |
| TI_TMS320F28003x_v1.pdf | https://www.ti.com/lit/pdf/spruiz6 |

## Spike PDFs (subset)

Phase 0 spike uses: TLV7021, TMS320F28003x, LM5176.

## Validate Ground Truth

```bash
python -c "
from pathlib import Path
from src.schemas import ComponentDatasheet
import json
for f in Path('corpus/golden').glob('*_ground_truth.json'):
    ComponentDatasheet.model_validate(json.loads(f.read_text()))
    print('OK:', f.name)
"
```
