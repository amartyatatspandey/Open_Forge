-- SECTION 0 — Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- SECTION 1 — Taxonomy
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
    full_path     TEXT,
    UNIQUE(full_path)
);

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

-- SECTION 2 — Components
CREATE TABLE components (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    manufacturer_id       UUID NOT NULL REFERENCES manufacturers(id),
    part_number           VARCHAR(150) NOT NULL,
    part_number_clean     VARCHAR(150),
    part_number_base      VARCHAR(100),
    category_id           UUID REFERENCES component_categories(id),
    description           TEXT,
    lifecycle_status      VARCHAR(50) DEFAULT 'active',
    rohs_compliant        BOOLEAN,
    reach_compliant       BOOLEAN,
    export_control_class  VARCHAR(50),
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW(),
    ingestion_version     VARCHAR(20),
    UNIQUE(manufacturer_id, part_number)
);

CREATE INDEX idx_components_fts ON components
    USING GIN(to_tsvector('english', coalesce(description, '') || ' ' || part_number));

CREATE INDEX idx_components_part_trgm ON components
    USING GIN(part_number_clean gin_trgm_ops);

-- SECTION 3 — Documents + document_files
-- Storage-level dedup: one row per unique file content
CREATE TABLE document_files (
    file_hash     VARCHAR(64) PRIMARY KEY,   -- SHA-256
    storage_path  TEXT NOT NULL,
    byte_size     BIGINT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE documents (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title             TEXT NOT NULL,
    doc_type          VARCHAR(50) NOT NULL,
    -- datasheet | app_note | reference_design | academic_paper | standard
    url               TEXT,
    doi               VARCHAR(200),
    local_path        TEXT,
    file_hash         VARCHAR(64) REFERENCES document_files(file_hash),
    -- FK to document_files; NOT UNIQUE — multiple docs can share same file
    file_size_bytes   BIGINT,
    page_count        INT,
    publication_date  DATE,
    revision          VARCHAR(50),
    manufacturer_id   UUID REFERENCES manufacturers(id),
    ingested_at       TIMESTAMPTZ DEFAULT NOW(),
    ingestion_status  VARCHAR(50) DEFAULT 'pending',
    -- pending | processing | complete | failed | needs_review | outdated
    ingestion_version VARCHAR(20),
    last_checked_at   TIMESTAMPTZ,
    remote_etag       VARCHAR(200),
    content_length    BIGINT,         -- for freshness: compare when ETag absent
    cover_sha256      VARCHAR(64)     -- SHA-256 of first 4KB; freshness fallback
);

CREATE TABLE component_documents (
    component_id      UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    document_id       UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL,
    is_primary        BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (component_id, document_id, relationship_type)
);

CREATE INDEX idx_documents_type ON documents(doc_type);
CREATE INDEX idx_documents_manufacturer ON documents(manufacturer_id)
    WHERE manufacturer_id IS NOT NULL;
CREATE INDEX idx_documents_fts ON documents
    USING GIN(to_tsvector('english', title));

-- SECTION 4 — Electrical parameters
CREATE TABLE electrical_parameters (
    id                  BIGSERIAL PRIMARY KEY,   -- 6.9: bigserial, not UUID
    component_id        UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    parameter_name      VARCHAR(200) NOT NULL,
    symbol              VARCHAR(50),
    section_type        VARCHAR(100),
    conditions          TEXT,
    value_min           DOUBLE PRECISION,
    value_typ           DOUBLE PRECISION,
    value_max           DOUBLE PRECISION,
    unit                VARCHAR(50),
    unit_raw            VARCHAR(50),
    raw_text            TEXT,
    footnote            TEXT,
    confidence          FLOAT NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
    extraction_method   VARCHAR(50),
    extraction_status   VARCHAR(50) NOT NULL DEFAULT 'approved',
    -- approved | needs_review | rejected
    -- needs_review: parameter failed QA gate during scrape-then-store path
    -- only 'approved' rows surface in parametric search
    source_document_id  UUID REFERENCES documents(id),
    source_page         INT,
    source_table_index  INT,
    -- 5.4: parameter versioning — track spec changes across datasheet revisions
    valid_from          TIMESTAMPTZ DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,             -- NULL = currently valid
    datasheet_revision_id UUID REFERENCES documents(id),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 6.1: B-tree indexes covering actual query patterns
CREATE INDEX idx_ep_component ON electrical_parameters(component_id);
CREATE INDEX idx_ep_symbol ON electrical_parameters(symbol)
    WHERE symbol IS NOT NULL;
CREATE INDEX idx_ep_section ON electrical_parameters(section_type);

-- Covering indexes for the two most common parametric query patterns
CREATE INDEX idx_ep_typ_lookup ON electrical_parameters(symbol, unit, value_typ)
    WHERE value_typ IS NOT NULL AND extraction_status = 'approved';
CREATE INDEX idx_ep_max_lookup ON electrical_parameters(symbol, unit, value_max)
    WHERE value_max IS NOT NULL AND extraction_status = 'approved';

-- GIST range index — keep for true range queries only (e.g. find supply voltage in 2.7-5.5V)
CREATE INDEX idx_ep_value_range ON electrical_parameters
    USING GIST(numrange(value_min::numeric, value_max::numeric, '[]'))
    WHERE value_min IS NOT NULL AND value_max IS NOT NULL;

-- 6.8: FTS index on raw_text + conditions for spec condition searches
CREATE INDEX idx_ep_raw_text_fts ON electrical_parameters
    USING GIN(to_tsvector('english',
        coalesce(raw_text, '') || ' ' || coalesce(conditions, '')));

-- Current parameters only (valid_to IS NULL = still current)
CREATE INDEX idx_ep_current ON electrical_parameters(component_id)
    WHERE valid_to IS NULL AND extraction_status = 'approved';

-- SECTION 5 — Pins + pin_function_vocabulary
-- 6.5: Controlled vocabulary for pin normalized functions
CREATE TABLE pin_function_vocabulary (
    function_name   VARCHAR(100) PRIMARY KEY,
    function_class  VARCHAR(50) NOT NULL,
    -- input | output | power | ground | io | clock | nc | analog | differential
    aliases         TEXT[],    -- e.g. ARRAY['VCC', 'VDD', 'PVDD']
    description     TEXT
);

-- Seed the vocabulary with canonical values from P2 normalization map
INSERT INTO pin_function_vocabulary (function_name, function_class, aliases) VALUES
    ('POWER_POSITIVE',  'power',       ARRAY['VDD', 'VCC', 'V+', 'PVDD', 'AVDD', 'DVDD', 'VIO', 'VBAT']),
    ('POWER_GROUND',    'ground',      ARRAY['GND', 'VSS', 'AGND', 'DGND', 'PGND']),
    ('POWER_INPUT',     'power',       ARRAY['VIN', 'VIN+', 'SUPPLY']),
    ('SPI_CLOCK',       'clock',       ARRAY['SCK', 'SCLK', 'CLK', 'CK', 'SPI_CLK']),
    ('SPI_DATA_IN',     'input',       ARRAY['MOSI', 'SDI', 'DI', 'COPI']),
    ('SPI_DATA_OUT',    'output',      ARRAY['MISO', 'SDO', 'DO', 'CIPO']),
    ('SPI_CHIP_SELECT', 'io',          ARRAY['CS', 'CSB', 'SS', 'NSS', 'CE', 'NCS']),
    ('I2C_DATA',        'io',          ARRAY['SDA', 'I2C_SDA', 'DAT']),
    ('I2C_CLOCK',       'clock',       ARRAY['SCL', 'I2C_SCL', 'I2C_CLK']),
    ('UART_TRANSMIT',   'output',      ARRAY['TX', 'TXD', 'UART_TX', 'TXO']),
    ('UART_RECEIVE',    'input',       ARRAY['RX', 'RXD', 'UART_RX', 'RXI']),
    ('ENABLE',          'input',       ARRAY['EN', 'ENABLE', 'ENB', 'EN_N']),
    ('RESET',           'input',       ARRAY['RST', 'RESET', 'NRST', 'RST_N']),
    ('INTERRUPT',       'output',      ARRAY['INT', 'IRQ', 'INTERRUPT', 'NIRQ']),
    ('PWM_OUTPUT',      'output',      ARRAY['PWM', 'PWM_OUT']),
    ('NO_CONNECT',      'nc',          ARRAY['NC', 'DNP']),
    ('ANALOG_INPUT',    'analog',      ARRAY['IN+', 'IN-', 'VIN+', 'VIN-', 'INP', 'INN']),
    ('ANALOG_OUTPUT',   'analog',      ARRAY['OUT', 'VOUT', 'OUTPUT']),
    ('DIFFERENTIAL_P',  'differential',ARRAY['INP', 'INN', 'VINP', 'VIN+']),
    ('DIFFERENTIAL_N',  'differential',ARRAY['INN', 'VINN', 'VIN-']);

CREATE TABLE pins (
    id                      BIGSERIAL PRIMARY KEY,   -- 6.9: bigserial
    component_id            UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    pin_number              VARCHAR(20) NOT NULL,
    raw_name                VARCHAR(100) NOT NULL,
    normalized_function     VARCHAR(100) REFERENCES pin_function_vocabulary(function_name),
    -- FK enforces controlled vocabulary; NULL allowed (not yet normalized)
    normalization_confidence FLOAT,
    normalization_method    VARCHAR(50),
    pin_type                VARCHAR(50),
    description             TEXT,
    alternate_functions     TEXT[],
    source_page             INT,
    UNIQUE(component_id, pin_number)
);

CREATE INDEX idx_pins_component ON pins(component_id);
CREATE INDEX idx_pins_function ON pins(normalized_function)
    WHERE normalized_function IS NOT NULL;

-- SECTION 6 — Packages
CREATE TABLE packages (
    id                  BIGSERIAL PRIMARY KEY,   -- 6.9: bigserial
    component_id        UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    package_name        VARCHAR(100) NOT NULL,
    package_name_raw    VARCHAR(100),
    pin_count           INT,
    body_length_mm      FLOAT,
    body_width_mm       FLOAT,
    height_mm           FLOAT,
    pitch_mm            FLOAT,
    land_pattern_name   VARCHAR(100),
    kicad_footprint     VARCHAR(300),
    tscircuit_footprint VARCHAR(300),
    is_primary          BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_packages_component ON packages(component_id);
CREATE INDEX idx_packages_name ON packages(package_name);

-- SECTION 7 — Layout constraints
CREATE TABLE layout_constraints (
    id               BIGSERIAL PRIMARY KEY,   -- 6.9: bigserial
    component_id     UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    constraint_type  VARCHAR(50) NOT NULL,
    subject          VARCHAR(200),
    relative_to      VARCHAR(200),
    relative_to_type VARCHAR(50),
    max_distance_mm  FLOAT,
    min_distance_mm  FLOAT,
    layer            VARCHAR(20),
    hard             BOOLEAN DEFAULT TRUE,
    source_sentence  TEXT,
    confidence       FLOAT,
    source_document_id UUID REFERENCES documents(id)
);

CREATE INDEX idx_lc_component ON layout_constraints(component_id);

-- SECTION 8 — Component relationships
CREATE TABLE component_relationships (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_a_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL,
    -- equivalent | drop_in_replacement | functional_alternative
    -- recommended_pairing | incompatible | replaces | replaced_by
    component_b_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    is_symmetric      BOOLEAN NOT NULL DEFAULT FALSE,  -- 6.2: default FALSE
    confidence        FLOAT NOT NULL,                  -- 6.3: no default, must be explicit
    notes             TEXT,
    source            VARCHAR(200),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    CHECK (component_a_id != component_b_id),
    -- 6.2: symmetric relationships must match type
    CHECK (
        (relationship_type IN ('equivalent', 'functional_alternative', 'drop_in_replacement')
            AND is_symmetric = TRUE)
        OR (relationship_type IN ('replaces', 'replaced_by', 'recommended_pairing',
            'incompatible') AND is_symmetric = FALSE)
    ),
    -- 6.3: confidence must be in valid range
    CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX idx_cr_a ON component_relationships(component_a_id, relationship_type);
CREATE INDEX idx_cr_b ON component_relationships(component_b_id, relationship_type);

-- SECTION 9 — Design patterns
CREATE TABLE design_patterns (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name              VARCHAR(200) NOT NULL,
    description       TEXT,
    topology_type     VARCHAR(100),
    source_document_id UUID REFERENCES documents(id),
    key_equations     TEXT,
    performance_notes TEXT,
    methodology       VARCHAR(50),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE design_pattern_roles (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_id            UUID NOT NULL REFERENCES design_patterns(id) ON DELETE CASCADE,
    role_name             VARCHAR(200) NOT NULL,
    component_category    VARCHAR(200),
    specific_component_id UUID REFERENCES components(id),
    is_critical           BOOLEAN DEFAULT FALSE,
    selection_criteria    TEXT,
    typical_value         TEXT
);

CREATE INDEX idx_dp_topology ON design_patterns(topology_type);
CREATE INDEX idx_dpr_pattern ON design_pattern_roles(pattern_id);

-- SECTION 10 — Supplier cache
CREATE TABLE supplier_cache (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    supplier        VARCHAR(100) NOT NULL,
    supplier_part_no VARCHAR(150),
    status          VARCHAR(50) NOT NULL DEFAULT 'unknown',
    stock_count     INT,
    price_usd_1     FLOAT,
    price_usd_100   FLOAT,
    price_usd_1000  FLOAT,
    lead_time_weeks INT,
    snapshot_date   DATE NOT NULL,
    UNIQUE(component_id, supplier)
);

CREATE INDEX idx_supplier_component ON supplier_cache(component_id);
CREATE INDEX idx_supplier_status ON supplier_cache(status, supplier);

-- SECTION 11 — Embeddings
CREATE TABLE component_embeddings (
    component_id    UUID PRIMARY KEY REFERENCES components(id) ON DELETE CASCADE,
    embedding       VECTOR(4096),
    embedding_text  TEXT,
    model_name      VARCHAR(100),
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- IVFFlat index: do NOT create manually. Call check_and_create_ann_index()
-- from the ingestion pipeline after each batch. See migration 002.
-- lists = sqrt(row_count), minimum 10.

CREATE TABLE document_embeddings (
    document_id     UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    embedding       VECTOR(4096),
    chunk_text      TEXT,
    chunk_index     INT DEFAULT 0,
    model_name      VARCHAR(100),
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- SECTION 12 — Review queue
CREATE TABLE review_queue (
    item_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stage           VARCHAR(100) NOT NULL,
    component_id    UUID REFERENCES components(id),
    document_id     UUID REFERENCES documents(id),
    severity        VARCHAR(20) NOT NULL,
    verdict         VARCHAR(50),
    flags           JSONB,
    status          VARCHAR(50) DEFAULT 'pending',
    -- pending | claimed | resolved | rejected
    assigned_to     UUID,               -- 6.6: engineer UUID, no FK (no users table yet)
    priority        VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    -- CRITICAL | HIGH | MEDIUM | LOW
    due_at          TIMESTAMPTZ,        -- 6.6: SLA deadline
    claimed_at      TIMESTAMPTZ,        -- 6.6: when engineer claimed this item
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolution_notes TEXT
);

CREATE INDEX idx_rq_status ON review_queue(status, severity);
CREATE INDEX idx_rq_component ON review_queue(component_id)
    WHERE component_id IS NOT NULL;
CREATE INDEX idx_rq_assigned ON review_queue(assigned_to)
    WHERE assigned_to IS NOT NULL;
CREATE INDEX idx_rq_priority ON review_queue(priority, status)
    WHERE status = 'pending';

-- SECTION 13 — Stage 2 inference audit trail
CREATE TABLE stage2_inferences (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    intent_id               UUID NOT NULL,
    -- no FK: intent is in-memory during Stage 2, persisted by caller if needed
    axiom_id                VARCHAR(100),       -- which YAML axiom fired, if any
    requirement             TEXT NOT NULL,
    component_implication   VARCHAR(200),
    raw_confidence          FLOAT NOT NULL CHECK (raw_confidence >= 0 AND raw_confidence <= 1),
    calibrated_confidence   FLOAT CHECK (calibrated_confidence >= 0 AND calibrated_confidence <= 1),
    -- NULL until empirical calibration is built (post-v1)
    grounding_document_id   UUID REFERENCES documents(id),
    -- NULL = LLM-inferred with no grounded KB document
    source_topology         VARCHAR(100),       -- which topology YAML this came from
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_s2i_intent ON stage2_inferences(intent_id);
CREATE INDEX idx_s2i_axiom ON stage2_inferences(axiom_id)
    WHERE axiom_id IS NOT NULL;

CREATE TABLE stage2_inference_feedback (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    inference_id    UUID NOT NULL REFERENCES stage2_inferences(id) ON DELETE CASCADE,
    feedback_type   VARCHAR(50) NOT NULL,
    -- accepted | rejected | modified | false_positive | false_negative
    engineer_id     UUID,               -- no FK until users table exists
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_s2if_inference ON stage2_inference_feedback(inference_id);
CREATE INDEX idx_s2if_type ON stage2_inference_feedback(feedback_type);
