"""
Gate tests for 001_initial_schema.sql.
No live DB required — validates the SQL file content directly.
"""
import re
from pathlib import Path

MIGRATION_PATH = Path(__file__).parent.parent.parent / "db" / "migrations" / "001_initial_schema.sql"
MIGRATION_SQL = MIGRATION_PATH.read_text()


def test_migration_file_exists():
    assert MIGRATION_PATH.exists(), "001_initial_schema.sql not found"


def test_fix_61_btree_index_exists():
    assert "idx_ep_typ_lookup" in MIGRATION_SQL, \
        "B-tree index idx_ep_typ_lookup missing (fix 6.1)"


def test_fix_61_gist_index_preserved():
    assert "idx_ep_value_range" in MIGRATION_SQL, \
        "GIST range index idx_ep_value_range missing (fix 6.1)"


def test_fix_62_is_symmetric_default_false():
    assert re.search(
        r"is_symmetric\s+BOOLEAN\s+NOT NULL\s+DEFAULT\s+FALSE",
        MIGRATION_SQL, re.IGNORECASE
    ), "is_symmetric DEFAULT FALSE not found (fix 6.2)"


def test_fix_62_symmetry_check_constraint():
    assert "relationship_type IN ('equivalent'" in MIGRATION_SQL and \
           "is_symmetric = TRUE" in MIGRATION_SQL, \
        "Symmetry CHECK constraint missing (fix 6.2)"


def test_fix_63_confidence_no_default():
    # confidence must appear as NOT NULL without DEFAULT
    assert re.search(
        r"confidence\s+FLOAT\s+NOT NULL[^,\n]*(?!DEFAULT)",
        MIGRATION_SQL
    ) or "confidence        FLOAT NOT NULL," in MIGRATION_SQL, \
        "confidence NOT NULL without DEFAULT missing (fix 6.3)"


def test_fix_65_pin_function_vocabulary_table():
    assert "CREATE TABLE pin_function_vocabulary" in MIGRATION_SQL, \
        "pin_function_vocabulary table missing (fix 6.5)"


def test_fix_65_vocabulary_seeded():
    assert "POWER_POSITIVE" in MIGRATION_SQL and "SPI_CLOCK" in MIGRATION_SQL, \
        "pin_function_vocabulary not seeded (fix 6.5)"


def test_fix_66_review_queue_ownership_columns():
    for col in ["assigned_to", "priority", "due_at", "claimed_at"]:
        assert col in MIGRATION_SQL, \
            f"review_queue.{col} missing (fix 6.6)"


def test_fix_67_document_files_table():
    assert "CREATE TABLE document_files" in MIGRATION_SQL, \
        "document_files table missing (fix 6.7)"


def test_fix_67_unique_file_hash_removed():
    # UNIQUE(file_hash) must NOT appear in the documents table definition
    # Find the documents table block and check
    doc_table_match = re.search(
        r"CREATE TABLE documents\s*\((.+?)\);",
        MIGRATION_SQL, re.DOTALL
    )
    assert doc_table_match, "documents table not found"
    doc_body = doc_table_match.group(1)
    assert "UNIQUE(file_hash)" not in doc_body and \
           "UNIQUE (file_hash)" not in doc_body, \
        "UNIQUE(file_hash) still present in documents table (fix 6.7)"


def test_fix_68_fts_index_on_raw_text():
    assert "idx_ep_raw_text_fts" in MIGRATION_SQL, \
        "FTS index idx_ep_raw_text_fts missing (fix 6.8)"


def test_fix_69_electrical_parameters_bigserial():
    assert re.search(
        r"CREATE TABLE electrical_parameters\s*\(\s*id\s+BIGSERIAL",
        MIGRATION_SQL, re.IGNORECASE
    ), "electrical_parameters.id not BIGSERIAL (fix 6.9)"


def test_fix_69_pins_bigserial():
    assert re.search(
        r"CREATE TABLE pins\s*\(\s*id\s+BIGSERIAL",
        MIGRATION_SQL, re.IGNORECASE
    ), "pins.id not BIGSERIAL (fix 6.9)"


def test_fix_610_stage2_inferences_table():
    assert "CREATE TABLE stage2_inferences" in MIGRATION_SQL, \
        "stage2_inferences table missing (fix 6.10)"


def test_fix_610_stage2_feedback_table():
    assert "CREATE TABLE stage2_inference_feedback" in MIGRATION_SQL, \
        "stage2_inference_feedback table missing (fix 6.10)"


def test_fix_54_valid_from_column():
    assert "valid_from" in MIGRATION_SQL, \
        "electrical_parameters.valid_from missing (parameter versioning, fix 5.4)"


def test_fix_53_extraction_status_column():
    assert "extraction_status" in MIGRATION_SQL, \
        "electrical_parameters.extraction_status missing (QA gate, fix 5.3)"


def test_ann_helper_migration_exists():
    helper_path = MIGRATION_PATH.parent / "002_ann_index_helper.sql"
    assert helper_path.exists(), "002_ann_index_helper.sql not found"
    assert "check_and_create_ann_index" in helper_path.read_text(), \
        "check_and_create_ann_index function missing from migration 002"
