# Open Forge — Schema Update Engine: Design Exploration

**Scope:** Exploration of a proposed LLM- and web-scraping-driven schema update engine that suggests schema changes (adding to existing fields, creating new fields for new classifications) upon human review.

**Status:** Design proposal, not yet implemented.

**Tone:** Same harshness as prior reviews. The idea is interesting; the naive implementation will cause real damage. This document proposes the safer path.

---

## 1. The Problem Being Solved

The `ImprovedIntentDict v2` schema (`01_INTENT_PARSING_SCHEMA.md`) was designed top-down by engineers who anticipated specific requirement categories: `PerformanceRequirements`, `ElectricalConstraints`, `ThermalConstraints`, `ManufacturingConstraints`, `ReliabilityRequirements`, `ComplianceRequirements`, `CostConstraints`, plus `ComponentPreference`, `ImpliedRequirement`, `DesignRequest`.

This is a sound v1 design. It will not survive contact with real DRDO prompts for more than ~6 months, for four concrete reasons:

### 1.1 Real prompts contain requirements the schema cannot represent

Examples the team will encounter within the first 100 real prompts:

- **"Must be field-upgradable without re-flashing the bootloader."** → No `FirmwareConstraints` category exists.
- **"Board must fit in a 19-inch rack chassis with 1U height."** → `ManufacturingConstraints.board_dimensions_mm` is a 2-tuple; mechanical form factor constraints (rack units, DIN rail mounting) have no field.
- **"Design must support over-the-air firmware updates for the next 10 years."** → No `LifecycleConstraints` category; `ReliabilityRequirements.mtbf_hours` doesn't capture this.
- **"Components must be sourced from Indian suppliers per Atmanirbhar Bharat policy."** → `CostConstraints.preferred_suppliers` is a string list; no notion of country-of-origin preference.
- **"Board must tolerate 100krad total ionizing dose for satellite deployment."** → `ReliabilityRequirements.radiation_tolerance` exists as a string but has no units, no standard taxonomy (TID vs. SEE vs. DD), no test methodology reference.
- **"Design must support secure boot with hardware root of trust."** → No `SecurityConstraints` category at all.

These requirements will fall into `explicit_constraints: list[str]` — the dumping ground for "couldn't classify this." They will then be invisible to Stage 2 (which keys off typed fields), to Stage 3 retrieval (which queries KB by typed attributes), and to Stage 6 BOM validation (which checks typed constraints). The schema's promise of "structured extraction drives downstream reasoning" silently fails for these requirements.

### 1.2 The schema cannot anticipate DRDO-specific compliance regimes

The current `ComplianceRequirements` field has:

```python
standards: list[str] = Field(default_factory=list)
# e.g. ["MIL-STD-461", "RoHS", "REACH", "CE", "DO-160", "MIL-PRF-38534"]
emc_class: Optional[str] = None
safety_class: Optional[str] = None
export_control: Optional[str] = None
country_of_origin_restriction: Optional[str] = None
```

This list reflects an American / European compliance worldview. It omits:
- **JSS 55555** (Indian military EMC standard)
- **CEA-2018** (Indian electromagnetic compatibility)
- **BIS CRS** (Bureau of Indian Standards compulsory registration)
- **MIL-STD-810H method 514.8** (vibration, specific method reference)
- **DESE (Defence Electronics Standard for EMI)** used in Indian MoD

As DRDO engineers use the system, they will need to express these. The current schema forces them into free-text strings, which means Stage 3 retrieval can't filter by them and Stage 6 validation can't verify them.

### 1.3 New component categories will appear that the schema doesn't model

The schema's `ComponentPreference` field has `component_type: str` — already flexible enough for new categories. But the `electrical_parameters` table in the DB schema is symbol-keyed, and the symbols are populated from datasheet parsing. A new component category (e.g., photonic ICs, memristor arrays, AI inference accelerators) brings new parameter symbols (`optical_gain_dB`, `weight_precision_bits`, `inference_latency_us`) that the parser doesn't know how to extract and the schema doesn't have categories for.

### 1.4 The YAML axiom library in Stage 2 will outgrow the schema

As Stage 2's domain knowledge YAML library expands (per the prior review's recommendation to decompose into atomic axioms), new axioms will reference requirements that don't have typed fields. The axiom will say `implies: ["design must support X"]` but `X` has no Pydantic field to populate. The inference becomes a string again, defeating the purpose of structured inference.

---

## 2. The Proposed Solution — and Why the Naive Version Is Dangerous

The team's proposal: an engine that uses LLM and/or web scraping to suggest schema updates upon human review. When a reviewer sees an unclassifiable requirement, the engine proposes either (a) adding to an existing field (e.g., adding a new compliance standard to the enum) or (b) creating a new field for the appropriate classification.

This is a real problem with a real need. The naive implementation has five specific failure modes that will damage the project if not addressed.

### 2.1 Failure mode: Schema proliferation 🔴

Without strict governance, every engineer adds their own fields for their own use cases. After 12 months you have 200 fields, 60% of which are used by <5 prompts. The schema becomes unmaintainable, the parser prompt grows to 30K tokens, downstream code has `if hasattr(...)` checks everywhere, and the field names diverge (`supply_voltage` vs `vsupply` vs `vin`).

**Mitigation:** Strict field lifecycle. Every new field has a sponsor, a deprecation date if unused, and a quarterly pruning review.

### 2.2 Failure mode: Semantic drift 🔴

Two engineers add `output_compliance_voltage` and `compliance_voltage_range` to represent the same concept. The schema now has two fields for one idea. Stage 3 retrieval has to query both. BOM validation has to check both. Tests have to cover both.

**Mitigation:** Field proposal requires mapping to an ontology. Before a new field is added, the LLM must propose its semantic relationship to existing fields (synonym, hypernym, hyponym, meronym). A field that duplicates an existing field is rejected.

### 2.3 Failure mode: Uncontrolled vocabularies 🔴

A new `radiation_tolerance` field is added. Engineer A populates it with "100krad TID". Engineer B populates it with "100k". Engineer C populates it with "tolerates 10^5 rad". The DB now has three representations of the same value. Parametric search fails. Aggregation fails.

