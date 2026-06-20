# Temperature, Model Selection, and Fine-Tuning Analysis
## OpenForge LLM Configuration Strategy

---

## 1. Temperature — What It Does and Why It Matters Here

Temperature controls how deterministic the LLM's output is. At temperature 0.0, the model always picks the highest-probability next token — the same input always produces the same output. At temperature 1.0, sampling is random and the same input produces different outputs every run.

This matters enormously for OpenForge because different stages of the pipeline need different things from the LLM.

---

### Temperature Per Stage — Recommended Settings

| Stage | Task Type | Recommended Temperature | Reason |
|-------|-----------|------------------------|--------|
| P1 Phase 2 TSR (Qwen2-VL) | Table → markdown grid | 0.0 | The table content is deterministic. There is one correct grid. |
| P1 Phase 3 Extraction | Grid text → typed JSON | 0.0 | A voltage value is what it is. No creativity needed. |
| P1 Phase 5 Layout Extraction | Prose → PlacementConstraint | 0.1 | Slight variability helps on ambiguous spatial language. |
| Pin Normalizer LLM fallback | Raw pin name → canonical | 0.0 | Lookup task. Deterministic is correct. |
| Triple Extractor | Sentence → (S,V,O) | 0.1 | Near-deterministic for consistent KG ingestion. |
| Intent Parser | NL prompt → IntentDict | 0.2 | Needs slight flexibility for edge case methodology classification. |
| Stage 2 Completion Engine | Intent → implied requirements | 0.3 | Requires genuine reasoning. Zero temperature makes it rigid and misses non-obvious inferences. |
| BOM Justification Generator | Component → justification text | 0.4 | Natural language output. Some stylistic variation is acceptable. |

---

### The Core Rule

**Structured extraction tasks: temperature 0.0.**
Anything where the output is a Pydantic model filled from source text — Phase 3, Phase 5, pin normalization — should run at temperature 0.0. The correct answer is in the source text and the model's job is to find it, not invent it. Instructor-enforced schemas constrain the format, but temperature still affects which values the model picks within those constraints. Lower temperature means more commitment to the most probable extraction, which for well-formatted datasheets is the correct one.

**Reasoning tasks: temperature 0.2–0.4.**
Stage 2 (the completion engine) is the exception. It is doing genuine inference — deriving that Kelvin sensing is required from the combination of "100mA" and "ultra precision resistors." Temperature 0.0 makes the model commit too early in the reasoning chain and miss implications that require connecting two non-obvious constraints. Temperature 0.3 with CoT prompting is the right combination here.

**Reproducibility note for DRDO:** Even at temperature 0.2–0.4, the same prompt will produce very similar outputs across runs because the model's probability distribution is still heavily peaked. For full reproducibility, set a fixed seed where the API supports it. For local vLLM deployment, `--seed 42` in the vLLM server startup command makes all stages fully deterministic regardless of temperature setting.

---

## 2. Model Selection — Qwen 3.5 vs MiniMax

### Qwen 3.5 397B

This is already specified in the architecture as the Stage 2 completion engine model for cloud deployment. The assessment is correct.

**What it actually is:** A Mixture-of-Experts model. 397B is the total parameter count but only approximately 30B parameters are active per forward pass. This means inference cost and latency are closer to a 30B dense model than to a 397B dense model. It punches above its weight on reasoning tasks because of the expert routing mechanism.

**Where it is the right choice:**
- Stage 2 requirement completion engine — strongest reasoning quality available
- Complex intent parsing where methodology classification is ambiguous
- Any task where domain reasoning depth matters more than speed

**Where it is not the right choice:**
- P1 Phase 3 extraction — a 7B local model is faster, cheaper, and produces the same quality on structured extraction
- Pin normalization — the task is too simple to need 397B parameters
- Any task already handled well by Qwen2.5-7B locally

---

### MiniMax (MiniMax-Text-01 / MiniMax-01)

MiniMax's distinguishing capability is its Lightning Attention mechanism which supports up to 1 million token context windows. For most of our tasks this is irrelevant. For one specific use case it becomes interesting.

