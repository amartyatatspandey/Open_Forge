"""Unit tests for src/review/queue.py.

Tests the SQLite-backed review queue including:
- Enqueue writes a row to SQLite
- list_pending returns only pending items
- update_status changes status and sets resolved_at
- export_corrections writes only corrected items
- get_item returns None for unknown item_id
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import Config
from src.datasheet.phase4_validate import ValidationResult
from src.review._schemas import ReviewQueueItem
from src.review.queue import (
    enqueue,
    export_corrections,
    get_item,
    list_pending,
    update_status,
)
from src.schemas.datasheet import ComponentDatasheet, ExtractionMethod


class TestEnqueue:
    """Tests for enqueue function."""

    @pytest.fixture
    def mock_config(self, tmp_path) -> Config:
        """Create mock Config with temp database path."""
        config = MagicMock(spec=Config)
        config.review_queue_path = tmp_path / "test_review.db"
        return config

    @pytest.fixture
    def sample_datasheet(self) -> ComponentDatasheet:
        """Create a sample ComponentDatasheet for testing."""
        return ComponentDatasheet(
            component_id="TPS62933",
            manufacturer="Texas Instruments",
            description="Buck Converter",
            package="SOT-23-5",
            source_pdf_hash="abc123hash",
            extraction_method=ExtractionMethod.P1_VECTOR,
            extraction_confidence=0.75,
            review_required=True,
            review_flags=["Low confidence", "Missing description"],
            created_at="2024-01-01T00:00:00Z",
        )

    @pytest.fixture
    def sample_validation_result(self) -> ValidationResult:
        """Create a sample ValidationResult."""
        return ValidationResult(
            verdict="WARN",
            severity="WARNING",
            confidence=0.75,
            flags=["Low confidence"],
        )

    def test_enqueue_writes_row_to_sqlite(
        self,
        mock_config,
        sample_datasheet,
        sample_validation_result,
    ) -> None:
        """Create temp SQLite file — test enqueue writes a row."""
        # Enqueue an item
        item = enqueue(sample_datasheet, sample_validation_result, mock_config)

        # Verify database file was created
        db_path = mock_config.review_queue_path
        assert db_path.exists()

        # Verify row was written by querying directly
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM review_queue WHERE item_id = ?", (item.item_id,))
            row = cursor.fetchone()

            assert row is not None
            assert row[0] == item.item_id
            assert row[1] == "phase4_validation"  # stage
            assert row[2] == "TPS62933"  # component_id
            assert row[4] == "WARNING"  # severity
            assert row[5] == "WARN"  # verdict

            # Verify flags are stored as JSON
            flags = json.loads(row[6])
            assert "Low confidence" in flags
            assert "Missing description" in flags
        finally:
            conn.close()

    def test_enqueue_returns_review_queue_item(
        self,
        mock_config,
        sample_datasheet,
        sample_validation_result,
    ) -> None:
        """Test enqueue returns a properly formed ReviewQueueItem."""
        item = enqueue(sample_datasheet, sample_validation_result, mock_config)

        assert isinstance(item, ReviewQueueItem)
        assert item.component_id == "TPS62933"
        assert item.stage == "phase4_validation"
        assert item.verdict == "WARN"
        assert item.severity == "WARNING"
        assert item.status == "pending"
        assert len(item.flags) == 2

    def test_enqueue_generates_unique_item_ids(
        self,
        mock_config,
        sample_datasheet,
        sample_validation_result,
    ) -> None:
        """Test that enqueue generates unique UUIDs for each item."""
        item1 = enqueue(sample_datasheet, sample_validation_result, mock_config)
        item2 = enqueue(sample_datasheet, sample_validation_result, mock_config)

        assert item1.item_id != item2.item_id
        assert len(item1.item_id) == 36  # Standard UUID length


class TestListPending:
    """Tests for list_pending function."""

    @pytest.fixture
    def mock_config(self, tmp_path) -> Config:
        """Create mock Config with temp database path."""
        config = MagicMock(spec=Config)
        config.review_queue_path = tmp_path / "test_review.db"
        return config

    @pytest.fixture
    def sample_datasheet(self) -> ComponentDatasheet:
        """Create a sample ComponentDatasheet."""
        return ComponentDatasheet(
            component_id="TEST",
            manufacturer="Test",
            description="Test",
            package="SOT-23-5",
            source_pdf_hash="hash",
            extraction_method=ExtractionMethod.P1_VECTOR,
            extraction_confidence=0.8,
            created_at="2024-01-01T00:00:00Z",
        )

    @pytest.fixture
    def sample_validation_result(self) -> ValidationResult:
        """Create a sample ValidationResult."""
        return ValidationResult(
            verdict="WARN",
            severity="WARNING",
            confidence=0.8,
            flags=[],
        )

    def test_list_pending_returns_only_pending_items(
        self,
        mock_config,
        sample_datasheet,
        sample_validation_result,
    ) -> None:
        """Test list_pending returns only pending items."""
        # Enqueue 3 items
        item1 = enqueue(sample_datasheet, sample_validation_result, mock_config)
        item2 = enqueue(sample_datasheet, sample_validation_result, mock_config)
        item3 = enqueue(sample_datasheet, sample_validation_result, mock_config)

        # Resolve one item
        update_status(item1.item_id, "approved", "Looks good", mock_config)

        # Get pending items
        pending = list_pending(mock_config)

        # Should only return 2 pending items
        assert len(pending) == 2

        # Verify correct items returned
        item_ids = {i.item_id for i in pending}
        assert item2.item_id in item_ids
        assert item3.item_id in item_ids
        assert item1.item_id not in item_ids

    def test_list_pending_orders_by_created_at_desc(
        self,
        mock_config,
        sample_datasheet,
        sample_validation_result,
    ) -> None:
        """Test list_pending orders by created_at descending (newest first)."""
        # Enqueue items with slight delay
        item1 = enqueue(sample_datasheet, sample_validation_result, mock_config)
        item2 = enqueue(sample_datasheet, sample_validation_result, mock_config)

        pending = list_pending(mock_config)

        # Newest should be first
        assert pending[0].item_id == item2.item_id
        assert pending[1].item_id == item1.item_id

    def test_list_pending_returns_empty_list_if_no_db(self, tmp_path) -> None:
        """Test list_pending returns empty list if database doesn't exist."""
        config = MagicMock(spec=Config)
        config.review_queue_path = tmp_path / "nonexistent.db"

        pending = list_pending(config)
        assert pending == []


