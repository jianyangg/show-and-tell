import { useCallback, useMemo } from 'react';
import { useAppStore } from '../store/appStore';

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
    planDetail,
    setStatus,
    addConsoleEntry,
    setPlanDetail,
  } = useAppStore((state) => ({
    apiBase: state.apiBase,
    synthProvider: state.synthProvider,
    latestRecording: state.latestRecording,
    planDetail: state.planDetail,
    setStatus: state.setStatus,
    addConsoleEntry: state.addConsoleEntry,
    setPlanDetail: state.setPlanDetail,
  }));

  const providerLabel = PROVIDER_LABELS[synthProvider] ?? synthProvider;

  const synthesizePlan = useCallback(async () => {
    if (!latestRecording) {
      setStatus('Capture a recording before synthesizing.');
      return;
    }
    setStatus(`Requesting plan synthesis via ${providerLabel}…`);
    addConsoleEntry('Synthesizer', `Sending bundle to ${providerLabel}…`);
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, '')}/plans/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recordingId: latestRecording.recordingId,
          planName: 'Captured flow',
          provider: synthProvider,
        }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const detail = await response.json();
      if (detail?.plan && !detail.plan.name) {
        detail.plan.name = DEFAULT_PLAN_NAME;
      }
      setPlanDetail(detail);
      setStatus(`Plan ${detail.planId} ready. Review steps before running.`);
      addConsoleEntry('Synthesizer', `Plan provider: ${providerLabel}`);
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
  }, [
    addConsoleEntry,
    apiBase,
    latestRecording,
    providerLabel,
    setPlanDetail,
    setStatus,
    synthProvider,
  ]);

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
        const response = await fetch(`${apiBase.replace(/\/$/, '')}/plans/${planDetail.planId}/save`, {
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
          const updatedDetail = { ...planDetail, plan: data.plan, planId: planDetail.planId };
          setPlanDetail(updatedDetail);
        }
        addConsoleEntry('Synthesizer', `Plan saved as "${data.name}".`);
        setStatus(`Plan saved as "${data.name}".`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error('Plan save failed', error);
        setStatus(`Plan save failed: ${message}`);
      }
    },
    [addConsoleEntry, apiBase, planDetail, setPlanDetail, setStatus]
  );

  return useMemo(
    () => ({
      synthesizePlan,
      savePlan,
      planDetail,
      providerLabel,
    }),
    [planDetail, providerLabel, savePlan, synthesizePlan]
  );
}
