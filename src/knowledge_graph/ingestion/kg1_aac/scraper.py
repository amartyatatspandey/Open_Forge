"""All About Circuits web scraper.

Scrapes textbook chapters from AAC website with caching based on content hash.
Respects rate limiting (1.5 seconds between requests).
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.knowledge_graph.ingestion._schemas import ScrapedChapter

logger = logging.getLogger(__name__)

# AAC base URL
AAC_BASE_URL = "https://www.allaboutcircuits.com/textbook/"

# Volume to URL path mapping
VOLUME_PATHS: dict[int, str] = {
    1: "direct-current/",
    2: "alternating-current/",
    3: "semiconductors/",
    5: "reference/",
}

# Volumes in scope (1, 2, 3, 5 - Vol 4 is not relevant)
IN_SCOPE_VOLUMES: set[int] = {1, 2, 3, 5}

# HTTP request settings
REQUEST_TIMEOUT = 30
USER_AGENT = "OpenForge-Scraper/1.0"
RATE_LIMIT_DELAY = 1.5  # seconds between requests


def _compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of text content."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _get_chapter_url(volume: int, chapter: int) -> Optional[str]:
    """Construct chapter URL from volume and chapter number.

    Args:
        volume: Volume number
        chapter: Chapter number

    Returns:
        Full URL or None if volume not in scope
    """
    if volume not in IN_SCOPE_VOLUMES:
        return None

    path = VOLUME_PATHS.get(volume)
    if not path:
        return None

    # AAC URL pattern: /textbook/{volume_path}/ch-{chapter:02d}/
    return f"{AAC_BASE_URL}{path}ch-{chapter:02d}/"


def _get_cache_paths(output_dir: Path, volume: int, chapter: int) -> tuple[Path, Path]:
    """Get cache file paths for a chapter.

    Args:
        output_dir: Base output directory
        volume: Volume number
        chapter: Chapter number

    Returns:
        Tuple of (html_path, hash_path)
    """
    chapter_dir = output_dir / "aac" / f"vol{volume}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    html_path = chapter_dir / f"ch{chapter:02d}.html"
    hash_path = chapter_dir / f"ch{chapter:02d}.hash"

    return html_path, hash_path


def _check_cache(hash_path: Path, content_hash: str) -> bool:
    """Check if content hash matches cached hash.

    Args:
        hash_path: Path to cached hash file
        content_hash: Current content hash

    Returns:
        True if cache matches (can skip download)
    """
    if not hash_path.exists():
        return False

    try:
        cached_hash = hash_path.read_text().strip()
        return cached_hash == content_hash
    except Exception:
        return False


def _save_cache(html_path: Path, hash_path: Path, html: str, content_hash: str) -> None:
    """Save HTML and hash to cache.

    Args:
        html_path: Path to save HTML
        hash_path: Path to save hash
        html: Raw HTML content
        content_hash: Content hash
    """
    try:
        html_path.write_text(html, encoding='utf-8')
        hash_path.write_text(content_hash, encoding='utf-8')
    except Exception as e:
        logger.warning(f"Failed to save cache: {e}")


def _extract_chapter_info(html: str, url: str) -> tuple[str, str]:
    """Extract chapter title and main content from HTML.

    Args:
        html: Raw HTML
        url: Source URL for logging

    Returns:
        Tuple of (title, content_html)
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not available, returning raw HTML")
        return "Unknown Chapter", html

    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Try to find chapter title
        title = "Unknown Chapter"
        title_elem = soup.find('h1') or soup.find('title')
        if title_elem:
            title = title_elem.get_text().strip()

        # Find main article content
        # AAC typically uses article or main element with class
        content = ""
        main_elem = (
            soup.find('article') or
            soup.find('main') or
            soup.find('div', class_='content') or
            soup.find('div', id='content') or
            soup.find('body')
        )

        if main_elem:
            content = str(main_elem)
        else:
            content = html

        return title, content

    except Exception as e:
        logger.warning(f"Failed to extract chapter info from {url}: {e}")
        return "Unknown Chapter", html


def _count_words(text: str) -> int:
    """Count words in text."""
    words = text.split()
    return len(words)


def _fetch_url(url: str) -> tuple[bool, str, list[str]]:
    """Fetch URL with requests.

    Args:
        url: URL to fetch

    Returns:
        Tuple of (success, html_or_empty, errors)
    """
    errors: list[str] = []

    try:
        import requests
    except ImportError:
        errors.append("requests library not available")
        return False, "", errors

    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return True, response.text, errors

    except requests.Timeout:
        errors.append(f"Timeout fetching {url}")
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        errors.append(f"HTTP error {status} fetching {url}")
    except requests.ConnectionError:
        errors.append(f"Connection error fetching {url}")
    except Exception as e:
        errors.append(f"Error fetching {url}: {e}")

    return False, "", errors


