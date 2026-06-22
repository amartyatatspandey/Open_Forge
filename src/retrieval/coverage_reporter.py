"""
Layer 1 coverage reporter (GLM 7.1).

Tracks how many components in the KB were considered by parametric search
vs how many were skipped because the queried symbol was never extracted
for them. Surfaces this as a coverage metric in retrieval_metadata so
engineers know what they might be missing.
"""
from __future__ import annotations
from dataclasses import dataclass
from src.retrieval.kb_client import KBClient


@dataclass
class CoverageReport:
    component_type: str
    symbol: str
    total_active_components: int
    components_with_symbol_extracted: int
    components_missing_symbol: int
    coverage_fraction: float
    # coverage_fraction = components_with_symbol / total_active
    # 1.0 = full coverage, 0.5 = half the KB lacks this parameter


def get_coverage_report(
    component_type: str,
    symbol: str,
    kb: KBClient,
) -> CoverageReport:
    """
    For a given parametric symbol (e.g. 'en' for op-amp noise),
    reports how many active components in the KB have this parameter
    extracted and approved vs how many don't.

    This tells the engineer: "Layer 1 considered X components;
    Y more components exist but lack extracted noise specs."
    """
    # Total active components (no category filter — intentionally broad)
    total_sql = """
        SELECT COUNT(*) AS total
        FROM components
        WHERE lifecycle_status = 'active'
    """
    total_row = kb.execute(total_sql, ())
    total = total_row[0]["total"] if total_row else 0

    # Components with this symbol extracted and approved
    covered_sql = """
        SELECT COUNT(DISTINCT component_id) AS covered
        FROM electrical_parameters
        WHERE symbol = %s
          AND extraction_status = 'approved'
          AND valid_to IS NULL
    """
    covered_row = kb.execute(covered_sql, (symbol,))
    covered = covered_row[0]["covered"] if covered_row else 0

    missing = max(0, total - covered)
    fraction = (covered / total) if total > 0 else 0.0

    return CoverageReport(
        component_type=component_type,
        symbol=symbol,
        total_active_components=total,
        components_with_symbol_extracted=covered,
        components_missing_symbol=missing,
        coverage_fraction=round(fraction, 4),
    )


# Symbol mapping: same as parametric_search in search_layers.py
COMPONENT_TYPE_TO_PRIMARY_SYMBOL: dict[str, str] = {
    "zero_drift_op_amp":          "VOS_drift",
    "low_noise_ldo":              "Vn",
    "precision_voltage_reference": "TC",
    "precision_resistor":         "TC",
    "negative_rail_converter":    "V_CC",
    "passive_component":          "tol",
}