**Mitigation:** Every new field must come with either (a) a controlled vocabulary (enum), (b) a unit + value type (numeric with SI unit), or (c) a canonicalization function. Free-text fields are not allowed in `ImprovedIntentDict`; they belong only in `explicit_constraints` (which is explicitly labeled as unstructured).

### 2.4 Failure mode: Backward incompatibility 🔴

Schema v2.3 adds `FirmwareConstraints`. BOMs generated before this version don't have this field. When re-loaded (e.g., for re-validation), the Pydantic model raises a validation error. Worse: historical BOMs become unreproducible because their `intent_id` references a v2.2 schema that no longer exists.

**Mitigation:** Every schema change has a migration script. Every persisted object carries its `schema_version`. Historical BOMs reference the schema version they were generated against; the system maintains all prior schema versions for replay.

### 2.5 Failure mode: Rubber-stamp review 🟠

Human review of schema change proposals will degrade to "approve all" within 3 months if the review queue is high-volume. Engineers under deadline pressure will not carefully consider "should this field exist." They will click "approve" and move on.

**Mitigation:** Tiered approval gates. Different change types have different approval costs. The cost must scale with impact.

---

## 3. Critical Assessment of the LLM + Web-Scraping Approach

### 3.1 LLM-driven schema proposals: useful but limited

**Where LLM-driven proposals help:**

- **Pattern detection.** When 5 prompts in a week contain "secure boot" or "root of trust" with no schema field, the LLM can surface this as a candidate for a new `SecurityConstraints` category. This is pattern detection, not schema design — and LLMs are good at it.
- **Synonym detection.** When 3 prompts use "input compliance voltage" and 2 use "compliance voltage range" for what appears to be the same concept, the LLM can propose consolidating to one field with a controlled alias list.
- **Field mapping.** For a new DRDO compliance standard (e.g., JSS 55555), the LLM can map it to the existing `ComplianceRequirements.standards` enum and propose the addition.

**Where LLM-driven proposals fail:**

- **Schema design.** The LLM cannot decide whether a new requirement belongs in `ReliabilityRequirements` or a new `EnvironmentalConstraints` category. This requires engineering judgment about long-term schema evolution, which the LLM doesn't have.
- **Field semantics.** The LLM will propose fields like `output_compliance_voltage: Optional[float]` without specifying units, value range, or canonicalization. Engineering judgment is required.
- **Naming.** The LLM will produce inconsistent field names (`compliance_v` vs `v_compliance` vs `output_compliance_voltage`). A human reviewer must enforce naming conventions.

**Recommendation:** LLM is the proposal engine, not the decision-maker. The LLM surfaces candidates; engineers make decisions.

### 3.2 Web-scraping-driven schema proposals: largely a bad idea 🟠

The proposal mentions web scraping as a source of schema update suggestions. Web scraping is appropriate for **populating** a controlled vocabulary (e.g., scraping the JSS 55555 document to extract the list of test methods), but **not for proposing schema changes**.

**Why web scraping fails for schema design:**

- Web content reflects what's documented, not what's engineered. A manufacturer datasheet doesn't tell you whether `inference_latency_us` should be a field on `ComponentPreference` or `PerformanceRequirements`.
- Web content is noisy. Scraping a forum post about "I needed a field for X" produces schema noise, not signal.
- Web content is asynchronous with engineering practice. By the time a requirement is widely documented on the web, the team has already encountered it in prompts.

**Where web scraping does help:**

- **Controlled vocabulary population.** When a new field is added (e.g., `compliance_standards`), the web scraper can populate the vocabulary by scraping official standards body websites (BIS, MIL-STD, JEDEC, etc.).
- **Component category discovery.** Scraping manufacturer catalogs (DigiKey categories, Mouser taxonomy) surfaces new component categories. This is useful for the KG, less useful for the intent schema.
- **Unit canonicalization.** Scraping unit conversion tables (e.g., "1 nV/rtHz = 1e-9 V/sqrt(Hz)") helps the canonicalization functions for new fields.

**Recommendation:** Use web scraping for vocabulary population, not schema design. The LLM is the schema design assistant; web scraping is the vocabulary researcher.

---

## 4. Recommended Architecture: Tiered Approval Schema Evolution

The right architecture has five components, with humans-in-the-loop at every decision point:

```
Real Prompts
     │
     ▼
┌─────────────────────────────────────────────┐
│  1. Pattern Detector (LLM-driven, weekly)    │
│  Surfaces: "5 prompts this week used a term  │
│  that doesn't map to any schema field"       │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  2. Proposal Generator (LLM-driven, on-demand)│
│  Produces: structured schema change proposal │
│  with ontology mapping, vocab, units, tests  │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  3. Tiered Approval Workflow (human)         │
│  Tier 1: Enum addition — any senior eng      │
│  Tier 2: New field — architecture review     │
│  Tier 3: Category restructure — full review  │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  4. Migration Generator (automated)          │
│  Produces: Alembic migration, Pydantic       │
│  update, parser prompt update, test updates  │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  5. Regression Gate (automated)              │
│  Runs golden corpus against new schema.      │
│  Promotion requires zero regressions.        │
└─────────────────────────────────────────────┘
```

Each component is detailed below.

---

## 5. Component 1: Pattern Detector

### 5.1 Purpose

Detect when real prompts contain requirements that the current schema cannot represent. This is the input to the entire schema update pipeline.

### 5.2 Implementation

A weekly cron job analyzes the past week's `ImprovedIntentDict` records:

