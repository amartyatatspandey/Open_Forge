"""BOM generator package — converts DesignSubgraph to ValidatedBOM.

Team C's entry point. Takes the output from Team B's knowledge graph query
and generates a complete Bill of Materials with component selections,
justifications, and confidence scores.

Public API:
    generate_bom(subgraph, intent, config) -> ValidatedBOM
    validate_bom(bom, config) -> ValidatedBOM
    generate_bom_candidates(subgraph, intent, config) -> BOMLadder
    TPEBOMSampler — cross-design component preference learning

Example:
    >>> from src.bom import generate_bom, validate_bom, generate_bom_candidates
    >>> from src.bom import TPEBOMSampler, record_asha_outcome
    >>> from src.schemas.intent import IntentDict
    >>> from src.schemas.kg import DesignSubgraph
    >>>
    >>> bom = generate_bom(subgraph, intent, config)
    >>> validated = validate_bom(bom, config)
    >>> print(f"BOM has {len(validated.components)} components")
    >>> print(f"Review required: {validated.review_required}")
"""

from __future__ import annotations

from src.bom.candidates import BOMLadder, generate_bom_candidates
from src.bom.generator import generate_bom
from src.bom.tpe_sampler import BOMOutcome, ComponentRanking, TPEBOMSampler, record_asha_outcome
from src.bom.validator import validate_bom

__all__ = [
    "generate_bom",
    "validate_bom",
    "generate_bom_candidates",
    "BOMLadder",
    "TPEBOMSampler",
    "BOMOutcome",
    "ComponentRanking",
    "record_asha_outcome",
]
