"""Unit tests for Path B VLM extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.config import Config, Phase2TSRConfig
from src.phase2_tsr.path_b_vlm import Qwen2VLExtractor, extract_table_via_vlm, parse_markdown_table


def test_vlm_extraction_parsing() -> None:
    markdown = """
| A | B | C |
|---|---|---|
| 1 | 2 | 3 |
| 4 | 5 | 6 |
"""
    grid = parse_markdown_table(markdown, section_type="electrical_characteristics", page_number=5)
    assert grid.num_rows == 3
    assert grid.num_cols == 3
    assert grid.rows[0] == ["A", "B", "C"]


def test_vlm_disabled_returns_none() -> None:
    config = Config(phase2_tsr=Phase2TSRConfig(vlm_enabled=False))
    result = extract_table_via_vlm(
        b"\x89PNG\r\n",
        section_type="pinout",
        page_number=3,
        config=config,
    )
    assert result is None


def test_vlm_extractor_singleton() -> None:
    Qwen2VLExtractor._instance = None
    a = Qwen2VLExtractor.get_instance()
    b = Qwen2VLExtractor.get_instance()
    assert a is b


@patch("src.phase2_tsr.path_b_vlm.Qwen2VLExtractor._load_model")
def test_vlm_extractor_loads_model(mock_load: MagicMock) -> None:
    Qwen2VLExtractor._instance = None
    config = Config(phase2_tsr=Phase2TSRConfig(vlm_enabled=False))
    extractor = Qwen2VLExtractor(config=config)
    assert extractor is not None
    mock_load.assert_not_called()
