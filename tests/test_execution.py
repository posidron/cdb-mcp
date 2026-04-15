"""
Tests for execution control: step, breakpoints, exception handling.
"""

import pytest


# ---------------------------------------------------------------------------
# cdb_step
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_go_hits_crash(mcp_server, buggy_exe):
    """'g' (go) should run to the access violation in scenario 1."""
    await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})

    resp = await mcp_server.call_tool("cdb_step", {"action": "g", "timeout": 30})
    text = mcp_server.tool_text(resp)
    assert "access violation" in text.lower() or "c0000005" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_step_over(mcp_server, buggy_exe):
    """'p' (step over) should advance one instruction."""
    await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})

    resp = await mcp_server.call_tool("cdb_step", {"action": "p"})
    text = mcp_server.tool_text(resp)
    # Should show a disassembled instruction (address + opcode)
    assert ":" in text  # CDB disassembly uses "address: opcode" format

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_step_no_session(mcp_server):
    """Stepping with no active session should error."""
    resp = await mcp_server.call_tool("cdb_step", {"action": "g"})
    text = mcp_server.tool_text(resp)
    assert "error" in text.lower()


# ---------------------------------------------------------------------------
# cdb_set_breakpoint / cdb_list_breakpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_and_list_breakpoints(mcp_server, buggy_exe):
    """Setting a breakpoint should show it in the breakpoint list."""
    await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})

    resp = await mcp_server.call_tool("cdb_set_breakpoint", {
        "expression": "buggy!main",
    })
    text = mcp_server.tool_text(resp)
    assert "breakpoint" in text.lower() or "buggy!main" in text.lower()

    resp = await mcp_server.call_tool("cdb_list_breakpoints")
    text = mcp_server.tool_text(resp)
    assert "buggy!main" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_hit_breakpoint(mcp_server, buggy_exe):
    """Running to a breakpoint should stop at the right place."""
    await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})

    await mcp_server.call_tool("cdb_set_breakpoint", {
        "expression": "buggy!proc_c",
    })

    resp = await mcp_server.call_tool("cdb_step", {"action": "g", "timeout": 30})
    text = mcp_server.tool_text(resp)
    assert "proc_c" in text.lower() or "breakpoint" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_exception_handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exception_handling_sxd(mcp_server, buggy_exe):
    """sxd av should make access violations second-chance only."""
    await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})

    resp = await mcp_server.call_tool("cdb_exception_handling", {
        "exception_code": "av",
        "handling": "sxd",
    })
    text = mcp_server.tool_text(resp)
    assert "updated" in text.lower() or "av" in text.lower()

    # Run — AV should be second-chance now
    resp = await mcp_server.call_tool("cdb_step", {"action": "g", "timeout": 30})
    text = mcp_server.tool_text(resp)
    assert "second chance" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_exception_handling_invalid(mcp_server, buggy_exe):
    """Invalid handling value should return an error."""
    await mcp_server.call_tool("cdb_launch", {"target_binary": buggy_exe})

    resp = await mcp_server.call_tool("cdb_exception_handling", {
        "exception_code": "av",
        "handling": "invalid",
    })
    text = mcp_server.tool_text(resp)
    assert "error" in text.lower()

    await mcp_server.call_tool("cdb_terminate")
