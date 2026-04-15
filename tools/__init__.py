"""
CDB MCP Tools package.

Importing this package registers all tool functions with the MCP server.
Tools are organized by category:

- session:    launch, session_info, terminate
- execution:  step, break, set_breakpoint, list_breakpoints
- inspection: analyze, stack_trace, registers, locals, examine_memory,
              read_string, disassemble, evaluate, exception_record
- navigation: switch_frame, switch_thread
- symbols:    symbols, near_symbol, data_type, modules
- advanced:   command, search_memory, heap, threads
"""

from tools import session      # noqa: F401
from tools import execution    # noqa: F401
from tools import inspection   # noqa: F401
from tools import navigation   # noqa: F401
from tools import symbols      # noqa: F401
from tools import advanced     # noqa: F401
