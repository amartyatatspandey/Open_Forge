from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from src.retrieval.coverage_reporter import (
    get_coverage_report,
    COMPONENT_TYPE_TO_PRIMARY_SYMBOL,
)
from src.retrieval.planner import build_retrieval_plan
from src.retrieval.schemas import (
    ComponentCandidate,
    DocumentQuery,
    DocumentResult,
    RetrievalResult,
)
from src.retrieval.search_layers import (
    fts_search,
    fuse_results,
    kg_traversal,
    parametric_search,
    vector_search,
)
from src.retrieval.freshness import DatasheetFreshnessChecker
from src.retrieval.kb_client import KBClient
from src.retrieval.qa_gate import QAGate
from src.schemas.intent import ImprovedIntentDict

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)


class RetrievalEngine:
    def __init__(self, db_url: str, config: "Config", encoder=None) -> None:
        self.kb = KBClient(db_url)
        self.config = config
        self.encoder = encoder
        self.freshness_checker = DatasheetFreshnessChecker()
        self.qa_gate = QAGate()

    def run_retrieval(self, intent: ImprovedIntentDict) -> RetrievalResult:
        start = time.monotonic()

        plan = build_retrieval_plan(intent)

        design_pattern_match = None
        for slug in plan.topology_slugs:
            pattern = self.kb.get_design_pattern(slug)
            if pattern:
                design_pattern_match = pattern
                break

        all_candidates: dict[str, list[ComponentCandidate]] = {}
        coverage_reports = []

        for cq in plan.component_queries:
            layer1 = parametric_search(cq, self.kb)
            primary_symbol = COMPONENT_TYPE_TO_PRIMARY_SYMBOL.get(cq.component_type)
            if primary_symbol:
                report = get_coverage_report(cq.component_type, primary_symbol, self.kb)
                coverage_reports.append(report)
            layer2 = fts_search(cq, self.kb)
            layer3 = vector_search(cq, self.kb, self.encoder)
            layer4 = kg_traversal(plan.topology_slugs, self.kb)

            fused = fuse_results(layer1, layer2, layer3, layer4)
            all_candidates[cq.component_type] = fused[:5]

        kb_coverage = {ct: len(cands) > 0 for ct, cands in all_candidates.items()}
        missing_components = [ct for ct, found in kb_coverage.items() if not found]

        air_gapped = getattr(self.config, "air_gapped", False)
        for missing_ct in missing_components:
            if air_gapped:
                self._route_to_review_queue(
                    component_type=missing_ct,
                    reason="Not in KB. System is air-gapped. Add datasheet manually.",
                    severity="WARNING",
                )
            else:
                logger.info(
                    "Component type '%s' not in KB. Scrape path would trigger here "
                    "(ingestion pipeline, out of Stage 3 scope).",
                    missing_ct,
                )

        document_results = self._retrieve_documents(plan.document_queries)

        all_flat = [c for cands in all_candidates.values() for c in cands]
        all_flat.sort(key=lambda c: c.final_score, reverse=True)

        elapsed = time.monotonic() - start

        return RetrievalResult(
            component_candidates=all_flat,
            document_results=document_results,
            design_pattern_match=design_pattern_match,
            kb_coverage=kb_coverage,
            missing_components=missing_components,
            retrieval_metadata={
                "elapsed_seconds": round(elapsed, 3),
                "plan_component_queries": len(plan.component_queries),
                "plan_document_queries": len(plan.document_queries),
                "topology_slugs": plan.topology_slugs,
                "layer_hit_counts": {
                    "parametric": sum(
                        1 for c in all_flat if "parametric" in c.source_layers
                    ),
                    "fts": sum(1 for c in all_flat if "fts" in c.source_layers),
                    "vector": sum(1 for c in all_flat if "vector" in c.source_layers),
                    "kg": sum(1 for c in all_flat if "kg" in c.source_layers),
                },
                "coverage_reports": [
                    {
                        "component_type": r.component_type,
                        "symbol": r.symbol,
                        "total_active_components": r.total_active_components,
                        "components_with_symbol_extracted": r.components_with_symbol_extracted,
                        "components_missing_symbol": r.components_missing_symbol,
                        "coverage_fraction": r.coverage_fraction,
                    }
                    for r in coverage_reports
                ],
            },
        )

    def _retrieve_documents(
        self, queries: list[DocumentQuery]
    ) -> list[DocumentResult]:
        seen: set[str] = set()
        results: list[DocumentResult] = []

        for dq in queries:
            if dq.doi:
                row = self.kb.execute(
                    """
                    SELECT id, title, doc_type, local_path, url
                    FROM documents
                    WHERE doi = %s AND ingestion_status = 'complete'
                    LIMIT 1
                    """,
                    (dq.doi,),
                )
                if row:
                    doc = row[0]
                    doc_id = str(doc["id"])
                    if doc_id not in seen:
                        seen.add(doc_id)
                        results.append(
                            DocumentResult(
                                document_id=doc_id,
                                title=doc["title"],
                                doc_type=doc["doc_type"],
                                relevance_score=1.0,
                                matched_terms=[dq.doi],
                                local_path=doc.get("local_path"),
                                url=doc.get("url"),
                            )
                        )
                continue

            fts_text = " ".join(dq.search_terms)
            rows = self.kb.execute(
                """
                SELECT id, title, doc_type, local_path, url,
                       ts_rank(
                           to_tsvector('english', title),
                           plainto_tsquery('english', %s)
                       ) AS rank
                FROM documents
                WHERE to_tsvector('english', title) @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT 20
                """,
                (fts_text, fts_text),
            )
            for row in rows:
                doc_id = str(row["id"])
                if doc_id in seen:
                    continue
                seen.add(doc_id)
                results.append(
                    DocumentResult(
                        document_id=doc_id,
                        title=row["title"],
                        doc_type=row["doc_type"],
                        relevance_score=float(row.get("rank") or 0.0),
                        matched_terms=dq.search_terms,
                        local_path=row.get("local_path"),
                        url=row.get("url"),
                    )
                )

        results.sort(key=lambda d: d.relevance_score, reverse=True)
        return results[:10]

    def _route_to_review_queue(
        self,
        component_type: str,
        reason: str,
        severity: str,
    ) -> None:
        priority = "HIGH" if severity == "WARNING" else "MEDIUM"
        self.kb.execute(
            """
            INSERT INTO review_queue (stage, severity, flags, status, priority)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                "stage3_retrieval",
                severity,
                json.dumps({"component_type": component_type, "reason": reason}),
                "pending",
                priority,
            ),
        )

    def close(self) -> None:
        self.kb.close()
