from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .synthesis import Plan, RecordingBundle, normalize_plan_variables


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
    start_url: Optional[str] = None


@dataclass
class StoredPlan:
    plan_id: str
    recording_id: str
    plan: Plan
    created_at: datetime
    updated_at: datetime
    prompt: Optional[str] = None
    raw_response: Optional[str] = None
    checkpoints: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    has_variables: bool = False


@dataclass
class PlanSummary:
    plan_id: str
    recording_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    has_variables: bool


class RecordingStore:
    """SQLite-backed storage for recordings captured via the frontend."""

    def __init__(self, *, db_path: Optional[Path] = None) -> None:
        self._lock = asyncio.Lock()
        default_path = Path(__file__).resolve().parent / "data" / "recordings.sqlite3"
        self._db_path = Path(db_path or default_path).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """
        Initialize the recordings database with necessary tables.
        Schema:
        - recording_id: unique identifier
        - title: optional recording name
        - status: 'started' or 'completed'
        - bundle_json: serialized RecordingBundle (frames, markers, audio, transcript)
        - events_json: serialized list of events
        - created_at, updated_at, ended_at: timestamps
        - start_url: the URL the recording was made on
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recordings (
                    recording_id TEXT PRIMARY KEY,
                    title TEXT,
                    status TEXT NOT NULL,
                    bundle_json TEXT,
                    events_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ended_at TEXT,
                    start_url TEXT
                )
                """
            )
            # Backfill the start_url column when migrating from older schemas.
            cursor = conn.execute("PRAGMA table_info(recordings)")
            columns = {row[1] for row in cursor.fetchall()}
            if "start_url" not in columns:
                conn.execute("ALTER TABLE recordings ADD COLUMN start_url TEXT")
            conn.commit()
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_recordings_status
                ON recordings (status, updated_at DESC)
                """
            )

    async def start(
        self,
        title: Optional[str],
        *,
        recording_id: Optional[str] = None,
        start_url: Optional[str] = None,
    ) -> StoredRecording:
        async with self._lock:
            rec_id = recording_id or uuid.uuid4().hex
            now = _utc_now()

            def _write() -> StoredRecording:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    # Check if recording already exists
                    cursor = conn.execute(
                        "SELECT recording_id FROM recordings WHERE recording_id = ?",
                        (rec_id,),
                    )
                    if cursor.fetchone() is not None:
                        raise KeyError(f"Recording {rec_id} already exists")

                    # Insert new recording
                    conn.execute(
                        """
                        INSERT INTO recordings (
                            recording_id, title, status, bundle_json, events_json,
                            created_at, updated_at, ended_at, start_url
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rec_id,
                            title,
                            "started",
                            None,  # bundle_json starts as NULL
                            json.dumps([]),  # events_json starts as empty array
                            now.isoformat(),
                            now.isoformat(),
                            None,  # ended_at starts as NULL
                            start_url,
                        ),
                    )
                    conn.commit()

                return StoredRecording(
                    recording_id=rec_id,
                    title=title,
                    status="started",
                    created_at=now,
                    updated_at=now,
                    bundle=None,
                    events=[],
                    ended_at=None,
                    start_url=start_url,
                )

            return await asyncio.to_thread(_write)

    async def complete(self, recording_id: str, bundle: RecordingBundle) -> StoredRecording:
        async with self._lock:
            now = _utc_now()

            def _write() -> StoredRecording:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    # Fetch existing recording
                    cursor = conn.execute(
                        "SELECT * FROM recordings WHERE recording_id = ?",
                        (recording_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise KeyError(recording_id)

                    # Parse existing events
                    existing_events = json.loads(row["events_json"]) if row["events_json"] else []

                    # Merge events into bundle
                    bundle.events = existing_events

                    # Serialize bundle to JSON
                    try:
                        bundle_dict = bundle.model_dump(mode="json", by_alias=True)
                    except AttributeError:  # Pydantic v1 fallback
                        bundle_dict = bundle.dict(by_alias=True)  # type: ignore[call-arg]
                    bundle_json = json.dumps(bundle_dict)

                    # Update recording
                    conn.execute(
                        """
                        UPDATE recordings
                        SET status = ?, bundle_json = ?, updated_at = ?, ended_at = ?
                        WHERE recording_id = ?
                        """,
                        (
                            "completed",
                            bundle_json,
                            now.isoformat(),
                            now.isoformat(),
                            recording_id,
                        ),
                    )
                    conn.commit()

                    # Return updated recording
                    created_at = datetime.fromisoformat(row["created_at"])
                    return StoredRecording(
                        recording_id=recording_id,
                        title=row["title"],
                        status="completed",
                        created_at=created_at,
                        updated_at=now,
                        bundle=bundle,
                        events=existing_events,
                        ended_at=now,
                        start_url=row["start_url"],
                    )

            return await asyncio.to_thread(_write)

    async def get(self, recording_id: str) -> StoredRecording:
        async with self._lock:
            def _read() -> StoredRecording:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        "SELECT * FROM recordings WHERE recording_id = ?",
                        (recording_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise KeyError(recording_id)

                    # Deserialize bundle if present
                    bundle = None
                    if row["bundle_json"]:
                        try:
                            bundle_data = json.loads(row["bundle_json"])
                            bundle = RecordingBundle.model_validate(bundle_data)
                        except Exception:
                            # If bundle parsing fails, leave it as None
                            pass

                    # Deserialize events
                    events = json.loads(row["events_json"]) if row["events_json"] else []

                    return StoredRecording(
                        recording_id=row["recording_id"],
                        title=row["title"],
                        status=row["status"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.fromisoformat(row["updated_at"]),
                        bundle=bundle,
                        events=events,
                        ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                        start_url=row["start_url"],
                    )

            return await asyncio.to_thread(_read)

    async def exists(self, recording_id: str) -> bool:
        async with self._lock:
            def _check() -> bool:
                with sqlite3.connect(self._db_path) as conn:
                    cursor = conn.execute(
                        "SELECT 1 FROM recordings WHERE recording_id = ?",
                        (recording_id,),
                    )
                    return cursor.fetchone() is not None

            return await asyncio.to_thread(_check)

    async def append_events(self, recording_id: str, events: List[Dict[str, object]]) -> None:
        if not events:
            return
        async with self._lock:
            now = _utc_now()

            def _write() -> None:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    # Fetch existing recording
                    cursor = conn.execute(
                        "SELECT events_json FROM recordings WHERE recording_id = ?",
                        (recording_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise KeyError(recording_id)

                    # Parse existing events and append new ones
                    existing_events = json.loads(row["events_json"]) if row["events_json"] else []
                    existing_events.extend(events)

                    # Update database
                    conn.execute(
                        "UPDATE recordings SET events_json = ?, updated_at = ? WHERE recording_id = ?",
                        (json.dumps(existing_events), now.isoformat(), recording_id),
                    )
                    conn.commit()

            await asyncio.to_thread(_write)

    async def get_bundle_payload(self, recording_id: str) -> Dict[str, object]:
        async with self._lock:
            def _read() -> Dict[str, object]:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        "SELECT * FROM recordings WHERE recording_id = ?",
                        (recording_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise KeyError(recording_id)

                    # Parse bundle or create empty one
                    if row["bundle_json"]:
                        try:
                            bundle_data = json.loads(row["bundle_json"])
                            bundle = RecordingBundle.model_validate(bundle_data)
                            bundle_payload = bundle.model_dump(by_alias=True)
                        except Exception:
                            # Fallback to empty bundle if parsing fails
                            bundle_payload = {
                                "frames": [],
                                "markers": [],
                                "audioWavBase64": None,
                                "transcript": None,
                            }
                    else:
                        bundle_payload = {
                            "frames": [],
                            "markers": [],
                            "audioWavBase64": None,
                            "transcript": None,
                        }

                    # Add events
                    events = json.loads(row["events_json"]) if row["events_json"] else []
                    bundle_payload["events"] = events

                    # Add metadata
                    bundle_payload["meta"] = {
                        "recordingId": row["recording_id"],
                        "title": row["title"],
                        "status": row["status"],
                        "startedAt": row["created_at"],
                        "updatedAt": row["updated_at"],
                        "endedAt": row["ended_at"],
                        "startUrl": row["start_url"],
                    }

                    return bundle_payload

            return await asyncio.to_thread(_read)

    async def list(self) -> List[StoredRecording]:
        """List all recordings ordered by most recent first."""
        async with self._lock:
            def _read() -> List[StoredRecording]:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        """
                        SELECT * FROM recordings
                        ORDER BY updated_at DESC
                        LIMIT 100
                        """
                    )
                    rows = cursor.fetchall()

                    recordings: List[StoredRecording] = []
                    for row in rows:
                        # Deserialize bundle if present
                        bundle = None
                        if row["bundle_json"]:
                            try:
                                bundle_data = json.loads(row["bundle_json"])
                                bundle = RecordingBundle.model_validate(bundle_data)
                            except Exception:
                                pass

                        # Deserialize events
                        events = json.loads(row["events_json"]) if row["events_json"] else []

                        recordings.append(StoredRecording(
                            recording_id=row["recording_id"],
                            title=row["title"],
                            status=row["status"],
                            created_at=datetime.fromisoformat(row["created_at"]),
                            updated_at=datetime.fromisoformat(row["updated_at"]),
                            bundle=bundle,
                            events=events,
                            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                            start_url=row["start_url"],
                        ))

                    return recordings

            return await asyncio.to_thread(_read)


class PlanStore:
    """SQLite-backed plan registry keyed by plan id."""

    def __init__(self, *, db_path: Optional[Path] = None) -> None:
        self._lock = asyncio.Lock()
        default_path = Path(__file__).resolve().parent / "data" / "plans.sqlite3"
        self._db_path = Path(db_path or default_path).resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    recording_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    prompt TEXT,
                    raw_response TEXT,
                    checkpoints_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_plans_recording
                ON plans (recording_id, updated_at DESC)
                """
            )

    @staticmethod
    def _plan_to_json(plan: Plan) -> str:
        try:
            payload = plan.model_dump(mode="json", by_alias=True)
        except AttributeError:  # pragma: no cover - Pydantic v1 fallback
            payload = plan.dict(by_alias=True)  # type: ignore[call-arg]
        return json.dumps(payload)

    @staticmethod
    def _plan_from_json(payload: str) -> Plan:
        data = json.loads(payload)
        return Plan.model_validate(data)

    @staticmethod
    def _decode_checkpoints(payload: Optional[str]) -> Dict[str, List[Dict[str, Any]]]:
        if not payload:
            return {}
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _row_to_stored_plan(row: sqlite3.Row) -> StoredPlan:
        plan = PlanStore._plan_from_json(row["plan_json"])
        plan, _ = normalize_plan_variables(plan)
        checkpoints = PlanStore._decode_checkpoints(row["checkpoints_json"])
        return StoredPlan(
            plan_id=row["plan_id"],
            recording_id=row["recording_id"],
            plan=plan,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            prompt=row["prompt"],
            raw_response=row["raw_response"],
            checkpoints=checkpoints,
            has_variables=plan.has_variables,
        )

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> PlanSummary:
        plan = PlanStore._plan_from_json(row["plan_json"])
        plan, _ = normalize_plan_variables(plan)
        return PlanSummary(
            plan_id=row["plan_id"],
            recording_id=row["recording_id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            has_variables=plan.has_variables,
        )

    async def save(
        self,
        recording_id: str,
        plan: Plan,
        *,
        plan_id: Optional[str] = None,
        prompt: Optional[str] = None,
        raw_response: Optional[str] = None,
        checkpoints: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> StoredPlan:
        plan, _ = normalize_plan_variables(plan)
        plan_key = plan_id or uuid.uuid4().hex
        now = _utc_now()
        plan_json = self._plan_to_json(plan)
        checkpoints_json = json.dumps(checkpoints or {})

        async with self._lock:
            def _write() -> StoredPlan:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        "SELECT created_at FROM plans WHERE plan_id = ?",
                        (plan_key,),
                    )
                    existing = cursor.fetchone()
                    created_at = existing["created_at"] if existing else now.isoformat()
                    conn.execute(
                        """
                        INSERT INTO plans (
                            plan_id,
                            recording_id,
                            name,
                            plan_json,
                            prompt,
                            raw_response,
                            checkpoints_json,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(plan_id) DO UPDATE SET
                            recording_id=excluded.recording_id,
                            name=excluded.name,
                            plan_json=excluded.plan_json,
                            prompt=excluded.prompt,
                            raw_response=excluded.raw_response,
                            checkpoints_json=excluded.checkpoints_json,
                            updated_at=excluded.updated_at
                        """,
                        (
                            plan_key,
                            recording_id,
                            plan.name,
                            plan_json,
                            prompt,
                            raw_response,
                            checkpoints_json,
                            created_at,
                            now.isoformat(),
                        ),
                    )
                    conn.commit()
                    cursor = conn.execute(
                        "SELECT * FROM plans WHERE plan_id = ?",
                        (plan_key,),
                    )
                    row = cursor.fetchone()
                    if row is None:  # pragma: no cover - defensive
                        raise KeyError(plan_key)
                    return self._row_to_stored_plan(row)

            return await asyncio.to_thread(_write)

    async def get(self, plan_id: str) -> StoredPlan:
        async with self._lock:
            def _read() -> StoredPlan:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        "SELECT * FROM plans WHERE plan_id = ?",
                        (plan_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise KeyError(plan_id)
                    return self._row_to_stored_plan(row)

            return await asyncio.to_thread(_read)

    async def list_for_recording(self, recording_id: str) -> list[StoredPlan]:
        async with self._lock:
            def _read() -> list[StoredPlan]:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        """
                        SELECT * FROM plans
                        WHERE recording_id = ?
                        ORDER BY updated_at DESC
                        """,
                        (recording_id,),
                    )
                    rows = cursor.fetchall()
                    return [self._row_to_stored_plan(row) for row in rows]

            return await asyncio.to_thread(_read)

    async def list_summary(
        self, *, recording_id: Optional[str] = None
    ) -> list[PlanSummary]:
        async with self._lock:
            def _read() -> list[PlanSummary]:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    if recording_id:
                        cursor = conn.execute(
                            """
                            SELECT plan_id, recording_id, name, plan_json, created_at, updated_at
                            FROM plans
                            WHERE recording_id = ?
                            ORDER BY updated_at DESC
                            """,
                            (recording_id,),
                        )
                    else:
                        cursor = conn.execute(
                            """
                            SELECT plan_id, recording_id, name, plan_json, created_at, updated_at
                            FROM plans
                            ORDER BY updated_at DESC
                            """
                        )
                    rows = cursor.fetchall()
                    return [self._row_to_summary(row) for row in rows]

            return await asyncio.to_thread(_read)

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
            def _write() -> StoredPlan:
                with sqlite3.connect(self._db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    # Read current
                    row = conn.execute(
                        "SELECT * FROM plans WHERE plan_id = ?",
                        (plan_id,),
                    ).fetchone()
                    if row is None:
                        raise KeyError(plan_id)

                    current = self._row_to_stored_plan(row)
                    target_plan = plan or current.plan
                    if name:
                        target_plan = self._copy_with_name(target_plan, name)
                    target_plan, _ = normalize_plan_variables(target_plan)
                    plan_json = self._plan_to_json(target_plan)

                    # Update
                    now_iso = _utc_now().isoformat()
                    conn.execute(
                        "UPDATE plans SET name = ?, plan_json = ?, updated_at = ? WHERE plan_id = ?",
                        (target_plan.name, plan_json, now_iso, plan_id),
                    )
                    conn.commit()

                    # Read back
                    updated_row = conn.execute(
                        "SELECT * FROM plans WHERE plan_id = ?",
                        (plan_id,),
                    ).fetchone()
                    if updated_row is None:  # pragma: no cover - defensive
                        raise KeyError(plan_id)
                    return self._row_to_stored_plan(updated_row)

            return await asyncio.to_thread(_write)


# -----------------------------------------------------------------------------
# Visual checkpoint helpers (module-level, in-memory)
# -----------------------------------------------------------------------------
# Mapping: recording_id -> { step_id -> [ { "png_base64": str, "label": Optional[str] }, ... ] }
_VISUAL_CHECKPOINTS: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

def save_visual_checkpoints_for_recording(recording_id: str, mapping: Dict[str, List[Dict[str, Any]]]) -> None:
    """
    Persist visual checkpoints in memory for a given recording. This matches the
    interface expected by synthesis/runner integration.
    Only keeps entries that include a 'png_base64' field.
    """
    if not isinstance(mapping, dict):
        return
    sanitized: Dict[str, List[Dict[str, Any]]] = {}
    for step_id, items in mapping.items():
        if not isinstance(step_id, str) or not isinstance(items, list):
            continue
        valid_items: List[Dict[str, Any]] = []
        for it in items:
            if isinstance(it, dict) and "png_base64" in it:
                valid_items.append({"png_base64": it["png_base64"], "label": it.get("label")})
        if valid_items:
            sanitized[step_id] = valid_items
    if sanitized:
        _VISUAL_CHECKPOINTS[recording_id] = sanitized

def get_visual_checkpoints_for_recording(recording_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retrieve the entire checkpoint mapping for a recording.
    Returns {} if none exist.
    """
    return dict(_VISUAL_CHECKPOINTS.get(recording_id, {}))

def get_visual_checkpoints_for_step(recording_id: str, step_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve the list of checkpoints for a specific step within a recording.
    Returns [] if none exist.
    """
    rec_map = _VISUAL_CHECKPOINTS.get(recording_id, {})
    return list(rec_map.get(step_id, []))
