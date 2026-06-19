# Q7 + Q8 + Q9 + Q10 — Search Architecture, Storage, Local Deployment, and Complete System

---

## Q7 — Search and Retrieval Architecture

The answer to "should we search every row" vs "use embeddings and graph" is not either/or. The correct architecture uses four layers in sequence, each faster and cheaper than invoking the next. Most queries are resolved in layers 1 or 2 without ever reaching the vector database.

### Four-Layer Retrieval Stack

```
Query: "Find a zero-drift op-amp with noise < 5nV/√Hz for 100mA current source"
        │
        ▼
LAYER 1: Structured SQL (fastest, exact)
    Parametric WHERE clauses on electrical_parameters
    Returns exact matches in <10ms
    Handles: known symbols, known units, known numeric ranges
        │
    Results? ──YES──► Return + stop
        │ NO
        ▼
LAYER 2: Full-Text Search (fast, keyword)
    PostgreSQL tsvector on description + part_number
    pg_trgm fuzzy match on part number
    Returns keyword matches in <50ms
    Handles: "libbrecht hall", "zero drift", "ultra precision"
        │
    Results? ──YES──► Return + stop
        │ NO
        ▼
LAYER 3: Vector Search (slower, semantic)
    pgvector cosine similarity on component embeddings
    all-MiniLM-L6-v2 (384-dim, CPU-runnable)
    Returns semantically similar components in <200ms
    Handles: intent-described requirements without exact symbol match
        │
    Results? ──YES──► Return + stop
        │ NO
        ▼
LAYER 4: Knowledge Graph Traversal (comprehensive)
    Neo4j / NetworkX traversal from component type nodes
    Follows REQUIRES, USES, IS_A edges
    Returns component types + design patterns in <500ms
    Handles: topology-level queries ("what goes in a current source?")
        │
    Results? ──YES──► Return
        │ NO
        ▼
FALLBACK: Web Scrape + Ingest (if not air-gapped)
    Download + P1 parse + store + return
    Latency: 30–120 seconds
    Only reached for genuinely unknown components
```

### Layer 1: Structured SQL Parametric Search

For "Libbrecht Hall design" + "ultra-low noise" + "zero-drift op-amps":

```sql
-- Layer 1: direct parametric match
SELECT DISTINCT c.id, c.part_number, m.short_name
FROM components c
JOIN manufacturers m ON c.manufacturer_id = m.id
JOIN electrical_parameters noise_ep
    ON noise_ep.component_id = c.id
    AND noise_ep.symbol = 'en'
    AND noise_ep.unit = 'nV/rtHz'
    AND noise_ep.value_typ < 5
JOIN electrical_parameters drift_ep
    ON drift_ep.component_id = c.id
    AND drift_ep.symbol = 'VOS_drift'
    AND drift_ep.unit = 'uV/C'
    AND drift_ep.value_max < 0.1
JOIN component_categories cat ON c.category_id = cat.id
    AND cat.full_path LIKE '%Op-Amp%'
WHERE c.lifecycle_status = 'active'
ORDER BY noise_ep.value_typ ASC
LIMIT 10;
```

Execution time: 5–15ms on 100K components with proper indexes.

### Layer 2: Full-Text + Fuzzy Search

```sql
-- Layer 2: keyword search when no parametric match
SELECT c.id, c.part_number,
    ts_rank(
        to_tsvector('english', c.description || ' ' || c.part_number),
        plainto_tsquery('english', 'zero drift precision op amp low noise')
    ) AS rank
FROM components c
WHERE to_tsvector('english', coalesce(c.description,'') || ' ' || c.part_number)
    @@ plainto_tsquery('english', 'zero drift precision op amp low noise')
ORDER BY rank DESC
LIMIT 20;
```

Also searches document titles for "Libbrecht Hall":

```sql
SELECT d.id, d.title, d.doc_type, d.url
FROM documents d
WHERE to_tsvector('english', d.title) @@ plainto_tsquery('libbrecht hall')
    OR d.doi = '10.1063/1.1144208';
```

### Layer 3: Vector Search

