"""Gate tests for the eval benchmark runner and metrics."""
from __future__ import annotations

import pytest
from eval.benchmarks import (
    BENCHMARK_TASKS,
    TASKS_BY_ID,
    BenchmarkReport,
    BenchmarkTask,
    TaskResult,
    compute_report,
    run_benchmark,
    generate_report,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _perfect_pipeline(task: BenchmarkTask) -> tuple[float, list[str], list[str]]:
    """Mock pipeline that always returns perfect score."""
    found_types = list(task.expected_component_types)
    found_topos = list(task.expected_topologies)
    return (1.0, found_types, found_topos)


def _failing_pipeline(task: BenchmarkTask) -> tuple[float, list[str], list[str]]:
    """Mock pipeline that always returns 0.0 score."""
    return (0.0, [], [])


def _partial_pipeline(task: BenchmarkTask) -> tuple[float, list[str], list[str]]:
    """Mock pipeline that returns 0.85 ERC — passes medium/hard, not simple."""
    return (0.85, list(task.expected_component_types), [])


def _crashing_pipeline(task: BenchmarkTask) -> tuple[float, list[str], list[str]]:
    """Mock pipeline that raises an exception."""
    raise RuntimeError("GPU OOM")


# ── Task definitions ──────────────────────────────────────────────────────────

def test_benchmark_has_15_tasks():
    assert len(BENCHMARK_TASKS) == 15

def test_benchmark_has_5_simple():
    simple = [t for t in BENCHMARK_TASKS if t.difficulty == "simple"]
    assert len(simple) == 5

def test_benchmark_has_5_medium():
    medium = [t for t in BENCHMARK_TASKS if t.difficulty == "medium"]
    assert len(medium) == 5

def test_benchmark_has_5_hard():
    hard = [t for t in BENCHMARK_TASKS if t.difficulty == "hard"]
    assert len(hard) == 5

def test_all_task_ids_unique():
    ids = [t.task_id for t in BENCHMARK_TASKS]
    assert len(ids) == len(set(ids))

def test_tasks_by_id_covers_all():
    assert len(TASKS_BY_ID) == 15

def test_task_001_is_ldo():
    task = TASKS_BY_ID["TASK_001"]
    assert "ldo" in task.expected_topologies
    assert task.difficulty == "simple"

def test_task_011_is_from_scientist_log():
    task = TASKS_BY_ID["TASK_011"]
    assert task.source == "scientist_log"
    assert task.difficulty == "hard"

def test_all_tasks_have_prompts():
    for task in BENCHMARK_TASKS:
        assert len(task.prompt) > 10

def test_all_tasks_have_valid_min_erc_score():
    for task in BENCHMARK_TASKS:
        assert 0.0 <= task.min_erc_score <= 1.0


# ── TaskResult schema ─────────────────────────────────────────────────────────

def test_task_result_creation():
    r = TaskResult(
        task_id="TASK_001",
        attempt=1,
        erc_score=0.95,
        passed=True,
    )
    assert r.task_id == "TASK_001"
    assert r.passed is True


# ── run_benchmark ─────────────────────────────────────────────────────────────

def test_run_benchmark_returns_report():
    tasks = BENCHMARK_TASKS[:3]
    report = run_benchmark(tasks, _perfect_pipeline, n_attempts=1)
    assert isinstance(report, BenchmarkReport)

def test_run_benchmark_perfect_pipeline_pass_at_1():
    tasks = BENCHMARK_TASKS[:5]
    report = run_benchmark(tasks, _perfect_pipeline, n_attempts=1)
    assert report.pass_at_1 == 1.0

def test_run_benchmark_failing_pipeline_pass_at_1_is_zero():
    tasks = BENCHMARK_TASKS[:5]
    report = run_benchmark(tasks, _failing_pipeline, n_attempts=1)
    assert report.pass_at_1 == 0.0

def test_run_benchmark_crashing_pipeline_does_not_raise():
    tasks = BENCHMARK_TASKS[:3]
    report = run_benchmark(tasks, _crashing_pipeline, n_attempts=1)
    assert isinstance(report, BenchmarkReport)
    assert report.pass_at_1 == 0.0

def test_run_benchmark_tasks_run_count_matches():
    tasks = BENCHMARK_TASKS[:4]
    report = run_benchmark(tasks, _perfect_pipeline, n_attempts=1)
    assert report.tasks_run == 4

def test_run_benchmark_n_attempts_respected():
    tasks = BENCHMARK_TASKS[:2]
    report = run_benchmark(tasks, _failing_pipeline, n_attempts=3,
                           stop_on_pass=False)
    assert report.n_attempts == 3

def test_run_benchmark_stop_on_pass_reduces_results():
    tasks = BENCHMARK_TASKS[:3]
    # Perfect pipeline → stops after attempt 1 per task
    report = run_benchmark(tasks, _perfect_pipeline, n_attempts=5,
                           stop_on_pass=True)
    # Should have exactly 3 results (one per task, stopped after pass)
    assert len(report.task_results) == 3

def test_run_benchmark_pass_at_n_with_multiple_attempts():
    # Failing pipeline: never passes → pass_at_n = 0
    tasks = BENCHMARK_TASKS[:3]
    report = run_benchmark(tasks, _failing_pipeline, n_attempts=3)
    assert report.pass_at_n == 0.0

def test_run_benchmark_failed_tasks_listed():
    tasks = BENCHMARK_TASKS[:3]
    report = run_benchmark(tasks, _failing_pipeline, n_attempts=1)
    assert len(report.failed_tasks) == 3

def test_run_benchmark_pipeline_label_preserved():
    tasks = BENCHMARK_TASKS[:1]
    report = run_benchmark(tasks, _perfect_pipeline, n_attempts=1,
                           pipeline_label="test_label")
    assert report.pipeline_label == "test_label"

def test_run_benchmark_mean_erc_score_correct():
    tasks = BENCHMARK_TASKS[:1]
    report = run_benchmark(tasks, _perfect_pipeline, n_attempts=1)
    assert report.mean_erc_score == pytest.approx(1.0)


# ── compute_report ────────────────────────────────────────────────────────────

def test_compute_report_empty_tasks():
    report = compute_report([], [], n_attempts=1)
    assert report.tasks_run == 0
    assert report.pass_at_1 == 0.0

def test_compute_report_by_difficulty_all_keys():
    tasks = BENCHMARK_TASKS[:3]
    results = [
        TaskResult(task_id=t.task_id, attempt=1, erc_score=1.0, passed=True)
        for t in tasks
    ]
    report = compute_report(tasks, results, n_attempts=1)
    assert "simple" in report.by_difficulty
    assert "medium" in report.by_difficulty
    assert "hard" in report.by_difficulty


# ── generate_report ───────────────────────────────────────────────────────────

def test_generate_report_returns_string():
    tasks = BENCHMARK_TASKS[:3]
    report = run_benchmark(tasks, _perfect_pipeline, n_attempts=1)
    markdown = generate_report(report)
    assert isinstance(markdown, str)
    assert "Pass@1" in markdown

def test_generate_report_writes_file(tmp_path):
    tasks = BENCHMARK_TASKS[:2]
    report = run_benchmark(tasks, _perfect_pipeline, n_attempts=1)
    output = tmp_path / "report.md"
    generate_report(report, output_path=output)
    assert output.exists()
    content = output.read_text()
    assert "Pass@1" in content

def test_generate_report_includes_failed_tasks():
    tasks = BENCHMARK_TASKS[:3]
    report = run_benchmark(tasks, _failing_pipeline, n_attempts=1)
    markdown = generate_report(report)
    assert "Failed Tasks" in markdown
