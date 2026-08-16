export interface ValidRemoteConfig {
  latest_version: string;
  min_version: string;
  download: {
    primary: string;
    mirrors: string[];
  };
  announcement: string;
  announcement_i18n?: Record<string, string>;
  source_expiry_hours: number;
  source_schema_version: number;
  updated_at: string;
}

const SEMVER_RE = /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/;

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:';
  } catch {
    return false;
  }
}

function semverPart(value: string, index: number): number {
  const raw = value.split('.')[index] || '';
  const match = raw.match(/^\d+/);
  return match ? Number.parseInt(match[0], 10) : 0;
}

/** Compare the numeric major/minor/patch portion of two version strings. */
export function compareSemver(a: string, b: string): number {
  for (let i = 0; i < 3; i++) {
    const na = semverPart(String(a || ''), i);
    const nb = semverPart(String(b || ''), i);
    if (na < nb) return -1;
    if (na > nb) return 1;
  }
  return 0;
}

export function isRemoteConfig(value: unknown): value is ValidRemoteConfig {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  if (typeof data.latest_version !== 'string' || !SEMVER_RE.test(data.latest_version.trim())) return false;
  if (typeof data.min_version !== 'string' || !SEMVER_RE.test(data.min_version.trim())) return false;
  if (!data.download || typeof data.download !== 'object') return false;
  const download = data.download as Record<string, unknown>;
  if (typeof download.primary !== 'string' || !isHttpUrl(download.primary)) return false;
  if (!Array.isArray(download.mirrors)
    || download.mirrors.some((item) => typeof item !== 'string' || !isHttpUrl(item))) return false;
  if (data.announcement != null && typeof data.announcement !== 'string') return false;
  if (data.announcement_i18n != null) {
    if (typeof data.announcement_i18n !== 'object' || Array.isArray(data.announcement_i18n)) return false;
    if (Object.values(data.announcement_i18n as Record<string, unknown>).some((item) => typeof item !== 'string')) return false;
  }
  if (data.source_expiry_hours != null
    && (typeof data.source_expiry_hours !== 'number' || !Number.isFinite(data.source_expiry_hours) || data.source_expiry_hours <= 0)) return false;
  if (data.source_schema_version != null
    && (typeof data.source_schema_version !== 'number' || !Number.isInteger(data.source_schema_version) || data.source_schema_version < 1)) return false;
  if (data.updated_at != null
    && (typeof data.updated_at !== 'string' || !Number.isFinite(Date.parse(data.updated_at)))) return false;
  return true;
}
