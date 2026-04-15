"""Advanced tools: raw command, search memory, heap, threads."""

from typing import Optional

from mcp.server.fastmcp import Context

from cdb_mcp import (
    mcp,
    _get_manager,
    truncate_output,
    DEFAULT_COMMAND_TIMEOUT,
)


@mcp.tool(name="cdb_command")
async def cdb_command(
    command: str,
    ctx: Context = None,
    session_id: Optional[str] = None,
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
) -> str:
    """Send any arbitrary CDB/WinDbg command and return the output.

    Args:
        command: The CDB command to execute (e.g. 'k', 'r', 'lm', '!analyze -v').
        session_id: Target a specific session. Uses active session if omitted.
        timeout: Max seconds to wait for the command to complete.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    try:
        output = await session.send_command(command, timeout=timeout)
    except RuntimeError as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_search_memory")
async def cdb_search_memory(
    start_address: str,
    range_length: str,
    pattern: str,
    ctx: Context = None,
    search_type: str = "-b",
    session_id: Optional[str] = None,
) -> str:
    """Search process memory for a byte pattern, string, or value.

    Args:
        start_address: Start address (e.g. '0x0', 'mymodule', 'esp').
        range_length: Range to search (e.g. 'L0x10000').
        pattern: Pattern to search for (e.g. '41 41 41 41', 'MZ').
        search_type: '-b' (byte), '-w' (word), '-d' (dword), '-q' (qword), '-a' (ascii), '-u' (unicode).
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        cmd = f"s {search_type} {start_address} {range_length} {pattern}"
        output = await session.send_command(cmd, timeout=60.0)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_heap")
async def cdb_heap(
    ctx: Context = None,
    command: str = "!heap -s",
    address: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Inspect Windows heap state for use-after-free, heap corruption, etc.

    Args:
        command: Heap command (e.g. '!heap -s', '!heap -a <addr>', '!heap -p -a <addr>').
        address: Heap or allocation address to inspect.
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        cmd = command
        if address:
            cmd += f" {address}"
        output = await session.send_command(cmd, timeout=60.0)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_threads")
async def cdb_threads(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """List all threads with per-thread stack traces.

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        threads = await session.send_command("~")
        stacks = await session.send_command("~*kn 10")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return f"Threads:\n{threads}\n\nThread Stacks (top 10 frames each):\n{truncate_output(stacks)}"
