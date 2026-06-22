# OpenForge Backup and Disaster Recovery Strategy

## PostgreSQL Backup (air-gapped compatible)

### Streaming Replication (hot standby)
- Configure one hot standby PostgreSQL node.
- Failover time: ~30 seconds with automatic promotion.
- Required for any production DRDO deployment.

### WAL Archiving
- Archive WAL segments to local NVMe (primary) or MinIO (air-gapped S3-compatible).
- MinIO configuration for air-gapped:
  ```
  MINIO_ENDPOINT=http://minio.local:9000
  MINIO_BUCKET=openforge-wal
  ARCHIVE_COMMAND=mc cp %p minio/openforge-wal/%f
  ```
- Retention: 30 days of WAL + daily base backups.

### Base Backups
- `pg_basebackup` nightly to local NVMe and replicated to standby.
- Verify backup integrity weekly with `pg_verifybackup`.

### DR Drills
- Quarterly: restore from backup to an isolated instance,
  run schema_validator.py, run full test suite.
- Document restore time. Target RTO: < 2 hours.

## Knowledge Base (component data)

- The KB is reconstructible from source datasheets + ingestion pipeline.
- Back up raw PDF corpus separately (cold storage, quarterly).
- Priority: back up PostgreSQL — it contains the extracted parameters
  that took compute to produce.

## Embedding Index

- `component_embeddings` table is backed up with PostgreSQL.
- If lost, regenerate by re-running the embedding pipeline over all
  components. With Qwen3-Embedding-8B Q4, estimate ~1 sec/component.
  10K components = ~3 hours on single GPU.
