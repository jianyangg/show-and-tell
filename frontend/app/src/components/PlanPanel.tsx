import { Paper, Stack, Typography } from '@mui/material';
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
}

export function PlanPanel({ planDetail, runStepStatus }: PlanPanelProps) {
  return (
    <PanelCard elevation={0}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline">
          <Typography variant="h6" fontSize="1rem">
            Plan steps
          </Typography>
          <Typography variant="body2" color="rgba(148, 197, 255, 0.85)">
            {planDetail?.plan?.name ?? 'No plan loaded'}
          </Typography>
        </Stack>
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
