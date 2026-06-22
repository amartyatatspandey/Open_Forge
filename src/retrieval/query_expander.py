"""
Expands component query strings using the electronics synonym dictionary
before vector encoding. Bidirectional: any synonym match triggers expansion
with all terms in that synonym group.

This is the auditable, air-gapped-compatible alternative to model fine-tuning
for handling technical term variation in electronics search.
"""
from __future__ import annotations
import yaml
from pathlib import Path
from functools import lru_cache


SYNONYMS_PATH = Path(__file__).parent / "synonyms.yaml"


@lru_cache(maxsize=1)
def _load_synonyms() -> list[dict]:
    with open(SYNONYMS_PATH) as f:
        data = yaml.safe_load(f)
    return data["synonyms"]


def expand_query(query_text: str) -> str:
    """
    Given a query string, returns an expanded version with all synonym
    terms added for any matching synonym group.

    Example:
        expand_query("chopper stabilized amplifier low noise")
        → "chopper stabilized amplifier low noise zero drift op amp
           auto zero amplifier autozero amplifier chopper op amp"

    The expanded string is passed to the encoder. The encoder sees all
    equivalent terms and produces a centroid embedding that covers the
    full synonym group.
    """
    query_lower = query_text.lower()
    additions: list[str] = []

    for entry in _load_synonyms():
        canonical = entry["canonical"]
        synonyms = entry.get("synonyms", [])
        all_terms = [canonical] + synonyms

        matched = any(term in query_lower for term in all_terms)
        if matched:
            # Add all terms not already present in the query
            for term in all_terms:
                if term not in query_lower and term not in additions:
                    additions.append(term)

    if not additions:
        return query_text

    return query_text + " " + " ".join(additions)


def expand_component_query_string(component_type: str, required_attributes: dict) -> str:
    """
    Builds and expands the full query string for a ComponentQuery.
    Used as input to vector_search before encoding.
    """
    base = component_type.replace("_", " ")
    attr_string = " ".join(
        f"{k.replace('_', ' ')} {v}" for k, v in required_attributes.items()
    )
    full = f"{base} {attr_string}".strip()
    return expand_query(full)
