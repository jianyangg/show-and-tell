import { useEffect, useMemo, useState } from 'react';
import {
  AppBar,
  Toolbar,
  TextField,
  MenuItem,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  Select,
  FormControl,
  InputLabel,
  Chip,
  Stack,
  Tooltip,
} from '@mui/material';
import { SelectChangeEvent } from '@mui/material/Select';
import { styled } from '../stitches.config';
import { SynthProvider, PlanSummary, useAppStore } from '../store/appStore';

const PROVIDER_STORAGE_KEY = 'plan-synth-provider';

const HeaderBar = styled(AppBar, {
  background: 'rgba(15, 23, 42, 0.9)',
  boxShadow: 'none',
  borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
  backdropFilter: 'blur(16px)',
});

const HeaderRow = styled('div', {
  width: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '$5',
});

const FieldGroup = styled('div', {
  display: 'flex',
  flex: 1,
  minWidth: 0,
  alignItems: 'center',
  gap: '$4',
  flexWrap: 'nowrap',
  overflowX: 'auto',
  paddingRight: '$2',
  '& > *': {
    flexShrink: 0,
  },
});

const ActionsGroup = styled('div', {
  display: 'flex',
  alignItems: 'center',
  gap: '$3',
  flexWrap: 'nowrap',
});

interface HeaderControlsProps {
  onStartTeach: () => void;
  onStopTeach: () => void;
  onSynthesize: () => void;
  onStartRun: () => void;
  onSavePlan: (name: string) => Promise<void> | void;
  onLoadPlan: (planId: string) => Promise<void> | void;
  onRefreshPlans: () => Promise<void> | void;
  onConnectToRun?: (runId: string) => void;
  isRecording: boolean;
  hasRecording: boolean;
  hasPlan: boolean;
  providerLabel: string;
  planSummaries: PlanSummary[];
}

export function HeaderControls({
  onStartTeach,
  onStopTeach,
  onSynthesize,
  onStartRun,
  onSavePlan,
  onLoadPlan,
  onRefreshPlans,
  onConnectToRun,
  isRecording,
  hasRecording,
  hasPlan,
  providerLabel,
  planSummaries,
}: HeaderControlsProps) {
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [selectedPlanId, setSelectedPlanId] = useState('');
  const [connectDialogOpen, setConnectDialogOpen] = useState(false);
  const [runIdInput, setRunIdInput] = useState('');

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

  const hasEmptyVariables = useMemo(() => {
    if (!planDetail?.plan?.vars) return false;
    const hasVariables = planDetail?.hasVariables || planDetail?.plan?.hasVariables;
    if (!hasVariables) return false;

    return Object.entries(planDetail.plan.vars).some(([_, value]) => {
      const stringValue = value === null || value === undefined ? '' : String(value);
      return stringValue.trim().length === 0;
    });
  }, [planDetail]);

  const runButtonTooltip = useMemo(() => {
    if (!hasPlan) return 'Generate a plan first';
    if (hasEmptyVariables) return 'Fill in all variable values before running';
    return '';
  }, [hasPlan, hasEmptyVariables]);

  useEffect(() => {
    if (planDetail?.planId) {
      setSelectedPlanId(planDetail.planId);
    }
  }, [planDetail?.planId]);

  const handlePlanSelect = (event: SelectChangeEvent) => {
    const value = event.target.value;
    setSelectedPlanId(value);
    if (value) {
      onLoadPlan(value);
    }
  };

  const handleRefreshPlans = () => {
    onRefreshPlans();
  };

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

  const openConnectDialog = () => {
    setRunIdInput('');
    setConnectDialogOpen(true);
  };

  const closeConnectDialog = () => setConnectDialogOpen(false);

  const handleConnectConfirm = () => {
    if (!runIdInput.trim() || !onConnectToRun) {
      return;
    }
    onConnectToRun(runIdInput.trim());
    setConnectDialogOpen(false);
  };

  return (
    <HeaderBar position="sticky" color="transparent">
      <Toolbar sx={{ width: '100%', alignItems: 'center', py: 1 }}>
        <HeaderRow>
          <FieldGroup>
            <TextField
              label="API Base"
              value={apiBase}
              onChange={(event) => setApiBase(event.target.value)}
              size="small"
              sx={{ width: 220 }}
            />
            <TextField
              label="Start URL"
              value={startUrl}
              onChange={(event) => setStartUrl(event.target.value)}
              size="small"
              sx={{ width: 220 }}
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
            <FormControl size="small" sx={{ minWidth: 240 }}>
              <InputLabel id="saved-plan-label">Saved Plan</InputLabel>
              <Select
                labelId="saved-plan-label"
                value={selectedPlanId}
                label="Saved Plan"
                onChange={handlePlanSelect}
                displayEmpty
                renderValue={(value) => {
                  if (!value) {
                    return 'Choose a saved plan';
                  }
                  const match = planSummaries.find((plan) => plan.planId === value);
                  if (!match) {
                    return value;
                  }
                  return match.hasVariables ? `${match.name} (variables)` : match.name;
                }}
              >
                <MenuItem value="">
                  <em>Choose a saved plan</em>
                </MenuItem>
                {planSummaries.map((plan) => (
                  <MenuItem key={plan.planId} value={plan.planId}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography component="span">
                        {plan.name} — {new Date(plan.updatedAt).toLocaleString()}
                      </Typography>
                      {plan.hasVariables ? (
                        <Chip label="Variables" size="small" color="warning" variant="outlined" />
                      ) : null}
                    </Stack>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Button variant="outlined" size="small" onClick={handleRefreshPlans}>
              Refresh plans
            </Button>
          </FieldGroup>
          <ActionsGroup>
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
            <Tooltip title={runButtonTooltip} arrow placement="bottom">
              <span>
                <Button
                  variant="contained"
                  color="success"
                  onClick={onStartRun}
                  disabled={!hasPlan || hasEmptyVariables}
                >
                  Run steps
                </Button>
              </span>
            </Tooltip>
            <Button variant="outlined" color="inherit" onClick={openSaveDialog} disabled={!hasPlan}>
              Save plan
            </Button>
            {onConnectToRun && (
              <Button variant="outlined" color="info" onClick={openConnectDialog}>
                Connect to run
              </Button>
            )}
          </ActionsGroup>
        </HeaderRow>
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
      <Dialog open={connectDialogOpen} onClose={closeConnectDialog} fullWidth maxWidth="sm">
        <DialogTitle>Connect to existing run</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
            Enter a run ID from an MCP-started run or previous session
          </Typography>
          <TextField
            autoFocus
            fullWidth
            label="Run ID"
            value={runIdInput}
            onChange={(event) => setRunIdInput(event.target.value)}
            placeholder="e.g., 50ae8591486841d2806e0e56442470c5"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={closeConnectDialog}>Cancel</Button>
          <Button onClick={handleConnectConfirm} variant="contained" disabled={!runIdInput.trim()}>
            Connect
          </Button>
        </DialogActions>
      </Dialog>
    </HeaderBar>
  );
}
