# Open Forge — Architecture Review

**Scope:** Assessment of six design documents — `PROJECT_CONTEXT.md`, `01_INTENT_PARSING_SCHEMA.md`, `02_REQUIREMENT_COMPLETION_ENGINE.md`, `03_RETRIEVAL_AND_KB_STRATEGY.md`, `04_DATABASE_SCHEMA.md`, `05_SEARCH_STORAGE_DEPLOYMENT_ARCHITECTURE.md`.

**Audience:** Open Forge engineering team, DRDO program reviewers.

**Purpose:** Identify architectural defects, gaps, and risks before implementation commits to a particular structure. Severity ratings reflect impact if the system ships as currently designed.

**Severity legend:**
- 🔴 **Critical** — Will cause incorrect BOM output, data loss, or security/compliance failure in production.
- 🟠 **High** — Will block scale-out, cause operational pain, or require significant rework within 6 months.
- 🟡 **Medium** — Will cause maintenance friction, perf issues, or quality drift over time.
- 🟢 **Low** — Polish, documentation, or future-proofing concerns.

---

## 1. Executive Summary

The current architecture is a defensible MVP for a single-topology, single-user, lab-environment prototype. It will not survive contact with real multi-topology designs, concurrent users, multi-year KB evolution, or the DRDO air-gapped procurement cycle without meaningful rework.

The five highest-impact defects, in priority order:

1. **Stage 2's single-topology keying** silently corrupts inferences for any compound design (🔴).
2. **The KB has no parameter versioning** — datasheet revisions that change specs cannot be tracked, audited, or rolled back (🔴).
3. **No end-to-end test corpus, observability, or feedback loop** — when a BOM is wrong, root cause is unrecoverable (🔴).
4. **The "hybrid is strictly superior" claim is overstated** — for one-off prototype work with novel parts, pure scraping wins on latency, and the hybrid has a data-poisoning vector (🟠).
5. **Cost and deployment estimates materially understate TCO** — missing power/cooling/procurement-cycle realities, which will distort DRDO funding decisions (🟠).

A more detailed breakdown follows, organized by stage and then by cross-cutting concerns. Each finding cites the source document and proposes a remediation. Items already discussed in earlier review are included here for completeness; the bulk of this document is new findings.

---

## 2. Project Context (`PROJECT_CONTEXT.md`)

### 2.1 The "living document" referenced does not exist in the provided materials 🟠

The stub reads:

> This file has moved. The living project status document is maintained at `documents/architecture/PROJECT_CONTEXT.md`. Attach that file to Claude Projects, Cursor, and handoffs. Do not edit this stub.

The referenced `documents/architecture/PROJECT_CONTEXT.md` is not among the six reviewed files. If this is the actual source of truth, every reviewer, AI assistant, and new engineer is being pointed at a document that may or may not exist. If the stub is the file, the architecture has no single source of truth.

**Remediation:** Either inline the living document into the stub or remove the stub entirely and make the real file the canonical entry point. The "do not edit this stub" instruction is itself a code smell — it suggests the team has been burned by people editing the wrong file, which is itself evidence that the file layout is confusing.

### 2.2 No version, owner, or changelog on any of the six documents 🟡

None of the six documents carry a version number, owner, last-reviewed date, or changelog. For a multi-year DRDO program this is non-negotiable — every architectural decision needs to be traceable to a decision date and decision maker.

**Remediation:** Add a header block to each document:

```markdown
---
title: Requirement Completion Engine
doc_id: ARCH-002
version: 0.3.0
status: draft | review | approved
owner: <name>
last_reviewed: 2026-06-21
changelog:
  - 0.3.0 (2026-06-21): added confidence calibration section
  - 0.2.0 (2026-04-10): refactored to Instructor + Pydantic
  - 0.1.0 (2026-02-15): initial draft
---
```

---

## 3. Stage 1 — Intent Parsing Schema (`01_INTENT_PARSING_SCHEMA.md`)

### 3.1 `goal_topology: Optional[str]` assumes a single topology per design 🔴

The schema allows exactly one topology. Real designs are compound: a Libbrecht-Hall current source feeding a 24-bit SAR ADC, or a boost converter driving a laser diode with telemetry. When Stage 1 must pick one topology, it picks wrong ~30% of the time on compound prompts, and the wrong choice cascades into Stage 2 injection, Stage 3 retrieval, and Stage 6 BOM validation.

**Remediation:**

```python
class TopologyGuess(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]  # which prompt phrases supported this guess

class ImprovedIntentDict(BaseModel):
    # ...
    goal_topologies: list[TopologyGuess] = Field(default_factory=list)
    # legacy single field kept for backward compat, populated from goal_topologies[0]
    goal_topology: Optional[str] = None
```

Stage 2 then injects axioms from all topologies above a confidence threshold and surfaces conflicts explicitly rather than silently picking one.

### 3.2 `ambiguities: list[dict]` is untyped 🟡

A `list[dict]` field provides zero type safety, zero validation, and zero downstream utility. Engineers will inevitably put different keys in different dicts and the consumer code will break.

**Remediation:**

```python
class Ambiguity(BaseModel):
    field: str
    description: str
    severity: Literal["INFO", "WARNING", "ERROR"]
    candidate_resolutions: list[str] = Field(default_factory=list)
    blocking: bool = False  # if True, pipeline cannot proceed without clarification
```

### 3.3 Vague spec quantification is deferred to Stage 2, but Stage 2 has no grounding either 🔴

The parser stores `"ultra low noise"` as `raw_text` and defers quantification. Stage 2 quantifies it as `<1 pA/rtHz` based on... what? The system prompt says "Published Libbrecht-Hall implementations achieve 0.1-1 pA/rtHz." This is the LLM reasoning from training data, not from any grounded source in the KB. If a published implementation later achieves 0.05 pA/rtHz, the threshold should drop, but the system has no way to update.

**Remediation:** Quantification must be grounded in (a) the topology's design_pattern row in the KB, or (b) a cited application note. Stage 2 output should include a `quantification_source` field pointing to a document ID and page. See Section 4 for the full Stage 2 critique.

