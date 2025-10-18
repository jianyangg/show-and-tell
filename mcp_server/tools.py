"""MCP tool registration for the runner backend."""

from __future__ import annotations

import asyncio
import logging
import base64
import binascii
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from mcp.server.fastmcp import FastMCP

from .config import ServerConfig
from .runner_client import PlanDetail, RunnerClient, create_runner_client, plan_summary_to_dict, plan_to_dict
from .streams import (
    run_event_stream,
    teach_event_stream,
)

logger = logging.getLogger(__name__)

LIST_PLANS_ARGS: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recording_id": {
            "type": ["string", "null"],
            "description": "Optional recording identifier to filter plans",
        }
    },
}

PLAN_SUMMARY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "planId": {"type": "string"},
        "recordingId": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "createdAt": {"type": "string"},
        "updatedAt": {"type": "string"},
        "hasVariables": {"type": "boolean"},
    },
}

PLAN_COLLECTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "plans": {
            "type": "array",
            "items": PLAN_SUMMARY_SCHEMA,
        }
    },
    "required": ["plans"],
}

PLAN_DETAIL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "planId": {"type": "string"},
        "recordingId": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "createdAt": {"type": "string"},
        "updatedAt": {"type": "string"},
        "hasVariables": {"type": "boolean"},
        "prompt": {"type": ["string", "null"]},
        "rawResponse": {"type": ["string", "null"]},
        "plan": {"type": "object"},
    },
    "required": ["planId", "plan"],
}

RECORDING_COLLECTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "recordings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "recordingId": {"type": "string"},
                    "title": {"type": ["string", "null"]},
                    "status": {"type": "string"},
                    "createdAt": {"type": "string"},
                    "updatedAt": {"type": "string"},
                    "endedAt": {"type": ["string", "null"]},
                },
            },
        }
    },
    "required": ["recordings"],
}

SYNTHESIZE_ARGS: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recording_id", "prompt"],
    "properties": {
        "recording_id": {"type": "string"},
        "prompt": {"type": "string"},
        "plan_name": {"type": ["string", "null"]},
    },
}

START_RUN_ARGS: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["plan_id"],
    "properties": {
        "plan_id": {"type": "string"},
        "variables": {
            "type": "object",
            "additionalProperties": {"type": ["string", "number"]},
        },
    },
}

ABORT_ARGS: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["run_id"],
    "properties": {"run_id": {"type": "string"}},
}

CAPTURE_ARGS: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["run_id"],
    "properties": {
        "run_id": {"type": "string"},
        "label": {
            "type": ["string", "null"],
            "description": "Optional description for the screenshot artifact",
        },
    },
}


