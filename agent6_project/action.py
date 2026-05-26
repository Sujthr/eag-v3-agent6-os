"""
Action layer — pure dispatch.
No LLM calls allowed here. Executes MCP tool calls and manages artifact offload.
"""
from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Optional

import artifacts as artifact_store
from schemas import ToolCall
from utils.logging_utils import get_logger

if TYPE_CHECKING:
    from mcp import ClientSession

log = get_logger("action")

LARGE_OUTPUT_THRESHOLD = 4096  # bytes; outputs larger than this go to artifact store


async def execute(
    session: "ClientSession",
    tool_call: ToolCall,
) -> tuple[str, Optional[str]]:
    """
    Execute a MCP tool call.
    Returns (descriptor, artifact_id_or_none).

    Raises ValueError for unsafe inputs (art: handles as arguments).
    """
    # Safety: reject artifact handles passed as tool arguments
    for key, val in tool_call.arguments.items():
        if isinstance(val, str) and val.startswith("art:"):
            raise ValueError(
                f"Artifact handle '{val}' in argument '{key}' must not be passed to tools. "
                "Use the attached artifact bytes from prompt context instead."
            )

    log.info("Executing tool: %s(%s)", tool_call.name, _arg_summary(tool_call.arguments))

    # fetch_url uses headless Chromium which can hang; give it a generous but
    # bounded timeout. Other tools get 30s.
    tool_timeout = 90 if tool_call.name == "fetch_url" else 30
    try:
        result = await asyncio.wait_for(
            session.call_tool(tool_call.name, tool_call.arguments),
            timeout=tool_timeout,
        )
    except asyncio.TimeoutError:
        log.error("MCP tool %s timed out after %ds", tool_call.name, tool_timeout)
        raise TimeoutError(f"{tool_call.name} timed out after {tool_timeout}s")
    except Exception as exc:
        log.error("MCP tool %s failed: %s", tool_call.name, exc)
        raise

    text = _flatten_content(result)
    encoded = text.encode("utf-8")

    if len(encoded) > LARGE_OUTPUT_THRESHOLD:
        meta = artifact_store.put(
            encoded,
            content_type="text/plain",
            source=f"tool:{tool_call.name}",
            descriptor=f"{tool_call.name}({_arg_summary(tool_call.arguments)})",
        )
        descriptor = f"[stored {meta.size_bytes:,}B | ARTIFACT_ID={meta.id}] {meta.descriptor}"
        log.info("Large output stored as artifact %s", meta.id)
        return descriptor, meta.id

    short = text[:400] if len(text) > 400 else text
    return short, None


def _flatten_content(result) -> str:
    """Flatten MCP tool result (ContentBlock list or raw value) to a string."""
    if result is None:
        return ""

    # MCP SDK CallToolResult has a .content attribute
    content = getattr(result, "content", result)

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif isinstance(block, dict):
                parts.append(block.get("text", json.dumps(block)))
            else:
                parts.append(str(block))
        return "\n".join(parts)

    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)

    return str(content)


def _arg_summary(args: dict) -> str:
    parts = [f"{k}={str(v)[:30]}" for k, v in list(args.items())[:3]]
    return ", ".join(parts)