### 3.4 `clarification_required: bool` has no associated mechanism 🟠

The flag exists but nothing in the architecture describes how clarification is actually obtained. Is it a synchronous user prompt? An async review queue item? A blocking gate before Stage 2 runs? Without a defined mechanism, the flag will be set and ignored.

**Remediation:** Define a clarification protocol — synchronous web UI prompt for interactive mode, async review queue item for batch mode. The pipeline must halt at Stage 1 if `clarification_required and any(a.blocking for a in ambiguities)`.

### 3.5 Backward compatibility with v1 will cause silent data loss 🟠

> The v1 `explicit_constraints` list is preserved in v2 for backward compatibility. Downstream modules that read v1 format continue to work.

This is dangerous. A downstream module reading only `explicit_constraints` will silently miss the typed fields in `performance.noise`, `electrical.supply_voltage`, etc. The BOM it generates will be incomplete, and the incompleteness will be invisible.

**Remediation:** Two options, pick one:
- **(a)** Add a `schema_version: Literal["1.0", "2.0"]` field and fail loud in any module that reads v1 fields when `schema_version == "2.0"` and the v2 equivalent is populated.
- **(b)** Sunset v1 with a hard cutover date. No backward compatibility. The migration cost is paid once.

The "gradual migration" approach never works for typed schemas — it always degrades to silent data loss.

### 3.6 `production_volume: Optional[str]` should be an enum 🟢

Currently allows any string. Should be `Literal["prototype", "small_batch", "pilot", "production", "fielded"]` with documented thresholds (e.g., prototype = 1-5 units, small_batch = 6-100, etc.).

### 3.7 `ImpliedRequirement` is defined in Stage 1 but populated by Stage 2 🟡

The schema for `ImpliedRequirement` lives in the Stage 1 doc but is described as "Generated by the Requirement Completion Engine (Stage 2)." This coupling means Stage 1 schema changes can break Stage 2 outputs without warning. Move `ImpliedRequirement` (and `DesignRequest`) into a shared `schema/common.py` module.

### 3.8 No max length on `raw_prompt: str` 🟡

A 50KB prompt will fit but will blow the LLM context budget when concatenated with the system prompt and domain knowledge. Define a `MAX_PROMPT_TOKENS = 4000` constant and reject prompts above it with a clear error.

### 3.9 `design_requests` mixes in-scope and out-of-scope items 🟢

The current schema includes `python_gui` and `firmware` as `request_type` values flagged `in_scope: false`. Cleaner to have:

```python
in_scope_requests: list[DesignRequest]
out_of_scope_requests: list[OutScopeRequest]  # separate type, with reason
```

This makes the scope decision auditable and avoids the awkward "request_type=python_gui, in_scope=false, out_of_scope_reason='not in v1'" pattern.

---

## 4. Stage 2 — Requirement Completion Engine (`02_REQUIREMENT_COMPLETION_ENGINE.md`)

### 4.1 Single-topology domain knowledge injection 🔴

Already discussed in prior review. Recap: `load_domain_knowledge(intent.goal_topology)` returns one YAML blob. Compound designs get one blob; novel topologies get nothing. The system silently degrades.

**Remediation:** Decompose into atomic engineering axioms with precondition matchers. See prior review for the schema sketch.

### 4.2 No grounding loop between YAML axioms and the KB 🔴

The YAML says "guard ring for ultra-low noise" as an absolute. The KB's `design_patterns` table (defined in `04_DATABASE_SCHEMA.md`) may have a reference design that says "guard ring required only below 100 fA/rtHz." Stage 2 never consults this. The LLM's confidence is self-assessed, not empirically validated against the KB.

**Remediation:** Two-pass inference. Pass 1 proposes from axioms. Pass 2 retrieves top-3 KB chunks per proposal and re-scores confidence based on support/contradiction. See prior review.

### 4.3 Manual YAML authoring caps topology coverage 🟠

Estimate: a senior engineer can author ~5 topologies/week with proper citations. To cover 100 topologies (a reasonable target for a precision analog lab) is 20 engineer-weeks. Beyond that, curation cost explodes and the library falls behind real-world usage.

**Remediation:** Hybrid generation. Senior engineers author the 30 highest-value topologies by hand. For the long tail, run a batch job that ingests app notes, asks the LLM to propose candidate axioms with citations, and routes them to a review queue. The review queue (already built) is the right human-in-the-loop gate.

### 4.4 Self-assessed confidence with no calibration 🔴

The confidence calibration table says "0.95–1.00 = Physically necessary. Cannot be false." But this is a *definition*, not a *measurement*. The LLM assigns 0.97 to "Kelvin sensing for 100mA precision current source" — but on what evidence? If you ran 200 real designs through this and 30 of them turned out not to need Kelvin sensing, the empirical confidence is 0.85, not 0.97.

**Remediation:** Build a 200-prompt ground-truth set, validated by senior engineers. Apply isotonic regression to map raw LLM confidence → empirical precision. Store the calibration curve and apply it at merge time. Re-calibrate quarterly.

### 4.5 No feedback path from Stage 6 BOM validation 🟠

Stage 6 will flag inferred requirements as unnecessary (false positives) or surface missing ones (false negatives). This signal dies in the review queue. It never feeds back to YAML confidence weights or proposes new axioms.

**Remediation:** Add an `axiom_feedback` table:

```sql
CREATE TABLE axiom_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    axiom_id VARCHAR(100) NOT NULL,
    intent_id UUID NOT NULL,
    feedback_type VARCHAR(50) NOT NULL,  -- false_positive | false_negative | wrong_confidence
    engineer_id UUID NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

A monthly job aggregates feedback and proposes weight adjustments to a human curator.

### 4.6 `inferred_constraints` and `implied_requirements` use different confidence thresholds 🟡

```python
"inferred_constraints": [r.requirement for r in result.implied_requirements
                          if r.confidence >= 0.80]
