TASK
====
Implement DatasheetPostgresWriter — writes a ComponentDatasheet object
into the PostgreSQL relational schema defined in db/migrations/.

This closes the storage gap: right now parsed output only goes to the
NetworkX KG via p1_importer.py. This writer puts it into PostgreSQL
for parametric search, FTS, and pgvector semantic queries.

CONTEXT FILES TO READ
=====================
src/schemas/datasheet.py                    ← ComponentDatasheet + all sub-types
src/knowledge_graph/importers/p1_importer.py ← pattern to follow (KG writer)
documents/improvement_plan/04_DATABASE_SCHEMA.md ← PostgreSQL schema reference
db/migrations/001_initial_schema.sql        ← actual table definitions
configs/default.yaml                        ← config structure

FILES TO CREATE
===============
src/parsing/storage/__init__.py
src/parsing/storage/postgres_writer.py
src/parsing/storage/_mappers.py

FILES TO MODIFY
===============
configs/default.yaml                        ← add storage config block

DO NOT MODIFY
=============
db/migrations/001_initial_schema.sql
src/knowledge_graph/importers/p1_importer.py
Any existing test files

---

## BACKGROUND — WHY TWO STORES

Think of it like a library with two catalogues:

  KG (NetworkX/Neo4j) = relationship catalogue
      "What requires what", "what connects to what"
      Used by BOM generator to traverse design subgraphs

  PostgreSQL = specification catalogue
      "Give me all op-amps where noise < 5nV/√Hz and VCC < 3.3V"
      Used by retrieval engine for parametric search

Both get written after a successful parse. They are complementary, not redundant.

---

## src/parsing/storage/_mappers.py

Pure functions. No DB calls. No side effects.
Maps ComponentDatasheet sub-objects to dict rows
ready for psycopg2 executemany().

### map_component_row(datasheet: ComponentDatasheet) -> dict

Maps to: components table
Returns dict with keys:
    id:                  str(uuid4())  ← generate here, store for FK use
    manufacturer_id:     None          ← caller resolves; write NULL for now
    part_number:         datasheet.component_id
    part_number_clean:   datasheet.component_id.upper().replace(" ", "")
    part_number_base:    datasheet.component_id.split("-")[0].upper()
    description:         datasheet.description or ""
    lifecycle_status:    "active"
    ingestion_version:   datasheet.pipeline_version
    created_at:          datasheet.created_at
    updated_at:          datasheet.created_at

### map_electrical_parameter_rows(
        datasheet: ComponentDatasheet,
        component_uuid: str
    ) -> list[dict]

Maps datasheet.electrical_parameters (list[ElectricalParameter])
to: electrical_parameters table

For each ElectricalParameter, return dict with:
    id:                str(uuid4())
    component_id:      component_uuid
    parameter_name:    param.name
    symbol:            param.symbol or None
    section_type:      param.section_type.value if param.section_type else None
    conditions:        param.conditions or None
    value_min:         param.value.min if param.value else None
    value_typ:         param.value.typ if param.value else None
    value_max:         param.value.max if param.value else None
    unit:              param.value.unit if param.value else None
    unit_raw:          param.value.raw_text if param.value else None
    raw_text:          param.value.raw_text if param.value else None
    footnote:          param.value.footnote if param.value else None
    confidence:        param.value.confidence if param.value else 0.0
    extraction_method: datasheet.extraction_method.value
    source_page:       param.source_page or None
    source_table_index: param.source_table_index or None
    created_at:        datasheet.created_at

### map_absolute_max_rows(
        datasheet: ComponentDatasheet,
        component_uuid: str
    ) -> list[dict]

Maps datasheet.absolute_max_ratings (list[AbsoluteMaxRating])
Same table: electrical_parameters
section_type forced to: "absolute_maximum_ratings"
Same field mapping as electrical parameters above.
value_min = None (abs-max entries have only a max value)
value_typ = None
value_max = rating.value.value if rating.value else None

### map_pin_rows(
        datasheet: ComponentDatasheet,
        component_uuid: str
    ) -> list[dict]

Maps datasheet.pins (list[PinDefinition])
to: component_pins table

