import { Paper, Stack, TextField, Typography } from '@mui/material';
import { styled } from '../stitches.config';

const PanelCard = styled(Paper, {
  background: 'rgba(15, 23, 42, 0.75)',
  borderRadius: '16px',
  border: '1px solid rgba(148, 163, 184, 0.2)',
  padding: '$5',
  display: 'flex',
  flexDirection: 'column',
  gap: '$4',
});

interface VariableHintsPanelProps {
  variableHints: string;
  onVariableHintsChange: (hints: string) => void;
  disabled?: boolean;
}

export function VariableHintsPanel({
  variableHints,
  onVariableHintsChange,
  disabled = false,
}: VariableHintsPanelProps) {
  return (
    <PanelCard elevation={0}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline">
          <Typography variant="h6" fontSize="1rem">
            Variable hints
          </Typography>
        </Stack>
        <TextField
          multiline
          rows={3}
          fullWidth
          placeholder="e.g., 'Make the search term a variable' or 'Parameterize the email address'"
          value={variableHints}
          onChange={(e) => onVariableHintsChange(e.target.value)}
          disabled={disabled}
          helperText="Provide instructions for the synthesizer on what values to make into variables"
          sx={{
            '& .MuiInputBase-root': {
              fontSize: '0.9rem',
            },
            '& .MuiFormHelperText-root': {
              fontSize: '0.75rem',
              color: 'rgba(148, 163, 184, 0.7)',
            },
          }}
        />
      </Stack>
    </PanelCard>
  );
}
