"""HTML to clean plain text cleaner for All About Circuits.

Removes navigation, ads, and HTML markup while preserving article content.
Normalizes whitespace and joins hyphenated line breaks.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Optional

logger = logging.getLogger(__name__)

# Tags to remove completely
TAGS_TO_REMOVE: set[str] = {
    "nav",
    "header",
    "footer",
    "aside",
    "script",
    "style",
    "figure",
    "figcaption",
}

# Class patterns indicating ads or non-content
AD_PATTERNS: tuple[str, ...] = (
    "advertisement",
    "ad-",
    "ads-",
    "sponsored",
    "promo",
    "promotion",
)


def _remove_tags(soup: Any, tags: set[str]) -> None:
    """Remove all elements with given tag names from soup."""
    for tag_name in tags:
        for element in soup.find_all(tag_name):
            element.decompose()


def _remove_ad_elements(soup: Any) -> None:
    """Remove elements that appear to be advertisements."""
    for element in soup.find_all(class_=True):
        class_str = " ".join(element.get("class", [])).lower()
        if any(pattern in class_str for pattern in AD_PATTERNS):
            element.decompose()


def _strip_specific_tags(html: str, tag_names: set[str]) -> str:
    """Remove specific HTML tags and their content using regex.
    
    Args:
        html: Raw HTML
        tag_names: Set of tag names to remove
    
    Returns:
        HTML with tags removed
    """
    result = html
    for tag in tag_names:
        # Pattern matches opening and closing tag with content in between
        # Non-greedy matching with re.DOTALL to handle multiline
        pattern = rf'<{tag}\b[^>]*>.*?</{tag}>'
        result = re.sub(pattern, ' ', result, flags=re.DOTALL | re.IGNORECASE)
        # Also handle self-closing tags
        pattern = rf'<{tag}\b[^>]*/?>'
        result = re.sub(pattern, ' ', result, flags=re.DOTALL | re.IGNORECASE)
    return result


def _strip_ad_classes(html: str) -> str:
    """Remove elements with ad-related class attributes.
    
    Args:
        html: Raw HTML
    
    Returns:
        HTML with ad elements removed
    """
    result = html
    for pattern in AD_PATTERNS:
        # Match elements with class containing ad pattern
        # Match: <tag class="...pattern...">content</tag>
        regex = rf'<[^>]*class="[^"]*{pattern}[^"]*"[^>]*>.*?</[^>]+>'
        result = re.sub(regex, ' ', result, flags=re.DOTALL | re.IGNORECASE)
    return result


def _strip_all_html_tags(html: str) -> str:
    """Remove all remaining HTML tags.
    
    Args:
        html: Raw HTML
    
    Returns:
        Plain text without HTML tags
    """
    return re.sub(r'<[^>]+>', ' ', html)


def _join_hyphenated_line_breaks(text: str) -> str:
    """Join hyphenated words across line breaks.

    Args:
        text: Raw text that may contain hyphenated line breaks

    Returns:
        Text with hyphenated line breaks joined ("resis-\ntor" → "resistor")
    """
    # Pattern: word hyphen followed by optional whitespace then newline then word continuation
    return re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.

    Collapses multiple spaces/newlines to single spaces,
    strips leading/trailing whitespace.

    Args:
        text: Text with arbitrary whitespace

    Returns:
        Text with normalized whitespace
    """
    # Replace newlines and multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    # Strip leading/trailing whitespace
    return text.strip()


def clean_html(html: str) -> str:
    """Clean HTML and return plain text.

    Removes navigation, ads, scripts, and styles.
    Joins hyphenated line breaks and normalizes whitespace.

    Args:
        html: Raw HTML string from web page

    Returns:
        Clean plain text with no HTML tags

    Example:
        >>> html = "<p>A resis-\ntor is a passive component.</p>"
        >>> clean_html(html)
        'A resistor is a passive component.'
    """
    if not html or not html.strip():
        return ""

    text = html
    bs4_available = False
    
    try:
        from bs4 import BeautifulSoup
        bs4_available = True
    except ImportError:
        logger.debug("BeautifulSoup not available, using regex-based cleaning")
    
    if bs4_available:
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove unwanted tags
            _remove_tags(soup, TAGS_TO_REMOVE)

            # Remove ad elements
            _remove_ad_elements(soup)

            # Extract text
            text = soup.get_text(separator=' ')
        except Exception as e:
            logger.warning(f"BeautifulSoup cleaning failed: {e}, using regex fallback")
            # Fall through to regex-based cleaning
            text = html
    
    # Regex-based cleaning (fallback or when BS4 unavailable)
    if not bs4_available or text == html:
        text = _strip_specific_tags(text, TAGS_TO_REMOVE)
        text = _strip_ad_classes(text)
        text = _strip_all_html_tags(text)

    # Join hyphenated line breaks
    text = _join_hyphenated_line_breaks(text)

    # Normalize whitespace
    text = _normalize_whitespace(text)

    return text