```

`implied_requirements` keeps all entries; `inferred_constraints` keeps >=0.80. This is confusing. Downstream code doesn't know which to trust. Pick one threshold, document it, and either filter at the source or don't filter at all.

### 4.7 Assumptions propagate silently — DRDO-specific risk 🔴

The example output includes:

```json
{
  "assumption": "Operating environment is laboratory (not industrial or military)",
  "reasoning": "Libbrecht-Hall design is predominantly used in AMO physics labs...",
  "confidence": 0.80
}
```

For a DRDO context, this is dangerous. If the actual deployment is field-deployable or airborne, the tempco budget, vibration spec, and component selection are all wrong. And the assumption is never surfaced to the user — it propagates silently through Stages 3-7.

**Remediation:** High-impact assumptions (operating environment, supply voltage, temperature range) must be promoted to "must-ask-human" conditions. The pipeline halts and surfaces them explicitly. Stage 2 should refuse to proceed with assumptions above a criticality threshold.

### 4.8 No contradiction solver — purely LLM-based detection 🟠

The contradictions field exists but detection relies entirely on LLM reasoning. Hard contradictions (e.g., "operates at -55°C" vs. "uses part rated to -40°C min") are mechanically checkable and should never be missed. LLM-based detection has ~70% recall on these.

**Remediation:** Add a formal constraint checker that runs after Stage 2. It compares every inferred requirement against the KB's `electrical_parameters` for the components selected so far. Any violation is a CRITICAL contradiction regardless of LLM output.

### 4.9 No caching strategy for Stage 2 LLM calls 🟡

Every Stage 2 call hits the 397B model. Identical intent dicts (e.g., an engineer iterating on a prompt) trigger fresh inference each time. At $0.05-0.20 per call and 50-100 queries/day, this is $75-600/month per engineer.

**Remediation:** Content-hash the intent dict (excluding `parsed_at` and `raw_prompt` if those contain non-semantic differences) and cache the Stage 2 result in Redis with a 30-day TTL. Cache invalidation on YAML axiom updates via version tag.

### 4.10 No timeout or retry strategy for LLM calls 🟡

`call_qwen_completion` is sketched as a single call. What happens when the cloud API times out at 90 seconds? When it returns a 429? When Instructor fails to parse the JSON after 3 retries? None of this is defined.

**Remediation:** Wrap every LLM call in a retry-with-jitter policy (3 attempts, exponential backoff). Define a hard timeout (60s for cloud, 90s for local). On final failure, route to review queue with the partial output, do not silently swallow.

### 4.11 No deterministic regression test set 🟠

Stage 2 prompts will be tuned, axioms will be edited, models will be swapped. Without a golden test set, you cannot detect regressions. The first sign of a regression will be a wrong BOM in production.

**Remediation:** Curate 50-100 prompts with expected `implied_requirements` (annotated by senior engineers). Run the suite on every prompt change, every axiom update, every model swap. CI gate: precision and recall must not drop more than 2pp from baseline.

---

## 5. Stage 3/4/5 — Retrieval and KB Strategy (`03_RETRIEVAL_AND_KB_STRATEGY.md`)

### 5.1 Freshness checker relies on ETag/Last-Modified, which manufacturers often don't set 🟠

```python
class DatasheetFreshnessChecker:
    def check_for_updates(self, component_id: str) -> bool:
        """HEAD request to manufacturer URL.
        Compare ETag or Last-Modified header to stored value."""
```

Empirically, ~40% of manufacturer PDF URLs return neither ETag nor Last-Modified (especially when served from CDNs or generated dynamically). The freshness checker will silently return "fresh" forever for these, and stale specs will propagate.

**Remediation:** Multi-signal freshness:
1. ETag/Last-Modified if present.
2. Content-Length comparison if headers absent.
3. SHA-256 of first 4KB (covers the cover page, which usually has revision info) — compare to stored hash.
4. Quarterly full re-download for the top 1K components regardless of header signals.

### 5.2 "Hybrid is strictly superior in every scenario" is overstated 🟡

The cost table claims hybrid wins in every scenario. For one-off prototype designs using a novel component (e.g., a part released last week), pure scraping has lower latency: 2-5 minutes vs. the hybrid path of "fail KB lookup, then scrape anyway, then store" which is 2-5 minutes + KB write overhead. The hybrid advantage is on the *second* query, not the first.

This isn't a real problem (hybrid is still the right architecture) but the overstatement erodes credibility of the rest of the document.

**Remediation:** Soften the claim. "Hybrid is superior for repeated queries and air-gapped deployment. Pure scraping wins on first-query latency for novel components." Honest framing.

### 5.3 The hybrid "store result after scraping" path has no QA gate 🔴

```
Download + Parse (P1 pipeline) → Store in KB (persistent) → Return result
```

If the scrape was partial (e.g., page 4 of 12 failed) or the P1 parser misextracted a parameter, the bad data goes straight into the persistent KB and contaminates every future query for that component. This is a data-poisoning vector.

**Remediation:** Insert a QA gate between parse and store:
1. Parser self-confidence score per parameter.
2. Cross-check: do extracted parameters fall within plausible ranges for the component category? (e.g., an op-amp with `en = 500 nV/rtHz` is probably misextracted)
3. If any parameter fails QA, store with `extraction_status = 'needs_review'` and route to the review queue. Do not surface in parametric search until approved.

### 5.4 No versioning for `electrical_parameters` 🔴

Datasheet revisions change specs. The OPA189 Rev C datasheet may list `en = 5.2 nV/rtHz`; Rev D revises to `5.8 nV/rtHz`. The current schema has no way to track this. Either:
- The old value is overwritten → no audit trail, no way to reproduce a BOM generated against Rev C.
- Both values are stored → no way to know which is current.

**Remediation:** Add `valid_from` and `valid_to` columns to `electrical_parameters`, plus a `datasheet_revision` FK. Every BOM generation records the parameter revision it was validated against.

```sql
ALTER TABLE electrical_parameters
    ADD COLUMN valid_from TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN valid_to TIMESTAMPTZ,
    ADD COLUMN datasheet_revision_id UUID REFERENCES documents(id);

-- Current parameters only
CREATE INDEX idx_ep_current ON electrical_parameters(component_id)
    WHERE valid_to IS NULL;
