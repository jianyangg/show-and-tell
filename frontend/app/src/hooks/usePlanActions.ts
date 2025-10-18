import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useAppStore } from '../store/appStore';
import type { PlanSummary } from '../store/appStore';
import { normalizeStartUrl } from '../utils/startUrl';

const PROVIDER_LABELS: Record<string, string> = {
  gemini: 'Gemini 2.5 Pro',
  chatgpt: 'ChatGPT 5',
};

const DEFAULT_PLAN_NAME = 'Unnamed plan';

export function usePlanActions() {
  const {
    apiBase,
    synthProvider,
    latestRecording,
    startUrl,
    planDetail,
    planSummaries,
    variableHints,
    setStatus,
    addConsoleEntry,
    setPlanDetail,
    setPlanSummaries,
    setApiBase,
    setStartUrl,
  } = useAppStore((state) => ({
    apiBase: state.apiBase,
    synthProvider: state.synthProvider,
    latestRecording: state.latestRecording,
    startUrl: state.startUrl,
    planDetail: state.planDetail,
    planSummaries: state.planSummaries,
    variableHints: state.variableHints,
    setStatus: state.setStatus,
    addConsoleEntry: state.addConsoleEntry,
    setPlanDetail: state.setPlanDetail,
    setPlanSummaries: state.setPlanSummaries,
    setApiBase: state.setApiBase,
    setStartUrl: state.setStartUrl,
  }));

  const providerLabel = PROVIDER_LABELS[synthProvider] ?? synthProvider;
  const apiRoot = useMemo(() => apiBase.replace(/\/$/, ''), [apiBase]);
  const fallbackAttemptedRef = useRef(false);

  useEffect(() => {
    fallbackAttemptedRef.current = false;
  }, [apiRoot]);

  const fallbackApiBase = useMemo(() => {
    if (!apiRoot || apiRoot === 'http://localhost:8000') {
      return null;
    }
    try {
      const url = new URL(apiRoot);
      if (
        (url.hostname === 'localhost' || url.hostname === '127.0.0.1') &&
        url.port !== '8000'
      ) {
        url.port = '8000';
        return url.origin;
      }
    } catch (error) {
      console.warn('Unable to determine fallback API base', error);
    }
    return null;
  }, [apiRoot]);

  const refreshPlans = useCallback(async () => {
    try {
      const response = await fetch(`${apiRoot}/plans`);
      // If the primary API base isn't serving /plans (e.g., you're on a static server),
      // switch to the fallback (usually http://localhost:8000) once.
      if (!response.ok && fallbackApiBase && !fallbackAttemptedRef.current && fallbackApiBase !== apiRoot) {
        fallbackAttemptedRef.current = true;
        console.info(
          `Got ${response.status} from ${apiRoot}/plans, switching API base to ${fallbackApiBase}`
        );
        setStatus(`Switching API base to ${fallbackApiBase}…`);
        setApiBase(fallbackApiBase);
        return;
      }
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const isJson = response.headers.get('content-type')?.includes('application/json') ?? false;
      if (!isJson) {
        const text = await response.text();
        const looksHtml = text.trimStart().startsWith('<!DOCTYPE');
        if (
          looksHtml &&
          !fallbackAttemptedRef.current &&
          fallbackApiBase &&
          fallbackApiBase !== apiRoot
        ) {
          fallbackAttemptedRef.current = true;
          console.info(
            `Received HTML when loading plans from ${apiRoot}, switching API base to ${fallbackApiBase}`
          );
          setStatus(`Switching API base to ${fallbackApiBase}…`);
          setApiBase(fallbackApiBase);
          return;
        }
        throw new Error(text ? text.slice(0, 200) : 'Non-JSON response');
      }
      const payload = await response.json();
      if (!payload || typeof payload !== 'object') {
        throw new Error('Malformed plan list payload');
      }
      const summaries = Array.isArray((payload as { plans?: unknown }).plans)
        ? ((payload as { plans: PlanSummary[] }).plans ?? [])
        : [];
      setPlanSummaries(summaries);
    } catch (error) {
      // Network/CORS failure: try fallback API base once
      if (!fallbackAttemptedRef.current && fallbackApiBase && fallbackApiBase !== apiRoot) {
        fallbackAttemptedRef.current = true;
        console.info(
          `Network error fetching ${apiRoot}/plans, switching API base to ${fallbackApiBase}`
        );
        setStatus(`Switching API base to ${fallbackApiBase}…`);
        setApiBase(fallbackApiBase);
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      console.error('Failed to load saved plans', error);
      const looksHtml = message.includes('<!DOCTYPE');
      const shortMessage = looksHtml ? 'HTML response received' : message;
      const hint =
        looksHtml || fallbackApiBase
          ? ' Ensure the API base points to the FastAPI server (e.g. http://localhost:8000).'
          : '';
      setStatus(`Failed to load saved plans: ${shortMessage}.${hint}`);
    }
  }, [apiRoot, fallbackApiBase, setApiBase, setPlanSummaries, setStatus]);

  const loadPlan = useCallback(
    async (planId: string) => {
      if (!planId) {
        return;
      }
      setStatus(`Loading plan ${planId}…`);
      try {
        const response = await fetch(`${apiRoot}/plans/${planId}`);
        if (!response.ok && fallbackApiBase && !fallbackAttemptedRef.current && fallbackApiBase !== apiRoot) {
          fallbackAttemptedRef.current = true;
          console.info(
            `Got ${response.status} from ${apiRoot}/plans/${planId}, switching API base to ${fallbackApiBase}`
          );
          setStatus(`Switching API base to ${fallbackApiBase}…`);
          setApiBase(fallbackApiBase);
          return;
        }
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const isJson = response.headers.get('content-type')?.includes('application/json') ?? false;
        if (!isJson) {
          const text = await response.text();
          const looksHtml = text.trimStart().startsWith('<!DOCTYPE');
          if (
            looksHtml &&
            !fallbackAttemptedRef.current &&
            fallbackApiBase &&
            fallbackApiBase !== apiRoot
          ) {
            fallbackAttemptedRef.current = true;
            console.info(
              `Received HTML when loading plan ${planId} from ${apiRoot}, switching API base to ${fallbackApiBase}`
            );
            setStatus(`Switching API base to ${fallbackApiBase}…`);
            setApiBase(fallbackApiBase);
            return;
          }
          throw new Error(text ? text.slice(0, 200) : 'Non-JSON response from server');
        }
        const detail = await response.json();
        if (detail?.plan && !detail.plan.name) {
          detail.plan.name = DEFAULT_PLAN_NAME;
        }
        setPlanDetail(detail);
        const planStart = typeof detail?.plan?.startUrl === 'string' ? detail.plan.startUrl : '';
        setStartUrl(planStart);
        const hasVariables = Boolean(detail.hasVariables || detail.plan?.hasVariables);
        const planName = detail.plan?.name ?? planId;
        const statusMessage = hasVariables
          ? `Loaded plan "${planName}". Variables will be requested before running.`
          : `Loaded plan "${planName}".`;
        setStatus(statusMessage);
        addConsoleEntry(
          'Plans',
          hasVariables
            ? `Loaded plan ${planId} (variables required).`
            : `Loaded plan ${planId}`
        );
      } catch (error) {
        if (!fallbackAttemptedRef.current && fallbackApiBase && fallbackApiBase !== apiRoot) {
          fallbackAttemptedRef.current = true;
          console.info(
            `Network error fetching ${apiRoot}/plans/${planId}, switching API base to ${fallbackApiBase}`
          );
          setStatus(`Switching API base to ${fallbackApiBase}…`);
          setApiBase(fallbackApiBase);
          return;
        }
      const message = error instanceof Error ? error.message : String(error);
      console.error('Plan load failed', error);
      const looksHtml = message.includes('<!DOCTYPE');
      const shortMessage = looksHtml ? 'HTML response received' : message;
      const hint =
        looksHtml || fallbackApiBase
          ? ' Ensure the API base points to the FastAPI server (e.g. http://localhost:8000).'
          : '';
      setStatus(`Failed to load plan: ${shortMessage}.${hint}`);
    }
  }, [addConsoleEntry, apiRoot, fallbackApiBase, setApiBase, setPlanDetail, setStartUrl, setStatus]);

  const synthesizePlan = useCallback(async () => {
    if (!latestRecording) {
      setStatus('Capture a recording before synthesizing.');
      return;
    }
    setStatus(`Requesting plan synthesis via ${providerLabel}…`);
    addConsoleEntry('Synthesizer', `Sending bundle to ${providerLabel}…`);
    try {
      const payload: Record<string, any> = {
        recordingId: latestRecording.recordingId,
        planName: 'Captured flow',
        provider: synthProvider,
        startUrl: normalizeStartUrl(startUrl),
      };

      // Include variable hints if provided
      if (variableHints.trim()) {
        payload.variableHints = variableHints.trim();
      }

      const response = await fetch(`${apiRoot}/plans/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const detail = await response.json();
      if (detail?.plan && !detail.plan.name) {
        detail.plan.name = DEFAULT_PLAN_NAME;
      }
      setPlanDetail(detail);
      const planStart = typeof detail?.plan?.startUrl === 'string' ? detail.plan.startUrl : '';
      setStartUrl(planStart);
      const hasVariables = Boolean(detail.hasVariables || detail.plan?.hasVariables);
      const statusMessage = hasVariables
        ? `Plan ${detail.planId} ready. Variables will be requested before running.`
        : `Plan ${detail.planId} ready. Review steps before running.`;
      setStatus(statusMessage);
      addConsoleEntry('Synthesizer', `Plan provider: ${providerLabel}`);
      if (hasVariables) {
        const varNames = Object.keys(detail.plan?.vars || {});
        addConsoleEntry(
          'Synthesizer',
          varNames.length
            ? `Plan variables detected: ${varNames.join(', ')}`
            : 'Plan includes unresolved variables.'
        );
      }
      if (detail.prompt) {
        addConsoleEntry('Synthesizer prompt', detail.prompt);
        console.info('Plan synthesis prompt:\n', detail.prompt);
      }
      if (detail.rawResponse) {
        addConsoleEntry('Synthesizer response', detail.rawResponse);
        console.info('Plan synthesis raw response:\n', detail.rawResponse);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error('Plan synthesis failed', error);
      setStatus(`Plan synthesis failed (${providerLabel}): ${message}`);
      addConsoleEntry('Synthesizer', `Failed (${providerLabel}): ${message}`);
    }
  }, [addConsoleEntry, apiRoot, latestRecording, providerLabel, setPlanDetail, setStartUrl, setStatus, startUrl, synthProvider, variableHints]);

  const savePlan = useCallback(
    async (name: string) => {
      if (!planDetail) {
        setStatus('Generate a plan before saving.');
        return;
      }
      const trimmed = name.trim();
      if (!trimmed) {
        setStatus('Enter a plan name before saving.');
        return;
      }
      try {
        const response = await fetch(`${apiRoot}/plans/${planDetail.planId}/save`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: trimmed,
            plan: planDetail.plan || null,
          }),
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const data = await response.json();
        if (planDetail) {
          const planHasVariables = Boolean(
            data.hasVariables ?? data.plan?.hasVariables ?? planDetail.hasVariables
          );
          const updatedDetail = {
            ...planDetail,
            hasVariables: planHasVariables,
            plan: {
              ...data.plan,
              name: data.name,
              hasVariables: data.plan?.hasVariables ?? planHasVariables,
            },
            planId: planDetail.planId,
            updatedAt: data.updatedAt,
          };
          setPlanDetail(updatedDetail);
        }
        addConsoleEntry('Synthesizer', `Plan saved as "${data.name}".`);
        setStatus(`Plan saved as "${data.name}".`);
        refreshPlans().catch((error) => {
          console.warn('Unable to refresh plan list after save', error);
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error('Plan save failed', error);
        setStatus(`Plan save failed: ${message}`);
      }
    },
    [addConsoleEntry, apiRoot, planDetail, refreshPlans, setPlanDetail, setStatus]
  );

  useEffect(() => {
    refreshPlans().catch((error) => {
      console.warn('Initial plan refresh failed', error);
    });
  }, [refreshPlans]);

  return useMemo(
    () => ({
      synthesizePlan,
      savePlan,
      planDetail,
      providerLabel,
      planSummaries,
      refreshPlans,
      loadPlan,
    }),
    [planDetail, planSummaries, providerLabel, savePlan, synthesizePlan, refreshPlans, loadPlan]
  );
}
