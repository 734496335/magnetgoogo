import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'mg_source_stats_v1';

interface SourcePerfStat {
  runs: number;
  okCount: number;
  emptyCount: number;
  failCount: number;
  challengeCount: number;
  totalMs: number;
  lastOkAt: number;
  lastFailAt: number;
}

type SourceStatMap = Record<string, SourcePerfStat>;

let _loaded = false;
let _stats: SourceStatMap = {};
let _persistTimer: ReturnType<typeof setTimeout> | null = null;

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
    } catch { /* ignore */ }
  }, 1000);
}

export async function loadSourceStats(): Promise<void> {
  if (_loaded) return;
  _loaded = true;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    _stats = raw ? JSON.parse(raw) : {};
  } catch {
    _stats = {};
  }
}

export function recordSourceRun(rule: any, params: {
  ok: boolean;
  count: number;
  ms: number;
  challenge?: boolean;
}) {
  const key = getSourceKey(rule);
  const stat = _stats[key] || defaultStat();
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

  _stats[key] = stat;
  schedulePersist();
}

export function getSourcePerfBoost(rule: any): number {
  const stat = _stats[getSourceKey(rule)];
  if (!stat || stat.runs <= 0) return 0;

  const avgMs = stat.totalMs / stat.runs;
  const successRate = stat.okCount / stat.runs;
  const emptyRate = stat.emptyCount / stat.runs;
  const failRate = stat.failCount / stat.runs;
  const challengeRate = stat.challengeCount / stat.runs;

  let boost = 0;
  boost += successRate * 35;
  boost -= emptyRate * 12;
  boost -= failRate * 20;
  boost -= challengeRate * 12;
  boost -= Math.min(avgMs / 500, 12);
  return boost;
}
