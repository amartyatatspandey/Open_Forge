# OpenForge Deployment Notes

## VRAM Budget (corrected from 05_SEARCH_STORAGE_DEPLOYMENT_ARCHITECTURE.md)

The original doc assumed all models run concurrently on one 8xH100 server.
This is incorrect. Actual VRAM requirements for concurrent operation:

| Model | VRAM |
|-------|------|
| Qwen2.5-7B-Instruct (inference) | ~14 GB |
| Qwen2-VL-7B-Instruct (multimodal) | ~20 GB |
| Qwen3-Embedding-8B Q4 (embedding) | ~5 GB |
| YOLOv8n-DocLayNet | ~0.5 GB |
| KV cache (5 concurrent users) | ~20–40 GB |
| **Total if all concurrent** | **~60–80 GB** |

A single 24GB GPU cannot run all models concurrently.
**Use sequential loading** (configured in `config/model_versions.yaml`):
load one model, run its stage, unload, load next.

For production with concurrent users, a 2×A100 80GB or 8×H100 config
is required. Do NOT present a single 24GB GPU as sufficient for production.

## RRF Tuning

`RRF_K = 60` is the current default (see `search_layers.py`).
k=60 is the standard default. k=20-30 gives more weight to top-ranked
items but requires a labeled eval set to tune safely.
**Do not change RRF_K without running the golden test suite.**

## Storage Estimates

The 2MB average datasheet size is valid for op-amps and passives.
RF/microwave ICs and FPGAs routinely have 20–50MB datasheets.
Track actual average datasheet size by category during Phase 1 ingestion
and re-estimate Phase 2/3 storage before provisioning NVMe.

The "40% dedup savings" figure has no empirical basis.
Run dedup on a 1,000-component sample, measure, then project.

## TCO (5-year)

Hardware capex is not the full cost. An 8×H100 server draws ~10kW under load.

| Cost item | 5-year estimate |
|-----------|----------------|
| Hardware capex | $400K–$650K |
| Power (10kW × $0.10/kWh × 43,800h) | ~$44K |
| Cooling (40% of power) | ~$18K |
| Network, UPS, datacenter space | ~$50K–$100K |
| **Realistic 5-year TCO** | **$512K–$812K** |

## DRDO Procurement Timeline

Hardware procurement in DRDO is realistically 12–24 months from
requisition to delivery. Real break-even from project start is
30–42 months, not 18. Plan cloud spend to bridge the procurement gap.
Consider a 2×A100 interim configuration running Qwen2.5-72B to bridge.
