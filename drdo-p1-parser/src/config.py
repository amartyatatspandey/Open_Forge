"""Global configuration for P1 datasheet parser.

This module centralizes all settings, thresholds, and constants.
Any part of the pipeline imports from here—never hardcode values elsewhere.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Literal, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CanonicalUnits:
    """Standard units for all electrical parameters."""

    voltage: str = "V"
    current: str = "mA"
    resistance: str = "Ω"
    capacitance: str = "pF"
    frequency: str = "MHz"
    temperature: str = "°C"
    time: str = "ns"


@dataclass
class SanityRanges:
    """Physical plausibility bounds for electrical parameters."""

    ranges: Dict[str, Tuple[str, float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize with sensible defaults if not provided."""
        if not self.ranges:
            self.ranges = {
                "V_CC": ("voltage", 0.5, 40.0),
                "V_GND": ("voltage", -0.5, 0.5),
                "V_DD": ("voltage", 0.5, 40.0),
                "I_CC": ("current", 0.001, 5000.0),
                "I_DD": ("current", 0.001, 5000.0),
                "T_J": ("temperature", -55.0, 175.0),
                "T_A": ("temperature", -40.0, 85.0),
            }


@dataclass
class ConfidenceThresholds:
    """Thresholds for data quality flags."""

    block_extraction: float = 0.70
    warn_downstream: float = 0.85
    require_approval: float = 0.60


@dataclass
class ModelConfig:
    """Paths and settings for offline ML models."""

    dla_model_path: Path = Path("models/yolov8_doclaynets.pt")
    dla_model_name: str = "yolov8_doclaynets"
    qwen2_vl_path: Path = Path("models/Qwen2-VL-7B-Instruct")
    qwen2_vl_model_name: str = "Qwen2-VL-7B-Instruct"
    local_llm_path: Path = Path("models/Qwen2.5-7B-Instruct")
    local_llm_model_name: str = "Qwen2.5-7B-Instruct"
    device: Literal["cuda", "cpu"] = "cuda"
    torch_dtype: str = "float16"
    batch_size: int = 4
    num_workers: int = 4


@dataclass
class PipelineConfig:
    """Paths and settings for pipeline I/O."""

    phase1_output_dir: Path = Path("output/phase1")
    phase2_output_dir: Path = Path("output/phase2")
    phase3_output_dir: Path = Path("output/phase3")
    phase4_output_dir: Path = Path("output/phase4")
    log_file: Path = Path("logs/pipeline.log")
    log_level: str = "INFO"
    pdf_dpi: int = 300
    pdf_fmt: str = "png"


