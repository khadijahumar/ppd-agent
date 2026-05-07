"""Shared types for tool functions."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolResult:
    """Returned by tool functions.

    `text` is what the LLM sees (and what is sent back as tool_message
    content). `image_paths` are PNG files generated as side-effects which
    the bot layer should send alongside the assistant's next message.
    """
    text: str
    image_paths: list[Path] = field(default_factory=list)


def as_str(result: ToolResult | str) -> str:
    if isinstance(result, ToolResult):
        return result.text
    return str(result)


def collect_images(result: ToolResult | str) -> list[Path]:
    if isinstance(result, ToolResult):
        return list(result.image_paths)
    return []