```python
# src/schema_evolution/pattern_detector.py

class SchemaPatternDetector:
    """
    Weekly job. Identifies prompts where:
    1. explicit_constraints contains items that look like typed requirements
       (contain numbers, units, or known constraint keywords) but don't map
       to any typed field.
    2. ambiguities were flagged with no resolution.
    3. The same phrase appears in explicit_constraints across multiple prompts
       (indicating a recurring unrepresented concept).
    """

    def run_weekly(self) -> list[PatternReport]:
        # 1. Pull all ImprovedIntentDict records from the past 7 days
        records = self.db.query(IntentRecord).filter(
            IntentRecord.parsed_at >= datetime.utcnow() - timedelta(days=7)
        ).all()

        # 2. Extract phrases from explicit_constraints that don't map to typed fields
        unclassified_phrases = []
        for record in records:
            for constraint in record.intent.explicit_constraints:
                if self._looks_like_typed_requirement(constraint):
                    if not self._maps_to_existing_field(constraint, record.intent):
                        unclassified_phrases.append({
                            "phrase": constraint,
                            "intent_id": record.id,
                            "parsed_at": record.parsed_at,
                        })

        # 3. Cluster similar phrases
        clusters = self._cluster_phrases(unclassified_phrases)

        # 4. For each cluster with >=3 members, emit a PatternReport
        reports = []
        for cluster in clusters:
            if len(cluster.members) >= 3:
                reports.append(PatternReport(
                    cluster_id=cluster.id,
                    member_phrases=cluster.members,
                    representative_phrase=cluster.centroid,
                    frequency=len(cluster.members),
                    first_seen=cluster.first_seen,
                    last_seen=cluster.last_seen,
                ))

        # 5. Surface in the architecture review dashboard
        self.dashboard.post_pattern_reports(reports)
        return reports

    def _looks_like_typed_requirement(self, phrase: str) -> bool:
        """
        Heuristic: does this phrase look like a typed requirement
        rather than a free-text note?
        - Contains a number + unit (e.g., "100krad TID")
        - Contains a known constraint keyword ("must", "shall", "required")
        - References a compliance standard pattern (e.g., "MIL-STD-XXX")
        """
        return bool(
            re.search(r'\d+\s*(?:krad|V|mA|µA|ppm|MHz|GHz|°C|mm|inch|U)', phrase)
            or re.search(r'\b(must|shall|required|tolerates?)\b', phrase, re.I)
            or re.search(r'\b(MIL-STD|MIL-PRF|JSS|BIS|JEDEC|IPC)-?\d+\b', phrase)
        )

    def _maps_to_existing_field(self, phrase: str, intent: ImprovedIntentDict) -> bool:
        """
        LLM check: does this phrase already correspond to a populated typed field?
        Returns True if the LLM judges the phrase is already represented.
        """
        # ... LLM call with current schema as context ...
```

### 5.3 Key design decisions

- **Weekly cadence, not real-time.** Schema evolution is not urgent. A weekly review forces consolidation and prevents reactive field additions.
- **Threshold of 3 occurrences.** One-off requirements don't earn schema changes. Three occurrences in a week indicate a real pattern.
- **LLM for "does this map to existing field" check.** This is a semantic judgment, not a string match. The LLM sees the current schema and judges whether the phrase is already represented.
- **Output is a dashboard, not a queue.** Pattern reports are surfaced for triage, not for automatic proposal generation. Engineers decide which patterns to act on.

### 5.4 What this component does NOT do

- Does not propose schema changes. That's Component 2.
- Does not auto-apply changes. That's Component 4.
- Does not run on every prompt. That would be too noisy and too expensive.

---

## 6. Component 2: Proposal Generator

### 6.1 Purpose

Given a pattern report (or a direct engineer request), generate a structured schema change proposal with all the metadata needed for review.

### 6.2 Proposal schema

```python
# src/schema_evolution/proposal.py

class SchemaChangeProposal(BaseModel):
    """A proposed change to the ImprovedIntentDict schema."""

    proposal_id: UUID
    proposed_at: datetime
    proposed_by: UUID  # engineer who triggered the proposal

    # What change is being proposed
    change_type: Literal[
        "add_enum_value",           # add to existing enum (e.g., new compliance standard)
        "add_field",                 # add new field to existing category
        "add_category",              # add new sub-schema (e.g., SecurityConstraints)
        "rename_field",              # rename existing field
        "deprecate_field",           # mark field as deprecated
        "merge_fields",              # combine two fields into one
        "split_field",               # split one field into two
    ]

    # The actual change, as a JSON Patch (RFC 6902)
    schema_patch: list[dict]  # JSON Patch operations

    # Semantic metadata (REQUIRED for review)
    ontology_mapping: OntologyMapping  # see 6.3
    controlled_vocabulary: Optional[VocabularySpec]  # required for enum/string fields
    unit_spec: Optional[UnitSpec]  # required for numeric fields
    canonicalization: Optional[str]  # function name for value normalization

    # Justification
    trigger_patterns: list[PatternReport]  # which patterns triggered this
    trigger_prompts: list[UUID]  # which specific prompts
    rationale: str  # why this change vs. alternatives considered

    # Impact assessment
    downstream_impact: DownstreamImpact  # see 6.4

    # Migration
    migration_script: str  # Alembic migration as Python source
    backward_compatible: bool
    deprecation_path: Optional[str]  # for breaking changes

    # Test coverage
    new_test_cases: list[TestCase]  # tests that must pass
    regression_test_additions: list[TestCase]

class OntologyMapping(BaseModel):
    """
    How this field relates to existing fields. Required for every proposal.
    Prevents semantic drift (Section 2.2).
    """
    related_fields: list[str]  # existing fields this is related to
    relationships: list[Literal[
        "synonym",        # same concept, different name (rejected: merge instead)
        "hypernym",       # this is a generalization of an existing field
        "hyponym",        # this is a specialization of an existing field
        "meronym",        # this is a part of an existing field's concept
        "orthogonal",     # genuinely new concept, no overlap
    ]]
    notes: str  # engineer's reasoning

class VocabularySpec(BaseModel):
    """Controlled vocabulary for enum/string fields."""
    vocabulary_type: Literal["enum", "string_with_pattern", "reference"]
    values: Optional[list[str]]  # for enum
    pattern: Optional[str]  # regex for string_with_pattern
    reference_url: Optional[str]  # for reference (e.g., standards body URL)
    canonicalizer: Optional[str]  # function name that normalizes inputs

class DownstreamImpact(BaseModel):
    """What needs to change in the rest of the system if this proposal is accepted."""
    parser_prompt_update: bool  # Stage 1 system prompt must change
    stage2_axiom_update: bool  # Stage 2 YAML axioms may need new preconditions
    kb_queries_affected: list[str]  # SQL queries that need updating
    bom_validator_update: bool  # Stage 6 validation rules affected
    review_queue_ui_update: bool  # review queue display must change
    engineering_report_template_update: bool  # report must display new field
    estimated_engineering_hours: int  # rough effort estimate
```

