"""Phase 2 TSR evaluation metrics (deferred until grid GT exists)."""

from __future__ import annotations

TARGET_CELL_ACCURACY = 0.95
TARGET_MERGED_CELL_ACCURACY = 0.90


def compute_metrics(*_args, **_kwargs) -> None:
    """Compute cell-level TSR metrics against golden grid GT.

    Raises:
        NotImplementedError: Grid-level golden GT not yet annotated.
    """
    raise NotImplementedError(
        "Phase 2 metrics require grid-level golden GT annotation. "
        "Annotate cell grids in corpus/golden/ before running metrics. "
        f"Targets: cell_accuracy >= {TARGET_CELL_ACCURACY}, "
        f"merged_cell_accuracy >= {TARGET_MERGED_CELL_ACCURACY}."
    )
