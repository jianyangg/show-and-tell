import { Button, List, ListItem, Paper, Stack, Typography } from '@mui/material';
import { styled } from '../stitches.config';
import { RecordingFrame, RecordingMarker } from '../store/appStore';

const PanelCard = styled(Paper, {
  background: 'rgba(15, 23, 42, 0.75)',
  borderRadius: '16px',
  border: '1px solid rgba(148, 163, 184, 0.2)',
  padding: '$5',
  display: 'flex',
  flexDirection: 'column',
  gap: '$4',
});

const ThumbButton = styled(Button, {
  background: 'rgba(30, 41, 59, 0.8)',
  border: '1px solid rgba(148, 163, 184, 0.25)',
  borderRadius: '12px',
  textTransform: 'none',
  justifyContent: 'flex-start',
  color: 'inherit',
  '&:hover': {
    background: 'rgba(30, 64, 175, 0.45)',
  },
});

const MarkerList = styled(List, {
  padding: 0,
  margin: 0,
});

interface TimelinePanelProps {
  frames: RecordingFrame[];
  markers: RecordingMarker[];
  onSelectFrame: (frame: RecordingFrame) => void;
}

export function TimelinePanel({ frames, markers, onSelectFrame }: TimelinePanelProps) {
  return (
    <PanelCard elevation={0}>
      <Stack spacing={3}>
        <Stack spacing={2}>
          <Typography variant="h6" fontSize="1rem">
            Timeline
          </Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap">
            {frames.length === 0 ? (
              <Typography variant="body2" color="textSecondary">
                No frames yet.
              </Typography>
            ) : (
              frames.map((frame, index) => (
                <ThumbButton key={`${frame.timestamp}-${index}`} onClick={() => onSelectFrame(frame)}>
                  {index + 1} • {frame.timestamp.toFixed(1)}s
                </ThumbButton>
              ))
            )}
          </Stack>
        </Stack>
        <Stack spacing={2}>
          <Typography variant="h6" fontSize="1rem">
            Markers
          </Typography>
          <MarkerList>
            {markers.length === 0 ? (
              <ListItem sx={{ color: 'rgba(226, 232, 240, 0.7)' }}>No markers yet.</ListItem>
            ) : (
              markers.map((marker, index) => (
                <ListItem key={`${marker.timestamp}-${index}`} sx={{ color: 'rgba(226, 232, 240, 0.8)' }}>
                  {marker.timestamp.toFixed(1)}s • {marker.label || `Marker ${index + 1}`}
                </ListItem>
              ))
            )}
          </MarkerList>
        </Stack>
      </Stack>
    </PanelCard>
  );
}
