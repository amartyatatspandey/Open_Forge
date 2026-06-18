"""SQLite-backed offline supplier availability cache.

This module provides a local cache for supplier availability data.
Updated via periodic offline snapshots — never makes network calls at runtime.

Example:
    >>> from src.bom.supplier_cache import check_availability, AvailabilityStatus
    >>> from src.config import get_config
    >>> config = get_config()
    >>> status = check_availability("TPS62933", config)
    >>> if status == AvailabilityStatus.AVAILABLE:
    ...     print("Component is available")
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)


class AvailabilityStatus(str, Enum):
    """Supplier availability status for a component.

    Values:
        AVAILABLE: Component is in stock and available for purchase.
        UNAVAILABLE: Component is out of stock or discontinued.
        UNKNOWN: Component status is not in the cache.
    """

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"  # not in cache


def _ensure_cache_schema(db_path: Path) -> None:
    """Ensure the supplier_cache table exists.

    Creates the SQLite table with the required schema if it doesn't exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS supplier_cache (
                component_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                price_usd REAL,
                stock_count INTEGER,
                supplier TEXT,
                snapshot_date TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()


def check_availability(
    component_id: str,
    config: Config,
) -> AvailabilityStatus:
    """Query local SQLite cache for component availability.

    Returns UNKNOWN if component_id not found in cache.
    Never raises — returns UNKNOWN on any database error.

    Args:
        component_id: The component part number to check (e.g., "TPS62933").
        config: Application configuration with supplier_cache_path.

    Returns:
        AvailabilityStatus: AVAILABLE, UNAVAILABLE, or UNKNOWN.

    Example:
        >>> status = check_availability("TPS62933", config)
        >>> print(status)
        AvailabilityStatus.AVAILABLE
    """
    cache_path = getattr(config, "supplier_cache_path", Path("data/supplier_cache.db"))
    conn: sqlite3.Connection | None = None

    try:
        _ensure_cache_schema(cache_path)

        conn = sqlite3.connect(cache_path)
        cursor = conn.execute(
            "SELECT status FROM supplier_cache WHERE component_id = ?",
            (component_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row is None:
            return AvailabilityStatus.UNKNOWN

        status_str = row[0]
        try:
            return AvailabilityStatus(status_str)
        except ValueError:
            logger.warning(f"Invalid status in cache for {component_id}: {status_str}")
            return AvailabilityStatus.UNKNOWN

    except sqlite3.Error as e:
        logger.warning(f"Database error checking availability for {component_id}: {e}")
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        return AvailabilityStatus.UNKNOWN
    except Exception as e:
        logger.warning(f"Unexpected error checking availability for {component_id}: {e}")
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        return AvailabilityStatus.UNKNOWN


def upsert_availability(
    component_id: str,
    status: AvailabilityStatus,
    price_usd: Optional[float],
    stock_count: Optional[int],
    supplier: str,
    snapshot_date: str,
    config: Config,
) -> None:
    """Insert or update one component's availability data.

    Args:
        component_id: The component part number (e.g., "TPS62933").
        status: Availability status (AVAILABLE, UNAVAILABLE).
        price_usd: Price in USD, or None if unknown.
        stock_count: Number of units in stock, or None if unknown.
        supplier: Supplier name (e.g., "DigiKey", "Mouser").
        snapshot_date: ISO 8601 date string of when data was captured.
        config: Application configuration with supplier_cache_path.

    Raises:
        sqlite3.Error: If database operation fails.

    Example:
        >>> upsert_availability(
        ...     "TPS62933",
        ...     AvailabilityStatus.AVAILABLE,
        ...     1.50,
        ...     1000,
        ...     "DigiKey",
        ...     "2026-06-18",
        ...     config,
        ... )
    """
    cache_path = getattr(config, "supplier_cache_path", Path("data/supplier_cache.db"))

    _ensure_cache_schema(cache_path)

    updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    conn = sqlite3.connect(cache_path)
    try:
        conn.execute(
            """
            INSERT INTO supplier_cache
                (component_id, status, price_usd, stock_count, supplier, snapshot_date, updated_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(component_id) DO UPDATE SET
                status = excluded.status,
                price_usd = excluded.price_usd,
                stock_count = excluded.stock_count,
                supplier = excluded.supplier,
                snapshot_date = excluded.snapshot_date,
                updated_at = excluded.updated_at
        """,
            (component_id, status.value, price_usd, stock_count, supplier, snapshot_date, updated_at),
        )
        conn.commit()
    finally:
        conn.close()

    logger.debug(f"Updated supplier cache for {component_id}: {status.value}")


__all__ = [
    "AvailabilityStatus",
    "check_availability",
    "upsert_availability",
]