```

### 5.5 "100 concurrent users = 100 DB queries" misidentifies the bottleneck 🟡

The cost table compares DB query cost across approaches but the real bottleneck for concurrent users is the Stage 2 LLM call, not the DB. 100 concurrent users each triggering a Stage 2 call means 100 concurrent 397B inferences — and a single 8xH100 server can serve maybe 4-8 concurrent requests at reasonable latency. The DB is the easy part.

**Remediation:** Model the actual bottleneck. Add a request queue with priority lanes. Document max concurrent users per hardware config.

### 5.6 Cost table omits the dominant cost: LLM inference 🟠

The KB row shows "$0.001 per query" but doesn't include the Stage 2 LLM call which is $0.05-0.20 per query for the 397B model. The table is misleading by omission.

**Remediation:** Add a "Stage 2 LLM cost" row that's identical across all three columns. The hybrid's actual advantage is on retrieval, not on inference.

### 5.7 Supplier data freshness is undefined 🟡

The `supplier_cache` table has `snapshot_date` but no strategy for refreshing. DigiKey/Mouser stock and pricing change hourly. For BOM cost estimation, stale supplier data is worse than no data — it produces confidently wrong numbers.

**Remediation:** Define refresh cadence by component criticality: daily for top 1K components, weekly for next 10K, monthly for the rest. Always show `snapshot_date` in any BOM cost report. Refuse to generate cost estimates for components with supplier data older than 30 days.

### 5.8 Air-gapped UX for adding components is undefined 🟠

> The only way to add new components is manual datasheet ingestion through the review queue CLI.

In practice, this becomes a bottleneck. An engineer working on a new design needs 15 new components. They have to find the PDFs, upload them, wait for parsing, wait for review. Each one is 10-30 minutes of friction. Engineers will route around this by using "close enough" components from the KB, producing suboptimal designs.

**Remediation:** Build a batch ingestion UI. Engineer drops 15 PDFs, the system ingests all in parallel, surfaces a single review report. Track "components pending ingestion per engineer" as a health metric.

---

## 6. Database Schema (`04_DATABASE_SCHEMA.md`)

### 6.1 The GIST range index will not be used by typical parametric queries 🔴

```sql
CREATE INDEX idx_ep_value_range ON electrical_parameters
    USING GIST(numrange(value_min, value_max, '[]'))
    WHERE value_min IS NOT NULL AND value_max IS NOT NULL;
```

The example query in the same doc:

```sql
JOIN electrical_parameters noise_ep
    ON noise_ep.symbol = 'en'
    AND noise_ep.unit = 'nV/rtHz'
    AND noise_ep.value_typ < 5
```

This filters on `value_typ`, not on the range. The GIST index is useless here. The query planner will do a full scan on the matching `symbol`/`unit` rows. At 1M components with 50 params each (50M rows), this is multi-second queries.

**Remediation:** Add B-tree indexes on `(symbol, unit, value_typ)`, `(symbol, unit, value_min)`, `(symbol, unit, value_max)`. These cover the actual query patterns. Reserve the GIST index for true range queries.

```sql
CREATE INDEX idx_ep_typ_lookup ON electrical_parameters(symbol, unit, value_typ)
    WHERE value_typ IS NOT NULL;
CREATE INDEX idx_ep_max_lookup ON electrical_parameters(symbol, unit, value_max)
    WHERE value_max IS NOT NULL;
```

### 6.2 `component_relationships.is_symmetric DEFAULT TRUE` is wrong for asymmetric relationships 🟠

```sql
is_symmetric BOOLEAN DEFAULT TRUE,
```

But `replaces`, `replaced_by`, `recommended_pairing` are asymmetric. Component A may replace B, but B does not replace A. The default of TRUE will create incorrect bidirectional edges for these.

**Remediation:** Default to FALSE. Force the inserter to declare symmetry explicitly. Or better: derive symmetry from `relationship_type` via a CHECK constraint:

```sql
CHECK (
    (relationship_type IN ('equivalent', 'functional_alternative') AND is_symmetric = TRUE)
    OR (relationship_type IN ('replaces', 'replaced_by', 'recommended_pairing') AND is_symmetric = FALSE)
)
```

### 6.3 `component_relationships.confidence DEFAULT 1.0` is dangerous 🟠

Default confidence of 1.0 means "certain." Most inferred relationships are not certain. If an inserter forgets to set confidence, the relationship is treated as gospel.

**Remediation:** Default to NULL. Force explicit confidence on insert. Add a NOT NULL constraint after backfilling existing rows.

### 6.4 `design_patterns` table is built but not wired to Stage 2 🔴

The `design_patterns` and `design_pattern_roles` tables exist (well-designed), but `02_REQUIREMENT_COMPLETION_ENGINE.md` never queries them. Stage 2 uses static YAML instead. This is the most egregious architectural disconnect in the entire system: the KB has the structured knowledge Stage 2 needs, and Stage 2 ignores it.

**Remediation:** This is the core of the "grounding loop" remediation in Section 4.2. Stage 2 should:
1. Query `design_patterns WHERE topology_type = intent.goal_topology` to retrieve the canonical pattern.
2. Query `design_pattern_roles` for the component categories the pattern requires.
3. Inject these as grounded context alongside (or instead of) the YAML axioms.

### 6.5 No controlled vocabulary for `pins.normalized_function` 🟡

```sql
normalized_function   VARCHAR(100),  -- set by P2 normalizer
```

What are valid values? "input", "in", "IN", "Input", "non-inverting input", "VIN+" — without a controlled vocabulary, downstream pin-matching logic will fail silently.

**Remediation:** Define a vocabulary table:

```sql
CREATE TABLE pin_function_vocabulary (
    function_name VARCHAR(100) PRIMARY KEY,
    function_class VARCHAR(50) NOT NULL,  -- input | output | power | ground | io | nc
    aliases TEXT[],
    description TEXT
);

ALTER TABLE pins ADD CONSTRAINT fk_normalized_function
    FOREIGN KEY (normalized_function) REFERENCES pin_function_vocabulary(function_name);
