#!/usr/bin/env python3
"""
Start a run and provide instructions for viewing it in the frontend.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp_server.config import ServerConfig, RunnerAuth
from mcp_server.runner_client import create_runner_client


async def start_run_and_watch():
    """Start a run and show how to watch it in the frontend."""

    config = ServerConfig(
        base_url="http://127.0.0.1:8000",
        auth=RunnerAuth()
    )

    print("\n" + "="*60)
    print("🚀 STARTING RUN")
    print("="*60)

    plan_id = input("\nEnter Plan ID: ").strip() or "3361a5f6d1f64cafa86aed664a666f27"

    # Ask for variables
    print("\n📝 Variables (press Enter to skip):")
    variables = {}
    while True:
        var_name = input("  Variable name (or press Enter when done): ").strip()
        if not var_name:
            break
        var_value = input(f"  Value for '{var_name}': ").strip()
        variables[var_name] = var_value

    print(f"\n📤 Starting run with plan: {plan_id}")
    if variables:
        print(f"   Variables: {json.dumps(variables, indent=2)}")

    try:
        client = await create_runner_client(config.base_url, config.auth)

        result = await client.start_run(plan_id, variables if variables else None)
        run_id = result.get("runId")

        print("\n" + "="*60)
        print("✅ RUN STARTED SUCCESSFULLY!")
        print("="*60)
        print(f"\n🆔 Run ID: {run_id}")

        print("\n📺 TO VIEW IN FRONTEND:")
        print("-" * 60)
        print("\n1. Open your frontend in the browser")
        print("   (Usually http://localhost:5173 if using Vite)")
        print("\n2. Open Browser DevTools Console (F12 or Cmd+Option+I)")
        print("\n3. Run this command:")
        print(f"\n   connectToRun(\"{run_id}\")")
        print("\n4. Watch your automation run live! 🎬")
        print("\n" + "="*60 + "\n")

        await client.close()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        if hasattr(e, 'response'):
            print(f"   Response: {e.response.text}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(start_run_and_watch())
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled by user")
