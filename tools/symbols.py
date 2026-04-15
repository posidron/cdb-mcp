"""Symbol and type inspection tools: symbols, near_symbol, data_type, modules."""

from typing import Optional

from mcp.server.fastmcp import Context

from cdb_mcp import mcp, _get_manager, truncate_output


@mcp.tool(name="cdb_symbols")
async def cdb_symbols(
    pattern: str,
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Search for symbols matching a wildcard pattern.

    Uses the 'x' command. Supports wildcards: '*' and '?'.

    Args:
        pattern: Symbol pattern (e.g. 'mymod!*alloc*', 'ntdll!Rtl*Free*', 'buggy!proc_*').
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command(f"x {pattern}")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return truncate_output(output) or "No matching symbols found."


@mcp.tool(name="cdb_near_symbol")
async def cdb_near_symbol(
    address: str,
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Find the nearest symbol(s) to a given address.

    Useful for resolving raw addresses back to function names or
    determining what function an address belongs to.

    Args:
        address: Address or expression to look up (e.g. '0x7ff612345678', '@rip').
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command(f"ln {address}")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return output


@mcp.tool(name="cdb_data_type")
async def cdb_data_type(
    type_name: str,
    ctx: Context = None,
    address: Optional[str] = None,
    recurse: int = 0,
    session_id: Optional[str] = None,
) -> str:
    """Display a data type layout or dump a structure instance at an address.

    Use without address to see the type layout. Provide address to dump a
    live instance from memory.

    Args:
        type_name: Type to display (e.g. 'ntdll!_PEB', 'mymod!MyStruct', '_EXCEPTION_RECORD').
        address: Memory address of a struct instance to dump. If omitted, shows the type layout.
        recurse: Recursion depth for nested structures (0-5). Use -1 for full recursion.
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        cmd = "dt"
        if recurse:
            cmd += f" -r{recurse}"
        cmd += f" {type_name}"
        if address:
            cmd += f" {address}"
        output = await session.send_command(cmd)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_modules")
async def cdb_modules(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """List all loaded modules (DLLs/EXEs) in the debugged process.

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command("lm")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return truncate_output(output)