@dataclass
class Phase1DLAConfig:
    """Phase 1 document layout analysis settings."""

    detection_confidence_min: float = 0.50
    table_iou_merge_threshold: float = 0.30
    table_width_match_tolerance: float = 0.15
    min_table_area_ratio: float = 0.04
    max_spec_page: int = 15
    expected_abs_max_printed_page: int = 5
    footnote_ocr_engine: str = "tesseract"
    section_keywords: Dict[str, list[str]] = field(default_factory=dict)
    max_tables_per_section: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize default section keyword mappings if not provided."""
        if not self.max_tables_per_section:
            self.max_tables_per_section = {
                "electrical_characteristics": 1,
                "absolute_maximum_ratings": 1,
                "pinout": 1,
                "timing": 1,
                "ordering": 1,
                "other": 0,
            }
        if not self.section_keywords:
            self.section_keywords = {
                "electrical_characteristics": [
                    "electrical characteristics",
                    "electrical specs",
                ],
                "absolute_maximum_ratings": ["absolute maximum", "abs max"],
                "pinout": ["pinout", "pin configuration", "pin functions", "pin definition"],
                "timing": ["timing characteristics", "switching characteristics"],
                "ordering": ["ordering information", "order information"],
            }


@dataclass
class Phase2TSRConfig:
    """Phase 2 table structure recognition settings."""

    vector_timeout_sec: int = 5
    vlm_timeout_sec: int = 60
    parallel_workers: int = 2
    camelot_flavor: Literal["lattice", "stream"] = "lattice"
    min_grid_rows: int = 2
    min_grid_cols: int = 2
    vector_source_bonus: float = 0.10
    max_empty_cell_ratio: float = 0.50
    vlm_enabled: bool = False


@dataclass
class Phase3ExtractConfig:
    """Phase 3 semantic extraction settings."""

    llm_enabled: bool = False
    min_parameter_confidence: float = 0.70


@dataclass
class Config:
    """Root configuration object."""

    canonical_units: CanonicalUnits = field(default_factory=CanonicalUnits)
    sanity_ranges: SanityRanges = field(default_factory=SanityRanges)
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    models: ModelConfig = field(default_factory=ModelConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    phase1_dla: Phase1DLAConfig = field(default_factory=Phase1DLAConfig)
    phase2_tsr: Phase2TSRConfig = field(default_factory=Phase2TSRConfig)
    phase3_extract: Phase3ExtractConfig = field(default_factory=Phase3ExtractConfig)

    @classmethod
    def load(cls, config_path: str = "configs/default.yaml") -> "Config":
        """Load configuration from YAML file.

        Args:
            config_path: Path to YAML config file.

        Returns:
            Initialized Config object.

        Raises:
            ValueError: If YAML is malformed.
        """
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning("Config not found at %s, using defaults", config_path)
            return cls()

        try:
            with open(config_file, encoding="utf-8") as file_handle:
                data: dict[str, Any] = yaml.safe_load(file_handle) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse {config_path}: {exc}") from exc

        logger.info("Loaded config from %s", config_path)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Config":
        """Build Config from a parsed YAML dictionary."""
        canonical_units = CanonicalUnits(**(data.get("canonical_units") or {}))

        sanity_data = data.get("sanity_ranges") or {}
        ranges: Dict[str, Tuple[str, float, float]] = {}
        for key, value in sanity_data.items():
            if isinstance(value, dict):
                ranges[key] = (value["type"], float(value["min"]), float(value["max"]))
            else:
                ranges[key] = value
        sanity_ranges = SanityRanges(ranges=ranges) if ranges else SanityRanges()

        thresholds = ConfidenceThresholds(**(data.get("confidence_thresholds") or {}))

        models_data = dict(data.get("models") or {})
        for path_key in ("dla_model_path", "qwen2_vl_path", "local_llm_path"):
            if path_key in models_data:
                models_data[path_key] = Path(models_data[path_key])
        models = ModelConfig(**models_data) if models_data else ModelConfig()

        pipeline_data = dict(data.get("pipeline") or {})
        for path_key in (
            "phase1_output_dir",
            "phase2_output_dir",
            "phase3_output_dir",
            "phase4_output_dir",
            "log_file",
        ):
            if path_key in pipeline_data:
                pipeline_data[path_key] = Path(pipeline_data[path_key])
        pipeline = PipelineConfig(**pipeline_data) if pipeline_data else PipelineConfig()

        phase1_data = data.get("phase1_dla") or {}
        phase1_dla = Phase1DLAConfig(**phase1_data) if phase1_data else Phase1DLAConfig()

        phase2_data = data.get("phase2_tsr") or {}
        phase2_tsr = Phase2TSRConfig(**phase2_data) if phase2_data else Phase2TSRConfig()

        phase3_data = data.get("phase3_extract") or {}
        phase3_extract = (
            Phase3ExtractConfig(**phase3_data) if phase3_data else Phase3ExtractConfig()
        )

        return cls(
            canonical_units=canonical_units,
            sanity_ranges=sanity_ranges,
            thresholds=thresholds,
            models=models,
            pipeline=pipeline,
            phase1_dla=phase1_dla,
            phase2_tsr=phase2_tsr,
            phase3_extract=phase3_extract,
        )

    def validate(self) -> None:
        """Sanity-check configuration values.

        Raises:
            ValueError: If any setting is invalid.
        """
        if self.thresholds.block_extraction > self.thresholds.warn_downstream:
            raise ValueError("block_extraction threshold must be <= warn_downstream threshold")
        if self.models.device not in ("cuda", "cpu"):
            raise ValueError(f"Invalid device: {self.models.device}")
        logger.info("Configuration validation passed")


_default_config: Config | None = None


def get_config() -> Config:
    """Get global config object (lazy-load on first use)."""
    global _default_config
    if _default_config is None:
        _default_config = Config.load("configs/default.yaml")
        _default_config.validate()
    return _default_config
