"""Footnote linking for Phase 1 DLA.

Links superscript markers to their corresponding footnote definitions
using regex pattern matching and spatial proximity heuristics.

Supports patterns like:
- (1), (2), (3) ... numbered markers
- *, **, †, ‡ ... symbol markers
- Superscript letters (a), (b), (c)
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.datasheet.phase1_dla._schemas import FootnoteMap

logger = logging.getLogger(__name__)

# Regex patterns for footnote markers
_SUPERSCRIPT_NUMBER_PATTERN: re.Pattern[str] = re.compile(
    r"\((\d+)\)",  # Matches (1), (2), (3), etc.
)

_SUPERSCRIPT_SYMBOL_PATTERN: re.Pattern[str] = re.compile(
    r"([\*\†\‡\§\¶\#\+]+)",  # Matches *, **, †, ‡, etc.
)

_SUPERSCRIPT_LETTER_PATTERN: re.Pattern[str] = re.compile(
    r"\(([a-z])\)",  # Matches (a), (b), (c), etc. (lowercase only)
    re.IGNORECASE,
)


def _find_footnote_markers(text: str) -> list[tuple[str, int]]:
    """Find all footnote marker positions in text.

    Args:
        text: Page text content (OCR or extracted)

    Returns:
        List of (marker, position) tuples where marker is the
        superscript identifier without parentheses (e.g., "1" for "(1)")
    """
    markers: list[tuple[str, int]] = []

    # Find numbered markers (1), (2), etc.
    for match in _SUPERSCRIPT_NUMBER_PATTERN.finditer(text):
        marker = match.group(1)  # The number inside parentheses
        position = match.start()
        markers.append((marker, position))

    # Find symbol markers *, **, †, etc.
    for match in _SUPERSCRIPT_SYMBOL_PATTERN.finditer(text):
        marker = match.group(1)
        position = match.start()
        markers.append((marker, position))

    # Find letter markers (a), (b), etc.
    for match in _SUPERSCRIPT_LETTER_PATTERN.finditer(text):
        marker = match.group(1).lower()
        position = match.start()
        markers.append((marker, position))

    # Sort by position in text
    markers.sort(key=lambda x: x[1])
    return markers


def _extract_footnote_definitions(
    text: str,
    markers: list[tuple[str, int]],
) -> dict[str, str]:
    """Extract footnote definition text following each marker.

    Uses spatial heuristics to associate text following markers
    as the footnote definition.

    Args:
        text: Full page text content
        markers: List of (marker, position) tuples

    Returns:
        Dictionary mapping marker -> footnote definition text
    """
    entries: dict[str, str] = {}

    for i, (marker, start_pos) in enumerate(markers):
        # Find the end of this footnote (start of next or end of text)
        if i + 1 < len(markers):
            next_pos = markers[i + 1][1]
        else:
            next_pos = len(text)

        # Extract text after the marker itself
        marker_end = start_pos + len(f"({marker})") if marker.isdigit() or len(marker) == 1 else start_pos + len(marker)

        # Skip the marker and get the definition text
        definition_start = marker_end
        while definition_start < len(text) and text[definition_start] in " \t\n)]:":
            definition_start += 1

        definition = text[definition_start:next_pos].strip()

        # Clean up the definition (remove newlines, extra spaces)
        definition = " ".join(definition.split())

        if definition:
            entries[marker] = definition
            logger.debug(f"Linked marker ({marker}) -> '{definition[:50]}...'")

    return entries


def _link_page_footnotes(
    page_text: str,
    page_number: int,
) -> FootnoteMap:
    """Link all footnotes on a single page.

    Args:
        page_text: Full text content of the page
        page_number: 1-indexed page number

    Returns:
        FootnoteMap with all linked footnotes for this page
    """
    markers = _find_footnote_markers(page_text)

    if not markers:
        logger.debug(f"Page {page_number}: No footnote markers found")
        return FootnoteMap(page_number=page_number, entries={})

    entries = _extract_footnote_definitions(page_text, markers)

    logger.info(f"Page {page_number}: Linked {len(entries)} footnotes")
    return FootnoteMap(page_number=page_number, entries=entries)


def link_footnotes(
    page_texts: dict[int, str],
) -> list[FootnoteMap]:
    """Link footnotes across all pages.

    Args:
        page_texts: Dictionary mapping page_number -> page text content

    Returns:
        List of FootnoteMap objects, one per page with footnotes
    """
    footnote_maps: list[FootnoteMap] = []

    for page_number, text in sorted(page_texts.items()):
        footnote_map = _link_page_footnotes(text, page_number)
        if footnote_map.entries:
            footnote_maps.append(footnote_map)

    return footnote_maps


def find_marker_in_cell(
    cell_text: str,
    footnote_maps: list[FootnoteMap],
    page_number: int,
) -> Optional[str]:
    """Find footnote text for a marker in a table cell.

    Searches for footnote markers in cell text and returns the
    corresponding footnote definition from the page's footnote map.

    Args:
        cell_text: Text content of a table cell
        footnote_maps: List of all footnote maps
        page_number: Page where cell is located

    Returns:
        Footnote text if marker found and linked, None otherwise
    """
    # Find markers in cell text
    markers = _find_footnote_markers(cell_text)

    if not markers:
        return None

    # Get the footnote map for this page
    page_map = None
    for fm in footnote_maps:
        if fm.page_number == page_number:
            page_map = fm
            break

    if not page_map:
        return None

    # Return the first linked footnote text
    for marker, _ in markers:
        if marker in page_map.entries:
            return page_map.entries[marker]

    return None
