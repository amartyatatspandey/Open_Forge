from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ComponentQuery(BaseModel):
    component_type: str
    required_attributes: dict[str, str]
    preferred_manufacturers: list[str] = Field(default_factory=list)
    source: str
    priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class DocumentQuery(BaseModel):
    query_type: Literal["datasheet", "app_note", "paper", "reference_design"]
    search_terms: list[str]
    target_url: Optional[str] = None
    doi: Optional[str] = None
    manufacturer: Optional[str] = None
    source: str


class RetrievalPlan(BaseModel):
    component_queries: list[ComponentQuery]
    document_queries: list[DocumentQuery]
    priority_order: list[str]
    topology_slugs: list[str]


class ComponentCandidate(BaseModel):
    component_id: str
    part_number: str
    manufacturer: str
    category: Optional[str] = None
    matched_query_type: str
    scores: dict[str, float]
    final_score: float
    matched_attributes: dict[str, str]
    missing_attributes: list[str]
    lifecycle_status: str
    source_layers: list[str]


class DocumentResult(BaseModel):
    document_id: str
    title: str
    doc_type: str
    relevance_score: float
    matched_terms: list[str]
    local_path: Optional[str] = None
    url: Optional[str] = None


class RetrievalResult(BaseModel):
    component_candidates: list[ComponentCandidate]
    document_results: list[DocumentResult]
    design_pattern_match: Optional[dict] = None
    kb_coverage: dict[str, bool]
    missing_components: list[str]
    retrieval_metadata: dict
