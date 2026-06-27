# Q6 — Relational Database Schema

## Design Principles

The schema is designed for PostgreSQL 15+ and must support:
- Millions of components with thousands of electrical parameters each
- Sub-second parametric search (find all zero-drift op-amps with noise <5nV/√Hz)
- Semantic similarity search via pgvector extension
- Component relationship traversal (equivalent parts, recommended pairings)
- Full document provenance (every parameter traces to a source page)
- Incremental ingestion without breaking existing queries

---

## Complete Schema

```sql
-- ═══════════════════════════════════════════════════════════
-- EXTENSIONS
-- ═══════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";     -- trigram fuzzy search
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS "btree_gist";   -- range indexing


-- ═══════════════════════════════════════════════════════════
-- TAXONOMY
-- ═══════════════════════════════════════════════════════════

CREATE TABLE manufacturers (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          VARCHAR(200) NOT NULL,
    short_name    VARCHAR(50),
    website       VARCHAR(500),
    country       VARCHAR(100),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name)
);

CREATE TABLE component_categories (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          VARCHAR(100) NOT NULL,
    parent_id     UUID REFERENCES component_categories(id),
    depth         INT NOT NULL DEFAULT 0,
    full_path     TEXT,   -- "Analog ICs / Op-Amps / Zero-Drift"
    UNIQUE(full_path)
);

-- Populate full_path via trigger on insert/update
CREATE OR REPLACE FUNCTION update_category_path() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.parent_id IS NULL THEN
        NEW.full_path := NEW.name;
        NEW.depth := 0;
    ELSE
        SELECT full_path || ' / ' || NEW.name, depth + 1
        INTO NEW.full_path, NEW.depth
        FROM component_categories WHERE id = NEW.parent_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_category_path
    BEFORE INSERT OR UPDATE ON component_categories
    FOR EACH ROW EXECUTE FUNCTION update_category_path();


-- ═══════════════════════════════════════════════════════════
-- COMPONENTS (Core)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE components (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_id       UUID NOT NULL REFERENCES manufacturers(id),
    part_number           VARCHAR(150) NOT NULL,
    part_number_clean     VARCHAR(150),  -- normalized: uppercase, no spaces
    part_number_base      VARCHAR(100),  -- base part (strip package suffix)
    category_id           UUID REFERENCES component_categories(id),
    description           TEXT,
    lifecycle_status      VARCHAR(50) DEFAULT 'active',
    -- active | nrfnd | obsolete | preview | discontinued
    rohs_compliant        BOOLEAN,
    reach_compliant       BOOLEAN,
    export_control_class  VARCHAR(50),  -- EAR99, ECCN, ITAR
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW(),
    ingestion_version     VARCHAR(20),  -- which P1 version parsed this
    UNIQUE(manufacturer_id, part_number)
);

-- Full-text search index on description + part_number
CREATE INDEX idx_components_fts ON components
    USING GIN(to_tsvector('english', coalesce(description, '') || ' ' || part_number));

-- Trigram index for fuzzy part number search
CREATE INDEX idx_components_part_trgm ON components
    USING GIN(part_number_clean gin_trgm_ops);


-- ═══════════════════════════════════════════════════════════
-- ELECTRICAL PARAMETERS
-- ═══════════════════════════════════════════════════════════

CREATE TABLE electrical_parameters (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    parameter_name  VARCHAR(200) NOT NULL,
    symbol          VARCHAR(50),
    section_type    VARCHAR(100),
    -- electrical_characteristics | absolute_maximum_ratings | timing | ordering
    conditions      TEXT,
    value_min       DOUBLE PRECISION,
    value_typ       DOUBLE PRECISION,
    value_max       DOUBLE PRECISION,
    unit            VARCHAR(50),       -- canonical SI unit
    unit_raw        VARCHAR(50),       -- as printed in datasheet
    raw_text        TEXT,              -- original cell text
    footnote        TEXT,              -- linked footnote if any
    confidence      FLOAT NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    extraction_method VARCHAR(50),     -- p1_vector | p1_vlm | manual
    source_document_id UUID,           -- references documents.id
    source_page     INT,
    source_table_index INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Partial indexes for common parametric queries
CREATE INDEX idx_ep_component ON electrical_parameters(component_id);
CREATE INDEX idx_ep_symbol ON electrical_parameters(symbol) WHERE symbol IS NOT NULL;
CREATE INDEX idx_ep_section ON electrical_parameters(section_type);

-- For range queries: find all components with supply voltage 2.7V-5.5V
CREATE INDEX idx_ep_value_range ON electrical_parameters
    USING GIST(numrange(value_min, value_max, '[]'))
    WHERE value_min IS NOT NULL AND value_max IS NOT NULL;


-- ═══════════════════════════════════════════════════════════
-- PINS
-- ═══════════════════════════════════════════════════════════

CREATE TABLE pins (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id          UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    pin_number            VARCHAR(20) NOT NULL,
    raw_name              VARCHAR(100) NOT NULL,
    normalized_function   VARCHAR(100),  -- set by P2 normalizer
    normalization_confidence FLOAT,
    normalization_method  VARCHAR(50),   -- dictionary | context | llm | manual
    pin_type              VARCHAR(50),
    -- input | output | power | ground | io | nc | analog | differential
    description           TEXT,
    alternate_functions   TEXT[],        -- array of alt function strings
    source_page           INT,
    UNIQUE(component_id, pin_number)
);

CREATE INDEX idx_pins_component ON pins(component_id);
CREATE INDEX idx_pins_function ON pins(normalized_function)
    WHERE normalized_function IS NOT NULL;


-- ═══════════════════════════════════════════════════════════
-- PACKAGES AND FOOTPRINTS
-- ═══════════════════════════════════════════════════════════

CREATE TABLE packages (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id      UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    package_name      VARCHAR(100) NOT NULL,  -- IPC-7351 normalized
    package_name_raw  VARCHAR(100),           -- as in datasheet
    pin_count         INT,
    body_length_mm    FLOAT,
    body_width_mm     FLOAT,
    height_mm         FLOAT,
    pitch_mm          FLOAT,
    land_pattern_name VARCHAR(100),
    kicad_footprint   VARCHAR(300),  -- KiCad library:footprint reference
    tscircuit_footprint VARCHAR(300), -- tscircuit footprint name
    is_primary        BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_packages_component ON packages(component_id);
CREATE INDEX idx_packages_name ON packages(package_name);


-- ═══════════════════════════════════════════════════════════
-- LAYOUT CONSTRAINTS (Phase 5 output)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE layout_constraints (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id     UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    constraint_type  VARCHAR(50) NOT NULL,
    -- proximity | keepout | layer | orientation | routing
    subject          VARCHAR(200),
    relative_to      VARCHAR(200),
    relative_to_type VARCHAR(50),  -- component | pin | board_edge
    max_distance_mm  FLOAT,
    min_distance_mm  FLOAT,
    layer            VARCHAR(20),  -- top | bottom | any
    hard             BOOLEAN DEFAULT TRUE,
    source_sentence  TEXT,
    confidence       FLOAT,
    source_document_id UUID
);

CREATE INDEX idx_lc_component ON layout_constraints(component_id);


-- ═══════════════════════════════════════════════════════════
-- DOCUMENTS
-- ═══════════════════════════════════════════════════════════

CREATE TABLE documents (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title             TEXT NOT NULL,
    doc_type          VARCHAR(50) NOT NULL,
    -- datasheet | app_note | reference_design | academic_paper | standard
    url               TEXT,
    doi               VARCHAR(200),   -- for academic papers
    local_path        TEXT,
    file_hash         VARCHAR(64),    -- SHA-256
    file_size_bytes   BIGINT,
    page_count        INT,
    publication_date  DATE,
    revision          VARCHAR(50),
    manufacturer_id   UUID REFERENCES manufacturers(id),
    ingested_at       TIMESTAMPTZ DEFAULT NOW(),
    ingestion_status  VARCHAR(50) DEFAULT 'pending',
    -- pending | processing | complete | failed | outdated
    ingestion_version VARCHAR(20),
    last_checked_at   TIMESTAMPTZ,
    remote_etag       VARCHAR(200),   -- for freshness checking
    UNIQUE(file_hash)
);

CREATE TABLE component_documents (
    component_id      UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    document_id       UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL,
    -- primary_datasheet | supplementary | app_note | reference_design
    is_primary        BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (component_id, document_id, relationship_type)
);

CREATE INDEX idx_documents_type ON documents(doc_type);
CREATE INDEX idx_documents_manufacturer ON documents(manufacturer_id)
    WHERE manufacturer_id IS NOT NULL;

-- Full-text search on document title
CREATE INDEX idx_documents_fts ON documents
    USING GIN(to_tsvector('english', title));


-- ═══════════════════════════════════════════════════════════
-- COMPONENT RELATIONSHIPS
-- ═══════════════════════════════════════════════════════════

CREATE TABLE component_relationships (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_a_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL,
    -- equivalent | drop_in_replacement | functional_alternative
    -- recommended_pairing | incompatible | replaces | replaced_by
    component_b_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    is_symmetric      BOOLEAN DEFAULT TRUE,
    confidence        FLOAT DEFAULT 1.0,
    notes             TEXT,
    source            VARCHAR(200),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    CHECK (component_a_id != component_b_id)
);

CREATE INDEX idx_cr_a ON component_relationships(component_a_id, relationship_type);
CREATE INDEX idx_cr_b ON component_relationships(component_b_id, relationship_type);


-- ═══════════════════════════════════════════════════════════
-- DESIGN PATTERNS
-- ═══════════════════════════════════════════════════════════

CREATE TABLE design_patterns (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name              VARCHAR(200) NOT NULL,
    description       TEXT,
    topology_type     VARCHAR(100),
    -- current_source | voltage_reference | filter | oscillator | converter
    source_document_id UUID REFERENCES documents(id),
    key_equations     TEXT,
    performance_notes TEXT,
    methodology       VARCHAR(50),
    -- RF_highfreq | power_management | mixed_signal | standard_SMD
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE design_pattern_roles (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_id           UUID NOT NULL REFERENCES design_patterns(id) ON DELETE CASCADE,
    role_name            VARCHAR(200) NOT NULL,
    -- error_amplifier | sense_resistor | power_transistor | reference
    component_category   VARCHAR(200),
    specific_component_id UUID REFERENCES components(id),
    is_critical          BOOLEAN DEFAULT FALSE,
    selection_criteria   TEXT,
    typical_value        TEXT
);

CREATE INDEX idx_dp_topology ON design_patterns(topology_type);
CREATE INDEX idx_dpr_pattern ON design_pattern_roles(pattern_id);


-- ═══════════════════════════════════════════════════════════
-- SUPPLIER AND AVAILABILITY
-- ═══════════════════════════════════════════════════════════

CREATE TABLE supplier_cache (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    supplier        VARCHAR(100) NOT NULL,
    -- DigiKey | Mouser | Arrow | Avnet | element14
    supplier_part_no VARCHAR(150),
    status          VARCHAR(50) NOT NULL DEFAULT 'unknown',
    -- available | unavailable | limited | unknown
    stock_count     INT,
    price_usd_1     FLOAT,   -- unit price at qty 1
    price_usd_100   FLOAT,   -- unit price at qty 100
    price_usd_1000  FLOAT,   -- unit price at qty 1000
    lead_time_weeks INT,
    snapshot_date   DATE NOT NULL,
    UNIQUE(component_id, supplier)
);

CREATE INDEX idx_supplier_component ON supplier_cache(component_id);
CREATE INDEX idx_supplier_status ON supplier_cache(status, supplier);


-- ═══════════════════════════════════════════════════════════
-- EMBEDDINGS (for semantic search)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE component_embeddings (
    component_id    UUID PRIMARY KEY REFERENCES components(id) ON DELETE CASCADE,
    embedding       VECTOR(384),   -- all-MiniLM-L6-v2 (384-dim)
    embedding_text  TEXT,          -- what was embedded
    model_name      VARCHAR(100),
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- IVFFlat index for approximate nearest neighbor search
-- Build AFTER 10K+ rows exist for best performance
-- CREATE INDEX idx_embeddings_ann ON component_embeddings
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE document_embeddings (
    document_id     UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    embedding       VECTOR(384),
    chunk_text      TEXT,          -- which chunk was embedded (for long docs)
    chunk_index     INT DEFAULT 0,
    model_name      VARCHAR(100),
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);


-- ═══════════════════════════════════════════════════════════
-- REVIEW QUEUE (for human validation)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE review_queue (
    item_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stage           VARCHAR(100) NOT NULL,
    component_id    UUID REFERENCES components(id),
    document_id     UUID REFERENCES documents(id),
    severity        VARCHAR(20) NOT NULL,  -- CRITICAL | WARNING | INFO
    verdict         VARCHAR(50),
    flags           JSONB,
    status          VARCHAR(50) DEFAULT 'pending',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolution_notes TEXT
);

CREATE INDEX idx_rq_status ON review_queue(status, severity);
CREATE INDEX idx_rq_component ON review_queue(component_id)
    WHERE component_id IS NOT NULL;
```