### 6.3 LLM-driven proposal generation

```python
class ProposalGenerator:
    """
    Given a PatternReport, generate a SchemaChangeProposal.
    The LLM proposes; the engineer reviews and edits.
    """

    PROPOSAL_PROMPT = """
    You are a senior schema architect for the Open Forge PCB design system.

    A pattern has been detected in real engineering prompts that the current
    ImprovedIntentDict schema cannot represent. Your task is to propose a
    structured schema change.

    PATTERN REPORT:
    {pattern_report}

    CURRENT SCHEMA (Pydantic):
    {current_schema_source}

    ONTOLOGY OF EXISTING FIELDS (with descriptions):
    {field_ontology}

    Generate a SchemaChangeProposal with the following requirements:
    1. Choose the smallest change that addresses the pattern. Prefer
       add_enum_value over add_field; prefer add_field over add_category.
    2. Provide a complete ontology mapping showing how the new field relates
       to existing fields. If the relationship is "synonym", instead propose
       a merge_fields change.
    3. Specify a controlled vocabulary. No free-text fields are allowed in
       ImprovedIntentDict v2.
    4. Specify units and canonicalization for numeric fields.
    5. Generate the Alembic migration script.
    6. Estimate downstream impact honestly.

    The proposal will be reviewed by a senior engineer. Be conservative —
    propose the minimum viable change.
    """

    def generate(
        self,
        pattern: PatternReport,
        sponsor: Engineer,
    ) -> SchemaChangeProposal:
        # LLM call with the above prompt
        raw_proposal = self.llm.call(
            system=self.PROPOSAL_PROMPT.format(
                pattern_report=pattern.to_json(),
                current_schema_source=self._get_current_schema_source(),
                field_ontology=self._get_field_ontology(),
            ),
            response_format=SchemaChangeProposal,
        )

        # Validate the proposal is well-formed
        self._validate_proposal(raw_proposal)

        # Check for duplicates (has this been proposed before?)
        duplicates = self._find_duplicate_proposals(raw_proposal)
        if duplicates:
            raw_proposal.duplicate_of = duplicates[0].id

        # Persist
        self.db.save(raw_proposal)
        return raw_proposal
```

### 6.4 Web scraping for vocabulary population

When the proposal involves a new enum (e.g., adding JSS 55555 to `ComplianceRequirements.standards`), the web scraper is invoked to validate and enrich the vocabulary:

```python
class VocabularyPopulator:
    """
    For proposals that add enum values, scrape authoritative sources
    to validate the value exists and gather metadata.
    """

    def populate_compliance_standard(self, standard_name: str) -> VocabularyEntry:
        # 1. Search the standards body website
        results = self.web_search.search(f"{standard_name} site:bis.gov.in OR site:jelec.org OR site:landandmaritime.dla.mil")

        if not results:
            raise VocabularyNotFoundError(f"Could not find {standard_name} in authoritative sources")

        # 2. Fetch the standards body page
        page = self.web_reader.read(results[0].url)

        # 3. Extract: official name, version, test methods, applicable categories
        metadata = self.llm.extract(
            page.content,
            response_format=StandardMetadata,
        )

        return VocabularyEntry(
            value=standard_name,
            official_name=metadata.official_name,
            current_version=metadata.current_version,
            governing_body=metadata.governing_body,
            source_url=results[0].url,
            source_verified_at=datetime.utcnow(),
        )
```

This is the appropriate use of web scraping: **validating that a proposed enum value refers to a real, verifiable standard**, not designing the schema itself.

---

## 7. Component 3: Tiered Approval Workflow

### 7.1 Why tiered approval

A flat approval workflow (any senior engineer approves any change) produces schema proliferation within 6 months. A single high-friction gate (architecture review board for every change) produces a 4-week delay for trivial additions. The right answer is tiered approval: friction scales with impact.

### 7.2 Tier definitions

| Tier | Change types | Approval required | SLA |
|------|-------------|-------------------|-----|
| **T1** | Add enum value to existing list (e.g., new compliance standard, new component type) | 1 senior engineer + 1 architect | 2 business days |
| **T2** | Add new field to existing category (e.g., `output_compliance_voltage` to `ElectricalConstraints`) | 2 senior engineers + architect sign-off | 1 week |
| **T3** | Add new category (e.g., `SecurityConstraints`) | Architecture review board (3+ people) | 2 weeks |
| **T4** | Rename, merge, split, or deprecate existing field | Architecture review board + DRDO program manager sign-off | 4 weeks |

### 7.3 Approval workflow implementation

```python
class ProposalReviewWorkflow:
    def submit_for_review(self, proposal: SchemaChangeProposal) -> None:
        tier = self._classify_tier(proposal)

        review_item = ReviewItem(
            proposal_id=proposal.proposal_id,
            tier=tier,
            status="awaiting_assignment",
            submitted_at=datetime.utcnow(),
            required_approvers=self._required_approvers(tier),
        )
        self.db.save(review_item)
        self.notify_approvers(review_item)

    def _classify_tier(self, proposal: SchemaChangeProposal) -> Tier:
        if proposal.change_type == "add_enum_value":
            return Tier.T1
        if proposal.change_type in ("add_field", "deprecate_field"):
            return Tier.T2
        if proposal.change_type == "add_category":
            return Tier.T3
        if proposal.change_type in ("rename_field", "merge_fields", "split_field"):
            return Tier.T4
        raise ValueError(f"Unknown change type: {proposal.change_type}")

    def approve(self, proposal_id: UUID, approver: Engineer, decision: Decision) -> None:
        review_item = self.db.get(proposal_id)

        if decision == Decision.REJECT:
            review_item.status = "rejected"
            self.db.save(review_item)
            return

        # Record approval
        review_item.approvals.append(Approval(
            approver=approver.id,
            role=approver.role,
            timestamp=datetime.utcnow(),
            comments=decision.comments,
        ))

        # Check if all required approvals are present
        if self._has_all_approvals(review_item):
            review_item.status = "approved"
            self.db.save(review_item)
            # Trigger migration generation (Component 4)
            self.migration_generator.generate(proposal_id)

    def _has_all_approvals(self, review_item: ReviewItem) -> bool:
        required_roles = self._required_roles(review_item.tier)
        approved_roles = {a.role for a in review_item.approvals}
        return required_roles.issubset(approved_roles)
```

