"""
Entry point for running the MCP server as a module.

Usage:
    python -m mcp_server
    python -m mcp_server --log-level DEBUG
"""

from .main import main

if __name__ == "__main__":
    main()
