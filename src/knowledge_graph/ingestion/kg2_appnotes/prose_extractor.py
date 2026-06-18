"""Prose text extraction and rule extraction from app note PDFs.

Two-pass extraction:
- Pass 1: Design rules → KG-2 (component types, recipes)
- Pass 2: Placement rules → KG-4 (spatial constraints)

Reuses Phase 5 spatial parser for placement constraint extraction.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src.datasheet.phase5_layout._schemas import PageTextBlock
from src.datasheet.phase5_layout.spatial_parser import parse_constraints
from src.knowledge_graph.ingestion import extract_triples
from src.knowledge_graph.ingestion._schemas import Triple
from src.schemas.datasheet import PlacementConstraint
from src.schemas.kg import KGRelation

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# Spatial keywords for Pass 2 placement rule detection
PLACEMENT_KEYWORDS: list[str] = [
    "place",
    "near",
    "close to",
    "away from",
    "within",
    "keepout",
    "avoid",
    "route",
    "shortest",
    "minimize",
    "adjacent",
    "distance",
    "proximity",
    "spacing",
    "layout",
    "position",
    "located",
]

# Design rule relations for Pass 1 filtering
DESIGN_RULE_RELATIONS: set[KGRelation] = {
    KGRelation.REQUIRES,
    KGRelation.USES,
    KGRelation.HAS_PROPERTY,
}


def _extract_text_from_pdf(pdf_path: Path, config: Config) -> list[PageTextBlock]:
    """Extract plain text from PDF using pdfplumber.
    
    Extracts non-table text sections only.
    
    Args:
        pdf_path: Path to PDF file
        config: Application config
        
    Returns:
        List of PageTextBlock per page
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available, cannot extract PDF text")
        return []
    
    blocks: list[PageTextBlock] = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    # Extract text, avoiding tables
                    text = page.extract_text() or ""
                    
                    # Simple heuristic: if text looks like a table (many | or tabs), skip
                    # This is a placeholder - real implementation would use pdfplumber's table detection
                    if len(text) < 50:  # Skip very short pages
                        continue
                    
                    blocks.append(
                        PageTextBlock(
                            page_number=i,
                            text=text,
                            char_count=len(text),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to extract page {i}: {e}")
                    continue
    except Exception as e:
        logger.error(f"Failed to open PDF {pdf_path}: {e}")
    
    return blocks


def _clean_prose_text(text: str) -> str:
    """Clean prose text for extraction.
    
    - Join hyphenated line breaks
    - Normalize whitespace
    - Remove page headers/footers (heuristic)
    
    Args:
        text: Raw text from PDF
        
    Returns:
        Cleaned text
    """
    # Join hyphenated line breaks
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common page artifacts
    # Page numbers
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    # Copyright footers (heuristic)
    text = re.sub(r'\n\s*©.*?(\n|$)', '\n', text, flags=re.IGNORECASE)
    
    return text.strip()


def _detect_placement_sentences(text: str) -> list[str]:
    """Detect sentences containing spatial keywords for placement rules.
    
    Args:
        text: Prose text
        
    Returns:
        List of sentences containing placement keywords
    """
    sentences = re.split(r'[.!?]+', text)
    matching: list[str] = []
    
    for sentence in sentences:
        sentence_lower = sentence.lower()
        if any(keyword in sentence_lower for keyword in PLACEMENT_KEYWORDS):
            matching.append(sentence.strip())
    
    return matching


def extract_design_rules(
    text: str,
    source_document: str,
    source_url: str,
    config: Config,
) -> list[Triple]:
    """Pass 1: Extract design rules (→ KG-2).
    
    Calls triple_extractor and filters for REQUIRES, USES, HAS_PROPERTY.
    
    Args:
        text: Prose text from PDF
        source_document: PDF filename
        source_url: PDF URL
        config: Application config
        
    Returns:
        List of Triples for design rules
    """
    logger.info("Pass 1: Extracting design rules for KG-2")
    
    # Extract all triples
    all_triples = extract_triples(text, source_document, source_url, config)
    
    # Filter for design rule relations
    design_triples = [
        t for t in all_triples
        if t.relation in DESIGN_RULE_RELATIONS
    ]
    
    logger.info(f"Extracted {len(design_triples)} design rule triples for KG-2")
    return design_triples


def extract_placement_rules(
    text: str,
    pdf_path: Path,
    config: Config,
) -> list[PlacementConstraint]:
    """Pass 2: Extract placement rules (→ KG-4).
    
    Detects spatial keyword sentences and uses Phase 5 spatial_parser.
    Reuses phase5_layout.spatial_parser for consistency.
    
    Args:
        text: Prose text from PDF
        pdf_path: Path to PDF file (for context)
        config: Application config
        
    Returns:
        List of PlacementConstraint objects
    """
    logger.info("Pass 2: Extracting placement rules for KG-4")
    
    # Detect placement-relevant sentences
    placement_sentences = _detect_placement_sentences(text)
    
    if not placement_sentences:
        logger.debug("No placement-relevant sentences detected")
        return []
    
    logger.info(f"Detected {len(placement_sentences)} placement-relevant sentences")
    
    # Create PageTextBlock for spatial_parser
    # Combine sentences into a single block
    combined_text = "\n".join(placement_sentences)
    block = PageTextBlock(
        page_number=1,  # App notes are treated as single document
        text=combined_text,
        char_count=len(combined_text),
    )
    
    # Call Phase 5 spatial_parser (reused)
    try:
        result = parse_constraints([block], config)
        constraints = result.constraints
        logger.info(f"Extracted {len(constraints)} placement constraints for KG-4")
        return constraints
    except Exception as e:
        logger.error(f"Placement extraction failed: {e}")
        return []


def extract_from_pdf(
    pdf_path: Path,
    config: Config,
) -> tuple[list[Triple], list[PlacementConstraint]]:
    """Extract both design rules and placement rules from PDF.
    
    Args:
        pdf_path: Path to app note PDF
        config: Application config
        
    Returns:
        Tuple of (design_triples, placement_constraints)
    """
    # Extract text blocks
    blocks = _extract_text_from_pdf(pdf_path, config)
    
    if not blocks:
        logger.warning(f"No text extracted from {pdf_path}")
        return [], []
    
    # Combine and clean text
    raw_text = "\n".join(b.text for b in blocks)
    cleaned_text = _clean_prose_text(raw_text)
    
    # Source info
    source_document = pdf_path.name
    source_url = f"file://{pdf_path}"
    
    # Pass 1: Design rules
    design_triples = extract_design_rules(
        cleaned_text,
        source_document,
        source_url,
        config,
    )
    
    # Pass 2: Placement rules
    placement_constraints = extract_placement_rules(
        cleaned_text,
        pdf_path,
        config,
    )
    
    return design_triples, placement_constraints
