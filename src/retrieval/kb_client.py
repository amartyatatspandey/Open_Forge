from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

if TYPE_CHECKING:
    from src.retrieval.qa_gate import QAResult


class KBClient:
    def __init__(self, database_url: str) -> None:
        self._conn = psycopg2.connect(database_url)
        self._conn.autocommit = True

    def execute(self, query: str, params: Optional[tuple | list] = None) -> list[dict]:
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            if cur.description is None:
                return []
            return [dict(row) for row in cur.fetchall()]

    def get_component_by_part_number(self, part_number: str) -> Optional[dict]:
        rows = self.execute(
            """
            SELECT c.*, m.name AS manufacturer_name
            FROM components c
            JOIN manufacturers m ON c.manufacturer_id = m.id
            WHERE c.part_number = %s
            LIMIT 1
            """,
            (part_number,),
        )
        return rows[0] if rows else None

    def get_electrical_parameters(self, component_id: str) -> list[dict]:
        return self.execute(
            """
            SELECT *
            FROM electrical_parameters
            WHERE component_id = %s
              AND extraction_status = 'approved'
              AND valid_to IS NULL
            """,
            (component_id,),
        )

    def store_component_with_qa(
        self,
        component_data: dict,
        parameters: list[dict],
        qa_result: "QAResult",
    ) -> str:
        extraction_status = "approved" if qa_result.passed else "needs_review"
        component_id = component_data.get("id") or str(uuid.uuid4())

        self.execute(
            """
            INSERT INTO components (
                id, manufacturer_id, part_number, part_number_clean, part_number_base,
                category_id, description, lifecycle_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (manufacturer_id, part_number) DO UPDATE
            SET description = EXCLUDED.description
            RETURNING id
            """,
            (
                component_id,
                component_data["manufacturer_id"],
                component_data["part_number"],
                component_data.get("part_number_clean"),
                component_data.get("part_number_base"),
                component_data.get("category_id"),
                component_data.get("description"),
                component_data.get("lifecycle_status", "active"),
            ),
        )

        for param in parameters:
            self.execute(
                """
                INSERT INTO electrical_parameters (
                    component_id, parameter_name, symbol, section_type, conditions,
                    value_min, value_typ, value_max, unit, unit_raw, raw_text,
                    footnote, confidence, extraction_method, extraction_status,
                    source_document_id, source_page, source_table_index
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    component_id,
                    param.get("parameter_name"),
                    param.get("symbol"),
                    param.get("section_type"),
                    param.get("conditions"),
                    param.get("value_min"),
                    param.get("value_typ"),
                    param.get("value_max"),
                    param.get("unit"),
                    param.get("unit_raw"),
                    param.get("raw_text"),
                    param.get("footnote"),
                    param.get("confidence", 0.0),
                    param.get("extraction_method"),
                    extraction_status,
                    param.get("source_document_id"),
                    param.get("source_page"),
                    param.get("source_table_index"),
                ),
            )

        if not qa_result.passed:
            self.execute(
                """
                INSERT INTO review_queue (stage, severity, flags, status, priority)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    "stage3_ingestion",
                    "WARNING",
                    json.dumps({"component_id": component_id, "qa_failed": True}),
                    "pending",
                    "HIGH",
                ),
            )

        return str(component_id)

    def get_document_by_doi(self, doi: str) -> Optional[dict]:
        rows = self.execute(
            "SELECT * FROM documents WHERE doi = %s LIMIT 1",
            (doi,),
        )
        return rows[0] if rows else None

    def get_design_pattern(self, topology_type: str) -> Optional[dict]:
        rows = self.execute(
            """
            SELECT id, name, description, topology_type
            FROM design_patterns
            WHERE topology_type = %s
            LIMIT 1
            """,
            (topology_type,),
        )
        if not rows:
            return None
        pattern = rows[0]
        roles = self.execute(
            """
            SELECT id, role_name, component_category, specific_component_id,
                   is_critical, selection_criteria, typical_value
            FROM design_pattern_roles
            WHERE pattern_id = %s
            """,
            (str(pattern["id"]),),
        )
        return {
            "pattern_id": str(pattern["id"]),
            "pattern_name": pattern["name"],
            "required_roles": [dict(r) for r in roles],
        }

    def get_component_details(self, component_id: str) -> Optional[dict]:
        rows = self.execute(
            """
            SELECT c.id, c.part_number, c.lifecycle_status, c.description,
                   m.name AS manufacturer_name,
                   cc.name AS category_name
            FROM components c
            JOIN manufacturers m ON c.manufacturer_id = m.id
            LEFT JOIN component_categories cc ON c.category_id = cc.id
            WHERE c.id = %s
            LIMIT 1
            """,
            (component_id,),
        )
        return rows[0] if rows else None

    def close(self) -> None:
        self._conn.close()
