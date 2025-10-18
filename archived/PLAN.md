# 0) Executive summary

**Goal.** A general **audio+visual learning** agent that watches you demonstrate a task inside an **embedded iframe**, learns the steps (using voice to infer intent), and then **replays** that task reliably on any site — all **browser-only**, with execution driven in the backend via Chromium + Playwright and **Gemini 2.5 Computer Use** (screenshot→action→screenshot loop). ([Google AI for Developers][1])

**Models.**

* **Runtime control:** **Gemini 2.5 Computer Use** (action planner).
* **Understanding/alignment & ASR:** **Gemini 2.5 Pro** as the default (optionally **2.5 Flash** for cheaper ASR-only parsing). Gemini 2.5 Pro is the long-context, multimodal “thinking” model suited for parsing audio+video timelines. ([Google AI for Developers][2])

**Key UX.** Record (iframe region + mic) → Review (steps, variables, assertions) → Run (live “runner viewport” streamed into your webapp’s iframe).

---

# 1) Non-goals & guardrails (MVP)

* **No desktop/OS automation** (browser-only).
* **No auth / no sharing** in MVP (keep flexibility to add later).
* **Ignore CAPTCHA/2FA** for now.
* **Local dev only; single run at a time** (no parallelism).
* **Keep raw recordings** (video/audio) for now.

---

# 2) System architecture (end-to-end)

## 2.1 Frontend (React + TS)

**Recorder (iframe-focused).**

* Capture **the tab** once, then **crop to your embedded iframe** using **Region Capture** (`CropTarget.fromElement(iframeEl)` + `track.cropTo()`), so recordings and thumbnails show only the task surface. Requires HTTPS and a user gesture. ([MDN Web Docs][3])
* Capture **mic** with `getUserMedia({ audio:true })`.
* Emit: **keyframes** (on nav / click / burst typing / every N sec), **input events** (click/keypress with DOM probes near the pointer), and **audio**.

**Review.**

* Timeline with keyframes + transcript ribbon.
* Steps table (title, action, **ranked locators**, assert, **voice_snippet**, alternates).
* Variables panel (infer literals → `{search_term}`, etc.).
* Dry-run assertions where possible.

**Run.**

* “Runner viewport” iframe shows a **live feed** of the backend Chromium page (not the actual cross-origin DOM). We render frames streaming from the backend (see §6.3).
* Live per-step logs, assertion pass/fail, token/cost.

**Permissions for embedded content.**

```html
<iframe src="about:blank" allow="display-capture; microphone"></iframe>
```

(Feature/Permissions-Policy governs capture prompts; HTTPS required.) ([MDN Web Docs][4])

## 2.2 Backend (FastAPI)

* **Step Synthesis Service** → builds a **Plan** from the `RecordingBundle` using **Gemini 2.5 Pro** (multimodal alignment of frames+ASR; Flash optional for ASR-only). ([Google AI for Developers][2])
* **Execution Service** → **Chromium via Playwright** (one context per run) + **Gemini 2.5 Computer Use** loop:

  * Pass screenshot/URL + step intent → receive UI action(s) → apply via Playwright → capture fresh screenshot/URL → repeat until assert passes. (Gemini Computer Use docs specify the screenshot→action agent loop and even show **Playwright** as the action handler.) ([Google AI for Developers][1])
* **Live updates** via **FastAPI WebSockets** to the FE (step_started/step_passed/screenshot_url, token usage, costs). ([fastapi.tiangolo.com][5])
* **Storage:** Postgres (Plans/Runs/Artifacts) + Redis (ephemeral run state & throttles).

---

# 3) Data contracts

**RecordingBundle**

```ts
type Word = { w: string; ts: number; te: number };
type DomProbe = { role?: string; name?: string; label?: string; testId?: string; text?: string; css?: string };
type Event = { t: number; type: 'click'|'fill'|'keypress'|'navigate'; domProbe?: DomProbe; xy?: [number,number]; value?: string };

type RecordingBundle = {
  frames: { t: number; png: string }[];     // iframe-cropped keyframes
  events: Event[];                           // DOM probes are best-effort hints
  audio: { wavPath: string };
  asr?: { words: Word[] };                   // optional if Gemini Pro handles ASR
};
```

**Plan / Step DSL**

```ts
type Locator =
  | { strategy:'role'; role:string; name?:string }
  | { strategy:'testid'; value:string }
  | { strategy:'text'; value:string }
  | { strategy:'css'; value:string };

type Assertion = { kind:'visible'|'visibleText'|'url'|'attribute'; expect:string; timeoutMs?:number };

type Step = {
  id: string; title: string;
  action: 'navigate'|'click'|'fill'|'select'|'press';
  target: Locator; value?: string;
  assert: Assertion;
  voice_snippet: string;
  alternatives?: Locator[];
};

type Plan = { name: string; vars: Record<string,string|number>; steps: Step[] };
```

