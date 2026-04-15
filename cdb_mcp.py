"""
CDB (Windows Debugger) MCP Server

An MCP server that wraps CDB.exe to enable AI-assisted interactive debugging.
Provides tools to launch debug sessions, control execution, inspect state,
and analyze crashes — all driven by an LLM through the Model Context Protocol.

Typical workflow:
  1. cdb_launch → start a debug session with a target binary
  2. cdb_analyze → run !analyze -v for automated crash triage
  3. cdb_stack_trace / cdb_registers / cdb_examine_memory → deep dive
  4. cdb_command → send any raw CDB command for full flexibility
  5. cdb_terminate → end the session
"""

import asyncio
import json
import os
import re
import shlex
import signal
import sys
import time
import logging
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Context

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Common CDB install locations (Debugging Tools for Windows)
CDB_SEARCH_PATHS = [
    r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe",
    r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x86\cdb.exe",
    r"C:\Program Files\Windows Kits\10\Debuggers\x64\cdb.exe",
    r"C:\Debuggers\cdb.exe",
]

# How long to wait for CDB to produce output before declaring a timeout
DEFAULT_COMMAND_TIMEOUT = 30.0
LAUNCH_TIMEOUT = 30.0
ANALYZE_TIMEOUT = 120.0  # !analyze can be slow

# Regex to detect the CDB input prompt — the debugger is ready for a command
# Matches patterns like "0:000>" or "0:001:x86>" or just ">"
# Also handles "*BUSY*" prefixed prompts and input prompt variants
CDB_PROMPT_RE = re.compile(
    r"(?:^|\n)"
    r"(?:\*?BUSY\*?\s*)?"
    r"(?:\d+:\d+(?::\w+)?)"
    r">\s*$"
    r"|"
    r"(?:^|\n)>\s*$",
    re.MULTILINE,
)

# Symbol path template
DEFAULT_SYMBOL_PATH = (
    r"srv*C:\Symbols*https://msdl.microsoft.com/download/symbols"
)

# Max output we'll capture per command to avoid memory blowup
MAX_OUTPUT_BYTES = 512 * 1024  # 512 KB

# Regex to strip the trailing CDB prompt from output
CDB_PROMPT_STRIP_RE = re.compile(
    r"\n?(?:\*?BUSY\*?\s*)?(?:\d+:\d+(?::\w+)?)>\s*$"
    r"|\n?>\s*$",
    re.MULTILINE,
)

logger = logging.getLogger("cdb_mcp")
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------


class SessionState(str, Enum):
    """Current state of a debug session."""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    BROKEN = "broken"       # hit breakpoint / exception / initial break
    TERMINATED = "terminated"
    ERROR = "error"