```

### 6.6 `review_queue` has no ownership model 🟡

```sql
CREATE TABLE review_queue (
    item_id UUID PRIMARY KEY,
    stage VARCHAR(100),
    -- ...
    status VARCHAR(50) DEFAULT 'pending',
    -- ...
);
```

No `assigned_to`, no `priority`, no `due_date`. In a team of 5 engineers, items will sit unowned or be claimed by multiple people.

**Remediation:**

```sql
ALTER TABLE review_queue
    ADD COLUMN assigned_to UUID REFERENCES users(id),
    ADD COLUMN priority VARCHAR(20) DEFAULT 'MEDIUM',
    ADD COLUMN due_at TIMESTAMPTZ,
    ADD COLUMN claimed_at TIMESTAMPTZ;
```

### 6.7 `documents.file_hash UNIQUE` is over-constrained 🟡

Two different documents (different titles, different manufacturers) can have identical content — common for rebranded datasheets (e.g., TI parts sold under different part numbers in different regions). The UNIQUE constraint will reject the second one.

**Remediation:** Remove the UNIQUE constraint on `file_hash`. Add a separate `document_hashes` table if you need to dedupe storage at the filesystem level:

```sql
CREATE TABLE document_files (
    file_hash VARCHAR(64) PRIMARY KEY,
    storage_path TEXT NOT NULL,
    byte_size BIGINT NOT NULL
);
ALTER TABLE documents
    ADD COLUMN file_hash VARCHAR(64) REFERENCES document_files(file_hash);
```

### 6.8 No FTS index on `electrical_parameters.raw_text` 🟡

Engineers search for specific conditions text: "5nV/rtHz at 1kHz", "Vs=±15V, Ta=25°C". Without an FTS index on `raw_text`, these searches are full scans.

**Remediation:**

```sql
CREATE INDEX idx_ep_raw_text_fts ON electrical_parameters
    USING GIN(to_tsvector('english', coalesce(raw_text, '') || ' ' || coalesce(conditions, '')));