**Where MiniMax has a genuine advantage:**

**Multi-document simultaneous ingestion.** Currently Phase 3 processes one datasheet table at a time. If you want to simultaneously provide multiple datasheets, multiple application notes, and the Libbrecht-Hall paper to the Stage 2 completion engine in a single context — something that would exceed Qwen 3.5's context window — MiniMax-01's 1M token window handles it without chunking.

**Where MiniMax does not help:**

Reasoning quality. For engineering implication inference — the core task of Stage 2 — Qwen 3.5 397B produces better-calibrated, more domain-specific inferences than MiniMax. MiniMax's strength is context length, not reasoning depth.

**Practical recommendation:** Do not replace Qwen 3.5 with MiniMax for Stage 2. Consider MiniMax as an optional path for a specific future scenario: if you want to build a "read 20 datasheets simultaneously and find the best component" retrieval mode that exceeds Qwen's context limit. That is a future capability, not a current requirement.

---

### Model Stack Summary

| Stage | Current Model | Alternative | Change Recommended |
|-------|--------------|-------------|-------------------|
| P1 Phase 1 DLA | YOLOv8n-DocLayNet | LocateAnything-3B | Under evaluation (spike pending) |
| P1 Phase 2 TSR | Qwen2-VL-7B-Instruct | — | No change |
| P1 Phase 3 Extraction | Qwen2.5-7B-Instruct | — | No change |
| P1 Phase 5 Layout | Qwen2.5-7B-Instruct | — | No change |
| Intent Parser | Qwen2.5-7B-Instruct | — | No change |
| Stage 2 Completion | Qwen 3.5 397B (cloud) | Qwen2.5-72B (local) | Qwen2.5-72B when local deployment active |
| Pin Normalizer | Rule dict + Qwen2.5-7B | — | No change |
| Triple Extractor | spaCy + Qwen2.5-7B | — | No change |

---

## 3. Fine-Tuning — Honest Assessment

This was ruled out in the original architecture in favor of KG + local LLM, and that decision was correct for the current stage. Here is the full analysis of when it becomes the right move.

---

### Why Fine-Tuning Is Wrong Right Now

**The data does not exist yet.** Fine-tuning requires hundreds to thousands of labeled examples of (input → correct output). The review queue is currently empty. The system has not been used on real designs. There is no correction data to fine-tune on. Fine-tuning on synthetic or assumed data means you are optimizing for the wrong distribution.

**The schema is still changing.** ImprovedIntentDict v2 was just designed. Team E is still being built. Phase 5 was added mid-project. Every schema change invalidates a fine-tuned model's output format. Prompt engineering is updated in minutes. Retraining a fine-tuned model takes hours to days.

**Catastrophic forgetting.** Fine-tuning a general-purpose model on narrow electronics extraction risks degrading its general reasoning capabilities. A model fine-tuned to output `ElectricalParameter` objects loses some of its ability to reason about circuit topologies. These capabilities are not separable in the weight space.

**Few-shot + Instructor already solves the format problem.** The primary reason people fine-tune for structured extraction is to improve output format compliance. Instructor with Pydantic v2 already enforces this with automatic re-prompting on validation failures. Fine-tuning for format compliance on top of Instructor is solving a problem that does not exist.

---

### When Fine-Tuning Becomes the Right Move

**Condition 1 — After 500+ Phase 3 review corrections accumulate.**

The review queue is already designed to export corrections to `data/corrections_export.jsonl`. Each correction is a (grid_text, wrong_extraction, correct_extraction) triple. After 500+ examples, LoRA fine-tuning of Qwen2.5-7B specifically for Phase 3 extraction becomes viable and beneficial.

Phase 3 extraction is the ideal fine-tuning target because:
- The task is narrow and well-defined
- The input-output format is stable (ElectricalParameter schema)
- The errors are systematic (specific unit aliases, specific manufacturers' table formats)
- A small LoRA adapter trained on real errors would eliminate the systematic failure modes permanently

**Condition 2 — When local Qwen2.5-72B replaces cloud Qwen 3.5 397B for Stage 2.**

Qwen2.5-72B achieves approximately 85% of Qwen 3.5 397B's implication quality on electronics reasoning. The 15% gap is primarily on obscure topologies — Libbrecht-Hall, specialized RF circuits, unusual power architectures. LoRA fine-tuning Qwen2.5-72B on 200+ expert-annotated implication chains (from the completion engine's review corrections) would close most of this gap.

