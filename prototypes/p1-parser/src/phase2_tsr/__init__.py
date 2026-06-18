"""Phase 2: Table Structure Recognition (TSR)."""

from src.phase2_tsr.confidence_scorer import pick_best_grid, score_grid
from src.phase2_tsr.merged_cell_handler import infer_col_count, normalise_merged_cells
from src.phase2_tsr.path_a_vector import bbox_to_pdf_points, extract_table_via_vector
from src.phase2_tsr.path_b_vlm import Qwen2VLExtractor, extract_table_via_vlm, parse_markdown_table
from src.phase2_tsr.runner import run_phase2

__all__ = [
    "Qwen2VLExtractor",
    "bbox_to_pdf_points",
    "extract_table_via_vector",
    "extract_table_via_vlm",
    "infer_col_count",
    "normalise_merged_cells",
    "parse_markdown_table",
    "pick_best_grid",
    "run_phase2",
    "score_grid",
]