---

## Key Query Patterns

### Parametric search — find zero-drift op-amps with noise < 5nV/√Hz

```sql
SELECT
    c.part_number,
    m.short_name as manufacturer,
    noise.value_typ as noise_nV_rtHz,
    drift.value_typ as drift_uV_C
FROM components c
JOIN manufacturers m ON c.manufacturer_id = m.id
JOIN electrical_parameters noise ON noise.component_id = c.id
    AND noise.symbol = 'en'
    AND noise.unit = 'nV/rtHz'
    AND noise.value_typ < 5
JOIN electrical_parameters drift ON drift.component_id = c.id
    AND drift.symbol IN ('VOS_drift', 'dVOS/dT')
    AND drift.unit = 'uV/C'
    AND drift.value_max < 0.1
WHERE c.lifecycle_status = 'active'
ORDER BY noise.value_typ ASC;
```

### Semantic search — find components similar to a description

```sql
SELECT
    c.part_number,
    m.short_name,
    1 - (e.embedding <=> query.vec) AS similarity
FROM component_embeddings e
JOIN components c ON e.component_id = c.id
JOIN manufacturers m ON c.manufacturer_id = m.id,
LATERAL (
    SELECT embedding AS vec
    FROM component_embeddings
    WHERE component_id = 'reference-component-uuid'
) query
WHERE 1 - (e.embedding <=> query.vec) > 0.7
ORDER BY similarity DESC
LIMIT 20;
```

