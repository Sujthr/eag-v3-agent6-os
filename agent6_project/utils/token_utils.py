"""Token counting utilities."""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Rough token estimate: words × 1.4."""
    return int(len(text.split()) * 1.4)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximately max_tokens, preserving head and tail."""
    words = text.split()
    allowed = int(max_tokens / 1.4)
    if len(words) <= allowed:
        return text
    half = allowed // 2
    return " ".join(words[:half]) + "\n\n…[truncated]…\n\n" + " ".join(words[-half:])
