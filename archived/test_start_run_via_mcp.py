#!/usr/bin/env python3
"""
Test calling start_run through the MCP protocol to debug the 400 error.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_start_run_via_mcp():
    """Call start_run through MCP protocol like Claude would."""

    server_params = StdioServerParameters(
        command="python3",
        args=["-m", "mcp_server"],
        env={
            "RUNNER_BASE_URL": "http://localhost:8000",
        },
    )

    print("="*60)
    print("Testing start_run via MCP protocol")
    print("="*60 + "\n")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ MCP session initialized\n")

            # Test Case 1: With variables as dict
            print("Test 1: Calling start_run with variables")
            print("-" * 40)
            try:
                result = await session.call_tool(
                    "start_run",
                    arguments={
                        "plan_id": "3361a5f6d1f64cafa86aed664a666f27",
                        "variables": {
                            "greetingText": "hey!"
                        }
                    }
                )
                print(f"✅ Success!")
                print(f"📥 Result: {json.dumps(result.model_dump() if hasattr(result, 'model_dump') else result, indent=2)}\n")
            except Exception as e:
                print(f"❌ Error: {e}")
                print(f"   Error type: {type(e).__name__}\n")
                import traceback
                traceback.print_exc()

            # Test Case 2: Without variables
            print("\nTest 2: Calling start_run without variables")
            print("-" * 40)
            try:
                result = await session.call_tool(
                    "start_run",
                    arguments={
                        "plan_id": "3361a5f6d1f64cafa86aed664a666f27"
                    }
                )
                print(f"✅ Success!")
                print(f"📥 Result: {json.dumps(result.model_dump() if hasattr(result, 'model_dump') else result, indent=2)}\n")
            except Exception as e:
                print(f"❌ Error: {e}")
                print(f"   Error type: {type(e).__name__}\n")


if __name__ == "__main__":
    try:
        asyncio.run(test_start_run_via_mcp())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