**Run events (WebSocket/SSE)**

```ts
type RunEvent =
  | { type:'run_started'; runId:string }
  | { type:'step_started'; stepId:string; screenshot:string; url:string }
  | { type:'action_applied'; stepId:string; action:any }
  | { type:'assert_passed'|'assert_failed'; stepId:string; details?:string }
  | { type:'token_usage'; model:string; input:number; output:number; costUsd:number }
  | { type:'runner_frame'; png:string }  // for live viewport
  | { type:'run_finished'; ok:boolean };
```

---

# 4) Recording → Synthesis pipeline

1. **Start.** User clicks **Record** → `getDisplayMedia()` + **Region Capture** → crop to the iframe rect; also `getUserMedia({audio:true})`. (User gesture + secure context apply.) ([MDN Web Docs][4])
2. **During.** Emit keyframes + input events (with **DOM probe** at pointer: role, name, label, testId, text).
3. **Stop.** Persist `RecordingBundle` (keep **raw** video/audio).
4. **Synthesize Plan.** Use **Gemini 2.5 Pro** to:

   * Align voice to interaction clusters → `voice_snippet` per step.
   * Infer **semantic locators** (rank: role+accessible name → data-test-id → stable text → CSS as last resort).
   * Propose **assertions** (“web-first” style, auto-waiting). ([Playwright][6])
   * Extract **variables** from typed literals.

---

# 5) Runtime loop (two-agent pattern)

**Agent-1 (Orchestrator; runs on backend).**
Builds a concise instruction for the current step from: {screenshot, URL, `voice_snippet`, Step DSL, `vars`}. On failure, tries alternates (selectors) + simple scroll/paginate heuristics.

**Agent-2 (Executor = Gemini 2.5 Computer Use).**
Inputs: screenshot + instruction. Output: **UI action(s)**. Your runner applies them via Playwright and returns a fresh screenshot/URL. (This is exactly the loop in the Computer Use docs; the page shows Playwright-based examples and recommended viewport.) ([Google AI for Developers][1])

**Web-first assertions (no sleeps).**
Assertions like `toBeVisible`, `toHaveURL` auto-wait/retry until stable; far less flake. ([Playwright][6])

**Pseudocode**

```ts
for (const step of plan.steps) {
  const obs = { screenshot, url, vars, voice: step.voice_snippet };
  const instruction = agent1_makeInstruction(step, obs);
  const action = gemini_computer_use(instruction, screenshot); // returns UI action(s)
  await playwright_apply(action);                               // click/fill/etc
  const { screenshot:newShot, url:newUrl } = await capture_state();
  const ok = assert_web_first(newShot, newUrl, step.assert);
  if (!ok) await try_alternates(step);
  screenshot = newShot; url = newUrl;
}
```

---

# 6) “I want to SEE it in the iframe” — runner viewport

Because cross-origin DOMs can’t be controlled/read from your FE parent page (SOP), you’ll **execute in a backend browser** and **stream visuals** to the webapp’s **iframe**. Two simple options:

1. **CDP screencast frames** → push PNGs via WS as `runner_frame` events; the iframe renders them to a `<canvas>` at ~5–10 fps for a smooth preview. (CDP exposes page screencast frame events.) ([chromedevtools.github.io][7])
2. **Periodic screenshots** via Playwright → lower fps but simpler (also push as `runner_frame`).

Either way, you meet the requirement: **actions are visible inside your app’s iframe**, not a separate OS window.

---

# 7) HTTP & WS APIs (thin, explicit)

**HTTP**

* `POST /recordings/start` → `{ recordingId }`
* `POST /recordings/:id/stop` → saves `RecordingBundle`
* `POST /plans/synthesize` → `{ planId, planJson }` (uses Gemini 2.5 Pro) ([Google AI for Developers][2])
* `PUT /plans/:id` → edit/save
* `POST /runs/start` → `{ runId }` (spins Chromium context, starts loop with **Computer Use**) ([Google AI for Developers][1])
* `POST /runs/:id/abort` → cancel

**WebSocket**

* `GET /runs/:id/stream` → emits **RunEvent** objects (includes `runner_frame` images) using FastAPI WebSockets. ([fastapi.tiangolo.com][5])

---

# 8) Telemetry & logs (day-one)

