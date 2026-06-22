from __future__ import annotations

import logging
from typing import Any, Optional

from src.retrieval.kb_client import KBClient
from src.retrieval.schemas import ComponentCandidate, ComponentQuery

logger = logging.getLogger(__name__)

# Query prefix — applied ONLY when encoding search queries, never for documents
QWEN3_QUERY_PREFIX = (
    "Instruct: Retrieve relevant electronic components and datasheets.\n"
    "Query: "
)

# Document prefix — empty string. Documents are encoded without prefix.
QWEN3_DOC_PREFIX = ""

# RRF tuning parameter — k=60 is standard default.
# Do not change without a labeled eval set. See docs/DEPLOYMENT_NOTES.md.
RRF_K = 60

SYMBOL_MAP: dict[str, tuple[str, str]] = {
    "noise_nV_rtHz": ("en", "value_typ"),
    "vos_drift_uV_C": ("VOS_drift", "value_max"),
    "offset_drift_uV_C": ("VOS_drift", "value_max"),
    "psrr_dB": ("PSRR", "value_min"),
    "tempco_ppm_C": ("TC", "value_max"),
    "tolerance_pct": ("tol", "value_max"),
    "noise_uVrms": ("Vn", "value_typ"),
}


def _parse_comparison(value_str: str) -> tuple[str, float]:
    value_str = value_str.strip()
    if value_str.startswith("<="):
        return "<=", float(value_str[2:])
    if value_str.startswith(">="):
        return ">=", float(value_str[2:])
    if value_str.startswith("<"):
        return "<", float(value_str[1:])
    if value_str.startswith(">"):
        return ">", float(value_str[1:])
    if value_str.startswith("=="):
        return "=", float(value_str[2:])
    return "=", float(value_str)


def _build_parametric_sql(
    query: ComponentQuery,
) -> tuple[str, list[Any]]:
    if not query.required_attributes:
        sql = """
            SELECT DISTINCT c.id AS component_id, c.part_number, c.lifecycle_status,
                   m.name AS manufacturer_name, cc.name AS category_name
            FROM components c
            JOIN manufacturers m ON c.manufacturer_id = m.id
            LEFT JOIN component_categories cc ON c.category_id = cc.id
            WHERE c.lifecycle_status = 'active'
            LIMIT 20
        """
        return sql, []

    joins: list[str] = []
    conditions: list[str] = ["c.lifecycle_status = 'active'"]
    params: list[Any] = []

    for idx, (attr_key, attr_val) in enumerate(query.required_attributes.items()):
        alias = f"ep{idx}"
        if attr_key in SYMBOL_MAP:
            symbol, column = SYMBOL_MAP[attr_key]
        else:
            symbol, column = attr_key, "value_typ"

        op, num = _parse_comparison(attr_val)
        joins.append(
            f"""
            JOIN electrical_parameters {alias} ON {alias}.component_id = c.id
                AND {alias}.extraction_status = 'approved'
                AND {alias}.valid_to IS NULL
                AND {alias}.symbol = %s
                AND {alias}.{column} {op} %s
            """
        )
        params.extend([symbol, num])

    sql = f"""
        SELECT DISTINCT c.id AS component_id, c.part_number, c.lifecycle_status,
               m.name AS manufacturer_name, cc.name AS category_name
        FROM components c
        JOIN manufacturers m ON c.manufacturer_id = m.id
        LEFT JOIN component_categories cc ON c.category_id = cc.id
        {"".join(joins)}
        WHERE {" AND ".join(conditions)}
        LIMIT 20
    """
    return sql, params


