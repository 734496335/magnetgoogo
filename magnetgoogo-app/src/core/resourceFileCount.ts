/** Shared torrent file-count parsing and conservative merge authority. */

const EXPLICIT_FILE_COUNT_RE = /(?:file\s*count|files?\s*count|number\s+of\s+files|total\s+files?|files?|文件(?:数量|數量|数)|檔案(?:數量|數)|总文件数|總檔案數)\s*[:：=]?\s*\(?\s*(\d{1,5})(?![.,]\d)/i;

/**
 * Parse only an explicit file-count label. Deliberately rejects strings such as
 * `File Size 771.59 MB` and `Files 8.14 GB`, which previously leaked the size's
 * leading integer into the file-count field.
 */
export function parseExplicitFileCount(raw?: string): number | undefined {
  if (!raw) return undefined;
  const match = String(raw).match(EXPLICIT_FILE_COUNT_RE);
  if (!match) return undefined;
  const count = Number.parseInt(match[1], 10);
  return Number.isFinite(count) && count > 0 ? count : undefined;
}

/** Parse a selector already bound to the file-count field. */
export function parseBoundFileCount(raw?: string): number | undefined {
  if (!raw) return undefined;
  const explicit = parseExplicitFileCount(raw);
  if (explicit) return explicit;
  const match = String(raw).trim().match(/^\(?\s*(\d{1,5})\s*\)?$/);
  if (!match) return undefined;
  const count = Number.parseInt(match[1], 10);
  return Number.isFinite(count) && count > 0 ? count : undefined;
}

export interface FileCountMergeResult {
  fileCount?: number;
  conflict: boolean;
}

/**
 * File count is invariant for one info-hash. If independent evidence disagrees,
 * hide the field rather than freezing the first or largest value.
 */
export function mergeResourceFileCount(
  existing: number | undefined,
  incoming: number | undefined,
  alreadyConflicted = false,
): FileCountMergeResult {
  if (alreadyConflicted) return { fileCount: undefined, conflict: true };
  const left = Number.isFinite(existing) && (existing || 0) > 0 ? Math.trunc(existing!) : undefined;
  const right = Number.isFinite(incoming) && (incoming || 0) > 0 ? Math.trunc(incoming!) : undefined;
  if (!left) return { fileCount: right, conflict: false };
  if (!right || left === right) return { fileCount: left, conflict: false };
  return { fileCount: undefined, conflict: true };
}