def scrape_chapter(
    volume: int,
    chapter: int,
    output_dir: Path,
) -> tuple[Optional[ScrapedChapter], list[str]]:
    """Scrape a single chapter from AAC.

    Checks cache first using content hash. If unchanged, returns cached
    data without HTTP request. Otherwise fetches fresh content.

    Args:
        volume: Volume number (1, 2, 3, or 5)
        chapter: Chapter number within volume
        output_dir: Directory to store cached HTML and hashes

    Returns:
        Tuple of (ScrapedChapter or None, list of errors)
    """
    errors: list[str] = []

    # Validate volume
    if volume not in IN_SCOPE_VOLUMES:
        errors.append(f"Volume {volume} not in scope (1, 2, 3, 5)")
        return None, errors

    # Get URL
    url = _get_chapter_url(volume, chapter)
    if not url:
        errors.append(f"Could not construct URL for volume {volume}, chapter {chapter}")
        return None, errors

    # Get cache paths
    html_path, hash_path = _get_cache_paths(output_dir, volume, chapter)

    # Fetch content
    success, html, fetch_errors = _fetch_url(url)
    errors.extend(fetch_errors)

    if not success:
        # Try to use cached content if fetch failed
        if html_path.exists():
            logger.info(f"Using cached content for {url}")
            html = html_path.read_text(encoding='utf-8')
        else:
            return None, errors
    else:
        # Save to cache
        title, content_html = _extract_chapter_info(html, url)

        # Compute hash of cleaned content
        from src.knowledge_graph.ingestion.kg1_aac.cleaner import clean_html
        cleaned = clean_html(content_html)
        content_hash = _compute_content_hash(cleaned)

        # Check if unchanged
        if _check_cache(hash_path, content_hash):
            logger.info(f"Skipping unchanged: {url}")
            # Still need to return ScrapedChapter
            # Load from cache
            html = html_path.read_text(encoding='utf-8')
            title, content_html = _extract_chapter_info(html, url)
            cleaned = clean_html(content_html)
        else:
            # Save new cache
            _save_cache(html_path, hash_path, html, content_hash)
            logger.info(f"Cached chapter {volume}.{chapter}: {url}")

    # Process HTML to get title and content
    title, content_html = _extract_chapter_info(html, url)

    # Clean HTML to get plain text
    from src.knowledge_graph.ingestion.kg1_aac.cleaner import clean_html
    cleaned_text = clean_html(content_html)

    if not cleaned_text:
        errors.append(f"No text content extracted from {url}")
        return None, errors

    # Compute hash
    content_hash = _compute_content_hash(cleaned_text)

    # Count words
    word_count = _count_words(cleaned_text)

    # Create ScrapedChapter
    scraped_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    chapter_obj = ScrapedChapter(
        volume=volume,
        chapter_number=chapter,
        chapter_title=title,
        url=url,
        text=cleaned_text,
        content_hash=content_hash,
        word_count=word_count,
        scraped_at=scraped_at,
    )

    return chapter_obj, errors


def scrape_volume(
    volume: int,
    output_dir: Path,
    max_chapters: int = 100,
) -> tuple[list[ScrapedChapter], list[str]]:
    """Scrape all chapters from a volume.

    Continues through chapters until a 404 is encountered or max_chapters
    is reached. Respects rate limiting between requests.

    Args:
        volume: Volume number
        output_dir: Cache directory
        max_chapters: Maximum chapters to attempt per volume

    Returns:
        Tuple of (list of ScrapedChapter, list of errors)
    """
    chapters: list[ScrapedChapter] = []
    all_errors: list[str] = []

    logger.info(f"Scraping volume {volume}")

    for chapter_num in range(1, max_chapters + 1):
        chapter, errors = scrape_chapter(volume, chapter_num, output_dir)

        all_errors.extend(errors)

        if chapter is None:
            # Check if this was a 404 - if so, stop this volume
            if any("404" in e for e in errors):
                logger.info(f"Reached end of volume {volume} at chapter {chapter_num - 1}")
                break
            # Otherwise continue to next chapter
            continue

        chapters.append(chapter)

        # Rate limiting
        if chapter_num < max_chapters:
            time.sleep(RATE_LIMIT_DELAY)

    logger.info(f"Scraped {len(chapters)} chapters from volume {volume}")
    return chapters, all_errors
