"""LLM extraction stub for future GPU-enabled Phase 3 path."""

from __future__ import annotations

import logging
from typing import Any

from src.config import Config, get_config
from src.phase3_extract.prompt_templates import build_extraction_prompt
from src.schemas.pipeline import GridMatrix, SectionType

logger = logging.getLogger(__name__)


class Qwen25Extractor:
    """Stateful Qwen2.5 extractor (lazy-loaded singleton)."""

    _instance: "Qwen25Extractor | None" = None

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or get_config()
        self._model = None

    @classmethod
    def get_instance(cls, config: Config | None = None) -> "Qwen25Extractor":
        """Return shared extractor instance."""
        if cls._instance is None:
            cls._instance = cls(config=config)
        return cls._instance

    def extract_via_llm(
        self,
        grid: GridMatrix,
        section_type: SectionType,
        footnote_map: dict[str, str] | None = None,
        config: Config | None = None,
    ) -> Any | None:
        """Extract structured data via Qwen2.5 + Instructor (disabled by default)."""
        cfg = config or self._config
        if not cfg.phase3_extract.llm_enabled:
            logger.debug("LLM extraction skipped (llm_enabled=False)")
            return None

        prompt = build_extraction_prompt(section_type, grid.rows, footnote_map)
        logger.info("LLM extraction prompt prepared (%d chars)", len(prompt))
        self._load_model()
        return None

    def _load_model(self) -> None:
        """Load Qwen2.5 model — only when llm_enabled."""
        if self._model is not None:
            return
        logger.info(
            "Loading Qwen2.5 from %s",
            self._config.models.local_llm_path,
        )
        self._model = True
