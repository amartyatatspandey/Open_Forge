"""BOM generator — orchestrates conversion from DesignSubgraph to ValidatedBOM.

Main entry point for Team C. Coordinates component selection, confidence scoring,
and validation to produce a complete Bill of Materials.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Config
    from src.schemas.intent import IntentDict, ValidatedBOM
    from src.schemas.kg import DesignSubgraph

logger = logging.getLogger(__name__)


def generate_bom(
    subgraph: DesignSubgraph,
    intent: IntentDict,
    config: Config,
) -> ValidatedBOM:
    """Generate a ValidatedBOM from a KG design subgraph.
    
    If subgraph has no component_types: returns ValidatedBOM with empty components
    and review_required=True.
    
    Never raises — catches all exceptions and returns a valid (possibly empty)
    ValidatedBOM with error information.
    
    Pipeline:
    1. Generate unique design_id (UUID)
    2. Reset reference designator counter
    3. For each component_type in subgraph: select_component()
    4. Calculate total_confidence with weighted scoring
    5. Determine review_required based on thresholds
    6. Return ValidatedBOM
    
    Args:
        subgraph: DesignSubgraph from knowledge graph query
        intent: Original design intent
        config: Application configuration with thresholds
        
    Returns:
        ValidatedBOM with component entries and confidence scores
        
    Example:
        >>> bom = generate_bom(subgraph, intent, config)
        >>> print(f"BOM: {bom.design_id}")
        >>> print(f"Components: {len(bom.components)}")
        >>> if bom.review_required:
        ...     print("Review required!")
    """
    from src.bom.confidence_scorer import score_bom
    from src.bom.selector import get_counter, select_component
    from src.schemas.intent import ValidatedBOM
    
    # Generate unique design ID
    design_id = str(uuid.uuid4())
    
    try:
        # Check for empty subgraph
        if not subgraph.component_types:
            logger.warning("Empty subgraph — no component types found for BOM generation")
            return ValidatedBOM(
                design_id=design_id,
                intent=intent,
                components=[],
                total_confidence=0.0,
                review_required=True,
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
        
        # Reset reference designator counter for this BOM
        counter = get_counter()
        counter.reset()
        
        # Generate BOM entries for each component type
        entries = []
        for comp_type_node in subgraph.component_types:
            try:
                entry = select_component(comp_type_node, subgraph, intent, counter)
                entries.append(entry)
            except Exception as e:
                logger.error(f"Failed to select component for {comp_type_node.id}: {e}")
                # Continue with other components — don't let one failure stop the BOM
                continue
        
        # Calculate total confidence
        total_confidence = score_bom(entries, subgraph)
        
        # Determine if review is required
        # Get thresholds from config (with defaults)
        bom_total_threshold = getattr(config, "confidence_thresholds", {}).get("bom_total", 0.85)
        bom_component_threshold = getattr(config, "confidence_thresholds", {}).get("bom_component", 0.75)
        
        review_required = (
            total_confidence < bom_total_threshold
            or any(e.confidence < bom_component_threshold for e in entries)
            or any(e.specific_part is None for e in entries)
        )
        
        # Create ValidatedBOM
        return ValidatedBOM(
            design_id=design_id,
            intent=intent,
            components=entries,
            total_confidence=total_confidence,
            review_required=review_required,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        
    except Exception as e:
        # Never raise — return empty BOM with error indication
        logger.error(f"BOM generation failed: {e}", exc_info=True)
        return ValidatedBOM(
            design_id=design_id,
            intent=intent,
            components=[],
            total_confidence=0.0,
            review_required=True,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
