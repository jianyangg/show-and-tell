from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field

try:  # pragma: no cover - compatibility shim for Pydantic v1
    from pydantic import ConfigDict  # type: ignore
except ImportError:  # pragma: no cover
    ConfigDict = None  # type: ignore


logger = logging.getLogger(__name__)

# Optional persistence for visual checkpoints (guarded import)
try:
    from .storage import save_visual_checkpoints_for_recording  # type: ignore
except Exception:  # pragma: no cover

    def save_visual_checkpoints_for_recording(
        recording_id: str, mapping: Dict[str, List[Dict[str, Any]]]
    ) -> None:
        """
        No-op fallback when storage layer isn't available.
        Expected mapping schema:
          { step_id: [ { "png_base64": str, "label": Optional[str] }, ... ] }
        """
        return


DEFAULT_PLAN_MODEL = "gemini-2.5-pro"
PLAN_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "startUrl": {"type": ["string", "null"], "default": None},
        "vars": {
            "type": "object",
            "default": {},
            "additionalProperties": {"type": ["string", "number"]},
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "title", "instructions"],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "instructions": {"type": "string"},
                },
            },
        },
    },
    "required": ["name", "startUrl", "vars", "steps"],
}

# OpenAI strict schema for plan synthesis (string-only, stricter requirements)
OPENAI_PLAN_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        # OpenAI's strict schema prefers simple types; use empty string when unknown
        "startUrl": {"type": "string"},
        # Simplify to a string-only map for broad compatibility
        "vars": {
            "type": "object",
            "additionalProperties": {"type": "string"}
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "instructions": {"type": "string"}
                },
                "required": ["id", "title", "instructions"]
            }
        }
    },
    # For strict mode, required must include every property key
    # Note: "vars" is optional since it can be an empty object
    "required": ["name", "startUrl", "steps"]
}

VarValue = Union[str, int, float]


class _BaseModel(BaseModel):
    """Populate-by-name works on both Pydantic v1 and v2."""

    if ConfigDict is not None:  # pragma: no branch - resolved at import time
        model_config = ConfigDict(populate_by_name=True)  # type: ignore
    else:  # pragma: no cover - v1 fallback

        class Config:
            allow_population_by_field_name = True


class RecordingFrame(_BaseModel):
    timestamp: float = Field(..., alias="timestamp")
    png: str


class RecordingMarker(_BaseModel):
    timestamp: float = Field(..., alias="timestamp")
    label: Optional[str] = None


class RecordingBundle(_BaseModel):
    frames: List[RecordingFrame] = Field(default_factory=list)
    markers: List[RecordingMarker] = Field(default_factory=list)
    audio_wav_base64: Optional[str] = Field(default=None, alias="audioWavBase64")
    transcript: Optional[str] = None
    events: List[Dict[str, Any]] = Field(default_factory=list)


class PlanStep(_BaseModel):
    id: str
    title: str
    instructions: str


class Plan(_BaseModel):
    name: str
    vars: Dict[str, VarValue] = Field(default_factory=dict)
    steps: List[PlanStep]
    start_url: Optional[str] = Field(default=None, alias="startUrl")
    has_variables: bool = Field(default=False, alias="hasVariables")


class PlanSynthesisRequest(_BaseModel):
    recording_id: str = Field(..., alias="recordingId")
    plan_name: Optional[str] = Field(default=None, alias="planName")
    start_url: Optional[str] = Field(default=None, alias="startUrl")
    provider: Optional[str] = None
    variable_hints: Optional[str] = Field(default=None, alias="variableHints")

_PLACEHOLDER_PATTERN = re.compile(
    r"""
    \{\{\s*(?P<double>[^{}\s][^{}]*)\s*\}\}
    |
    \{(?P<single>[^{}]+)\}
    """,
    re.VERBOSE,
)


def _extract_placeholder(match: re.Match[str]) -> Optional[str]:
    raw = match.group("double") or match.group("single")
    if raw is None:
        return None
    candidate = raw.strip()
    return candidate or None


def collect_plan_placeholders(plan: Plan) -> Set[str]:
    placeholders: Set[str] = set()

    def scan(text: Optional[str]) -> None:
        if not text:
            return
        for match in _PLACEHOLDER_PATTERN.finditer(text):
            key = _extract_placeholder(match)
            if key:
                placeholders.add(key)

    scan(plan.name)
    for step in plan.steps:
        scan(step.title)
        scan(step.instructions)
    return placeholders


def _plan_model_copy(plan: Plan, **updates: Any) -> Plan:
    try:
        return plan.model_copy(update=updates)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - Pydantic v1 fallback
        return plan.copy(update=updates)  # type: ignore[call-arg]


def copy_plan_with_vars(plan: Plan, vars_map: Dict[str, VarValue]) -> Plan:
    return _plan_model_copy(plan, vars=dict(vars_map))


def normalize_plan_variables(plan: Plan) -> tuple[Plan, Set[str]]:
    placeholders = collect_plan_placeholders(plan)
    merged_vars = dict(plan.vars)
    vars_changed = False
    for name in placeholders:
        if name not in merged_vars:
            merged_vars[name] = ""
            vars_changed = True
    updates: Dict[str, Any] = {}
    if vars_changed:
        updates["vars"] = merged_vars
    has_variables = bool(placeholders)
    if plan.has_variables != has_variables:
        updates["has_variables"] = has_variables
    if updates:
        plan = _plan_model_copy(plan, **updates)
    return plan, placeholders


def apply_plan_variables(value: Optional[str], vars_map: Dict[str, VarValue]) -> Optional[str]:
    if value is None:
        return None

    def repl(match: re.Match[str]) -> str:
        key = _extract_placeholder(match)
        if key and key in vars_map:
            return str(vars_map[key])
        return match.group(0)

    return _PLACEHOLDER_PATTERN.sub(repl, value)


