"""Benchmark task schema for the OpenForge search controller eval."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class BenchmarkTask(BaseModel):
    """One evaluation task for the search controller benchmark.

    task_id:              Unique identifier, e.g. "TASK_001".
    prompt:               The natural language design prompt.
    difficulty:           "simple" | "medium" | "hard"
    expected_component_types: Component types that MUST appear in the BOM.
                          Pass@1 requires all of these to be present.
    expected_topologies:  Topology names from TOPOLOGY_TEMPLATES that must
                          be detected in the generated netlist by Layer 4.
    min_erc_score:        Minimum acceptable ERC score to count as a pass.
                          1.0 = perfect. 0.9 = high bar. 0.8 = acceptable.
    source:               Where this task came from:
                          "scientist_log" | "corpus" | "canonical" | "manual"
    notes:                Optional human-readable notes for reviewers.
    """
    task_id:                  str
    prompt:                   str
    difficulty:               Literal["simple", "medium", "hard"]
    expected_component_types: list[str] = Field(default_factory=list)
    expected_topologies:      list[str] = Field(default_factory=list)
    min_erc_score:            float = Field(ge=0.0, le=1.0, default=0.90)
    source:                   str = "canonical"
    notes:                    Optional[str] = None


class TaskResult(BaseModel):
    """Result of running one benchmark task.

    task_id:       Matches BenchmarkTask.task_id.
    attempt:       Which attempt this is (1 to n_attempts).
    erc_score:     VerificationResult.score from the structural verifier.
    passed:        True if erc_score >= task.min_erc_score.
    component_types_found: Component types present in the generated BOM.
    topologies_found:      Topology names detected by Layer 4 verifier.
    error:         Exception message if the pipeline failed, else None.
    duration_s:    Wall-clock seconds for this attempt.
    """
    task_id:               str
    attempt:               int
    erc_score:             float
    passed:                bool
    component_types_found: list[str] = Field(default_factory=list)
    topologies_found:      list[str] = Field(default_factory=list)
    error:                 Optional[str] = None
    duration_s:            float = 0.0


class BenchmarkReport(BaseModel):
    """Aggregated results of a complete benchmark run.

    tasks_run:       Number of tasks evaluated.
    n_attempts:      Attempts per task (for Pass@N).
    pass_at_1:       Fraction of tasks passed on the first attempt.
    pass_at_n:       Fraction of tasks passed within n_attempts attempts.
    mean_erc_score:  Mean ERC score across all first attempts.
    by_difficulty:   Pass@1 broken down by difficulty level.
    task_results:    All TaskResult objects (all attempts, all tasks).
    failed_tasks:    task_ids where no attempt passed.
    run_timestamp:   ISO 8601 UTC timestamp of the run.
    pipeline_label:  Identifier for what pipeline was evaluated
                     (e.g., "baseline", "with_search_controller").
    """
    tasks_run:       int
    n_attempts:      int
    pass_at_1:       float
    pass_at_n:       float
    mean_erc_score:  float
    by_difficulty:   dict[str, float] = Field(default_factory=dict)
    task_results:    list[TaskResult] = Field(default_factory=list)
    failed_tasks:    list[str] = Field(default_factory=list)
    run_timestamp:   str
    pipeline_label:  str = "unnamed"
