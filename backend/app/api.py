from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

try:  # pragma: no cover - compatibility shim for Pydantic v1
    from pydantic import ConfigDict  # type: ignore
except ImportError:  # pragma: no cover
    ConfigDict = None  # type: ignore

from .runner import (
    AbortRequested,
    PlanRunner,
    RunnerCallbacks,
    RunnerError,
    VIEWPORT,
    teach_manager,
)
from .storage import PlanStore, RecordingStore, StoredPlan, StoredRecording
from .synthesis import (
    Plan,
    PlanSynthesisRequest,
    PlanSynthesisResult,
    PlanSynthesizer,
    RecordingBundle,
    RecordingFrame,
    RecordingMarker,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Gemini Computer Use Runner")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_root = Path(__file__).resolve().parent.parent.parent / "frontend"


class APIModel(BaseModel):
    """Base model ensuring populate-by-name for both Pydantic v1 and v2."""

    if ConfigDict is not None:  # pragma: no branch - resolved at import time
        model_config = ConfigDict(populate_by_name=True)  # type: ignore
    else:  # pragma: no cover - v1 fallback

        class Config:
            allow_population_by_field_name = True

recording_store = RecordingStore()
plan_store = PlanStore()
plan_synthesizer = PlanSynthesizer()
plan_runner = PlanRunner()

_FOCUS_INTROSPECTION_SCRIPT = """
() => {
    const doc = document;
    const active = doc.activeElement;
    if (!active || active === doc.body || active === doc.documentElement) {
        return null;
    }

    const describeNode = (el) => {
        if (!el || el.nodeType !== 1) return null;
        const tag = el.tagName ? el.tagName.toLowerCase() : "element";
        const id = el.id ? `#${el.id}` : "";
        const classes = el.classList ? Array.from(el.classList).slice(0, 3).map((cls) => `.${cls}`).join("") : "";
        const nameAttr = el.getAttribute ? el.getAttribute("name") : null;
        const roleAttr = el.getAttribute ? el.getAttribute("role") : null;
        const typeAttr = el.getAttribute ? el.getAttribute("type") : null;
        const ariaLabel = el.getAttribute ? el.getAttribute("aria-label") : null;
        const placeholder = el.getAttribute ? el.getAttribute("placeholder") : null;
        return {
            tag,
            descriptor: `${tag}${id}${classes}${nameAttr ? `[name=\"${nameAttr}\"]` : ""}${roleAttr ? `[role=\"${roleAttr}\"]` : ""}${typeAttr ? `[type=\"${typeAttr}\"]` : ""}`,
            ariaLabel: ariaLabel && ariaLabel.trim() ? ariaLabel.trim().slice(0, 120) : null,
            placeholder: placeholder && placeholder.trim() ? placeholder.trim().slice(0, 120) : null,
            valuePreview: typeof el.value === "string" && el.value.trim() ? el.value.trim().slice(0, 120) : null,
        };
    };

    const hierarchy = [];
    const seen = new Set();
    let node = active;
    while (node && node.nodeType === 1 && !seen.has(node)) {
        seen.add(node);
        const info = describeNode(node);
        if (info) {
            hierarchy.push(info);
        }
        if (node.parentElement) {
            node = node.parentElement;
            continue;
        }
        const root = node.getRootNode?.();
        if (root && root.host) {
            node = root.host;
            continue;
        }
        break;
    }

    if (!hierarchy.length) {
        return null;
    }

    const top = hierarchy[0];
    const selector = hierarchy.slice(0, 6).map((info) => info.descriptor).filter(Boolean).join(" > ");

    return {
        selector,
        tag: top.tag,
        ariaLabel: top.ariaLabel,
        placeholder: top.placeholder,
        valuePreview: top.valuePreview,
        hierarchy: hierarchy.slice(0, 8).map((info) => info.descriptor),
    };
}
"""

_CLICK_INTROSPECTION_SCRIPT = """
([x, y]) => {
    const doc = document;
    const element = doc.elementFromPoint(x, y);
    if (!element) return null;

    const toCssPath = (el) => {
        if (!el || !el.parentElement) return null;
        const segments = [];
        let node = el;
        let depth = 0;
        while (node && node.nodeType === 1 && depth < 8) {
            let selector = node.tagName ? node.tagName.toLowerCase() : "element";
            if (node.id) {
                selector += `#${node.id}`;
                segments.unshift(selector);
                break;
            }
            if (node.classList && node.classList.length) {
                selector += "." + Array.from(node.classList).slice(0, 3).join(".");
            }
            let siblingIndex = 1;
            let sibling = node.previousElementSibling;
            while (sibling) {
                if (sibling.tagName === node.tagName) siblingIndex += 1;
                sibling = sibling.previousElementSibling;
            }
            if (siblingIndex > 1) {
                selector += `:nth-of-type(${siblingIndex})`;
            }
            segments.unshift(selector);
            node = node.parentElement;
            depth += 1;
        }
        return segments.join(" > ");
    };

    const labelFor = (el) => {
        if (!el) return null;
        const ariaLabel = el.getAttribute && el.getAttribute("aria-label");
        if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim().slice(0, 120);
        const ariaLabelledBy = el.getAttribute && el.getAttribute("aria-labelledby");
        if (ariaLabelledBy) {
            const ref = ariaLabelledBy.split(" ").map((id) => id && doc.getElementById(id)).filter(Boolean).map((refEl) => refEl.innerText || refEl.textContent || "").join(" ");
            if (ref && ref.trim()) return ref.trim().slice(0, 120);
        }
        const title = el.getAttribute && el.getAttribute("title");
        if (title && title.trim()) return title.trim().slice(0, 120);
        const text = el.innerText || el.textContent || "";
        const normalized = text.replace(/\\s+/g, " ").trim();
        if (normalized) return normalized.slice(0, 120);
        return null;
    };

    const isActionable = (el) => {
        if (!el || el.nodeType !== 1) return false;
        const tag = el.tagName ? el.tagName.toLowerCase() : "";
        if (["button", "summary", "details"].includes(tag)) return true;
        if (tag === "a" && el.getAttribute("href")) return true;
        if (tag === "label") return true;
        if (tag === "input") {
            const type = (el.getAttribute("type") || "").toLowerCase();
            if (["button", "submit", "reset", "checkbox", "radio", "file"].includes(type)) return true;
        }
        const role = el.getAttribute ? el.getAttribute("role") : null;
        if (role && ["button", "link", "tab", "switch", "menuitem", "option", "checkbox"].includes(role)) return true;
        if (el.getAttribute && (el.getAttribute("onclick") || el.getAttribute("href") || el.getAttribute("for"))) return true;
        const style = window.getComputedStyle(el);
        if (style && style.cursor === "pointer") return true;
        return false;
    };

    let actionable = element;
    while (actionable && actionable !== doc.body && !isActionable(actionable)) {
        actionable = actionable.parentElement;
    }

    const summarize = (el) => {
        if (!el) return null;
        const tag = el.tagName ? el.tagName.toLowerCase() : null;
        const role = el.getAttribute ? el.getAttribute("role") : null;
        const typeAttr = el.getAttribute ? el.getAttribute("type") : null;
        return {
            tag,
            cssPath: toCssPath(el),
            label: labelFor(el),
            role: role,
            type: typeAttr,
        };
    };

    const info = {
        element: summarize(element),
        actionable: summarize(actionable || element),
        clickable: !!(actionable && actionable !== element),
    };
    const preferred = info.actionable && info.actionable.cssPath ? info.actionable : info.element;
    info.bestSelector = preferred ? preferred.cssPath : null;
    return info;
}
"""

def _frame_breadcrumb(frame) -> List[Dict[str, Optional[str]]]:
    lineage: List[Dict[str, Optional[str]]] = []
    current = frame
    while current is not None:
        name_attr = getattr(current, "name", None)
        name = name_attr() if callable(name_attr) else name_attr
        url_attr = getattr(current, "url", None)
        url = url_attr() if callable(url_attr) else url_attr
        lineage.append({"name": name or None, "url": url or None})
        parent_attr = getattr(current, "parent", None)
        current = parent_attr() if callable(parent_attr) else parent_attr
    lineage.reverse()
    return lineage


async def _describe_focused_element(page) -> Optional[Dict[str, Any]]:
    for frame in getattr(page, "frames", []):
        try:
            info = await frame.evaluate(_FOCUS_INTROSPECTION_SCRIPT)
        except Exception:
            continue
        if info:
            info["framePath"] = _frame_breadcrumb(frame)
            return info
    return None


async def _describe_click_target(page, x: float, y: float) -> Optional[Dict[str, Any]]:
    try:
        return await page.evaluate(_CLICK_INTROSPECTION_SCRIPT, (x, y))
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Teach mode endpoints
# -----------------------------------------------------------------------------


@app.post("/teach/start")
async def teach_start(payload: Dict[str, Any] = Body(default={})):
    recording_id = uuid.uuid4().hex
    teach_id, _session = await teach_manager.start(
        recording_id=recording_id, start_url=payload.get("startUrl")
    )
    try:
        stored_recording = await recording_store.start(
            title=None, recording_id=recording_id
        )
    except Exception:
        with contextlib.suppress(Exception):
            await teach_manager.stop(teach_id)
        raise
    logger.info(
        "Teach session %s started (recording=%s url=%s)",
        teach_id,
        stored_recording.recording_id,
        payload.get("startUrl"),
    )
    return {
        "teachId": teach_id,
        "recordingId": stored_recording.recording_id,
        "viewport": VIEWPORT,
        "thumbnail": None,
    }


@app.post("/teach/stop")
async def teach_stop():
    result = await teach_manager.stop()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason", "no active session"))
    recording_id = result["recordingId"]
    events = result.get("events", [])
    frames_payload = result.get("frames", [])
    markers_payload = result.get("markers", [])

    # Persist recording bundle so downstream synthesis has something to read.
    await recording_store.append_events(recording_id, events)
    frame_objects: List[RecordingFrame] = []
    for frame in frames_payload:
        try:
            frame_objects.append(
                RecordingFrame(timestamp=frame["timestamp"], png=frame["png"])
            )
        except KeyError:
            logger.debug("Skipping malformed frame payload: %s", frame)
    marker_objects: List[RecordingMarker] = []
    for marker in markers_payload:
        try:
            marker_objects.append(
                RecordingMarker(
                    timestamp=marker["timestamp"], label=marker.get("label")
                )
            )
        except KeyError:
            logger.debug("Skipping malformed marker payload: %s", marker)

    bundle = RecordingBundle(
        frames=frame_objects,
        markers=marker_objects,
        events=events,
    )
    stored = await recording_store.complete(recording_id, bundle)
    bundle_payload = stored.bundle.model_dump(by_alias=True) if stored.bundle else {}

    logger.info("Teach session %s stopped", result.get("teachId"))
    return {
        "recordingId": stored.recording_id,
        "frames": bundle_payload.get("frames", []),
        "markers": bundle_payload.get("markers", []),
        "events": stored.events,
    }


@app.websocket("/ws/teach/{teach_id}")
async def ws_teach(ws: WebSocket, teach_id: str):
    await ws.accept()
    session = await teach_manager.get(teach_id)
    if not session:
        await ws.send_json({"type": "status", "message": "No such session"})
        await ws.close()
        return

    async def pump_frames() -> None:
        try:
            while session.running:
                frame_b64 = await session.capture_frame()
                await ws.send_json(
                    {"type": "runner_frame", "frame": frame_b64, "cursor": None}
                )
                await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - best-effort streaming
            logger.debug("Teach frame pump ended: %s", exc)

    frame_task = asyncio.create_task(pump_frames())

    try:
        while True:
            message = await ws.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            msg_type = payload.get("type")
            page = session.page

            if msg_type == "mouse_move":
                await page.mouse.move(payload["x"], payload["y"])
            elif msg_type == "mouse_down":
                button = {0: "left", 1: "middle", 2: "right"}.get(
                    int(payload.get("button", 0)), "left"
                )
                await page.mouse.move(payload["x"], payload["y"])
                await page.mouse.down(button=button)
                click_meta = await _describe_click_target(page, payload["x"], payload["y"])
                event_payload: Dict[str, Any] = {
                    "x": payload["x"],
                    "y": payload["y"],
                    "button": button,
                }
                if click_meta:
                    event_payload.update(
                        {
                            "element": click_meta.get("element"),
                            "actionable": click_meta.get("actionable"),
                            "selector": click_meta.get("bestSelector"),
                            "clickable": click_meta.get("clickable"),
                        }
                    )
                session.log("click", **event_payload)
            elif msg_type == "mouse_up":
                button = {0: "left", 1: "middle", 2: "right"}.get(
                    int(payload.get("button", 0)), "left"
                )
                await page.mouse.up(button=button)
            elif msg_type == "wheel":
                await page.mouse.wheel(
                    delta_x=int(payload.get("deltaX", 0)),
                    delta_y=int(payload.get("deltaY", 0)),
                )
                session.log(
                    "scroll",
                    deltaX=int(payload.get("deltaX", 0)),
                    deltaY=int(payload.get("deltaY", 0)),
                )
            elif msg_type == "key_down":
                key = payload.get("key")
                code = payload.get("code")
                if key:
                    await page.keyboard.down(key)
                mods = [k for k in ("alt", "ctrl", "meta", "shift") if payload.get(k)]
                focus_info = await _describe_focused_element(page)
                combo_parts = [m.capitalize() for m in mods]
                if key:
                    combo_parts.append(key)
                combo = "+".join(combo_parts) if combo_parts else None
                event_payload: Dict[str, Any] = {}
                if combo:
                    event_payload["combo"] = combo
                if focus_info:
                    event_payload["selector"] = focus_info.get("selector")
                    event_payload["focus"] = focus_info
                session.record_key_down(key, code, mods, extra=event_payload)
            elif msg_type == "key_up":
                key = payload.get("key")
                if key:
                    await page.keyboard.up(key)
                focus_info = await _describe_focused_element(page)
                event_payload: Dict[str, Any] = {}
                if focus_info:
                    event_payload["selector"] = focus_info.get("selector")
                    event_payload["focus"] = focus_info
                session.record_key_up(key, extra=event_payload)

            if session.events and len(session.events) % 5 == 0:
                recent = [
                    {"ts": event.ts, "kind": event.kind, **event.data}
                    for event in session.events[-50:]
                ]
                await ws.send_json({"type": "event_log", "events": recent})
    except WebSocketDisconnect:
        logger.info("Teach websocket disconnected for %s", teach_id)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Teach websocket error for %s: %s", teach_id, exc)
    finally:
        session.running = False
        frame_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await frame_task
# -----------------------------------------------------------------------------
# Recording API models
# -----------------------------------------------------------------------------


class RecordingStartRequest(APIModel):
    title: Optional[str] = None


class RecordingStartResponse(APIModel):
    recording_id: str = Field(..., alias="recordingId")
    title: Optional[str] = None
    status: str
    created_at: datetime = Field(..., alias="createdAt")


class RecordingStopRequest(APIModel):
    frames: list[RecordingFrame]
    markers: list[RecordingMarker] = Field(default_factory=list)
    audio_wav_base64: Optional[str] = Field(default=None, alias="audioWavBase64")
    transcript: Optional[str] = None


class RecordingFrameResponse(APIModel):
    index: int
    timestamp: float
    png: str


class RecordingMarkerResponse(APIModel):
    timestamp: float
    label: Optional[str] = None


class RecordingDetailResponse(APIModel):
    recording_id: str = Field(..., alias="recordingId")
    title: Optional[str] = None
    status: str
    frames: list[RecordingFrameResponse]
    markers: list[RecordingMarkerResponse]
    audio_available: bool = Field(..., alias="audioAvailable")
    transcript: Optional[str] = None
    updated_at: datetime = Field(..., alias="updatedAt")


class EventBatch(APIModel):
    events: List[Dict[str, Any]]


# -----------------------------------------------------------------------------
# Plan synthesis API models
# -----------------------------------------------------------------------------


class PlanSynthesisResponse(APIModel):
    plan_id: str = Field(..., alias="planId")
    recording_id: str = Field(..., alias="recordingId")
    plan: Plan
    prompt: str
    raw_response: str = Field(..., alias="rawResponse")
    created_at: datetime = Field(..., alias="createdAt")


class PlanSaveRequest(APIModel):
    name: str = Field(..., min_length=1)
    plan: Optional[Plan] = None


class PlanSaveResponse(APIModel):
    plan_id: str = Field(..., alias="planId")
    name: str
    updated_at: datetime = Field(..., alias="updatedAt")
    plan: Plan


# -----------------------------------------------------------------------------
# Run orchestration models
# -----------------------------------------------------------------------------


class RunStartRequest(APIModel):
    plan_id: str = Field(..., alias="planId")
    start_url: Optional[str] = Field(default=None, alias="startUrl")


class RunStartResponse(APIModel):
    run_id: str = Field(..., alias="runId")


class RunAbortResponse(APIModel):
    run_id: str = Field(..., alias="runId")
    status: str


class RunState:
    """Tracks async run status and provides fan-out to any connected websocket clients."""

    def __init__(self, plan: StoredPlan, *, start_url: Optional[str]) -> None:
        self.run_id = uuid.uuid4().hex
        self.plan = plan
        self.start_url = start_url
        self.status = "pending"
        self.created_at = datetime.utcnow()
        self.abort_event = asyncio.Event()
        self._subscribers: set[asyncio.Queue[Dict[str, object]]] = set()
        self._lock = asyncio.Lock()
        self._latest_frame: Optional[Dict[str, object]] = None
        self._latest_status: Optional[Dict[str, object]] = None
        self._confirmation_future: Optional[asyncio.Future[bool]] = None
        self.task: Optional[asyncio.Task[None]] = None

    async def publish(self, message: Dict[str, object]) -> None:
        # Take a snapshot of subscribers and update latest pointers under the lock
        async with self._lock:
            subscribers = list(self._subscribers)
            if message.get("type") == "runner_frame":
                self._latest_frame = message
            else:
                self._latest_status = message
        # Release the lock before awaiting
        for queue in subscribers:
            await queue.put(message)

    async def add_subscriber(self) -> asyncio.Queue[Dict[str, object]]:
        queue: asyncio.Queue[Dict[str, object]] = asyncio.Queue()
        # Take snapshots of latest status/frame under the lock
        async with self._lock:
            self._subscribers.add(queue)
            latest_status = self._latest_status
            latest_frame = self._latest_frame
        if latest_status:
            await queue.put(latest_status)
        if latest_frame:
            await queue.put(latest_frame)
        return queue

    async def remove_subscriber(self, queue: asyncio.Queue[Dict[str, object]]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def request_confirmation(self, payload: Dict[str, object]) -> bool:
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        async with self._lock:
            if self._confirmation_future is not None:
                raise RuntimeError("Confirmation already pending")
            self._confirmation_future = future
        await self.publish({"type": "safety_prompt", "payload": payload})
        try:
            return await future
        finally:
            async with self._lock:
                self._confirmation_future = None

    async def resolve_confirmation(self, allowed: bool) -> None:
        async with self._lock:
            if self._confirmation_future and not self._confirmation_future.done():
                self._confirmation_future.set_result(bool(allowed))

    async def request_abort(self) -> None:
        self.abort_event.set()
        await self.publish({"type": "runner_status", "message": "abort_requested"})


class RunRegistry:
    def __init__(self) -> None:
        self._runs: Dict[str, RunState] = {}
        self._lock = asyncio.Lock()

    async def create(self, plan: StoredPlan, *, start_url: Optional[str]) -> RunState:
        state = RunState(plan, start_url=start_url)
        async with self._lock:
            self._runs[state.run_id] = state
        return state

    async def get(self, run_id: str) -> Optional[RunState]:
        async with self._lock:
            return self._runs.get(run_id)

    async def remove(self, run_id: str) -> None:
        async with self._lock:
            self._runs.pop(run_id, None)


run_registry = RunRegistry()


class RunnerDispatcher(RunnerCallbacks):
    """Bridges PlanRunner callbacks to websocket broadcasts via RunState."""

    def __init__(self, state: RunState) -> None:
        self._state = state

    async def publish_event(self, event_type: str, payload: Dict[str, object]) -> None:
        message = {"type": event_type, **payload}
        await self._state.publish(message)

    async def publish_frame(
        self,
        png_base64: str,
        *,
        step_id: Optional[str],
        cursor: Optional[Dict[str, float]],
    ) -> None:
        message: Dict[str, object] = {
            "type": "runner_frame",
            "frame": png_base64,
            "stepId": step_id,
        }
        if cursor is not None:
            message["cursor"] = cursor
        await self._state.publish(message)

    async def is_aborted(self) -> bool:
        return self._state.abort_event.is_set()

    async def request_confirmation(self, payload: Dict[str, object]) -> bool:
        return await self._state.request_confirmation(payload)


def get_frontend_path() -> Path:
    if frontend_root.exists():
        return frontend_root / "index.html"
    raise RuntimeError("frontend bundle not found")


@app.get("/")
async def serve_frontend() -> FileResponse:
    return FileResponse(get_frontend_path())


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.post("/recordings/start", response_model=RecordingStartResponse)
async def recordings_start(
    request: Optional[RecordingStartRequest] = Body(default=None),
) -> RecordingStartResponse:
    stored = await recording_store.start(request.title if request else None)
    return RecordingStartResponse(
        recording_id=stored.recording_id,
        title=stored.title,
        status=stored.status,
        created_at=stored.created_at,
    )


@app.post("/recordings/{recording_id}/keystrokes")
async def recordings_keystrokes(
    recording_id: str,
    batch: EventBatch,
) -> Dict[str, object]:
    if not await recording_store.exists(recording_id):
        raise HTTPException(status_code=404, detail="Recording not found")
    try:
        await recording_store.append_events(recording_id, batch.events)
    except KeyError as exc:  # pragma: no cover - defensive double-check
        raise HTTPException(status_code=404, detail="Recording not found") from exc
    return {"ok": True, "count": len(batch.events)}


@app.post("/recordings/{recording_id}/stop", response_model=RecordingDetailResponse)
async def recordings_stop(
    recording_id: str,
    payload: Optional[RecordingStopRequest] = Body(default=None),
) -> RecordingDetailResponse:
    try:
        await recording_store.get(recording_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recording not found") from exc
    if payload is None:
        payload = RecordingStopRequest(
            frames=[],
            markers=[],
            audio_wav_base64=None,
            transcript=None,
        )
    bundle = RecordingBundle(
        frames=payload.frames,
        markers=payload.markers,
        audio_wav_base64=payload.audio_wav_base64,
        transcript=payload.transcript,
    )
    stored = await recording_store.complete(recording_id, bundle)

    frame_responses = [
        RecordingFrameResponse(index=index, timestamp=frame.timestamp, png=frame.png)
        for index, frame in enumerate(payload.frames)
    ]
    marker_responses = [
        RecordingMarkerResponse(timestamp=marker.timestamp, label=marker.label)
        for marker in payload.markers
    ]
    return RecordingDetailResponse(
        recordingId=stored.recording_id,
        title=stored.title,
        status=stored.status,
        frames=frame_responses,
        markers=marker_responses,
        audioAvailable=payload.audio_wav_base64 is not None,
        transcript=payload.transcript,
        updatedAt=stored.updated_at,
    )


@app.get("/recordings/{recording_id}/bundle")
async def recordings_bundle(recording_id: str) -> Dict[str, object]:
    try:
        return await recording_store.get_bundle_payload(recording_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recording not found") from exc


@app.post("/plans/synthesize", response_model=PlanSynthesisResponse)
async def plans_synthesize(request: PlanSynthesisRequest) -> PlanSynthesisResponse:
    try:
        recording = await recording_store.get(request.recording_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recording not found") from exc

    if recording.bundle is None:
        raise HTTPException(status_code=400, detail="Recording has no frames yet")

    try:
        result: PlanSynthesisResult = await plan_synthesizer.synthesize(
            recording.bundle, request
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stored_plan = await plan_store.save(
        recording.recording_id,
        result.plan,
        prompt=result.prompt,
        raw_response=result.raw_response,
    )

    return PlanSynthesisResponse(
        plan_id=stored_plan.plan_id,
        recording_id=stored_plan.recording_id,
        plan=stored_plan.plan,
        prompt=result.prompt,
        raw_response=result.raw_response,
        created_at=stored_plan.created_at,
    )


async def _get_plan(plan_id: str) -> StoredPlan:
    try:
        return await plan_store.get(plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Plan not found") from exc


@app.post("/plans/{plan_id}/save", response_model=PlanSaveResponse)
async def plans_save(plan_id: str, request: PlanSaveRequest) -> PlanSaveResponse:
    stored = await plan_store.update(
        plan_id,
        name=request.name.strip(),
        plan=request.plan,
    )
    return PlanSaveResponse(
        planId=stored.plan_id,
        name=stored.plan.name,
        updatedAt=stored.updated_at,
        plan=stored.plan,
    )


@app.post("/runs/start", response_model=RunStartResponse)
async def runs_start(request: RunStartRequest) -> RunStartResponse:
    stored_plan = await _get_plan(request.plan_id)
    state = await run_registry.create(stored_plan, start_url=request.start_url)
    dispatcher = RunnerDispatcher(state)

    async def _runner_task() -> None:
        try:
            await plan_runner.run(
                stored_plan.plan,
                start_url=state.start_url,
                callbacks=dispatcher,
            )
            state.status = "completed"
            await state.publish({"type": "runner_status", "message": "completed"})
        except AbortRequested:
            state.status = "aborted"
            await state.publish({"type": "runner_status", "message": "aborted"})
        except RunnerError as exc:
            state.status = "failed"
            await state.publish(
                {"type": "runner_status", "message": "failed", "error": str(exc)}
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Run %s crashed", state.run_id)
            state.status = "failed"
            await state.publish(
                {"type": "runner_status", "message": "failed", "error": str(exc)}
            )
        finally:
            await run_registry.remove(state.run_id)

    state.task = asyncio.create_task(_runner_task(), name=f"run-{state.run_id}")
    await state.publish(
        {
            "type": "runner_status",
            "message": "started",
            "runId": state.run_id,
            "planId": stored_plan.plan_id,
        }
    )
    return RunStartResponse(run_id=state.run_id)


@app.post("/runs/{run_id}/abort", response_model=RunAbortResponse)
async def runs_abort(run_id: str) -> RunAbortResponse:
    state = await run_registry.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    await state.request_abort()
    return RunAbortResponse(run_id=state.run_id, status="aborting")


async def _websocket_sender(websocket: WebSocket, queue: asyncio.Queue[Dict[str, object]]) -> None:
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
        pass


async def _websocket_receiver(websocket: WebSocket, state: RunState) -> None:
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            if message_type == "confirm_action":
                await state.resolve_confirmation(bool(data.get("allow", False)))
            elif message_type == "abort":
                await state.request_abort()
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
        pass


@app.websocket("/ws/runs/{run_id}")
async def runs_ws(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    state = await run_registry.get(run_id)
    if not state:
        await websocket.send_json({"type": "runner_status", "message": "unknown_run"})
        await websocket.close(code=4404)
        return

    subscriber_queue = await state.add_subscriber()
    sender = asyncio.create_task(_websocket_sender(websocket, subscriber_queue))
    receiver = asyncio.create_task(_websocket_receiver(websocket, state))
    try:
        await asyncio.wait(
            {sender, receiver},
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        sender.cancel()
        receiver.cancel()
        await state.remove_subscriber(subscriber_queue)
        with contextlib.suppress(Exception):
            await websocket.close()


__all__ = ["app"]