### 7.4 Review dashboard

A dedicated UI (separate from the regular review queue) for schema changes. For each proposal, the reviewer sees:

- The pattern that triggered it (with example prompts)
- The proposed schema diff (Pydantic source before/after)
- The ontology mapping (how it relates to existing fields)
- The controlled vocabulary (with web-scraped validation)
- The downstream impact assessment
- The migration script
- The test cases

The reviewer can:
- Approve as-is
- Approve with modifications (which creates a new proposal version)
- Reject with reasoning
- Defer (request more information)

### 7.5 Anti-rubber-stamping measures

- **Cooling-off period.** A reviewer cannot approve more than 5 proposals in a single day. After 5, the dashboard locks them out until the next day.
- **Justification required.** Approval requires a 1-2 sentence justification, not just a click. The justification is recorded in the audit log.
- **Spot audit.** 10% of approved proposals are randomly selected for retrospective review by the architecture review board. Patterns of careless approval trigger a review of the approver's privileges.
- **Cooling period between proposal and approval.** A proposal cannot be approved within 24 hours of submission. This prevents reactive "fire-fighting" approvals.

---

## 8. Component 4: Migration Generator

### 8.1 Purpose

Once a proposal is approved, generate all the artifacts needed to apply the change safely: Alembic migration, Pydantic schema update, parser prompt update, downstream code updates, test updates.

### 8.2 Artifacts generated

```python
class MigrationArtifacts(BaseModel):
    proposal_id: UUID
    generated_at: datetime

    # Database migration
    alembic_migration: str  # Python source for the migration

    # Schema code
    pydantic_schema_diff: str  # unified diff of src/schema/intent.py

    # Parser prompt
    parser_prompt_diff: str  # unified diff of Stage 1 system prompt

    # Downstream code (if needed)
    stage2_axiom_yaml_diffs: list[str]  # YAML axiom files that need updating
    kb_query_updates: list[str]  # SQL queries that need updating
    bom_validator_diff: Optional[str]  # if Stage 6 needs updating
    review_queue_ui_diff: Optional[str]  # if UI needs updating
    report_template_diff: Optional[str]  # if report needs updating

    # Tests
    new_test_files: list[str]  # new test files to add
    modified_test_files: list[str]  # existing tests to modify

    # Backward compatibility
    backward_compat_shim: Optional[str]  # code that maps old schema to new

    # Documentation
    changelog_entry: str  # for the schema changelog
    migration_guide: str  # for engineers updating their code
```

### 8.3 Backward compatibility strategy

The hardest part of schema evolution is not breaking existing data. Three strategies, used in combination:

**Strategy A: Additive changes only (default)**

New fields are added as `Optional[T] = None`. Old data without the field loads correctly. The parser prompt is updated to populate the new field going forward; old data is not backfilled.

**Strategy B: Deprecation path (for renames/removals)**

```python
class ElectricalConstraints(BaseModel):
    # Deprecated in v2.3 — use output_compliance_voltage_range instead
    output_compliance_voltage: Optional[VoltageSpec] = Field(
        None,
        deprecated=True,
        description="Use output_compliance_voltage_range instead. Removed in v3.0."
    )
    output_compliance_voltage_range: Optional[tuple[float, float]] = None
```

A deprecation warning is emitted every time the deprecated field is accessed. The field is removed in the next major version (v3.0).

**Strategy C: Versioned schema (for major changes)**

Every persisted object carries `schema_version`. The system maintains all prior schema versions in a registry. When loading an old object:

```python
def load_intent_record(record_id: UUID) -> ImprovedIntentDict:
    raw = db.get_raw(record_id)
    schema_version = raw["schema_version"]

    if schema_version == "2.0":
        # Apply migrations 2.0 → 2.1 → 2.2 → 2.3 → current
        return migrate_chain(raw, from_version="2.0", to_version=CURRENT_VERSION)
    elif schema_version == "2.3":
        return ImprovedIntentDict.model_validate(raw)
    else:
        raise UnsupportedSchemaVersionError(schema_version)
```

This is more complex but allows arbitrary schema evolution without breaking historical data.

### 8.4 Migration script execution

```python
class MigrationExecutor:
    def execute(self, artifacts: MigrationArtifacts) -> MigrationResult:
        # 1. Apply Alembic migration (in a transaction)
        with self.db.transaction():
            self.db.run_alembic(artifacts.alembic_migration)

        # 2. Apply Pydantic schema change (in Git)
        self.git.apply_patch(
            file="src/schema/intent.py",
            patch=artifacts.pydantic_schema_diff,
            commit_message=f"schema: {artifacts.proposal_id} - {artifacts.changelog_entry}",
        )

        # 3. Apply parser prompt change
        self.git.apply_patch(
            file="src/stage1/prompts/system_prompt.md",
            patch=artifacts.parser_prompt_diff,
            commit_message=f"parser prompt: {artifacts.proposal_id}",
        )

        # 4. Apply downstream changes
        for diff in artifacts.stage2_axiom_yaml_diffs:
            self.git.apply_patch(...)

        # 5. Add new tests
        for test_file in artifacts.new_test_files:
            self.git.write_file(test_file)

        # 6. Run regression tests (Component 5)
        result = self.regression_gate.run()
        if not result.passed:
            # Rollback everything
            self.git.revert()
            with self.db.transaction():
                self.db.run_alembic_down(artifacts.alembic_migration)
            return MigrationResult(rolled_back=True, reason=result.failures)

        return MigrationResult(success=True)
```

