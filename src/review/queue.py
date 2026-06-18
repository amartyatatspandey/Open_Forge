"""SQLite-backed review queue implementation.

Provides persistent storage for review queue items using SQLite.
All functions open and close their own connections — no connection pooling.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, cast

from src.datasheet.phase4_validate import ValidationResult
from src.review._schemas import ReviewQueueItem
from src.config import Config
from src.schemas.datasheet import ComponentDatasheet
from src.schemas.intent import ValidatedBOM
from src.schemas.nir import NIR

logger = logging.getLogger(__name__)

# SQL schema for review queue table
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS review_queue (
    item_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    component_id TEXT NOT NULL,
    pdf_path TEXT NOT NULL,
    severity TEXT NOT NULL,
    verdict TEXT NOT NULL,
    flags TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_at TEXT,
    resolution_notes TEXT
)
"""


def _get_db_path(config: Config) -> Path:
    """Get the SQLite database path from config.

    Args:
        config: Application configuration

    Returns:
        Path to the SQLite database file
    """
    # Use review_queue_path from config, or default to output_dir
    if hasattr(config, "review_queue_path") and config.review_queue_path:
        return config.review_queue_path

    # Default to output_dir/review_queue.db
    if hasattr(config, "output_dir") and config.output_dir:
        return Path(config.output_dir) / "review_queue.db"

    # Fallback to current directory
    return Path("review_queue.db")