class TestUpdateStatus:
    """Tests for update_status function."""

    @pytest.fixture
    def mock_config(self, tmp_path) -> Config:
        """Create mock Config with temp database path."""
        config = MagicMock(spec=Config)
        config.review_queue_path = tmp_path / "test_review.db"
        return config

    @pytest.fixture
    def sample_item(
        self,
        mock_config,
    ) -> ReviewQueueItem:
        """Create and return a sample enqueued item."""
        datasheet = ComponentDatasheet(
            component_id="TEST",
            manufacturer="Test",
            description="Test",
            package="SOT-23-5",
            source_pdf_hash="hash",
            extraction_method=ExtractionMethod.P1_VECTOR,
            extraction_confidence=0.8,
            created_at="2024-01-01T00:00:00Z",
        )
        validation = ValidationResult(
            verdict="WARN",
            severity="WARNING",
            confidence=0.8,
            flags=[],
        )
        return enqueue(datasheet, validation, mock_config)

    def test_update_status_changes_status_and_sets_resolved_at(
        self,
        mock_config,
        sample_item,
    ) -> None:
        """Test update_status changes status and sets resolved_at."""
        assert sample_item.status == "pending"
        assert sample_item.resolved_at is None

        # Update to approved
        updated = update_status(
            sample_item.item_id, "approved", "Approved by reviewer", mock_config
        )

        assert updated.status == "approved"
        assert updated.resolved_at is not None
        assert updated.resolution_notes == "Approved by reviewer"

    def test_update_status_returns_updated_item(
        self,
        mock_config,
        sample_item,
    ) -> None:
        """Test update_status returns the updated ReviewQueueItem."""
        updated = update_status(sample_item.item_id, "corrected", "Fixed package name", mock_config)

        assert isinstance(updated, ReviewQueueItem)
        assert updated.item_id == sample_item.item_id
        assert updated.component_id == sample_item.component_id
        assert updated.status == "corrected"

    def test_update_status_raises_on_unknown_item_id(self, mock_config) -> None:
        """Test update_status raises ValueError for unknown item_id."""
        with pytest.raises(ValueError) as exc_info:
            update_status("nonexistent-uuid", "approved", "notes", mock_config)

        assert "not found" in str(exc_info.value)

    def test_update_status_corrected_status(self, mock_config, sample_item) -> None:
        """Test update_status works with 'corrected' status."""
        updated = update_status(
            sample_item.item_id, "corrected", "Package changed to SOT-23-3", mock_config
        )

        assert updated.status == "corrected"
        assert updated.resolved_at is not None


