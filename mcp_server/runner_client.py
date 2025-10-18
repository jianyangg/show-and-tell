"""Typed client wrappers around the FastAPI runner endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Mapping, Optional

import httpx
from backend.app.schemas import (
    PlanSynthesisRequest,
    PlanSynthesisResponse,
    RecordingBundle,
)
from backend.app.synthesis import Plan
from websockets.client import connect

from .config import RunnerAuth


@dataclass
class PlanSummary:
    """Summary metadata for a stored plan."""
    plan_id: str
    recording_id: str
    name: str
    created_at: str
    updated_at: str
    has_variables: bool


@dataclass
class PlanDetail:
    """Complete plan definition with all steps and metadata."""
    plan_id: str
    recording_id: str
    name: str
    plan: Plan
    has_variables: bool
    prompt: Optional[str]
    raw_response: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class RecordingSummary:
    """Summary metadata for a captured recording."""
    recording_id: str
    title: Optional[str]
    status: str
    created_at: str
    updated_at: str
    ended_at: Optional[str]


class RunnerClient:
    """Asynchronous HTTP client for the runner backend."""

    def __init__(
        self,
        base_url: str,
        auth: Optional[RunnerAuth] = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._auth = auth or RunnerAuth()
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers=self._auth.headers(),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> Dict[str, Any]:
        response = await self._client.get("health")
        response.raise_for_status()
        return response.json()

    async def list_plans(self, recording_id: Optional[str] = None) -> list[PlanSummary]:
        params = {"recordingId": recording_id} if recording_id else None
        response = await self._client.get("plans", params=params)
        response.raise_for_status()
        payload = response.json()
        items = []
        for item in payload.get("plans", []):
            items.append(
                PlanSummary(
                    plan_id=item.get("planId"),
                    recording_id=item.get("recordingId"),
                    name=item.get("name", ""),
                    created_at=item.get("createdAt", ""),
                    updated_at=item.get("updatedAt", ""),
                    has_variables=bool(item.get("hasVariables")),
                )
            )
        return items

    async def get_plan(self, plan_id: str) -> PlanDetail:
        response = await self._client.get(f"plans/{plan_id}")
        response.raise_for_status()
        payload = response.json()
        plan = _parse_plan(payload.get("plan"))
        return PlanDetail(
            plan_id=payload.get("planId"),
            recording_id=payload.get("recordingId"),
            name=plan.name,
            plan=plan,
            has_variables=bool(payload.get("hasVariables")),
            prompt=payload.get("prompt"),
            raw_response=payload.get("rawResponse"),
            created_at=payload.get("createdAt", ""),
            updated_at=payload.get("updatedAt", ""),
        )

    async def save_plan(self, plan_id: str, name: str, plan: Plan) -> PlanDetail:
        payload = {"name": name, "plan": _dump_plan(plan)}
        response = await self._client.post(f"plans/{plan_id}/save", json=payload)
        response.raise_for_status()
        # Fetch the latest plan snapshot so downstream tools receive the full payload.
        return await self.get_plan(plan_id)

    async def list_recordings(self) -> list[RecordingSummary]:
        response = await self._client.get("recordings")
        response.raise_for_status()
        payload = response.json()
        items = []
        for item in payload.get("recordings", []):
            items.append(
                RecordingSummary(
                    recording_id=item.get("recordingId"),
                    title=item.get("title"),
                    status=item.get("status", ""),
                    created_at=item.get("createdAt", ""),
                    updated_at=item.get("updatedAt", ""),
                    ended_at=item.get("endedAt"),
                )
            )
        return items

    async def get_recording_bundle(self, recording_id: str) -> RecordingBundle:
        response = await self._client.get(f"recordings/{recording_id}/bundle")
        response.raise_for_status()
        return _parse_recording_bundle(response.json())

    async def synthesize_plan(
        self,
        request: PlanSynthesisRequest,
    ) -> PlanSynthesisResponse:
        response = await self._client.post(
            "plans/synthesize", json=request.model_dump(by_alias=True)
        )
        response.raise_for_status()
        return PlanSynthesisResponse.model_validate(response.json())

    async def start_run(
        self,
        plan_id: str,
        variables: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"planId": plan_id}
        if variables:
            payload["variables"] = dict(variables)
        response = await self._client.post("runs/start", json=payload)
        response.raise_for_status()
        return response.json()

    async def abort_run(self, run_id: str) -> Dict[str, Any]:
        response = await self._client.post(f"runs/{run_id}/abort")
        response.raise_for_status()
        return response.json()

    async def capture_screenshot(self, run_id: str) -> Dict[str, Any]:
        response = await self._client.post(f"runs/{run_id}/capture")
        if response.status_code == httpx.codes.NOT_FOUND:
            return {"ok": False, "message": "capture endpoint unavailable"}
        response.raise_for_status()
        return response.json()

    async def stream(
        self, path: str, *, query: Optional[Mapping[str, str]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Connect to a websocket path and yield JSON payloads."""

        ws_url = self._to_ws_url(path, query=query)
        headers = dict(self._auth.headers())
        extra_headers = {str(k): str(v) for k, v in headers.items()}
        async with connect(ws_url, extra_headers=extra_headers) as websocket:
            async for message in websocket:
                if not message:
                    continue
                try:
                    yield json.loads(message)
                except json.JSONDecodeError:  # pragma: no cover - defensive parsing
                    continue

    def _to_ws_url(
        self, path: str, *, query: Optional[Mapping[str, str]] = None
    ) -> str:
        base = self._base_url
        if base.startswith("https"):
            scheme = "wss://"
            remainder = base[len("https://") :]
        elif base.startswith("http"):
            scheme = "ws://"
            remainder = base[len("http://") :]
        else:
            scheme = "ws://"
            remainder = base
        path = path.lstrip("/")
        ws = f"{scheme}{remainder}{path}"
        if query:
            query_pairs = [f"{key}={value}" for key, value in query.items()]
            return f"{ws}?{'&'.join(query_pairs)}"
        return ws


