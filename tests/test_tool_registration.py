"""
Tests for tool registration.

Verifies that all expected tools are available after server startup.
"""

import pytest

EXPECTED_TOOLS = [
    # Session
    "cdb_launch", "cdb_attach", "cdb_session_info", "cdb_terminate",
    # Execution
    "cdb_step", "cdb_break", "cdb_set_breakpoint", "cdb_list_breakpoints",
    "cdb_exception_handling",
    # Inspection
    "cdb_analyze", "cdb_stack_trace", "cdb_registers", "cdb_locals",
    "cdb_examine_memory", "cdb_read_string", "cdb_disassemble",
    "cdb_evaluate", "cdb_exception_record",
    # Navigation
    "cdb_switch_frame", "cdb_switch_thread",
    # Symbols
    "cdb_symbols", "cdb_near_symbol", "cdb_data_type", "cdb_modules",
    # Advanced
    "cdb_command", "cdb_search_memory", "cdb_heap", "cdb_threads",
]


@pytest.mark.asyncio
async def test_tool_count(mcp_server):
    """Server should register exactly 28 tools."""
    tools = await mcp_server.list_tools()
    assert len(tools) == 28


@pytest.mark.asyncio
async def test_all_tools_registered(mcp_server):
    """Every expected tool name must be present."""
    tools = await mcp_server.list_tools()
    for name in EXPECTED_TOOLS:
        assert name in tools, f"Tool '{name}' not registered"


@pytest.mark.asyncio
async def test_no_unexpected_tools(mcp_server):
    """No tools beyond the expected set should be registered."""
    tools = await mcp_server.list_tools()
    expected = set(EXPECTED_TOOLS)
    unexpected = set(tools) - expected
    assert not unexpected, f"Unexpected tools: {unexpected}"
