#!/usr/bin/env python3
"""Download offline model weights for the P1 datasheet parser.

Downloads YOLOv8n-DocLayNet (Phase 1 DLA) and optionally Qwen2-VL / Qwen2.5
instruction models from Hugging Face. Logs to console and logs/download.log.

Usage:
    python scripts/download_models.py --yolo-only
    python scripts/download_models.py --all
    python scripts/download_models.py --qwen-only
    python scripts/download_models.py --yolo-only --force
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LOG_FILE = PROJECT_ROOT / "logs" / "download.log"
MODELS_DIR = PROJECT_ROOT / "models"

# YOLOv8n fine-tuned on DocLayNet (Ultralytics-compatible .pt, community weights on HF)
YOLO_SOURCE_URL = "https://huggingface.co/hantian/yolo-doclaynet/resolve/main/yolov8n-doclaynet.pt"
YOLO_DEST_NAME = "yolov8_doclaynets.pt"
YOLO_MIN_BYTES = 5_000_000
YOLO_MAX_BYTES = 20_000_000
YOLO_EXPECTED_BYTES = 6_340_000

QWEN2_VL_REPO = "Qwen/Qwen2-VL-7B-Instruct"
QWEN2_VL_DEST = MODELS_DIR / "Qwen2-VL-7B-Instruct"
QWEN2_VL_MIN_BYTES = 10_000_000_000

QWEN25_REPO = "Qwen/Qwen2.5-7B-Instruct"
QWEN25_DEST = MODELS_DIR / "Qwen2.5-7B-Instruct"
QWEN25_MIN_BYTES = 10_000_000_000

MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2.0
CHUNK_SIZE = 1024 * 1024
HF_MAX_WORKERS = 4


DownloadMode = Literal["yolo_only", "all", "qwen_only"]


@dataclass
class DownloadResult:
    """Result of a single model download attempt."""

    label: str
    path: Path
    success: bool
    bytes_written: int = 0
    skipped: bool = False
    message: str = ""


@dataclass
class DownloadSummary:
    """Aggregate download run summary."""

    results: list[DownloadResult] = field(default_factory=list)

    @property
    def downloaded_count(self) -> int:
        """Count successfully downloaded (non-skipped) artifacts."""
        return sum(1 for r in self.results if r.success and not r.skipped)

    @property
    def total_bytes(self) -> int:
        """Total bytes written across all results."""
        return sum(r.bytes_written for r in self.results)


def enable_hf_transfer() -> bool:
    """Enable high-performance Hugging Face downloads (Xet + parallel workers).

    Returns:
        True if acceleration packages are available, False for standard HTTP.
    """
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    try:
        import hf_transfer  # noqa: F401

        logger.info(
            "HF high-performance download enabled (hf_transfer + max_workers=%d)",
            HF_MAX_WORKERS,
        )
        return True
    except ImportError:
        logger.warning(
            "hf_transfer not installed — using Xet/parallel workers only. "
            "Install with: pip install hf_transfer"
        )
        return False


def setup_logging() -> None:
    """Configure logging to console and logs/download.log."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


logger = logging.getLogger(__name__)


