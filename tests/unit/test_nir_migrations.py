"""Unit tests for NIR schema migration utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.nir.migrations import CURRENT_NIR_VERSION, check_version, migrate


def test_migrate_returns_dict_unchanged_when_current_version() -> None:
    nir_dict = {"schema_version": "1.0", "design_id": "test"}
    result = migrate(nir_dict)
    assert result is nir_dict  # same object, no copy needed


def test_migrate_assumes_1_0_when_version_missing() -> None:
    nir_dict = {"design_id": "test"}  # no schema_version key
    result = migrate(nir_dict)
    assert result is nir_dict


def test_migrate_raises_on_unknown_version() -> None:
    nir_dict = {"schema_version": "99.0"}
    with pytest.raises(ValueError, match="Unknown NIR schema version"):
        migrate(nir_dict)


def test_check_version_passes_for_current_version() -> None:
    nir = MagicMock()
    nir.schema_version = CURRENT_NIR_VERSION
    check_version(nir)  # must not raise


def test_check_version_raises_for_wrong_version() -> None:
    nir = MagicMock()
    nir.schema_version = "0.9"
    with pytest.raises(ValueError, match="NIR schema version mismatch"):
        check_version(nir)
