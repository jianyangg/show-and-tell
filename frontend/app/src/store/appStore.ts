import { create } from 'zustand';

export type SynthProvider = 'gemini' | 'chatgpt';

export interface RecordingFrame {
  timestamp: number;
  png: string;
}

export interface RecordingMarker {
  timestamp: number;
  label: string;
}

export interface EventEntry {
  id: string;
  text: string;
}

export interface ConsoleEntry {
  id: string;
  role: string;
  message: string;
  timestamp: number;
}

export interface CursorPosition {
  x: number;
  y: number;
}

export interface FramePayload {
  png: string;
  cursor?: CursorPosition | null;
}

export interface PlanStep {
  id: string;
  title: string;
  instructions: string;
}

export interface PlanData {
  name: string;
  startUrl?: string | null;
  vars?: Record<string, string | number>;
  steps: PlanStep[];
  hasVariables?: boolean;
}

export interface PlanDetail {
  planId: string;
  recordingId: string;
  plan: PlanData;
  prompt?: string;
  rawResponse?: string;
  createdAt: string;
  updatedAt?: string;
  hasVariables?: boolean;
}

export interface PlanSummary {
  planId: string;
  recordingId: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  hasVariables?: boolean;
}

export type StepStatus = 'idle' | 'active' | 'done';

export interface RecordingDetail {
  recordingId: string;
  frames: RecordingFrame[];
  markers: RecordingMarker[];
  events: unknown[];
}

export interface RecordingSummary {
  recordingId: string;
  title: string | null;
  status: string;
  createdAt: string;
  updatedAt: string;
  endedAt: string | null;
}

export interface PromptState {
  summary: string;
  detail: string;
}

export interface VariableField {
  name: string;
  value: string;
}

export interface VariableRequest {
  fields: VariableField[];
}

interface AppStore {
  apiBase: string;
  startUrl: string;
  synthProvider: SynthProvider;
  status: string;
  consoleEntries: ConsoleEntry[];
  eventEntries: EventEntry[];
  markers: RecordingMarker[];
  recordingFrames: RecordingFrame[];
  latestRecording: RecordingDetail | null;
  planDetail: PlanDetail | null;
  planSummaries: PlanSummary[];
  runStepStatus: Record<string, StepStatus>;
  prompt: PromptState | null;
  runId: string | null;
  isTeachActive: boolean;
  isRecording: boolean;
  teachViewport: { width: number; height: number };
  currentFrame: FramePayload | null;
  recordingStartedAt: number | null;
  pendingPromptPayload: Record<string, unknown> | null;
  variableRequest: VariableRequest | null;
  variableHints: string;
  setApiBase: (value: string) => void;
  setStartUrl: (value: string) => void;
  setSynthProvider: (value: SynthProvider) => void;
  setStatus: (value: string) => void;
  addConsoleEntry: (role: string, message: string) => void;
  clearConsole: () => void;
  setEventEntries: (entries: EventEntry[]) => void;
  setMarkers: (markers: RecordingMarker[]) => void;
  setRecordingFrames: (frames: RecordingFrame[]) => void;
  setLatestRecording: (detail: RecordingDetail | null) => void;
  setPlanDetail: (detail: PlanDetail | null) => void;
  setPlanSummaries: (summaries: PlanSummary[]) => void;
  setRunStepState: (stepId: string, status: StepStatus) => void;
  setPrompt: (prompt: PromptState | null, payload?: Record<string, unknown> | null) => void;
  setRunId: (runId: string | null) => void;
  setTeachActive: (active: boolean) => void;
  setIsRecording: (recording: boolean) => void;
  setTeachViewport: (viewport: { width: number; height: number }) => void;
  setCurrentFrame: (frame: FramePayload | null) => void;
  setRecordingStartedAt: (timestamp: number | null) => void;
  setVariableRequest: (request: VariableRequest | null) => void;
  setVariableHints: (hints: string) => void;
  applyPlanVariables: (vars: Record<string, string | number>) => void;
}

const RESOLVED_BACKEND_PORT = '8000';