---

## 9. Component 5: Regression Gate

### 9.1 Purpose

Every schema change must pass the golden corpus regression suite before promotion. This is the safety net that catches unintended consequences.

### 9.2 Test suite composition

The regression suite has four layers:

**Layer 1: Schema validation tests**
- Every prompt in the golden corpus parses without error.
- Every field that was previously populated is still populated.
- No field has changed type (a `float` field is still `float`, not `int`).

**Layer 2: Semantic equivalence tests**
- For prompts that previously populated the now-deprecated field, the new field is populated with the equivalent value.
- The BOM generated from the new schema is identical to the BOM generated from the old schema (for prompts where the schema change is irrelevant).

**Layer 3: Downstream integration tests**
- Stage 2 completion engine produces the same implied requirements (or a documented delta) for every golden prompt.
- Stage 3 retrieval returns the same component candidates (or a documented delta).
- Stage 6 BOM validation produces the same verdicts (or a documented delta).

**Layer 4: New capability tests**
- The new field is populated correctly for prompts that triggered the proposal.
- The new field flows through to the engineering report.
- The new field is queryable in the KB.

### 9.3 Failure handling

If any test in Layers 1-3 fails:
- The migration is rolled back.
- The proposal is marked "regression_failed" with the specific failure.
- The proposal author is notified and can revise.

If Layer 4 fails:
- The migration is rolled back.
- The proposal is marked "capability_failed" — the new field doesn't actually work as intended.

If all layers pass:
- The migration is committed.
- The schema version is bumped (e.g., v2.3 → v2.4).
- The changelog is updated.
- A notification is sent to all engineers using the system.

### 9.4 Promotion criteria

```python
class RegressionGate:
    def run(self, artifacts: MigrationArtifacts) -> RegressionResult:
        results = [
            self._run_schema_validation_tests(),
            self._run_semantic_equivalence_tests(),
            self._run_downstream_integration_tests(),
            self._run_new_capability_tests(artifacts),
        ]

        if any(r.failed for r in results[:3]):  # Layers 1-3 must pass
            return RegressionResult(passed=False, failures=...)

        if not results[3].passed:  # Layer 4 must also pass
            return RegressionResult(passed=False, failures=...)

        return RegressionResult(passed=True)
```

---

## 10. Additional Mechanisms to Add

Beyond the core five components, the following mechanisms make the system robust:

### 10.1 Field lifecycle tracking

Every field has a lifecycle: `proposed → added → stable → deprecated → removed`. Track:

```sql
CREATE TABLE schema_field_lifecycle (
    field_path VARCHAR(500) PRIMARY KEY,  -- e.g., "electrical.supply_voltage"
    introduced_in_version VARCHAR(20) NOT NULL,
    introduced_at TIMESTAMPTZ NOT NULL,
    introduced_by UUID NOT NULL,
    current_status VARCHAR(20) NOT NULL,  -- proposed | added | stable | deprecated | removed
    deprecated_in_version VARCHAR(20),
    deprecated_at TIMESTAMPTZ,
    deprecated_by UUID,
    deprecated_reason TEXT,
    removed_in_version VARCHAR(20),
    usage_count_30d INT DEFAULT 0,  -- updated weekly
    usage_count_90d INT DEFAULT 0,
    usage_count_365d INT DEFAULT 0
);

CREATE TABLE schema_field_usage_log (
    field_path VARCHAR(500) NOT NULL,
    intent_id UUID NOT NULL,
    populated_at TIMESTAMPTZ NOT NULL,
    value_hash VARCHAR(64),  -- hash of the value, for distinctness analysis
    PRIMARY KEY (field_path, intent_id)
);
```

Quarterly review: any field with `usage_count_90d < 5` is a candidate for deprecation.

### 10.2 Field deprecation quarterly review

A quarterly job generates a "schema pruning report" listing:
- Fields used <5 times in 90 days
- Fields used by only 1 engineer (single-stakeholder fields)
- Fields that overlap semantically with other fields (synonym candidates)
- Fields where the populated values are 95% identical (over-specified field)

This report is reviewed by the architecture review board, which proposes deprecations.

### 10.3 Ontology registry

A separate registry documents the semantic meaning of every field:

```sql
CREATE TABLE schema_ontology (
    field_path VARCHAR(500) PRIMARY KEY,
    canonical_name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    engineering_meaning TEXT NOT NULL,  -- what does this represent physically?
    unit_spec JSONB,  -- {"unit": "V", "range": [0, 1000], "canonicalizer": "voltage_canonicalize"}
    related_fields JSONB,  -- [{field: "electrical.vsupply", relationship: "synonym"}]
    external_reference TEXT,  -- URL to standards body or documentation
    last_reviewed_at TIMESTAMPTZ,
    last_reviewed_by UUID
);
```

Every new field requires an ontology entry. Every deprecation review includes checking the ontology for orphaned relationships.

### 10.4 Schema archaeology — audit trail

Every schema change is permanently recorded:

```sql
CREATE TABLE schema_change_audit (
    audit_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    schema_patch JSONB NOT NULL,
    approved_by UUID[] NOT NULL,  -- all approvers
    approved_at TIMESTAMPTZ NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    schema_version_before VARCHAR(20),
    schema_version_after VARCHAR(20),
    trigger_pattern_ids UUID[],  -- which patterns led to this
    trigger_prompt_ids UUID[],  -- which specific prompts
    rollback_available BOOLEAN DEFAULT TRUE,
    rolled_back_at TIMESTAMPTZ
);
```

For DRDO audit purposes, this is the permanent record of why every schema field exists, who approved it, and what prompted it.

### 10.5 Schema versioning convention

- **Major version** (v2 → v3): breaking changes (fields removed, types changed). Requires DRDO program manager sign-off.
- **Minor version** (v2.3 → v2.4): additive changes (new fields, new enum values). Tier T1-T3 approval.
- **Patch version** (v2.3.1 → v2.3.2): documentation updates, no schema changes. No approval needed.

