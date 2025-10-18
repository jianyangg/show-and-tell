import { RefObject, useEffect, useMemo, useState } from 'react';
import {
  Paper,
  Typography,
  Stack,
  Box,
  Divider,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from '@mui/material';
import { SelectChangeEvent } from '@mui/material/Select';
import { styled } from '../stitches.config';
import {
  ConsoleEntry,
  EventEntry,
  FramePayload,
  PromptState,
  useAppStore,
  VariableRequest,
} from '../store/appStore';
import { drawFrameToCanvas } from '../utils/canvas';
import { buildEventEntries, RawEvent } from '../utils/events';

const ViewerCard = styled(Paper, {
  background: 'rgba(15, 23, 42, 0.75)',
  borderRadius: '16px',
  border: '1px solid rgba(148, 163, 184, 0.2)',
  padding: '$6',
  display: 'flex',
  flexDirection: 'column',
  gap: '$5',
  boxShadow: '0 16px 40px rgba(15, 23, 42, 0.45)',
});

const CanvasBox = styled('div', {
  width: '100%',
  position: 'relative',
  borderRadius: '14px',
  overflow: 'hidden',
  border: '1px solid rgba(148, 163, 184, 0.2)',
  background: 'radial-gradient(circle at 25% 25%, rgba(51, 65, 85, 0.4), rgba(15, 23, 42, 0.8))',
});

const RecordingSelectorOverlay = styled('div', {
  position: 'absolute',
  top: '$4',
  left: '$4',
  zIndex: 10,
  minWidth: '220px',
});

const StatusText = styled(Typography, {
  color: 'rgba(148, 197, 255, 0.85)',
  fontSize: '0.95rem',
  minHeight: '1.5rem',
});

const Panel = styled(Paper, {
  background: 'rgba(15, 23, 42, 0.6)',
  borderRadius: '12px',
  border: '1px solid rgba(148, 163, 184, 0.25)',
  padding: '$4',
  maxHeight: '240px',
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: '$3',
});

const ConsoleText = styled(Typography, {
  fontSize: '0.8rem',
  lineHeight: 1.35,
  color: 'rgba(226, 232, 240, 0.85)',
  wordBreak: 'break-word',
});

const EventText = styled(Typography, {
  fontSize: '0.75rem',
  lineHeight: 1.3,
  color: 'rgba(226, 232, 240, 0.85)',
  wordBreak: 'break-word',
});

const PromptOverlay = styled('div', {
  position: 'absolute',
  bottom: '$6',
  left: '$6',
  right: '$6',
  background: 'rgba(15, 23, 42, 0.92)',
  borderRadius: '12px',
  border: '1px solid rgba(148, 163, 184, 0.3)',
  padding: '$5',
  display: 'flex',
  flexDirection: 'column',
  gap: '$4',
  boxShadow: '0 18px 35px rgba(15, 23, 42, 0.6)',
});

const VariableOverlay = styled(PromptOverlay, {
  gap: '$3',
});

const CanvasElement = styled('canvas', {
  width: '100%',
  aspectRatio: '16 / 10',
});

interface RecordingSummary {
  recordingId: string;
  title: string | null;
  status: string;
  createdAt: string;
  updatedAt: string;
  endedAt: string | null;
}

interface ViewerSectionProps {
  canvasRef: RefObject<HTMLCanvasElement>;
  status: string;
  consoleEntries: ConsoleEntry[];
  eventEntries: EventEntry[];
  currentFrame: FramePayload | null;
  prompt: PromptState | null;
  onConfirmPrompt: (allow: boolean) => void;
  variableRequest: VariableRequest | null;
  onSubmitVariables: (values: Record<string, string>) => void;
  onAbortVariables: () => void;
}

export function ViewerSection({
  canvasRef,
  status,
  consoleEntries,
  eventEntries,
  currentFrame,
  prompt,
  onConfirmPrompt,
  variableRequest,
  onSubmitVariables,
  onAbortVariables,
}: ViewerSectionProps) {
  const {
    teachViewport,
    apiBase,
    latestRecording,
    setLatestRecording,
    setRecordingFrames,
    setMarkers,
    setEventEntries,
    setCurrentFrame,
  } = useAppStore((state) => ({
    teachViewport: state.teachViewport,
    apiBase: state.apiBase,
    latestRecording: state.latestRecording,
    setLatestRecording: state.setLatestRecording,
    setRecordingFrames: state.setRecordingFrames,
    setMarkers: state.setMarkers,
    setEventEntries: state.setEventEntries,
    setCurrentFrame: state.setCurrentFrame,
  }));
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [variableError, setVariableError] = useState('');
  const [recordings, setRecordings] = useState<RecordingSummary[]>([]);
  const [selectedRecordingId, setSelectedRecordingId] = useState<string>('new');

  // Fetch recordings list on mount and when latestRecording changes
  useEffect(() => {
    const fetchRecordings = async () => {
      try {
        const response = await fetch(`${apiBase}/recordings`);
        if (response.ok) {
          const data = await response.json();
          setRecordings(data.recordings || []);
        }
      } catch (error) {
        console.error('Failed to fetch recordings:', error);
      }
    };
    fetchRecordings();
  }, [apiBase, latestRecording]);

  // Update selected recording when latestRecording changes
  useEffect(() => {
    if (latestRecording?.recordingId) {
      setSelectedRecordingId(latestRecording.recordingId);
    }
  }, [latestRecording?.recordingId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = teachViewport.width;
    canvas.height = teachViewport.height;
  }, [canvasRef, teachViewport.height, teachViewport.width]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas && currentFrame?.png) {
      drawFrameToCanvas(canvas, currentFrame.png, currentFrame.cursor);
    }
  }, [canvasRef, currentFrame]);

  useEffect(() => {
    if (variableRequest) {
      const initial: Record<string, string> = {};
      variableRequest.fields.forEach((field) => {
        initial[field.name] = field.value ?? '';
      });
      setVariableValues(initial);
      setVariableError('');
    } else {
      setVariableValues({});
      setVariableError('');
    }
  }, [variableRequest]);

  const pendingVariableNames = useMemo(() => {
    if (!variableRequest) {
      return [] as string[];
    }
    return variableRequest.fields.map((field) => field.name);
  }, [variableRequest]);

  const isVariableSubmitDisabled = useMemo(() => {
    if (!variableRequest || variableRequest.fields.length === 0) {
      return true;
    }
    return variableRequest.fields.some((field) => {
      const val = variableValues[field.name] ?? '';
      return !val.trim();
    });
  }, [variableRequest, variableValues]);

  const handleVariableChange = (name: string, value: string) => {
    setVariableValues((prev) => ({ ...prev, [name]: value }));
    if (variableError) {
      setVariableError('');
    }
  };

  const handleVariableSubmit = () => {
    if (!variableRequest) {
      return;
    }
    const missing: string[] = [];
    const payload: Record<string, string> = {};
    variableRequest.fields.forEach((field) => {
      const raw = variableValues[field.name] ?? '';
      const trimmed = raw.trim();
      if (!trimmed) {
        missing.push(field.name);
      }
      payload[field.name] = trimmed;
    });
    if (missing.length) {
      setVariableError(`Provide values for: ${missing.join(', ')}`);
      return;
    }
    setVariableError('');
    onSubmitVariables(payload);
  };

  const handleRecordingChange = async (event: SelectChangeEvent) => {
    const value = event.target.value;
    setSelectedRecordingId(value);

    if (value === 'new') {
      // Clear current recording state
      setLatestRecording(null);
      setRecordingFrames([]);
      setMarkers([]);
      setEventEntries([{ id: 'empty', text: 'No events yet.' }]);
      setCurrentFrame(null);
      return;
    }

    // Load the selected recording
    try {
      const response = await fetch(`${apiBase}/recordings/${value}/bundle`);
      if (response.ok) {
        const data = await response.json();

        // Update app state with the loaded recording data
        const frames = data.frames || [];
        const markers = data.markers || [];
        const events = (data.events || []) as RawEvent[];

        setLatestRecording({
          recordingId: data.meta?.recordingId || value,
          frames: frames,
          markers: markers,
          events: events,
        });

        setRecordingFrames(frames);
        setMarkers(markers);
        setEventEntries(buildEventEntries(events));

        // Set the first frame as current frame if available
        if (frames.length > 0) {
          setCurrentFrame({ png: frames[0].png });
        } else {
          setCurrentFrame(null);
        }
      } else {
        console.error('Failed to load recording:', response.statusText);
      }
    } catch (error) {
      console.error('Failed to load recording:', error);
    }
  };

  const showVariableOverlay = Boolean(variableRequest && variableRequest.fields.length);

  return (
    <ViewerCard elevation={0}>
      <Box>
        <CanvasBox>
          <RecordingSelectorOverlay>
            <FormControl size="small" fullWidth>
              <InputLabel id="recording-selector-label">Recording</InputLabel>
              <Select
                labelId="recording-selector-label"
                value={selectedRecordingId}
                label="Recording"
                onChange={handleRecordingChange}
                sx={{
                  background: 'rgba(15, 23, 42, 0.95)',
                  backdropFilter: 'blur(8px)',
                }}
              >
                <MenuItem value="new">
                  <em>New Recording</em>
                </MenuItem>
                {recordings.map((rec) => (
                  <MenuItem key={rec.recordingId} value={rec.recordingId}>
                    {rec.title || rec.recordingId.slice(0, 8)} — {new Date(rec.updatedAt).toLocaleString()}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </RecordingSelectorOverlay>
          <CanvasElement ref={canvasRef} />
          {showVariableOverlay ? (
            <VariableOverlay>
              <Typography variant="subtitle1">Plan variables required</Typography>
              <Typography variant="body2" color="rgba(226, 232, 240, 0.85)">
                Provide values so the run can continue.
              </Typography>
              <Stack spacing={2}>
                {variableRequest?.fields.map((field) => (
                  <TextField
                    key={field.name}
                    label={field.name}
                    value={variableValues[field.name] ?? ''}
                    onChange={(event) => handleVariableChange(field.name, event.target.value)}
                    autoFocus={pendingVariableNames[0] === field.name}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        handleVariableSubmit();
                      }
                    }}
                  />
                ))}
              </Stack>
              {variableError ? (
                <Typography variant="body2" color="rgba(248, 113, 113, 0.9)">
                  {variableError}
                </Typography>
              ) : null}
              <Stack direction="row" spacing={2} justifyContent="flex-end">
                <Button variant="outlined" color="inherit" onClick={onAbortVariables}>
                  Abort Run
                </Button>
                <Button
                  variant="contained"
                  color="primary"
                  disabled={isVariableSubmitDisabled}
                  onClick={handleVariableSubmit}
                >
                  Continue
                </Button>
              </Stack>
            </VariableOverlay>
          ) : prompt ? (
            <PromptOverlay>
              <Typography variant="subtitle1">{prompt.summary}</Typography>
              <Typography variant="body2" color="rgba(226, 232, 240, 0.85)">
                {prompt.detail}
              </Typography>
              <Stack direction="row" spacing={2} justifyContent="flex-end">
                <Button variant="outlined" color="inherit" onClick={() => onConfirmPrompt(false)}>
                  Deny
                </Button>
                <Button variant="contained" color="primary" onClick={() => onConfirmPrompt(true)}>
                  Allow
                </Button>
              </Stack>
            </PromptOverlay>
          ) : null}
        </CanvasBox>
      </Box>
      <StatusText>{status}</StatusText>
      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={4} sx={{ width: '100%' }}>
        <Panel elevation={0} sx={{ flex: 1 }}>
          <Typography variant="subtitle2" sx={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Console
          </Typography>
          <Divider sx={{ borderColor: 'rgba(148, 163, 184, 0.25)' }} />
          <Stack spacing={1}>
            {consoleEntries.length === 0 ? (
              <ConsoleText>No console output yet.</ConsoleText>
            ) : (
              consoleEntries.map((entry) => (
                <ConsoleText key={entry.id}>
                  <strong>[{entry.role}] </strong>
                  {entry.message}
                </ConsoleText>
              ))
            )}
          </Stack>
        </Panel>
        <Panel elevation={0} sx={{ flex: 1 }}>
          <Typography variant="subtitle2" sx={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Event log
          </Typography>
          <Divider sx={{ borderColor: 'rgba(148, 163, 184, 0.25)' }} />
          <Stack spacing={0.5}>
            {eventEntries.length === 0 ? (
              <EventText className="event-empty">No events yet.</EventText>
            ) : (
              eventEntries.map((entry) => <EventText key={entry.id}>{entry.text}</EventText>)
            )}
          </Stack>
        </Panel>
      </Stack>
    </ViewerCard>
  );
}
