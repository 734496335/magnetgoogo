import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  classifyQueryProfile,
  computeSourceLearningBoost,
  getSourceBenchmarkBoost,
  type QueryProfile,
  type SourceLearningSnapshot,
} from './searchQuality';

const STORAGE_KEY = 'mg_source_stats_v1';
const EWMA_ALPHA = 0.25;

interface SourceQualityStat {
  samples: number;
  relevantYieldEwma: number;
  precisionEwma: number;
}

interface SourcePerfStat {
  runs: number;
  okCount: number;
  emptyCount: number;
  failCount: number;
  challengeCount: number;
  totalMs: number;
  lastOkAt: number;
  lastFailAt: number;
  quality: SourceQualityStat;
  profiles: Partial<Record<QueryProfile, SourceQualityStat>>;
}

type SourceStatMap = Record<string, SourcePerfStat>;

let _loaded = false;
let _stats: SourceStatMap = {};
let _persistTimer: ReturnType<typeof setTimeout> | null = null;

function defaultQualityStat(): SourceQualityStat {
  return {
    samples: 0,
    relevantYieldEwma: 0,
    precisionEwma: 0,
  };
}

function defaultStat(): SourcePerfStat {
  return {
    runs: 0,
    okCount: 0,
    emptyCount: 0,
    failCount: 0,
    challengeCount: 0,
    totalMs: 0,
    lastOkAt: 0,
    lastFailAt: 0,
    quality: defaultQualityStat(),
    profiles: {},
  };
}

function normalizeQualityStat(value: unknown): SourceQualityStat {
  const raw = value && typeof value === 'object' ? value as Partial<SourceQualityStat> : {};
  return {
    samples: Number.isFinite(raw.samples) ? Math.max(0, Number(raw.samples)) : 0,
    relevantYieldEwma: Number.isFinite(raw.relevantYieldEwma) ? Math.max(0, Number(raw.relevantYieldEwma)) : 0,
    precisionEwma: Number.isFinite(raw.precisionEwma)
      ? Math.min(1, Math.max(0, Number(raw.precisionEwma)))
      : 0,
  };
}

function normalizeStat(value: unknown): SourcePerfStat {
  const raw = value && typeof value === 'object' ? value as Partial<SourcePerfStat> : {};
  const profiles = raw.profiles && typeof raw.profiles === 'object' ? raw.profiles : {};
  return {
    runs: Number.isFinite(raw.runs) ? Math.max(0, Number(raw.runs)) : 0,
    okCount: Number.isFinite(raw.okCount) ? Math.max(0, Number(raw.okCount)) : 0,
    emptyCount: Number.isFinite(raw.emptyCount) ? Math.max(0, Number(raw.emptyCount)) : 0,
    failCount: Number.isFinite(raw.failCount) ? Math.max(0, Number(raw.failCount)) : 0,
    challengeCount: Number.isFinite(raw.challengeCount) ? Math.max(0, Number(raw.challengeCount)) : 0,
    totalMs: Number.isFinite(raw.totalMs) ? Math.max(0, Number(raw.totalMs)) : 0,
    lastOkAt: Number.isFinite(raw.lastOkAt) ? Math.max(0, Number(raw.lastOkAt)) : 0,
    lastFailAt: Number.isFinite(raw.lastFailAt) ? Math.max(0, Number(raw.lastFailAt)) : 0,
    quality: normalizeQualityStat(raw.quality),
    profiles: {
      code: normalizeQualityStat(profiles.code),
      cjk: normalizeQualityStat(profiles.cjk),
      latin: normalizeQualityStat(profiles.latin),
      mixed: normalizeQualityStat(profiles.mixed),
    },
  };
}

function getSourceKey(rule: any): string {
  return String(rule?.site?.origin || rule?.site?.name || 'unknown');
}

function schedulePersist() {
  if (_persistTimer) return;
  _persistTimer = setTimeout(async () => {
    _persistTimer = null;
    try {
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(_stats));
    } catch {
      // Search must not wait for or fail because of local ranking persistence.
    }
  }, 1000);
}