def _row_to_candidate(
    row: dict,
    query: ComponentQuery,
    layer: str,
    score: float,
    kb: KBClient,
) -> ComponentCandidate:
    component_id = str(row["component_id"])
    params = kb.get_electrical_parameters(component_id)
    matched_attributes: dict[str, str] = {}
    missing_attributes: list[str] = []

    for attr_key in query.required_attributes:
        if attr_key in SYMBOL_MAP:
            symbol, column = SYMBOL_MAP[attr_key]
        else:
            symbol, column = attr_key, "value_typ"
        found = False
        for p in params:
            if p.get("symbol") == symbol:
                val = p.get(column)
                if val is not None:
                    matched_attributes[attr_key] = str(val)
                    found = True
                    break
        if not found:
            missing_attributes.append(attr_key)

    return ComponentCandidate(
        component_id=component_id,
        part_number=row.get("part_number", ""),
        manufacturer=row.get("manufacturer_name", ""),
        category=row.get("category_name"),
        matched_query_type=query.component_type,
        scores={layer: score},
        final_score=score,
        matched_attributes=matched_attributes,
        missing_attributes=missing_attributes,
        lifecycle_status=row.get("lifecycle_status", "active"),
        source_layers=[layer],
    )


def parametric_search(query: ComponentQuery, kb: KBClient) -> list[ComponentCandidate]:
    sql, params = _build_parametric_sql(query)
    rows = kb.execute(sql, tuple(params))
    return [
        _row_to_candidate(row, query, "parametric", 1.0, kb)
        for row in rows
    ]


def fts_search(query: ComponentQuery, kb: KBClient) -> list[ComponentCandidate]:
    fts_text = " ".join(
        [query.component_type.replace("_", " "), *query.required_attributes.keys()]
    )
    rows = kb.execute(
        """
        SELECT DISTINCT c.id AS component_id, c.part_number, c.lifecycle_status,
               m.name AS manufacturer_name, cc.name AS category_name,
               ts_rank(
                   to_tsvector('english', coalesce(c.description, '') || ' ' || c.part_number),
                   plainto_tsquery('english', %s)
               ) AS rank
        FROM components c
        JOIN manufacturers m ON c.manufacturer_id = m.id
        LEFT JOIN component_categories cc ON c.category_id = cc.id
        WHERE c.lifecycle_status = 'active'
          AND to_tsvector('english', coalesce(c.description, '') || ' ' || c.part_number)
              @@ plainto_tsquery('english', %s)
        ORDER BY rank DESC
        LIMIT 20
        """,
        (fts_text, fts_text),
    )
    return [
        _row_to_candidate(row, query, "fts", float(row.get("rank") or 0.0), kb)
        for row in rows
    ]


