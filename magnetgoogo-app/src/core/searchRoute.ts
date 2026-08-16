let searchRunSequence = 0;

export function createSearchRunId(now = Date.now()): string {
  searchRunSequence = (searchRunSequence + 1) >>> 0;
  return `${now.toString(36)}-${searchRunSequence.toString(36)}`;
}

export function normalizeSearchRunId(value: unknown): string {
  return typeof value === 'string' ? value.trim().slice(0, 64) : '';
}

export function routeSearchMatchesSession(
  routeQuery: string,
  routeRunId: string,
  sessionQuery?: string,
  sessionRunId?: string,
): boolean {
  if (!sessionQuery || sessionQuery !== routeQuery) return false;
  if (!routeRunId) return false;
  return sessionRunId === routeRunId;
}
