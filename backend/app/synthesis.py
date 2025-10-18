from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

try:  # pragma: no cover - compatibility shim for Pydantic v1
    from pydantic import ConfigDict  # type: ignore
except ImportError:  # pragma: no cover
    ConfigDict = None  # type: ignore

logger = logging.getLogger(__name__)

DEFAULT_PLAN_MODEL = "gemini-2.5-pro"
PLAN_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
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
    "required": ["name", "steps"],
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


class PlanSynthesisRequest(_BaseModel):
    recording_id: str = Field(..., alias="recordingId")
    plan_name: Optional[str] = Field(default=None, alias="planName")
    provider: Optional[str] = None


@dataclass
class PlanSynthesisResult:
    plan: Plan
    prompt: str
    raw_response: str


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

        provider = self._resolve_provider(request.provider)
        prompt = self._build_prompt(recording, request.plan_name)

        if provider == "gemini":
            plan_payload, raw_response = await self._synthesize_with_gemini(
                prompt, recording
            )
        else:
            plan_payload, raw_response = await self._synthesize_with_chatgpt(
                prompt, recording
            )

        plan = Plan.model_validate(plan_payload)
        return PlanSynthesisResult(plan=plan, prompt=prompt, raw_response=raw_response)

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
                    "name": "plan_schema",  # required
                    "schema": PLAN_JSON_SCHEMA,  # <-- REQUIRED here (not inside 'json_schema')
                    "strict": True,  # optional but recommended
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

    def _build_prompt(
        self, recording: RecordingBundle, plan_name: Optional[str]
    ) -> str:
        markers = sorted(recording.markers, key=lambda marker: marker.timestamp)
        marker_lines = [
            f"- t={marker.timestamp:.2f}s :: {marker.label or 'Marked step'}"
            for marker in markers
        ]
        timeline_lines = self._summarize_events(recording.events, limit=2_000)

        prompt_lines = [
            "You are building an automation plan for Gemini Computer Use.",
            "Return strict JSON following this schema:",
            json.dumps(
                {
                    "name": plan_name or "recorded run",
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
            "Rules:",
            "- Prefer descriptive step titles.",
            "- Provide actionable natural language instructions that reference visible UI affordances.",
            "- When you reference a plan variable use the {var} notation and register it under vars.",
            "- Prefer 3-6 concise steps that map to the marked timestamps.",
            "Computer Use toolbelt (reference these capabilities in your instructions when helpful): "
            "navigate(url), open_web_browser(), wait_5_seconds(), go_back(), go_forward(), search(), "
            "click_at(x,y), hover_at(x,y), type_text_at(x,y,text, press_enter=false, clear_before_typing=true), "
            "key_combination(keys), scroll_document(direction), scroll_at(x,y,direction,magnitude), drag_and_drop(x,y,destination_x,destination_y).",
            'Write instructions as first-person imperatives (e.g., "Click the Investing link in the top navigation").',
        ]

        if marker_lines:
            prompt_lines.append("Markers collected during teaching:")
            prompt_lines.extend(marker_lines)

        if timeline_lines:
            prompt_lines.append(
                "Interaction timeline (chronological, already normalized into high-level cues):"
            )
            prompt_lines.append(
                'Use these cues to craft precise natural language instructions (e.g., "Scroll down to the market section").'
            )
            prompt_lines.extend(timeline_lines)

        if recording.transcript:
            prompt_lines.append("Transcribed narration (chronological):")
            prompt_lines.append(recording.transcript.strip())

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
                lines.append(f"{ts_text} {kind} on " + " ".join(part for part in detail_parts if part))
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
