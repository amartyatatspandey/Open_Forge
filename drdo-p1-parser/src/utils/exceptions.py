"""Custom exceptions for pipeline phases."""


class PipelineError(Exception):
    """Base exception for pipeline failures."""


class DLAError(PipelineError):
    """Phase 1 (DLA) failure."""


# Alias used in Phase 1 design docs
Phase1LayoutError = DLAError


class TSRError(PipelineError):
    """Phase 2 (TSR) failure."""


class ExtractionError(PipelineError):
    """Phase 3 semantic extraction failure."""


class ValidationError(PipelineError):
    """Phase 4 validation failure."""
