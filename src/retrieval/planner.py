from __future__ import annotations

from src.retrieval.schemas import ComponentQuery, DocumentQuery, RetrievalPlan
from src.schemas.intent import ImprovedIntentDict

_PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

_IMPLICATION_MAP: dict[str, tuple[str, dict[str, str]]] = {
    "precision_voltage_reference": (
        "precision_voltage_reference",
        {"tempco_ppm_C": "<10", "noise_uVpp": "<10"},
    ),
    "low_noise_ldo": (
        "low_noise_ldo",
        {"noise_uVrms": "<10", "psrr_dB": ">60"},
    ),
    "zero_drift_op_amp": (
        "zero_drift_op_amp",
        {"vos_drift_uV_C": "<0.1", "noise_nV_rtHz": "<10"},
    ),
    "negative_rail_converter": (
        "negative_rail_converter",
        {"type": "inverting"},
    ),
    "passive_compensation_network": ("passive_component", {}),
    "precision_resistor_pair": (
        "precision_resistor",
        {"tempco_ppm_C": "<5", "tolerance_pct": "<0.01"},
    ),
}


def build_retrieval_plan(intent: ImprovedIntentDict) -> RetrievalPlan:
    component_queries: list[ComponentQuery] = []

    for req in intent.implied_requirements:
        implication = req.component_implication
        if implication is None or implication == "pcb_layout_constraint":
            continue

        if implication in _IMPLICATION_MAP:
            component_type, attrs_seed = _IMPLICATION_MAP[implication]
        else:
            component_type = implication
            attrs_seed = {}

        required_attributes = dict(attrs_seed)
        if (
            intent.performance
            and intent.performance.noise is not None
            and component_type == "zero_drift_op_amp"
            and "noise_nV_rtHz" not in required_attributes
        ):
            required_attributes["noise_nV_rtHz"] = "<10"

        component_queries.append(
            ComponentQuery(
                component_type=component_type,
                required_attributes=required_attributes,
                source=req.requirement[:100],
                priority=req.priority,
            )
        )

    component_queries.sort(key=lambda cq: _PRIORITY_RANK.get(cq.priority, 99))

    priority_order: list[str] = []
    seen: set[str] = set()
    for cq in component_queries:
        if cq.component_type not in seen:
            priority_order.append(cq.component_type)
            seen.add(cq.component_type)

    document_queries: list[DocumentQuery] = []
    topology_slugs = [t.name for t in intent.goal_topologies if t.confidence >= 0.6]

    for topology in intent.goal_topologies:
        if topology.confidence < 0.6:
            continue
        label = topology.name.replace("_", " ")
        document_queries.append(
            DocumentQuery(
                query_type="paper",
                search_terms=[f"{label} circuit design"],
                source=f"topology:{topology.name}",
            )
        )
        document_queries.append(
            DocumentQuery(
                query_type="app_note",
                search_terms=[f"{label} application note"],
                source=f"topology:{topology.name}",
            )
        )

    for cq in component_queries:
        if cq.priority in ("CRITICAL", "HIGH"):
            document_queries.append(
                DocumentQuery(
                    query_type="app_note",
                    search_terms=[f"{cq.component_type.replace('_', ' ')} selection guide"],
                    source=cq.source,
                )
            )

    return RetrievalPlan(
        component_queries=component_queries,
        document_queries=document_queries,
        priority_order=priority_order,
        topology_slugs=topology_slugs,
    )
