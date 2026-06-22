"""
Schema validator for OpenForge DB migration 001.
Connects to PostgreSQL and asserts all 9 GLM corrections are present.

Usage:
    DATABASE_URL=postgresql://user:pass@localhost/openforge \
    python open_forge/db/schema_validator.py
"""
import os
import sys
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    return psycopg2.connect(DATABASE_URL)


def check(label: str, query: str, expected: bool, conn) -> bool:
    cur = conn.cursor()
    cur.execute(query)
    result = cur.fetchone()[0]
    passed = bool(result) == expected
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {label}")
    return passed


def main():
    conn = get_conn()
    results = []

    print("\n=== OpenForge Schema Validation ===\n")

    # 6.1 — B-tree index on (symbol, unit, value_typ) exists
    results.append(check(
        "6.1: B-tree idx_ep_typ_lookup exists",
        "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_ep_typ_lookup'",
        True, conn
    ))

    # 6.1 — GIST range index still present (for true range queries)
    results.append(check(
        "6.1: GIST idx_ep_value_range exists",
        "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_ep_value_range'",
        True, conn
    ))

    # 6.2 — is_symmetric DEFAULT FALSE
    results.append(check(
        "6.2: component_relationships.is_symmetric default is FALSE",
        """SELECT column_default = 'false'
           FROM information_schema.columns
           WHERE table_name = 'component_relationships'
             AND column_name = 'is_symmetric'""",
        True, conn
    ))

    # 6.3 — confidence has NO default (NULL)
    results.append(check(
        "6.3: component_relationships.confidence has no default",
        """SELECT column_default IS NULL
           FROM information_schema.columns
           WHERE table_name = 'component_relationships'
             AND column_name = 'confidence'""",
        True, conn
    ))

    # 6.5 — pin_function_vocabulary table exists with rows
    results.append(check(
        "6.5: pin_function_vocabulary exists and is seeded",
        "SELECT COUNT(*) >= 10 FROM pin_function_vocabulary",
        True, conn
    ))

    # 6.5 — pins.normalized_function has FK to vocabulary
    results.append(check(
        "6.5: pins.normalized_function FK to pin_function_vocabulary exists",
        """SELECT COUNT(*) FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
           WHERE tc.table_name = 'pins'
             AND tc.constraint_type = 'FOREIGN KEY'
             AND kcu.column_name = 'normalized_function'""",
        True, conn
    ))

    # 6.6 — review_queue has assigned_to column
    results.append(check(
        "6.6: review_queue.assigned_to column exists",
        """SELECT COUNT(*) FROM information_schema.columns
           WHERE table_name = 'review_queue'
             AND column_name = 'assigned_to'""",
        True, conn
    ))

    # 6.7 — documents.file_hash is NOT UNIQUE (unique constraint removed)
    results.append(check(
        "6.7: documents.file_hash UNIQUE constraint removed",
        """SELECT COUNT(*) = 0 FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
           WHERE tc.table_name = 'documents'
             AND tc.constraint_type = 'UNIQUE'
             AND kcu.column_name = 'file_hash'""",
        True, conn
    ))

    # 6.7 — document_files table exists
    results.append(check(
        "6.7: document_files table exists",
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'document_files'",
        True, conn
    ))

    # 6.8 — FTS index on electrical_parameters raw_text
    results.append(check(
        "6.8: idx_ep_raw_text_fts GIN index exists",
        "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_ep_raw_text_fts'",
        True, conn
    ))

    # 6.9 — electrical_parameters PK is bigserial (integer type)
    results.append(check(
        "6.9: electrical_parameters.id is bigint (bigserial)",
        """SELECT data_type = 'bigint'
           FROM information_schema.columns
           WHERE table_name = 'electrical_parameters'
             AND column_name = 'id'""",
        True, conn
    ))

    # 6.9 — pins PK is bigserial
    results.append(check(
        "6.9: pins.id is bigint (bigserial)",
        """SELECT data_type = 'bigint'
           FROM information_schema.columns
           WHERE table_name = 'pins'
             AND column_name = 'id'""",
        True, conn
    ))

    # 6.10 — stage2_inferences table exists
    results.append(check(
        "6.10: stage2_inferences table exists",
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'stage2_inferences'",
        True, conn
    ))

    # 6.10 — stage2_inference_feedback table exists
    results.append(check(
        "6.10: stage2_inference_feedback table exists",
        """SELECT COUNT(*) FROM information_schema.tables
           WHERE table_name = 'stage2_inference_feedback'""",
        True, conn
    ))

    # 5.4 — electrical_parameters has valid_from column
    results.append(check(
        "5.4: electrical_parameters.valid_from exists (parameter versioning)",
        """SELECT COUNT(*) FROM information_schema.columns
           WHERE table_name = 'electrical_parameters'
             AND column_name = 'valid_from'""",
        True, conn
    ))

    # 5.4 — extraction_status column exists (QA gate)
    results.append(check(
        "5.3: electrical_parameters.extraction_status exists (QA gate)",
        """SELECT COUNT(*) FROM information_schema.columns
           WHERE table_name = 'electrical_parameters'
             AND column_name = 'extraction_status'""",
        True, conn
    ))

    conn.close()

    passed = sum(results)
    total = len(results)
    print(f"\n=== {passed}/{total} checks passed ===")

    if passed == total:
        print("SCHEMA VALIDATION: PASS")
        sys.exit(0)
    else:
        print("SCHEMA VALIDATION: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
