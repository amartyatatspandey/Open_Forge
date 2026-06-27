# Q3 + Q4 + Q5 — Retrieval Architecture, Scraping vs Knowledge Base, and Hybrid Strategy

## Q3 — Datasheet Retrieval Architecture

After intent extraction and requirement completion, the system knows what it needs. The retrieval planner converts that into specific retrieval queries.

### Retrieval Planner

```
ImprovedIntentDict v2 (with implied requirements)
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  Retrieval Planner                                     │
│                                                        │
│  Input:  ImprovedIntentDict v2                         │
│  Output: RetrievalPlan                                 │
│                                                        │
│  Determines:                                           │
│  - Which component categories to search                │
│  - Which specific parts to fetch datasheets for        │
│  - Which application notes to retrieve                 │
│  - Which academic papers are relevant                  │
│  - Which reference designs to locate                   │
└────────────────────────────────────────────────────────┘
```

**RetrievalPlan schema:**

```python
class ComponentQuery(BaseModel):
    component_type: str          # "zero_drift_op_amp"
    required_attributes: dict    # {"noise_nV_rtHz": "<5", "offset_drift_uV_C": "<0.05"}
    preferred_manufacturers: list[str]
    source: str                  # which implied requirement generated this

class DocumentQuery(BaseModel):
    query_type: str              # "datasheet", "app_note", "paper", "reference_design"
    search_terms: list[str]      # ["libbrecht hall current source", "precision current source low noise"]
    target_url: Optional[str]    # if direct URL is known
    doi: Optional[str]           # for academic papers
    manufacturer: Optional[str]  # for app notes: which manufacturer to search

class RetrievalPlan(BaseModel):
    component_queries: list[ComponentQuery]
    document_queries: list[DocumentQuery]
    priority_order: list[str]    # which to retrieve first
```

### Retrieval Plan for Prompt 1 (Libbrecht-Hall)

The planner generates this from the completed intent dict:

**Component queries:**
- Zero-drift op-amp: `{offset_drift: <0.1µV/°C, noise: <10nV/√Hz, single_supply: true}`
- Ultra-precision resistor: `{tempco: <5ppm/°C, tolerance: <0.01%}`
- Precision voltage reference: `{tempco: <5ppm/°C, noise: <10µVpp}`
- Low-noise LDO: `{output_noise: <10µVrms, PSRR: >60dB}`
- Potentiometer: `{type: wirewound_or_cermet, precision: true}`
- Power transistor: `{type: NPN_or_NMOS, Ic_max: >100mA}`
- Negative rail converter: `{type: inverting_charge_pump_or_negative_LDO}`

**Document queries:**
- Academic paper: `"Libbrecht Hall current source"` → DOI: 10.1063/1.1144208
- App note: TI SBOA327 — "Precision Current Source Design"
- App note: TI SBOA273 — "Low-Noise Current Source Techniques"
- App note: ADI AN-1357 — "Precision Current Sources and Sinks"
- App note: Any LDO app note for low-noise filtering
- Reference design: Any published Libbrecht-Hall implementation

### Source Priority by Document Type

| Document Type | Primary Source | Secondary Source | Tertiary Source |
|--------------|----------------|-----------------|----------------|
| Datasheet | Manufacturer website | DigiKey/Mouser PDF | Internal corpus |
| App note | Manufacturer app note portal | Internal corpus | Web search |
| Academic paper | DOI resolver → publisher | Semantic Scholar API | ArXiv |
| Reference design | Manufacturer reference design DB | GitHub search | EEVblog/forum |

---

## Q4 — Web Scraping vs Persistent Knowledge Base

### Approach A: Real-Time Web Scraping

Every user prompt triggers live web scraping, PDF download, and parsing.

**Advantages:**
- Always retrieves the latest datasheet revision
- No storage infrastructure required
- Zero upfront cost — nothing to build before first query
- Covers any component ever made as long as it has a web presence

**Disadvantages:**
- Latency is severe: scraping + downloading + P1 parsing a single datasheet takes 30–120 seconds. For a design requiring 15 datasheets, that is 8–30 minutes of waiting before BOM generation even begins.
- Network dependency: fails completely in air-gapped deployments (DRDO use case)
- Reliability: manufacturer websites block scrapers, change URL patterns, go offline. DigiKey changed their PDF URL scheme three times in 2023 alone.
- Cost: cloud LLM inference (Qwen 397B) for P1 Phase 3 extraction on 15 datasheets = significant API cost per query, repeated on every query even for the same components
- Scalability: every concurrent user triggers a fresh scraping + parsing pipeline. 10 concurrent users = 10 simultaneous scraping jobs
- Failure modes: soft failures are dangerous. A partially scraped datasheet produces wrong specs. The system has no way to know that page 4 of 12 failed to download.
- No learning: every run is cold. The system never gets better at knowing which components are frequently needed.

**Failure mode example:** A user designs a precision current source. The scraper downloads the OPA189 datasheet but page 3 (containing the noise density curve) fails with a 503. The system extracts noise specs from surrounding text only. The resulting BOM uses the wrong op-amp because the noise spec is incorrect.

