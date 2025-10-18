import { useEffect, useMemo, useState } from 'react';
import {
  AppBar,
  Toolbar,
  TextField,
  MenuItem,
  Button,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Select,
  FormControl,
  InputLabel,
} from '@mui/material';
import { SelectChangeEvent } from '@mui/material/Select';
import { styled } from '../stitches.config';
import { SynthProvider, useAppStore } from '../store/appStore';

const PROVIDER_STORAGE_KEY = 'plan-synth-provider';

const HeaderBar = styled(AppBar, {
  background: 'rgba(15, 23, 42, 0.9)',
  boxShadow: 'none',
  borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
  backdropFilter: 'blur(16px)',
});

const ControlsStack = styled(Stack, {
  width: '100%',
  display: 'flex',
  flexDirection: 'row',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '$5',
  flexWrap: 'wrap',
});

const FieldStack = styled(Stack, {
  display: 'flex',
  flexDirection: 'row',
  flexWrap: 'wrap',
  gap: '$4',
  alignItems: 'center',
});

const ActionsStack = styled(Stack, {
  display: 'flex',
  flexDirection: 'row',
  gap: '$3',
  flexWrap: 'wrap',
});

interface HeaderControlsProps {
  onStartTeach: () => void;
  onStopTeach: () => void;
  onSynthesize: () => void;
  onStartRun: () => void;
  onSavePlan: (name: string) => Promise<void> | void;
  isRecording: boolean;
  hasRecording: boolean;
  hasPlan: boolean;
  providerLabel: string;
}

export function HeaderControls({
  onStartTeach,
  onStopTeach,
  onSynthesize,
  onStartRun,
  onSavePlan,
  isRecording,
  hasRecording,
  hasPlan,
  providerLabel,
}: HeaderControlsProps) {
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveName, setSaveName] = useState('');

  const { apiBase, setApiBase, startUrl, setStartUrl, synthProvider, setSynthProvider, planDetail } =
    useAppStore((state) => ({
      apiBase: state.apiBase,
      setApiBase: state.setApiBase,
      startUrl: state.startUrl,
      setStartUrl: state.setStartUrl,
      synthProvider: state.synthProvider,
      setSynthProvider: state.setSynthProvider,
      planDetail: state.planDetail,
    }));

  useEffect(() => {
    try {
      const stored = localStorage.getItem(PROVIDER_STORAGE_KEY);
      if (stored && (stored === 'gemini' || stored === 'chatgpt')) {
        setSynthProvider(stored as SynthProvider);
      }
    } catch (error) {
      console.warn('Unable to load provider preference from storage', error);
    }
  }, [setSynthProvider]);

  const handleProviderChange = (event: SelectChangeEvent) => {
    const value = event.target.value as SynthProvider;
    setSynthProvider(value);
    try {
      localStorage.setItem(PROVIDER_STORAGE_KEY, value);
    } catch (error) {
      console.warn('Unable to persist provider preference', error);
    }
  };

  const planName = useMemo(() => planDetail?.plan?.name ?? 'No plan loaded', [planDetail]);

  const openSaveDialog = () => {
    if (!hasPlan) return;
    setSaveName(planDetail?.plan?.name ?? '');
    setSaveDialogOpen(true);
  };

  const closeSaveDialog = () => setSaveDialogOpen(false);

  const handleSaveConfirm = async () => {
    if (!saveName.trim()) {
      return;
    }
    await onSavePlan(saveName.trim());
    setSaveDialogOpen(false);
  };

  return (
    <HeaderBar position="sticky" color="transparent">
      <Toolbar sx={{ width: '100%', alignItems: 'flex-start' }}>
        <ControlsStack>
          <FieldStack spacing={2}>
            <TextField
              label="API Base"
              value={apiBase}
              onChange={(event) => setApiBase(event.target.value)}
              size="small"
              sx={{ minWidth: 220 }}
            />
            <TextField
              label="Start URL"
              value={startUrl}
              onChange={(event) => setStartUrl(event.target.value)}
              size="small"
              sx={{ minWidth: 220 }}
              placeholder="https://example.com"
            />
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel id="synth-provider-label">Synth Provider</InputLabel>
              <Select
                labelId="synth-provider-label"
                value={synthProvider}
                label="Synth Provider"
                onChange={handleProviderChange}
              >
                <MenuItem value="gemini">Gemini 2.5 Pro</MenuItem>
                <MenuItem value="chatgpt">ChatGPT 5</MenuItem>
              </Select>
            </FormControl>
          </FieldStack>
          <ActionsStack direction="row">
            <Button
              variant="contained"
              color="primary"
              onClick={onStartTeach}
              disabled={isRecording}
            >
              Start teach
            </Button>
            <Button
              variant="outlined"
              color="primary"
              onClick={onStopTeach}
              disabled={!isRecording}
            >
              Stop teach
            </Button>
            <Button variant="contained" color="secondary" onClick={onSynthesize} disabled={!hasRecording}>
              Synthesize
            </Button>
            <Button variant="contained" color="success" onClick={onStartRun} disabled={!hasPlan}>
              Run steps
            </Button>
            <Button variant="outlined" color="inherit" onClick={openSaveDialog} disabled={!hasPlan}>
              Save plan
            </Button>
          </ActionsStack>
        </ControlsStack>
      </Toolbar>
      <Dialog open={saveDialogOpen} onClose={closeSaveDialog} fullWidth maxWidth="sm">
        <DialogTitle>Save plan</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
            Current provider: {providerLabel}
          </Typography>
          <TextField
            autoFocus
            fullWidth
            label="Plan name"
            value={saveName}
            onChange={(event) => setSaveName(event.target.value)}
            placeholder={planName}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={closeSaveDialog}>Cancel</Button>
          <Button onClick={handleSaveConfirm} variant="contained">
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </HeaderBar>
  );
}
