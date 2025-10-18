# Frontend (Record → Review → Run)

* React + TypeScript + Vite (SPA, timeline editor, runner viewport canvas).
* State/data: Zustand + TanStack Query.
* UI: MUI + emotion.
* Capture APIs: `getDisplayMedia` + **Region Capture** (`CropTarget`) for **iframe-only** video; `getUserMedia({ audio:true })` for narration. (Vite shows `yarn create vite`; Region Capture needs a user gesture + HTTPS/localhost.) ([vitejs][1])
* Runner viewport: an `<iframe>` that paints WS-streamed PNG frames onto a `<canvas>` (~5–10 fps).

# Backend (Orchestrator + Executor)

* Python 3.11+, FastAPI + Uvicorn (HTTP + WebSockets).
* Playwright (Python) + **Chromium** (one context per run).
* Persistence: Postgres (+ SQLAlchemy 2.x async) for Plans/Runs/Artifacts; Redis for ephemeral run state/throttles.

# Models & SDKs (Google)

* **Gemini 2.5 Computer Use** for runtime (screenshot → action → screenshot loop).
* **Gemini 2.5 Pro** for Agent-1 reasoning + post-recording synthesis (audio+frames alignment).
  (Your SDK calls stay the same; only the FE package manager changed.)

---

# Yarn environment setup (recommended)

```bash
# Use Corepack to get modern Yarn (no global npm install)
corepack enable                                   # enables shims
corepack prepare yarn@stable --activate           # or: yarn set version stable
```

(Corepack comes with Node and is enabled via `corepack enable`.) ([nodejs.org][2])

**If a tool doesn’t love PnP yet:** add a `.yarnrc.yml` with:

```yaml
nodeLinker: node-modules
```

(Yarn defaults to PnP; switching to `node-modules` is first-class and often simplest with Vite/dev tooling.) ([yarnpkg.com][3])

---

# Minimal “getting started” (local, Yarn)

## Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn[standard] websockets playwright google-genai SQLAlchemy psycopg[binary] redis
python -m playwright install chromium
# run:
uvicorn app.main:app --reload
```

## Frontend

```bash
# Scaffold with Yarn
yarn create vite show-and-tell --template react-ts    # Vite's official quickstart supports yarn create
cd show-and-tell

# App deps
yarn add @mui/material @emotion/react @emotion/styled zustand @tanstack/react-query

# Dev & test tooling (optional)
yarn add -D vitest @vitest/ui @types/node @types/react @types/react-dom eslint

# Run
yarn dev
```

(Vite docs show `yarn create vite`, plus template flags; `yarn dev` runs the script in package.json.) ([vitejs][1])

**Alternative (Yarn 3/4 universal way):**

```bash
yarn dlx create-vite@latest show-and-tell -- --template react-ts
```

(`yarn dlx` runs a one-off binary in a temp env.) ([yarnpkg.com][4])

---

# Testing & DX with Yarn

* **Vitest** for unit/integration: `yarn test` script.
* **Biome/ESLint** as you had (install with `yarn add -D ...`).
* **Editor SDKs (if using PnP):** `yarn dlx @yarnpkg/sdks` to configure TS/ESLint in your IDE. ([yarnpkg.com][5])

---

# Notes you might care about

* If Corepack/Yarn versions act odd on your machine, re-enable Corepack and avoid globally-installed Yarn; the Yarn team recommends Corepack-managed Yarn. ([yarnpkg.com][6])
* Vite requires modern Node (20.19+ / 22.12+), so ensure Node is up to date before scaffolding. ([vitejs][1])