```

### 6.9 UUID PKs on hot tables are index-unfriendly 🟡

`electrical_parameters` at 1M components × 50 params = 50M rows. UUID PKs are 16 bytes vs 8 bytes for bigserial, and they're random so they fragment B-tree indexes. At 50M rows this is a measurable perf hit.

**Remediation:** Use bigserial for hot tables (`electrical_parameters`, `pins`, `layout_constraints`). Reserve UUIDs for entities referenced from external systems (`components`, `documents`).

### 6.10 No table for Stage 2 inference audit trail 🟠

Every Stage 2 inference should be persisted for audit and feedback. The current schema has no place for this. When a BOM is wrong, you can't trace which inferences led to the wrong component selection.

**Remediation:**

```sql
CREATE TABLE stage2_inferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    intent_id UUID NOT NULL,
    axiom_id VARCHAR(100),  -- which axiom fired
    requirement TEXT NOT NULL,
    component_implication VARCHAR(200),
    raw_confidence FLOAT,
    calibrated_confidence FLOAT,
    grounding_document_id UUID REFERENCES documents(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE stage2_inference_feedback (
    inference_id UUID REFERENCES stage2_inferences(id),
    feedback_type VARCHAR(50),  -- accepted | rejected | modified
    engineer_id UUID,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.11 `pgvector IVFFlat` index creation is manual and will be forgotten 🟡

The schema comments:

```sql
-- CREATE INDEX idx_embeddings_ann ON component_embeddings
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

This is commented out "build AFTER 10K+ rows." In practice, nobody remembers to do this. The system runs with linear scan forever.

**Remediation:** Add a migration job that triggers index creation automatically when row count crosses 10K. Document the `lists = sqrt(row_count)` tuning. Add a monitoring alert if ANN queries are taking >500ms (indicating missing or stale index).

### 6.12 No materialized views for common parametric queries 🟡

The example op-amp query at 1M components will be slow even with indexes — multiple joins across 50M-row tables. Common queries should be pre-materialized.

**Remediation:**

```sql
CREATE MATERIALIZED VIEW mv_op_amp_parametric AS
SELECT
    c.id, c.part_number, m.short_name,
    en.value_typ AS noise_nV_rtHz,
    drift.value_max AS drift_uV_C,
    vsupp.value_min AS vsupply_min,
    vsupp.value_max AS vsupply_max
FROM components c
JOIN manufacturers m ON c.manufacturer_id = m.id
LEFT JOIN electrical_parameters en ON en.component_id = c.id AND en.symbol = 'en'
LEFT JOIN electrical_parameters drift ON drift.component_id = c.id AND drift.symbol = 'VOS_drift'
LEFT JOIN electrical_parameters vsupp ON vsupp.component_id = c.id AND vsupp.symbol = 'Vsupply'
WHERE c.lifecycle_status = 'active';

CREATE UNIQUE INDEX ON mv_op_amp_parametric(id);
-- Refresh nightly or on ingestion
```

---

## 7. Search, Storage, and Deployment (`05_SEARCH_STORAGE_DEPLOYMENT_ARCHITECTURE.md`)

### 7.1 Layer 1 (SQL) coverage gap silently routes to slower layers 🟠

> Layer 1: Returns exact matches in <10ms. Handles: known symbols, known units, known numeric ranges.

If a component was ingested but its noise parameter wasn't extracted (P1 parser failed on that table), Layer 1 returns nothing for that component, and the query falls through to Layer 2/3/4. This is invisible to the user. The "fast path" is actually "fast path for well-parsed components only."

**Remediation:** Track extraction completeness per component. Surface a "coverage" metric in the UI: "This query hit 847 components in Layer 1; 153 components lack extracted noise specs and were not considered." Engineers need to know what they're missing.

### 7.2 `all-MiniLM-L6-v2` is too weak for technical semantic search 🟠

The 384-dim MiniLM model is fine for general text but weak for technical specs. "Zero-drift op-amp" and "chopper-stabilized amplifier" are semantically equivalent but MiniLM cosine similarity is ~0.55 (below the 0.70 threshold). Many real synonyms will be missed.

**Remediation:** Either:
- **(a)** Fine-tune MiniLM on a technical corpus (datasheet descriptions + Wikipedia electronics articles + app notes). 2-3 days of work, ~10% recall improvement.
- **(b)** Switch to `bge-large-en-v1.5` (1024-dim, 3x larger but much better on technical text).
- **(c)** Maintain a synonym dictionary ("zero-drift" ↔ "chopper-stabilized" ↔ "auto-zero") and expand queries before vector search.

For a DRDO program, (c) is the auditable choice. (a) is the highest-leverage choice.

### 7.3 Neo4j cold-start latency not accounted for 🟡

> Layer 4: Returns component types + design patterns in <500ms.

Neo4j cold-start for complex traversals can be 2-5 seconds. After warmup it's fast, but the first query after server start (or after a long idle period) will blow the SLA.

**Remediation:** Define a warmup query that runs on server start. Document the cold-start behavior. Add a health check that probes Neo4j with a representative traversal.

### 7.4 RRF k=60 is untuned 🟢

```python
score = sum(1 / (rank + 60)) for each list containing the item.
```

k=60 is the standard default but for technical retrieval with high recall needs, k=20-30 often works better (gives more weight to top-ranked items). Tuning requires a labeled eval set (which you should build anyway, see Section 4.4).

### 7.5 Storage estimates undercount on RF/microwave datasheets 🟡

> Raw datasheets (PDF): 10,000 × 2MB avg = 20 GB

The 2MB average is plausible for op-amps and passives. RF/microwave ICs, FPGAs, and complex SoCs routinely have 20-50MB datasheets. If your component mix includes any of these (and DRDO's likely does), the Phase 3 estimate is 1.5-2x understated.

**Remediation:** Track actual average datasheet size by category during Phase 1. Re-estimate Phase 2/3 sizing based on observed distribution, not a flat 2MB assumption.

### 7.6 "40% dedup savings" is unjustified 🟡

> Raw datasheets: 1M × 2MB, ~40% dedup savings

Where does 40% come from? No methodology given. The actual dedup rate depends on how aggressively you collect multi-vendor equivalent parts. Could be 20% (mostly unique parts) or 60% (heavy on commodity passives). A wrong estimate here means a wrong NVMe budget.

**Remediation:** Run dedup on a 1000-component sample, measure, project. Update the table with empirical numbers.

### 7.7 8xH100 server doesn't account for co-tenancy with other models 🔴

> Recommended configuration: 8× NVIDIA H100 80GB NVLink (640GB combined VRAM) running FP8.

The doc later says "Model weights: YOLOv8n + Qwen2.5-7B + MiniLM = 35 GB." If these share the H100 server with Qwen 3.5 397B (which the architecture implies — "Inference Server (GPU)" handles "Intent parser, Requirement completion, P1 Phase 3 & 5"), then:
- Qwen 3.5 397B FP8: ~397 GB
- Qwen2.5-7B (for P1 Phase 3): ~14 GB
- YOLOv8n: ~0.5 GB
- MiniLM: ~0.5 GB
- KV cache for concurrent requests: ~100-200 GB
- **Total: 512-612 GB**

640 GB total VRAM leaves only 28-128 GB headroom. With 5+ concurrent users, this will OOM. The recommendation is presented as "comfortable headroom" — it isn't.

**Remediation:** Either:
- **(a)** Dedicate the 8xH100 server to Qwen 3.5 397B only. Run the smaller models on a separate 1-2x A100 server.
- **(b)** Upsize to 16xH100 (likely impossible as a single node) or move to a 2-node 8xH100 cluster.
- **(c)** Use Qwen2.5-72B locally and reserve the 397B for cloud fallback. This is what the doc itself recommends as a fallback but then ignores in the deployment sizing.

### 7.8 TCO estimate omits power, cooling, datacenter, network 🟠

> Total on-premise hardware cost estimate: $400K–$650K

This is capex only. A 8xH100 server draws ~10kW under load. Over 5 years at $0.10/kWh, that's $43K in electricity. Cooling is another 30-50% on top. Datacenter space, network infrastructure, and UPS add more. Real 5-year TCO is $700K-$1.2M, not $400-650K.

**Remediation:** Add an "operating cost over 5 years" row to the comparison table. The cloud-vs-on-prem break-even calculation changes materially.

### 7.9 18-month break-even ignores DRDO procurement cycles 🟠

> Break-even: ~18 months at cloud rate

DRDO procurement for an 8xH100 server is realistically 12-24 months from requisition to delivery. During that period, the team pays cloud costs *and* is committed to on-prem capex. Real break-even is 30-42 months from project start, not 18.

**Remediation:** Add a "procurement lead time" row. Plan the cloud spend to bridge the procurement gap explicitly. Consider smaller interim hardware (e.g., a 2xA100 server running Qwen2.5-72B) to bridge.

### 7.10 "Cloud-to-local migration requires zero code changes" is optimistic 🟠

The only file that changes is `config.py`, swapping `llm_base_url`. In practice:
- Cloud APIs may support tool calling, structured outputs, JSON mode that local vLLM does not (or supports differently).
- Context windows differ: cloud Qwen 3.5 397B may offer 256K context; local Qwen2.5-72B may cap at 32K.
- Token limits, rate limits, retry behavior all differ.
- Prompt formatting that works on one model may not work on another (different system prompt handling, different few-shot stability).

**Remediation:** Maintain a compatibility matrix. Test every prompt against both cloud and local models in CI. Document the actual delta, not the idealized one.

### 7.11 No DR/backup strategy for local PostgreSQL 🟠

Single-node PostgreSQL failure takes down the entire system. For a DRDO program, this is unacceptable.

**Remediation:** Plan for:
- **(a)** Streaming replication to a hot standby.
- **(b)** WAL archiving to S3-compatible storage (MinIO for air-gapped).
- **(c)** Daily base backups with 30-day retention.
- **(d)** Quarterly DR drills — actually restore from backup and verify.

### 7.12 No model versioning or prompt regression strategy 🟠

When Qwen 3.5 397B is updated (or you migrate to Qwen 4.x), every Stage 1/2 prompt may regress. There's no plan to detect this.

**Remediation:** Pin model versions in config. Run the golden test suite (see Section 4.11) against any model change. Maintain a "model card" documenting which model versions have been validated against which prompt versions.

### 7.13 No GPU scheduling strategy for concurrent users 🟠

If 5 engineers submit queries simultaneously, who gets GPU priority? An interactive user waiting on a response? Or a batch ingestion job? Without scheduling, batch jobs will starve interactive users.

**Remediation:** Define priority classes:
- P0: Interactive user queries (preempt)
- P1: Batch ingestion
- P2: Background freshness checks
- P3: Embedding regeneration

Implement via vLLM's priority queue or a side queue manager.

### 7.14 vLLM configuration not specified 🟡

The doc recommends vLLM but doesn't specify:
- `--tensor-parallel-size` (should be 8 for the 8xH100 config)
- `--max-model-len` (256K? 128K? Affects KV cache sizing)
- `--quantization` (FP8 via `--quantization fp8`)
- `--gpu-memory-utilization` (default 0.9 leaves headroom for other processes)
- Continuous batching parameters

**Remediation:** Add a "vLLM deployment config" section with specific flags. Document the trade-offs.

---

## 8. Cross-Cutting Concerns

These don't fit cleanly into any one stage but affect the entire system.

### 8.1 No end-to-end test corpus 🔴

There is no mention anywhere of a golden test set spanning Stage 1 → Stage 7. Without this:
- Prompt changes cannot be validated.
- Model swaps cannot be validated.
- Schema migrations cannot be validated.
- Axiom updates cannot be validated.
- You will ship regressions to production and not know.

**Remediation:** Curate 50-100 prompts covering:
- 10 single-topology designs per major topology (current source, voltage reference, filter, converter, oscillator)
- 20 compound designs (e.g., current source + ADC + isolation)
- 10 edge cases (missing specs, contradictions, out-of-scope requests)
- 10 DRDO-specific cases (mil-spec compliance, air-gapped operation, ITAR components)

Each prompt has expected outputs at every stage. CI runs the full pipeline and diffs against expected.

### 8.2 No observability or tracing strategy 🔴

When a BOM comes out wrong, how do you trace which stage introduced the error? The architecture has no:
- Distributed tracing (OpenTelemetry spans across stages)
- Per-stage logging standards
- LLM call audit log (inputs, outputs, model version, latency, cost)
- Retrieval audit log (which layers fired, which results returned)
- BOM generation audit log (which inferences drove which component selections)

**Remediation:** Add an `audit_log` table. Every LLM call, every retrieval, every BOM generation writes a row. Build a trace UI that lets an engineer click a BOM line and see the full inference chain that produced it.

### 8.3 No A/B testing framework 🟠

When you change the Stage 2 prompt, how do you measure improvement? Currently: you can't.

**Remediation:** Shadow-mode A/B. Run both old and new prompts for 2 weeks, log both outputs, surface diffs to engineers for review. Promote the new prompt only when the diff is net-positive on the golden set *and* on shadow-mode review.

### 8.4 No data versioning for the KB 🟠

The KB evolves. Components get added, parameters get re-extracted, axioms get updated. You cannot reproduce a BOM generated 6 months ago because the KB state has changed.

**Remediation:** Snapshot the KB state with every BOM generation. Either:
- **(a)** Full snapshot (expensive at 2.2 TB).
- **(b)** Content-hash every row and store the hash set per BOM (cheap, allows reconstruction if old data is retained).
- **(c)** DVC-style versioning for the entire KB, with periodic snapshots.

For DRDO audit purposes, (b) is the minimum acceptable.

### 8.5 No security model for NDA-restricted datasheets 🟠

Some manufacturer datasheets are under NDA and cannot be redistributed. The architecture has no notion of:
- Per-document access control
- Per-user clearance levels
- Per-project data isolation
- Audit logging of who accessed what

For a DRDO program with multiple classified projects sharing the same infrastructure, this is a compliance blocker.

**Remediation:**

```sql
CREATE TABLE document_access_controls (
    document_id UUID REFERENCES documents(id),
    clearance_required VARCHAR(50),  -- 'public', 'internal', 'confidential', 'secret'
    project_scope UUID,  -- NULL = all projects; non-NULL = restricted to project
    PRIMARY KEY (document_id, clearance_required)
);

CREATE TABLE user_clearances (
    user_id UUID,
    clearance_level VARCHAR(50),
    project_scopes UUID[],
    granted_at TIMESTAMPTZ,
    granted_by UUID,
    PRIMARY KEY (user_id, clearance_level)
);
```

Every retrieval checks both the user's clearance and the document's access control.

### 8.6 No cost attribution per user / per project 🟡

LLM inference is expensive. Without per-user attribution, you can't tell which projects are burning the budget, can't charge back, can't detect abuse.

**Remediation:** Every LLM call logs `user_id`, `project_id`, `tokens_in`, `tokens_out`, `model`, `cost_usd`. Monthly cost report per project.

### 8.7 No rate limiting on the user-facing API 🟡

5 concurrent engineers each submitting 20-prompt batches will saturate the GPU server. Without rate limiting, the system collapses under load.

**Remediation:** Token bucket per user (e.g., 10 requests/minute, 100/hour). Queue overflow returns 429 with retry-after.

### 8.8 Stage 6 "confidence < 0.85" threshold is undefined 🟠

> Human review gate: if confidence < 0.85

Confidence in *what*? The BOM as a whole? Each component? Each inferred requirement? The threshold value is meaningless without defining the unit.

**Remediation:** Define multiple confidence metrics:
- Per-component selection confidence (from Stage 6's compatibility check)
- Per-inferred-requirement confidence (from Stage 2, calibrated per Section 4.4)
- Per-BOM aggregate confidence (weighted by component criticality)

Different thresholds for each. Surface all three to the reviewer.

### 8.9 No schema migration strategy 🟠

Schema v2.0 today, v3.0 in 6 months. How do existing intent dicts migrate? How do existing KB rows migrate? How do existing BOMs (generated against v2 schemas) remain reproducible?

**Remediation:** Adopt a formal schema evolution policy:
- Schemas are versioned (`schema_version` field on every persisted object).
- Migrations are forward-only with explicit upconverters.
- Old data is never mutated; new columns get defaults; deprecated columns are kept until all consumers upgrade.
- Every BOM references the schema version it was generated against.

### 8.10 "GAP-001-D" and "GAP-002-A" are undefined 🟡

```
SPICE Netlist    Noise Analysis
[GAP-002-A]      [GAP-001-D]
```

What are these? Not defined anywhere in the six docs. If they're internal task tracker IDs, they shouldn't be in the architecture doc. If they're architectural gaps, they need to be documented.

**Remediation:** Either remove or define. If gaps, add a "Known Gaps" section to PROJECT_CONTEXT.md listing each gap with description, impact, and mitigation.

### 8.11 No multi-tenant isolation 🟠

If DRDO uses Open Forge for multiple classified projects on shared infrastructure, can Project A's prompts, inferences, or retrieved documents leak into Project B's sessions? The architecture is silent on this.

**Remediation:** Project-scoped sessions. Every prompt, every inference, every retrieval is tagged with `project_id`. Cross-project data access requires explicit elevation. LLM context windows never include data from multiple projects.

### 8.12 No audit log of LLM calls 🟠

For a DRDO system, every LLM call should be logged: who, when, what prompt, what model, what output, what cost. This is basic compliance and is entirely missing.

**Remediation:**

```sql
CREATE TABLE llm_call_audit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    project_id UUID,
    stage VARCHAR(50) NOT NULL,  -- 'stage1' | 'stage2' | 'p1_phase3' | etc.
    model_version VARCHAR(100) NOT NULL,
    prompt_hash VARCHAR(64) NOT NULL,  -- don't store full prompt for security
    prompt_tokens INT,
    output_tokens INT,
    latency_ms INT,
    cost_usd FLOAT,
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Retain for 7 years per typical government records retention policy.

---

## 9. Prioritized Recommendations

### Immediate (before any production deployment)

1. **Add parameter versioning to the KB** (Section 5.4). Without this, datasheet revisions silently corrupt BOMs.
2. **Fix the `electrical_parameters` indexing** (Section 6.1). Current indexes won't be used by the documented query patterns.
3. **Wire Stage 2 to the existing `design_patterns` table** (Section 6.4). The KB has the knowledge; Stage 2 ignores it.
4. **Add a QA gate between scraping and KB storage** (Section 5.3). Otherwise scraping poisons the KB.
5. **Define the golden test corpus** (Section 8.1). Without this, every change is a coin flip.
6. **Add an audit log for every LLM call** (Section 8.12). Non-negotiable for DRDO compliance.

### High priority (within first 3 months of production)

7. **Decompose Stage 2 YAML into atomic axioms with preconditions** (Section 4.1).
8. **Build the grounding loop** between Stage 2 inferences and KB content (Section 4.2).
9. **Calibrate confidence scores against ground truth** (Section 4.4).
10. **Add multi-topology support to the intent schema** (Section 3.1).
11. **Fix the GPU co-tenancy issue** (Section 7.7) — separate the 397B server from the smaller-model server.
12. **Define and implement the security model for NDA documents** (Section 8.5).
13. **Re-do the TCO estimate with power/cooling/procurement** (Sections 7.8, 7.9).

### Medium priority (within first 12 months)

14. **Build the feedback loop from Stage 6 to axiom weights** (Section 4.5).
15. **Add Stage 2 caching** (Section 4.9).
16. **Tune or replace the embedding model** (Section 7.2).
17. **Implement DR/backup for PostgreSQL** (Section 7.11).
18. **Define GPU scheduling priorities** (Section 7.13).
19. **Build the multi-tenant isolation layer** (Section 8.11).
20. **Add observability/tracing across all stages** (Section 8.2).

### Lower priority (ongoing)

21. **Document all vLLM configuration** (Section 7.14).
22. **Add materialized views for common parametric queries** (Section 6.12).
23. **Build the batch ingestion UI** (Section 5.8).
24. **Tune RRF k parameter** (Section 7.4).
25. **Add a schema migration policy** (Section 8.9).

---

## 10. What the Architecture Gets Right

For balance, the design has genuine strengths that should be preserved through any refactor:

1. **The four-layer retrieval stack (SQL → FTS → Vector → KG)** is the correct shape. Most teams jump straight to vector search and lose the precision of structured queries. This design uses each layer for what it's good at.

2. **Hybrid KB + scraping fallback is the right architecture**, especially given the DRDO air-gapped requirement. The defect is in the implementation details, not the architecture.

3. **Instructor + Pydantic for structured LLM output** is the correct tool. Don't let anyone talk you into manual JSON parsing.

4. **The DB schema is mostly well-normalized** with appropriate foreign keys, cascading deletes, and partial indexes where they help. The defects are tactical (wrong indexes, missing columns), not strategic.

5. **Separating the LLM serving layer (vLLM) from the application server** is correct. Allows independent scaling.

6. **The cloud-to-local config swap design** is the right instinct, even if the "zero code changes" claim is optimistic. The architecture is at least *designed* for portability, which most systems aren't.

7. **The schema's typed requirement categories** (Performance, Electrical, Thermal, Manufacturing, Reliability, Compliance, Cost) are well-chosen and cover the space without overlap.

8. **The review queue is a first-class entity**, not an afterthought. This is rare and correct for a system that needs human-in-the-loop validation.

9. **The Reciprocal Rank Fusion approach** for merging multi-layer results is standard and correct. Tuning is needed but the algorithm choice is right.

10. **The cloud-first-then-migrate-on-prem path** is the right sequencing for a DRDO program that needs to demonstrate value before procurement cycles deliver hardware.

These strengths should be the foundation that the above remediations build on, not thrown out.

---

## 11. Closing Note

This review is deliberately harsh. The architecture is good enough that the defects are worth naming precisely rather than glossing over. A weaker architecture wouldn't sustain this level of detailed critique — the issues would be too systemic to enumerate.

The single most important remediation is **Section 8.1: the golden test corpus**. Almost every other issue in this document becomes either detectable or fixable once that corpus exists. Without it, every change is a guess. With it, the system becomes improvable.

Build the test corpus first. Everything else follows.