The version follows semver. Persisted objects carry the schema version they were created against. The migration chain handles cross-version loading.

### 10.6 Parser prompt versioning

Every schema change requires a parser prompt change. Both must be versioned together:

```python
class ParserPromptVersion(BaseModel):
    prompt_version: str  # e.g., "1.7.2"
    schema_version: str  # corresponding schema version
    prompt_hash: str  # SHA-256 of the prompt text
    effective_at: datetime
    changelog: str  # what changed in this prompt version
```

When loading an old `IntentRecord`, the system uses the parser prompt version that was active when it was created. This ensures reproducibility.

### 10.7 A/B testing for schema changes

Before promoting a schema change to production, run it in shadow mode for 1 week:
- Both old and new schemas parse every incoming prompt.
- Results are compared.
- Any divergence is flagged for review.

```python
class SchemaABTest:
    def run_shadow(self, prompt: str) -> ABTestResult:
        old_intent = self.old_parser.parse(prompt)
        new_intent = self.new_parser.parse(prompt)

        diffs = self._compute_diffs(old_intent, new_intent)
        if diffs:
            self.db.save_shadow_diff(prompt_id, diffs)

        # Return old result for production use; new result is shadow only
        return ABTestResult(production=old_intent, shadow=new_intent, diffs=diffs)
```

After 1 week, the shadow diffs are reviewed. If the new schema produces strictly better results (more fields populated, fewer `explicit_constraints` items), promote. Otherwise revise.

### 10.8 Engineering report schema display

The engineering report (the final deliverable to the engineer) must display the new field. This means:
- The report template must be updated as part of the migration.
- The report must show "new field" with a footnote like "introduced in schema v2.4" for the first 90 days after the change.

This prevents confusion when an engineer sees a new field in their report that wasn't there last month.

### 10.9 Schema change advisory board

For Tier T3 and T4 changes, a standing advisory board reviews proposals. The board consists of:
- 2 senior electronics engineers (rotating, 6-month terms)
- 1 software architect
- 1 DRDO program representative (for compliance-critical changes)
- 1 knowledge engineer (responsible for the KG and ontology)

The board meets bi-weekly. Decisions are documented and auditable.

### 10.10 Schema freeze during DRDO design reviews

During active DRDO design campaigns (when engineers are actively generating BOMs for a classified program), the schema is frozen. No changes are applied. Proposals accumulate in the queue and are batch-applied between campaigns.

This prevents a schema change from breaking an in-progress design review.

---

## 11. Implementation Roadmap

### Phase 0: Prerequisites (must be done first)

1. **Build the golden corpus** (50-100 prompts with expected outputs). This is the same prerequisite identified in prior reviews. Without it, regression testing is impossible.
2. **Pin the current schema version** as v2.0.0. Tag every persisted object with its schema version.
3. **Add the `schema_version` field to every persisted object** (`IntentRecord`, `BOM`, `InferenceRecord`). Backfill existing records with v2.0.0.

### Phase 1: Manual schema evolution (1-2 weeks)

