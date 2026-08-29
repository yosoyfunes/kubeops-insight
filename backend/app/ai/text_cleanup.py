"""Text cleanup utilities for AI responses."""

from typing import Any

import emoji


def strip_emojis(text: str) -> str:
    """Remove all emoji from text using the official Unicode emoji database.

    Uses the emoji library which is maintained with the official Unicode
    emoji standard, ensuring comprehensive coverage of all emoji variants
    including:
    - Standard emoji (😀, 🎉, 🔴)
    - Emoji with variation selectors (ℹ️, ⚠️)
    - Multi-character emoji (👨‍👩‍👧‍👦)
    - Emoji with skin tone modifiers (👍🏽)

    Args:
        text: Input text that may contain emoji

    Returns:
        Text with all emoji removed
    """
    return emoji.replace_emoji(text, replace='')


def strip_emojis_recursive(data: Any) -> Any:
    """Recursively strip emojis from strings in nested dicts/lists.

    Walks through nested data structures and applies emoji stripping
    to all string values found. Useful for cleaning entire API response
    payloads.

    Args:
        data: Input data (str, dict, list, or primitive)

    Returns:
        Same structure with emojis removed from all strings
    """
    if isinstance(data, str):
        return strip_emojis(data)
    elif isinstance(data, dict):
        return {k: strip_emojis_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [strip_emojis_recursive(item) for item in data]
    return data
