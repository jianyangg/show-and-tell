from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .synthesis import Plan, RecordingBundle


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StoredRecording:
    recording_id: str
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    bundle: Optional[RecordingBundle] = None
    events: List[Dict[str, object]] = field(default_factory=list)
    ended_at: Optional[datetime] = None


@dataclass
class StoredPlan:
    plan_id: str
    recording_id: str
    plan: Plan
    created_at: datetime
    updated_at: datetime
    prompt: Optional[str] = None
    raw_response: Optional[str] = None


class RecordingStore:
    """In-memory storage for recordings captured via the frontend."""

    def __init__(self) -> None:
        self._items: Dict[str, StoredRecording] = {}
        self._lock = asyncio.Lock()

    async def start(
        self, title: Optional[str], *, recording_id: Optional[str] = None
    ) -> StoredRecording:
        async with self._lock:
            rec_id = recording_id or uuid.uuid4().hex
            if rec_id in self._items:
                raise KeyError(f"Recording {rec_id} already exists")
            now = _utc_now()
            stored = StoredRecording(
                recording_id=rec_id,
                title=title,
                status="started",
                created_at=now,
                updated_at=now,
                bundle=None,
                events=[],
                ended_at=None,
            )
            self._items[rec_id] = stored
            return stored

    async def complete(self, recording_id: str, bundle: RecordingBundle) -> StoredRecording:
        async with self._lock:
            if recording_id not in self._items:
                raise KeyError(recording_id)
            stored = self._items[recording_id]
            bundle.events = list(stored.events)
            stored.bundle = bundle
            stored.status = "completed"
            now = _utc_now()
            stored.updated_at = now
            stored.ended_at = now
            return stored

    async def get(self, recording_id: str) -> StoredRecording:
        async with self._lock:
            if recording_id not in self._items:
                raise KeyError(recording_id)
            return self._items[recording_id]

    async def exists(self, recording_id: str) -> bool:
        async with self._lock:
            return recording_id in self._items

    async def append_events(self, recording_id: str, events: List[Dict[str, object]]) -> None:
        if not events:
            return
        async with self._lock:
            if recording_id not in self._items:
                raise KeyError(recording_id)
            stored = self._items[recording_id]
            stored.events.extend(events)
            stored.updated_at = _utc_now()

    async def get_bundle_payload(self, recording_id: str) -> Dict[str, object]:
        async with self._lock:
            if recording_id not in self._items:
                raise KeyError(recording_id)
            stored = self._items[recording_id]
            if stored.bundle is not None:
                bundle_payload = stored.bundle.model_dump(by_alias=True)
            else:
                bundle_payload = {
                    "frames": [],
                    "markers": [],
                    "audioWavBase64": None,
                    "transcript": None,
                }
            bundle_payload["events"] = list(stored.events)
            bundle_payload["meta"] = {
                "recordingId": stored.recording_id,
                "title": stored.title,
                "status": stored.status,
                "startedAt": stored.created_at.isoformat(),
                "updatedAt": stored.updated_at.isoformat(),
                "endedAt": stored.ended_at.isoformat() if stored.ended_at else None,
            }
            return bundle_payload


class PlanStore:
    """In-memory plan registry keyed by plan id."""

    def __init__(self) -> None:
        self._items: Dict[str, StoredPlan] = {}
        self._by_recording: Dict[str, list[str]] = {}
        self._lock = asyncio.Lock()

    async def save(
        self,
        recording_id: str,
        plan: Plan,
        *,
        plan_id: Optional[str] = None,
        prompt: Optional[str] = None,
        raw_response: Optional[str] = None,
    ) -> StoredPlan:
        async with self._lock:
            plan_key = plan_id or uuid.uuid4().hex
            now = _utc_now()
            stored = StoredPlan(
                plan_id=plan_key,
                recording_id=recording_id,
                plan=plan,
                created_at=now,
                updated_at=now,
                prompt=prompt,
                raw_response=raw_response,
            )
            self._items[plan_key] = stored
            self._by_recording.setdefault(recording_id, []).append(plan_key)
            return stored

    async def get(self, plan_id: str) -> StoredPlan:
        async with self._lock:
            if plan_id not in self._items:
                raise KeyError(plan_id)
            return self._items[plan_id]

    async def list_for_recording(self, recording_id: str) -> list[StoredPlan]:
        async with self._lock:
            plan_ids = list(self._by_recording.get(recording_id, []))
            return [self._items[plan_id] for plan_id in plan_ids if plan_id in self._items]

    def _copy_with_name(self, plan: Plan, name: str) -> Plan:
        try:
            return plan.model_copy(update={"name": name})  # type: ignore[attr-defined]
        except AttributeError:  # pragma: no cover - Pydantic v1 fallback
            return plan.copy(update={"name": name})  # type: ignore[call-arg]

    async def update(
        self,
        plan_id: str,
        *,
        name: Optional[str] = None,
        plan: Optional[Plan] = None,
    ) -> StoredPlan:
        async with self._lock:
            if plan_id not in self._items:
                raise KeyError(plan_id)
            stored = self._items[plan_id]
            new_plan = plan or stored.plan
            if name:
                new_plan = self._copy_with_name(new_plan, name)
            stored.plan = new_plan
            stored.updated_at = _utc_now()
            return stored