```python
def semantic_search(
    query_text: str,
    n_results: int = 20,
    min_similarity: float = 0.70,
) -> list[ComponentSearchResult]:
    # Encode query using same model as embeddings
    query_vec = encoder.encode(query_text).tolist()

    # pgvector cosine similarity search
    results = db.execute("""
        SELECT c.part_number, m.short_name,
               1 - (e.embedding <=> %s::vector) AS similarity
        FROM component_embeddings e
        JOIN components c ON e.component_id = c.id
        JOIN manufacturers m ON c.manufacturer_id = m.id
        WHERE 1 - (e.embedding <=> %s::vector) > %s
        ORDER BY similarity DESC
        LIMIT %s
    """, [query_vec, query_vec, min_similarity, n_results])
    return results
```

### Layer 4: Knowledge Graph Traversal

The KG traversal (already built in Team B) handles topology-level queries:

```
"current_source" → REQUIRES → sense_resistor, error_amplifier, power_transistor
"precision_current_source" → USES → zero_drift_op_amp, precision_resistor
"libbrecht_hall" → PART_OF → kelvin_sensing, guard_ring, compensation_network
```

### Result Fusion

When multiple layers return results, they are merged and ranked:

```python
class RetrievalFusionEngine:
    def fuse(
        self,
        sql_results: list,
        fts_results: list,
        vector_results: list,
        kg_results: list,
    ) -> list[RankedResult]:
        """
        Reciprocal Rank Fusion (RRF) across all result lists.
        score = sum(1 / (rank + 60)) for each list containing the item.
        Items appearing in multiple layers score higher.
        """
```

---

## Q8 — Storage Requirements

### Phase 1: 10,000 Components

| Asset | Calculation | Size |
|-------|------------|------|
| Raw datasheets (PDF) | 10,000 × 2MB avg | 20 GB |
| Parsed JSON (ComponentDatasheet) | 10,000 × 80KB | 800 MB |
| PostgreSQL data | 10,000 components × 50 params each | 2 GB |
| Component embeddings (384-dim f32) | 10,000 × 384 × 4 bytes | 15 MB |
| Application notes | 2,000 × 5MB avg | 10 GB |
| App note embeddings | 2,000 × 10 chunks × 384 × 4 | 30 MB |
| Academic papers | 200 × 3MB | 600 MB |
| Reference designs | 500 × 2MB | 1 GB |
| KG (GraphML) | ~50K nodes, ~200K edges | 500 MB |
| Model weights | YOLOv8n + Qwen2.5-7B + MiniLM | 35 GB |
| **Total** | | **~70 GB** |

Operating requirement: 100GB SSD minimum. 256GB recommended.

### Phase 2: 100,000 Components

| Asset | Calculation | Size |
|-------|------------|------|
| Raw datasheets | 100,000 × 2MB | 200 GB |
| Parsed JSON | 100,000 × 80KB | 8 GB |
| PostgreSQL data | 100,000 components × 50 params | 20 GB |
| Component embeddings | 100,000 × 384 × 4 | 150 MB |
| Application notes | 20,000 × 5MB | 100 GB |
| App note embeddings | 20,000 × 10 × 384 × 4 | 300 MB |
| Academic papers | 2,000 × 3MB | 6 GB |
| Reference designs | 5,000 × 2MB | 10 GB |
| Neo4j (production KG) | ~500K nodes, ~2M edges | 5 GB |
| Model weights | same | 35 GB |
| **Total** | | **~385 GB** |

Operating requirement: 500GB NVMe SSD. 1TB recommended.

### Phase 3: 1,000,000 Components

| Asset | Calculation | Size |
|-------|------------|------|
| Raw datasheets | 1M × 2MB, ~40% dedup savings | 1.2 TB |
| Parsed JSON | 1M × 80KB | 80 GB |
| PostgreSQL data (partitioned) | 1M × 50 params | 200 GB |
| Component embeddings | 1M × 384 × 4 | 1.5 GB |
| pgvector IVFFlat index | ~3× embedding size | 4.5 GB |
| Application notes | 100,000 × 5MB | 500 GB |
| App note embeddings + index | 100K × 10 × 384 × 4 × 3 | 4.5 GB |
| Academic papers | 10,000 × 3MB | 30 GB |
| Reference designs | 50,000 × 2MB | 100 GB |
| Neo4j | ~5M nodes, ~20M edges | 50 GB |
| Model weights | same | 35 GB |
| **Total** | | **~2.2 TB** |

Operating requirement: 3TB NVMe RAID. Separate GPU server for inference.

### What is Surprisingly Small

Component embeddings at any scale are tiny. 1 million components × 384 dimensions × 4 bytes = 1.5GB. This is the entire semantic search index for a million-component database. FAISS or pgvector can hold this in RAM on any modern server.