class TestExportCorrections:
    """Tests for export_corrections function."""

    @pytest.fixture
    def mock_config(self, tmp_path) -> Config:
        """Create mock Config with temp database path."""
        config = MagicMock(spec=Config)
        config.review_queue_path = tmp_path / "test_review.db"
        return config

    @pytest.fixture
    def sample_datasheet(self) -> ComponentDatasheet:
        """Create a sample ComponentDatasheet."""
        return ComponentDatasheet(
            component_id="TEST",
            manufacturer="Test",
            description="Test",
            package="SOT-23-5",
            source_pdf_hash="hash",
            extraction_method=ExtractionMethod.P1_VECTOR,
            extraction_confidence=0.8,
            created_at="2024-01-01T00:00:00Z",
        )

    @pytest.fixture
    def sample_validation_result(self) -> ValidationResult:
        """Create a sample ValidationResult."""
        return ValidationResult(
            verdict="WARN",
            severity="WARNING",
            confidence=0.8,
            flags=[],
        )

    def test_export_corrections_writes_only_corrected_items(
        self,
        mock_config,
        sample_datasheet,
        sample_validation_result,
        tmp_path,
    ) -> None:
        """Test export_corrections writes only corrected items to JSONL."""
        # Enqueue 3 items
        item1 = enqueue(sample_datasheet, sample_validation_result, mock_config)
        item2 = enqueue(sample_datasheet, sample_validation_result, mock_config)
        item3 = enqueue(sample_datasheet, sample_validation_result, mock_config)

        # Mark 2 as corrected, 1 as approved
        update_status(item1.item_id, "corrected", "Fixed", mock_config)
        update_status(item2.item_id, "corrected", "Fixed again", mock_config)
        update_status(item3.item_id, "approved", "Good", mock_config)

        # Export to JSONL
        output_path = tmp_path / "corrections.jsonl"
        count = export_corrections(output_path, mock_config)

        # Should export only 2 corrected items
        assert count == 2
        assert output_path.exists()

        # Verify JSONL content
        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 2

        # Parse and verify
        for line in lines:
            data = json.loads(line)
            assert data["status"] == "corrected"
            assert data["item_id"] in [item1.item_id, item2.item_id]

    def test_export_corrections_returns_count(
        self,
        mock_config,
        sample_datasheet,
        sample_validation_result,
        tmp_path,
    ) -> None:
        """Test export_corrections returns count of exported items."""
        # Enqueue and correct 5 items
        for _ in range(5):
            item = enqueue(sample_datasheet, sample_validation_result, mock_config)
            update_status(item.item_id, "corrected", "Fixed", mock_config)

        output_path = tmp_path / "corrections.jsonl"
        count = export_corrections(output_path, mock_config)

        assert count == 5

    def test_export_corrections_creates_output_directory(
        self,
        mock_config,
        sample_datasheet,
        sample_validation_result,
        tmp_path,
    ) -> None:
        """Test export_corrections creates output directory if needed."""
        item = enqueue(sample_datasheet, sample_validation_result, mock_config)
        update_status(item.item_id, "corrected", "Fixed", mock_config)

        # Use nested path that doesn't exist
        output_path = tmp_path / "data" / "exports" / "corrections.jsonl"
        export_corrections(output_path, mock_config)

        assert output_path.exists()

    def test_export_corrections_returns_zero_if_no_db(self, tmp_path) -> None:
        """Test export_corrections returns 0 if database doesn't exist."""
        config = MagicMock(spec=Config)
        config.review_queue_path = tmp_path / "nonexistent.db"

        output_path = tmp_path / "corrections.jsonl"
        count = export_corrections(output_path, config)

        assert count == 0


class TestGetItem:
    """Tests for get_item function."""

    @pytest.fixture
    def mock_config(self, tmp_path) -> Config:
        """Create mock Config with temp database path."""
        config = MagicMock(spec=Config)
        config.review_queue_path = tmp_path / "test_review.db"
        return config

    @pytest.fixture
    def sample_item(self, mock_config) -> ReviewQueueItem:
        """Create and return a sample enqueued item."""
        datasheet = ComponentDatasheet(
            component_id="TEST",
            manufacturer="Test",
            description="Test",
            package="SOT-23-5",
            source_pdf_hash="hash",
            extraction_method=ExtractionMethod.P1_VECTOR,
            extraction_confidence=0.8,
            created_at="2024-01-01T00:00:00Z",
        )
        validation = ValidationResult(
            verdict="WARN",
            severity="WARNING",
            confidence=0.8,
            flags=[],
        )
        return enqueue(datasheet, validation, mock_config)

    def test_get_item_returns_item_by_id(self, mock_config, sample_item) -> None:
        """Test get_item returns ReviewQueueItem when found."""
        result = get_item(sample_item.item_id, mock_config)

        assert result is not None
        assert result.item_id == sample_item.item_id
        assert result.component_id == sample_item.component_id

    def test_get_item_returns_none_for_unknown_id(self, mock_config) -> None:
        """Test get_item returns None for unknown item_id."""
        result = get_item("nonexistent-uuid-1234", mock_config)

        assert result is None

    def test_get_item_returns_none_if_no_db(self, tmp_path) -> None:
        """Test get_item returns None if database doesn't exist."""
        config = MagicMock(spec=Config)
        config.review_queue_path = tmp_path / "nonexistent.db"

        result = get_item("any-id", config)
        assert result is None
