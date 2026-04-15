"""
Tests for session management: launch, attach, session_info, terminate.
"""

import pytest


# ---------------------------------------------------------------------------
# cdb_launch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_launch_and_terminate(mcp_server, buggy_exe):
    """Launch a debug session and terminate it cleanly."""
    resp = await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})
    text = mcp_server.tool_text(resp)
    assert "started successfully" in text
    assert "buggy.exe" in text

    resp = await mcp_server.call_tool("cdb_terminate")
    text = mcp_server.tool_text(resp)
    assert "terminated" in text.lower()


@pytest.mark.asyncio
async def test_launch_with_target_args(mcp_server, buggy_exe):
    """Launch with target_args should include them in the command line."""
    resp = await mcp_server.call_tool("cdb_launch", {
        "target_binary": buggy_exe,
        "target_args": "2",
    })
    text = mcp_server.tool_text(resp)
    assert "started successfully" in text
    # CDB shows the full command line including args
    assert "buggy.exe 2" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_launch_with_disable_debug_heap(mcp_server, buggy_exe):
    """Launch with disable_debug_heap should pass -hd flag."""
    resp = await mcp_server.call_tool("cdb_launch", {
        "target_binary": buggy_exe,
        "disable_debug_heap": True,
    })
    text = mcp_server.tool_text(resp)
    assert "started successfully" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_launch_with_exception_handling(mcp_server, buggy_exe):
    """Launch with exception_handling should apply the flags."""
    resp = await mcp_server.call_tool("cdb_launch", {
        "target_binary": buggy_exe,
        "exception_handling": ["-xd av"],
    })
    text = mcp_server.tool_text(resp)
    assert "started successfully" in text

    # Run to crash — with -xd av, AV should be second-chance
    resp = await mcp_server.call_tool("cdb_step", {"action": "g", "timeout": 30})
    text = mcp_server.tool_text(resp)
    assert "second chance" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_launch_invalid_path(mcp_server):
    """Launching a nonexistent binary should return an error."""
    resp = await mcp_server.call_tool("cdb_launch", {
        "target_binary": r"C:\nonexistent\fake.exe",
    })
    text = mcp_server.tool_text(resp)
    # CDB will fail to start or report an error
    assert "error" in text.lower() or "cannot" in text.lower() or "not found" in text.lower()


@pytest.mark.asyncio
async def test_launch_shell_injection_blocked(mcp_server):
    """Target paths with shell characters should be rejected."""
    resp = await mcp_server.call_tool("cdb_launch", {
        "target_binary": "test.exe; rm -rf /",
    })
    text = mcp_server.tool_text(resp)
    assert "disallowed" in text.lower()


# ---------------------------------------------------------------------------
# cdb_session_info
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_info(mcp_server, buggy_exe):
    """session_info should return JSON with expected fields."""
    await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})

    resp = await mcp_server.call_tool("cdb_session_info")
    text = mcp_server.tool_text(resp)
    assert "session_id" in text
    assert "broken" in text  # state after initial break
    assert "buggy.exe" in text

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_terminate (edge cases)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_terminate_no_session(mcp_server):
    """Terminating with no active session should return an error."""
    resp = await mcp_server.call_tool("cdb_terminate")
    text = mcp_server.tool_text(resp)
    assert "error" in text.lower() or "no active" in text.lower()