function updateQualityStat(stat: SourceQualityStat, relevantCount: number, precision: number) {
  const safeRelevant = Math.max(0, relevantCount || 0);
  const safePrecision = Math.min(1, Math.max(0, precision || 0));
  const alpha = stat.samples === 0 ? 1 : EWMA_ALPHA;
  stat.relevantYieldEwma = stat.relevantYieldEwma * (1 - alpha) + safeRelevant * alpha;
  stat.precisionEwma = stat.precisionEwma * (1 - alpha) + safePrecision * alpha;
  stat.samples += 1;
}

export async function loadSourceStats(): Promise<void> {
  if (_loaded) return;
  _loaded = true;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      _stats = {};
      return;
    }
    _stats = Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [key, normalizeStat(value)]),
    );
  } catch {
    _stats = {};
  }
}

export function recordSourceRun(rule: any, params: {
  ok: boolean;
  count: number;
  ms: number;
  query?: string;
  uniqueCount?: number;
  relevantCount?: number;
  relevancePrecision?: number;
  challenge?: boolean;
}) {
  const key = getSourceKey(rule);
  const stat = normalizeStat(_stats[key] || defaultStat());
  stat.runs += 1;
  stat.totalMs += Math.max(0, params.ms || 0);
  if (params.challenge) stat.challengeCount += 1;

  if (params.ok && params.count > 0) {
    stat.okCount += 1;
    stat.lastOkAt = Date.now();
  } else if (params.ok) {
    stat.emptyCount += 1;
  } else {
    stat.failCount += 1;
    stat.lastFailAt = Date.now();
  }

  if (params.ok) {
    const relevantCount = Math.max(0, params.relevantCount || 0);
    const uniqueCount = Math.max(0, params.uniqueCount ?? params.count ?? 0);
    const precision = Number.isFinite(params.relevancePrecision)
      ? Math.min(1, Math.max(0, Number(params.relevancePrecision)))
      : uniqueCount > 0 ? relevantCount / uniqueCount : 0;
    updateQualityStat(stat.quality, relevantCount, precision);
    if (params.query) {
      const profile = classifyQueryProfile(params.query);
      const profileStat = normalizeQualityStat(stat.profiles[profile]);
      updateQualityStat(profileStat, relevantCount, precision);
      stat.profiles[profile] = profileStat;
    }
  }

  _stats[key] = stat;
  schedulePersist();
}

function getPoolRoleBoost(rule: any): number {
  const role = String(rule?.quality?.pool_role || '').toLowerCase();
  if (role === 'primary') return 1.5;
  if (role === 'fallback') return 0;
  return 0.5;
}

export function getSourcePerfBoost(rule: any, query = '', ignoreLocalLearning = false): number {
  const benchmarkBoost = query ? getSourceBenchmarkBoost(rule, query) : 0;
  const roleBoost = getPoolRoleBoost(rule);
  const stat = ignoreLocalLearning ? undefined : _stats[getSourceKey(rule)];
  if (!stat || stat.runs <= 0) {
    return benchmarkBoost + roleBoost + computeSourceLearningBoost({
      successRate: 0,
      emptyRate: 0,
      failRate: 0,
      challengeRate: 0,
      avgMs: 0,
      relevantYield: 0,
      precision: 0,
      qualitySamples: 0,
    });
  }

  const avgMs = stat.totalMs / stat.runs;
  const profile = query ? classifyQueryProfile(query) : null;
  const profileQuality = profile ? stat.profiles?.[profile] : undefined;
  const quality = profileQuality && profileQuality.samples >= 2 ? profileQuality : stat.quality;
  const snapshot: SourceLearningSnapshot = {
    successRate: stat.okCount / stat.runs,
    emptyRate: stat.emptyCount / stat.runs,
    failRate: stat.failCount / stat.runs,
    challengeRate: stat.challengeCount / stat.runs,
    avgMs,
    relevantYield: quality?.relevantYieldEwma || 0,
    precision: quality?.precisionEwma || 0,
    qualitySamples: quality?.samples || 0,
  };
  return benchmarkBoost + roleBoost + computeSourceLearningBoost(snapshot);
}
