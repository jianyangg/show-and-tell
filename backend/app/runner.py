from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple

from playwright.async_api import Browser, Page, async_playwright

from .synthesis import (
    Plan,
    PlanStep,
    VarValue,
    apply_plan_variables,
    copy_plan_with_vars,
    normalize_plan_variables,
)
from .navigation import wait_for_embedded_page

from io import BytesIO

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # Pillow optional; visual checks will be disabled if missing
logger = logging.getLogger(__name__)

RUNNER_VIEWPORT = {"width": 1440, "height": 900}
MAX_TURNS_PER_STEP = int(os.environ.get("RUNNER_MAX_TURNS", "4"))
NORMALIZED_RANGE = 999
VIEWPORT = RUNNER_VIEWPORT
TEACH_FRAME_INTERVAL = float(os.environ.get("TEACH_FRAME_INTERVAL_SECONDS", "1.0"))
TEACH_MAX_FRAMES = int(os.environ.get("TEACH_MAX_FRAMES", "360"))
DEFAULT_SEARCH_URL = os.environ.get(
    "RUNNER_DEFAULT_SEARCH_URL", "https://www.google.com/"
)

CHECKPOINT_SIMILARITY_THRESHOLD = float(
    os.environ.get("RUNNER_CHECKPOINT_THRESHOLD", "0.88")
)


class RunnerCallbacks(Protocol):
    async def publish_event(self, event_type: str, payload: Dict[str, Any]) -> None: ...

    async def publish_frame(
        self,
        png_base64: str,
        *,
        step_id: Optional[str],
        cursor: Optional[Dict[str, float]],
    ) -> None: ...

    async def is_aborted(self) -> bool: ...

    async def request_confirmation(self, payload: Dict[str, Any]) -> bool: ...

    async def request_variables(
        self, payload: Dict[str, Any]
    ) -> Dict[str, VarValue]: ...

    async def get_checkpoints(self, step_id: str) -> List[Dict[str, Any]]: ...


@dataclass
class AgentObservation:
    goal: str
    screenshot: str
    url: str
    turn: int
    history: List[str]
    vars: Dict[str, VarValue]
    step: PlanStep


@dataclass
class AgentAction:
    name: str
    args: Dict[str, Any]
    safety_decision: Optional[str] = None


@dataclass
class AgentDecision:
    prompt: str
    response_summary: str
    actions: List[AgentAction]


@dataclass
class TeachEvent:
    """Represents a single user action captured during Teach mode."""

    ts: float
    kind: str
    data: Dict[str, Any]


