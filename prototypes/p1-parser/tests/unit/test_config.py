"""Test configuration loading and validation."""

import pytest

from src.config import Config, ConfidenceThresholds


class TestConfig:
    """Test Config class."""

    def test_load_default_yaml(self) -> None:
        """Load configs/default.yaml successfully."""
        config = Config.load("configs/default.yaml")
        config.validate()
        assert config.canonical_units.voltage == "V"
        assert config.thresholds.warn_downstream == 0.85
        assert config.pipeline.pdf_dpi == 300

    def test_threshold_ordering_validation(self) -> None:
        """block_extraction must be <= warn_downstream."""
        config = Config()
        config.thresholds = ConfidenceThresholds(
            block_extraction=0.90,
            warn_downstream=0.85,
        )
        with pytest.raises(ValueError, match="block_extraction threshold"):
            config.validate()

    def test_invalid_device_raises(self) -> None:
        """Device must be cuda or cpu."""
        config = Config()
        config.models.device = "tpu"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Invalid device"):
            config.validate()