* **Model chatter**: store the **exact prompts & tool calls** between Agent-1 ↔ Computer Use (sanitized).
* **Token & cost** per turn (model id, in/out tokens, unit price).
* **Selector resolution**: which locator won; alternates tried.
* **Assertion retries & latencies** (per step).
* **Runner stats**: fps of viewport, screenshot latency, navigation timings.

(Expose all of the above in the browser console + a collapsible “Run details” pane.)

---

# 9) Implementation checklist (MVP, local-only)

**Models & SDK**

* Install **Google GenAI SDK**; enable **Gemini 2.5 Computer Use** + **2.5 Pro**. The Computer Use doc shows Playwright wiring and the **exact model id** to call (`gemini-2.5-computer-use-preview-10-2025`). ([Google AI for Developers][1])

**Backend**

* ✅ FastAPI app exposes `/runs/start`, `/runs/:id/stream`, `/plans/synthesize`, `/recordings/*`, etc. ([fastapi.tiangolo.com][5])
* ✅ **Playwright (Python)** loop runs on Chromium, translating Gemini Computer Use actions (normalized coords → pixels). ([Google AI for Developers][1])
* ✅ **Runner viewport** streams CDP screencast frames over WebSocket as base64 PNGs. ([chromedevtools.github.io][7])
* 🔄 Next: let the runner consume synthesized Plans (step orchestration) instead of free-form goal turns.

**Frontend**

* ✅ **Recorder**: `getDisplayMedia()` + **Region Capture`** against the same-origin demo iframe; hooks capture start/stop/upload. ([MDN Web Docs][4])
* ✅ **Review screen**: timeline scrubber canvas, event overlays, plan panel (steps, vars, locator hints). Run screen still streams live viewport + event log.
* 🔄 Next: inline editing for variables/assertions, confidence badges, and tighter integration with plan-driven runs.

**Storage**

* ✅ Recording bundles persist to disk (frames/audio/events). Plan + run history now flow through repository interfaces with in-memory defaults.
* 🔄 Next: wire Postgres (`DATABASE_URL`) + Redis (`REDIS_URL`) in dev, add migrations, and persist plan-driven run artifacts.

---

# 10) Robust selectors & assertions (why this works)

* Prefer **role + accessible name** (Testing Library/Playwright guidance), then **data-test-id**, then **stable text**, then **CSS** as last resort.
* Use **web-first assertions** (auto-wait/retry like `toBeVisible`, `toHaveURL`) to eliminate sleeps and reduce flake. ([Playwright][6])

---

# 11) Milestones

* **M0 — Happy path**
  ✅ Record iframe+mic → synthesize Plan (Pro or fallback). 🔄 Wire the runner to execute the stored Plan on a public, low-friction site and stream per-step asserts in the iframe.

* **M1 — Variables & templates**
  Detect literals → `{search_term}`; re-run with new values.

* **M2 — Resilience**
  Alternates, scroll/paginate heuristics, better failure messages.

* **M3 — Reporting**
  Timeline with step screenshots, token/cost summary, exported Plan JSON.

---

# 12) Risks & mitigations

* **Cross-origin DOM access** is blocked in FE; **backend execution** via Playwright avoids SOP issues and is the pattern recommended by the **Computer Use** docs (screenshot→action in your controlled browser). ([Google AI for Developers][1])
* **Viewport streaming** via CDP screencast can be CPU-heavy at high FPS; start at ~5–10 fps. (CDP exposes screencast frames, but watch perf.) ([chromedevtools.github.io][7])
* **Recording friction**: Region Capture requires secure context & user gesture. Make the prompt UX obvious. ([MDN Web Docs][4])

---

## Anchor references

* **Gemini 2.5 Computer Use** (agent loop, Playwright examples, supported actions, model id). ([Google AI for Developers][1])
* **Gemini 2.5 Pro** (multimodal, long-context; great for audio+video alignment). ([Google AI for Developers][2])
* **Region Capture / CropTarget** (crop tab capture to iframe rect). ([MDN Web Docs][3])
* **Playwright web-first assertions** (auto-wait, stability). ([Playwright][6])
* **FastAPI WebSockets** (live step updates & runner frames). ([fastapi.tiangolo.com][5])
* **CDP Page screencast frames** (for the runner viewport). ([chromedevtools.github.io][7])

---

### Tiny bootstrap (just to de-risk “runner viewport”)

* Chromium context at fixed viewport (e.g., 1440×900) as per Computer Use examples. ([Google AI for Developers][1])
* Start run → immediately begin **screencast** (or 500ms screenshots) and push `runner_frame` WS events; FE paints to canvas in the iframe.
* Log **every** Computer Use function_call and the Playwright action you executed (plus normalized→pixel coordinate transform), and emit a **token_usage** event after each turn.
