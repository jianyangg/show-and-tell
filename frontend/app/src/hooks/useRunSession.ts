import { useCallback, useEffect, useMemo, useRef } from 'react';
import { RecordingMarker, useAppStore } from '../store/appStore';
import { buildEventEntries, RawEvent } from '../utils/events';
import { normalizeStartUrl } from '../utils/startUrl';

function buildRunWsUrl(apiBase: string, runId: string): string {
  const url = new URL(apiBase);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = url.pathname.replace(/\/$/, '') + `/ws/runs/${encodeURIComponent(runId)}`;
  url.search = '';
  return url.toString();
}

export function useRunSession() {
  const runSocketRef = useRef<WebSocket | null>(null);

  const {
    apiBase,
    startUrl,
    planDetail,
    setStatus,
    addConsoleEntry,
    setRunId,
    setRunStepState,
    setPrompt,
    setCurrentFrame,
    setEventEntries,
    setMarkers,
    setVariableRequest,
    applyPlanVariables,
  } = useAppStore((state) => ({
    apiBase: state.apiBase,
    startUrl: state.startUrl,
    planDetail: state.planDetail,
    setStatus: state.setStatus,
    addConsoleEntry: state.addConsoleEntry,
    setRunId: state.setRunId,
    setRunStepState: state.setRunStepState,
    setPrompt: state.setPrompt,
    setCurrentFrame: state.setCurrentFrame,
    setEventEntries: state.setEventEntries,
    setMarkers: state.setMarkers,
    setVariableRequest: state.setVariableRequest,
    applyPlanVariables: state.applyPlanVariables,
  }));

  const closeRunSocket = useCallback(() => {
    const socket = runSocketRef.current;
    if (socket) {
      socket.close();
      runSocketRef.current = null;
    }
    setVariableRequest(null);
  }, [setVariableRequest]);

  const handleRunMessage = useCallback(
    (message: any) => {
      switch (message.type) {
        case 'runner_frame':
          if (message.frame || message.png) {
            setCurrentFrame({ png: message.frame || message.png, cursor: message.cursor });
          }
          break;
        case 'runner_status': {
          const label = message.message || 'Runner update';
          setStatus(label);
          const detail = message.error || message.reason;
          addConsoleEntry('Runner', detail ? `${label}: ${detail}` : label);
          if (['failed', 'aborted', 'completed'].includes(label)) {
            setPrompt(null);
            setVariableRequest(null);
          }
          break;
        }
        case 'step_started':
          if (message.stepId) {
            setRunStepState(message.stepId, 'active');
            addConsoleEntry('Runner', `Step started: ${message.stepId}`);
          }
          break;
        case 'step_completed':
          if (message.stepId) {
            setRunStepState(message.stepId, 'done');
            addConsoleEntry('Runner', `Step completed: ${message.stepId}`);
          }
          break;
        case 'run_completed':
          setStatus(message.ok ? 'Run completed successfully.' : 'Run finished.');
          setPrompt(null);
          setVariableRequest(null);
          addConsoleEntry('Runner', message.ok ? 'Run completed successfully.' : 'Run finished.');
          break;
        case 'safety_prompt': {
          const payload = message.payload || {};
          const summary = `${payload.action || 'action'} ${JSON.stringify(payload.args || {})}`;
          setPrompt(
            {
              summary: 'Allow model-proposed action?',
              detail: `Allow model-proposed ${summary}?`,
            },
            payload
          );
          addConsoleEntry('Runner', 'Safety confirmation required.');
          break;
        }
        case 'variable_prompt': {
          const payload = message.payload || {};
          const vars = Array.isArray(payload?.vars) ? payload.vars : [];
          const fields = vars
            .map((entry: any) => {
              const name = typeof entry?.name === 'string' ? entry.name.trim() : '';
              if (!name) {
                return null;
              }
              const value =
                entry?.value === null || entry?.value === undefined ? '' : String(entry.value);
              return { name, value };
            })
            .filter(Boolean) as { name: string; value: string }[];
          if (fields.length) {
            setVariableRequest({ fields });
            setPrompt(null);
            setStatus('Awaiting variable inputs…');
            addConsoleEntry('Runner', 'Awaiting operator-provided variables.');
          } else {
            addConsoleEntry('Runner', 'Variable prompt received without any fields.');
          }
          break;
        }
        case 'variables_applied': {
          const applied = (message.vars || {}) as Record<string, string | number>;
          setVariableRequest(null);
          applyPlanVariables(applied);
          const parts = Object.entries(applied).map(
            ([name, value]) => `${name}=${String(value ?? '')}`
          );
          addConsoleEntry(
            'Runner',
            parts.length ? `Variables applied: ${parts.join(', ')}` : 'Variables applied.'
          );
          break;
        }
        case 'console': {
          const role = message.role || 'Log';
          const content = message.message || '';
          addConsoleEntry(role, content);
          break;
        }
        case 'event_log':
          setEventEntries(buildEventEntries((message.events || []) as RawEvent[]));
          break;
        case 'markers':
          setMarkers((message.markers || []) as RecordingMarker[]);
          break;
        default:
          break;
      }
    },
    [
      addConsoleEntry,
      applyPlanVariables,
      setCurrentFrame,
      setEventEntries,
      setMarkers,
      setPrompt,
      setRunStepState,
      setStatus,
      setVariableRequest,
    ]
  );

  const connectToRun = useCallback(
    (runId: string) => {
      closeRunSocket();
      const url = buildRunWsUrl(apiBase, runId);
      const socket = new WebSocket(url);
      runSocketRef.current = socket;

      socket.addEventListener('open', () => {
        setStatus(`Connected to run ${runId}.`);
        addConsoleEntry('Runner', `Connected to ${url}`);
      });

      socket.addEventListener('message', (event) => {
        try {
          const data = JSON.parse(event.data);
          handleRunMessage(data);
        } catch (error) {
          console.error('Malformed runner message', error);
        }
      });

      socket.addEventListener('close', () => {
        setStatus('Run connection closed.');
        addConsoleEntry('Runner', 'Connection closed.');
        runSocketRef.current = null;
        setPrompt(null);
        setVariableRequest(null);
      });

      socket.addEventListener('error', () => {
        setStatus('Run connection error.');
        addConsoleEntry('Runner', 'Connection error.');
        setVariableRequest(null);
      });
    },
    [
      addConsoleEntry,
      apiBase,
      closeRunSocket,
      handleRunMessage,
      setPrompt,
      setStatus,
      setVariableRequest,
    ]
  );

  const startRun = useCallback(async () => {
    if (!planDetail) {
      setStatus('Generate a plan first.');
      return;
    }
    setPrompt(null);
    setVariableRequest(null);
    if (planDetail.plan?.steps) {
      planDetail.plan.steps.forEach((step) => setRunStepState(step.id, 'idle'));
    }
    addConsoleEntry('Runner', `Launching plan ${planDetail.planId}`);
    setStatus('Starting run…');
    try {
      const preparedVars: Record<string, string | number> = {};
      const planVars = planDetail.plan?.vars ?? {};
      Object.entries(planVars).forEach(([name, rawValue]) => {
        if (!name) return;
        if (rawValue === null || rawValue === undefined) {
          return;
        }
        if (typeof rawValue === 'string') {
          const trimmed = rawValue.trim();
          if (!trimmed) {
            return;
          }
          preparedVars[name] = trimmed;
          return;
        }
        preparedVars[name] = rawValue;
      });
      const payload: Record<string, unknown> = {
        planId: planDetail.planId,
        startUrl: normalizeStartUrl(startUrl),
      };
      if (Object.keys(preparedVars).length > 0) {
        payload.variables = preparedVars;
      }
      const response = await fetch(`${apiBase.replace(/\/$/, '')}/runs/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const data = await response.json();
      const runId: string = data.runId;
      setRunId(runId);
      connectToRun(runId);
      setStatus(`Run ${runId} launched.`);
      addConsoleEntry('Runner', `Run ${runId} launched.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error('Run start failed', error);
      setStatus(`Run failed to start: ${message}`);
      addConsoleEntry('Runner', `Run failed to start: ${message}`);
    }
  }, [
    addConsoleEntry,
    apiBase,
    connectToRun,
    planDetail,
    setPrompt,
    setRunId,
    setRunStepState,
    setStatus,
    setVariableRequest,
    startUrl,
  ]);

  const confirmPrompt = useCallback(
    (allow: boolean) => {
      const socket = runSocketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'confirm_action', allow }));
      }
      setPrompt(null);
    },
    [setPrompt]
  );

  const submitVariables = useCallback(
    (values: Record<string, string>) => {
      const socket = runSocketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'submit_variables', values }));
        addConsoleEntry('Runner', 'Submitted variable values.');
        setStatus('Variables submitted. Resuming run…');
      } else {
        addConsoleEntry('Runner', 'Unable to submit variables: no active run connection.');
        setStatus('Unable to submit variables (no active run).');
      }
      setVariableRequest(null);
    },
    [addConsoleEntry, setStatus, setVariableRequest]
  );

  const abortVariables = useCallback(() => {
    const socket = runSocketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'abort' }));
    }
    addConsoleEntry('Runner', 'Abort requested while waiting for variables.');
    setStatus('Abort requested.');
    setVariableRequest(null);
    setPrompt(null);
  }, [addConsoleEntry, setPrompt, setStatus, setVariableRequest]);

  useEffect(() => {
    return () => {
      closeRunSocket();
    };
  }, [closeRunSocket]);

  return useMemo(
    () => ({
      startRun,
      confirmPrompt,
      submitVariables,
      abortVariables,
      connectToRun,
    }),
    [abortVariables, confirmPrompt, connectToRun, startRun, submitVariables]
  );
}
