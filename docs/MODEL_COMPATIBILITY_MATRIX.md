# OpenForge Model Compatibility Matrix

## Cloud vs Local Model Delta

"Swapping llm_base_url is the only change needed" is an oversimplification.
This matrix documents the actual delta between cloud and local deployments.

| Feature | Cloud (Qwen2.5-72B API) | Local (Qwen2.5-7B vLLM) |
|---------|------------------------|------------------------|
| Context window | Up to 128K tokens | 32K tokens (configured) |
| JSON mode | Supported | Supported via Instructor |
| Tool calling | Supported | Supported (vLLM ≥0.4) |
| Structured outputs | Via Instructor | Via Instructor |
| Prompt stability | High | High (same family) |
| Throughput (5 users) | API rate limits apply | ~4-8 concurrent |
| Latency (Stage 2) | ~5–15s | ~10–30s (7B vs 72B) |
| Output quality | Higher (72B) | Acceptable (7B) |
| Air-gapped | No | Yes |
| Cost | ~$0.05-0.20/query | ~$0.001/query (power) |

## Testing Requirements on Model Change

Before updating any model version in `config/model_versions.yaml`:

1. Run `python -m pytest tests/` — all existing tests must pass.
2. Run `python tests/completion/smoke_test_real_prompts.py` — 12/12 required.
3. Run golden prompt set (when available) — precision/recall must not drop >2pp.
4. Document results in this file under a new version entry.

## Validated Model Versions

| Stage | Model | Version | Validated | Notes |
|-------|-------|---------|-----------|-------|
| Stage 1+2 | Qwen2.5-7B-Instruct | main | Mocked only | Pending GPU validation |
| Embedding | Qwen3-Embedding-8B | main | Not yet | Pending lab deployment |
| Multimodal | Qwen2-VL-7B-Instruct | main | Mocked only | Pending GPU validation |
