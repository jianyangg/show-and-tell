#!/usr/bin/env python3
"""
Simple test script for the MCP server.

This script creates an MCP client that connects to the server via stdio
and tests basic functionality like listing tools.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import mcp_server
sys.path.insert(0, str(Path(__file__).parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_mcp_server():
    """Test the MCP server by connecting and listing available tools."""

    # Define server parameters - run as a module to avoid import issues
    server_params = StdioServerParameters(
        command="python3",
        args=["-m", "mcp_server"],
        env={
            # Set environment variables required by ServerConfig
            "RUNNER_BASE_URL": "http://localhost:8000",  # Your backend URL
            # Add other required env vars if needed
        },
    )

    print("🚀 Starting MCP server...")

    # Connect to the server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            print("✅ Connected to MCP server!")

            # Initialize the session
            await session.initialize()
            print("✅ Session initialized")

            # List available tools
            tools_result = await session.list_tools()
            print(f"\n📋 Available tools ({len(tools_result.tools)}):")
            for tool in tools_result.tools:
                print(f"  • {tool.name}: {tool.description}")

            print("\n✅ MCP server test completed successfully!")


if __name__ == "__main__":
    try:
        asyncio.run(test_mcp_server())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
