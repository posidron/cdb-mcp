---
name: cdb-debugging
description: Debug Windows native binaries (C/C++) using CDB through MCP tools. Covers crash triage, memory inspection, breakpoint-driven analysis, disassembly, heap corruption diagnosis, and root cause identification — all without a GUI.
---

# CDB Debugging via MCP

## Prerequisites

**Platform**: This skill is Windows-only. If not on Windows, notify the user and stop.

**CDB required**: Before using any tools, verify CDB is available. The `cdb_launch` tool auto-detects CDB from the Windows SDK paths and `CDB_PATH` environment variable. If launch fails with "CDB not found":

1. Install [Debugging Tools for Windows](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/debugger-download-tools) (part of the Windows SDK). Select only the "Debugging Tools" component.
2. CDB is typically installed to `C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe` but may not be on PATH.
3. Either add the Debuggers directory to PATH, or set `CDB_PATH` to the full path of cdb.exe.
4. **Stop and tell the user** — no debugging is possible without CDB.

## Description

Debug Windows native binaries (C/C++) using CDB (Console Debugger) through MCP tools. Covers crash triage, memory inspection, breakpoint-driven analysis, and root cause identification — all without a GUI.

## Tools

- `cdb_launch` — Start a debug session on an .exe or .dmp file
- `cdb_attach` — Attach to a running process by PID or name
- `cdb_terminate` — End a debug session
- `cdb_session_info` — Check session state and metadata
- `cdb_step` — Control execution: go (`g`), step over (`p`), step into (`t`), step out (`gu`)
- `cdb_break` — Interrupt a running target (Ctrl+Break)
- `cdb_set_breakpoint` — Set breakpoints (`bp`, `bu`, `bm`)
- `cdb_list_breakpoints` — List active breakpoints
- `cdb_exception_handling` — Configure first/second chance exception behavior
- `cdb_analyze` — Run `!analyze -v` for automated crash triage
- `cdb_stack_trace` — Display call stack (`k`, `kpn`, `kvn`)
- `cdb_registers` — Show CPU register values
- `cdb_locals` — Show local variables (`dv`)
- `cdb_examine_memory` — Read memory in various formats (`db`, `dq`, `dps`, etc.)
- `cdb_read_string` — Read ASCII or Unicode strings from memory
- `cdb_disassemble` — Disassemble instructions or entire functions
- `cdb_evaluate` — Evaluate debugger expressions (`? expr`)
- `cdb_exception_record` — Show exception record and context (`.ecxr`)
- `cdb_switch_frame` — Navigate stack frames
- `cdb_switch_thread` — Switch active thread
- `cdb_symbols` — Search for symbols by wildcard pattern
- `cdb_near_symbol` — Resolve an address to the nearest symbol
- `cdb_data_type` — Display struct layouts or dump live instances
- `cdb_modules` — List loaded modules
- `cdb_command` — Send any raw CDB command
- `cdb_search_memory` — Search memory for byte patterns or strings
- `cdb_heap` — Inspect heap state for corruption analysis
- `cdb_threads` — List all threads with stack traces

## Workflow: Crash Triage

1. **Launch** with `cdb_launch`. Always use `disable_debug_heap: true` for realistic heap behavior.
2. **Run to crash** with `cdb_step` action `g`. Use a generous timeout (30–60s).
3. **Triage** with `cdb_analyze`. This identifies exception type, faulting instruction, and probable cause.
4. **Inspect context**: `cdb_stack_trace`, then `cdb_registers`, then `cdb_locals` to understand the crash frame.
5. **Switch frames** with `cdb_switch_frame` to examine callers if the crash frame lacks symbols.
6. **Read memory** with `cdb_examine_memory` to inspect pointers, buffers, and structures.
7. **Disassemble** with `cdb_disassemble` to verify what instruction faulted.
8. **Terminate** with `cdb_terminate` when done.

## Workflow: Binary-Only Bug Hunting (No Source)

1. Launch with `disable_debug_heap: true`.
2. Use `cdb_symbols` to discover function names (e.g., `module!*`).
3. Use `cdb_disassemble` with `function: true` to reverse-engineer each function.
4. Set breakpoints on interesting functions with `cdb_set_breakpoint`.
5. Run with `cdb_step` action `g`, then inspect state when breakpoints hit.
6. Use `cdb_examine_memory` and `cdb_data_type` to understand data structures.
7. Use `cdb_evaluate` to compute offsets, dereference pointers, and test hypotheses.

