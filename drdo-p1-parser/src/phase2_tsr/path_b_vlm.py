"""Path B: VLM table extraction via Qwen2-VL."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from src.config import Config, get_config
from src.schemas.pipeline import GridMatrix, SectionType

logger = logging.getLogger(__name__)

_VLM_PROMPT_TEMPLATE = """You are a table extraction expert. Extract the table from this image as clean Markdown.

Output **ONLY** the Markdown table. No explanations. Example:

| Parameter | Min | Max | Unit |
|-----------|-----|-----|------|
| V_CC      | 1.8 | 5.5 | V    |
| I_CC      | — | 2.0 | mA   |

Table to extract (section: {section_type}):
"""


def parse_markdown_table(
    markdown: str,
    section_type: SectionType = "other",
    page_number: int = 0,
) -> GridMatrix:
    """Parse a markdown pipe table into a GridMatrix.

    Args:
        markdown: Raw markdown text containing a pipe table.
        section_type: Section type for the grid.
        page_number: Source page number.

    Returns:
        GridMatrix parsed from markdown rows.
    """
    rows: list[list[str]] = []
    for line in markdown.strip().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(re.match(r"^[-:]+$", c) for c in cells if c):
            continue
        rows.append(cells)

    num_cols = max((len(row) for row in rows), default=0)
    normalized = [row + [""] * (num_cols - len(row)) for row in rows]
    return GridMatrix(
        rows=normalized,
        num_rows=len(normalized),
        num_cols=num_cols,
        section_type=section_type,
        page_number=page_number,
        confidence=0.75,
        source="vlm_path_B",
    )


class Qwen2VLExtractor:
    """Stateful Qwen2-VL table extractor (lazy-loaded singleton)."""

    _instance: "Qwen2VLExtractor | None" = None

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or get_config()
        self._model = None
        self._processor = None

    @classmethod
    def get_instance(cls, config: Config | None = None) -> "Qwen2VLExtractor":
        """Return shared extractor instance."""
        if cls._instance is None:
            cls._instance = cls(config=config)
        return cls._instance

    def _load_model(self) -> None:
        """Load Qwen2-VL model and processor."""
        if self._model is not None:
            return
        from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
        import torch

        model_path = self._config.models.qwen2_vl_path
        dtype = getattr(torch, self._config.models.torch_dtype, torch.float16)
        logger.info("Loading Qwen2-VL from %s", model_path)
        self._processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True)
        self._model = Qwen2VLForConditionalGeneration.from_pretrained(
            str(model_path),
            torch_dtype=dtype,
            device_map=self._config.models.device,
            trust_remote_code=True,
        )

    def extract_table_via_vlm(
        self,
        image_bytes: bytes,
        section_type: SectionType,
        page_number: int = 0,
        config: Config | None = None,
    ) -> GridMatrix | None:
        """Extract table via Qwen2-VL markdown prompt.

        Args:
            image_bytes: PNG bytes of cropped table.
            section_type: Section context for prompt.
            page_number: Source page number.
            config: Optional config override.

        Returns:
            GridMatrix from VLM, or None if VLM disabled or failed.
        """
        cfg = config or self._config
        if not cfg.phase2_tsr.vlm_enabled:
            logger.debug("VLM path skipped (vlm_enabled=False)")
            return None

        try:
            from PIL import Image

            self._load_model()
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            prompt = _VLM_PROMPT_TEMPLATE.format(section_type=section_type)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self._processor(
                text=[text],
                images=[image],
                return_tensors="pt",
            ).to(self._model.device)
            output_ids = self._model.generate(**inputs, max_new_tokens=1024)
            generated = self._processor.batch_decode(
                output_ids, skip_special_tokens=True
            )[0]
            return parse_markdown_table(generated, section_type, page_number)
        except Exception as exc:
            logger.warning("VLM extraction failed: %s", exc)
            return None


def extract_table_via_vlm(
    image_bytes: bytes,
    section_type: SectionType,
    page_number: int = 0,
    config: Config | None = None,
) -> GridMatrix | None:
    """Convenience wrapper for VLM table extraction."""
    extractor = Qwen2VLExtractor.get_instance(config=config)
    return extractor.extract_table_via_vlm(
        image_bytes, section_type, page_number=page_number, config=config
    )
