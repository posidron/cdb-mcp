# Architecture

```
┌──────────────┐     stdio      ┌──────────────┐    subprocess    ┌──────────┐
│  MCP Client  │ ◄────────────► │   cdb_mcp    │ ◄──────────────► │  CDB.exe │
│ (Claude, etc)│   MCP JSON-RPC │  (Python)    │  stdin/stdout    │          │
└──────────────┘                └──────────────┘                  └──────────┘
                                       │
                                 SessionManager
                                       │
                                  DebugSession
                                  - async I/O
                                  - prompt detection
                                  - timeout handling
                                  - command history
```

## Overview

The CDB MCP server acts as a bridge between an MCP client (e.g., Claude, VS Code Copilot) and the Windows CDB debugger. Communication with the client uses **MCP JSON-RPC over stdio**. Communication with CDB uses an **async subprocess** over stdin/stdout.

## Key Components

### `cdb_mcp.py` — Core

| Component | Responsibility |
|-----------|---------------|
| `DebugSession` | Manages a single CDB subprocess: launch, send commands, read output, terminate |
| `SessionManager` | Tracks multiple sessions, resolves active session for tool calls |
| `_read_until_prompt()` | Reads CDB stdout until the prompt regex matches or timeout expires |
| `_clean_output()` | Strips echoed commands and trailing prompts from CDB output |
| `break_execution()` | Interrupts a running target via `DebugBreakProcess` (Win32) or Ctrl+C fallback |
| `app_lifespan()` | Creates the `SessionManager` and resolves the CDB path at server startup |

### `tools/` — MCP Tool Definitions

Each file registers `@mcp.tool` handlers that delegate to `DebugSession.send_command()`:

| Module | Tools |
|--------|-------|
| `session.py` | `cdb_launch`, `cdb_attach`, `cdb_session_info`, `cdb_terminate` |
| `execution.py` | `cdb_step`, `cdb_break`, `cdb_set_breakpoint`, `cdb_list_breakpoints`, `cdb_exception_handling` |
| `inspection.py` | `cdb_analyze`, `cdb_stack_trace`, `cdb_registers`, `cdb_locals`, `cdb_examine_memory`, `cdb_read_string`, `cdb_disassemble`, `cdb_evaluate`, `cdb_exception_record` |
| `navigation.py` | `cdb_switch_frame`, `cdb_switch_thread` |
| `symbols.py` | `cdb_symbols`, `cdb_near_symbol`, `cdb_data_type`, `cdb_modules` |
| `advanced.py` | `cdb_command`, `cdb_search_memory`, `cdb_heap`, `cdb_threads` |

## CDB I/O Model

```
           send_command("kpn 20")
                   │
                   ▼
    ┌─────────────────────────┐
    │  Write "kpn 20\n" to    │
    │  CDB stdin              │
    └────────────┬────────────┘
                 │
                 ▼
    ┌─────────────────────────┐
    │  Read stdout chunks     │
    │  until CDB_PROMPT_RE    │◄──── timeout check on each read
    │  matches                │
    └────────────┬────────────┘
                 │
                 ▼
    ┌─────────────────────────┐
    │  _clean_output():       │
    │  - strip echoed command │
    │  - strip trailing prompt│
    └────────────┬────────────┘
                 │
                 ▼
           return output
```

- Commands are serialized with an `asyncio.Lock` — only one command executes at a time per session.
- Prompt detection uses a compiled regex matching patterns like `0:000>`, `0:001:x86>`, and bare `>`.
- The output buffer is capped at 512 KB to prevent memory blowup on very large outputs.

## State Machine

```
  NOT_STARTED ──launch()──► BROKEN ──g──► RUNNING
                              ▲                │
                              │                │
                         breakpoint/       break/
                         exception         timeout
                              │                │
                              └────────────────┘
                              │
                         terminate()
                              │
                              ▼
                         TERMINATED
```

The session state is updated heuristically based on output markers (e.g., "Break instruction exception", "Access violation").

## Lifespan

```
Server start
    │
    ▼
app_lifespan():
    - Create SessionManager
    - Resolve CDB path (env → PATH → known locations)
    - yield {manager, cdb_path}
    │
    ▼
Server running (tool calls use manager from context)
    │
    ▼
Server shutdown
    - manager.terminate_all() kills any remaining CDB processes
```

## File Layout

```
cdb_mcp.py              — Server core: DebugSession, SessionManager, MCP setup
tools/
  __init__.py            — Imports all tool modules to register them
  session.py             — Launch, attach, info, terminate
  execution.py           — Step, break, breakpoints, exception handling
  inspection.py          — Analyze, stack, registers, locals, memory, disassemble
  navigation.py          — Frame/thread switching
  symbols.py             — Symbol search, type inspection, modules
  advanced.py            — Raw command, memory search, heap, threads
tests/
  conftest.py            — MCP client fixture, test helpers
  test_session.py        — Session lifecycle tests
  test_execution.py      — Execution control tests
  test_inspection.py     — Inspection tool tests
  test_navigation_and_advanced.py — Navigation, symbols, advanced tests
  test_tool_registration.py — Verifies all 28 tools are registered
```