async def create_runner_client(
    base_url: str, auth: Optional[RunnerAuth] = None
) -> RunnerClient:
    client = RunnerClient(base_url, auth)
    # Issue a quick health check so failures surface early.
    await client.health()
    return client


__all__ = [
    "RunnerClient",
    "create_runner_client",
    "PlanSummary",
    "PlanDetail",
    "RecordingSummary",
    "plan_to_dict",
    "plan_summary_to_dict",
]


def _parse_plan(payload: Any) -> Plan:
    try:
        return Plan.model_validate(payload)
    except AttributeError:  # pragma: no cover - Pydantic v1 compatibility path
        return Plan.parse_obj(payload)  # type: ignore[attr-defined]


def _dump_plan(plan: Plan) -> Dict[str, Any]:
    try:
        return plan.model_dump(by_alias=True)
    except AttributeError:  # pragma: no cover - Pydantic v1 compatibility path
        return plan.dict(by_alias=True)  # type: ignore[attr-defined]


def _parse_recording_bundle(payload: Any) -> RecordingBundle:
    try:
        return RecordingBundle.model_validate(payload)
    except AttributeError:  # pragma: no cover - Pydantic v1 compatibility path
        return RecordingBundle.parse_obj(payload)  # type: ignore[attr-defined]


def plan_to_dict(plan: Plan) -> Dict[str, Any]:
    return _dump_plan(plan)


def plan_summary_to_dict(summary: PlanSummary) -> Dict[str, Any]:
    return {
        "planId": summary.plan_id,
        "recordingId": summary.recording_id,
        "name": summary.name,
        "createdAt": summary.created_at,
        "updatedAt": summary.updated_at,
        "hasVariables": summary.has_variables,
    }
