-- Call this function from the ingestion pipeline after every batch insert.
-- It creates or rebuilds the IVFFlat ANN index only when the row count
-- justifies it (>= 10,000 rows). Safe to call repeatedly — it is a no-op
-- below threshold or if the index is already current.

CREATE OR REPLACE FUNCTION check_and_create_ann_index() RETURNS TEXT AS $$
DECLARE
    row_count   BIGINT;
    lists_count INT;
    index_exists BOOLEAN;
BEGIN
    SELECT COUNT(*) INTO row_count FROM component_embeddings;

    IF row_count < 10000 THEN
        RETURN FORMAT('ANN index not created: only %s rows (need >= 10000)', row_count);
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'component_embeddings'
          AND indexname = 'idx_embeddings_ann'
    ) INTO index_exists;

    -- lists = sqrt(row_count), minimum 10, maximum 1000
    lists_count := GREATEST(10, LEAST(1000, FLOOR(SQRT(row_count::FLOAT))::INT));

    IF index_exists THEN
        DROP INDEX CONCURRENTLY IF EXISTS idx_embeddings_ann;
    END IF;

    EXECUTE FORMAT(
        'CREATE INDEX idx_embeddings_ann ON component_embeddings '
        'USING ivfflat (embedding vector_cosine_ops) WITH (lists = %s)',
        lists_count
    );

    RETURN FORMAT('ANN index created with lists=%s for %s rows', lists_count, row_count);
END;
$$ LANGUAGE plpgsql;