def build_fastmcp_server(config: ServerConfig) -> FastMCP:
    """
    Create and configure a FastMCP server for the runner backend.

    FastMCP provides a high-level decorator-based API for defining MCP tools.
    It automatically handles JSON-RPC communication, input validation, and
    result serialization. This function registers all runner-related tools
    (plan management, recording management, run execution, etc.) with the
    MCP server instance.

    Note: The runner client is created lazily on first use and stored in the
    FastMCP context, ensuring proper async initialization and resource cleanup.
    """
    mcp = FastMCP("runner-mcp")

    # Store client and config in the MCP context for access by tool handlers
    # We'll initialize the client lazily on first tool invocation
    _client: Optional[RunnerClient] = None
    _client_lock = asyncio.Lock()

    async def get_client() -> RunnerClient:
        """Lazily initialize and return the runner client."""
        nonlocal _client
        async with _client_lock:
            if _client is None:
                _client = await create_runner_client(config.base_url, config.auth)
        return _client

    @mcp.tool()
    async def list_plans(recording_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List stored plans visible to the runner backend.

        Args:
            recording_id: Optional recording identifier to filter plans

        Returns:
            A dictionary containing a list of plan summaries with metadata
        """
        client = await get_client()
        plans = await client.list_plans(recording_id)
        return {"plans": [plan_summary_to_dict(plan) for plan in plans]}

    @mcp.tool()
    async def get_plan_details(plan_id: str) -> Dict[str, Any]:
        """
        Fetch a plan definition, including steps and variable metadata.

        Args:
            plan_id: The unique identifier for the plan

        Returns:
            Detailed plan information including steps, variables, and metadata
        """
        client = await get_client()
        detail = await client.get_plan(plan_id)
        return _plan_detail_to_dict(detail)

    @mcp.tool()
    async def save_plan(plan_id: str, name: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update the name or body of a stored plan.

        Args:
            plan_id: The unique identifier for the plan
            name: The new name for the plan
            plan: The plan definition object containing steps and variables

        Returns:
            The updated plan details
        """
        client = await get_client()
        updated_plan = _parse_plan_from_mapping(plan)
        detail = await client.save_plan(plan_id, name, updated_plan)
        return _plan_detail_to_dict(detail)

    @mcp.tool()
    async def list_recordings() -> Dict[str, Any]:
        """
        List all recordings captured by the runner.

        Returns:
            A dictionary containing a list of recording metadata including
            IDs, titles, status, and timestamps
        """
        client = await get_client()
        recordings = await client.list_recordings()
        return {
            "recordings": [
                {
                    "recordingId": rec.recording_id,
                    "title": rec.title,
                    "status": rec.status,
                    "createdAt": rec.created_at,
                    "updatedAt": rec.updated_at,
                    "endedAt": rec.ended_at,
                }
                for rec in recordings
            ]
        }

    @mcp.tool()
    async def get_recording_bundle(recording_id: str) -> Dict[str, Any]:
        """
        Download a recording bundle containing frames, events, and audio metadata.

        Args:
            recording_id: The unique identifier for the recording

        Returns:
            The complete recording bundle with all associated data
        """
        client = await get_client()
        bundle = await client.get_recording_bundle(recording_id)
        try:
            return bundle.model_dump()
        except AttributeError:  # pragma: no cover - Pydantic v1
            return bundle.dict()  # type: ignore[attr-defined]

    @mcp.tool()
    async def synthesize_plan(
        recording_id: str, prompt: str, plan_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Call the synthesis endpoint with a recording and prompt.

        Args:
            recording_id: The recording to synthesize a plan from
            prompt: Instructions for plan synthesis
            plan_name: Optional name for the generated plan

        Returns:
            The synthesized plan with metadata and debug information
        """
        client = await get_client()
        request = _build_synthesis_request(recording_id, prompt, plan_name)
        response = await client.synthesize_plan(request)
        return {
            "planId": response.plan_id,
            "recordingId": response.recording_id,
            "createdAt": str(response.created_at),
            "updatedAt": str(response.updated_at),
            "plan": plan_to_dict(response.plan),
            "debugPrompt": response.debug_prompt,
        }

    @mcp.tool()
    async def start_run(plan_id: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Start a new automation run from a stored plan.

        Args:
            plan_id: The plan to execute
            variables: Optional variables to inject into the plan execution

        Returns:
            The run execution details including run ID and status
        """
        client = await get_client()
        response = await client.start_run(plan_id, variables)
        return response

    @mcp.tool()
    async def abort_run(run_id: str) -> Dict[str, Any]:
        """
        Abort an in-flight run.

        Args:
            run_id: The run to abort

        Returns:
            Confirmation of the abort operation
        """
        client = await get_client()
        response = await client.abort_run(run_id)
        return response

    @mcp.tool()
    async def capture_screenshot(
        run_id: str, label: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Request a screenshot for the supplied run identifier.

        Args:
            run_id: The run to capture a screenshot from
            label: Optional description for the screenshot artifact

        Returns:
            Screenshot data including image path and metadata. The response includes:
            - ok: Whether the capture was successful
            - path: Absolute path to the saved screenshot file (if successful)
            - message: Status or error message
        """
        client = await get_client()
        response = await client.capture_screenshot(run_id)

        # Normalize the response format: map 'frame' to 'imageBase64' for compatibility
        if response.get("frame") and not response.get("imageBase64"):
            response["imageBase64"] = response["frame"]

        # Materialize the screenshot to disk and get the file path
        response = _materialize_screenshot(config, run_id, response)

        # Add label file if requested
        if label and response.get("path"):
            _write_label(Path(response["path"]), label)

        # Enhance the response message to include the file path for better visibility
        if response.get("ok") and response.get("path"):
            original_message = response.get("message", "Screenshot captured successfully")
            response["message"] = f"{original_message}. Saved to: {response['path']}"

        # Remove the large base64 frame data from the response since it's already saved to disk
        # This significantly reduces response size and token usage
        response.pop("frame", None)
        response.pop("imageBase64", None)

        return response

    # NOTE: FastMCP streaming support may differ from the lower-level SDK.
    # These streaming tools are temporarily disabled and need to be re-implemented
    # using FastMCP's streaming API once confirmed. For now, tools return
    # aggregated results instead of streams.

    # TODO: Re-implement streaming tools with FastMCP streaming API
    # @mcp.tool()
    # async def run_events(run_id: str):
    #     """Stream runner events for a run id."""
    #     client = await get_client()
    #     async for item in run_event_stream(client, run_id):
    #         yield item

    # @mcp.tool()
    # async def teach_events(teach_id: str):
    #     """Stream teach-mode websocket events."""
    #     client = await get_client()
    #     async for item in teach_event_stream(client, teach_id):
    #         yield item

    return mcp


def _build_synthesis_request(
    recording_id: str, prompt: str, plan_name: Optional[str]
) -> Any:
    from backend.app.schemas import PlanSynthesisRequest

    request = PlanSynthesisRequest(
        recordingId=recording_id,
        planName=plan_name,
        variableHints=prompt,
    )
    return request


def _parse_plan_from_mapping(payload: Mapping[str, Any]) -> Any:
    from backend.app.synthesis import Plan

    try:
        return Plan.model_validate(payload)
    except AttributeError:  # pragma: no cover - Pydantic v1 fallback
        return Plan.parse_obj(payload)  # type: ignore[attr-defined]


def _plan_detail_to_dict(detail: PlanDetail) -> Dict[str, Any]:
    return {
        "planId": detail.plan_id,
        "recordingId": detail.recording_id,
        "name": detail.name,
        "plan": plan_to_dict(detail.plan),
        "hasVariables": detail.has_variables,
        "prompt": detail.prompt,
        "rawResponse": detail.raw_response,
        "createdAt": detail.created_at,
        "updatedAt": detail.updated_at,
    }


def _write_label(path: Path, label: str) -> None:
    try:
        path = path.with_suffix(".txt")
        path.write_text(label, encoding="utf-8")
    except OSError:
        logger.warning("Failed to write label for %s", path)


def _materialize_screenshot(
    config: ServerConfig, run_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    run_dir = config.screenshot_dir / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Unable to create screenshot directory %s", run_dir)
        run_dir = config.screenshot_dir

    image_data = payload.get("imageBase64")
    if isinstance(image_data, str) and image_data:
        try:
            data = base64.b64decode(image_data)
        except (ValueError, binascii.Error):  # type: ignore[name-defined]
            data = None
        if data:
            timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            path = run_dir / f"screenshot-{timestamp}.png"
            try:
                path.write_bytes(data)
                payload.setdefault("path", str(path))
            except OSError:
                logger.warning("Failed to persist screenshot to %s", path)

    if "filename" in payload and "path" not in payload:
        candidate = run_dir / str(payload["filename"])
        payload["path"] = str(candidate)

    return payload


__all__ = ["build_fastmcp_server"]