@dataclass
class TeachSession:
    """Tracks the browser/page pair for an active Teach mode session."""

    browser: Browser
    page: Page
    recording_id: str
    created_at: float = field(default_factory=time.time)
    events: List[TeachEvent] = field(default_factory=list)
    running: bool = True
    frames: List[Dict[str, Any]] = field(default_factory=list)
    _last_frame_ts: float = 0.0
    _pressed_keys: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    async def capture_frame(self, *, force: bool = False) -> str:
        png = await self.page.screenshot(type="png")
        encoded = base64.b64encode(png).decode("ascii")
        now = time.time()
        elapsed = now - self.created_at
        should_store = (
            force
            or not self.frames
            or (elapsed - self._last_frame_ts) >= TEACH_FRAME_INTERVAL
        )
        if should_store:
            self.frames.append({"timestamp": elapsed, "png": encoded})
            self._last_frame_ts = elapsed
            if len(self.frames) > TEACH_MAX_FRAMES:
                self.frames.pop(0)
        return encoded

    def log(self, kind: str, **data: Any) -> None:
        self.events.append(
            TeachEvent(ts=time.time() - self.created_at, kind=kind, data=data)
        )

    def record_key_down(
        self,
        key: Optional[str],
        code: Optional[str],
        mods: List[str],
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not key:
            return
        now = time.time() - self.created_at
        if key not in self._pressed_keys:
            data = {"ts": now, "code": code, "mods": mods, "extra": extra or {}}
            self._pressed_keys[key] = data
            payload = {"key": key, "code": code, "mods": mods}
            if extra:
                payload.update(extra)
            self.events.append(TeachEvent(ts=now, kind="keydown", data=payload))
        else:
            # Repeated keydown while held; track it separately.
            payload = {"key": key, "code": code, "mods": mods}
            if extra:
                payload.update(extra)
            self.events.append(
                TeachEvent(
                    ts=now,
                    kind="keydown_repeat",
                    data=payload,
                )
            )

    def record_key_up(
        self, key: Optional[str], extra: Optional[Dict[str, Any]] = None
    ) -> None:
        if not key:
            return
        now = time.time() - self.created_at
        pressed = self._pressed_keys.pop(key, None)
        payload = {"key": key}
        if extra:
            payload.update(extra)
        self.events.append(TeachEvent(ts=now, kind="keyup", data=payload))
        if pressed:
            duration = max(0.0, now - pressed["ts"])
            hold_payload = {
                "key": key,
                "code": pressed.get("code"),
                "mods": pressed.get("mods", []),
                "duration": duration,
            }
            hold_extra = pressed.get("extra") or {}
            hold_payload.update(hold_extra)
            self.events.append(
                TeachEvent(
                    ts=now,
                    kind="key_hold",
                    data=hold_payload,
                )
            )


class TeachManager:
    """Owns the shared Playwright instance and active Teach sessions."""

    def __init__(self) -> None:
        self._pl = None
        self._sessions: Dict[str, TeachSession] = {}
        self._lock = asyncio.Lock()

    async def _ensure_playwright(self) -> None:
        if self._pl is None:
            self._pl = await async_playwright().start()

    async def start(
        self, *, recording_id: str, start_url: Optional[str] = None
    ) -> Tuple[str, TeachSession]:
        await self._ensure_playwright()
        browser = await self._pl.chromium.launch(
            headless=True, args=["--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=1.0)
        page = await context.new_page()
        if start_url:
            if not start_url.startswith(("http://", "https://")):
                start_url = f"https://{start_url}"
            await page.goto(start_url)
        session = TeachSession(browser=browser, page=page, recording_id=recording_id)
        session_id = f"teach_{int(time.time() * 1000)}"
        async with self._lock:
            self._sessions[session_id] = session
        return session_id, session

    async def stop(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        async with self._lock:
            if not self._sessions:
                return {"ok": False, "reason": "no active session"}
            if session_id is None:
                session_id, session = self._sessions.popitem()
            else:
                session = self._sessions.pop(session_id, None)
                if session is None:
                    return {"ok": False, "reason": "no such session"}
        session.running = False
        with contextlib.suppress(Exception):
            await session.capture_frame(force=True)
        with contextlib.suppress(Exception):
            await session.page.context.close()
            await session.browser.close()
        frames: List[Any] = list(session.frames)
        markers: List[Any] = []
        events = [
            {"ts": event.ts, "kind": event.kind, **event.data}
            for event in session.events
        ]
        return {
            "ok": True,
            "recordingId": session.recording_id,
            "teachId": session_id,
            "frames": frames,
            "markers": markers,
            "events": events,
        }

    async def get(self, session_id: str) -> Optional[TeachSession]:
        async with self._lock:
            return self._sessions.get(session_id)


teach_manager = TeachManager()


class RunnerError(RuntimeError):
    """Generic error raised when the executor cannot continue."""


class RunnerDecisionError(RunnerError):
    """Raised when Computer Use returns an unusable response, with prompt context."""

    def __init__(
        self,
        message: str,
        *,
        prompt: Optional[str] = None,
        response_summary: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.prompt = prompt
        self.response_summary = response_summary


class AbortRequested(RuntimeError):
    """Raised when the caller asks the loop to halt."""


class ComputerUseAgent:
    """Thin wrapper around the Gemini Computer Use API."""

    MODEL_ID = "gemini-2.5-computer-use-preview-10-2025"
    SUPPORTED_ACTIONS = {
        "navigate",
        "click_at",
        "type_text_at",
        "wait_5_seconds",
        "go_back",
        "go_forward",
        "search",
        "hover_at",
        "scroll_document",
        "scroll_at",
        "drag_and_drop",
        "key_combination",
    }
    ACTION_ALIASES = {
        "open_web_browser": "navigate",
        "open_url": "navigate",
    }

    def __init__(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        enabled_flag = os.environ.get("COMPUTER_USE_ENABLED") == "1"
        self.enabled = bool(api_key) and enabled_flag
        self._client = None
        self._config = None
        self._types = None
        self._debug = os.environ.get("COMPUTER_USE_DEBUG") == "1"

        if not self.enabled:
            if enabled_flag and not api_key:
                logger.warning(
                    "COMPUTER_USE_ENABLED=1 but GEMINI_API_KEY unset; Computer Use disabled."
                )
            return

        from google import (
            genai,
        )  # Imported lazily so unit tests do not require the SDK.
        from google.genai import types

        system_prompt = (
            "You control a Chromium browser via Playwright. "
            "Execute ONLY the current plan step and emit at most two actions per turn.\n"
            "Available tools (call exactly with the spelled names):\n"
            "- navigate(url: str)\n"
            "- open_web_browser()\n"
            "- wait_5_seconds()\n"
            "- go_back()\n"
            "- go_forward()\n"
            "- search()\n"
            "- click_at(x: int, y: int)\n"
            "- hover_at(x: int, y: int)\n"
            "- type_text_at(x: int, y: int, text: str, press_enter: bool = false, clear_before_typing: bool = true)\n"
            "- key_combination(keys: str)\n"
            "- scroll_document(direction: str)\n"
            "- scroll_at(x: int, y: int, direction: str, magnitude: int = 800)\n"
            "- drag_and_drop(x: int, y: int, destination_x: int, destination_y: int)\n"
            "Coordinate arguments use a 0-999 grid mapped to the viewport.\n"
            "Favor the tool that best matches the plan step. Avoid redundant browser launches or waits unless explicitly helpful."
        )

        self._client = genai.Client(api_key=api_key)
        self._config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[
                types.Tool(
                    computer_use=types.ComputerUse(
                        environment=types.Environment.ENVIRONMENT_BROWSER,
                        excluded_predefined_functions=[],
                    )
                )
            ],
        )
        self._types = types

    async def propose_actions(self, observation: AgentObservation) -> AgentDecision:
        if not (self.enabled and self._client and self._config and self._types):
            raise RunnerDecisionError(
                "Computer Use agent disabled. Set GEMINI_API_KEY and COMPUTER_USE_ENABLED=1."
            )

        screenshot_bytes = base64.b64decode(observation.screenshot.encode("ascii"))
        prompt_lines = [
            f"Overall goal: {observation.goal}",
            f"Current URL: {observation.url}",
            f"Turn: {observation.turn}",
            f"Plan variables: {json_dumps(observation.vars)}",
            f"Step JSON: {observation.step.model_dump(by_alias=True)}",
        ]
        instructions_text = getattr(observation.step, "instructions", None)
        if isinstance(instructions_text, str) and instructions_text.strip():
            prompt_lines.append(f"Instructions: {instructions_text}")
        if observation.history:
            prompt_lines.append("Recent actions:")
            prompt_lines.extend(f"- {item}" for item in observation.history[-5:])

        prompt_text = "\n".join(prompt_lines)

        request = self._types.Content(
            role="user",
            parts=[
                self._types.Part(text=prompt_text),
                self._types.Part.from_bytes(
                    data=screenshot_bytes, mime_type="image/png"
                ),
            ],
        )

        if self._debug:
            logger.info(
                "Computer Use turn=%d step=%s prompt=%s",
                observation.turn,
                observation.step.id,
                " ".join(prompt_lines)[:2000],
            )

        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self.MODEL_ID,
            contents=[request],
            config=self._config,
        )

        if not response.candidates:
            raise RunnerDecisionError(
                "Computer Use returned no candidates",
                prompt=prompt_text,
                response_summary="[]",
            )

        candidate = response.candidates[0]
        actions: List[AgentAction] = []
        parts = getattr(candidate.content, "parts", []) or []
        for part in parts:
            function_call = getattr(part, "function_call", None)
            if not function_call:
                continue
            name = getattr(function_call, "name", "")
            args = dict(getattr(function_call, "args", {}) or {})
            if name not in self.SUPPORTED_ACTIONS:
                alias = self.ACTION_ALIASES.get(name)
                if alias:
                    logger.info("Mapping Computer Use action '%s' to '%s'", name, alias)
                    name = alias
                    if name == "navigate" and "url" not in args:
                        candidate_url = _extract_first_url(
                            getattr(observation.step, "instructions", None)
                        )
                        if not candidate_url:
                            plan_url = observation.vars.get("url")
                            candidate_url = (
                                plan_url if isinstance(plan_url, str) else None
                            )
                        if candidate_url:
                            args["url"] = candidate_url
                if name not in self.SUPPORTED_ACTIONS:
                    logger.info("Ignoring unsupported Computer Use action '%s'", name)
                    continue
            safety = args.pop("safety_decision", None)
            actions.append(AgentAction(name=name, args=args, safety_decision=safety))

        if not actions:
            response_summary = json_dumps(
                [
                    {
                        "name": getattr(
                            getattr(part, "function_call", None), "name", ""
                        ),
                        "args": dict(
                            getattr(getattr(part, "function_call", None), "args", {})
                            or {}
                        ),
                    }
                    for part in parts
                    if getattr(part, "function_call", None)
                ]
            )
            raise RunnerDecisionError(
                "Computer Use returned no supported actions",
                prompt=prompt_text,
                response_summary=response_summary,
            )

        response_summary = json_dumps(
            [
                {
                    "name": action.name,
                    "args": action.args,
                    **(
                        {"safety_decision": action.safety_decision}
                        if action.safety_decision
                        else {}
                    ),
                }
                for action in actions
            ]
        )

        if self._debug:
            logger.info(
                "Computer Use proposed actions: %s",
                response_summary,
            )
        return AgentDecision(
            prompt=prompt_text, response_summary=response_summary, actions=actions
        )


class PlanRunner:
    """Executes plans by delegating low-level decisions to Gemini Computer Use."""

    def __init__(self) -> None:
        self._agent = ComputerUseAgent()
        # cache: step_id -> List[Tuple[str|None, int]]  (label, aHash)
        self._checkpoint_hash_cache: Dict[str, List[Tuple[Optional[str], int]]] = {}

    # --- Visual checkpoint helpers ------------------------------------------------
    def _decode_base64_png(png_b64: str) -> Optional["Image.Image"]:
        if Image is None:
            return None
        try:
            raw = base64.b64decode(png_b64.encode("ascii"))
            return Image.open(BytesIO(raw)).convert("L")
        except Exception:
            return None

    def _ahash(img: "Image.Image", size: int = 16) -> Optional[int]:
        try:
            # Downscale to size x size, compute average, and threshold to bits
            small = img.resize((size, size))
            pixels = list(small.getdata())
            avg = sum(pixels) / (size * size)
            bits = 0
            for p in pixels:
                bits = (bits << 1) | (1 if p >= avg else 0)
            return bits
        except Exception:
            return None

    def _hamming_distance(a: int, b: int) -> int:
        x = a ^ b
        # Count set bits
        return x.bit_count() if hasattr(int, "bit_count") else bin(x).count("1")

    def _hash_similarity(a: int, b: int, size: int = 16) -> float:
        # 1.0 == identical, 0.0 == totally different
        max_bits = size * size
        dist = _hamming_distance(a, b)
        return max(0.0, 1.0 - (dist / max_bits))

    async def run(
        self,
        plan: Plan,
        *,
        start_url: Optional[str],
        callbacks: RunnerCallbacks,
    ) -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                await self._execute_with_browser(
                    browser, plan, start_url=start_url, callbacks=callbacks
                )
            finally:
                await browser.close()

    async def _execute_with_browser(
        self,
        browser: Browser,
        plan: Plan,
        *,
        start_url: Optional[str],
        callbacks: RunnerCallbacks,
    ) -> None:
        context = await browser.new_context(
            viewport=RUNNER_VIEWPORT,
            screen=RUNNER_VIEWPORT,
            device_scale_factor=1.0,
            locale="en-US",
        )
        page = await context.new_page()
        try:
            await callbacks.publish_event(
                "runner_status",
                {"message": "browser_ready", "url": page.url},
            )

            if start_url:
                if not start_url.startswith(("http://", "https://")):
                    start_url = f"https://{start_url}"
                await page.goto(start_url, wait_until="domcontentloaded")
                try:
                    await wait_for_embedded_page(page, start_url)
                except RuntimeError as exc:
                    raise RunnerError(f"Start url iframe not ready: {exc}") from exc
                await callbacks.publish_event(
                    "navigate",
                    {"kind": "start_url", "url": start_url},
                )

            await self._emit_frame(callbacks, page, step_id=None, cursor=None)

            plan = await self._prepare_plan_variables(plan, callbacks)

            history: List[str] = []
            for raw_step in plan.steps:
                if await callbacks.is_aborted():
                    raise AbortRequested()
                step = self._resolve_step(raw_step, plan.vars)
                await callbacks.publish_event(
                    "step_started", {"stepId": step.id, "title": step.title}
                )
                if getattr(step, "instructions", None):
                    await callbacks.publish_event(
                        "console",
                        {"role": "Plan instructions", "message": step.instructions},
                    )

                await self._run_step(page, plan, step, history, callbacks)
                await callbacks.publish_event("step_completed", {"stepId": step.id})

            await callbacks.publish_event(
                "run_completed", {"ok": True, "url": page.url}
            )
        finally:
            await page.close()
            await context.close()

    async def _prepare_plan_variables(
        self,
        plan: Plan,
        callbacks: RunnerCallbacks,
    ) -> Plan:
        plan, placeholders = normalize_plan_variables(plan)
        if not placeholders:
            return plan
        missing = self._missing_plan_variables(plan, placeholders)
        if not missing:
            return plan
        await callbacks.publish_event(
            "console",
            {
                "role": "Runner",
                "message": "Awaiting variable values for: " + ", ".join(missing),
            },
        )
        payload: Dict[str, Any] = {
            "vars": [
                {"name": name, "value": plan.vars.get(name, "")} for name in missing
            ]
        }
        if await callbacks.is_aborted():
            raise AbortRequested()
        try:
            provided = await callbacks.request_variables(payload)
        except AbortRequested:
            raise
        except Exception as exc:
            raise RunnerError(f"Variable handshake failed: {exc}") from exc
        if not isinstance(provided, dict):
            raise RunnerError("Variable handshake returned invalid payload")
        if await callbacks.is_aborted():
            raise AbortRequested()
        sanitized = dict(plan.vars)
        missing_after: List[str] = []
        for name in missing:
            if name not in provided:
                missing_after.append(name)
                continue
            coerced = self._coerce_runtime_variable(provided[name])
            if coerced is None:
                missing_after.append(name)
                continue
            sanitized[name] = coerced
        if missing_after:
            raise RunnerError(
                "Missing values for variables: " + ", ".join(sorted(missing_after))
            )
        plan = copy_plan_with_vars(plan, sanitized)
        await callbacks.publish_event(
            "variables_applied",
            {"vars": {name: sanitized[name] for name in sorted(missing)}},
        )
        return plan

    def _missing_plan_variables(self, plan: Plan, placeholders: Set[str]) -> List[str]:
        missing: List[str] = []
        for name in sorted(placeholders):
            if name not in plan.vars:
                missing.append(name)
                continue
            value = plan.vars[name]
            if isinstance(value, str):
                if value.strip():
                    continue
                missing.append(name)
            elif value is None:
                missing.append(name)
        return missing

    def _coerce_runtime_variable(self, value: Any) -> Optional[VarValue]:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip()
        return text or None

    async def _get_step_checkpoints(
        self, callbacks: RunnerCallbacks, step_id: str
    ) -> List[Dict[str, Any]]:
        # Best-effort: callbacks may not implement get_checkpoints yet.
        try:
            cps = await callbacks.get_checkpoints(step_id)  # type: ignore[attr-defined]
            if not isinstance(cps, list):
                return []
            # Expected schema for each checkpoint:
            # {"png_base64": str, "label": Optional[str]}
            return [cp for cp in cps if isinstance(cp, dict) and "png_base64" in cp]
        except AttributeError:
            return []
        except Exception:
            logger.exception("Failed to fetch checkpoints for step %s", step_id)
            return []

    def _ensure_checkpoint_hashes(
        self, step_id: str, checkpoints: List[Dict[str, Any]]
    ) -> None:
        if step_id in self._checkpoint_hash_cache:
            return
        results: List[Tuple[Optional[str], int]] = []
        for cp in checkpoints:
            img = _decode_base64_png(cp.get("png_base64", ""))
            if img is None:
                continue
            h = _ahash(img)
            if h is None:
                continue
            results.append((cp.get("label"), h))
        if results:
            self._checkpoint_hash_cache[step_id] = results

    def _visual_match_score(
        self, screenshot_b64: str, step_id: str
    ) -> Tuple[float, Optional[str]]:
        """Return best similarity score in [0,1] against cached checkpoints for step_id."""
        if step_id not in self._checkpoint_hash_cache:
            return (0.0, None)
        img = _decode_base64_png(screenshot_b64)
        if img is None:
            return (0.0, None)
        h = _ahash(img)
        if h is None:
            return (0.0, None)
        best = (0.0, None)  # (score, label)
        for label, cp_hash in self._checkpoint_hash_cache[step_id]:
            score = _hash_similarity(h, cp_hash)
            if score > best[0]:
                best = (score, label)
        return best

    async def _run_step(
        self,
        page: Page,
        plan: Plan,
        step: PlanStep,
        history: List[str],
        callbacks: RunnerCallbacks,
    ) -> None:
        # Fetch any reference frames for this step (if provided by the caller)
        checkpoints = await self._get_step_checkpoints(callbacks, step.id)
        require_visual_match = bool(checkpoints)
        if require_visual_match:
            self._ensure_checkpoint_hashes(step.id, checkpoints)
        for turn in range(1, MAX_TURNS_PER_STEP + 1):
            if await callbacks.is_aborted():
                raise AbortRequested()

            screenshot = await self._capture(page)
            observation = AgentObservation(
                goal=_apply_vars(plan.name, plan.vars) or plan.name,
                screenshot=screenshot,
                url=page.url,
                turn=turn,
                history=history,
                vars=plan.vars,
                step=step,
            )
            try:
                decision = await self._agent.propose_actions(observation)
            except RunnerDecisionError as exc:
                if exc.prompt:
                    await callbacks.publish_event(
                        "console",
                        {"role": "ComputerUse prompt", "message": exc.prompt},
                    )
                if exc.response_summary:
                    await callbacks.publish_event(
                        "console",
                        {
                            "role": "ComputerUse response",
                            "message": exc.response_summary,
                        },
                    )
                raise
            await callbacks.publish_event(
                "console",
                {
                    "role": "ComputerUse prompt",
                    "message": decision.prompt,
                },
            )
            await callbacks.publish_event(
                "console",
                {
                    "role": "ComputerUse response",
                    "message": decision.response_summary,
                },
            )

            turn_cursor: Optional[Dict[str, float]] = None
            summaries: List[str] = []
            action_failed = False
            for action in decision.actions:
                if action.safety_decision == "require_confirmation":
                    allowed = await callbacks.request_confirmation(
                        {"stepId": step.id, "action": action.name, "args": action.args}
                    )
                    if not allowed:
                        raise RunnerError("Action declined by operator")

                try:
                    summary, cursor = await self._apply_action(page, action)
                except RunnerError as exc:
                    error_message = str(exc)
                    await callbacks.publish_event(
                        "console",
                        {
                            "role": "Runner",
                            "message": f"Action failed: {error_message}",
                        },
                    )
                    history.append(f"error: {error_message}")
                    action_failed = True
                    break
                turn_cursor = cursor or turn_cursor
                summaries.append(summary)
                history.append(summary)
                await callbacks.publish_event(
                    "action_executed",
                    {
                        "stepId": step.id,
                        "action": action.name,
                        "args": action.args,
                        "summary": summary,
                    },
                )
                await self._emit_frame(
                    callbacks, page, step_id=step.id, cursor=turn_cursor
                )

            await self._emit_frame(callbacks, page, step_id=step.id, cursor=turn_cursor)

            if action_failed:
                continue

            # Decide if the step is complete
            if require_visual_match:
                latest = await self._capture(page)
                score, label = self._visual_match_score(latest, step.id)
                await callbacks.publish_event(
                    "checkpoint_evaluated",
                    {
                        "stepId": step.id,
                        "score": round(score, 4),
                        "threshold": CHECKPOINT_SIMILARITY_THRESHOLD,
                        **({"label": label} if label else {}),
                    },
                )
                if score >= CHECKPOINT_SIMILARITY_THRESHOLD:
                    await callbacks.publish_event(
                        "checkpoint_matched",
                        {
                            "stepId": step.id,
                            "score": round(score, 4),
                            **({"label": label} if label else {}),
                        },
                    )
                    return
                # Not yet matched; try another turn (until MAX_TURNS_PER_STEP)
                continue
            else:
                # Backward compatible: if no checkpoints provided for this step,
                # consider the step complete after a single turn (previous behavior).
                return

        raise RunnerError(f"Exceeded max turns for step {step.id}")

    async def _apply_action(
        self, page: Page, action: AgentAction
    ) -> tuple[str, Optional[Dict[str, float]]]:
        name = action.name
        args = action.args

        if name == "navigate":
            url = args.get("url")
            if not isinstance(url, str):
                raise RunnerError("navigate requires a 'url' argument")
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            await page.goto(url, wait_until="domcontentloaded")
            return (f"navigate -> {url}", None)

        if name == "wait_5_seconds":
            await page.wait_for_timeout(5_000)
            return ("wait_5_seconds", None)

        if name == "go_back":
            response = await page.go_back(wait_until="domcontentloaded")
            suffix = " (noop)" if response is None else ""
            return (f"go_back{suffix}", None)

        if name == "go_forward":
            response = await page.go_forward(wait_until="domcontentloaded")
            suffix = " (noop)" if response is None else ""
            return (f"go_forward{suffix}", None)

        if name == "search":
            await page.goto(DEFAULT_SEARCH_URL, wait_until="domcontentloaded")
            return (f"search -> {DEFAULT_SEARCH_URL}", None)

        if name in {"click_at", "type_text_at"}:
            x_norm = _to_float(args.get("x", 0.0))
            y_norm = _to_float(args.get("y", 0.0))
            x_px, y_px = _denormalize_point(x_norm, y_norm)
            cursor = {"x": x_norm / NORMALIZED_RANGE, "y": y_norm / NORMALIZED_RANGE}
            if name == "type_text_at":
                text = str(args.get("text") or "")
                clear_before_typing = bool(args.get("clear_before_typing", True))
                if clear_before_typing:
                    # Triple-click to select all text before clearing.
                    await page.mouse.click(x_px, y_px, click_count=3)
                    await page.keyboard.press("Delete")
                else:
                    await page.mouse.click(x_px, y_px)

                if text:
                    await page.keyboard.type(text)
                if args.get("press_enter"):
                    await page.keyboard.press("Enter")
            else:  # click_at
                await page.mouse.click(x_px, y_px)
            return (f"{name} @{x_px},{y_px}", cursor)

        if name == "hover_at":
            x_norm = _to_float(args.get("x", 0.0))
            y_norm = _to_float(args.get("y", 0.0))
            x_px, y_px = _denormalize_point(x_norm, y_norm)
            cursor = {"x": x_norm / NORMALIZED_RANGE, "y": y_norm / NORMALIZED_RANGE}
            await page.mouse.move(x_px, y_px)
            return ("hover_at", cursor)

        if name == "scroll_document":
            direction = str(args.get("direction", "") or "").lower()
            dx, dy = _scroll_deltas(direction, args.get("magnitude"))
            await page.mouse.wheel(dx, dy)
            return (f"scroll_document {direction or 'down'}", None)

        if name == "scroll_at":
            x_norm = _to_float(args.get("x", 0.0))
            y_norm = _to_float(args.get("y", 0.0))
            direction = str(args.get("direction", "") or "").lower()
            magnitude = args.get("magnitude")
            dx, dy = _scroll_deltas(direction, magnitude)
            x_px, y_px = _denormalize_point(x_norm, y_norm)
            cursor = {"x": x_norm / NORMALIZED_RANGE, "y": y_norm / NORMALIZED_RANGE}
            await page.mouse.move(x_px, y_px)
            scrolled = await page.evaluate(
                """
                ([x, y, dx, dy]) => {
                    const point = document.elementFromPoint(x, y);
                    if (!point) {
                        window.scrollBy({left: dx, top: dy, behavior: 'auto'});
                        return false;
                    }
                    let node = point;
                    const isScrollable = el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const overflowY = style.overflowY;
                        const overflowX = style.overflowX;
                        const canScrollY = dy !== 0 && el.scrollHeight > el.clientHeight;
                        const canScrollX = dx !== 0 && el.scrollWidth > el.clientWidth;
                        return (
                            ((canScrollY && (overflowY === 'auto' || overflowY === 'scroll')) ||
                                (canScrollX && (overflowX === 'auto' || overflowX === 'scroll')))
                        );
                    };
                    while (node && node !== document.body && !isScrollable(node)) {
                        node = node.parentElement;
                    }
                    if (!node) {
                        window.scrollBy({left: dx, top: dy, behavior: 'auto'});
                        return false;
                    }
                    node.scrollBy({left: dx, top: dy, behavior: 'auto'});
                    return true;
                }
                """,
                (x_px, y_px, dx, dy),
            )
            label = "element" if scrolled else "document"
            return (f"scroll_at {direction or 'down'} ({label})", cursor)

        if name == "drag_and_drop":
            x_norm = _to_float(args.get("x", 0.0))
            y_norm = _to_float(args.get("y", 0.0))
            dest_x_norm = _to_float(args.get("destination_x", 0.0))
            dest_y_norm = _to_float(args.get("destination_y", 0.0))
            x_px, y_px = _denormalize_point(x_norm, y_norm)
            dest_x_px, dest_y_px = _denormalize_point(dest_x_norm, dest_y_norm)
            cursor = {
                "x": dest_x_norm / NORMALIZED_RANGE,
                "y": dest_y_norm / NORMALIZED_RANGE,
            }
            await page.mouse.move(x_px, y_px)
            await page.mouse.down()
            await page.mouse.move(dest_x_px, dest_y_px, steps=20)
            await page.mouse.up()
            return (f"drag_and_drop {x_px},{y_px}->{dest_x_px},{dest_y_px}", cursor)

        if name == "key_combination":
            keys = args.get("keys")
            if not isinstance(keys, str) or not keys:
                raise RunnerError("key_combination requires a 'keys' string argument")
            await page.keyboard.press(keys)
            return (f"key_combination {keys}", None)

        raise RunnerError(f"Unsupported Computer Use action '{name}'")

    def _resolve_step(self, step: PlanStep, vars: Dict[str, VarValue]) -> PlanStep:
        payload = step.model_dump()
        payload["instructions"] = _apply_vars(payload.get("instructions"), vars)
        payload["title"] = _apply_vars(payload.get("title"), vars)
        return PlanStep.model_validate(payload)

    async def _capture(self, page: Page) -> str:
        png_bytes = await page.screenshot(full_page=False)
        return base64.b64encode(png_bytes).decode("ascii")

    async def _emit_frame(
        self,
        callbacks: RunnerCallbacks,
        page: Page,
        *,
        step_id: Optional[str],
        cursor: Optional[Dict[str, float]],
    ) -> None:
        screenshot = await self._capture(page)
        await callbacks.publish_frame(screenshot, step_id=step_id, cursor=cursor)


def _apply_vars(value: Optional[str], vars: Dict[str, VarValue]) -> Optional[str]:
    return apply_plan_variables(value, vars)


def _extract_first_url(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"https?://[^\s)]+", text)
    if match:
        return match.group(0).rstrip(".,)")
    match = re.search(r"\b(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s)]*)?", text)
    if match:
        url = match.group(0).rstrip(".,)")
        if not url.lower().startswith("http"):
            url = f"http://{url}"
        return url
    return None


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _denormalize_point(x_norm: float, y_norm: float) -> tuple[int, int]:
    def clamp(coord: float) -> float:
        return max(0.0, min(coord, float(NORMALIZED_RANGE)))

    x_clamped = clamp(x_norm)
    y_clamped = clamp(y_norm)
    width = RUNNER_VIEWPORT["width"]
    height = RUNNER_VIEWPORT["height"]
    x_px = int(round((x_clamped / NORMALIZED_RANGE) * (width - 1)))
    y_px = int(round((y_clamped / NORMALIZED_RANGE) * (height - 1)))
    return x_px, y_px


def _scroll_deltas(direction: str, magnitude: Optional[Any]) -> tuple[int, int]:
    default_magnitude = 800
    try:
        mag = int(magnitude)
    except (TypeError, ValueError):
        mag = default_magnitude
    mag = max(-2000, min(2000, mag))  # prevent extreme scroll events
    direction = direction.lower()
    if direction == "up":
        return (0, -abs(mag))
    if direction == "left":
        return (-abs(mag), 0)
    if direction == "right":
        return (abs(mag), 0)
    # default to scrolling down
    return (0, abs(mag))


def json_dumps(payload: Any) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


# Expected get_checkpoints() return format:
# List[{"png_base64": <base64 PNG string>, "label": Optional[str]}]
# You can source these frames from storage.py or synthesis.py (e.g., plan synthesis
# can annotate step IDs with representative screenshots taken during Teach mode).
# To tune strictness, set RUNNER_CHECKPOINT_THRESHOLD (default 0.88).
