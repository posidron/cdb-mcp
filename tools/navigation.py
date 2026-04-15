"""Navigation tools: switch frame, switch thread."""

from typing import Optional

from mcp.server.fastmcp import Context

from cdb_mcp import mcp, _get_manager


@mcp.tool(name="cdb_switch_frame")
async def cdb_switch_frame(
    frame_number: int,
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Switch to a specific stack frame to inspect its locals and context.

    After switching, cdb_locals and cdb_registers show that frame's state.

    Args:
        frame_number: Frame index from the stack trace (0 = top/current).
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command(f".frame {frame_number}")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return output


@mcp.tool(name="cdb_switch_thread")
async def cdb_switch_thread(
    thread_number: int,
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Switch the active thread context for inspection.

    Args:
        thread_number: Thread index from the thread list (e.g. 0, 1, 2).
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        output = await session.send_command(f"~{thread_number}s")
        regs = await session.send_command("r")
        stack = await session.send_command("kn 10")
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return f"Switched to thread {thread_number}:\n{output}\n\nRegisters:\n{regs}\n\nStack:\n{stack}"
