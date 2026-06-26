"""Benchmark runner for the OpenForge search controller eval.

The runner is pipeline-agnostic. The pipeline is injected as a callable
with signature:

    pipeline_fn(task: BenchmarkTask) -> tuple[float, list[str], list[str]]

Where the return value is:
    (erc_score, component_types_found, topologies_found)

This design allows:
- Mocked pipeline in CI (fast, no GPU)
- Real pipeline in GPU lab (slow, accurate)
- Baseline pipeline (no search controller) for comparison
- Full pipeline (with search controller) for evaluation
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from eval.benchmarks.metrics import compute_report
from eval.benchmarks.task_schema import (
    BenchmarkReport,
    BenchmarkTask,
    TaskResult,
)

logger = logging.getLogger(__name__)

# Type alias for the pipeline callable
PipelineFn = Callable[
    [BenchmarkTask],
    tuple[float, list[str], list[str]]
]


def _run_single_attempt(
    task: BenchmarkTask,
    pipeline_fn: PipelineFn,
    attempt: int,
) -> TaskResult:
    """Run one attempt of one task. Never raises."""
    start = time.perf_counter()
    try:
        erc_score, component_types_found, topologies_found = pipeline_fn(task)
        passed = (
            erc_score >= task.min_erc_score
            and all(
                any(ct in found.lower() for found in component_types_found)
                for ct in task.expected_component_types
            )
        )
        return TaskResult(
            task_id=task.task_id,
            attempt=attempt,
            erc_score=erc_score,
            passed=passed,
            component_types_found=component_types_found,
            topologies_found=topologies_found,
            duration_s=round(time.perf_counter() - start, 3),
        )
    except Exception as exc:
        logger.warning(
            "Benchmark task %s attempt %d failed: %s",
            task.task_id, attempt, exc,
        )
        return TaskResult(
            task_id=task.task_id,
            attempt=attempt,
            erc_score=0.0,
            passed=False,
            error=str(exc),
            duration_s=round(time.perf_counter() - start, 3),
        )


def run_benchmark(
    tasks: list[BenchmarkTask],
    pipeline_fn: PipelineFn,
    n_attempts: int = 5,
    pipeline_label: str = "unnamed",
    stop_on_pass: bool = True,
) -> BenchmarkReport:
    """Run the full benchmark.

    For each task, run up to n_attempts attempts.
    If stop_on_pass=True, stop early once a passing attempt is found.

    Args:
        tasks:          List of BenchmarkTask objects to evaluate.
        pipeline_fn:    Callable that runs the pipeline for one task.
        n_attempts:     Maximum attempts per task (for Pass@N metric).
        pipeline_label: Name tag for the report (e.g., "baseline", "with_controller").
        stop_on_pass:   Stop early when a task passes. Saves time.

    Returns:
        BenchmarkReport with Pass@1, Pass@N, and per-task results.
    """
    all_results: list[TaskResult] = []
    n_tasks = len(tasks)

    logger.info(
        "Benchmark starting. Tasks: %d, Attempts per task: %d, Pipeline: %s",
        n_tasks, n_attempts, pipeline_label,
    )

    for i, task in enumerate(tasks, 1):
        logger.info(
            "[%d/%d] Running task %s (%s): %s",
            i, n_tasks, task.task_id, task.difficulty,
            task.prompt[:60] + "..." if len(task.prompt) > 60 else task.prompt,
        )

        passed_this_task = False
        for attempt in range(1, n_attempts + 1):
            result = _run_single_attempt(task, pipeline_fn, attempt)
            all_results.append(result)

            logger.info(
                "  Attempt %d: ERC=%.4f, passed=%s",
                attempt, result.erc_score, result.passed,
            )

            if result.passed:
                passed_this_task = True
                if stop_on_pass:
                    break

        if not passed_this_task:
            logger.warning("Task %s: no passing attempt found.", task.task_id)

    report = compute_report(tasks, all_results, n_attempts, pipeline_label)

    logger.info(
        "Benchmark complete. Pass@1=%.2f%%, Pass@%d=%.2f%%, Mean ERC=%.4f",
        report.pass_at_1 * 100,
        n_attempts,
        report.pass_at_n * 100,
        report.mean_erc_score,
    )

    return report
