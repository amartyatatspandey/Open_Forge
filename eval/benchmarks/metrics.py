"""Metrics computation for the OpenForge eval benchmark."""

from __future__ import annotations

from typing import Literal
from eval.benchmarks.task_schema import BenchmarkTask, BenchmarkReport, TaskResult


def compute_pass_at_1(
    task: BenchmarkTask,
    results: list[TaskResult],
) -> bool:
    """True if the first attempt passed."""
    attempt_1 = next((r for r in results if r.attempt == 1), None)
    return attempt_1 is not None and attempt_1.passed


def compute_pass_at_n(
    task: BenchmarkTask,
    results: list[TaskResult],
) -> bool:
    """True if any attempt passed."""
    return any(r.passed for r in results)


def compute_report(
    tasks: list[BenchmarkTask],
    all_results: list[TaskResult],
    n_attempts: int,
    pipeline_label: str = "unnamed",
) -> BenchmarkReport:
    """Compute a BenchmarkReport from raw TaskResult objects.

    Args:
        tasks:          The full list of BenchmarkTask objects evaluated.
        all_results:    All TaskResult objects across all tasks and attempts.
        n_attempts:     Number of attempts per task.
        pipeline_label: Identifier for what pipeline was evaluated.

    Returns:
        BenchmarkReport with aggregated metrics.
    """
    from datetime import datetime, timezone

    results_by_task: dict[str, list[TaskResult]] = {}
    for r in all_results:
        results_by_task.setdefault(r.task_id, []).append(r)

    pass1_count  = 0
    passn_count  = 0
    erc_scores   = []
    failed_tasks = []

    difficulty_pass1: dict[str, list[bool]] = {"simple": [], "medium": [], "hard": []}

    for task in tasks:
        task_results = results_by_task.get(task.task_id, [])

        p1 = compute_pass_at_1(task, task_results)
        pn = compute_pass_at_n(task, task_results)

        if p1:
            pass1_count += 1
        if pn:
            passn_count += 1
        else:
            failed_tasks.append(task.task_id)

        attempt1 = next((r for r in task_results if r.attempt == 1), None)
        if attempt1:
            erc_scores.append(attempt1.erc_score)

        difficulty_pass1[task.difficulty].append(p1)

    n_tasks      = len(tasks)
    pass_at_1    = pass1_count / n_tasks if n_tasks else 0.0
    pass_at_n    = passn_count / n_tasks if n_tasks else 0.0
    mean_erc     = sum(erc_scores) / len(erc_scores) if erc_scores else 0.0

    by_difficulty = {
        diff: (sum(passes) / len(passes) if passes else 0.0)
        for diff, passes in difficulty_pass1.items()
    }

    return BenchmarkReport(
        tasks_run=n_tasks,
        n_attempts=n_attempts,
        pass_at_1=round(pass_at_1, 4),
        pass_at_n=round(pass_at_n, 4),
        mean_erc_score=round(mean_erc, 4),
        by_difficulty={k: round(v, 4) for k, v in by_difficulty.items()},
        task_results=all_results,
        failed_tasks=failed_tasks,
        run_timestamp=datetime.now(timezone.utc).isoformat(),
        pipeline_label=pipeline_label,
    )
