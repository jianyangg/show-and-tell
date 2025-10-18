import { RefObject, useEffect } from 'react';
import {
  Paper,
  Typography,
  Stack,
  Box,
  Divider,
  Button,
} from '@mui/material';
import { styled } from '../stitches.config';
import {
  ConsoleEntry,
  EventEntry,
  FramePayload,
  PromptState,
  useAppStore,
} from '../store/appStore';
import { drawFrameToCanvas } from '../utils/canvas';

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

const CanvasElement = styled('canvas', {
  width: '100%',
  aspectRatio: '16 / 10',
});

interface ViewerSectionProps {
  canvasRef: RefObject<HTMLCanvasElement>;
  status: string;
  consoleEntries: ConsoleEntry[];
  eventEntries: EventEntry[];
  currentFrame: FramePayload | null;
  prompt: PromptState | null;
  onConfirmPrompt: (allow: boolean) => void;
}

export function ViewerSection({
  canvasRef,
  status,
  consoleEntries,
  eventEntries,
  currentFrame,
  prompt,
  onConfirmPrompt,
}: ViewerSectionProps) {
  const { teachViewport } = useAppStore((state) => ({ teachViewport: state.teachViewport }));

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

  return (
    <ViewerCard elevation={0}>
      <Box>
        <CanvasBox>
          <CanvasElement ref={canvasRef} />
          {prompt ? (
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
