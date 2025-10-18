import { useMemo, useRef } from 'react';
import { ThemeProvider, createTheme, CssBaseline, Container, Stack, Box } from '@mui/material';
import { HeaderControls } from './components/HeaderControls';
import { ViewerSection } from './components/ViewerSection';
import { TimelinePanel } from './components/TimelinePanel';
import { PlanPanel } from './components/PlanPanel';
import { useTeachSession } from './hooks/useTeachSession';
import { useRunSession } from './hooks/useRunSession';
import { usePlanActions } from './hooks/usePlanActions';
import { useAppStore } from './store/appStore';
import { styled } from './stitches.config';

const Footer = styled('footer', {
  textAlign: 'center',
  padding: '$6',
  fontSize: '0.85rem',
  color: 'rgba(148, 163, 184, 0.75)',
  borderTop: '1px solid rgba(148, 163, 184, 0.2)',
  background: 'rgba(15, 23, 42, 0.9)',
  marginTop: '$6',
});

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#38bdf8',
    },
    secondary: {
      main: '#0ea5e9',
    },
    background: {
      default: '#0f172a',
      paper: 'rgba(15, 23, 42, 0.8)',
    },
  },
  typography: {
    fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
  },
});

export default function App() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { startTeach, stopTeach, isRecording } = useTeachSession(canvasRef);
  const { startRun, confirmPrompt } = useRunSession();
  const { synthesizePlan, savePlan, planDetail, providerLabel } = usePlanActions();

  const status = useAppStore((state) => state.status);
  const consoleEntries = useAppStore((state) => state.consoleEntries);
  const eventEntries = useAppStore((state) => state.eventEntries);
  const currentFrame = useAppStore((state) => state.currentFrame);
  const markers = useAppStore((state) => state.markers);
  const frames = useAppStore((state) => state.recordingFrames);
  const prompt = useAppStore((state) => state.prompt);
  const runStepStatus = useAppStore((state) => state.runStepStatus);
  const latestRecording = useAppStore((state) => state.latestRecording);
  const setCurrentFrame = useAppStore((state) => state.setCurrentFrame);

  const hasRecording = useMemo(() => Boolean(latestRecording), [latestRecording]);
  const hasPlan = useMemo(() => Boolean(planDetail), [planDetail]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <HeaderControls
        onStartTeach={startTeach}
        onStopTeach={stopTeach}
        onSynthesize={synthesizePlan}
        onStartRun={startRun}
        onSavePlan={savePlan}
        isRecording={isRecording}
        hasRecording={hasRecording}
        hasPlan={hasPlan}
        providerLabel={providerLabel}
      />
      <Container maxWidth="xl" sx={{ py: 6 }}>
        <Stack direction={{ xs: 'column', lg: 'row' }} spacing={4} alignItems="flex-start">
          <Box sx={{ flex: 2.5, width: '100%' }}>
            <ViewerSection
              canvasRef={canvasRef}
              status={status}
              consoleEntries={consoleEntries}
              eventEntries={eventEntries}
              currentFrame={currentFrame}
              prompt={prompt}
              onConfirmPrompt={confirmPrompt}
            />
          </Box>
          <Stack spacing={4} sx={{ flex: 1, width: '100%' }}>
            <TimelinePanel
              frames={frames}
              markers={markers}
              onSelectFrame={(frame) => setCurrentFrame({ png: frame.png })}
            />
            <PlanPanel planDetail={planDetail ?? null} runStepStatus={runStepStatus} />
          </Stack>
        </Stack>
      </Container>
      <Footer>Gemini Computer Use Runner</Footer>
    </ThemeProvider>
  );
}
