"""
Tests for navigation, symbols, and advanced tools.
"""

import pytest


async def _launch_and_crash(mcp_server, buggy_exe):
    """Helper: launch buggy.exe and run to the crash."""
    await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})
    await mcp_server.call_tool("cdb_step", {"action": "g", "timeout": 30})


# ---------------------------------------------------------------------------
# Navigation: cdb_switch_frame, cdb_switch_thread
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_switch_frame(mcp_server, buggy_exe):
    """Switching to frame 1 (main) should show main context."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_switch_frame", {"frame_number": 1})
    text = mcp_server.tool_text(resp)
    assert "main" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_switch_thread(mcp_server, buggy_exe):
    """Switching to thread 0 should show registers and stack."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_switch_thread", {"thread_number": 0})
    text = mcp_server.tool_text(resp)
    assert "rax=" in text
    assert "proc_c" in text or "main" in text

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# Symbols: cdb_symbols, cdb_near_symbol, cdb_data_type, cdb_modules
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_symbols_search(mcp_server, buggy_exe):
    """Searching for buggy!proc_* should find all proc functions."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_symbols", {"pattern": "buggy!proc_*"})
    text = mcp_server.tool_text(resp)
    assert "proc_a" in text
    assert "proc_b" in text
    assert "proc_c" in text
    assert "proc_d" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_near_symbol(mcp_server, buggy_exe):
    """Looking up @rip should resolve to buggy!proc_c."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_near_symbol", {"address": "@rip"})
    text = mcp_server.tool_text(resp)
    assert "proc_c" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_modules(mcp_server, buggy_exe):
    """Module list should include buggy.exe and ntdll.dll."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_modules")
    text = mcp_server.tool_text(resp)
    assert "buggy" in text.lower()
    assert "ntdll" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# Advanced: cdb_command, cdb_threads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raw_command(mcp_server, buggy_exe):
    """Sending a raw 'r rax' command should return the register value."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_command", {"command": "r rax"})
    text = mcp_server.tool_text(resp)
    assert "rax=" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_threads(mcp_server, buggy_exe):
    """Thread listing should show at least one thread."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_threads")
    text = mcp_server.tool_text(resp)
    assert "thread" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# Scenario tests: different crash types
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario2_divide_by_zero(mcp_server, buggy_exe):
    """Scenario 2 should hit an integer divide-by-zero crash."""
    await mcp_server.call_tool("cdb_launch", {
        "target_binary": buggy_exe,
        "target_args": "2",
    })

    resp = await mcp_server.call_tool("cdb_step", {"action": "g", "timeout": 30})
    text = mcp_server.tool_text(resp)
    assert "divide" in text.lower() or "c0000094" in text.lower()

    resp = await mcp_server.call_tool("cdb_locals")
    text = mcp_server.tool_text(resp)
    assert "d" in text  # divisor variable

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_scenario4_stack_overflow(mcp_server, buggy_exe):
    """Scenario 4 should hit a stack buffer overflow (GS check failure)."""
    await mcp_server.call_tool("cdb_launch", {
        "target_binary": buggy_exe,
        "target_args": "4",
    })

    resp = await mcp_server.call_tool("cdb_step", {"action": "g", "timeout": 30})
    text = mcp_server.tool_text(resp)
    assert "stack" in text.lower() or "cookie" in text.lower() or "c0000409" in text.lower()

    await mcp_server.call_tool("cdb_terminate")
