"""Helper utilities to bridge runner websocket streams into MCP streams."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict

from mcp import types

from .runner_client import RunnerClient

RUN_EVENT_STREAM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "message": {"type": "string"},
        "runId": {"type": "string"},
    },
    "required": ["type"],
}

TEACH_EVENT_STREAM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "teachId": {"type": "string"},
    },
    "required": ["type"],
}


async def run_event_stream(client: RunnerClient, run_id: str) -> AsyncIterator[types.JSONContent]:
    async for payload in client.stream(f"/ws/runs/{run_id}"):
        yield types.JSONContent(json=payload)


async def teach_event_stream(client: RunnerClient, teach_id: str) -> AsyncIterator[types.JSONContent]:
    async for payload in client.stream(f"/ws/teach/{teach_id}"):
        yield types.JSONContent(json=payload)


__all__ = [
    "run_event_stream",
    "teach_event_stream",
    "RUN_EVENT_STREAM_SCHEMA",
    "TEACH_EVENT_STREAM_SCHEMA",
]
