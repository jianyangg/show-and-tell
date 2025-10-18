from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

try:  # FastAPI may pin either Pydantic v1 or v2.
    from pydantic import ConfigDict  # type: ignore
except ImportError:  # pragma: no cover - v1 path keeps Config subclasses
    ConfigDict = None  # type: ignore

try:  # Compatibility hook for validators across Pydantic versions.
    from pydantic import model_validator  # type: ignore
except ImportError:  # pragma: no cover - Pydantic v1 path
    model_validator = None  # type: ignore

try:  # pragma: no cover - Pydantic v2 path
    from pydantic import root_validator  # type: ignore
except ImportError:
    root_validator = None  # type: ignore
VarValue = Union[str, int, float]


class _Model(BaseModel):
    if ConfigDict is not None:  # pragma: no branch - evaluated once
        model_config = ConfigDict(populate_by_name=True)  # type: ignore
    else:  # pragma: no cover - executed on Pydantic 1.x
        class Config:
            allow_population_by_field_name = True


class Word(_Model):
    w: str
    ts: float
    te: float


class DomProbe(_Model):
    role: Optional[str] = None
    name: Optional[str] = None
    label: Optional[str] = None
    test_id: Optional[str] = Field(default=None, alias="testId")
    text: Optional[str] = None
    css: Optional[str] = None


class Event(_Model):
    t: float
    type: Literal["click", "fill", "keypress", "navigate"]
    dom_probe: Optional[DomProbe] = Field(default=None, alias="domProbe")
    xy: Optional[List[float]] = None
    value: Optional[str] = None


class FramePayload(_Model):
    t: float
    png: str


class AudioPayload(_Model):
    wav_base64: Optional[str] = Field(default=None, alias="wavBase64")
    wav_path: Optional[str] = Field(default=None, alias="wavPath")


class RecordingASR(_Model):
    words: List[Word] = Field(default_factory=list)


class RecordingBundle(_Model):
    frames: List[FramePayload] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    audio: Optional[AudioPayload] = None
    asr: Optional[RecordingASR] = None


class Locator(_Model):
    strategy: Literal["role", "testid", "text", "css"]
    role: Optional[str] = None
    name: Optional[str] = None
    value: Optional[str] = None


class Assertion(_Model):
    kind: Literal["visible", "visibleText", "url", "attribute"]
    expect: str
    attribute: Optional[str] = None
    timeout_ms: Optional[int] = Field(default=None, alias="timeoutMs")
    # Optional assertion-specific target; if provided, it overrides the step target for this check
    target: Optional[Locator] = None


class Step(_Model):
    id: str
    title: str
    action: Literal["navigate", "click", "fill", "select", "press", "noop"]
    target: Optional[Locator] = None
    value: Optional[str] = None
    assertion: Assertion = Field(..., alias="assert")
    voice_snippet: Optional[str] = Field(default=None, alias="voice_snippet")
    alternatives: List[Locator] = Field(default_factory=list)


class Plan(_Model):
    name: str
    vars: Dict[str, VarValue] = Field(default_factory=dict)
    steps: List[Step]


class PlanSynthesisRequest(_Model):
    recording_id: str = Field(alias="recordingId")
    plan_name: Optional[str] = Field(default=None, alias="planName")
    include_frames: int = Field(default=8, alias="includeFrames", ge=1, le=40)
    # max_events: 0 means include all events (no cap)
    max_events: int = Field(default=0, alias="maxEvents", ge=0)


class PlanSynthesisResponse(_Model):
    plan_id: str = Field(alias="planId")
    recording_id: str = Field(alias="recordingId")
    plan: Plan
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    debug_prompt: Optional[str] = Field(default=None, alias="debugPrompt")


class PlanListResponse(_Model):
    recording_id: str = Field(alias="recordingId")
    plans: List[PlanSynthesisResponse] = Field(default_factory=list)


class RunStartRequest(_Model):
    goal: Optional[str] = None
    start_url: Optional[str] = Field(default=None, alias="startUrl")
    max_turns: int = Field(default=12, alias="maxTurns", ge=1, le=50)
    run_id: Optional[str] = Field(default=None, alias="runId")
    plan_id: Optional[str] = Field(default=None, alias="planId")

    def _ensure_goal_or_plan(self) -> "RunStartRequest":
        if not (self.goal or self.plan_id):
            raise ValueError("Either goal or planId must be provided.")
        return self

    def model_post_init(self, __context: Any) -> None:  # pragma: no cover - executed on Pydantic v2
        self._ensure_goal_or_plan()

    if root_validator is not None:  # pragma: no cover - executed on Pydantic v1

        @root_validator(skip_on_failure=True)
        def _validate_goal_or_plan(cls, values: Dict[str, object]) -> Dict[str, object]:
            goal = values.get("goal")
            plan_id = values.get("plan_id")
            if not (goal or plan_id):
                raise ValueError("Either goal or planId must be provided.")
            return values


class RunStartResponse(_Model):
    run_id: str = Field(alias="runId")


class RecordingStartRequest(_Model):
    title: Optional[str] = None


class RecordingStartResponse(_Model):
    recording_id: str = Field(alias="recordingId")
    title: Optional[str] = None
    status: Literal["started", "completed"]
    created_at: datetime = Field(alias="createdAt")


class RecordingFrameInfo(_Model):
    frame_id: str = Field(alias="frameId")
    timestamp: float
    png_url: str = Field(alias="pngUrl")


class RecordingAudioInfo(_Model):
    wav_url: str = Field(alias="wavUrl")


class RecordingDetailResponse(_Model):
    recording_id: str = Field(alias="recordingId")
    title: Optional[str] = None
    status: Literal["started", "completed"]
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    frames: List[RecordingFrameInfo] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    asr: Optional[RecordingASR] = None
    audio: Optional[RecordingAudioInfo] = None


class RunHistoryItem(_Model):
    run_id: str = Field(alias="runId")
    goal: str
    start_url: Optional[str] = Field(default=None, alias="startUrl")
    max_turns: int = Field(alias="maxTurns")
    status: Literal["pending", "running", "completed", "failed", "aborted"]
    reason: Optional[str] = None
    created_at: datetime = Field(alias="createdAt")
    completed_at: Optional[datetime] = Field(default=None, alias="completedAt")


class RunHistoryResponse(_Model):
    runs: List[RunHistoryItem] = Field(default_factory=list)
