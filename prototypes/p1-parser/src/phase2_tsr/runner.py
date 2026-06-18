"""Phase 2 orchestrator: dual-path TSR on Phase 1 table crops."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

from src.config import Config, get_config
from src.phase2_tsr.confidence_scorer import pick_best_grid
from src.phase2_tsr.merged_cell_handler import normalise_merged_cells
from src.phase2_tsr.path_a_vector import extract_table_via_vector
from src.phase2_tsr.path_b_vlm import Qwen2VLExtractor
from src.schemas.pipeline import GridMatrix, Phase1Output, Phase2Output
from src.utils.exceptions import TSRError

logger = logging.getLogger(__name__)


def _process_table(
    phase1_output: Phase1Output,
    table_index: int,
    vlm_extractor: Qwen2VLExtractor,
    config: Config,
) -> tuple[GridMatrix | None, str]:
    """Run dual-path TSR on a single detected table.

    Returns:
        Tuple of (grid or None, winner label: path_a|path_b|failed|vlm_skipped).
    """
    table = phase1_output.detected_tables[table_index]
    pdf_path = phase1_output.pdf_path

    with ThreadPoolExecutor(max_workers=config.phase2_tsr.parallel_workers) as executor:
        future_a = executor.submit(
            extract_table_via_vector,
            pdf_path,
            table.bbox,
            table.page_number,
            table.section_type,
            config,
        )
        future_b = executor.submit(
            vlm_extractor.extract_table_via_vlm,
            table.crop_bytes,
            table.section_type,
            table.page_number,
            config,
        )
        try:
            grid_a = future_a.result(timeout=config.phase2_tsr.vector_timeout_sec)
        except FuturesTimeoutError:
            logger.warning("Vector path timed out for table %d", table_index)
            grid_a = None
        try:
            grid_b = future_b.result(timeout=config.phase2_tsr.vlm_timeout_sec)
        except FuturesTimeoutError:
            logger.warning("VLM path timed out for table %d", table_index)
            grid_b = None

    vlm_skipped = not config.phase2_tsr.vlm_enabled

    best = pick_best_grid(grid_a, grid_b, config=config)
    if best is None:
        logger.warning(
            "Both paths failed for table on page %d (%s)",
            table.page_number,
            table.section_type,
        )
        if vlm_skipped:
            return None, "vlm_skipped"
        return None, "failed"

    if best.source == "vector_path_A":
        winner_label = "path_a"
    elif best.source == "vlm_path_B":
        winner_label = "path_b"
    else:
        winner_label = "failed"

    normalized_rows = normalise_merged_cells(best.rows, target_col_count=best.num_cols)
    return (
        GridMatrix(
            rows=normalized_rows,
            num_rows=len(normalized_rows),
            num_cols=best.num_cols,
            section_type=table.section_type,
            page_number=table.page_number,
            confidence=best.confidence,
            source=best.source,
            heading_text=table.heading_text,
        ),
        winner_label,
    )


def run_phase2(
    phase1_output: Phase1Output,
    config: Config | None = None,
) -> Phase2Output:
    """Run full Phase 2 TSR pipeline on Phase 1 detections.

    Args:
        phase1_output: Output from Phase 1 DLA.
        config: Optional config override.

    Returns:
        Phase2Output with extracted grids.

    Raises:
        TSRError: If no tables could be extracted from non-empty Phase 1 output.
    """
    cfg = config or get_config()
    vlm_extractor = Qwen2VLExtractor.get_instance(config=cfg)
    logger.info(
        "Phase 2 TSR starting for %s (%d tables)",
        phase1_output.pdf_path,
        len(phase1_output.detected_tables),
    )

    grids: list[GridMatrix] = []
    path_a_wins = 0
    path_b_wins = 0
    both_failed = 0
    vlm_skipped = 0

    for index in range(len(phase1_output.detected_tables)):
        grid, winner = _process_table(phase1_output, index, vlm_extractor, cfg)
        if not cfg.phase2_tsr.vlm_enabled:
            vlm_skipped += 1
        if winner == "path_a":
            path_a_wins += 1
        elif winner == "path_b":
            path_b_wins += 1
        elif grid is None:
            both_failed += 1
        if grid is not None:
            grids.append(grid)

    if not grids and phase1_output.detected_tables:
        raise TSRError(
            f"No tables extracted from {Path(phase1_output.pdf_path).name}"
        )

    metadata = {
        "num_tables_input": len(phase1_output.detected_tables),
        "num_tables_success": len(grids),
        "path_a_wins": path_a_wins,
        "path_b_wins": path_b_wins,
        "both_failed": both_failed,
        "vlm_skipped": vlm_skipped,
        "vlm_enabled": cfg.phase2_tsr.vlm_enabled,
    }

    output = Phase2Output(
        pdf_path=phase1_output.pdf_path,
        grids=grids,
        metadata=metadata,
    )
    _write_debug_output(output, cfg)
    logger.info(
        "Phase 2 complete: %d/%d tables for %s",
        len(grids),
        len(phase1_output.detected_tables),
        Path(phase1_output.pdf_path).name,
    )
    return output


def _write_debug_output(output: Phase2Output, config: Config) -> None:
    """Write optional debug metadata to phase2 output directory."""
    out_dir = config.pipeline.phase2_output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(output.pdf_path).stem
    meta_path = out_dir / f"{stem}_phase2_meta.json"
    meta = {
        "pdf_path": output.pdf_path,
        "num_tables": output.num_tables,
        "metadata": output.metadata,
        "section_types": [g.section_type for g in output.grids],
        "sources": [g.source for g in output.grids],
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