def _init_db(db_path: Path) -> None:
    """Initialize the SQLite database with review queue table.

    Args:
        db_path: Path to the SQLite database file
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


def _row_to_item(
    row: tuple[
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str | None,
        str | None,
    ],
) -> ReviewQueueItem:
    """Convert a database row to a ReviewQueueItem.

    Args:
        row: Database row tuple

    Returns:
        ReviewQueueItem from the row data
    """
    return ReviewQueueItem(
        item_id=row[0],
        stage=row[1],
        component_id=row[2],
        pdf_path=row[3],
        severity=cast(Literal["CRITICAL", "WARNING"], row[4]),
        verdict=row[5],
        flags=json.loads(row[6]),
        created_at=row[7],
        status=cast(Literal["pending", "approved", "corrected", "rejected"], row[8]),
        resolved_at=row[9],
        resolution_notes=row[10],
    )


def enqueue(
    datasheet: ComponentDatasheet,
    validation_result: ValidationResult,
    config: Config,
) -> ReviewQueueItem:
    """Write a pending review item to the SQLite queue.

    Creates a new ReviewQueueItem from the datasheet and validation result,
    persists it to the SQLite queue, and returns the created item.

    Args:
        datasheet: ComponentDatasheet with review flags
        validation_result: ValidationResult with verdict and severity
        config: Application configuration with queue database path

    Returns:
        The created ReviewQueueItem with generated item_id

    Example:
        >>> item = enqueue(datasheet, validation_result, config)
        >>> item.component_id
        'TPS62933DRLR'
        >>> item.status
        'pending'
    """
    db_path = _get_db_path(config)
    _init_db(db_path)

    # Create the queue item
    item = ReviewQueueItem(
        stage="phase4_validation",
        component_id=datasheet.component_id or "unknown",
        pdf_path=str(datasheet.source_pdf_hash),  # Using hash as identifier
        severity=cast(Literal["CRITICAL", "WARNING"], validation_result.severity),
        verdict=validation_result.verdict,
        flags=datasheet.review_flags,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO review_queue
            (item_id, stage, component_id, pdf_path, severity, verdict, flags, created_at, status, resolved_at, resolution_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.item_id,
                item.stage,
                item.component_id,
                item.pdf_path,
                item.severity,
                item.verdict,
                json.dumps(item.flags),
                item.created_at,
                item.status,
                item.resolved_at,
                item.resolution_notes,
            ),
        )
        conn.commit()
        logger.info(f"Enqueued review item {item.item_id[:8]}... for {item.component_id}")
    finally:
        conn.close()

    return item


def _write_item(
    stage: str,
    component_id: str,
    pdf_path: str,
    severity: Literal["CRITICAL", "WARNING"],
    verdict: str,
    flags: list[str],
    config: Config,
) -> ReviewQueueItem:
    """Write a review queue item to SQLite."""
    db_path = _get_db_path(config)
    _init_db(db_path)

    item = ReviewQueueItem(
        stage=stage,
        component_id=component_id,
        pdf_path=pdf_path,
        severity=severity,
        verdict=verdict,
        flags=flags,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO review_queue
            (item_id, stage, component_id, pdf_path, severity, verdict, flags, created_at, status, resolved_at, resolution_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.item_id,
                item.stage,
                item.component_id,
                item.pdf_path,
                item.severity,
                item.verdict,
                json.dumps(item.flags),
                item.created_at,
                item.status,
                item.resolved_at,
                item.resolution_notes,
            ),
        )
        conn.commit()
        logger.info(f"Enqueued review item {item.item_id[:8]}... for {item.component_id}")
    finally:
        conn.close()

    return item


def enqueue_bom(bom: ValidatedBOM, config: Config) -> ReviewQueueItem:
    """Write BOM review item to queue with stage='bom_generation'."""
    severity: Literal["CRITICAL", "WARNING"] = (
        "CRITICAL" if any("CRITICAL" in f for f in bom.review_flags) else "WARNING"
    )
    return _write_item(
        stage="bom_generation",
        component_id=bom.design_id,
        pdf_path="N/A",
        severity=severity,
        verdict="REVIEW_REQUIRED",
        flags=bom.review_flags,
        config=config,
    )


def enqueue_nir(nir: NIR, config: Config) -> ReviewQueueItem:
    """Write NIR review item to queue with stage='nir_validation'."""
    severity: Literal["CRITICAL", "WARNING"] = (
        "CRITICAL" if nir.is_review_required() else "WARNING"
    )
    flags = [f"{flag.severity}: {flag.reason}" for flag in nir.review_flags]
    return _write_item(
        stage="nir_validation",
        component_id=nir.design_id,
        pdf_path="N/A",
        severity=severity,
        verdict="REVIEW_REQUIRED",
        flags=flags,
        config=config,
    )


def list_pending(config: Config) -> list[ReviewQueueItem]:
    """Return all items with status == 'pending', ordered by created_at desc.

    Args:
        config: Application configuration with queue database path

    Returns:
        List of pending ReviewQueueItem objects, newest first

    Example:
        >>> pending = list_pending(config)
        >>> len(pending)
        5
        >>> pending[0].status
        'pending'
    """
    db_path = _get_db_path(config)

    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM review_queue
            WHERE status = 'pending'
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()
        return [_row_to_item(row) for row in rows]
    finally:
        conn.close()


def get_item(item_id: str, config: Config) -> Optional[ReviewQueueItem]:
    """Fetch a single item by item_id.

    Args:
        item_id: Unique UUID of the item to fetch
        config: Application configuration with queue database path

    Returns:
        ReviewQueueItem if found, None otherwise

    Example:
        >>> item = get_item("550e8400-e29b-41d4-a716-446655440000", config)
        >>> item.component_id if item else "not found"
        'TPS62933DRLR'
    """
    db_path = _get_db_path(config)

    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM review_queue WHERE item_id = ?", (item_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        return _row_to_item(row)
    finally:
        conn.close()


def update_status(
    item_id: str,
    status: str,
    resolution_notes: str,
    config: Config,
) -> ReviewQueueItem:
    """Update item status and set resolved_at = now().

    Args:
        item_id: Unique UUID of the item to update
        status: New status (approved, corrected, rejected)
        resolution_notes: Human-entered notes about the resolution
        config: Application configuration with queue database path

    Returns:
        Updated ReviewQueueItem

    Raises:
        ValueError: If item_id not found in queue

    Example:
        >>> item = update_status(item_id, "approved", "Looks good", config)
        >>> item.status
        'approved'
        >>> item.resolved_at is not None
        True
    """
    db_path = _get_db_path(config)

    if not db_path.exists():
        raise ValueError(f"Item {item_id} not found in queue")

    resolved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # First check if item exists
        cursor.execute("SELECT 1 FROM review_queue WHERE item_id = ?", (item_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Item {item_id} not found in queue")

        cursor.execute(
            """
            UPDATE review_queue
            SET status = ?, resolved_at = ?, resolution_notes = ?
            WHERE item_id = ?
            """,
            (status, resolved_at, resolution_notes, item_id),
        )
        conn.commit()

        # Fetch and return the updated item
        cursor.execute("SELECT * FROM review_queue WHERE item_id = ?", (item_id,))
        row = cursor.fetchone()
        item = _row_to_item(row)

        logger.info(f"Updated review item {item_id[:8]}... status to {status}")
        return item
    finally:
        conn.close()


def export_corrections(output_path: Path, config: Config) -> int:
    """Export all items with status='corrected' to JSONL at output_path.

    Used for fine-tuning corpus generation. Each line is a JSON object
    with the correction data.

    Args:
        output_path: Path to write the JSONL file
        config: Application configuration with queue database path

    Returns:
        Count of exported items

    Example:
        >>> count = export_corrections(Path("corrections.jsonl"), config)
        >>> print(f"Exported {count} corrections")
        Exported 42 items to data/corrections_export.jsonl
    """
    db_path = _get_db_path(config)

    if not db_path.exists():
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM review_queue
            WHERE status = 'corrected'
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()

        items = [_row_to_item(row) for row in rows]
    finally:
        conn.close()

    # Write to JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for item in items:
            # Write as JSON lines format
            f.write(item.model_dump_json() + "\n")

    logger.info(f"Exported {len(items)} corrected items to {output_path}")
    return len(items)
