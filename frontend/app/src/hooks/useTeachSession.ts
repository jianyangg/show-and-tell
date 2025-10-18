import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  RecordingMarker,
  RecordingFrame,
  useAppStore,
  appStoreApi,
} from '../store/appStore';
import { buildEventEntries, RawEvent } from '../utils/events';
import { normalizeStartUrl } from '../utils/startUrl';

function buildTeachWsUrl(apiBase: string, teachId: string): string {
  const url = new URL(apiBase);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = url.pathname.replace(/\/$/, '') + `/ws/teach/${encodeURIComponent(teachId)}`;
  url.search = '';
  return url.toString();
}

export function useTeachSession(canvasRef: React.RefObject<HTMLCanvasElement>) {
  const teachSocketRef = useRef<WebSocket | null>(null);
  const detachListenersRef = useRef<(() => void) | null>(null);
  const markersRef = useRef<RecordingMarker[]>([]);
  const recordingFramesRef = useRef<RecordingFrame[]>([]);

  const {
    apiBase,
    startUrl,
    setStatus,
    clearConsole,
    addConsoleEntry,
    setTeachActive,
    setTeachViewport,
    setMarkers,
    setRecordingFrames,
    setEventEntries,
    setCurrentFrame,
    setIsRecording,
    setRecordingStartedAt,
    setLatestRecording,
    setPlanDetail,
    isRecording,
  } = useAppStore((state) => ({
    apiBase: state.apiBase,
    startUrl: state.startUrl,
    setStatus: state.setStatus,
    clearConsole: state.clearConsole,
    addConsoleEntry: state.addConsoleEntry,
    setTeachActive: state.setTeachActive,
    setTeachViewport: state.setTeachViewport,
    setMarkers: state.setMarkers,
    setRecordingFrames: state.setRecordingFrames,
    setEventEntries: state.setEventEntries,
    setCurrentFrame: state.setCurrentFrame,
    setIsRecording: state.setIsRecording,
    setRecordingStartedAt: state.setRecordingStartedAt,
    setLatestRecording: state.setLatestRecording,
    setPlanDetail: state.setPlanDetail,
    isRecording: state.isRecording,
  }));

  const attachTeachListeners = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return () => undefined;
    }
    canvas.tabIndex = 0;
    const send = (type: string, payload: Record<string, unknown> = {}) => {
      const socket = teachSocketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type, ...payload }));
      }
    };

    const sendDomProbe = (x: number, y: number, reason: string) => {
      const socket = teachSocketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'probe_dom', x, y, reason }));
      }
    };

    // NOTE: We cannot resolve DOM nodes from a remote screenshot canvas.
    // The 'probe_dom' message asks the backend (Playwright) to run elementFromPoint
    // and respond with metadata (tag/id/classes/role/aria/text/selector).

    const canvasXYToViewport = (clientX: number, clientY: number) => {
      const { width, height } = appStoreApi.getState().teachViewport;
      const rect = canvas.getBoundingClientRect();
      const x = ((clientX - rect.left) / rect.width) * width;
      const y = ((clientY - rect.top) / rect.height) * height;
      return {
        x: Math.max(0, Math.min(width, x)),
        y: Math.max(0, Math.min(height, y)),
      };
    };
    const onMouseDown = (event: MouseEvent) => {
      const { x, y } = canvasXYToViewport(event.clientX, event.clientY);
      send('mouse_down', { x, y, button: event.button });
      event.preventDefault();
    };
    const onMouseUp = (event: MouseEvent) => {
      const { x, y } = canvasXYToViewport(event.clientX, event.clientY);
      send('mouse_up', { x, y, button: event.button });
      // Ask backend to resolve DOM target for better action synthesis
      sendDomProbe(x, y, 'mouse_up');
      event.preventDefault();
    };
    const onMouseMove = (event: MouseEvent) => {
      const { x, y } = canvasXYToViewport(event.clientX, event.clientY);
      send('mouse_move', { x, y });
    };
    const onWheel = (event: WheelEvent) => {
      const { x, y } = canvasXYToViewport(event.clientX, event.clientY);
      send('wheel', { x, y, deltaX: event.deltaX, deltaY: event.deltaY });
      event.preventDefault();
    };
    const isMarkerHotkey = (event: KeyboardEvent) =>
      event.key.toLowerCase() === 'm' && (event.metaKey || event.ctrlKey);
    const onKeyDown = (event: KeyboardEvent) => {
      if (isMarkerHotkey(event)) return;
      send('key_down', {
        key: event.key,
        code: event.code,
        alt: event.altKey,
        ctrl: event.ctrlKey,
        meta: event.metaKey,
        shift: event.shiftKey,
      });
      event.preventDefault();
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (isMarkerHotkey(event)) return;
      send('key_up', {
        key: event.key,
        code: event.code,
        alt: event.altKey,
        ctrl: event.ctrlKey,
        meta: event.metaKey,
        shift: event.shiftKey,
      });
      event.preventDefault();
    };

    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('keydown', onKeyDown);
    canvas.addEventListener('keyup', onKeyUp);

    return () => {
      canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('keydown', onKeyDown);
      canvas.removeEventListener('keyup', onKeyUp);
    };
  }, [canvasRef]);

  const addMarker = useCallback(() => {
    const startedAt = appStoreApi.getState().recordingStartedAt;
    if (!startedAt) return;
    const timestamp = (performance.now() - startedAt) / 1000;
    const marker: RecordingMarker = {
      timestamp: Number(timestamp.toFixed(3)),
      label: `Marker ${markersRef.current.length + 1}`,
    };
    markersRef.current = [...markersRef.current, marker];
    setMarkers(markersRef.current);
    setStatus(`Marked ${marker.label}`);
  }, [setMarkers, setStatus]);

  const markerHotkeyListener = useCallback(
    (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'm' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        addMarker();
      }
    },
    [addMarker]
  );

  const cleanupTeach = useCallback(() => {
    const socket = teachSocketRef.current;
    if (socket) {
      socket.close();
      teachSocketRef.current = null;
    }
    const detach = detachListenersRef.current;
    if (detach) {
      detach();
      detachListenersRef.current = null;
    }
    window.removeEventListener('keydown', markerHotkeyListener);
    setTeachActive(false);
    setIsRecording(false);
  }, [markerHotkeyListener, setIsRecording, setTeachActive]);

  const startTeach = useCallback(async () => {
    setPlanDetail(null);
    clearConsole();
    setStatus('Starting teach session…');
    try {
      const payload = { startUrl: normalizeStartUrl(startUrl) };
      const response = await fetch(`${apiBase.replace(/\/$/, '')}/teach/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const { teachId, viewport, recordingId } = await response.json();
      if (viewport?.width && viewport?.height) {
        setTeachViewport(viewport);
      } else {
        setTeachViewport({ width: 1440, height: 900 });
      }
      if (recordingId) {
        addConsoleEntry('Teach', `Recording id ${recordingId}`);
      }
      markersRef.current = [];
      recordingFramesRef.current = [];
      setRecordingFrames([]);
      setMarkers([]);
      setEventEntries([{ id: 'empty', text: 'No events yet.' }]);
      setCurrentFrame(null);
      setLatestRecording(null);
      setRecordingStartedAt(performance.now());
      setTeachActive(true);
      setIsRecording(true);
      const socketUrl = buildTeachWsUrl(apiBase, teachId);
      const socket = new WebSocket(socketUrl);
      teachSocketRef.current = socket;
      detachListenersRef.current = attachTeachListeners();
      window.addEventListener('keydown', markerHotkeyListener);

      socket.addEventListener('open', () => {
        setStatus(`Teaching… (${teachId})`);
        addConsoleEntry('Teach', `Connected to ${teachId}`);
        canvasRef.current?.focus();
      });

      socket.addEventListener('message', (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'runner_frame' && message.frame) {
            setCurrentFrame({ png: message.frame || message.png, cursor: message.cursor });
          } else if (message.type === 'event_log') {
            const entries = buildEventEntries((message.events || []) as RawEvent[]);
            setEventEntries(entries);
          } else if (message.type === 'dom_probe' && message.target) {
            try {
              const t = message.target as {
                tag?: string; id?: string; class?: string;
                role?: string; name?: string; ariaLabel?: string; text?: string;
                selector?: string; xpath?: string;
              };
              const tag = (t.tag || '').toLowerCase();
              const id = t.id ? `#${t.id}` : '';
              const cls = t.class ? '.' + String(t.class).trim().split(/\s+/).slice(0, 2).join('.') : '';
              const role = t.role ? ` [role=${t.role}]` : '';
              const nameish = t.name || t.ariaLabel || '';
              const text = t.text ? ` "${String(t.text).trim().slice(0, 60)}"` : '';
              const sel = t.selector ? ` selector=${t.selector}` : (t.xpath ? ` xpath=${t.xpath}` : '');
              addConsoleEntry('Target', `${tag}${id}${cls}${role}${text}${nameish ? ' name=' + nameish : ''}${sel ? ' ' + sel : ''}`.trim());
            } catch (e) {
              // Fallback: raw dump
              addConsoleEntry('Target', `DOM target: ${JSON.stringify(message.target)}`);
            }
          } else if (message.type === 'status') {
            setStatus(message.message || 'Teach update');
          }
        } catch (error) {
          console.error('Malformed teach message', error);
        }
      });

      socket.addEventListener('close', () => {
        setStatus('Teach session closed.');
        cleanupTeach();
      });

      socket.addEventListener('error', () => {
        setStatus('Teach session error.');
        addConsoleEntry('Teach', 'Connection error.');
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus(`Failed to start teach session: ${message}`);
      addConsoleEntry('Teach', `Failed: ${message}`);
      cleanupTeach();
    }
  }, [
    apiBase,
    attachTeachListeners,
    addConsoleEntry,
    canvasRef,
    clearConsole,
    cleanupTeach,
    markerHotkeyListener,
    setCurrentFrame,
    setEventEntries,
    setIsRecording,
    setLatestRecording,
    setMarkers,
    setPlanDetail,
    setRecordingFrames,
    setRecordingStartedAt,
    setStatus,
    setTeachActive,
    setTeachViewport,
    startUrl,
  ]);

  const stopTeach = useCallback(async () => {
    setStatus('Stopping teach session…');
    try {
      cleanupTeach();
      const response = await fetch(`${apiBase.replace(/\/$/, '')}/teach/stop`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const detail = (await response.json()) as {
        recordingId: string;
        frames?: RecordingFrame[];
        markers?: RecordingMarker[];
        events?: RawEvent[];
      };
      setLatestRecording({
        recordingId: detail.recordingId,
        frames: detail.frames ?? [],
        markers: detail.markers ?? [],
        events: detail.events ?? [],
      });
      recordingFramesRef.current = detail.frames ?? [];
      setRecordingFrames(recordingFramesRef.current);
      const markers =
        markersRef.current.length > 0
          ? markersRef.current
          : detail.markers ?? [];
      markersRef.current = markers;
      setMarkers(markers);
      setEventEntries(buildEventEntries((detail.events ?? []) as RawEvent[]));
      const savedCount = recordingFramesRef.current.length;
      setStatus(`Recording ${detail.recordingId} saved (${savedCount} frames).`);
      addConsoleEntry('Teach', `Recording ${detail.recordingId} saved.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus(`Failed to stop teach session: ${message}`);
    } finally {
      setRecordingStartedAt(null);
      setIsRecording(false);
      setTeachActive(false);
    }
  }, [
    addConsoleEntry,
    apiBase,
    cleanupTeach,
    setEventEntries,
    setIsRecording,
    setLatestRecording,
    setMarkers,
    setRecordingFrames,
    setRecordingStartedAt,
    setStatus,
    setTeachActive,
  ]);

  useEffect(() => {
    return () => {
      cleanupTeach();
    };
  }, [cleanupTeach]);

  return useMemo(
    () => ({
      startTeach,
      stopTeach,
      addMarker,
      isRecording,
    }),
    [addMarker, isRecording, startTeach, stopTeach]
  );
}