class DebugSession:
    """
    Manages a single CDB.exe subprocess.

    Handles launching the process, sending commands, reading output
    (waiting for the prompt), and tearing down.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.process: Optional[asyncio.subprocess.Process] = None
        self.state = SessionState.NOT_STARTED
        self.target_binary: Optional[str] = None
        self.target_args: Optional[str] = None
        self.launch_time: Optional[float] = None
        self._lock = asyncio.Lock()
        self.command_history: List[Dict[str, str]] = []

    async def launch(
        self,
        cdb_path: str,
        target_binary: str,
        target_args: str = "",
        testcase_path: Optional[str] = None,
        symbol_path: Optional[str] = None,
        additional_cdb_args: Optional[List[str]] = None,
        open_dump: bool = False,
        skip_initial_break: bool = False,
        skip_final_break: bool = False,
        disable_debug_heap: bool = False,
        initial_commands: Optional[str] = None,
        app_verifier: bool = False,
        source_path: Optional[str] = None,
        exception_handling: Optional[List[str]] = None,
    ) -> str:
        """Launch CDB with the given target. Returns initial output."""
        self.target_binary = target_binary
        self.target_args = target_args
        self.launch_time = time.time()

        sym_path = symbol_path or DEFAULT_SYMBOL_PATH

        cmd = [cdb_path]

        # Symbol path
        cmd += ["-y", sym_path]

        # Source path
        if source_path:
            cmd += ["-srcpath", source_path]

        # Behavioural flags
        if skip_initial_break:
            cmd.append("-g")
        if skip_final_break:
            cmd.append("-G")
        if disable_debug_heap:
            cmd.append("-hd")
        if app_verifier:
            cmd.append("-vf")

        # Exception handling policies (e.g. ["-xd av", "-xe ld"])
        if exception_handling:
            for eh in exception_handling:
                cmd.extend(eh.split(None, 1))  # split "-xd av" → ["-xd", "av"]

        # Initial commands to run at startup
        if initial_commands:
            cmd += ["-c", initial_commands]

        if additional_cdb_args:
            cmd.extend(additional_cdb_args)

        if open_dump:
            # Opening a crash dump
            cmd += ["-z", target_binary]
        else:
            # Launch a new process under the debugger
            cmd += ["-o"]  # debug child processes

            # Build the command line — each token must be a separate
            # list element for create_subprocess_exec, otherwise the
            # entire string gets quoted as a single path.
            cmd.append(target_binary)
            args_str = target_args or ""
            if testcase_path:
                args_str = (
                    args_str.replace("@@", testcase_path)
                    if "@@" in args_str
                    else f"{args_str} {testcase_path}".strip()
                )
            if args_str:
                # Split respecting quoted arguments
                cmd.extend(shlex.split(args_str, posix=False))

        logger.info(f"Launching CDB: {' '.join(cmd)}")

        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=getattr(
                    __import__("subprocess"), "CREATE_NO_WINDOW", 0
                ),
            )
        except FileNotFoundError:
            self.state = SessionState.ERROR
            raise RuntimeError(
                f"CDB not found at '{cdb_path}'. Install Debugging Tools for Windows "
                f"from the Windows SDK, or set CDB_PATH in your environment."
            )
        except Exception as e:
            self.state = SessionState.ERROR
            raise RuntimeError(f"Failed to launch CDB: {e}")

        # Read the initial output (CDB banner + initial break)
        # If -g was used, the target may be running — use a longer timeout
        launch_timeout = LAUNCH_TIMEOUT * 2 if skip_initial_break else LAUNCH_TIMEOUT
        initial_output = await self._read_until_prompt(timeout=launch_timeout)
        self.state = SessionState.BROKEN
        return initial_output

    async def attach(
        self,
        cdb_path: str,
        pid: Optional[int] = None,
        process_name: Optional[str] = None,
        noninvasive: bool = False,
        symbol_path: Optional[str] = None,
        source_path: Optional[str] = None,
        additional_cdb_args: Optional[List[str]] = None,
        exception_handling: Optional[List[str]] = None,
    ) -> str:
        """Attach CDB to a running process. Returns initial output."""
        if not pid and not process_name:
            raise ValueError("Either pid or process_name must be provided.")

        self.target_binary = process_name or f"PID:{pid}"
        self.launch_time = time.time()

        sym_path = symbol_path or DEFAULT_SYMBOL_PATH

        cmd = [cdb_path]
        cmd += ["-y", sym_path]

        if source_path:
            cmd += ["-srcpath", source_path]

        if exception_handling:
            for eh in exception_handling:
                cmd.extend(eh.split(None, 1))

        if noninvasive:
            cmd.append("-pv")

        if pid:
            cmd += ["-p", str(pid)]
        elif process_name:
            cmd += ["-pn", process_name]

        if additional_cdb_args:
            cmd.extend(additional_cdb_args)

        logger.info(f"Attaching CDB: {' '.join(cmd)}")

        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=getattr(
                    __import__("subprocess"), "CREATE_NO_WINDOW", 0
                ),
            )
        except FileNotFoundError:
            self.state = SessionState.ERROR
            raise RuntimeError(
                f"CDB not found at '{cdb_path}'. Install Debugging Tools for Windows "
                f"from the Windows SDK, or set CDB_PATH in your environment."
            )
        except Exception as e:
            self.state = SessionState.ERROR
            raise RuntimeError(f"Failed to attach CDB: {e}")

        initial_output = await self._read_until_prompt(timeout=LAUNCH_TIMEOUT)
        self.state = SessionState.BROKEN
        return initial_output

    async def send_command(
        self, command: str, timeout: float = DEFAULT_COMMAND_TIMEOUT
    ) -> str:
        """
        Send a debugger command and return the output.

        Waits until the CDB prompt reappears, indicating the command
        has finished executing.
        """
        async with self._lock:
            if self.process is None or self.process.returncode is not None:
                self.state = SessionState.TERMINATED
                raise RuntimeError(
                    "Debug session is not active. The target may have exited. "
                    "Use cdb_launch to start a new session."
                )

            # Record in history
            self.command_history.append({"command": command, "timestamp": time.time()})

            # Write the command
            try:
                self.process.stdin.write(f"{command}\n".encode("utf-8"))
                await self.process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                self.state = SessionState.TERMINATED
                raise RuntimeError(
                    "CDB process has exited. The debug session is over."
                )

            # Read output until the next prompt
            raw_output = await self._read_until_prompt(timeout=timeout)

            # Update state heuristic
            if any(marker in raw_output for marker in (
                "Break instruction exception",
                "Access violation",
                "divide by zero",
                "Stack overflow",
                "STATUS_BREAKPOINT",
                "first chance",
                "second chance",
                "single step exception",
            )):
                self.state = SessionState.BROKEN
            elif self.process.returncode is not None:
                self.state = SessionState.TERMINATED

            # Clean output: strip echoed command and trailing prompt
            output = self._clean_output(raw_output, command)
            return output

    @staticmethod
    def _clean_output(raw: str, command: str = "") -> str:
        """
        Strip the echoed command line and the trailing CDB prompt from output.

        This gives the LLM cleaner data to work with — no redundant echoes
        or prompt lines cluttering the context.
        """
        text = raw

        # 1. Strip the echoed command (CDB echoes every command you type)
        if command:
            # The echo is typically the first line of output
            lines = text.split("\n", 1)
            if lines and lines[0].strip() == command.strip():
                text = lines[1] if len(lines) > 1 else ""

        # 2. Strip trailing CDB prompt (e.g. "0:000> ")
        text = CDB_PROMPT_STRIP_RE.sub("", text)

        return text.strip()

    async def _read_until_prompt(self, timeout: float) -> str:
        """
        Read from CDB stdout until we see the input prompt or timeout.

        Returns all output received (minus the final prompt line).
        """
        buf = ""
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return buf + "\n[TIMEOUT: CDB did not return to prompt within the time limit. The target may be running. Try sending 'break' with Ctrl+C via cdb_break, or increase timeout.]"

            try:
                chunk = await asyncio.wait_for(
                    self.process.stdout.read(4096),
                    timeout=min(remaining, 2.0),
                )
            except asyncio.TimeoutError:
                # Check if process exited
                if self.process.returncode is not None:
                    # Drain any remaining output
                    try:
                        rest = await asyncio.wait_for(
                            self.process.stdout.read(MAX_OUTPUT_BYTES), timeout=1.0
                        )
                        buf += rest.decode("utf-8", errors="replace")
                    except Exception:
                        pass
                    self.state = SessionState.TERMINATED
                    return buf + "\n[Target process has exited.]"
                continue

            if not chunk:
                # EOF — process exited
                self.state = SessionState.TERMINATED
                return buf + "\n[CDB process has exited.]"

            text = chunk.decode("utf-8", errors="replace")
            buf += text

            if len(buf) > MAX_OUTPUT_BYTES:
                buf = buf[-MAX_OUTPUT_BYTES:]

            # Check for prompt
            if CDB_PROMPT_RE.search(buf):
                return buf

    async def break_execution(self) -> str:
        """Send a debug break to interrupt execution."""
        if self.process is None or self.process.returncode is not None:
            raise RuntimeError("No active session to break into.")

        if sys.platform == "win32":
            # On Windows, GenerateConsoleCtrlEvent won't work because we
            # launched CDB with CREATE_NO_WINDOW. Instead we:
            # 1. Try DebugBreakProcess on the CDB process itself, or
            # 2. Fall back to sending Ctrl+C byte via stdin.
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # Open the CDB process with PROCESS_ALL_ACCESS
                PROCESS_ALL_ACCESS = 0x1F0FFF
                handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, self.process.pid)
                if handle:
                    kernel32.DebugBreakProcess(handle)
                    kernel32.CloseHandle(handle)
                else:
                    raise OSError("OpenProcess failed")
            except Exception:
                # Last resort: send Ctrl+C byte on stdin
                try:
                    self.process.stdin.write(b"\x03")
                    await self.process.stdin.drain()
                except Exception:
                    pass
        else:
            self.process.send_signal(signal.SIGINT)

        output = await self._read_until_prompt(timeout=10.0)
        self.state = SessionState.BROKEN
        return output

    async def terminate(self) -> str:
        """Kill the CDB process and clean up."""
        if self.process is None:
            self.state = SessionState.TERMINATED
            return "No active session."

        try:
            # Try graceful quit first
            try:
                self.process.stdin.write(b"q\n")
                await self.process.stdin.drain()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except Exception:
                self.process.kill()
                await self.process.wait()
        except Exception as e:
            logger.warning(f"Error terminating CDB: {e}")

        self.state = SessionState.TERMINATED
        return "Debug session terminated."

    def get_info(self) -> Dict[str, Any]:
        """Return a summary of the current session."""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "target_binary": self.target_binary,
            "target_args": self.target_args,
            "launch_time": self.launch_time,
            "uptime_seconds": round(time.time() - self.launch_time, 1) if self.launch_time else None,
            "commands_executed": len(self.command_history),
            "pid": self.process.pid if self.process else None,
            "cdb_pid": self.process.pid if self.process else None,
        }


class SessionManager:
    """Manages multiple debug sessions (though typically one at a time)."""

    def __init__(self):
        self.sessions: Dict[str, DebugSession] = {}
        self._counter = 0

    def create_session(self) -> DebugSession:
        self._counter += 1
        sid = f"session_{self._counter}"
        session = DebugSession(sid)
        self.sessions[sid] = session
        return session

    def get_active_session(self) -> Optional[DebugSession]:
        """Return the most recently created non-terminated session."""
        for sid in reversed(list(self.sessions.keys())):
            s = self.sessions[sid]
            if s.state not in (SessionState.TERMINATED, SessionState.NOT_STARTED):
                return s
        return None

    def get_session(self, session_id: Optional[str] = None) -> DebugSession:
        """Get a specific session or the active one."""
        if session_id:
            if session_id not in self.sessions:
                raise ValueError(
                    f"Session '{session_id}' not found. "
                    f"Available: {list(self.sessions.keys())}"
                )
            return self.sessions[session_id]
        active = self.get_active_session()
        if not active:
            raise RuntimeError(
                "No active debug session. Use cdb_launch to start one."
            )
        return active

    async def terminate_all(self):
        for s in self.sessions.values():
            if s.state not in (SessionState.TERMINATED, SessionState.NOT_STARTED):
                await s.terminate()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def find_cdb() -> str:
    """Locate cdb.exe on the system."""
    # Check environment variable first
    env_path = os.environ.get("CDB_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    # Check PATH
    import shutil
    which = shutil.which("cdb.exe") or shutil.which("cdb")
    if which:
        return which

    # Check common install locations
    for p in CDB_SEARCH_PATHS:
        if os.path.isfile(p):
            return p

    raise FileNotFoundError(
        "cdb.exe not found. Install 'Debugging Tools for Windows' from the "
        "Windows SDK, or set the CDB_PATH environment variable. "
        "Download: https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/"
    )


def truncate_output(output: str, max_lines: int = 500) -> str:
    """Truncate very long output to keep context manageable."""
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    head = lines[: max_lines // 2]
    tail = lines[-(max_lines // 2):]
    omitted = len(lines) - max_lines
    return "\n".join(head) + f"\n\n[... {omitted} lines omitted ...]\n\n" + "\n".join(tail)


# ---------------------------------------------------------------------------
# Lifespan: initialise SessionManager and resolve CDB path
# ---------------------------------------------------------------------------

@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Server lifespan — create shared resources."""
    manager = SessionManager()
    cdb_path: Optional[str] = None
    try:
        cdb_path = find_cdb()
        logger.info(f"Found CDB at: {cdb_path}")
    except FileNotFoundError as e:
        logger.warning(str(e))
        # We'll still start — user can provide the path explicitly at launch time

    yield {"manager": manager, "cdb_path": cdb_path}

    # Cleanup
    await manager.terminate_all()


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("cdb_mcp", lifespan=app_lifespan)


# ========================== Helper ==========================

def _get_state(ctx: Context) -> dict:
    """Extract lifespan state from context."""
    if ctx and ctx.request_context:
        return ctx.request_context.lifespan_context or {}
    return {}


def _get_manager(ctx: Context) -> "SessionManager":
    """Get the SessionManager from context."""
    manager = _get_state(ctx).get("manager")
    if manager is None:
        raise RuntimeError(
            "No session manager available. The server may not have "
            "initialized properly. Use cdb_launch to start a session."
        )
    return manager


# ========================== Tools ==========================
# Tools are defined in the tools/ package. Importing it registers
# all @mcp.tool decorators with the server instance above.
#
# When this file runs as __main__, we must ensure the tools package
# can import us by the module name "cdb_mcp" (not "__main__").
# Without this, `from cdb_mcp import mcp` would re-import the file
# as a separate module, creating a second mcp instance.
if __name__ == "__main__":
    import sys as _sys
    _sys.modules.setdefault("cdb_mcp", _sys.modules[__name__])

import tools  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