### Find all recommended pairings for a component

```sql
SELECT
    c2.part_number,
    cr.relationship_type,
    cr.notes
FROM component_relationships cr
JOIN components c2 ON cr.component_b_id = c2.id
WHERE cr.component_a_id = 'target-component-uuid'
    AND cr.relationship_type IN ('recommended_pairing', 'equivalent')
ORDER BY cr.confidence DESC;
```

---

## Scalability Notes

**Partitioning for Phase 3 (1M+ components):**

```sql
-- Partition electrical_parameters by section_type for faster per-section queries
CREATE TABLE electrical_parameters (
    -- same columns as above
) PARTITION BY LIST (section_type);

CREATE TABLE ep_electrical_characteristics
    PARTITION OF electrical_parameters
    FOR VALUES IN ('electrical_characteristics');

CREATE TABLE ep_absolute_maximum
    PARTITION OF electrical_parameters
    FOR VALUES IN ('absolute_maximum_ratings');
```

**Read replicas:** Parametric search queries are read-heavy. At Phase 3 scale, add one PostgreSQL read replica. All SELECT queries route to replicas. All INSERT/UPDATE route to primary.

**pgvector index at scale:** The `ivfflat` index comment in the schema is intentionally commented out. Build it only after 10,000+ embeddings exist. Use `lists = sqrt(row_count)` as the lists parameter.
