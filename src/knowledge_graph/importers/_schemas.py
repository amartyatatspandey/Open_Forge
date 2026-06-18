"""Internal schemas for knowledge graph importers.

Pydantic models for import operation results and batch processing status.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportResult(BaseModel):
    """Result of importing a single ComponentDatasheet into the knowledge graph.

    Tracks nodes created, edges created, duplicates skipped, placement rules
    imported, and any errors encountered during the import process.

    Attributes:
        component_id: The component ID that was imported
        nodes_created: Number of new nodes added to the graph
        edges_created: Number of new edges added to the graph
        skipped_duplicates: Number of nodes that already existed (updated in place)
        placement_rules_imported: Number of placement constraints converted to KG nodes
        import_errors: List of error messages encountered during import
        success: True if import completed without critical errors
    """

    component_id: str = Field(
        description="The component ID that was imported",
    )
    nodes_created: int = Field(
        default=0,
        ge=0,
        description="Number of new nodes added to the graph",
    )
    edges_created: int = Field(
        default=0,
        ge=0,
        description="Number of new edges added to the graph",
    )
    skipped_duplicates: int = Field(
        default=0,
        ge=0,
        description="Number of nodes that already existed (updated in place)",
    )
    placement_rules_imported: int = Field(
        default=0,
        ge=0,
        description="Number of placement constraints converted to KG nodes",
    )
    import_errors: list[str] = Field(
        default_factory=list,
        description="List of error messages encountered during import",
    )
    success: bool = Field(
        default=True,
        description="True if import completed without critical errors",
    )


class BatchImportResult(BaseModel):
    """Result of batch importing multiple ComponentDatasheets.

    Aggregates statistics across all individual import operations.

    Attributes:
        total_datasheets: Total number of datasheets in the batch
        successful: Number of successful imports
        failed: Number of failed imports
        results: List of individual ImportResult objects
        total_nodes_created: Total nodes created across all imports
        total_edges_created: Total edges created across all imports
    """

    total_datasheets: int = Field(
        ge=0,
        description="Total number of datasheets in the batch",
    )
    successful: int = Field(
        default=0,
        ge=0,
        description="Number of successful imports",
    )
    failed: int = Field(
        default=0,
        ge=0,
        description="Number of failed imports",
    )
    results: list[ImportResult] = Field(
        default_factory=list,
        description="List of individual ImportResult objects",
    )
    total_nodes_created: int = Field(
        default=0,
        ge=0,
        description="Total nodes created across all imports",
    )
    total_edges_created: int = Field(
        default=0,
        ge=0,
        description="Total edges created across all imports",
    )