def format_bytes(num_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if num_bytes >= 1_000_000_000:
        return f"{num_bytes / 1_000_000_000:.2f} GB"
    if num_bytes >= 1_000_000:
        return f"{num_bytes / 1_000_000:.2f} MB"
    if num_bytes >= 1_000:
        return f"{num_bytes / 1_000:.2f} KB"
    return f"{num_bytes} B"


def check_disk_space(required_bytes: int, target_dir: Path) -> None:
    """Verify sufficient free disk space.

    Args:
        required_bytes: Minimum bytes required.
        target_dir: Directory where files will be written.

    Raises:
        OSError: If insufficient disk space is available.
    """
    usage = shutil.disk_usage(target_dir)
    if usage.free < required_bytes:
        raise OSError(
            f"Insufficient disk space: need {format_bytes(required_bytes)}, "
            f"have {format_bytes(usage.free)} free on {target_dir}"
        )
    logger.info(
        "Disk space OK: %s free (need %s)",
        format_bytes(usage.free),
        format_bytes(required_bytes),
    )


def prompt_re_download(path: Path, force: bool) -> bool:
    """Ask user whether to re-download an existing file.

    Args:
        path: Existing file or directory path.
        force: If True, always re-download without prompting.

    Returns:
        True if download should proceed, False to skip.
    """
    if force:
        return True
    if not path.exists():
        return True
    if path.is_file() and path.stat().st_size == 0:
        return True

    answer = (
        input(f"{path} already exists ({format_bytes(_path_size(path))}). " "Re-download? [y/N]: ")
        .strip()
        .lower()
    )
    return answer in ("y", "yes")


def _path_size(path: Path) -> int:
    """Return file size or total size of directory tree."""
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def download_url_with_retry(
    url: str,
    dest: Path,
    expected_bytes: int | None = None,
    retries: int = MAX_RETRIES,
) -> int:
    """Download a file over HTTP with retries and progress reporting.

    Args:
        url: Source URL.
        dest: Destination file path.
        expected_bytes: Optional Content-Length hint for progress percentage.
        retries: Maximum number of attempts.

    Returns:
        Number of bytes written.

    Raises:
        OSError: On network failure after all retries.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers={"User-Agent": "drdo-p1-parser/0.1.0"})
            with urlopen(request, timeout=120) as response:
                total = int(response.headers.get("Content-Length", expected_bytes or 0))
                downloaded = 0
                temp_path = dest.with_suffix(dest.suffix + ".part")

                with open(temp_path, "wb") as file_handle:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        file_handle.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = 100.0 * downloaded / total
                            logger.info(
                                "Downloading %s: %s / %s (%.1f%%)",
                                dest.name,
                                format_bytes(downloaded),
                                format_bytes(total),
                                pct,
                            )
                        else:
                            logger.info(
                                "Downloading %s: %s",
                                dest.name,
                                format_bytes(downloaded),
                            )

                temp_path.replace(dest)
                logger.info(
                    "Saved %s (%s)",
                    dest,
                    format_bytes(downloaded),
                )
                return downloaded

        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            logger.warning(
                "Download attempt %d/%d failed for %s: %s",
                attempt,
                retries,
                url,
                exc,
            )
            if attempt < retries:
                sleep_sec = RETRY_BACKOFF_SEC * attempt
                logger.info("Retrying in %.1f seconds...", sleep_sec)
                time.sleep(sleep_sec)

    raise OSError(f"Failed to download {url} after {retries} attempts") from last_error


def verify_yolo_weights(path: Path) -> None:
    """Verify YOLO weight file size is within expected range.

    Raises:
        ValueError: If file size is outside expected bounds.
    """
    size = path.stat().st_size
    if not YOLO_MIN_BYTES <= size <= YOLO_MAX_BYTES:
        raise ValueError(
            f"YOLO weights size {format_bytes(size)} outside expected "
            f"{format_bytes(YOLO_MIN_BYTES)}–{format_bytes(YOLO_MAX_BYTES)}"
        )
    logger.info("YOLO verification passed: %s", format_bytes(size))


def _required_weight_files(path: Path) -> set[str]:
    """Return safetensors shard filenames required by the model index."""
    index_path = path / "model.safetensors.index.json"
    if index_path.exists():
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        return set(index_data.get("weight_map", {}).values())

    single = path / "model.safetensors"
    if single.exists():
        return {"model.safetensors"}
    return set()


def _missing_weight_files(path: Path) -> list[str]:
    """List weight shard files that are absent or empty."""
    missing: list[str] = []
    for filename in sorted(_required_weight_files(path)):
        shard = path / filename
        if not shard.exists() or shard.stat().st_size == 0:
            missing.append(filename)
    return missing


def clean_stale_hf_cache(dest: Path) -> int:
    """Remove zero-byte incomplete downloads and stale lock files.

    Args:
        dest: Model directory containing `.cache/huggingface/download/`.

    Returns:
        Number of stale artifacts removed.
    """
    cache_dir = dest / ".cache" / "huggingface" / "download"
    if not cache_dir.is_dir():
        return 0

    removed = 0
    for artifact in cache_dir.iterdir():
        if artifact.suffix == ".lock":
            artifact.unlink(missing_ok=True)
            removed += 1
            continue
        if artifact.name.endswith(".incomplete") and artifact.stat().st_size == 0:
            artifact.unlink(missing_ok=True)
            removed += 1
    if removed:
        logger.info("Cleaned %d stale HF cache artifact(s) in %s", removed, dest.name)
    return removed


def verify_qwen_directory(path: Path, min_bytes: int, label: str) -> None:
    """Verify a Qwen model directory is complete.

    Raises:
        ValueError: If directory is incomplete or missing required files.
    """
    if not path.is_dir():
        raise ValueError(f"{label} directory not found: {path}")

    config = path / "config.json"
    if not config.exists():
        raise ValueError(f"{label} missing config.json in {path}")

    missing = _missing_weight_files(path)
    if missing:
        raise ValueError(f"{label} missing weight shards: {', '.join(missing)}")

    total = _path_size(path)
    if total < min_bytes:
        raise ValueError(
            f"{label} size {format_bytes(total)} below minimum {format_bytes(min_bytes)}"
        )
    logger.info("%s verification passed: %s", label, format_bytes(total))


def _hf_resolve_url(repo_id: str, filename: str) -> str:
    """Build a direct Hugging Face resolve URL for a repository file."""
    return f"https://huggingface.co/{repo_id}/resolve/main/{filename}"


def _auth_headers() -> dict[str, str]:
    """Build HTTP headers including optional Hugging Face token."""
    headers = {"User-Agent": "drdo-p1-parser/0.1.0"}
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_remote_content_length(url: str) -> int | None:
    """Fetch Content-Length for a remote URL via HEAD request."""
    request = Request(url, headers=_auth_headers(), method="HEAD")
    with urlopen(request, timeout=60) as response:
        content_length = response.headers.get("Content-Length")
        return int(content_length) if content_length else None


def download_file_with_resume(url: str, dest: Path, label: str) -> int:
    """Download a large file with HTTP Range resume and progress logging.

    Args:
        url: Direct download URL.
        dest: Final destination path.
        label: Log label (usually filename).

    Returns:
        Total bytes in the completed file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest.with_suffix(dest.suffix + ".part")
    expected_total = get_remote_content_length(url)
    if expected_total:
        logger.info("Expected size for %s: %s", label, format_bytes(expected_total))

    resume_from = part_path.stat().st_size if part_path.exists() else 0
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = _auth_headers()
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"
                logger.info(
                    "Resuming %s from %s",
                    label,
                    format_bytes(resume_from),
                )

            request = Request(url, headers=headers)
            with urlopen(request, timeout=600) as response:
                status = getattr(response, "status", 200)
                if resume_from > 0 and status not in (200, 206):
                    part_path.unlink(missing_ok=True)
                    resume_from = 0
                    continue

                chunk_length = response.headers.get("Content-Length")
                if status == 206 and chunk_length:
                    total = int(chunk_length) + resume_from
                elif expected_total:
                    total = expected_total
                elif chunk_length:
                    total = int(chunk_length)
                else:
                    total = None

                mode = "ab" if resume_from > 0 else "wb"
                downloaded = resume_from

                with open(part_path, mode) as file_handle:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        file_handle.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = 100.0 * downloaded / total
                            if downloaded % (50 * CHUNK_SIZE) < CHUNK_SIZE:
                                logger.info(
                                    "%s: %s / %s (%.1f%%)",
                                    label,
                                    format_bytes(downloaded),
                                    format_bytes(total),
                                    pct,
                                )
                        elif downloaded % (50 * CHUNK_SIZE) < CHUNK_SIZE:
                            logger.info("%s: %s", label, format_bytes(downloaded))

            final_size = part_path.stat().st_size
            if expected_total and final_size < expected_total * 0.99:
                raise OSError(
                    f"Incomplete download for {label}: got {format_bytes(final_size)}, "
                    f"expected {format_bytes(expected_total)}"
                )

            part_path.replace(dest)
            logger.info("Shard complete: %s (%s)", label, format_bytes(final_size))
            return final_size

        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            resume_from = part_path.stat().st_size if part_path.exists() else 0
            logger.warning(
                "Download %s attempt %d/%d failed at %s: %s",
                label,
                attempt,
                MAX_RETRIES,
                format_bytes(resume_from),
                exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC * attempt)

    raise OSError(f"Failed to download {label} after {MAX_RETRIES} attempts") from last_error


def download_missing_shards(repo_id: str, dest: Path, label: str) -> int:
    """Download missing safetensors shards sequentially with HTTP resume.

    Args:
        repo_id: Hugging Face repository id.
        dest: Local model directory.
        label: Human-readable model name.

    Returns:
        Number of shards downloaded.
    """
    missing = _missing_weight_files(dest)
    if not missing:
        return 0

    logger.info(
        "%s: downloading %d missing shard(s) sequentially with resume",
        label,
        len(missing),
    )
    clean_stale_hf_cache(dest)

    for index, filename in enumerate(missing, start=1):
        logger.info("Shard %d/%d: %s", index, len(missing), filename)
        shard_path = dest / filename
        url = _hf_resolve_url(repo_id, filename)
        download_file_with_resume(url, shard_path, filename)

    return len(missing)


def download_yolo(force: bool, skip_existing: bool) -> DownloadResult:
    """Download YOLOv8n-DocLayNet weights.

    Args:
        force: Overwrite existing file without prompt (or with auto-yes).
        skip_existing: Skip if valid file already exists.

    Returns:
        DownloadResult for this artifact.
    """
    dest = MODELS_DIR / YOLO_DEST_NAME
    label = "YOLOv8n-DocLayNet"

    if dest.exists() and skip_existing and not force:
        try:
            verify_yolo_weights(dest)
            logger.info("Skipping %s — valid file exists at %s", label, dest)
            return DownloadResult(
                label=label,
                path=dest,
                success=True,
                bytes_written=0,
                skipped=True,
                message="Already present",
            )
        except ValueError:
            logger.warning("Existing YOLO file failed verification — re-downloading")

    if dest.exists() and not skip_existing and not prompt_re_download(dest, force):
        return DownloadResult(
            label=label,
            path=dest,
            success=True,
            bytes_written=0,
            skipped=True,
            message="User skipped re-download",
        )

    check_disk_space(YOLO_MAX_BYTES * 2, MODELS_DIR)
    logger.info("Downloading %s from %s", label, YOLO_SOURCE_URL)

    bytes_written = download_url_with_retry(
        YOLO_SOURCE_URL,
        dest,
        expected_bytes=YOLO_EXPECTED_BYTES,
    )
    verify_yolo_weights(dest)

    return DownloadResult(
        label=label,
        path=dest,
        success=True,
        bytes_written=bytes_written,
        message="Downloaded",
    )


def download_hf_snapshot(
    repo_id: str,
    dest: Path,
    label: str,
    min_bytes: int,
    force: bool,
    skip_existing: bool,
) -> DownloadResult:
    """Download a Hugging Face model repository via snapshot_download.

    Args:
        repo_id: Hugging Face repo id (e.g. Qwen/Qwen2-VL-7B-Instruct).
        dest: Local destination directory.
        label: Human-readable model name for logging.
        min_bytes: Minimum expected total download size.
        force: Force re-download.
        skip_existing: Skip if valid directory already exists.

    Returns:
        DownloadResult for this artifact.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise OSError(
            "huggingface_hub is required for Qwen downloads. "
            "Install with: pip install huggingface_hub"
        ) from exc

    if dest.exists() and skip_existing and not force:
        try:
            verify_qwen_directory(dest, min_bytes, label)
            logger.info("Skipping %s — valid directory exists at %s", label, dest)
            return DownloadResult(
                label=label,
                path=dest,
                success=True,
                bytes_written=0,
                skipped=True,
                message="Already present",
            )
        except ValueError:
            logger.warning("Existing %s failed verification — re-downloading", label)

    if dest.exists() and not skip_existing and not prompt_re_download(dest, force):
        return DownloadResult(
            label=label,
            path=dest,
            success=True,
            bytes_written=0,
            skipped=True,
            message="User skipped re-download",
        )

    check_disk_space(min_bytes + 2_000_000_000, MODELS_DIR)
    logger.warning(
        "%s is ~15 GB+. Download may take a long time and requires stable network.",
        label,
    )

    dest.mkdir(parents=True, exist_ok=True)
    clean_stale_hf_cache(dest)

    size_before = _path_size(dest) if dest.exists() else 0
    if size_before > 0:
        logger.info(
            "Resuming %s from %s already on disk",
            label,
            format_bytes(size_before),
        )

    missing_before = _missing_weight_files(dest)
    has_metadata = (dest / "config.json").exists() and (
        dest / "model.safetensors.index.json"
    ).exists()

    if has_metadata and missing_before and not force:
        logger.info(
            "%s: metadata present, fetching %d missing shard(s) directly",
            label,
            len(missing_before),
        )
        download_missing_shards(repo_id, dest, label)
    else:
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(dest),
            force_download=force,
            max_workers=HF_MAX_WORKERS,
        )
        missing_after = _missing_weight_files(dest)
        if missing_after:
            logger.warning(
                "%s incomplete after snapshot (%s) — fetching shards sequentially",
                label,
                ", ".join(missing_after),
            )
            clean_stale_hf_cache(dest)
            download_missing_shards(repo_id, dest, label)

    verify_qwen_directory(dest, min_bytes, label)
    bytes_written = max(_path_size(dest) - size_before, 0)

    return DownloadResult(
        label=label,
        path=dest,
        success=True,
        bytes_written=bytes_written,
        message="Downloaded",
    )


def verify_yolo_inference(weights_path: Path) -> None:
    """Optional smoke test: load YOLO weights with Ultralytics.

    Args:
        weights_path: Path to .pt weights file.
    """
    try:
        from ultralytics import YOLO

        model = YOLO(str(weights_path))
        logger.info(
            "YOLO load test passed — model type: %s, task: %s",
            type(model).__name__,
            getattr(model, "task", "detect"),
        )
    except Exception as exc:
        logger.warning("YOLO load test failed (weights saved but may need review): %s", exc)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download offline model weights for drdo-p1-parser.",
    )
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--yolo-only",
        action="store_true",
        help="Download YOLOv8n-DocLayNet only (default).",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Download YOLO + Qwen2-VL-7B + Qwen2.5-7B-Instruct.",
    )
    mode.add_argument(
        "--qwen-only",
        action="store_true",
        help="Download Qwen models only (skip YOLO).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if files already exist (no prompt).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip download when valid files already exist (default: True).",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Prompt before overwriting existing files.",
    )
    parser.add_argument(
        "--verify-yolo",
        action="store_true",
        default=True,
        help="Run Ultralytics load test after YOLO download (default: True).",
    )
    parser.add_argument(
        "--no-verify-yolo",
        action="store_false",
        dest="verify_yolo",
        help="Skip Ultralytics load test after YOLO download.",
    )
    return parser.parse_args()


def resolve_mode(args: argparse.Namespace) -> DownloadMode:
    """Resolve download mode from CLI flags."""
    if args.all:
        return "all"
    if args.qwen_only:
        return "qwen_only"
    return "yolo_only"


def run_downloads(mode: DownloadMode, force: bool, skip_existing: bool) -> DownloadSummary:
    """Execute downloads for the selected mode.

    Args:
        mode: Which models to download.
        force: Force re-download.
        skip_existing: Skip valid existing artifacts.

    Returns:
        DownloadSummary with per-artifact results.
    """
    summary = DownloadSummary()
    download_fns: list[Callable[[], DownloadResult]] = []

    if mode in ("yolo_only", "all"):
        download_fns.append(lambda: download_yolo(force, skip_existing))
    if mode in ("qwen_only", "all"):
        download_fns.extend(
            [
                lambda: download_hf_snapshot(
                    QWEN2_VL_REPO,
                    QWEN2_VL_DEST,
                    "Qwen2-VL-7B-Instruct",
                    QWEN2_VL_MIN_BYTES,
                    force,
                    skip_existing,
                ),
                lambda: download_hf_snapshot(
                    QWEN25_REPO,
                    QWEN25_DEST,
                    "Qwen2.5-7B-Instruct",
                    QWEN25_MIN_BYTES,
                    force,
                    skip_existing,
                ),
            ]
        )

    for download_fn in download_fns:
        try:
            result = download_fn()
            summary.results.append(result)
        except (OSError, ValueError) as exc:
            logger.error("Download failed: %s", exc)
            summary.results.append(
                DownloadResult(
                    label="unknown",
                    path=MODELS_DIR,
                    success=False,
                    message=str(exc),
                )
            )

    return summary


def print_summary(summary: DownloadSummary) -> None:
    """Print final download summary to console."""
    total_gb = summary.total_bytes / 1_000_000_000
    logger.info(
        "Downloaded %d file(s)/model(s), total %s (%.2f GB)",
        summary.downloaded_count,
        format_bytes(summary.total_bytes),
        total_gb,
    )
    for result in summary.results:
        status = "OK" if result.success else "FAILED"
        skip_note = " (skipped)" if result.skipped else ""
        logger.info(
            "  [%s] %s -> %s%s — %s",
            status,
            result.label,
            result.path,
            skip_note,
            result.message,
        )


def main() -> int:
    """Entry point."""
    setup_logging()
    args = parse_args()
    mode = resolve_mode(args)

    logger.info("Model download started — mode=%s, project_root=%s", mode, PROJECT_ROOT)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    enable_hf_transfer()

    summary = run_downloads(mode, force=args.force, skip_existing=args.skip_existing)

    yolo_result = next(
        (r for r in summary.results if r.label == "YOLOv8n-DocLayNet" and r.success),
        None,
    )
    if yolo_result and not yolo_result.skipped and args.verify_yolo:
        verify_yolo_inference(yolo_result.path)

    print_summary(summary)

    failed = [r for r in summary.results if not r.success]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
