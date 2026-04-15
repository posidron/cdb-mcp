"""
Test suite for cdb-mcp.

Tests launch the MCP server as a subprocess and communicate via JSON-RPC
over stdio, exactly as a real MCP client would. This exercises the full
stack: tool registration, argument parsing, CDB process management, and
output handling.

Requirements:
  - Debugging Tools for Windows (cdb.exe) installed
  - samples/buggy.exe present in the project root
"""