The dominant storage consumers are always raw PDFs and application note PDFs — not the structured data.

---

## Q9 — Local Deployment Feasibility (Qwen 3.5 397B)

### Memory Requirements

Qwen 3.5 397B has 397 billion parameters.

| Precision | Memory per param | Total VRAM | A100 80GB GPUs | H100 80GB GPUs |
|-----------|-----------------|-----------|----------------|----------------|
| BF16 | 2 bytes | 794 GB | 10 GPUs | 10 GPUs |
| FP8 | 1 byte | 397 GB | 5 GPUs | 5 GPUs |
| GPTQ 4-bit | 0.5 bytes | ~200 GB | 3 GPUs | 3 GPUs |
| AWQ 4-bit + KV cache | ~0.55 bytes | ~220 GB | 3 GPUs | 3 GPUs |

**Practical minimum:** 4× NVIDIA A100 80GB SXM (320GB combined) running AWQ 4-bit quantization. This is viable but tight — leaves ~100GB for KV cache and activation memory.

**Recommended configuration:** 8× NVIDIA H100 80GB NVLink (640GB combined VRAM) running FP8. This gives comfortable headroom for KV cache at long context lengths, supports multiple concurrent requests, and delivers ~3× faster token generation than A100.

### Infrastructure Architecture for On-Premise

```
┌────────────────────────────────────────────────────────────────────┐
│  Inference Server (GPU)                                            │
│  2× DGX H100 or 1× 8-GPU H100 server                             │
│  640GB VRAM total                                                  │
│  vLLM serving layer (continuous batching, paged attention)         │
│  Handles: Intent parser, Requirement completion, P1 Phase 3 & 5   │
│  Estimated cost: $300K–$500K (1× 8-GPU H100 server)              │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  Database Server (CPU + NVMe)                                      │
│  64–128 core CPU, 512GB RAM, 4TB NVMe RAID                        │
│  PostgreSQL 15 + pgvector                                          │
│  Neo4j Enterprise                                                  │
│  Elasticsearch (optional, for FTS at Phase 3 scale)               │
│  Estimated cost: $40K–$80K                                        │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  Application Server (CPU)                                          │
│  16–32 core CPU, 128GB RAM                                        │
│  Runs: pipeline orchestrator, scrapers, review CLI, API layer      │
│  Estimated cost: $15K–$25K                                        │
└────────────────────────────────────────────────────────────────────┘
```

**Total on-premise hardware cost estimate: $400K–$650K**

For DRDO context: this is within the range of a single lab instrument budget. The H100 server cost is the dominant line item.

### Short-term Cloud Alternative

While waiting for infrastructure approval:

| Component | Cloud Service | Estimated Cost |
|-----------|--------------|----------------|
| Qwen 3.5 397B inference | Together AI / Fireworks AI / SambaNova | $0.003–$0.008/1K tokens |
| PostgreSQL | AWS RDS PostgreSQL + pgvector | $500–$2,000/month |
| File storage | AWS S3 | $23/TB/month |
| Compute (P1 pipeline) | AWS c6i.8xlarge | $1.36/hour |

For a research lab running 50–100 design queries per day, cloud cost is approximately $2,000–$5,000/month.

---

## Q10 — Complete End-to-End Architecture

