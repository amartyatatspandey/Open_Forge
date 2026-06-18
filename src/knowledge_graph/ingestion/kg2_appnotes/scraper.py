"""Application note PDF scraper.

Downloads TI/ADI application note PDFs listed in configs/sources.yaml.
Implements skip-if-exists logic for efficient re-runs.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, cast

import yaml

logger = logging.getLogger(__name__)

# PDF header magic bytes
PDF_MAGIC = b"%PDF"

# HTTP settings
REQUEST_TIMEOUT = 60  # seconds for large PDFs
USER_AGENT = "OpenForge-Scraper/1.0"


def _compute_filename_hash(name: str) -> str:
    """Compute hash of filename for change detection."""
    return hashlib.sha256(name.encode()).hexdigest()[:16]


def load_sources_config(config_path: Path) -> list[dict[str, Any]]:
    """Load app note sources from YAML config.
    
    Args:
        config_path: Path to sources.yaml file
        
    Returns:
        List of app note source dictionaries
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML is invalid
    """
    with open(config_path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return []
    return cast(list[dict[str, Any]], data.get("app_notes", []))


def _verify_pdf_header(file_path: Path) -> bool:
    """Verify file starts with PDF magic bytes.
    
    Args:
        file_path: Path to downloaded file
        
    Returns:
        True if valid PDF header
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
            return header == PDF_MAGIC
    except Exception as e:
        logger.warning(f"Failed to verify PDF header for {file_path}: {e}")
        return False


def _should_skip_download(name: str, output_dir: Path) -> bool:
    """Check if PDF already exists and is valid.
    
    Args:
        name: App note name (filename stem)
        output_dir: Directory containing downloaded PDFs
        
    Returns:
        True if file exists and should be skipped
    """
    pdf_path = output_dir / f"{name}.pdf"
    if not pdf_path.exists():
        return False
    
    # Verify it's a valid PDF
    if _verify_pdf_header(pdf_path):
        return True
    
    # File exists but invalid - re-download
    logger.warning(f"Existing file {pdf_path} has invalid PDF header, will re-download")
    return False


def download_pdf(
    name: str,
    url: str,
    output_dir: Path,
) -> tuple[bool, Path | None, str]:
    """Download a single PDF from URL.
    
    Args:
        name: App note name (used for filename)
        url: PDF download URL
        output_dir: Directory to save PDF
        
    Returns:
        Tuple of (success, pdf_path_or_none, error_message)
    """
    try:
        import requests
    except ImportError:
        return False, None, "requests library not installed"
    
    output_path = output_dir / f"{name}.pdf"
    
    try:
        headers = {"User-Agent": USER_AGENT}
        with requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()
            
            # Download with streaming for large files
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        
        # Verify download
        if not _verify_pdf_header(output_path):
            output_path.unlink(missing_ok=True)
            return False, None, "Downloaded file is not a valid PDF"
        
        logger.info(f"Downloaded {name} to {output_path}")
        return True, output_path, ""
        
    except requests.Timeout:
        return False, None, f"Timeout downloading {url}"
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        return False, None, f"HTTP error {status} for {url}"
    except requests.ConnectionError:
        return False, None, f"Connection error for {url}"
    except Exception as e:
        return False, None, f"Error downloading {url}: {e}"


def scrape_app_notes_from_config(
    config_path: Path,
    output_dir: Path,
) -> list[Path]:
    """Download app note PDFs from sources.yaml config.
    
    Skips PDFs already downloaded (checks by filename).
    Verifies PDF headers after download.
    Logs warnings and continues on failures.
    
    Args:
        config_path: Path to sources.yaml
        output_dir: Directory to save downloaded PDFs
        
    Returns:
        List of local PDF paths successfully downloaded
        
    Example:
        >>> paths = scrape_app_notes_from_config(
        ...     Path("configs/sources.yaml"),
        ...     Path("data/appnotes")
        ... )
        >>> len(paths)
        3
    """
    # Load sources
    try:
        sources = load_sources_config(config_path)
    except FileNotFoundError:
        logger.error(f"Sources config not found: {config_path}")
        return []
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in {config_path}: {e}")
        return []
    
    downloaded: list[Path] = []
    
    for source in sources:
        name = source.get("name")
        url = source.get("url")
        
        if not name or not url:
            logger.warning(f"Skipping invalid source entry: {source}")
            continue
        
        # Check if already downloaded
        if _should_skip_download(name, output_dir):
            pdf_path = output_dir / f"{name}.pdf"
            logger.debug(f"Skipping already downloaded: {name}")
            downloaded.append(pdf_path)
            continue
        
        # Download
        success, downloaded_path, error = download_pdf(name, url, output_dir)

        if success and downloaded_path:
            downloaded.append(downloaded_path)
        else:
            logger.warning(f"Failed to download {name}: {error}")
            # Continue to next source
            continue
    
    logger.info(f"Downloaded {len(downloaded)} app notes")
    return downloaded
