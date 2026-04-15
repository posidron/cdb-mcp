"""
Shared fixtures for cdb-mcp tests.

The central fixture is `mcp_server` — it starts the MCP server process,
performs the JSON-RPC initialize handshake, and provides helper methods
to call tools and list tools. It tears down cleanly after each test.
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = PROJECT_ROOT / "cdb_mcp.py"
BUGGY_EXE = PROJECT_ROOT / "samples" / "easy" / "buggy.exe"
CHALLENGE_EXE = PROJECT_ROOT / "samples" / "hard" / "challenge.exe"


# ---------------------------------------------------------------------------
# MCP client helper
# ---------------------------------------------------------------------------

@dataclass
class MCPClient:
    """Lightweight JSON-RPC stdio client for the MCP server under test."""

    proc: asyncio.subprocess.Process
    _next_id: int = field(default=10, init=False)

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None, *, is_notification: bool = False) -> Optional[Dict]:
        """Send a JSON-RPC request/notification and return the parsed response (or None for notifications)."""
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not is_notification:
            self._next_id += 1
            msg["id"] = self._next_id

        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        await self.proc.stdin.drain()

        if is_notification:
            return None

        # Read lines until we get a response with our id
        for _ in range(30):
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=60)
            if not line:
                raise RuntimeError("Server closed stdout")
            parsed = json.loads(line.decode().strip())
            if parsed.get("id") == self._next_id:
                return parsed
        raise TimeoutError(f"No response for id={self._next_id}")

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None, timeout: float = 60) -> Dict:
        """Call an MCP tool and return the result dict."""
        params: Dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments

        self._next_id += 1
        msg_id = self._next_id
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": params}
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        await self.proc.stdin.drain()

        for _ in range(30):
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=timeout)
            if not line:
                raise RuntimeError("Server closed stdout")
            parsed = json.loads(line.decode().strip())
            if parsed.get("id") == msg_id:
                return parsed
        raise TimeoutError(f"No response for tool call {name}")

    async def list_tools(self) -> List[str]:
        """Return sorted list of registered tool names."""
        resp = await self.send("tools/list", {})
        return sorted(t["name"] for t in resp.get("result", {}).get("tools", []))

    def tool_text(self, response: Dict) -> str:
        """Extract the text content from a tool call response."""
        content = response.get("result", {}).get("content", [{}])
        return content[0].get("text", "") if content else ""

    def tool_is_error(self, response: Dict) -> bool:
        """Check if a tool call returned an error."""
        return response.get("result", {}).get("isError", False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mcp_server():
    """
    Start the MCP server, perform the initialize handshake, and yield
    an MCPClient. Terminates the server on teardown.
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(SERVER_SCRIPT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    client = MCPClient(proc=proc)

    # Initialize handshake
    await client.send("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1.0"},
    })
    await client.send(
        "notifications/initialized", {}, is_notification=True
    )
    await asyncio.sleep(0.3)

    yield client

    # Teardown: try to terminate gracefully, kill if needed
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5)
    except Exception:
        proc.kill()


@pytest.fixture
def buggy_exe() -> str:
    """Return absolute path to samples/easy/buggy.exe, skip if missing."""
    if not BUGGY_EXE.exists():
        pytest.skip("samples/easy/buggy.exe not found")
    return str(BUGGY_EXE)


@pytest.fixture
def challenge_exe() -> str:
    """Return absolute path to samples/hard/challenge.exe, skip if missing."""
    if not CHALLENGE_EXE.exists():
        pytest.skip("samples/hard/challenge.exe not found")
    return str(CHALLENGE_EXE)
