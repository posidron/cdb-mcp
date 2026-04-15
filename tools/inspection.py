"""Inspection & analysis tools: analyze, stack, registers, locals, memory, disassemble, evaluate, exceptions."""

from typing import Optional

from mcp.server.fastmcp import Context

from cdb_mcp import (
    mcp,
    _get_manager,
    truncate_output,
    ANALYZE_TIMEOUT,
)


@mcp.tool(name="cdb_analyze")
async def cdb_analyze(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Run !analyze -v for comprehensive automated crash analysis.

    Provides exception type, faulting instruction, call stack, probable
    root cause, and bucket ID. Can take 30-120 seconds.

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    try:
        output = await session.send_command("!analyze -v", timeout=ANALYZE_TIMEOUT)
    except RuntimeError as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_stack_trace")
async def cdb_stack_trace(
    ctx: Context = None,
    variant: str = "kpn",
    num_frames: int = 20,
    session_id: Optional[str] = None,
) -> str:
    """Display the call stack of the current thread.

    Args:
        variant: Stack trace variant: 'k', 'kp', 'kn', 'kpn', 'kvn', 'kP'.
        num_frames: Maximum number of stack frames to display.
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    try:
        output = await session.send_command(f"{variant} {num_frames}")
    except RuntimeError as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_registers")
async def cdb_registers(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Display all CPU register values for the current thread.

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command("r")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return output


@mcp.tool(name="cdb_locals")
async def cdb_locals(
    ctx: Context = None,
    session_id: Optional[str] = None,
    verbose: bool = False,
) -> str:
    """Display local variables and parameters of the current stack frame.

    Uses the 'dv' command to show names, types, and values of locals.

    Args:
        session_id: Optional session ID.
        verbose: If true, show variable types and locations (dv /t /v).
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        cmd = "dv /t /v" if verbose else "dv"
        output = await session.send_command(cmd)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return output or "No local variables available (symbols may not include locals)."


@mcp.tool(name="cdb_examine_memory")
async def cdb_examine_memory(
    address: str,
    ctx: Context = None,
    display_format: str = "dps",
    count: int = 20,
    session_id: Optional[str] = None,
) -> str:
    """Read and display memory at a given address in various formats.

    Args:
        address: Memory address or expression (e.g. '@rsp', 'poi(rcx+8)', '0x7ff612340000').
        display_format: Display format — 'db' (bytes), 'dw' (words), 'dd' (dwords), 'dq' (qwords), 'dps' (pointer+symbols), 'da' (ascii string), 'du' (unicode string), 'dc' (dwords+ascii).
        count: Number of elements to display (passed as CDB 'L' length).
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command(f"{display_format} {address} L{count}")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_read_string")
async def cdb_read_string(
    address: str,
    ctx: Context = None,
    string_type: str = "ascii",
    session_id: Optional[str] = None,
) -> str:
    """Read a null-terminated string from memory.

    Args:
        address: Memory address or expression pointing to the string.
        string_type: 'ascii' (da) or 'unicode' (du).
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        cmd = "da" if string_type == "ascii" else "du"
        output = await session.send_command(f"{cmd} {address}")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return output


@mcp.tool(name="cdb_disassemble")
async def cdb_disassemble(
    ctx: Context = None,
    address: Optional[str] = None,
    function: bool = False,
    instruction_count: int = 20,
    session_id: Optional[str] = None,
) -> str:
    """Disassemble instructions at an address or for an entire function.

    Args:
        address: Address or symbol to disassemble (e.g. 'buggy!main', '@rip'). Defaults to current IP.
        function: If true, disassemble entire function (uses 'uf' instead of 'u').
        instruction_count: Number of instructions to disassemble (ignored if function=true).
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        if function:
            addr = address or "@rip"
            cmd = f"uf {addr}"
        else:
            addr = address or "@rip"
            cmd = f"u {addr} L{instruction_count}"
        output = await session.send_command(cmd)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_evaluate")
async def cdb_evaluate(
    expression: str,
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Evaluate a debugger expression and return the result.

    Args:
        expression: Expression to evaluate (e.g. 'poi(esp)', '@eax & 0xff').
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command(f"? {expression}")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return output


@mcp.tool(name="cdb_exception_record")
async def cdb_exception_record(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Show exception record and switch to exception context (.ecxr).

    Critical for crash analysis — shows exception code, address, and
    registers at the point of the crash.

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        ecxr = await session.send_command(".ecxr")
        exr = await session.send_command(".exr -1")
        regs = await session.send_command("r")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return f"Exception Context (.ecxr):\n{ecxr}\n\nException Record:\n{exr}\n\nRegisters:\n{regs}"
