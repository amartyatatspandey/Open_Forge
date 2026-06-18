"""
NIR schema migration utilities.
When a breaking NIR schema change occurs:
  1. Bump schema_version in src/schemas/nir.py
  2. Add a migration function here: _migrate_X_Y_to_X_Z(nir_dict: dict) -> dict
  3. Add a version branch in migrate() below
  4. Update SUPPORTED_NIR_VERSION in all serializers
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.schemas.nir import NIR

CURRENT_NIR_VERSION = "1.0"


def migrate(nir_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate a raw NIR dict to the current schema version.
    Call this before constructing NIR from a stored dict.
    Returns the dict unchanged if already at current version.
    Raises ValueError if version is unknown.
    """
    version = nir_dict.get("schema_version", "1.0")

    if version == CURRENT_NIR_VERSION:
        return nir_dict

    # Future migrations added here:
    # if version == "1.0":
    #     nir_dict = _migrate_1_0_to_1_1(nir_dict)
    #     nir_dict["schema_version"] = "1.1"
    #     version = "1.1"

    raise ValueError(
        f"Unknown NIR schema version '{version}'. "
        f"Cannot migrate to {CURRENT_NIR_VERSION}. "
        f"Add a migration function in src/nir/migrations.py."
    )


def check_version(nir: "NIR") -> None:
    """
    Call this at the start of every serializer.
    Raises ValueError with a clear message if version mismatch.
    Import NIR inside function to avoid circular import.
    """
    if nir.schema_version != CURRENT_NIR_VERSION:
        raise ValueError(
            f"NIR schema version mismatch. "
            f"Serializer supports '{CURRENT_NIR_VERSION}', "
            f"received '{nir.schema_version}'. "
            f"Run src.nir.migrations.migrate() before serializing."
        )
