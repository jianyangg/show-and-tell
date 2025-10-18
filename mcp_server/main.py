"""Entrypoint for the runner MCP server."""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from .config import ServerConfig
from .tools import build_fastmcp_server

LOGGER = logging.getLogger(__name__)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments for the MCP server.

    This allows users to configure the logging level at runtime, which is
    important for debugging MCP communication issues. Note that for STDIO
    transport, all logging goes to stderr to avoid corrupting the JSON-RPC
    messages sent over stdout.
    """
    parser = argparse.ArgumentParser(description="Run the runner MCP server")
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    """
    Main entry point for the MCP server.

    This function sets up logging, loads configuration from environment
    variables, initializes the runner client, and starts the FastMCP server
    with stdio transport. FastMCP handles all the MCP protocol details,
    allowing us to focus on implementing the tool logic.
    """
    try:
        args = parse_args(argv)
        # Configure logging to stderr (stdout is reserved for MCP JSON-RPC)
        logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

        config = ServerConfig.from_env()
        LOGGER.info("Starting MCP server against %s", config.base_url)

        # Build the FastMCP server with all tools registered
        # The runner_client will be created and injected into tool handlers
        mcp = build_fastmcp_server(config)

        # Run the server using stdio transport (standard for MCP servers)
        # This call blocks until the server is shut down
        mcp.run(transport='stdio')

    except KeyboardInterrupt:  # pragma: no cover - graceful shutdown
        LOGGER.info("MCP server interrupted")


if __name__ == "__main__":
    main()
