"""
Tests for inspection tools: analyze, stack_trace, registers, locals,
examine_memory, disassemble, evaluate, exception_record, read_string.
"""

import pytest


async def _launch_and_crash(mcp_server, buggy_exe, args=None):
    """Helper: launch buggy.exe, run to the crash, return the server."""
    launch_args = {"target_binary": buggy_exe}
    if args:
        launch_args["target_args"] = args
    await mcp_server.call_tool("cdb_launch", launch_args)
    await mcp_server.call_tool("cdb_step", {"action": "g", "timeout": 30})


# ---------------------------------------------------------------------------
# cdb_analyze
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze(mcp_server, buggy_exe):
    """!analyze -v should identify the NULL_POINTER_WRITE."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_analyze")
    text = mcp_server.tool_text(resp)
    assert "null" in text.lower() or "c0000005" in text.lower()
    assert "proc_c" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_stack_trace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stack_trace(mcp_server, buggy_exe):
    """Stack trace at the crash should include proc_c and main."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_stack_trace")
    text = mcp_server.tool_text(resp)
    assert "proc_c" in text
    assert "main" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_stack_trace_variants(mcp_server, buggy_exe):
    """Different variants (k, kpn, kvn) should all work."""
    await _launch_and_crash(mcp_server, buggy_exe)

    for variant in ["k", "kpn", "kvn"]:
        resp = await mcp_server.call_tool("cdb_stack_trace", {"variant": variant})
        text = mcp_server.tool_text(resp)
        assert "proc_c" in text, f"variant '{variant}' missing proc_c"

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_registers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registers(mcp_server, buggy_exe):
    """Registers should include rax, rip, rsp on x64."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_registers")
    text = mcp_server.tool_text(resp)
    assert "rax=" in text
    assert "rip=" in text
    assert "rsp=" in text

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_locals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_locals(mcp_server, buggy_exe):
    """Locals in proc_c should show the NULL pointer 'p'."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_locals")
    text = mcp_server.tool_text(resp)
    assert "p" in text
    assert "0x00000000" in text.replace("`", "")

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_locals_verbose(mcp_server, buggy_exe):
    """Verbose locals should show type info."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_locals", {"verbose": True})
    text = mcp_server.tool_text(resp)
    # Verbose mode shows addresses and types
    assert "p" in text

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_examine_memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_examine_memory(mcp_server, buggy_exe):
    """Reading memory at @rsp should return data."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_examine_memory", {
        "address": "@rsp",
        "display_format": "dq",
        "count": 4,
    })
    text = mcp_server.tool_text(resp)
    # Should contain hex addresses
    assert "`" in text  # CDB formats 64-bit addresses with backtick

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_disassemble
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disassemble_at_crash(mcp_server, buggy_exe):
    """Disassembly at the crash point should show the faulting instruction."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_disassemble", {
        "address": "buggy!proc_c",
        "instruction_count": 10,
    })
    text = mcp_server.tool_text(resp)
    assert "proc_c" in text
    assert "mov" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_disassemble_function(mcp_server, buggy_exe):
    """Disassembling an entire function should include ret."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_disassemble", {
        "address": "buggy!proc_c",
        "function": True,
    })
    text = mcp_server.tool_text(resp)
    assert "ret" in text.lower()

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_evaluate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate(mcp_server, buggy_exe):
    """Evaluating a simple expression should return a result."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_evaluate", {"expression": "2 + 2"})
    text = mcp_server.tool_text(resp)
    assert "4" in text

    await mcp_server.call_tool("cdb_terminate")


@pytest.mark.asyncio
async def test_evaluate_register(mcp_server, buggy_exe):
    """Evaluating @rax should return 0 (NULL ptr at crash)."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_evaluate", {"expression": "@rax"})
    text = mcp_server.tool_text(resp)
    assert "0" in text

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_exception_record
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exception_record(mcp_server, buggy_exe):
    """Exception record at crash should show c0000005 and registers."""
    await _launch_and_crash(mcp_server, buggy_exe)

    resp = await mcp_server.call_tool("cdb_exception_record")
    text = mcp_server.tool_text(resp)
    assert "c0000005" in text.lower()
    assert "rax=" in text

    await mcp_server.call_tool("cdb_terminate")


# ---------------------------------------------------------------------------
# cdb_read_string
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_string(mcp_server, buggy_exe):
    """Reading the 'entering proc_c' string from the binary."""
    await _launch_and_crash(mcp_server, buggy_exe)

    # This string is at a known location in the binary
    resp = await mcp_server.call_tool("cdb_read_string", {
        "address": "buggy!__xt_z+0x160",
        "string_type": "ascii",
    })
    text = mcp_server.tool_text(resp)
    assert "proc_c" in text.lower()

    await mcp_server.call_tool("cdb_terminate")
