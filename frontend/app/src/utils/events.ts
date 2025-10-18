import { EventEntry } from '../store/appStore';

export interface RawEvent {
  timestamp?: number;
  kind?: string;
  button?: number | string;
  duration?: number;
  combo?: string;
  key?: string;
  detail?: string;
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