**Verdict:** Acceptable only for proof-of-concept. Not production-ready. Completely incompatible with air-gapped DRDO deployment.

---

### Approach B: Persistent Knowledge Base

Every datasheet is downloaded once, parsed once, and stored permanently. Queries hit the database.

**Advantages:**
- Latency: sub-second retrieval after initial ingestion. A query for "low-noise op-amp <5nV/√Hz" returns results in milliseconds.
- Air-gapped compatible: once built, the knowledge base requires no internet
- Reliability: data quality is verified at ingestion time, not at query time. Partial failures during ingestion are caught and corrected before the data is used.
- Cost efficiency: parsing cost is paid once per component, not once per query. For frequently used components (TL071, OPA189, LM317) the parsing cost is amortized across hundreds of queries.
- Enables quality control: the review queue (already built) catches extraction errors before they enter production use.
- Accumulating intelligence: as more components are ingested, the system becomes progressively more capable.

**Disadvantages:**
- Upfront investment: the knowledge base is empty at day one. An ingestion campaign is required before the system is useful.
- Staleness risk: datasheet revisions are not automatically detected. An LDO with a revised noise spec will show old data until the datasheet is re-ingested.
- Storage cost: scaling to 1M components requires significant storage infrastructure (see Q8).
- Coverage gaps: if a required component has never been ingested, the system falls back to "no data" rather than retrieving it automatically.

**Failure mode example:** Engineer requests a design using a newly released component (released last month). It is not in the knowledge base. The system correctly returns "component not found" and routes to human review — the engineer must manually add the datasheet.

**Verdict:** The correct long-term architecture. The staleness and coverage problems are manageable with a hybrid fallback.

---

## Q5 — Hybrid Architecture (Recommended)

The hybrid approach uses the persistent knowledge base as the primary path and falls back to real-time web scraping only when necessary.

```
Design Query
      │
      ▼
┌─────────────────────────────────────┐
│  Query Internal Knowledge Base      │
│  (PostgreSQL + vector search + KG)  │
└──────────────┬──────────────────────┘
               │
       Component found?
       ┌───────┴───────┐
      YES              NO
       │               │
       ▼               ▼
  Return from     ┌────────────────────────┐
  KB instantly    │  Is scraping allowed?  │
                  │  (not air-gapped?)     │
                  └──────┬─────────────────┘
                         │
                   ┌─────┴─────┐
                  YES          NO
                   │           │
                   ▼           ▼
           ┌────────────┐  Flag as missing,
           │  Real-time │  route to human
           │  Scraper   │  review queue
           └─────┬──────┘
                 │
                 ▼
         Download + Parse
         (P1 pipeline)
                 │
                 ▼
         Store in KB
         (persistent)
                 │
                 ▼
         Return result
```

### Freshness Management

For components already in the knowledge base, a staleness check runs on a schedule:

```python
class DatasheetFreshnessChecker:
    def check_for_updates(self, component_id: str) -> bool:
        """
        HEAD request to manufacturer URL.
        Compare ETag or Last-Modified header to stored value.
        Flag for re-ingestion if changed.
        Cost: ~50ms per component, run nightly for top 10K components.
        """
```

Components that change rarely (discrete passives, standard logic) are checked quarterly. Components that change frequently (complex ICs with errata) are checked monthly.

### Query Decision Logic

```python
def retrieve_component_data(component_id: str, config: Config) -> ComponentDatasheet:
    # Step 1: Check internal KB
    result = kb.get_component(component_id)
    if result and result.freshness_days < config.max_staleness_days:
        return result

    # Step 2: Is scraping permitted?
    if config.air_gapped:
        raise ComponentNotFoundError(
            f"{component_id} not in knowledge base. "
            f"System is air-gapped. Add datasheet manually."
        )

    # Step 3: Scrape, parse, store
    pdf_path = scraper.download_datasheet(component_id)
    datasheet = p1_pipeline.parse(component_id, pdf_path)
    kb.store(datasheet)
    return datasheet
```

### Air-Gapped Operation

For DRDO air-gapped deployment, the hybrid reduces to pure persistent KB. The scraping fallback is disabled via `config.air_gapped = True`. The system operates entirely offline. The only way to add new components is manual datasheet ingestion through the review queue CLI.

This is operationally manageable: before a new design campaign, the DRDO team runs a batch ingestion of all expected components. The corpus grows with each project.

### Cost Analysis

| Scenario | Approach A (scraping) | Approach B (KB only) | Hybrid |
|---------|----------------------|---------------------|--------|
| First query, known component | 2–5 min, ~$0.50 API | <1 sec, ~$0.001 | <1 sec, ~$0.001 |
| First query, unknown component | 2–5 min, ~$0.50 API | Fails | 2–5 min, stores result |
| Second query, same component | 2–5 min, ~$0.50 API | <1 sec, ~$0.001 | <1 sec, ~$0.001 |
| Air-gapped deployment | Fails | Works | Works |
| 100 concurrent users | 100 parallel scrape jobs | 100 DB queries | 100 DB queries + rare scrapes |

Hybrid is strictly superior in every scenario.