@dataclass
class PlanSynthesisResult:
    plan: Plan
    prompt: str
    raw_response: str
    has_variables: bool = False
    checkpoints: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


class PlanSynthesizer:
    """Produces plan steps using either Gemini 2.5 Pro or ChatGPT 5."""

    SUPPORTED_PROVIDERS = {"gemini", "chatgpt"}

    def __init__(self) -> None:
        self._enabled = os.environ.get("PLAN_SYNTH_ENABLED") == "1"
        self._default_provider = os.environ.get("PLAN_SYNTH_PROVIDER", "gemini").lower()
        self._debug = os.environ.get("PLAN_SYNTH_DEBUG") == "1"

        self._gemini_client = None
        self._gemini_types = None
        self._gemini_config = None
        self._gemini_model_id = os.environ.get("PLAN_MODEL_ID", DEFAULT_PLAN_MODEL)

        self._openai_client = None
        self._openai_model_id = os.environ.get("PLAN_MODEL_ID_CHATGPT", "gpt-5")

        if not self._enabled:
            logger.info("Plan synthesizer disabled (PLAN_SYNTH_ENABLED != 1).")
            return

        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            from google import genai  # Imported lazily to keep the module import cheap.
            from google.genai import types

            self._gemini_client = genai.Client(api_key=gemini_key)
            self._gemini_config = types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                max_output_tokens=8_192,
            )
            self._gemini_types = types
        else:
            logger.info(
                "Gemini plan synthesizer not configured (missing GEMINI_API_KEY)."
            )

        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            from openai import (
                OpenAI,
            )  # Imported lazily to avoid hard dependency when unused.

            self._openai_client = OpenAI(api_key=openai_key)
        else:
            logger.info(
                "ChatGPT plan synthesizer not configured (missing OPENAI_API_KEY)."
            )

    async def synthesize(
        self,
        recording: RecordingBundle,
        request: PlanSynthesisRequest,
    ) -> PlanSynthesisResult:
        if not self._enabled:
            raise RuntimeError("Plan synthesizer is disabled")

        # Attempt to transcribe audio if present (before building prompt)
        # This populates recording.transcript which is then included in the prompt
        await self._transcribe_audio_if_present(recording)

        provider = self._resolve_provider(request.provider)
        prompt = self._build_prompt(
            recording, request.plan_name, request.start_url, request.variable_hints
        )

        if provider == "gemini":
            plan_payload, raw_response = await self._synthesize_with_gemini(
                prompt, recording
            )
        else:
            plan_payload, raw_response = await self._synthesize_with_chatgpt(
                prompt, recording
            )

        plan = Plan.model_validate(plan_payload)
        start_url = (request.start_url or "").strip() or None
        if start_url or plan.start_url:
            target_start_url = start_url or plan.start_url
            if target_start_url != plan.start_url:
                plan = _plan_model_copy(plan, start_url=target_start_url)
        plan, placeholders = normalize_plan_variables(plan)
        has_variables = bool(placeholders)
        # Derive and persist visual checkpoints so the runner can gate completion on them
        try:
            cp_map = self._derive_step_checkpoints(recording, plan)
            self._persist_step_checkpoints(request.recording_id, cp_map)
        except Exception:
            logger.exception(
                "Checkpoint derivation/persistence failed for recording_id=%s",
                request.recording_id,
            )
        return PlanSynthesisResult(
            plan=plan,
            prompt=prompt,
            raw_response=raw_response,
            has_variables=has_variables,
            checkpoints=cp_map if "cp_map" in locals() else {},
        )

    def _resolve_provider(self, requested: Optional[str]) -> str:
        provider = (requested or self._default_provider or "gemini").lower()
        if provider not in self.SUPPORTED_PROVIDERS:
            raise RuntimeError(f"Unsupported plan synthesizer provider '{provider}'")
        if provider == "gemini":
            if not (self._gemini_client and self._gemini_config and self._gemini_types):
                raise RuntimeError("Gemini plan synthesizer is disabled")
        else:
            if not self._openai_client:
                raise RuntimeError("ChatGPT plan synthesizer is disabled")
        return provider

    async def _transcribe_audio_if_present(self, recording: RecordingBundle) -> None:
        """
        Transcribe audio if available and populate recording.transcript.

        This method is called before building the synthesis prompt to ensure
        the transcript is available for inclusion. Failures are logged but
        don't stop synthesis (graceful degradation).

        Args:
            recording: RecordingBundle that may contain audio_wav_base64.
                      Its transcript field will be populated if transcription succeeds.
        """
        # Skip if no audio or transcript already exists
        if not recording.audio_wav_base64:
            logger.debug("No audio data in recording, skipping transcription")
            return

        if recording.transcript and recording.transcript.strip():
            logger.debug("Transcript already exists, skipping transcription")
            return

        try:
            # Import transcription service (lazy import to avoid hard dependency)
            from .transcription import get_transcription_service

            service = get_transcription_service()

            if not service.enabled:
                logger.debug("Transcription service disabled, skipping")
                return

            logger.info("Starting audio transcription...")
            result = await service.transcribe(recording.audio_wav_base64)

            if result:
                # Format transcript for prompt inclusion
                formatted = service.format_for_prompt(result)
                if formatted:
                    recording.transcript = formatted
                    logger.info(
                        "Transcription completed: %d words in %d chunks",
                        len(result.words),
                        len(result.chunks)
                    )
                    # Log the actual transcript for debugging
                    logger.info("Transcript preview:\n%s", formatted[:500] + ("..." if len(formatted) > 500 else ""))
                else:
                    logger.warning("Transcription returned empty result")
            else:
                logger.warning("Transcription failed, continuing without transcript")

        except Exception as exc:
            # Graceful degradation: log error but don't raise
            # Plan synthesis should work even without transcript
            logger.error(
                "Audio transcription failed: %s. Continuing without transcript.",
                exc,
                exc_info=True
            )

    async def _synthesize_with_gemini(
        self,
        prompt: str,
        recording: RecordingBundle,
    ) -> tuple[Dict[str, Any], str]:
        assert self._gemini_client and self._gemini_types and self._gemini_config
        parts = [self._gemini_types.Part(text=prompt)]

        for index, frame in enumerate(
            self._downsample_frames(recording.frames, limit=8)
        ):
            try:
                png_bytes = base64.b64decode(frame.png.encode("ascii"))
            except ValueError:
                logger.warning("Skipping malformed PNG for frame index %d", index)
                continue
            parts.append(
                self._gemini_types.Part(
                    text=f"frame_index={index}, timestamp={frame.timestamp:.2f}s"
                )
            )
            parts.append(
                self._gemini_types.Part.from_bytes(
                    data=png_bytes, mime_type="image/png"
                )
            )

        response = await asyncio.to_thread(
            self._gemini_client.models.generate_content,
            model=self._gemini_model_id,
            contents=[self._gemini_types.Content(role="user", parts=parts)],
            config=self._gemini_config,
        )

        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates")

        candidate = response.candidates[0]
        plan_json = self._extract_candidate_text(candidate)
        plan_payload = self._parse_payload(plan_json)
        return plan_payload, plan_json

    async def _synthesize_with_chatgpt(
        self,
        prompt: str,
        recording: RecordingBundle,
    ) -> tuple[Dict[str, Any], str]:
        assert self._openai_client is not None

        system_prompt = (
            "You are building an automation plan for a web browser agent. "
            "Follow the provided schema exactly."
        )

        # Build multimodal content (favor 'input_text'; fall back to 'text' if the API complains)
        user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for index, frame in enumerate(
            self._downsample_frames(recording.frames, limit=6)
        ):
            user_content.append(
                {
                    "type": "input_text",
                    "text": f"frame_index={index}, timestamp={frame.timestamp:.2f}s",
                }
            )
            user_content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{frame.png}",
                }
            )

        input_payload = [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {"role": "user", "content": user_content},
        ]

        response = await asyncio.to_thread(
            self._openai_client.responses.create,
            model=self._openai_model_id,
            input=input_payload,
            reasoning={"effort": "medium", "summary": "auto"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "plan_schema",
                    "schema": OPENAI_PLAN_JSON_SCHEMA,
                    "strict": True,
                },
                "verbosity": "medium",
            },
            tools=[],
            include=[
                "reasoning.encrypted_content",
                "web_search_call.action.sources",
            ],
            store=True,
        )

        plan_payload, raw_response = self._extract_openai_payload(response)
        return plan_payload, raw_response

    def _format_locator(self, ev: Dict[str, Any]) -> str:
        """Format a compact, human-readable locator from event payload."""
        pl = ev.get("primaryLocator")
        if not pl and isinstance(ev.get("focus"), dict):
            pl = ev["focus"].get("primaryLocator")
        if isinstance(pl, dict):
            if pl.get("by") == "role" and pl.get("role") and pl.get("name"):
                return f'[role={pl["role"]}] name="{str(pl["name"])[:80]}"'
            if pl.get("by") == "css" and pl.get("value"):
                return str(pl["value"])
        # Fallbacks
        sel = ev.get("selector")
        if sel:
            return str(sel)
        target = ev.get("actionable") or ev.get("element") or ev.get("focus")
        if isinstance(target, dict):
            tag = str(target.get("tag") or "element").lower()
            nameish = target.get("name") or target.get("label") or ""
            css = target.get("cssPath") or target.get("selector")
            text = f' "{str(nameish)[:80]}"' if nameish else ""
            if css:
                return f"{tag}{text} {css}"
            return f"{tag}{text}".strip()
        return ""

    def _build_interaction_cues(self, events: List[Dict[str, Any]]) -> List[str]:
        """Turn raw recorded events into timeline cue strings with semantic targets."""
        cues: List[str] = []
        for e in events or []:
            try:
                ts = float(e.get("ts", 0.0))
            except Exception:
                ts = 0.0
            t = f"{ts:.3f}s"
            kind = str(e.get("kind") or "")
            loc = self._format_locator(e)
            if kind == "click":
                btn = e.get("button", "left")
                cues.append(f"{t} click → {btn}{(' on ' + loc) if loc else ''}")
            elif kind == "drag":
                # Drag events contain start and end coordinates, essential for drawing/positioning actions
                # Format: "ts drag → (start_x,start_y) to (end_x,end_y) [duration] [on element]"
                start_x = e.get("start_x", 0)
                start_y = e.get("start_y", 0)
                end_x = e.get("end_x", 0)
                end_y = e.get("end_y", 0)
                duration = float(e.get("duration") or 0.0)
                btn = e.get("button", "left")
                # Calculate drag distance for context
                distance = ((end_x - start_x) ** 2 + (end_y - start_y) ** 2) ** 0.5
                # Format end element locator if available
                end_loc = ""
                if e.get("end_primaryLocator") or e.get("end_selector"):
                    end_loc = self._format_locator(
                        {
                            "primaryLocator": e.get("end_primaryLocator"),
                            "selector": e.get("end_selector"),
                            "element": e.get("end_element"),
                        }
                    )
                detail_parts = [
                    f"({start_x:.0f},{start_y:.0f}) → ({end_x:.0f},{end_y:.0f})",
                    f"distance={distance:.0f}px",
                    f"{duration:.2f}s",
                ]
                if end_loc:
                    detail_parts.append(f"to {end_loc}")
                cues.append(f"{t} drag → {btn} {' '.join(detail_parts)}")
            elif kind == "dom_probe":
                cues.append(f"{t} probe → {loc or 'target'}")
            elif kind == "scroll":
                dx = int(e.get("deltaX") or 0)
                dy = int(e.get("deltaY") or 0)
                cues.append(f"{t} scroll → Δx={dx}, Δy={dy}")
            elif kind == "key_down":
                combo = e.get("combo") or e.get("key") or ""
                focus_loc = self._format_locator(
                    {"focus": e.get("focus"), "selector": e.get("selector")}
                )
                cues.append(
                    f"{t} key_down → {combo}{(' into ' + focus_loc) if focus_loc else ''}"
                )
            elif kind == "key_up":
                key = e.get("key") or ""
                focus_loc = self._format_locator(
                    {"focus": e.get("focus"), "selector": e.get("selector")}
                )
                cues.append(
                    f"{t} key_up → {key}{(' on ' + focus_loc) if focus_loc else ''}"
                )
            elif kind == "key_hold":
                # Extract the key/combo and duration to show what character was held and for how long
                # This is critical for understanding typing patterns and repeated characters
                key = e.get("key")
                combo = e.get("combo")
                duration = float(e.get("duration") or 0.0)
                detail = combo or key or "key"
                focus_loc = self._format_locator(
                    {"focus": e.get("focus"), "selector": e.get("selector")}
                )
                cues.append(
                    f"{t} key_hold → {detail} for {duration:.2f}s{(' on ' + focus_loc) if focus_loc else ''}"
                )
            else:
                cues.append(f"{t} {kind}")
        return cues

    def _candidate_strings(self, ev: Dict[str, Any]) -> List[str]:
        """Collect locator candidates from an event, deduped and ordered by robustness."""
        out: List[str] = []
        seen: set[str] = set()

        def push(s: Optional[str]) -> None:
            if not s:
                return
            if s in seen:
                return
            seen.add(s)
            out.append(s)

        # 1) Primary locator first
        pl = ev.get("primaryLocator")
        if not pl and isinstance(ev.get("focus"), dict):
            pl = ev["focus"].get("primaryLocator")
        if isinstance(pl, dict):
            if pl.get("by") == "role" and pl.get("role") and pl.get("name"):
                push(f'role({pl["role"]},"{str(pl["name"])[:80]}")')
            if pl.get("by") == "css" and pl.get("value"):
                push(str(pl["value"]))

        # 2) Other selector candidates
        for c in ev.get("selectorCandidates") or []:
            if not isinstance(c, dict):
                continue
            if c.get("by") == "css" and c.get("value"):
                push(str(c["value"]))
            elif c.get("by") == "role" and c.get("role") and c.get("name"):
                push(f'role({c["role"]},"{str(c["name"])[:80]}")')

        # 3) Actionable/element fallbacks: id, name, cssPath
        target = ev.get("actionable") or ev.get("element") or ev.get("focus")
        if isinstance(target, dict):
            tid = target.get("id")
            if tid:
                push(f"#{tid}")
            tname = target.get("name") or target.get("label")
            ttag = (target.get("tag") or "").lower()
            if ttag in {"input", "select", "textarea"} and tname:
                push(f'{ttag}[name="{str(tname)[:80]}"]')
            css = target.get("cssPath") or target.get("selector")
            if css:
                push(str(css))

        # 4) Legacy single selector if present
        if ev.get("selector"):
            push(str(ev["selector"]))

        return out[:6]

    def _collect_dom_context(
        self, events: List[Dict[str, Any]], *, limit: int = 16
    ) -> List[str]:
        """
        Return deduped bullets summarizing observed actionable elements with general DOM info.
        Each line favors role+name, test IDs, then CSS fallbacks.
        """
        bullets: List[str] = []
        seen_keys: set[str] = set()

        def key_for(ev: Dict[str, Any]) -> Optional[str]:
            pl = ev.get("primaryLocator")
            if not pl and isinstance(ev.get("focus"), dict):
                pl = ev["focus"].get("primaryLocator")
            if (
                isinstance(pl, dict)
                and pl.get("by") == "role"
                and pl.get("role")
                and pl.get("name")
            ):
                return f'role::{pl["role"]}::{str(pl["name"]).strip()}'
            if isinstance(pl, dict) and pl.get("by") == "css" and pl.get("value"):
                return f'css::{str(pl["value"])}'
            sel = ev.get("selector")
            if sel:
                return f"css::{str(sel)}"
            tgt = ev.get("actionable") or ev.get("element")
            if isinstance(tgt, dict):
                nameish = tgt.get("name") or tgt.get("label") or ""
                tag = (tgt.get("tag") or "").lower()
                cssp = tgt.get("cssPath") or ""
                return f"{tag}::{nameish}::{cssp}"
            return None

        for e in events or []:
            # Collect DOM context from all interactive events including drag operations
            if e.get("kind") not in {"click", "drag", "dom_probe", "key_down", "key_up"}:
                continue
            k = key_for(e)
            if not k or k in seen_keys:
                continue
            seen_keys.add(k)

            # Human-facing header
            tgt = e.get("actionable") or e.get("element") or e.get("focus") or {}
            tag = (
                (tgt.get("tag") or "element").lower()
                if isinstance(tgt, dict)
                else "element"
            )
            role = (tgt.get("role") or "").lower() if isinstance(tgt, dict) else ""
            nameish = ""
            if isinstance(tgt, dict):
                nameish = (
                    tgt.get("name") or tgt.get("label") or tgt.get("ariaLabel") or ""
                )
            header = f"{tag}"
            if role:
                header += f" [role={role}]"
            if nameish:
                header += f' name="{str(nameish)[:80]}"'

            # Candidates list
            cands = self._candidate_strings(e)
            if cands:
                bullets.append(f"- {header} | candidates: " + ", ".join(cands))
            else:
                css = (
                    (tgt.get("cssPath") if isinstance(tgt, dict) else None)
                    or e.get("selector")
                    or ""
                )
                bullets.append(f"- {header}{(' | css: ' + css) if css else ''}")

            if len(bullets) >= limit:
                break

        return bullets

    def _build_prompt(
        self,
        recording: RecordingBundle,
        plan_name: Optional[str],
        start_url: Optional[str],
        variable_hints: Optional[str] = None,
    ) -> str:
        markers = sorted(recording.markers, key=lambda marker: marker.timestamp)
        marker_lines = [
            f"- t={marker.timestamp:.2f}s :: {marker.label or 'Marked step'}"
            for marker in markers
        ]
        timeline_lines = self._summarize_events(recording.events, limit=2_000)
        normalized_start_url = (start_url or "").strip()

        prompt_lines = [
            "You are building an automation plan for Gemini Computer Use.",
            "Your goal is to create GOAL-ORIENTED, FLEXIBLE instructions that focus on the intended outcome rather than rigid step-by-step actions.",
            "",
            "Return strict JSON following this schema:",
            json.dumps(
                {
                    "name": plan_name or "recorded run",
                    "startUrl": normalized_start_url or "",
                    "vars": {"example": ""},
                    "steps": [
                        {
                            "id": "s1",
                            "title": "Human readable summary of what happens",
                            "instructions": "Natural language guidance for the Computer Use agent (full sentences).",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            "",
            "CRITICAL: The 'name' field is the OVERALL GOAL of this automation.",
            "- Analyze the recording and infer what the user is trying to accomplish",
            "- Write a descriptive name that captures the intent (e.g., 'Draw hi on tldraw', 'Search for flights to Paris', 'Create new document')",
            "- This name will be shown to the user and to the AI agent as the overall goal",
            "- DO NOT use generic names like 'Captured flow' or 'recorded run'",
            "- Keep it concise (≤ 60 chars) but meaningful",
            "",
            "CRITICAL INSTRUCTION STYLE:",
            "- Focus on WHAT needs to be achieved, not HOW to click specific elements",
            "- Write instructions that describe the desired outcome or goal of each step",
            '- Example: Instead of "Click the pen icon in the third button", write "Select the pen/draw tool from the toolbar"',
            '- Example: Instead of "Click at coordinates and drag", write "Draw the desired shape or text on the canvas"',
            "- Let the Computer Use agent figure out the specific UI interactions",
            "- Instructions should work even if the UI layout changes slightly",
            "",
            "NAVIGATION RULES:",
            "- The startUrl will be loaded AUTOMATICALLY before any steps execute",
            "- DO NOT include navigation instructions in the first step (e.g., 'Open [site]', 'Navigate to [url]')",
            "- The user is ALREADY on the startUrl when step 1 begins",
            "- Start directly with the first meaningful action (e.g., 'Select the pen tool', not 'Open tldraw and select...')",
            "",
            "Rules:",
            "- Use deterministic step IDs 's1', 's2', ... in chronological order.",
            "- Align step boundaries to the provided markers (1:1 in order) when markers exist.",
            "- Keep step IDs stable and human-readable titles short (≤ 80 chars).",
            "- Infer the USER'S INTENT from the interaction timeline and create instructions that express that intent.",
            "- If the user draws something, the instruction should be 'Draw [description]', not 'Click and drag'.",
            "- If the user types text, the instruction should be 'Enter [text] into [field]', not 'Click text box then type'.",
            "- Provide GOAL-ORIENTED instructions that reference what needs to happen, not rigid click sequences.",
            '- When referencing UI elements, quote the visible label or role when available (e.g., "press the \'Search\' button", "open the \'Settings\' menu") and avoid low-level selectors.',
            "- Explicitly call out key presses the user performed (e.g., pressing Enter or shortcuts) so the agent knows to repeat them.",
            "- Whenever you mention text the user typed that should remain flexible (like names, emails, greetings), replace the literal with a variable placeholder {variableName} and record that variable in vars.",
            "- Apply the same placeholder rule to the overall plan name and each step title/instruction; never hard-code sample values if a variable exists.",
            "- Avoid raw x,y coordinates completely unless absolutely necessary for drawing/positioning.",
            '- Always include the top-level startUrl as a string; use an empty string ("") if unknown.',
            "- When you reference a plan variable use the {var} notation and register it under vars.",
            '- All entries in vars must be strings (coerce numbers to strings).',
            "- Prefer concise, outcome-focused steps. Each step should describe a meaningful action or goal.",
            "- Write instructions that are resilient to minor UI changes.",
            "",
            "=== GEMINI COMPUTER USE ACTIONS (CRITICAL) ===",
            "The agent executing this plan has access to the following Computer Use actions.",
            "Your step instructions MUST reference these actions when describing what needs to be done:",
            "",
            "NAVIGATION:",
            '  • navigate(url) - Go directly to a URL: "Navigate to https://example.com"',
            '  • open_web_browser() - Open browser: "Open the web browser"',
            '  • go_back() / go_forward() - Browser navigation: "Go back to the previous page"',
            '  • search() - Open search engine: "Open Google search"',
            "",
            "INTERACTION:",
            '  • click_at(x, y) - Click at coordinates: "Click the submit button"',
            '  • hover_at(x, y) - Hover for menus: "Hover over the File menu to reveal options"',
            '  • type_text_at(x, y, text, press_enter, clear_before_typing) - Type text: "Type \'{searchTerm}\' into the search box and press Enter"',
            '  • key_combination(keys) - Press keyboard shortcuts: "Press Control+A to select all" or "Press Enter to submit"',
            "",
            "SCROLLING:",
            '  • scroll_document(direction) - Scroll the page: "Scroll down to see more results"',
            '  • scroll_at(x, y, direction, magnitude) - Scroll specific element: "Scroll down within the chat window"',
            "",
            "DRAG AND DRAW:",
            '  • drag_and_drop(x, y, destination_x, destination_y) - Drag from one point to another',
            '    - Use for DRAWING: "Draw a line/shape on the canvas" (maps to drag motion)',
            '    - Use for REPOSITIONING: "Drag the slider to adjust volume"',
            '    - Use for DRAG-DROP: "Drag the file to the upload area"',
            "",
            "TIMING:",
            '  • wait_5_seconds() - Wait for content to load: "Wait for the page to finish loading"',
            "",
            "INSTRUCTION MAPPING EXAMPLES (how recorded events → step instructions):",
            '  Recorded: "7.5s drag → left (200,300) → (450,320) distance=250px"',
            '  Instruction: "Draw a horizontal line on the canvas using the pen tool"',
            '  → Agent will use: drag_and_drop(x=200, y=300, destination_x=450, destination_y=320)',
            "",
            '  Recorded: "3.2s click → left on button[aria-label=\'Submit\']"',
            '  Instruction: "Click the Submit button to send the form"',
            '  → Agent will use: click_at(x, y) based on button location',
            "",
            '  Recorded: "5.1s key_hold → h for 0.06s on input[type=\'text\']"',
            '           "5.2s key_hold → i for 0.05s on input[type=\'text\']"',
            '  Instruction: "Type \'{greeting}\' into the text input field"',
            '  → Agent will use: type_text_at(x, y, text="{greeting}", press_enter=false)',
            "",
            '  Recorded: "2.8s scroll → Δx=0, Δy=450"',
            '  Instruction: "Scroll down the page to view more content"',
            '  → Agent will use: scroll_document(direction="down")',
            "",
            "CRITICAL DRAG INSTRUCTION RULES:",
            "- When you see DRAG events in the timeline, analyze the context:",
            '  • If on a DRAWING canvas (tldraw, whiteboard, etc.) → "Draw [shape/text] on the canvas"',
            '  • If moving a UI element (slider, resize handle) → "Adjust the [element] by dragging"',
            '  • If dragging between containers → "Drag the [item] to [destination]"',
            "- The agent will automatically use drag_and_drop() with the appropriate coordinates",
            "- DO NOT write rigid instructions like \"Drag from (100,200) to (500,600)\"",
            '- INSTEAD write intent: "Draw the letter \'h\' on the canvas" or "Slide the volume control to maximum"',
            "",
            'Write instructions in natural language that express INTENT and reference the actions above.',
            'The Computer Use agent will map your instructions to the appropriate action based on context.',
        ]

        normalized_start_url = (start_url or "").strip()
        if normalized_start_url:
            prompt_lines.append(
                f"Initial start URL (load this page before following the steps): {normalized_start_url}"
            )

        # Include user's variable hints if provided
        if variable_hints and variable_hints.strip():
            prompt_lines.append("")
            prompt_lines.append("IMPORTANT: User-provided instructions for variable creation:")
            prompt_lines.append(variable_hints.strip())
            prompt_lines.append(
                "Follow these instructions carefully when deciding which values to parameterize. "
                "Identify the relevant values from the recording and create appropriately named variables."
            )
            prompt_lines.append("")

        if marker_lines:
            prompt_lines.append("Markers collected during teaching:")
            prompt_lines.extend(marker_lines)
            prompt_lines.append(
                "Create one step per marker in the same order when possible."
            )

        timeline_lines = self._summarize_events(
            recording.events, limit=2_000
        )  # legacy fallback

        # Prefer enriched cues built from recorded events (role/name/selector), fall back to legacy summary
        try:
            interaction_lines = self._build_interaction_cues(recording.events or [])
        except Exception:
            interaction_lines = []

        lines_to_use = interaction_lines or timeline_lines
        if lines_to_use:
            prompt_lines.append("")
            prompt_lines.append("Interaction timeline (chronological, already normalized into high-level cues):")
            prompt_lines.append("")
            prompt_lines.append("IMPORTANT: Analyze these interactions to INFER THE USER'S GOAL.")
            prompt_lines.append("Ask yourself:")
            prompt_lines.append("- What is the user trying to accomplish?")
            prompt_lines.append("- What tool/feature are they trying to use?")
            prompt_lines.append("- What content are they creating or modifying?")
            prompt_lines.append("- What is the end result they want?")
            prompt_lines.append("")
            prompt_lines.append("Then write instructions that express that goal, not the mechanical steps.")
            prompt_lines.append("")
            prompt_lines.append("MAP INTERACTIONS TO COMPUTER USE ACTIONS:")
            prompt_lines.append('• If you see DRAG events → Use drag_and_drop() action:')
            prompt_lines.append('  - Drawing context: "Draw [description] on the canvas"')
            prompt_lines.append('  - UI manipulation: "Adjust the [slider/control] by dragging"')
            prompt_lines.append('• If you see CLICK events → Use click_at() action:')
            prompt_lines.append('  - "Click the [button/link] to [action]"')
            prompt_lines.append('• If you see KEY_HOLD events (typing) → Use type_text_at() action:')
            prompt_lines.append('  - "Type \'{variableName}\' into the [field]"')
            prompt_lines.append('• If you see SCROLL events → Use scroll_document() or scroll_at() action:')
            prompt_lines.append('  - "Scroll down to view more content"')
            prompt_lines.append("")
            prompt_lines.extend(lines_to_use)

        # Add a compact DOM context snapshot so the model can reference robust locators
        try:
            dom_bullets = self._collect_dom_context(recording.events or [], limit=16)
        except Exception:
            dom_bullets = []
        if dom_bullets:
            prompt_lines.append(
                "Observed UI elements (deduped; prefer these locators in instructions):"
            )
            prompt_lines.extend(dom_bullets)

        if recording.transcript:
            prompt_lines.append("")
            prompt_lines.append("USER NARRATION (voice-over recorded during the session):")
            prompt_lines.append("")
            prompt_lines.append("The user narrated their actions while recording. Use this to understand:")
            prompt_lines.append("- The INTENT behind each action (what they're trying to accomplish)")
            prompt_lines.append("- Variable names they mention verbally (e.g., 'username', 'password', 'search term')")
            prompt_lines.append("- Business logic and reasoning for the workflow")
            prompt_lines.append("- Context for ambiguous UI interactions")
            prompt_lines.append("- Correlate timestamps with interaction timeline to see what was said during each action")
            prompt_lines.append("")
            prompt_lines.append(recording.transcript.strip())
            prompt_lines.append("")

        prompt_lines.append("")
        prompt_lines.append("FINAL REMINDERS:")
        prompt_lines.append("1. Set a DESCRIPTIVE 'name' that captures what the user is trying to accomplish.")
        prompt_lines.append("2. Replace literal typed strings with variable placeholders {varName} everywhere (name, steps, instructions) if they should be provided at runtime.")
        prompt_lines.append("3. Mention the button/link labels or field names the user interacted with (as seen in the cues).")
        prompt_lines.append("4. Write GOAL-ORIENTED step instructions that express intent, not mechanical clicks.")
        prompt_lines.append("5. Use flexible element descriptions, not rigid CSS selectors.")
        prompt_lines.append("6. DO NOT include 'Open [site]' or 'Navigate to [url]' in steps - the startUrl loads automatically.")
        prompt_lines.append("")
        prompt_lines.append("Respond with JSON only. Do not add commentary.")
        return "\n".join(prompt_lines)

    @staticmethod
    def _summarize_events(events: List[Dict[str, Any]], *, limit: int) -> List[str]:
        if not events:
            return []
        lines: List[str] = []
        scroll_dx = 0
        scroll_dy = 0
        scroll_ts: Optional[str] = None

        def flush_scroll() -> None:
            nonlocal scroll_dx, scroll_dy, scroll_ts
            if scroll_dx == 0 and scroll_dy == 0:
                return
            ts_text = scroll_ts or "?"
            parts: List[str] = []
            if scroll_dy:
                direction = "down" if scroll_dy > 0 else "up"
                parts.append(f"{direction} ~{abs(scroll_dy)}")
            if scroll_dx:
                direction = "right" if scroll_dx > 0 else "left"
                parts.append(f"{direction} ~{abs(scroll_dx)}")
            detail = " & ".join(parts) if parts else "down"
            lines.append(f"{ts_text} scroll {detail}")
            scroll_dx = 0
            scroll_dy = 0
            scroll_ts = None

        for event in events[:limit]:
            kind = str(event.get("kind") or "")
            ts_value = event.get("ts")
            try:
                ts = float(ts_value)
                ts_text = f"{ts:06.3f}s"
            except (TypeError, ValueError):
                ts_text = str(ts_value) if ts_value is not None else "?"

            if kind == "scroll":
                delta_x = int(event.get("deltaX") or 0)
                delta_y = int(event.get("deltaY") or 0)
                scroll_dx += delta_x
                scroll_dy += delta_y
                scroll_ts = scroll_ts or ts_text
                continue

            flush_scroll()

            if kind == "key_hold":
                key = event.get("key")
                combo = event.get("combo")
                duration = float(event.get("duration") or 0.0)
                detail = combo or key or "key"
                lines.append(f"{ts_text} key_hold {detail} for {duration:0.2f}s")
                continue

            if kind in {"keydown", "keydown_repeat"}:
                key = event.get("key")
                combo = event.get("combo")
                detail = combo or key or "key"
                lines.append(f"{ts_text} {kind} {detail}")
                continue

            if kind == "keyup":
                key = event.get("key")
                lines.append(f"{ts_text} keyup {key!r}")
                continue

            if kind in {"pointerdown", "click", "pointerup"}:
                x = event.get("x")
                y = event.get("y")
                selector = event.get("selector") or ""
                actionable = event.get("actionable") or {}
                label = None
                if isinstance(actionable, dict):
                    label = actionable.get("label") or actionable.get("tag")
                if not label and isinstance(event.get("element"), dict):
                    label = event["element"].get("label")
                button = event.get("button")
                detail_parts = [f"({x:.1f},{y:.1f})"]
                if label:
                    detail_parts.append(f'"{label}"')
                if selector:
                    detail_parts.append(selector)
                if button:
                    detail_parts.append(f"button={button}")
                lines.append(
                    f"{ts_text} {kind} on "
                    + " ".join(part for part in detail_parts if part)
                )
                continue

            if kind == "input":
                selector = event.get("selector") or ""
                length = event.get("len")
                lines.append(f"{ts_text} input on {selector} len={length}")
                continue

            if kind.startswith("tab_"):
                title = event.get("title") or ""
                url = event.get("url") or ""
                lines.append(f"{ts_text} {kind} {title} {url}".strip())
                continue

            lines.append(f"{ts_text} {kind} {event}")

        flush_scroll()
        return lines

    @staticmethod
    def _downsample_frames(
        frames: List[RecordingFrame],
        *,
        limit: int,
    ) -> List[RecordingFrame]:
        if len(frames) <= limit:
            return frames
        step = max(1, len(frames) // limit)
        return frames[::step][:limit]

    def _extract_candidate_text(self, candidate) -> str:  # type: ignore[no-untyped-def]
        parts = getattr(candidate.content, "parts", []) or []
        chunks = [
            getattr(part, "text", "") for part in parts if getattr(part, "text", None)
        ]
        combined = "\n".join(chunk.strip() for chunk in chunks if chunk.strip())
        if not combined:
            raise RuntimeError("Gemini candidate response did not contain text")
        if self._debug:
            logger.debug("Plan synth raw response: %s", combined)
        return combined

    def _parse_payload(self, payload_text: str) -> Dict[str, object]:
        try:
            parsed = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode plan payload: %s", exc)
            raise RuntimeError("Plan provider returned malformed JSON") from exc

        if not isinstance(parsed, dict):
            raise RuntimeError("Plan payload must be a JSON object")

        steps = parsed.get("steps")
        if not isinstance(steps, list) or not steps:
            raise RuntimeError("Plan must contain at least one step")

        for raw_step in steps:
            if not isinstance(raw_step, dict):
                raise RuntimeError("Each step must be a JSON object")
            instructions = raw_step.get("instructions")
            if not isinstance(instructions, str) or not instructions.strip():
                raise RuntimeError(
                    "Each step must include natural language instructions"
                )

        return parsed

    def _extract_openai_payload(self, response):
        """
        Returns (plan_payload_dict, raw_response_json_str).
        Handles both structured-outputs and plain-text fallbacks.
        """
        # 1) Prefer structured outputs (already schema-validated)
        plan_payload = getattr(response, "output_parsed", None)

        # 2) Fallback: parse text when not using structured outputs
        if plan_payload is None:
            # Try the common helpers first
            text = getattr(response, "output_text", None)
            if not text:
                # As a belt-and-suspenders fallback, walk the content shape
                # (varies by SDK version / tool use)
                try:
                    first = response.output[0]
                    # many builds expose .content[0].text for text-only responses
                    text = first.content[0].text  # may raise; that's fine
                except Exception:
                    text = None
            if not text:
                raise ValueError(
                    "OpenAI response had no output_parsed and no output_text to parse."
                )
            plan_payload = json.loads(text)

        # 3) Raw response for logs – make sure to CALL model_dump()/model_dump_json()
        if hasattr(response, "model_dump_json"):
            raw_response = response.model_dump_json(exclude_none=True)  # <- JSON string
        elif hasattr(response, "model_dump"):
            raw_response = json.dumps(
                response.model_dump(exclude_none=True), ensure_ascii=False
            )
        else:
            # Very old SDKs: try a generic to_json()/dict conversion
            raw_response = json.dumps(
                json.loads(response.to_json()), ensure_ascii=False
            )

        return plan_payload, raw_response

    def _derive_step_checkpoints(
        self, recording: RecordingBundle, plan: Plan
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Heuristic: map steps to the closest recorded frame by timestamp.
        If markers exist, align steps 1:1 with markers in order.
        Otherwise, distribute target timestamps evenly across the frame timeline.
        Returns { step_id: [ { "png_base64": str, "label": str } ] }.
        """
        if not recording.frames or not plan.steps:
            return {}

        # Build arrays of (ts, png)
        frame_ts = [float(f.timestamp) for f in recording.frames]
        frame_png = [f.png for f in recording.frames]

        # Target timestamps per step
        if recording.markers:
            markers_sorted = sorted(recording.markers, key=lambda m: float(m.timestamp))
            target_ts = [float(m.timestamp) for m in markers_sorted][: len(plan.steps)]
        else:
            # Evenly spread across the observed time range
            start_ts = frame_ts[0]
            end_ts = frame_ts[-1]
            if end_ts <= start_ts:
                target_ts = [start_ts for _ in plan.steps]
            else:
                span = end_ts - start_ts
                target_ts = [
                    start_ts + (i * (span / max(1, len(plan.steps) - 1)))
                    for i in range(len(plan.steps))
                ]

        # For each target timestamp, choose nearest frame index
        def nearest_index(ts: float) -> int:
            # Linear search is fine (frames are already limited for synthesis); keep simple/robust
            best_i = 0
            best_d = float("inf")
            for i, fts in enumerate(frame_ts):
                d = abs(fts - ts)
                if d < best_d:
                    best_d = d
                    best_i = i
            return best_i

        mapping: Dict[str, List[Dict[str, Any]]] = {}
        for i, step in enumerate(plan.steps):
            idx = nearest_index(target_ts[i] if i < len(target_ts) else frame_ts[-1])
            # Single primary reference for now; can add neighborhood frames later if needed
            label = step.title
            mapping[step.id] = [{"png_base64": frame_png[idx], "label": label}]
        return mapping

    def _persist_step_checkpoints(
        self, recording_id: str, mapping: Dict[str, List[Dict[str, Any]]]
    ) -> None:
        """
        Persist to storage if available. Guarded to be non-fatal.
        """
        try:
            if mapping:
                save_visual_checkpoints_for_recording(recording_id, mapping)
        except Exception:
            logger.exception(
                "Failed to persist visual checkpoints for recording_id=%s", recording_id
            )