Before building automation, establish the manual workflow:
1. Define the schema change proposal format (Component 2's schema).
2. Define the tiered approval policy (Component 3).
3. Define the migration script format.
4. Define the regression test suite (Component 5).
5. Process the first 3-5 schema changes manually to validate the workflow.

This phase validates the workflow before adding LLM assistance.

### Phase 2: Pattern detector (1-2 weeks)

Build Component 1 (Pattern Detector):
1. Implement the weekly cron job.
2. Implement the LLM "does this map to existing field" check.
3. Build the dashboard for surfacing pattern reports.
4. Run for 4 weeks to validate that the patterns surfaced are actionable.

### Phase 3: Proposal generator (2-3 weeks)

Build Component 2 (Proposal Generator):
1. Implement the LLM-driven proposal generator.
2. Implement the web-scraping vocabulary populator.
3. Implement the duplicate detection.
4. Wire to the manual workflow from Phase 1.

### Phase 4: Migration generator (2-3 weeks)

Build Component 4 (Migration Generator):
1. Implement Alembic migration generation.
2. Implement Pydantic schema diff generation.
3. Implement parser prompt diff generation.
4. Implement downstream code update generation (for common patterns).
5. Implement backward compatibility shim generation.

### Phase 5: Regression gate (1-2 weeks)

Build Component 5 (Regression Gate):
1. Implement the four-layer test suite.
2. Implement the rollback mechanism.
3. Wire to CI/CD.

### Phase 6: Lifecycle management (ongoing)

Build the additional mechanisms:
1. Field lifecycle tracking (Section 10.1).
2. Quarterly pruning review (Section 10.2).
3. Ontology registry (Section 10.3).
4. Schema archaeology (Section 10.4).
5. A/B testing (Section 10.7).

**Total estimated effort: 10-14 engineer-weeks for Phases 1-5. Ongoing maintenance: 2-4 hours/week for the schema archaeology and quarterly reviews.**

---

## 12. Anti-Patterns to Avoid

These are mistakes other teams have made. Avoid them.

### 12.1 Fully autonomous schema mutation

Do not let the LLM apply schema changes without human approval. The LLM is good at pattern detection but bad at schema design. Autonomous mutation produces a schema that reflects LLM biases, not engineering needs. The DRDO audit trail requires human accountability for every change.

### 12.2 Free-text fields in ImprovedIntentDict

Every new field must have a controlled vocabulary, units, or a canonicalization function. Free-text fields belong only in `explicit_constraints`, which is explicitly labeled as unstructured. Adding free-text fields to typed categories defeats the purpose of the typed schema.

### 12.3 Allowing field additions without ontology mapping

Every new field must declare its relationship to existing fields (synonym, hypernym, hyponym, meronym, orthogonal). Without this, semantic drift is inevitable. The ontology mapping is the single most important field in the proposal.

### 12.4 Schema changes during active design campaigns

A schema change mid-campaign breaks reproducibility. Freeze the schema during DRDO design reviews. Apply changes in batches between campaigns.

### 12.5 Skipping the regression gate

Never apply a schema change without running the full regression suite. The regression gate is the only thing preventing a bad change from breaking production.

### 12.6 Allowing the schema to grow without pruning

Without quarterly pruning, the schema accumulates unused fields. After 2 years, 50% of fields will be unused. The quarterly pruning review is mandatory.

### 12.7 Treating schema changes as engineering tickets

Schema changes are architectural decisions, not engineering tasks. They require architectural review, not just sprint allocation. Tier T3+ changes should be discussed at architecture review board meetings, not handled in standup.

### 12.8 Not versioning the parser prompt alongside the schema

The parser prompt and the schema are coupled. If you change one without the other, the parser produces output that doesn't match the schema (or vice versa). Always version them together.

### 12.9 Not backfilling historical data

When you add a new field, old data doesn't have it. Decide explicitly: do you backfill (re-parse old prompts with the new prompt), leave as null (and accept that old data is incomplete), or mark old data as deprecated. Don't leave this implicit.

### 12.10 Not documenting the engineering meaning

Every field needs an ontology entry explaining what it represents physically. "output_compliance_voltage" is ambiguous — is it the minimum, the maximum, or the range? The ontology entry must specify. Without this, two engineers will populate the same field differently.

---

## 13. What This Architecture Does NOT Solve

For honesty, several problems the team might hope this solves are not addressed:

### 13.1 It does not eliminate the need for engineering judgment

The LLM surfaces patterns and proposes changes. Engineers still make decisions. If the team hopes the LLM will autonomously evolve the schema, this document disappoints them. The LLM is an assistant, not a replacement.

### 13.2 It does not make schema changes fast

With tiered approval, regression testing, and A/B testing, a typical T2 change takes 2-3 weeks from proposal to production. This is by design — schema changes should not be fast. If the team needs rapid schema iteration, they need a different architecture (perhaps a separate "experimental" schema that doesn't affect production).

### 13.3 It does not handle fundamental ontology shifts

If the team discovers that `ReliabilityRequirements` and `EnvironmentalConstraints` should be merged, this architecture handles it (as a Tier T4 change). But it doesn't help the team *discover* this need. Ontology-level restructuring requires human architectural insight, not pattern detection.

### 13.4 It does not solve cross-pipeline schema coherence

The `ImprovedIntentDict` is one schema. The KB has its own schema (`electrical_parameters`, `pins`, `packages`). The NIR has its own schema. The BOM has its own schema. This architecture only addresses the intent schema. Cross-schema coherence is a separate problem.

### 13.5 It does not handle DRDO-specific approval cycles

DRDO has its own approval processes for engineering artifacts. This architecture assumes the team has authority to make schema changes internally. If DRDO requires external approval for schema changes affecting classified designs, this architecture needs an additional approval gate that this document does not address.

---

## 14. Comparison to the Naive Approach

| Aspect | Naive (LLM + scraping, auto-apply) | Recommended (this document) |
|--------|------------------------------------|----------------------------|
| Pattern detection | LLM (good) | LLM (good) — same |
| Proposal generation | LLM (limited — no ontology, no vocab) | LLM + structured proposal format (better) |
| Approval | None or rubber-stamp | Tiered, with cooling-off and spot audit |
| Migration | Ad-hoc | Automated generation with backward compat |
| Regression testing | None | Four-layer gate, mandatory |
| Backward compatibility | Broken | Three strategies, applied per-change |
| Field proliferation | Guaranteed within 6 months | Controlled via lifecycle tracking + pruning |
| Audit trail | None | Complete, permanent, DRDO-grade |
| Time-to-apply | Hours | Weeks (by design) |
| DRDO acceptability | No | Yes |

The naive approach is faster initially and breaks the project within 12 months. The recommended approach is slower initially and produces a sustainable, auditable schema evolution process.

---

## 15. Final Recommendation

**Build the recommended architecture. Do not build the naive version.**

The naive version (LLM + scraping, auto-apply) is technically feasible and would produce visible results within 2 weeks. It would also produce schema chaos within 6 months, break reproducibility for DRDO audits within 12 months, and require a full schema reset within 18 months.

The recommended architecture requires 10-14 engineer-weeks of upfront work but produces a sustainable schema evolution process that:
- Surfaces real patterns from real prompts
- Proposes changes with full semantic metadata
- Approves changes at the right level of friction
- Migrates safely with backward compatibility
- Tests regressions before promotion
- Prunes unused fields quarterly
- Maintains a complete audit trail for DRDO compliance

The single most important prerequisite (called out in prior reviews, called out again here) is **the golden corpus**. Without it, the regression gate cannot function, and without the regression gate, no schema evolution is safe. Build the corpus first.

---

## 16. Concrete Next Steps (Ordered)

1. **Build the golden corpus.** 50-100 prompts with expected outputs at every stage. 2-4 engineer-weeks. (Same as prior reviews' #1 recommendation.)
2. **Tag all persisted objects with `schema_version = "2.0.0"`.** Backfill existing records. 1 day.
3. **Write the manual schema change workflow document.** Define proposal format, approval tiers, migration format, regression test format. 3-5 days.
4. **Process 3-5 schema changes manually** to validate the workflow. Identify what the manual process is missing. 1-2 weeks.
5. **Build the Pattern Detector** (Component 1). 1-2 weeks.
6. **Run the Pattern Detector for 4 weeks** to validate it surfaces actionable patterns. 4 weeks (mostly waiting).
7. **Build the Proposal Generator** (Component 2). 2-3 weeks.
8. **Build the Migration Generator** (Component 4). 2-3 weeks.
9. **Build the Regression Gate** (Component 5). 1-2 weeks.
10. **Build the Lifecycle Management components** (Section 10). Ongoing.

Items 1-4 are prerequisites that must be done before any automation. Items 5-9 are the automation itself, in dependency order. Item 10 is ongoing.

**Do not skip items 1-4.** They are the manual validation that the automation will work. Skipping them produces an automated system that automates a broken workflow.
