"""Unit tests for Phase 3 LLM stubs."""

from src.config import Config, Phase3ExtractConfig
from src.phase3_extract.extractor import Qwen25Extractor
from src.phase3_extract.prompt_templates import build_extraction_prompt
from tests.fixtures.phase2_mock_outputs import mock_tlv7021_electrical_grid


def test_build_extraction_prompt() -> None:
    grid = mock_tlv7021_electrical_grid()
    prompt = build_extraction_prompt(
        "electrical_characteristics",
        grid.rows,
        {"(1)": "Test footnote"},
    )
    assert "electrical characteristics" in prompt.lower()
    assert "V_CC" in prompt
    assert "(1)" in prompt


def test_llm_disabled_returns_none() -> None:
    Qwen25Extractor._instance = None
    config = Config(phase3_extract=Phase3ExtractConfig(llm_enabled=False))
    extractor = Qwen25Extractor.get_instance(config=config)
    grid = mock_tlv7021_electrical_grid()
    result = extractor.extract_via_llm(grid, "electrical_characteristics", config=config)
    assert result is None


def test_llm_extractor_singleton() -> None:
    Qwen25Extractor._instance = None
    a = Qwen25Extractor.get_instance()
    b = Qwen25Extractor.get_instance()
    assert a is b
