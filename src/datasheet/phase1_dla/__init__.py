"""Phase 1 Document Layout Analysis (DLA) package.

This package provides the complete Phase 1 pipeline for extracting table regions,
footnotes, and section classifications from PDF datasheets.

Only one public function is exported: `process()`

Internal modules (private):
- _schemas: Internal Pydantic models (not public API)
- rasterizer: PDF to PIL Image conversion
- detector: YOLOv8n-DocLayNet inference
- section_classifier: Section heading classification
- footnote_linker: Superscript to footnote linking
- multipage_merger: Multipage table detection

Usage:
    from src.datasheet.phase1_dla import process
    from src.config import get_config

    config = get_config()
    result = process(Path("datasheet.pdf"), config)
    # result is Phase1Output with table_crops and footnote_maps
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.datasheet.phase1_dla._schemas import FootnoteMap, Phase1Output, TableCrop
from src.datasheet.phase1_dla.detector import (
    CLASS_CAPTION,
    CLASS_FOOTNOTE,
    CLASS_TABLE,
    _crop_region,
    _detect_all_pages,
    _load_yolo_model,
)
from src.datasheet.phase1_dla.footnote_linker import link_footnotes
from src.datasheet.phase1_dla.multipage_merger import detect_multipage_tables
from src.datasheet.phase1_dla.rasterizer import (
    _rasterize_all_pages,
    _rasterize_page,
)
from src.datasheet.phase1_dla.section_classifier import classify_section
from src.datasheet.utils import compute_pdf_sha256

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Public API exports only the process function
__all__ = ["process"]


def _extract_page_text_placeholder(image: Image.Image) -> str:
    """Placeholder for OCR text extraction from page image.

    In production, this would use an OCR engine like Tesseract or
    EasyOCR to extract text from the page image.

    For now, returns empty string as placeholder.

    Args:
        image: PIL Image of the page

    Returns:
        Extracted text (placeholder returns "")
    """
    # Placeholder: would use OCR in production
    return ""


def _detect_and_crop_tables(
    pages: list[tuple[int, Image.Image]],
    config: Config,
) -> list[TableCrop]:
    """Detect tables on all pages and crop to PNG bytes.

    Args:
        pages: List of (page_number, PIL.Image) tuples
        config: Application configuration

    Returns:
        List of TableCrop objects with cropped images
    """
    # Load YOLO model (raises FileNotFoundError if missing)
    model = _load_yolo_model(config)

    # Detect regions on all pages
    all_detections = _detect_all_pages(
        pages,
        model,
        confidence_threshold=0.25,
    )

    table_crops: list[TableCrop] = []

    for page_num, image in pages:
        detections = all_detections.get(page_num, [])

        # Get image dimensions for normalization
        page_width, page_height = image.size

        # Filter to table detections only
        table_detections = [
            d for d in detections
            if d["class_id"] == CLASS_TABLE
        ]

        # Get caption/heading detections for classification
        caption_detections = [
            d for d in detections
            if d["class_id"] == CLASS_CAPTION
        ]

        for table_idx, detection in enumerate(table_detections):
            bbox = detection["bounding_box"]
            confidence = detection["confidence"]

            # Extract heading text from nearby caption detection
            heading_text = None
            if caption_detections:
                # Simple heuristic: closest caption above table
                tx1, ty1, tx2, ty2 = bbox
                closest_caption = None
                min_distance = float("inf")

                for cap in caption_detections:
                    cx1, cy1, cx2, cy2 = cap["bounding_box"]
                    # Caption should be above table
                    if cy2 < ty1:
                        distance = ty1 - cy2
                        if distance < min_distance:
                            min_distance = distance
                            closest_caption = cap

                # Placeholder: would extract caption text via OCR
                if closest_caption and min_distance < page_height * 0.1:
                    heading_text = f"Detected caption near table"

            # Classify section type
            section_type = classify_section(
                heading_text=heading_text,
                page_number=page_num,
                table_index=table_idx,
            )

            # Crop table region
            image_bytes = _crop_region(image, bbox)

            table_crop = TableCrop(
                page_number=page_num,
                section_type=section_type,
                image_bytes=image_bytes,
                bounding_box=bbox,
                heading_text=heading_text,
                is_multipage_continuation=False,  # Will be set by merger
                detection_confidence=confidence,
            )

            table_crops.append(table_crop)
            logger.debug(
                f"Page {page_num}: Cropped {section_type.value} "
                f"table at {bbox}"
            )

    logger.info(f"Created {len(table_crops)} table crops from {len(pages)} pages")
    return table_crops


def process(
    pdf_path: Path,
    config: Config,
) -> Phase1Output:
    """Phase 1: Document Layout Analysis.

    Rasterizes PDF, detects table regions and footnotes, classifies section types.

    This is the only public function exported from this package. It orchestrates
    the complete Phase 1 pipeline:
    1. Rasterize PDF pages to images
    2. Run YOLOv8n-DocLayNet detection
    3. Crop detected tables
    4. Classify section types from headings
    5. Extract and link footnotes
    6. Detect multipage table continuations

    Args:
        pdf_path: Path to the PDF datasheet file
        config: Application configuration with model paths

    Returns:
        Phase1Output containing table crops, footnote maps, and metadata

    Raises:
        FileNotFoundError: If PDF file or YOLO model is missing
        RuntimeError: If processing fails

    Example:
        >>> from src.datasheet.phase1_dla import process
        >>> from src.config import get_config
        >>> config = get_config()
        >>> result = process(Path("TI_TPS62933.pdf"), config)
        >>> len(result.table_crops)
        3
        >>> result.table_crops[0].section_type.value
        'electrical_characteristics'
    """
    start_time = time.time()
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    logger.info(f"Starting Phase 1 DLA on {path}")

    # Step 1: Compute PDF hash for provenance
    source_hash = compute_pdf_sha256(path)
    logger.info(f"PDF SHA-256: {source_hash[:16]}...")

    # Step 2: Rasterize all pages
    pages = _rasterize_all_pages(path)
    total_pages = len(pages)
    logger.info(f"Rasterized {total_pages} pages")

    # Step 3: Detect and crop tables
    # This loads YOLO model - will raise FileNotFoundError if missing
    table_crops = _detect_and_crop_tables(pages, config)

    # Step 4: Detect multipage table continuations
    if table_crops and pages:
        _, first_image = pages[0]
        page_height = first_image.height
        table_crops = detect_multipage_tables(table_crops, page_height)

    # Step 5: Extract text and link footnotes (placeholder)
    # In production, this would:
    # 1. OCR each page
    # 2. Extract text regions
    # 3. Link superscripts to footnote definitions
    page_texts: dict[int, str] = {}
    for page_num, image in pages:
        page_texts[page_num] = _extract_page_text_placeholder(image)

    footnote_maps = link_footnotes(page_texts)

    # Calculate processing time
    processing_time_ms = (time.time() - start_time) * 1000
    logger.info(
        f"Phase 1 complete: {len(table_crops)} tables, "
        f"{len(footnote_maps)} footnote maps, "
        f"{processing_time_ms:.1f}ms"
    )

    return Phase1Output(
        pdf_path=str(path),
        source_pdf_hash=source_hash,
        total_pages=total_pages,
        table_crops=table_crops,
        footnote_maps=footnote_maps,
        processing_time_ms=processing_time_ms,
    )


# Import Image at module level to avoid issues
from PIL import Image