## Workflow: Heap Corruption

1. Launch with `app_verifier: true` for heap instrumentation, or `disable_debug_heap: true` for natural behavior.
2. Run to the crash.
3. Use `cdb_heap` with `!heap -s` for a summary, then `!heap -p -a <addr>` for page heap details.
4. Check the exception record with `cdb_exception_record`.
5. Look for use-after-free patterns: freed blocks being written to, double-frees, buffer overruns.

## Workflow: Browser / Chromium Debugging

Chromium-based browsers (Edge, Chrome) are multi-process and split across many DLLs. Extra steps are needed.

### Setup symbols

After launch, ensure the build output directory is on the symbol path:
```
cdb_command: .sympath+ D:\path\to\out\dir
cdb_command: .reload
```
Without `.pdb` files (`symbol_level = 2` in GN args), debugging is blind.

### Multi-process debugging

Browser code often runs in a child (renderer, GPU, utility) process — not the main browser process.

- Enable child process debugging early: `cdb_command` with `.childdbg 1`
- To break in a child on load, use: `cdb_command` with `sxe -c "bp blink_core!blink::MyClass::Method" cpr`
- After a child spawns, use `cdb_command` with `|` to list processes and `|<n>s` to switch.

### Chromium module map

Chromium component builds split code across DLLs. Use the right module prefix in breakpoints and symbol searches:

| Module prefix | Contains |
|---------------|----------|
| `blink_core!` | Layout, DOM, Blink core |
| `content!` | Content layer (navigation, frames, workers) |
| `base!` | Base utilities (strings, threading, containers) |
| `chrome!` / `msedge!` | Browser-layer code (UI, profiles, extensions) |
| `v8!` | JavaScript engine |
| `cc!` | Compositor |
| `net!` | Network stack |
| `gpu!` | GPU process code |

For non-component (static/release) builds, most code is in `msedge.dll` or `chrome.dll`.

Check `ModLoad` lines in launch output or use `cdb_modules` to find which DLL contains your code.

### GTest debugging

For unit/browser tests, filter to a **single failing test** and use single-process mode:
```
cdb_launch: target_binary="out\Debug\unit_tests.exe"
            target_args="--gtest_filter=Suite.Test --single-process-tests"
```

### Performance

- Debug browser builds take **30–60+ seconds** to start. Use `timeout: 120` or higher on `cdb_step` action `g`.
- Use `skip_initial_break: true` and `skip_final_break: true` for faster startup when you only care about your own breakpoints.
- ASan browser builds: always use `disable_debug_heap: true` and `exception_handling: ["-xd av"]`.

## Best Practices

- **Always launch with `disable_debug_heap: true`** unless you specifically need the debug heap. The debug heap changes allocation behavior and can mask or hide real bugs.
- **Use `cdb_analyze` first** on any crash — it gives you the best starting point before manual inspection.
- **Prefer `kpn` for stack traces** — it shows frame numbers and parameter values, which are the most useful for triage.
- **Use `dps` for memory inspection** by default — it shows pointer-sized values with symbol resolution, immediately revealing function pointers and vtables.
- **For ASan binaries**, launch with `exception_handling: ["-xd av"]` to let ASan handle access violations instead of breaking on first chance.
- **Check `cdb_session_info`** if commands return unexpected errors — the target may have exited.
- **Use `cdb_command`** for anything the specialized tools don't cover. CDB has hundreds of commands; the tools wrap the most common ones.
- **When disassembling without source**, use `cdb_symbols` with `module!*` to get an overview of all functions before diving into specific ones.
- **For multi-threaded bugs**, use `cdb_threads` to see all thread stacks, then `cdb_switch_thread` to inspect suspicious threads individually.

## Common Pitfalls

- Forgetting to increase `timeout` when using `cdb_step` with action `g` — the default 30s may not be enough for slow targets.
- Not using `.ecxr` (via `cdb_exception_record`) before inspecting registers at a crash — without it, registers show the debugger's context, not the crash context.
- Trying to set breakpoints in a noninvasive attach session — use invasive attach for breakpoint support.
- Running `cdb_analyze` on a non-crash break (e.g., initial breakpoint) — it only produces useful output at an actual exception.
