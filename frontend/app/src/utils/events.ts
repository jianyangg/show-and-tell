import { EventEntry } from '../store/appStore';

export interface RawEvent {
  timestamp?: number;
  kind?: string;
  button?: number | string;
  duration?: number;
  combo?: string;
  key?: string;
  detail?: string;
  start_x?: number;
  start_y?: number;
  end_x?: number;
  end_y?: number;
}

function formatTimestamp(value?: number): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '0.0s';
  }
  return `${value.toFixed(2)}s`;
}

function describeMouseButton(button: number | string | undefined): string {
  if (typeof button === 'number') {
    if (button === 0) return 'left';
    if (button === 1) return 'middle';
    if (button === 2) return 'right';
  }
  if (typeof button === 'string') {
    return button;
  }
  return '?';
}

function buildDetail(event: RawEvent): string {
  const kind = event.kind ?? 'event';
  switch (kind) {
    case 'click':
      return `→ ${describeMouseButton(event.button)} button`;
    case 'doubleclick':
      return `→ ${describeMouseButton(event.button)} double click`;
    case 'wheel':
      return `→ scroll`;
    case 'keypress':
      return event.detail ? `→ ${event.detail}` : event.key ? `→ ${event.key}` : '';
    case 'keydown_repeat':
      return `→ ${event.combo || event.key || '?'}`;
    case 'keydown':
    case 'keyup':
      return `→ ${event.combo || event.key || '?'}`;
    case 'drag':
      // Show drag start→end coordinates and distance for better visibility
      if (
        typeof event.start_x === 'number' &&
        typeof event.start_y === 'number' &&
        typeof event.end_x === 'number' &&
        typeof event.end_y === 'number'
      ) {
        const dx = event.end_x - event.start_x;
        const dy = event.end_y - event.start_y;
        const distance = Math.round(Math.sqrt(dx * dx + dy * dy));
        return `→ (${Math.round(event.start_x)},${Math.round(event.start_y)}) to (${Math.round(event.end_x)},${Math.round(event.end_y)}) ${distance}px`;
      }
      return event.detail ? `→ ${event.detail}` : '';
    default:
      if (event.key) {
        return `→ ${event.key}`;
      }
      return event.detail ? `→ ${event.detail}` : '';
  }
}

export function buildEventEntries(events: RawEvent[]): EventEntry[] {
  if (!Array.isArray(events) || events.length === 0) {
    return [{ id: 'empty', text: 'No events yet.' }];
  }
  return events.map((event, index) => {
    const timestamp = formatTimestamp(event.timestamp);
    const kind = (event.kind || 'event').replace(/_/g, ' ');
    const detail = buildDetail(event);
    const suffix = detail ? ` ${detail}` : '';
    return {
      id: `${index}-${event.kind ?? 'event'}`,
      text: `${timestamp} ${kind}${suffix}`,
    };
  });
}
