const MAX_SEARCH_CODEPOINTS = 100;

/** Normalize route, history, analytics, and engine input to one canonical term. */
export function normalizeSearchTerm(input: unknown): string {
  if (typeof input !== 'string') return '';
  const compact = input.trim().replace(/\s+/gu, ' ');
  return Array.from(compact).slice(0, MAX_SEARCH_CODEPOINTS).join('');
}