```
Natural Language Prompt
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│  STAGE 1: Intent Parser                                           │
│  Model: Qwen 3.5 397B (cloud) / Qwen2.5-72B (local)            │
│  Output: ImprovedIntentDict v2                                    │
│  Schema: 01_INTENT_PARSING_SCHEMA.md                             │
└──────────────────────────────┬────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  STAGE 2: Requirement Completion Engine                           │
│  Model: Qwen 3.5 397B                                            │
│  Domain knowledge: loaded from domain_knowledge.yaml by topology  │
│  Output: implied_requirements, quantified_specs, contradictions   │
│  Schema: 02_REQUIREMENT_COMPLETION_ENGINE.md                     │
└──────────────────────────────┬────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  STAGE 3: Retrieval Planner                                       │
│  Converts enhanced intent → RetrievalPlan                        │
│  Identifies: components needed, papers needed, app notes needed   │
└──────────────────────────────┬────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   Internal KB          Academic Search        Web Scraper
   (Layers 1–4)         (Semantic Scholar,     (fallback only,
   SQL + FTS +           ArXiv, DOI lookup)     not air-gapped)
   Vector + KG
          │                    │                    │
          └────────────────────┼────────────────────┘
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  STAGE 4: Datasheet Acquisition                                   │
│  For any component not in KB:                                     │
│  Download PDF → P1 Parser (5 phases) → PostgreSQL + Neo4j        │
│  For components in KB: retrieve directly                          │
└──────────────────────────────┬────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  STAGE 5: Knowledge Storage                                       │
│  PostgreSQL: components, parameters, pins, packages, documents    │
│  Neo4j: 5-layer Knowledge Graph                                   │
│  pgvector: component embeddings                                   │
│  Filesystem: raw PDFs, parsed JSON                               │
└──────────────────────────────┬────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  STAGE 6: Component Selection + BOM Generation                    │
│  KG query engine: intent → DesignSubgraph                        │
│  BOM generator: DesignSubgraph → ValidatedBOM                    │
│  BOM validator: cross-component compatibility                     │
│  Human review gate: if confidence < 0.85                         │
└──────────────────────────────┬────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│  STAGE 7: Design Synthesis                                        │
│  Schematic synthesizer: BOM + datasheets → netlist               │
│  Layout engine: netlist + KG-4 → placement constraints           │
│  NIR builder: all artifacts → Neutral Intermediate Representation │
└──────────────────────────────┬────────────────────────────────────┘
                               │
          ┌────────────────────┼──────────────────────────────────┐
          ▼                    ▼                    ▼             ▼
   KiCad Files         tscircuit Files        SPICE Netlist   Noise Analysis
   .kicad_sch          .tsx + SVG + 3D        .net / .cir     (if requested)
   .kicad_pcb          (schematic render)     [GAP-002-A]     [GAP-001-D]
   Gerbers             (PCB 3D model)
          │
          └──────────────────────────────────┐
                                             ▼
                              ┌──────────────────────────┐
                              │  Engineering Report (PDF) │
                              │  BOM with justifications  │
                              │  Source citations         │
                              │  ERC/DRC results          │
                              │  Noise analysis (if run)  │
                              └──────────────────────────┘
```

### Technology Stack Summary

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| LLM (cloud) | Qwen 3.5 397B via API | Best-in-class reasoning, large context |
| LLM (local) | Qwen2.5-72B-Instruct | Fits 2× A100 80GB, strong performance |
| Structured extraction | Instructor + Pydantic v2 | Guaranteed schema compliance |
| Primary database | PostgreSQL 15 + pgvector | ACID, parametric search, semantic search |
| Knowledge graph | Neo4j (prod) / NetworkX (dev) | Graph traversal, relationship queries |
| Full-text search | PostgreSQL FTS / Elasticsearch | Keyword and fuzzy search |
| Vector embeddings | all-MiniLM-L6-v2 (384-dim) | CPU-runnable, good quality, small |
| PDF parsing | pdfplumber + Camelot + YOLOv8n | Dual-path TSR, layout detection |
| Schematic output | KiCad MCP + tscircuit | Industry standard + programmatic |
| Serving (local) | vLLM | Continuous batching, paged attention |

### Cloud-to-On-Premise Migration Path

The system is designed so cloud-to-local migration requires zero code changes:

```python
# In src/config.py — the only file that changes between cloud and local

# Cloud configuration
class CloudConfig(Config):
    llm_base_url: str = "https://api.together.ai/v1"
    llm_model: str = "Qwen/Qwen2.5-72B-Instruct-Turbo"
    air_gapped: bool = False

# Local configuration
class LocalConfig(Config):
    llm_base_url: str = "http://localhost:8000/v1"  # vLLM server
    llm_model: str = "Qwen/Qwen2.5-72B-Instruct"
    air_gapped: bool = True  # disables web scraping fallback
```

The `llm_base_url` swap from cloud API to local vLLM server is the entire migration. All Instructor calls, all pipeline logic, all serializers are unchanged.

### Cost Comparison at Steady State

| Item | Cloud | On-Premise |
|------|-------|------------|
| LLM inference (100 queries/day) | ~$150/month | $0 (capex paid) |
| Database hosting | $1,000/month | $0 (capex paid) |
| Storage | $100/month | $0 (capex paid) |
| Hardware amortized (5 years) | — | ~$10,000/month |
| **Break-even** | — | ~18 months at cloud rate |

For DRDO: the air-gapped requirement eliminates cloud as an option for production regardless of cost. The on-premise path is not a choice — it is the only viable deployment for classified design work.
