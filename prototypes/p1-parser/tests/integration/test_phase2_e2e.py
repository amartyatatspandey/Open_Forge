"""Integration tests for Phase 2 TSR runner."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.phase2_tsr.runner import run_phase2
from tests.fixtures.phase1_mock_outputs import mock_phase1_output_tlv7021
from tests.fixtures.phase2_mock_outputs import (
    mock_tlv7021_absolute_max,
    mock_tlv7021_electrical_grid,
    mock_tlv7021_pinout_grid,
)


@pytest.fixture
def mock_grids():
    return [
        mock_tlv7021_absolute_max(),
        mock_tlv7021_electrical_grid(),
        mock_tlv7021_pinout_grid(),
    ]


@patch("src.phase2_tsr.runner.Qwen2VLExtractor")
@patch("src.phase2_tsr.runner.extract_table_via_vector")
def test_runner_with_mocks(mock_vector, mock_extractor_cls, mock_grids) -> None:
    vector_grids = [
        g.model_copy(update={"source": "vector_path_A"}) for g in mock_grids
    ]
    mock_vector.side_effect = vector_grids
    mock_extractor = mock_extractor_cls.get_instance.return_value
    mock_extractor.extract_table_via_vlm.return_value = None

    phase1_out = mock_phase1_output_tlv7021()
    phase2_out = run_phase2(phase1_out)

    assert phase2_out is not None
    assert len(phase2_out.grids) == 3
    assert phase2_out.pdf_path == phase1_out.pdf_path
    assert phase2_out.metadata["path_a_wins"] == 3
    assert all(g.num_cols > 0 for g in phase2_out.grids)
