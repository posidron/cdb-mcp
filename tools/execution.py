"""Execution control tools: step, break, breakpoints, exception handling."""

from typing import Optional

from mcp.server.fastmcp import Context

from cdb_mcp import (
    mcp,
    _get_manager,
    truncate_output,
    DEFAULT_COMMAND_TIMEOUT,
)


@mcp.tool(name="cdb_step")
async def cdb_step(
    ctx: Context = None,
    action: str = "p",
    count: int = 1,
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
    session_id: Optional[str] = None,
) -> str:
    """Control execution: step into, step over, step out, or continue.

    Args:
        action: 'g' (go), 'p' (step over), 't' (step into), 'gu' (step out), 'pc', 'ph', 'tt'.
        count: Number of times to repeat the step action.
        timeout: Max seconds to wait. Use higher values for 'g'.
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        if count > 1 and action in ("p", "t"):
            cmd = f"{action} {count}"
        else:
            cmd = action
        output = await session.send_command(cmd, timeout=timeout)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return truncate_output(output)


@mcp.tool(name="cdb_break")
async def cdb_break(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Send a break/interrupt to halt the running target (Ctrl+Break equivalent).

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.break_execution()
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return output


@mcp.tool(name="cdb_set_breakpoint")
async def cdb_set_breakpoint(
    expression: str,
    ctx: Context = None,
    bp_type: str = "bp",
    condition: Optional[str] = None,
    commands: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Set a breakpoint at a specified location.

    Args:
        expression: Breakpoint location (e.g. 'kernel32!CreateFileW', 'mymodule!main+0x20').
        bp_type: Breakpoint type: 'bp' (soft), 'bu' (deferred), 'bm' (pattern).
        condition: Optional conditional expression.
        commands: Commands to execute when hit (e.g. 'kb; g').
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        cmd = f"{bp_type} {expression}"
        if condition:
            cmd += f" /j '{condition}' ''"
        if commands:
            cmd += f' "{commands}"'
        output = await session.send_command(cmd)
        bp_list = await session.send_command("bl")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return f"Breakpoint set:\n{output}\n\nActive breakpoints:\n{bp_list}"


@mcp.tool(name="cdb_list_breakpoints")
async def cdb_list_breakpoints(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """List all active breakpoints in the current session.

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command("bl")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return output or "No breakpoints set."


@mcp.tool(name="cdb_exception_handling")
async def cdb_exception_handling(
    exception_code: str,
    ctx: Context = None,
    handling: str = "sxe",
    session_id: Optional[str] = None,
) -> str:
    """Configure how the debugger handles a specific exception or event.

    Controls whether a given exception breaks into the debugger, is logged,
    or is silently passed to the application. Essential for ASan binaries
    (use 'sxd av' to disable first-chance break on access violations) and
    for ignoring noisy C++ exceptions.

    Args:
        exception_code: Exception code or event name. Common values:
            'av' (access violation), 'eh' (C++ exception), 'clr' (.NET exception),
            'ld' (module load), 'ud' (module unload), 'bpe' (breakpoint),
            'c0000005' (AV by hex), 'c0000094' (divide by zero), '*' (all exceptions).
        handling: How to handle the exception:
            'sxe' — break on first chance (enabled),
            'sxd' — break on second chance only (disabled first-chance),
            'sxn' — log but don't break (notify),
            'sxi' — ignore completely.
        session_id: Optional session ID.
    """
    if handling not in ("sxe", "sxd", "sxn", "sxi"):
        return f"Error: handling must be one of 'sxe', 'sxd', 'sxn', 'sxi'. Got: '{handling}'"

    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command(f"{handling} {exception_code}")
        # Show current exception/event settings for verification
        sx_output = await session.send_command("sx")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"

    # Filter sx output to show just the relevant line(s)
    relevant_lines = [
        line for line in sx_output.splitlines()
        if exception_code.lower() in line.lower()
    ]
    summary = "\n".join(relevant_lines) if relevant_lines else sx_output[:500]

    return f"Exception handling updated:\n{output}\n\nCurrent setting for '{exception_code}':\n{summary}"