For each PinDefinition:
    id:               str(uuid4())
    component_id:     component_uuid
    pin_number:       pin.pin_number
    pin_name:         pin.raw_name or f"Pin {pin.pin_number}"
    pin_type:         pin.pin_type or None
    description:      pin.description or None
    alternate_functions: json.dumps(pin.alternate_functions or [])
    created_at:       datasheet.created_at

### map_layout_constraint_rows(
        datasheet: ComponentDatasheet,
        component_uuid: str
    ) -> list[dict]

Maps datasheet.layout_constraints or [] (list[PlacementConstraint])
to: layout_constraints table

For each PlacementConstraint:
    id:               str(uuid4())
    component_id:     component_uuid
    constraint_type:  constraint.constraint_type
    subject:          constraint.subject
    relative_to:      constraint.relative_to
    relative_to_type: constraint.relative_to_type
    max_distance_mm:  constraint.max_distance_mm or None
    min_distance_mm:  constraint.min_distance_mm or None
    layer:            constraint.layer or None
    hard:             constraint.hard
    source_sentence:  constraint.source_sentence or None
    confidence:       constraint.confidence

### map_document_row(
        datasheet: ComponentDatasheet,
        component_uuid: str
    ) -> dict

Maps to: documents table
    id:               str(uuid4())  ← store for component_documents FK
    title:            f"{datasheet.component_id} Datasheet"
    doc_type:         "datasheet"
    file_hash:        datasheet.source_pdf_hash
    ingestion_status: "complete"
    ingestion_version: datasheet.pipeline_version
    ingested_at:      datasheet.created_at

---

## src/parsing/storage/postgres_writer.py

Class: DatasheetPostgresWriter

Constructor: __init__(self, config: Config)
    Reads from config:
        storage.postgres_dsn: str   ← e.g. "postgresql://user:pass@localhost/openforge"
    self._dsn = postgres_dsn
    self._conn = None   ← lazy

Method: _get_conn(self)
    If self._conn is None or self._conn.closed:
        import psycopg2
        self._conn = psycopg2.connect(self._dsn)
    Return self._conn

Method: write(self, datasheet: ComponentDatasheet) -> WriteResult
    Idempotent: if component with same part_number already exists,
    DELETE its child rows and re-insert. Use ON CONFLICT DO UPDATE
    on components table, DELETE+INSERT on child tables.

    Step 1: Map all rows using _mappers functions
        component_row = map_component_row(datasheet)
        component_uuid = component_row["id"]
        param_rows     = map_electrical_parameter_rows(datasheet, component_uuid)
        abs_max_rows   = map_absolute_max_rows(datasheet, component_uuid)
        pin_rows       = map_pin_rows(datasheet, component_uuid)
        constraint_rows= map_layout_constraint_rows(datasheet, component_uuid)
        doc_row        = map_document_row(datasheet, component_uuid)

    Step 2: Write in a single transaction
        conn = self._get_conn()
        with conn:
            cur = conn.cursor()

            # Upsert component (ON CONFLICT on part_number_clean)
            cur.execute(INSERT INTO components ... ON CONFLICT (part_number_clean)
                        DO UPDATE SET updated_at=NOW(), description=EXCLUDED.description,
                        ingestion_version=EXCLUDED.ingestion_version
                        RETURNING id)
            actual_uuid = cur.fetchone()[0]
            ← use actual_uuid for all child inserts (handles conflict case)

            # Delete existing child rows for this component
            cur.execute("DELETE FROM electrical_parameters WHERE component_id=%s",
                        (actual_uuid,))
            cur.execute("DELETE FROM component_pins WHERE component_id=%s",
                        (actual_uuid,))
            cur.execute("DELETE FROM layout_constraints WHERE component_id=%s",
                        (actual_uuid,))

            # Bulk insert child rows
            if param_rows + abs_max_rows:
                psycopg2.extras.execute_batch(cur,
                    INSERT INTO electrical_parameters ...,
                    param_rows + abs_max_rows
                )
            if pin_rows:
                psycopg2.extras.execute_batch(cur,
                    INSERT INTO component_pins ...,
                    pin_rows
                )
            if constraint_rows:
                psycopg2.extras.execute_batch(cur,
                    INSERT INTO layout_constraints ...,
                    constraint_rows
                )

            # Insert document (ON CONFLICT on file_hash DO NOTHING)
            cur.execute(INSERT INTO documents ... ON CONFLICT (file_hash) DO NOTHING)

    Step 3: Return WriteResult
        DatasheetWriteResult(
            component_id=datasheet.component_id,
            postgres_uuid=actual_uuid,
            parameters_written=len(param_rows) + len(abs_max_rows),
            pins_written=len(pin_rows),
            constraints_written=len(constraint_rows),
            success=True,
            errors=[],
        )

    Error handling:
        Any psycopg2 error → rollback, log, return WriteResult(success=False,
        errors=[str(e)]). Never raise.

