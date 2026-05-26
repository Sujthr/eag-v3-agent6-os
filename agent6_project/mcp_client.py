"""
MCP client — manages the stdio subprocess connection to the MCP server.
Used as an async context manager throughout the agent loop.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from utils.logging_utils import get_logger

log = get_logger("mcp")

# MCP server script lives at the Resubmission root level
_SERVER_SCRIPT = str(
    Path(__file__).parent.parent / "7c50da52-c1ee-4d0a-b89a-6938753940f1.py"
)


class MCPClient:
    """
    Async context manager that launches the MCP server as a subprocess
    and exposes a ClientSession for tool dispatch.

    Usage:
        async with MCPClient() as client:
            tools = await client.list_tools()
            result = await client.session.call_tool("web_search", {"query": "..."})
    """

    def __init__(self, server_script: str = _SERVER_SCRIPT):
        self.server_script = server_script
        self.session: Optional[ClientSession] = None
        self._stdio_cm = None
        self._session_cm = None
        self._tools_cache: Optional[list[dict]] = None

    async def __aenter__(self) -> "MCPClient":
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        params = StdioServerParameters(
            command="python",
            args=[self.server_script],
            env=env,
        )
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self.session = await self._session_cm.__aenter__()
        await self.session.initialize()
        log.info("MCP session initialized with %s", Path(self.server_script).name)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session_cm:
            try:
                await self._session_cm.__aexit__(*exc)
            except Exception as e:
                log.debug("Session exit error: %s", e)
        if self._stdio_cm:
            try:
                await self._stdio_cm.__aexit__(*exc)
            except Exception as e:
                log.debug("Stdio exit error: %s", e)

    async def list_tools(self) -> list[dict]:
        """Return tool definitions as plain dicts (cached after first call)."""
        if self._tools_cache is not None:
            return self._tools_cache

        result = await self.session.list_tools()
        self._tools_cache = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": getattr(t, "inputSchema", {}) or {},
            }
            for t in result.tools
        ]
        log.info("Tools available: %s", [t["name"] for t in self._tools_cache])
        return self._tools_cache
