"""NIR → design report PDF/Markdown generator."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from src.config import Config
from src.schemas.nir import NIR, PlacementConstraint, PinRef, ReviewFlag, RoutingHint

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
_LOW_CONFIDENCE_THRESHOLD = 0.75


def _aggregate_confidence(nir: NIR) -> float:
    scores: list[float] = [c.datasheet_confidence for c in nir.components]
    scores.extend(net.net_confidence for net in nir.netlist)
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _format_yes_no(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "N/A"


def _connected_pins_str(net_connections: list[PinRef]) -> str:
    return ", ".join(f"{p.ref}.{p.pin_name}" for p in net_connections)


def _constraint_distance(constraint: PlacementConstraint) -> str:
    if constraint.max_distance_mm is not None:
        return f"max {constraint.max_distance_mm}mm"
    if constraint.min_distance_mm is not None:
        return f"min {constraint.min_distance_mm}mm"
    return "—"


def _sort_review_flags(flags: list[ReviewFlag]) -> list[ReviewFlag]:
    return sorted(flags, key=lambda f: _SEVERITY_ORDER.get(f.severity, 99))


def _build_markdown(nir: NIR) -> str:
    lines: list[str] = []
    agg_confidence = _aggregate_confidence(nir)
    review_required = "yes" if nir.is_review_required() else "no"

    lines.extend(
        [
            "# Design Report",
            "",
            "## 1. Design Summary",
            "",
            f"- **Design ID:** {nir.design_id}",
            f"- **Prompt:** {nir.prompt}",
            f"- **Methodology:** {nir.design_methodology}",
            f"- **Created At:** {nir.created_at}",
            f"- **Aggregate Confidence Score:** {agg_confidence:.2f}",
            f"- **Review Required:** {review_required}",
            "",
            "## 2. Bill of Materials",
            "",
            "| Ref | Component ID | Type | Value | Footprint | Confidence | Justification | Source |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for comp in nir.components:
        source = nir.source_citations.get(comp.ref, "—")
        value = comp.value or "—"
        lines.append(
            f"| {comp.ref} | {comp.component_id} | {comp.component_type} | "
            f"{value} | {comp.footprint} | {comp.datasheet_confidence:.2f} | "
            f"{comp.justification} | {source} |"
        )

    lines.extend(
        [
            "",
            "## 3. Netlist Summary",
            "",
            "| Net Name | Type | Connected Pins | Confidence |",
            "| --- | --- | --- | --- |",
        ]
    )

    for net in nir.netlist:
        low_confidence_flag = (
            " ⚠ LOW" if net.net_confidence < _LOW_CONFIDENCE_THRESHOLD else ""
        )
        pins = _connected_pins_str(net.connections)
        lines.append(
            f"| {net.net_name} | {net.net_type} | {pins} | "
            f"{net.net_confidence:.2f}{low_confidence_flag} |"
        )

    lines.extend(
        [
            "",
            "## 4. Placement Constraints",
            "",
            "| Component | Constraint Type | Relative To | Distance | Hard/Soft | Source |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    for constraint in nir.placement_constraints:
        hard_soft = "Hard" if constraint.hard else "Soft"
        lines.append(
            f"| {constraint.ref} | {constraint.constraint_type} | "
            f"{constraint.relative_to} | {_constraint_distance(constraint)} | "
            f"{hard_soft} | {constraint.source} |"
        )

    if not nir.placement_constraints:
        lines.append("| — | — | — | — | — | — |")

    lines.extend(
        [
            "",
            "## 5. Routing Hints",
            "",
            "| Nets | Hint Type | Value | Note |",
            "| --- | --- | --- | --- |",
        ]
    )

    for hint in nir.routing_hints:
        lines.append(_format_routing_hint_row(hint))

    if not nir.routing_hints:
        lines.append("| — | — | — | — |")

    lines.extend(["", "## 6. Design Decisions Log", ""])
    if nir.justifications:
        for ref, justification in nir.justifications.items():
            source = nir.source_citations.get(ref, "—")
            lines.append(f"- **{ref}:** {justification} (Source: {source})")
    else:
        lines.append("- No design decisions recorded.")

    lines.extend(
        [
            "",
            "## 7. Review Flags",
            "",
            "| Ref | Severity | Reason | Stage |",
            "| --- | --- | --- | --- |",
        ]
    )

    sorted_flags = _sort_review_flags(nir.review_flags)
    for review_flag in sorted_flags:
        lines.append(
            f"| {review_flag.item_ref} | {review_flag.severity} | "
            f"{review_flag.reason} | {review_flag.stage} |"
        )

    if not sorted_flags:
        lines.append("| — | — | — | — |")

    critical_count = sum(1 for f in nir.review_flags if f.severity == "CRITICAL")
    warning_count = sum(1 for f in nir.review_flags if f.severity == "WARNING")
    info_count = sum(1 for f in nir.review_flags if f.severity == "INFO")
    erc_passed = _format_yes_no(nir.extraction_metadata.get("erc_passed"))
    drc_passed = _format_yes_no(nir.extraction_metadata.get("drc_passed"))

    lines.extend(
        [
            "",
            "## 8. Validation Summary",
            "",
            f"- **ERC passed:** {erc_passed}",
            f"- **DRC passed:** {drc_passed}",
            f"- **Total review flags:** {critical_count} critical, "
            f"{warning_count} warning, {info_count} info",
        ]
    )

    return "\n".join(lines) + "\n"


def _format_routing_hint_row(hint: RoutingHint) -> str:
    nets = ", ".join(hint.nets)
    value = f"{hint.value} {hint.unit}" if hint.value is not None and hint.unit else (
        str(hint.value) if hint.value is not None else "—"
    )
    return f"| {nets} | {hint.hint_type} | {value} | {hint.note} |"


def _try_pandoc(md_path: Path, pdf_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["pandoc", str(md_path), "-o", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 0 and pdf_path.exists():
            return True
        logger.warning("pandoc PDF conversion failed: %s", result.stderr)
    except FileNotFoundError:
        logger.warning("pandoc not found — trying weasyprint")
    except subprocess.TimeoutExpired:
        logger.warning("pandoc timed out — trying weasyprint")
    return False


def _try_weasyprint(markdown_content: str, pdf_path: Path) -> bool:
    try:
        from weasyprint import HTML

        html = (
            "<html><head><meta charset='utf-8'></head>"
            f"<body><pre>{_escape_html(markdown_content)}</pre></body></html>"
        )
        HTML(string=html).write_pdf(str(pdf_path))
        return pdf_path.exists()
    except ImportError:
        logger.warning("weasyprint not installed — saving Markdown only")
    except Exception as exc:
        logger.warning("weasyprint PDF conversion failed: %s", exc)
    return False


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def generate_design_report(
    nir: NIR,
    output_dir: Path,
    config: Config,
) -> Path:
    """
    Generate a PDF design report from the NIR.
    Returns path to generated PDF.
    Falls back to Markdown if PDF generation fails.
    Never raises.
    """
    _ = config  # reserved for future template/format configuration

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_content = _build_markdown(nir)
        md_path = output_dir / f"{nir.design_id}_report.md"
        pdf_path = output_dir / f"{nir.design_id}_report.pdf"
        md_path.write_text(markdown_content, encoding="utf-8")

        if _try_pandoc(md_path, pdf_path):
            return pdf_path
        if _try_weasyprint(markdown_content, pdf_path):
            return pdf_path

        logger.warning(
            "PDF generation unavailable for design %s — returning Markdown report",
            nir.design_id,
        )
        return md_path
    except Exception as exc:
        logger.error("Design report generation failed: %s", exc)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            fallback = output_dir / f"{nir.design_id}_report.md"
            if not fallback.exists():
                fallback.write_text(
                    f"# Design Report\n\nDesign ID: {nir.design_id}\n\n"
                    f"Report generation failed: {exc}\n",
                    encoding="utf-8",
                )
            return fallback
        except Exception as inner_exc:
            logger.error("Could not write fallback report: %s", inner_exc)
            return output_dir / f"{nir.design_id}_report.md"