Method: close(self)
    If self._conn and not self._conn.closed:
        self._conn.close()

### WriteResult schema (define in postgres_writer.py)

class DatasheetWriteResult(BaseModel):
    component_id:         str
    postgres_uuid:        Optional[str]
    parameters_written:   int = 0
    pins_written:         int = 0
    constraints_written:  int = 0
    success:              bool
    errors:               list[str] = []

---

## src/parsing/storage/__init__.py

Export DatasheetPostgresWriter and DatasheetWriteResult only.

---

## configs/default.yaml addition

Under existing config add:

storage:
  postgres_dsn: "postgresql://openforge:openforge@localhost:5432/openforge"

---

GATE TESTS
==========
File: tests/unit/parsing/test_postgres_writer.py

All tests mock psycopg2. No real database needed.

Test 1: map_component_row produces correct part_number_clean
    datasheet.component_id = "TPS62933 DRLR"
    row = map_component_row(datasheet)
    Assert: row["part_number_clean"] == "TPS62933DRLR"
    Assert: row["part_number_base"] == "TPS62933"

Test 2: map_electrical_parameter_rows length matches datasheet
    datasheet with 3 electrical_parameters + 2 absolute_max_ratings
    param_rows = map_electrical_parameter_rows(datasheet, "uuid-123")
    abs_rows   = map_absolute_max_rows(datasheet, "uuid-123")
    Assert: len(param_rows) == 3
    Assert: len(abs_rows) == 2
    Assert: all rows have component_id == "uuid-123"

Test 3: map_absolute_max_rows forces section_type
    abs_rows = map_absolute_max_rows(datasheet, "uuid")
    Assert: all(r["section_type"] == "absolute_maximum_ratings" for r in abs_rows)
    Assert: all(r["value_min"] is None for r in abs_rows)

Test 4: map_pin_rows alternate_functions is JSON string
    pin with alternate_functions=["GPIO", "SPI_CLK"]
    row = map_pin_rows(datasheet, "uuid")[0]
    import json
    Assert: json.loads(row["alternate_functions"]) == ["GPIO", "SPI_CLK"]

Test 5: write() calls execute_batch for parameters
    Mock psycopg2.connect and cursor
    datasheet with 2 electrical_parameters, 1 pin, 0 constraints
    writer.write(datasheet)
    Assert: execute_batch called for electrical_parameters
    Assert: execute_batch called for component_pins
    Assert: DELETE statements executed before inserts

Test 6: write() returns success=False on psycopg2 error
    Mock cursor.execute to raise psycopg2.OperationalError("conn refused")
    result = writer.write(datasheet)
    Assert: result.success == False
    Assert: len(result.errors) == 1
    Assert no exception raised from write()

Test 7: write() is idempotent — DELETE before INSERT
    Capture all SQL strings executed via mock
    Assert: "DELETE FROM electrical_parameters" appears before
            any INSERT INTO electrical_parameters

Test 8: DatasheetPostgresWriter connection is lazy
    After __init__, self._conn is None
    psycopg2.connect not called at construction time

CONSTRAINTS
===========
- psycopg2 imported only inside methods — never at module top level
- All mapper functions are pure — no DB access, no side effects
- WriteResult uses Pydantic v2
- Python 3.11+
- Idempotent writes — safe to call twice on same datasheet