def vector_search(
    query: ComponentQuery,
    kb: KBClient,
    encoder,          # sentence-transformers model instance or None
) -> list[ComponentCandidate]:
    """
    Layer 3: Semantic vector search using Qwen3-Embedding-8B (4096-dim).

    Query expansion via synonyms.yaml runs before encoding.
    Query prefix is applied on query side only — document embeddings
    in the KB are stored without prefix.

    Degrades gracefully to empty list if encoder is None.
    """
    if encoder is None:
        logger.warning(
            "vector_search: encoder is None (model not loaded). "
            "Returning empty list. Layer 3 will not contribute to results."
        )
        return []

    from src.retrieval.query_expander import expand_component_query_string

    # 1. Build and expand query string
    raw_query = expand_component_query_string(
        query.component_type, query.required_attributes
    )

    # 2. Apply query prefix (query side only — asymmetric by design)
    prefixed_query = QWEN3_QUERY_PREFIX + raw_query

    # 3. Encode — Qwen3-Embedding requires prompt_name="query" or manual prefix
    # Use manual prefix approach for explicit control
    query_embedding = encoder.encode(
        prefixed_query,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    # Validate dimension
    expected_dim = 4096
    if len(query_embedding) != expected_dim:
        logger.error(
            "vector_search: embedding dimension mismatch. "
            "Expected %d, got %d. Check model config.",
            expected_dim, len(query_embedding)
        )
        return []

    # 4. Query pgvector with cosine similarity
    sql = """
        SELECT
            c.id::text AS component_id,
            c.part_number,
            m.name AS manufacturer,
            cc.full_path AS category,
            c.lifecycle_status,
            1 - (e.embedding <=> %s::vector) AS similarity
        FROM component_embeddings e
        JOIN components c ON e.component_id = c.id
        JOIN manufacturers m ON c.manufacturer_id = m.id
        LEFT JOIN component_categories cc ON c.category_id = cc.id
        WHERE 1 - (e.embedding <=> %s::vector) > 0.70
          AND c.lifecycle_status = 'active'
        ORDER BY similarity DESC
        LIMIT 20
    """

    embedding_list = query_embedding.tolist()
    rows = kb.execute(sql, (embedding_list, embedding_list))

    candidates = []
    for row in rows:
        candidates.append(ComponentCandidate(
            component_id=row["component_id"],
            part_number=row["part_number"],
            manufacturer=row["manufacturer"],
            category=row.get("category"),
            matched_query_type=query.component_type,
            scores={"vector": float(row["similarity"])},
            final_score=float(row["similarity"]),
            matched_attributes={},
            missing_attributes=[],
            lifecycle_status=row["lifecycle_status"],
            source_layers=["vector"],
        ))

    return candidates


def kg_traversal(
    topology_slugs: list[str],
    kb: KBClient,
) -> list[ComponentCandidate]:
    candidates: list[ComponentCandidate] = []

    for slug in topology_slugs:
        pattern = kb.get_design_pattern(slug)
        if not pattern:
            continue
        for role in pattern.get("required_roles", []):
            specific_id = role.get("specific_component_id")
            if specific_id is not None:
                details = kb.get_component_details(str(specific_id))
                if details:
                    candidates.append(
                        ComponentCandidate(
                            component_id=str(details["id"]),
                            part_number=details.get("part_number", ""),
                            manufacturer=details.get("manufacturer_name", ""),
                            category=details.get("category_name"),
                            matched_query_type=role.get("component_category", slug),
                            scores={"kg": 1.0},
                            final_score=1.0,
                            matched_attributes={},
                            missing_attributes=[],
                            lifecycle_status=details.get("lifecycle_status", "active"),
                            source_layers=["kg"],
                        )
                    )
            elif role.get("component_category"):
                sub_query = ComponentQuery(
                    component_type=role["component_category"],
                    required_attributes={},
                    source=f"kg_role:{role.get('role_name', '')}",
                    priority="MEDIUM",
                )
                for cand in parametric_search(sub_query, kb):
                    cand.scores = {"kg": 0.8}
                    cand.final_score = 0.8
                    cand.source_layers = ["kg"]
                    candidates.append(cand)

    return candidates


def fuse_results(
    parametric: list[ComponentCandidate],
    fts: list[ComponentCandidate],
    vector: list[ComponentCandidate],
    kg: list[ComponentCandidate],
) -> list[ComponentCandidate]:
    lists = [
        ("parametric", parametric),
        ("fts", fts),
        ("vector", vector),
        ("kg", kg),
    ]
    rrf_scores: dict[str, float] = {}
    merged: dict[str, ComponentCandidate] = {}

    for layer_name, layer_list in lists:
        for rank, cand in enumerate(layer_list, start=1):
            cid = cand.component_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rank + RRF_K)
            if cid not in merged:
                merged[cid] = cand.model_copy(deep=True)
            else:
                existing = merged[cid]
                existing.scores.update(cand.scores)
                if layer_name not in existing.source_layers:
                    existing.source_layers.append(layer_name)

    results: list[ComponentCandidate] = []
    for cid, cand in merged.items():
        cand.final_score = rrf_scores[cid]
        cand.source_layers = list(dict.fromkeys(cand.source_layers))
        results.append(cand)

    results.sort(key=lambda c: c.final_score, reverse=True)
    return results[:10]