function resolveInitialApiBase(): string {
  if (typeof window === 'undefined') {
    return `http://localhost:${RESOLVED_BACKEND_PORT}`;
  }
  const origin = window.location.origin;
  try {
    const url = new URL(origin);
    const isLocalhost =
      url.hostname === 'localhost' || url.hostname === '127.0.0.1' || url.hostname === '0.0.0.0';
    if (isLocalhost && url.port && url.port !== RESOLVED_BACKEND_PORT) {
      return `${url.protocol}//${url.hostname}:${RESOLVED_BACKEND_PORT}`;
    }
    if (isLocalhost && !url.port) {
      return `${url.protocol}//${url.hostname}:${RESOLVED_BACKEND_PORT}`;
    }
    return origin;
  } catch (error) {
    console.warn('Unable to resolve API base from origin, falling back to localhost:8000', error);
    return `http://localhost:${RESOLVED_BACKEND_PORT}`;
  }
}

const initialApiBase = resolveInitialApiBase();
const initialViewport = { width: 1440, height: 900 };

export const useAppStore = create<AppStore>((set, get) => ({
  apiBase: initialApiBase,
  startUrl: 'https://www.google.com',
  synthProvider: 'gemini',
  status: 'Ready to record.',
  consoleEntries: [],
  eventEntries: [],
  markers: [],
  recordingFrames: [],
  latestRecording: null,
  planDetail: null,
  planSummaries: [],
  runStepStatus: {},
  prompt: null,
  runId: null,
  isTeachActive: false,
  isRecording: false,
  teachViewport: initialViewport,
  currentFrame: null,
  recordingStartedAt: null,
  pendingPromptPayload: null,
  variableRequest: null,
  variableHints: '',
  setApiBase: (value) => set({ apiBase: value }),
  setStartUrl: (value) => set({ startUrl: value }),
  setSynthProvider: (value) => set({ synthProvider: value }),
  setStatus: (value) => set({ status: value }),
  addConsoleEntry: (role, message) => {
    const entry: ConsoleEntry = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      role,
      message,
      timestamp: Date.now(),
    };
    set((state) => ({ consoleEntries: [...state.consoleEntries, entry] }));
  },
  clearConsole: () => set({ consoleEntries: [] }),
  setEventEntries: (entries) => set({ eventEntries: entries }),
  setMarkers: (markers) => set({ markers }),
  setRecordingFrames: (frames) => set({ recordingFrames: frames }),
  setLatestRecording: (detail) => set({ latestRecording: detail }),
  setPlanDetail: (detail) => {
    const statuses: Record<string, StepStatus> = {};
    if (detail?.plan?.steps) {
      detail.plan.steps.forEach((step) => {
        statuses[step.id] = 'idle';
      });
    }
    set({ planDetail: detail, runStepStatus: statuses });
  },
  setPlanSummaries: (summaries) => set({ planSummaries: summaries }),
  setRunStepState: (stepId, status) =>
    set((state) => ({
      runStepStatus: { ...state.runStepStatus, [stepId]: status },
    })),
  setPrompt: (prompt, payload = null) => set({ prompt, pendingPromptPayload: payload ?? null }),
  setRunId: (runId) => set({ runId }),
  setTeachActive: (active) => set({ isTeachActive: active }),
  setIsRecording: (recording) => set({ isRecording: recording }),
  setTeachViewport: (viewport) => set({ teachViewport: viewport }),
  setCurrentFrame: (frame) => set({ currentFrame: frame }),
  setRecordingStartedAt: (timestamp) => set({ recordingStartedAt: timestamp }),
  setVariableRequest: (request) => set({ variableRequest: request }),
  setVariableHints: (hints) => set({ variableHints: hints }),
  applyPlanVariables: (vars) =>
    set((state) => {
      if (!state.planDetail?.plan) {
        return {};
      }
      const currentVars = { ...(state.planDetail.plan.vars ?? {}) };
      for (const [key, value] of Object.entries(vars)) {
        currentVars[key] = value;
      }
      const hasVariables =
        state.planDetail.plan.hasVariables ??
        state.planDetail.hasVariables ??
        Object.keys(currentVars).length > 0;
      return {
        planDetail: {
          ...state.planDetail,
          hasVariables: state.planDetail.hasVariables ?? hasVariables,
          plan: {
            ...state.planDetail.plan,
            hasVariables,
            vars: currentVars,
          },
        },
      };
    }),
}));

export const appStoreApi = {
  getState: useAppStore.getState,
};
