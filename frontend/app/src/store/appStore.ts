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
  instructions?: string;
}

export interface PlanData {
  name: string;
  steps: PlanStep[];
}

export interface PlanDetail {
  planId: string;
  plan: PlanData;
  prompt?: string;
  rawResponse?: string;
}

export type StepStatus = 'idle' | 'active' | 'done';

export interface RecordingDetail {
  recordingId: string;
  frames: RecordingFrame[];
  markers: RecordingMarker[];
  events: unknown[];
}

export interface PromptState {
  summary: string;
  detail: string;
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
  runStepStatus: Record<string, StepStatus>;
  prompt: PromptState | null;
  runId: string | null;
  isTeachActive: boolean;
  isRecording: boolean;
  teachViewport: { width: number; height: number };
  currentFrame: FramePayload | null;
  recordingStartedAt: number | null;
  pendingPromptPayload: Record<string, unknown> | null;
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
  setRunStepState: (stepId: string, status: StepStatus) => void;
  setPrompt: (prompt: PromptState | null, payload?: Record<string, unknown> | null) => void;
  setRunId: (runId: string | null) => void;
  setTeachActive: (active: boolean) => void;
  setIsRecording: (recording: boolean) => void;
  setTeachViewport: (viewport: { width: number; height: number }) => void;
  setCurrentFrame: (frame: FramePayload | null) => void;
  setRecordingStartedAt: (timestamp: number | null) => void;
}

const initialViewport = { width: 1440, height: 900 };

export const useAppStore = create<AppStore>((set, get) => ({
  apiBase: typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000',
  startUrl: '',
  synthProvider: 'gemini',
  status: 'Ready to record.',
  consoleEntries: [],
  eventEntries: [],
  markers: [],
  recordingFrames: [],
  latestRecording: null,
  planDetail: null,
  runStepStatus: {},
  prompt: null,
  runId: null,
  isTeachActive: false,
  isRecording: false,
  teachViewport: initialViewport,
  currentFrame: null,
  recordingStartedAt: null,
  pendingPromptPayload: null,
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
}));

export const appStoreApi = {
  getState: useAppStore.getState,
};
