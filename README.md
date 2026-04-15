# CDB MCP Server

An MCP (Model Context Protocol) server that wraps **CDB.exe** (the Windows command-line debugger) to enable **AI-assisted interactive debugging**. Point it at a crashing binary and a testcase, then let an LLM drive the debugger to find the root cause.

- [CDB MCP Server](#cdb-mcp-server)
  - [Why?](#why)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [MCP Client Configuration](#mcp-client-configuration)
    - [Claude Desktop (`claude_desktop_config.json`)](#claude-desktop-claude_desktop_configjson)
    - [VS Code / Claude Code (`.mcp.json`)](#vs-code--claude-code-mcpjson)
    - [Using `uv` (recommended for isolation)](#using-uv-recommended-for-isolation)
  - [Available Tools (28)](#available-tools-28)
    - [Session Management](#session-management)
    - [Execution Control](#execution-control)
    - [Inspection \& Analysis](#inspection--analysis)
    - [Navigation](#navigation)
    - [Symbols \& Types](#symbols--types)
    - [Advanced](#advanced)
  - [Example Workflows](#example-workflows)
    - [Crash Triage (the common case)](#crash-triage-the-common-case)
    - [Crash Dump Analysis](#crash-dump-analysis)
    - [Interactive Debugging](#interactive-debugging)
    - [ASan Binary Debugging](#asan-binary-debugging)
    - [Attaching to a Running Process](#attaching-to-a-running-process)
  - [Architecture](#architecture)
  - [Environment Variables](#environment-variables)
  - [Security Notes](#security-notes)


## Why?

When your fuzzer finds a crash, the debugging workflow is predictable but tedious:
1. Launch the binary under a debugger with the crash input
2. Run `!analyze -v`
3. Inspect the stack, registers, memory around the fault
4. Trace backward to find the root cause
5. Classify the vulnerability

This MCP server makes every one of those steps available as tools that an LLM can call — turning crash triage into a conversation.

## Prerequisites

- **Windows** with [Debugging Tools for Windows](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/) installed (part of the Windows SDK)
- **Python 3.10+**
- **CDB.exe** in your PATH, or set the `CDB_PATH` environment variable

## Installation

```bash
cd cdb_mcp
pip install -e .
```

## MCP Client Configuration

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "cdb": {
      "command": "python",
      "args": ["C:\\path\\to\\cdb_mcp\\cdb_mcp.py"],
      "env": {
        "CDB_PATH": "C:\\Program Files (x86)\\Windows Kits\\10\\Debuggers\\x64\\cdb.exe"
      }
    }
  }
}
```

### VS Code / Claude Code (`.mcp.json`)

```json
{
  "servers": {
    "cdb": {
      "type": "stdio",
      "command": "python",
      "args": ["C:\\path\\to\\cdb_mcp\\cdb_mcp.py"],
      "env": {
        "CDB_PATH": "C:\\Program Files (x86)\\Windows Kits\\10\\Debuggers\\x64\\cdb.exe"
      }
    }
  }
}
```

### Using `uv` (recommended for isolation)

```bash
pipx install uv
```

```json
{
  "mcpServers": {
    "cdb": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\path\\to\\cdb_mcp", "python", "cdb_mcp.py"],
      "env": {
        "CDB_PATH": "C:\\Program Files (x86)\\Windows Kits\\10\\Debuggers\\x64\\cdb.exe"
      }
    }
  }
}
```

## Available Tools (28)

### Session Management

| Tool | Description |
|------|-------------|
| `cdb_launch` | Launch a debug session with a binary, args, and optional testcase |
| `cdb_attach` | Attach to a running process by PID or name (invasive or noninvasive) |
| `cdb_session_info` | Get session metadata (state, PID, uptime) |
| `cdb_terminate` | Kill the target and end the debug session |

### Execution Control

| Tool | Description |
|------|-------------|
| `cdb_step` | Step over/into/out, continue, or trace (`g`, `p`, `t`, `gu`, ...) |
| `cdb_break` | Break/interrupt a running target (Ctrl+Break equivalent) |
| `cdb_set_breakpoint` | Set breakpoints (`bp`, `bu`, `bm`) with conditions/commands |
| `cdb_list_breakpoints` | List all active breakpoints |
| `cdb_exception_handling` | Configure exception handling policy (`sxe`/`sxd`/`sxn`/`sxi`) |

### Inspection & Analysis

| Tool | Description |
|------|-------------|
| `cdb_analyze` | Run `!analyze -v` for automated crash triage |
| `cdb_stack_trace` | Get the call stack (`k`, `kp`, `kpn`, `kvn` variants) |
| `cdb_registers` | Show CPU register values |
| `cdb_locals` | Display local variables and parameters (`dv`) |
| `cdb_examine_memory` | Read memory in various formats (`db`, `dd`, `dq`, `dps`, `da`, ...) |
| `cdb_read_string` | Read a null-terminated ASCII or Unicode string from memory |
| `cdb_disassemble` | Disassemble instructions or entire functions (`u`, `uf`) |
| `cdb_evaluate` | Evaluate debugger expressions (`?`, `poi()`, arithmetic) |
| `cdb_exception_record` | Show exception record and switch to exception context (`.ecxr`) |

### Navigation

| Tool | Description |
|------|-------------|
| `cdb_switch_frame` | Switch to a specific stack frame to inspect its locals/context |
| `cdb_switch_thread` | Switch active thread (auto-shows registers + stack) |

### Symbols & Types

| Tool | Description |
|------|-------------|
| `cdb_symbols` | Search for symbols matching a wildcard pattern (`x`) |
| `cdb_near_symbol` | Resolve a raw address to the nearest symbol (`ln`) |
| `cdb_data_type` | Display struct layouts or dump live instances (`dt`) |
| `cdb_modules` | List loaded modules (DLLs/EXEs) |

### Advanced

| Tool | Description |
|------|-------------|
| `cdb_command` | Send any raw CDB/WinDbg command (full flexibility escape hatch) |
| `cdb_search_memory` | Search memory for patterns, strings, or values |
| `cdb_heap` | Heap analysis (`!heap` family of commands) |
| `cdb_threads` | List threads with per-thread stack traces |

## Example Workflows

### Crash Triage (the common case)

```
User: Debug C:\fuzzing\crashes\crash_001.bin against C:\build\target.exe --parse @@

→ cdb_launch(target_binary="C:\build\target.exe", target_args="--parse @@",
             testcase_path="C:\fuzzing\crashes\crash_001.bin")
→ cdb_analyze()                    # !analyze -v
→ cdb_exception_record()           # .ecxr + exception details
→ cdb_stack_trace(variant="kpn")   # full stack with params
→ cdb_examine_memory(address="@rcx", display_format="dps")  # inspect faulting pointer
→ cdb_disassemble(function=true)   # disassemble crashing function
→ cdb_locals()                     # inspect local variables
→ cdb_terminate()
```

### Crash Dump Analysis

```
User: Analyze this crash dump: C:\dumps\app_crash.dmp

→ cdb_launch(target_binary="C:\dumps\app_crash.dmp", open_dump=true)
→ cdb_analyze()
→ cdb_stack_trace()
→ cdb_terminate()
```

### Interactive Debugging

```
User: I want to understand why CreateFileW fails in my app

→ cdb_launch(target_binary="C:\build\myapp.exe", target_args="test.txt")
→ cdb_set_breakpoint(expression="kernel32!CreateFileW", bp_type="bu")
→ cdb_step(action="g")            # run until breakpoint
→ cdb_stack_trace()                # who called CreateFileW?
→ cdb_examine_memory(address="@rcx", display_format="du")  # filename argument
→ cdb_registers()
→ cdb_step(action="gu")           # step out to see return value
→ cdb_evaluate(expression="@rax") # check HANDLE return
→ cdb_terminate()
```

### ASan Binary Debugging

```
User: Debug this ASan-compiled binary — it crashes on bad input

→ cdb_launch(target_binary="C:\build\target_asan.exe",
             target_args="--parse crash.bin",
             disable_debug_heap=true,
             exception_handling=["-xd av"])   # ASan handles its own AVs
→ cdb_step(action="g")
→ cdb_analyze()
→ cdb_terminate()
```

### Attaching to a Running Process

```
User: My app is hanging, attach and find out where it's stuck

→ cdb_attach(process_name="myapp.exe")
→ cdb_threads()                    # see all threads
→ cdb_switch_thread(thread_number=0)
→ cdb_stack_trace()
→ cdb_terminate()
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for details on the internal design, I/O model, state machine, and file layout.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CDB_PATH` | Explicit path to cdb.exe | Auto-detected from Windows SDK paths |

## Security Notes

- This MCP server executes arbitrary binaries under a debugger. Only use with trusted targets.
- The `cdb_command` tool allows sending any debugger command — it's intentionally unrestricted for maximum flexibility.
- Path validation prevents shell injection in target paths, but always run in an isolated environment when debugging untrusted crash inputs.
