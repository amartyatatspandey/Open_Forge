"""Intent parser package — converts natural language to structured design intent.

Parses PCB design prompts into IntentDict objects using Qwen2.5-7B-Instruct
via Instructor, with fallback to rule-based parsing when models are unavailable.

Public API:
    parse_intent(prompt, config) -> IntentDict
    get_clarification_questions(intent) -> list[dict]

Example:
    >>> from src.intent import parse_intent, get_clarification_questions
    >>> from src.config import get_config
    >>> config = get_config()
    >>>
    >>> intent = parse_intent("build a 2.4GHz patch antenna for a drone", config)
    >>> print(intent.goal)
    patch_antenna
    >>> print(intent.design_methodology.value)
    RF_highfreq
    >>>
    >>> if intent.clarification_required:
    ...     questions = get_clarification_questions(intent)
    ...     for q in questions:
    ...         print(f"Need clarification: {q['question']}")
"""

from __future__ import annotations

from src.intent.parser import get_clarification_questions, parse_intent

__all__ = ["parse_intent", "get_clarification_questions"]