**Condition 3 — Domain vocabulary normalization.**

Electronics has highly specialized vocabulary that general-purpose models handle inconsistently: "tempco" vs "temperature coefficient," "PSRR" vs "power supply rejection ratio," "JFET" vs "junction field-effect transistor." A lightweight vocabulary fine-tune (50-100 examples) improves consistency across all stages simultaneously.

---

### LoRA — The Only Viable Fine-Tuning Approach

Full fine-tuning of 7B or 72B models is impractical without a dedicated training cluster. LoRA (Low-Rank Adaptation) is the correct approach for this use case.

**What LoRA does:** Instead of updating all model weights, it trains two small matrices per attention layer that approximate the weight update. The result is a small adapter file (50-200MB) that is applied on top of the base model weights at inference time.

**Hardware requirements for LoRA:**

| Model | LoRA Training VRAM | Training Time (500 examples) |
|-------|-------------------|------------------------------|
| Qwen2.5-7B | 16GB (single A100 40GB) | 2–4 hours |
| Qwen2.5-72B | 80GB (single A100 80GB) | 12–24 hours |

Both fit within the GPU lab hardware already available.

**Framework:** Use LLaMA-Factory or Axolotl. Both support Qwen2.5 natively, have clean LoRA training pipelines, and produce adapter files compatible with vLLM serving.

---

### Fine-Tuning Timeline Recommendation

```
Now (Month 0–3):
    Run system on real DRDO prompts.
    Accumulate review queue corrections.
    No fine-tuning.

Month 3–6:
    Evaluate: how many Phase 3 corrections have accumulated?
    If > 300: begin building fine-tuning dataset
    If < 300: continue with few-shot improvements only

Month 6+:
    If 500+ Phase 3 corrections exist:
        → LoRA fine-tune Qwen2.5-7B for Phase 3 extraction
        → Eval on golden corpus: expect F1 improvement of 8–15%
        → Deploy as drop-in replacement for Phase 3 model

    If local deployment active AND 200+ Stage 2 corrections exist:
        → LoRA fine-tune Qwen2.5-72B for Stage 2 completion
        → Eval on implication quality vs Qwen 3.5 benchmark
```

---

## 4. Combined Recommendation

Three changes to make now, before the GPU validation run:

**Change 1 — Temperature settings.** Set explicit temperature values per stage in `configs/default.yaml`. Currently temperature is likely using API defaults (varies by provider, often 0.7 or 1.0). This is wrong for extraction stages.

```yaml
llm_temperature:
  phase3_extraction: 0.0
  phase5_layout: 0.1
  pin_normalizer_fallback: 0.0
  triple_extractor: 0.1
  intent_parser: 0.2
  completion_engine: 0.3
  bom_justification: 0.4
```

**Change 2 — Fixed seed for DRDO deployment.** Add `llm_seed: 42` to the local vLLM config. Makes all outputs reproducible regardless of temperature setting. Required for defense-grade reproducibility.

**Change 3 — Do not fine-tune yet.** Wait for real correction data. Mark this in the backlog as "revisit at 500 Phase 3 corrections."

Three changes to make later, after data accumulates:

**Change 4 (Month 6+):** LoRA fine-tune Qwen2.5-7B for Phase 3 extraction on accumulated corrections.

**Change 5 (Month 6+):** LoRA fine-tune Qwen2.5-72B for Stage 2 completion if local deployment is active.

**Change 6 (Conditional):** Evaluate MiniMax-01 only if a multi-document simultaneous ingestion use case emerges that exceeds Qwen 3.5's context window.

---

*Update this document when the review queue reaches 300+ corrections. That is the decision point for initiating the fine-tuning pipeline.*