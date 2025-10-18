export function normalizeStartUrl(rawUrl: string | null | undefined): string | null {
  if (!rawUrl) {
    return null;
  }
  const trimmed = rawUrl.trim();
  if (!trimmed) {
    return null;
  }
  if (/^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(trimmed)) {
    return trimmed;
  }
  return `http://${trimmed}`;
}

