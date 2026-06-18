"""Reference designator to datasheet mapping."""

from __future__ import annotations

from typing import Optional

from src.schemas.datasheet import ComponentDatasheet
from src.schemas.intent import ValidatedBOM


def build_ref_map(
    bom: ValidatedBOM,
    datasheets: list[ComponentDatasheet],
) -> dict[str, tuple[str, Optional[ComponentDatasheet]]]:
    """Build component_id → (ref_designator, datasheet) lookup.

    Returns:
        Mapping keyed by component_id (or BOM ref when specific_part is None).
    """
    datasheet_by_id = {ds.component_id: ds for ds in datasheets}
    ref_map: dict[str, tuple[str, Optional[ComponentDatasheet]]] = {}

    for entry in bom.components:
        if entry.specific_part is None:
            ref_map[entry.ref] = (entry.ref, None)
            continue

        datasheet = datasheet_by_id.get(entry.specific_part)
        ref_map[entry.specific_part] = (entry.ref, datasheet)

    return ref_map
