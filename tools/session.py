"""Session management tools: launch, attach, info, terminate."""

import json
from typing import List, Optional

from mcp.server.fastmcp import Context

from cdb_mcp import (
    mcp,
    _get_state,
    _get_manager,
    find_cdb,
    truncate_output,
    SessionManager,
)


@mcp.tool(name="cdb_launch")
async def cdb_launch(
    target_binary: str,
    ctx: Context = None,
    target_args: Optional[str] = None,
    testcase_path: Optional[str] = None,
    cdb_path: Optional[str] = None,
    symbol_path: Optional[str] = None,
    open_dump: bool = False,
    additional_args: Optional[List[str]] = None,
    skip_initial_break: bool = False,
    skip_final_break: bool = False,
    disable_debug_heap: bool = False,
    initial_commands: Optional[str] = None,
    app_verifier: bool = False,
    source_path: Optional[str] = None,
    exception_handling: Optional[List[str]] = None,
) -> str:
    """Launch a new CDB debug session targeting a binary or crash dump.

    Args:
        target_binary: Path to the executable or .dmp file to debug.
        target_args: Command-line arguments for the target. Use '@@' as placeholder for testcase path.
        testcase_path: Path to a testcase/input file that triggers the crash.
        cdb_path: Explicit path to cdb.exe. Auto-detected if not provided.
        symbol_path: Symbol search path. Defaults to Microsoft public symbol server.
        open_dump: Set to true if target_binary is a crash dump (.dmp) file.
        additional_args: Extra command-line arguments to pass to CDB itself.
        skip_initial_break: Skip the initial breakpoint (CDB -g flag). Target runs immediately.
        skip_final_break: Skip the final breakpoint on process exit (CDB -G flag).
        disable_debug_heap: Disable the debug heap (CDB -hd flag). Recommended for ASan binaries and for reproducing real-world behavior.
        initial_commands: CDB commands to run at startup (e.g. 'bp main; g'). Semicolon-separated.
        app_verifier: Enable Application Verifier (CDB -vf flag) for heap/handle/lock instrumentation.
        source_path: Source file search path for source-level debugging.
        exception_handling: List of exception handling directives (e.g. ['-xd av', '-xe ld']). Use '-xd av' for ASan binaries to ignore ASan-managed access violations.
    """
    # Validate target path
    if any(c in target_binary for c in ["|", "&", ";", "`", "$", "(", ")"]):
        return "Error: target_binary contains disallowed shell characters."

    state = _get_state(ctx)
    manager = state.get("manager")
    if manager is None:
        return "Error: Server not properly initialized. No session manager available."
    default_cdb = state.get("cdb_path")

    resolved_cdb = cdb_path or default_cdb
    if not resolved_cdb:
        try:
            resolved_cdb = find_cdb()
        except FileNotFoundError as e:
            return str(e)

    # Auto-detect dump files
    if not open_dump and target_binary.lower().endswith(".dmp"):
        open_dump = True

    session = manager.create_session()
    try:
        initial_output = await session.launch(
            cdb_path=resolved_cdb,
            target_binary=target_binary,
            target_args=target_args or "",
            testcase_path=testcase_path,
            symbol_path=symbol_path,
            additional_cdb_args=additional_args,
            open_dump=open_dump,
            skip_initial_break=skip_initial_break,
            skip_final_break=skip_final_break,
            disable_debug_heap=disable_debug_heap,
            initial_commands=initial_commands,
            app_verifier=app_verifier,
            source_path=source_path,
            exception_handling=exception_handling,
        )
    except RuntimeError as e:
        return f"Error: {e}"

    info = session.get_info()
    header = (
        f"Session '{info['session_id']}' started successfully.\n"
        f"Target: {info['target_binary']}\n"
        f"PID: {info['pid']}\n"
        f"State: {info['state']}\n"
        f"{'=' * 60}\n"
    )
    return header + truncate_output(initial_output)


@mcp.tool(name="cdb_attach")
async def cdb_attach(
    ctx: Context = None,
    pid: Optional[int] = None,
    process_name: Optional[str] = None,
    noninvasive: bool = False,
    cdb_path: Optional[str] = None,
    symbol_path: Optional[str] = None,
    source_path: Optional[str] = None,
    additional_args: Optional[List[str]] = None,
    exception_handling: Optional[List[str]] = None,
) -> str:
    """Attach CDB to a running process by PID or name.

    Args:
        pid: Process ID to attach to (decimal).
        process_name: Process name to attach to (e.g. 'notepad.exe'). Must be unique.
        noninvasive: If true, attach noninvasively (-pv). Allows inspection without disrupting the target, but cannot set breakpoints or single-step.
        cdb_path: Explicit path to cdb.exe. Auto-detected if not provided.
        symbol_path: Symbol search path.
        source_path: Source file search path.
        additional_args: Extra CDB command-line arguments.
        exception_handling: Exception handling directives (e.g. ['-xd av']).
    """
    if not pid and not process_name:
        return "Error: Provide either 'pid' or 'process_name'."

    state = _get_state(ctx)
    manager = state.get("manager")
    if manager is None:
        return "Error: Server not properly initialized. No session manager available."
    default_cdb = state.get("cdb_path")

    resolved_cdb = cdb_path or default_cdb
    if not resolved_cdb:
        try:
            resolved_cdb = find_cdb()
        except FileNotFoundError as e:
            return str(e)

    session = manager.create_session()
    try:
        initial_output = await session.attach(
            cdb_path=resolved_cdb,
            pid=pid,
            process_name=process_name,
            noninvasive=noninvasive,
            symbol_path=symbol_path,
            source_path=source_path,
            additional_cdb_args=additional_args,
            exception_handling=exception_handling,
        )
    except (RuntimeError, ValueError) as e:
        return f"Error: {e}"

    info = session.get_info()
    mode = "noninvasive" if noninvasive else "invasive"
    header = (
        f"Session '{info['session_id']}' attached successfully ({mode}).\n"
        f"Target: {info['target_binary']}\n"
        f"CDB PID: {info['cdb_pid']}\n"
        f"State: {info['state']}\n"
        f"{'=' * 60}\n"
    )
    return header + truncate_output(initial_output)


@mcp.tool(name="cdb_session_info")
async def cdb_session_info(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Get session metadata (state, PID, uptime, commands executed).

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return json.dumps(session.get_info(), indent=2)


@mcp.tool(name="cdb_terminate")
async def cdb_terminate(
    ctx: Context = None,
    session_id: Optional[str] = None,
) -> str:
    """Terminate the debug session and kill the target process.

    Args:
        session_id: Optional session ID.
    """
    manager = _get_manager(ctx)
    try:
        session = manager.get_session(session_id)
        result = await session.terminate()
    except (ValueError, RuntimeError) as e:
        return f"Error: {e}"
    return result
