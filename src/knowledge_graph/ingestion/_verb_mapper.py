"""Verb phrase to KGRelation mapping.

Maps natural language verb phrases to canonical KGRelation types
for triple extraction from engineering text.
"""

from __future__ import annotations

from typing import Optional

from src.schemas.kg import KGRelation

# Verb phrase to KGRelation mapping
VERB_TO_RELATION: dict[str, KGRelation] = {
    # REQUIRES family
    "require": KGRelation.REQUIRES,
    "requires": KGRelation.REQUIRES,
    "need": KGRelation.REQUIRES,
    "needs": KGRelation.REQUIRES,
    "must have": KGRelation.REQUIRES,
    "depend on": KGRelation.REQUIRES,
    "depends on": KGRelation.REQUIRES,
    "requirement": KGRelation.REQUIRES,
    "needs to have": KGRelation.REQUIRES,
    "must possess": KGRelation.REQUIRES,
    "necessitate": KGRelation.REQUIRES,
    "necessitates": KGRelation.REQUIRES,
    # USES family
    "use": KGRelation.USES,
    "uses": KGRelation.USES,
    "utilize": KGRelation.USES,
    "utilizes": KGRelation.USES,
    "employ": KGRelation.USES,
    "employs": KGRelation.USES,
    "implement": KGRelation.USES,
    "implements": KGRelation.USES,
    "apply": KGRelation.USES,
    "applies": KGRelation.USES,
    # IS_A family
    "is a": KGRelation.IS_A,
    "is an": KGRelation.IS_A,
    "is called": KGRelation.IS_A,
    "is known as": KGRelation.IS_A,
    "refers to": KGRelation.IS_A,
    "is classified as": KGRelation.IS_A,
    "belongs to the category": KGRelation.IS_A,
    "is considered": KGRelation.IS_A,
    "defines": KGRelation.IS_A,
    "defines a": KGRelation.IS_A,
    "is defined as": KGRelation.IS_A,
    # HAS_PROPERTY family
    "has": KGRelation.HAS_PROPERTY,
    "have": KGRelation.HAS_PROPERTY,
    "exhibit": KGRelation.HAS_PROPERTY,
    "exhibits": KGRelation.HAS_PROPERTY,
    "possess": KGRelation.HAS_PROPERTY,
    "possesses": KGRelation.HAS_PROPERTY,
    "provide": KGRelation.HAS_PROPERTY,
    "provides": KGRelation.HAS_PROPERTY,
    "offers": KGRelation.HAS_PROPERTY,
    "features": KGRelation.HAS_PROPERTY,
    "includes": KGRelation.HAS_PROPERTY,
    "contains": KGRelation.HAS_PROPERTY,
    "is characterized by": KGRelation.HAS_PROPERTY,
    "demonstrates": KGRelation.HAS_PROPERTY,
    "show": KGRelation.HAS_PROPERTY,
    "shows": KGRelation.HAS_PROPERTY,
    # CONNECTS_TO family
    "connect": KGRelation.CONNECTS_TO,
    "connects": KGRelation.CONNECTS_TO,
    "connect to": KGRelation.CONNECTS_TO,
    "connects to": KGRelation.CONNECTS_TO,
    "wire": KGRelation.CONNECTS_TO,
    "wires": KGRelation.CONNECTS_TO,
    "wire to": KGRelation.CONNECTS_TO,
    "link": KGRelation.CONNECTS_TO,
    "links": KGRelation.CONNECTS_TO,
    "couple": KGRelation.CONNECTS_TO,
    "couples": KGRelation.CONNECTS_TO,
    "attach": KGRelation.CONNECTS_TO,
    "attaches": KGRelation.CONNECTS_TO,
    "interface": KGRelation.CONNECTS_TO,
    "interfaces": KGRelation.CONNECTS_TO,
    "interface with": KGRelation.CONNECTS_TO,
    # PART_OF family
    "part of": KGRelation.PART_OF,
    "component of": KGRelation.PART_OF,
    "belong to": KGRelation.PART_OF,
    "belongs to": KGRelation.PART_OF,
    "constituent of": KGRelation.PART_OF,
    "member of": KGRelation.PART_OF,
    "element of": KGRelation.PART_OF,
    "section of": KGRelation.PART_OF,
    "module of": KGRelation.PART_OF,
    # INCOMPATIBLE_WITH family
    "incompatible": KGRelation.INCOMPATIBLE_WITH,
    "incompatible with": KGRelation.INCOMPATIBLE_WITH,
    "cannot connect": KGRelation.INCOMPATIBLE_WITH,
    "conflicts with": KGRelation.INCOMPATIBLE_WITH,
    "interferes with": KGRelation.INCOMPATIBLE_WITH,
    "cannot interface": KGRelation.INCOMPATIBLE_WITH,
    "mutually exclusive": KGRelation.INCOMPATIBLE_WITH,
    "opposes": KGRelation.INCOMPATIBLE_WITH,
    # OVERRIDES family
    "override": KGRelation.OVERRIDES,
    "overrides": KGRelation.OVERRIDES,
    "supersede": KGRelation.OVERRIDES,
    "supersedes": KGRelation.OVERRIDES,
    "replaces": KGRelation.REPLACES,
    "substitute": KGRelation.REPLACES,
    "substitutes": KGRelation.REPLACES,
    # GOVERNED_BY family
    "governed by": KGRelation.GOVERNED_BY,
    "controlled by": KGRelation.GOVERNED_BY,
    "regulated by": KGRelation.GOVERNED_BY,
    "constrained by": KGRelation.GOVERNED_BY,
    "limited by": KGRelation.GOVERNED_BY,
    # REPLACES family
    "replace": KGRelation.REPLACES,
    "substitute for": KGRelation.REPLACES,
    "is alternative to": KGRelation.REPLACES,
    "is an alternative to": KGRelation.REPLACES,
}


def map_verb(verb_phrase: str) -> Optional[KGRelation]:
    """Map a verb phrase to KGRelation. Case-insensitive.

    Normalizes the verb phrase by lowercasing and stripping whitespace,
    then looks up in VERB_TO_RELATION mapping.

    Args:
        verb_phrase: The verb phrase extracted from text (e.g., "connects to")

    Returns:
        KGRelation if mapping found, None if no mapping (triggers LLM fallback)

    Examples:
        >>> map_verb("requires")
        <KGRelation.REQUIRES: 'requires'>
        >>> map_verb("connects to")
        <KGRelation.CONNECTS_TO: 'connects_to'>
        >>> map_verb("is an inductor")
        None
    """
    if not verb_phrase:
        return None

    # Normalize: lowercase and strip whitespace
    normalized = verb_phrase.strip().lower()

    # Direct lookup
    return VERB_TO_RELATION.get(normalized)
