"""Phase 1 DLA evaluation metrics against golden ground truth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.schemas import ComponentDatasheet, Phase1Output

TARGET_TABLE_RECALL = 0.92
TARGET_TABLE_PRECISION = 0.90
TARGET_FOOTNOTE_RECALL = 0.85
TARGET_SECTION_ACC = 0.85
PAGE_MATCH_SLACK = 3  # TI PDF index vs printed page numbering


@dataclass
class Phase1Metrics:
    """Per-datasheet Phase 1 metric bundle."""

    component_id: str
    table_recall: float
    table_precision: float
    footnote_recall: float
    section_classification_acc: float
    num_detections: int
    num_gt_sections: int

    @property
    def passed(self) -> bool:
        """Return True if all Phase 1 exit metrics are met."""
        return (
            self.table_recall >= TARGET_TABLE_RECALL
            and self.table_precision >= TARGET_TABLE_PRECISION
            and self.footnote_recall >= TARGET_FOOTNOTE_RECALL
            and self.section_classification_acc >= TARGET_SECTION_ACC
        )


def load_ground_truth(path: Path) -> ComponentDatasheet:
    """Load a golden ground-truth JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ComponentDatasheet(**data)


def _gt_table_sections(datasheet: ComponentDatasheet) -> list[tuple[str, tuple[int, int]]]:
    """Return (section_type, page_range) for sections that contain tables."""
    relevant = {
        "electrical_characteristics",
        "absolute_maximum_ratings",
        "pinout",
        "timing",
        "ordering",
    }
    sections: list[tuple[str, tuple[int, int]]] = []
    for section in datasheet.sections:
        if section.section_type in relevant:
            sections.append((section.section_type, section.page_range))
    return sections


def _page_in_range(page: int, page_range: tuple[int, int], slack: int = PAGE_MATCH_SLACK) -> bool:
    """Check if page falls within inclusive page_range with optional slack."""
    return (page_range[0] - slack) <= page <= (page_range[1] + slack)


def _best_gt_match(
    section_type: str,
    page_number: int,
    gt_sections: list[tuple[str, tuple[int, int]]],
) -> tuple[str, tuple[int, int]] | None:
    """Find best-matching GT section for a detection (type match preferred)."""
    type_matches = [
        (gt_type, page_range)
        for gt_type, page_range in gt_sections
        if gt_type == section_type and _page_in_range(page_number, page_range)
    ]
    if type_matches:
        return type_matches[0]
    page_matches = [
        (gt_type, page_range)
        for gt_type, page_range in gt_sections
        if _page_in_range(page_number, page_range)
    ]
    return page_matches[0] if page_matches else None


def _match_detection_to_gt(
    section_type: str,
    page_number: int,
    gt_sections: list[tuple[str, tuple[int, int]]],
) -> bool:
    """Return True if detection matches a ground-truth section."""
    match = _best_gt_match(section_type, page_number, gt_sections)
    return match is not None and match[0] == section_type


def _gt_footnote_keys(datasheet: ComponentDatasheet) -> set[str]:
    """Extract expected footnote markers from ground truth metadata if present."""
    # Ground truth may store footnotes in validation or embedded metadata patterns
    keys: set[str] = set()
    raw = datasheet.model_dump()
    metadata = raw.get("metadata") or {}
    footnote_map = metadata.get("footnote_map") or {}
    keys.update(footnote_map.keys())
    # Also count footnote refs in parameter footnote fields
    for section in datasheet.sections:
        for param in section.parameters:
            for value in (param.min_value, param.typ_value, param.max_value):
                if value and value.footnote:
                    keys.add(value.footnote)
    return keys


def table_detection_metrics(
    output: Phase1Output,
    ground_truth: ComponentDatasheet,
) -> Phase1Metrics:
    """Compute Phase 1 table detection and classification metrics.

    Args:
        output: Phase 1 pipeline output.
        ground_truth: Hand-verified ComponentDatasheet ground truth.

    Returns:
        Phase1Metrics with recall, precision, footnote recall, section accuracy.
    """
    gt_sections = _gt_table_sections(ground_truth)
    detections = output.detected_tables

    # Recall: fraction of GT sections with at least one matching detection
    matched_gt = 0
    for gt_type, page_range in gt_sections:
        for det in detections:
            if det.section_type == gt_type and _page_in_range(det.page_number, page_range):
                matched_gt += 1
                break
    table_recall = matched_gt / len(gt_sections) if gt_sections else 1.0

    # Precision: fraction of detections matching a GT section
    correct_detections = 0
    for det in detections:
        if _match_detection_to_gt(det.section_type, det.page_number, gt_sections):
            correct_detections += 1
    table_precision = correct_detections / len(detections) if detections else 0.0

    # Section classification accuracy on detections with a GT match
    classified_correct = 0
    classified_total = 0
    for det in detections:
        match = _best_gt_match(det.section_type, det.page_number, gt_sections)
        if match is None:
            continue
        classified_total += 1
        if det.section_type == match[0]:
            classified_correct += 1
    section_acc = classified_correct / classified_total if classified_total else 1.0

    # Footnote recall — marker keys from metadata, or presence-based when prose-only
    gt_fn_keys = _gt_footnote_keys(ground_truth)
    marker_keys = {k for k in gt_fn_keys if k.startswith("(") or k == "*"}
    extracted_markers = set(output.footnote_map.keys())
    if marker_keys:
        matched_fn = sum(
            1
            for key in marker_keys
            if key in extracted_markers or key.strip("()") in extracted_markers
        )
        footnote_recall = matched_fn / len(marker_keys)
    elif gt_fn_keys:
        # Prose footnotes in GT — credit if any footnotes were extracted
        footnote_recall = 1.0 if output.footnotes else 0.0
    else:
        footnote_recall = 1.0 if not output.footnotes else min(1.0, len(output.footnotes) / 2)

    return Phase1Metrics(
        component_id=ground_truth.component_id,
        table_recall=table_recall,
        table_precision=table_precision,
        footnote_recall=footnote_recall,
        section_classification_acc=section_acc,
        num_detections=len(detections),
        num_gt_sections=len(gt_sections),
    )
