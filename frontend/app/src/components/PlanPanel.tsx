import { Chip, Paper, Stack, TextField, Typography } from '@mui/material';
import { styled } from '../stitches.config';
import { PlanDetail, StepStatus } from '../store/appStore';

const PanelCard = styled(Paper, {
  background: 'rgba(15, 23, 42, 0.75)',
  borderRadius: '16px',
  border: '1px solid rgba(148, 163, 184, 0.2)',
  padding: '$5',
  display: 'flex',
  flexDirection: 'column',
  gap: '$4',
});

const StepCard = styled('div', {
  borderRadius: '12px',
  border: '1px solid rgba(148, 163, 184, 0.2)',
  background: 'rgba(30, 41, 59, 0.65)',
  padding: '$4',
  transition: 'border-color 0.15s ease, background 0.15s ease',
  variants: {
    state: {
      idle: {},
      active: {
        borderColor: 'rgba(96, 165, 250, 0.7)',
        background: 'rgba(30, 64, 175, 0.45)',
      },
      done: {
        borderColor: 'rgba(74, 222, 128, 0.8)',
        background: 'rgba(22, 101, 52, 0.35)',
      },
    },
  },
});

interface PlanPanelProps {
  planDetail: PlanDetail | null;
  runStepStatus: Record<string, StepStatus>;
  onVariableChange?: (name: string, value: string) => void;
}

export function PlanPanel({ planDetail, runStepStatus, onVariableChange }: PlanPanelProps) {
  const planVars = planDetail?.plan?.vars ?? {};
  const hasVariables = Boolean(planDetail?.hasVariables || planDetail?.plan?.hasVariables);
  const variableEntries = Object.entries(planVars);

  return (
    <PanelCard elevation={0}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline">
          <Typography variant="h6" fontSize="1rem">
            Plan steps
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2" color="rgba(148, 197, 255, 0.85)">
              {planDetail?.plan?.name ?? 'No plan loaded'}
            </Typography>
            {hasVariables ? <Chip label="Variables required" size="small" color="warning" /> : null}
          </Stack>
        </Stack>
        {hasVariables ? (
          <Stack
            spacing={1}
            sx={{
              borderRadius: '12px',
              border: '1px solid rgba(148, 163, 184, 0.25)',
              background: 'rgba(15, 23, 42, 0.55)',
              padding: '16px',
            }}
          >
            <Typography
              variant="subtitle2"
              sx={{ textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(148, 197, 255, 0.85)' }}
            >
              Variables
            </Typography>
            {variableEntries.length ? (
              <Stack spacing={2}>
                {variableEntries
                  .slice()
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([name, value]) => {
                    const stringValue = value === null || value === undefined ? '' : String(value);
                    return (
                      <TextField
                        key={name}
                        label={name}
                        value={stringValue}
                        onChange={(e) => onVariableChange?.(name, e.target.value)}
                        size="small"
                        fullWidth
                        placeholder="Enter value..."
                        sx={{
                          '& .MuiInputBase-root': {
                            fontSize: '0.9rem',
                            background: 'rgba(30, 41, 59, 0.5)',
                          },
                          '& .MuiInputLabel-root': {
                            color: 'rgba(148, 197, 255, 0.9)',
                          },
                        }}
                      />
                    );
                  })}
              </Stack>
            ) : (
              <Typography variant="body2" color="rgba(226, 232, 240, 0.7)">
                Values will be requested before the run begins.
              </Typography>
            )}
          </Stack>
        ) : null}
        {planDetail?.plan?.steps?.length ? (
          <Stack spacing={2}>
            {planDetail.plan.steps.map((step) => (
              <StepCard key={step.id} state={runStepStatus[step.id] ?? 'idle'}>
                <Typography variant="subtitle1" fontSize="0.95rem">
                  {step.id}: {step.title}
                </Typography>
                <Typography variant="body2" color="rgba(226, 232, 240, 0.7)">
                  {step.instructions || '(no instructions provided)'}
                </Typography>
              </StepCard>
            ))}
          </Stack>
        ) : (
          <Typography variant="body2" color="textSecondary">
            Record and synthesize to view steps.
          </Typography>
        )}
      </Stack>
    </PanelCard>
  );
}
