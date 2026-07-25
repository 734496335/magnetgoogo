import { AppRegistry } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { loadSources, syncSources } from './secureSourceStore';
import { runSearchTask } from './searchRunner';
import { loadSourceStats } from './sourceStats';
import { notifySearchCompleted } from './searchNotifications';
import { stopSearchKeepAlive } from './searchKeepAlive';
import { flush, trackSearchCompleted } from './analytics';
import { setBackgroundNetworkMode } from './httpClient';
import { VerifyManager } from './VerifyManager';
import { getResultStableId } from './types';
import {
  backgroundSnapshotMatches,
  mergeBackgroundSearchResults,
  parseBackgroundSearchSnapshot,
  type BackgroundSearchSnapshot,
} from './backgroundSearchProtocol';

const TASK_NAME = 'SearchHeadlessTask';
const RESULT_KEY = 'mg_background_search_result';
const PROGRESS_KEY = 'mg_background_search_progress';
const OWNER_KEY = 'mg_background_search_owner';
const PROGRESS_SAVE_INTERVAL_MS = 1200;
const PROGRESS_SAVE_SOURCE_STEP = 4;

let _registered = false;
const _listeners = new Set<(snapshot: BackgroundSearchSnapshot) => void>();

function reportBackgroundError(stage: string, error: unknown, extra: Record<string, unknown> = {}) {
  const message = error instanceof Error ? error.message : String(error);
  console.warn('[BackgroundSearch]', {
    search_id: typeof extra.searchId === 'string' ? extra.searchId : '',
    rule_id: '',
    stage,
    error_code: message,
    ...extra,
  });
}

function emitSnapshot(snapshot: BackgroundSearchSnapshot) {
  for (const listener of _listeners) {
    try {
      listener(snapshot);
    } catch (error) {
      reportBackgroundError('emit_snapshot', error, { searchId: snapshot.searchId || '', query: snapshot.query });
    }
  }
}

async function loadUsableSources() {
  const cached = await loadSources();
  if (cached && cached.length > 0) return cached;
  const synced = await syncSources();
  return synced.sources;
}

export function subscribeBackgroundSearch(
  listener: (snapshot: BackgroundSearchSnapshot) => void,
): () => void {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

type BackgroundSearchOwner = Pick<BackgroundSearchSnapshot, 'query' | 'token'>;

async function getBackgroundSearchOwner(): Promise<BackgroundSearchOwner | null> {
  const raw = await AsyncStorage.getItem(OWNER_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const query = typeof parsed.query === 'string' ? parsed.query.trim() : '';
    const token = typeof parsed.token === 'number' ? Math.trunc(parsed.token) : 0;
    return query && token > 0 ? { query, token } : null;
  } catch (error) {
    reportBackgroundError('read_owner', error);
    return null;
  }
}

function ownerMatches(owner: BackgroundSearchOwner | null, snapshot: BackgroundSearchSnapshot): boolean {
  return !!owner && owner.query === snapshot.query && owner.token === snapshot.token;
}

export async function claimBackgroundSearch(snapshot: BackgroundSearchSnapshot): Promise<void> {
  const normalized = parseBackgroundSearchSnapshot(snapshot);
  if (!normalized || !normalized.token) throw new Error('invalid_background_claim');
  await AsyncStorage.multiSet([
    [OWNER_KEY, JSON.stringify({ query: normalized.query, token: normalized.token })],
    [PROGRESS_KEY, JSON.stringify(normalized)],
  ]);
  await AsyncStorage.removeItem(RESULT_KEY);
  emitSnapshot(normalized);
}

export async function saveBackgroundSearchResult(
  snapshot: BackgroundSearchSnapshot,
): Promise<boolean> {
  const normalized = parseBackgroundSearchSnapshot(snapshot);
  if (!normalized) throw new Error('invalid_background_result');
  const owner = await getBackgroundSearchOwner();
  if (!ownerMatches(owner, normalized)) return false;
  const encoded = JSON.stringify(normalized);
  await AsyncStorage.multiSet([
    [RESULT_KEY, encoded],
    [PROGRESS_KEY, encoded],
  ]);
  emitSnapshot(normalized);
  return true;
}

export async function saveBackgroundSearchProgress(
  snapshot: BackgroundSearchSnapshot,
): Promise<boolean> {
  const normalized = parseBackgroundSearchSnapshot(snapshot);
  if (!normalized) throw new Error('invalid_background_progress');
  const owner = await getBackgroundSearchOwner();
  if (!ownerMatches(owner, normalized)) return false;
  await AsyncStorage.setItem(PROGRESS_KEY, JSON.stringify(normalized));
  emitSnapshot(normalized);
  return true;
}

export async function getBackgroundSearchSnapshot(): Promise<BackgroundSearchSnapshot | null> {
  const raw = await AsyncStorage.getItem(PROGRESS_KEY);
  if (!raw) return null;
  try {
    return parseBackgroundSearchSnapshot(JSON.parse(raw));
  } catch (error) {
    reportBackgroundError('read_progress', error);
    return null;
  }
}

export async function consumeBackgroundSearchResult(): Promise<BackgroundSearchSnapshot | null> {
  const raw = await AsyncStorage.getItem(RESULT_KEY);
  if (!raw) return null;
  try {
    const snapshot = parseBackgroundSearchSnapshot(JSON.parse(raw));
    if (snapshot) await clearBackgroundSearchState(snapshot.query, snapshot.token);
    return snapshot;
  } catch (error) {
    reportBackgroundError('consume_result', error);
    return null;
  }
}

export async function clearBackgroundSearchState(
  query = '',
  token = 0,
): Promise<boolean> {
  const owner = await getBackgroundSearchOwner();
  if (query && token && owner && (owner.query !== query || owner.token !== token)) {
    return false;
  }
  await AsyncStorage.multiRemove([OWNER_KEY, RESULT_KEY, PROGRESS_KEY]);
  return true;
}

export function registerBackgroundSearchTask() {
  if (_registered) return;
  _registered = true;
  AppRegistry.registerHeadlessTask(
    TASK_NAME,
    () => async (data: { query?: string; token?: number; searchId?: string }) => {
      const term = data?.query?.trim();
      const token = typeof data?.token === 'number' ? Math.trunc(data.token) : 0;
      const passedSearchId = typeof data?.searchId === 'string' ? data.searchId : '';
      if (!term) {
        if (token) await stopSearchKeepAlive(token).catch(() => {});
        return;
      }

      const startedAt = Date.now();
      let sourceCount = 0;
      let doneCount = 0;
      let liveResults = [] as BackgroundSearchSnapshot['results'];
      let searchId = passedSearchId;
      let lastSavedAt = 0;
      let lastSavedDone = -1;
      let persistChain = Promise.resolve();
      let ownershipLost = false;

      const makeSnapshot = (
        searching: boolean,
        completed: boolean,
        error?: string,
      ): BackgroundSearchSnapshot => ({
        query: term,
        token,
        searchId: searchId || undefined,
        updatedAt: new Date().toISOString(),
        startedAt,
        sourceCount,
        doneCount,
        searching,
        completed,
        resultCount: liveResults.length,
        results: liveResults,
        error,
      });

      const queueProgressSave = (force = false) => {
        const now = Date.now();
        if (
          !force &&
          now - lastSavedAt < PROGRESS_SAVE_INTERVAL_MS &&
          doneCount - lastSavedDone < PROGRESS_SAVE_SOURCE_STEP
        ) {
          return;
        }
        lastSavedAt = now;
        lastSavedDone = doneCount;
        const snapshot = makeSnapshot(true, false);
        persistChain = persistChain
          .then(async () => {
            const saved = await saveBackgroundSearchProgress(snapshot);
            if (!saved) ownershipLost = true;
          })
          .catch((error) => {
            reportBackgroundError('save_progress', error, { searchId, query: term, token });
          });
      };

      try {
        const inherited = await getBackgroundSearchSnapshot();
        if (inherited && backgroundSnapshotMatches(inherited, term, token)) {
          liveResults = inherited.results;
          searchId = searchId || inherited.searchId || '';
          sourceCount = inherited.sourceCount;
          doneCount = inherited.doneCount;
        }

        const ownsSearch = await saveBackgroundSearchProgress(makeSnapshot(true, false));
        if (!ownsSearch) throw new Error('background_ownership_lost');
        await loadSourceStats();
        const sources = await loadUsableSources();
        const backgroundSources = sources.filter((rule: any) => {
          const origin = typeof rule?.site?.origin === 'string' ? rule.site.origin : '';
          return !rule?.search?.requires_browser && !VerifyManager.isVerifyOrigin(origin);
        });
        sourceCount = backgroundSources.length;
        doneCount = 0;
        queueProgressSave(true);
        setBackgroundNetworkMode(true);

        const result = await runSearchTask({
          term,
          sources: backgroundSources,
          backgroundMode: true,
          shouldAbort: () => ownershipLost,
          onProgress: (nextDoneCount, nextSourceCount) => {
            doneCount = nextDoneCount;
            sourceCount = nextSourceCount;
            queueProgressSave(nextDoneCount === nextSourceCount);
          },
          onItems: (items) => {
            if (items.length === 0) return;
            liveResults = mergeBackgroundSearchResults(liveResults, items, getResultStableId);
            queueProgressSave();
          },
        });

        doneCount = result.doneCount;
        sourceCount = result.sourceCount;
        liveResults = mergeBackgroundSearchResults(liveResults, result.results, getResultStableId);
        queueProgressSave(true);
        await persistChain;
        if (ownershipLost) return;

        if (searchId) {
          await trackSearchCompleted({
            searchId,
            term,
            sourceCount: result.sourceCount,
            doneCount: result.doneCount,
            resultCount: liveResults.length,
            aborted: result.aborted,
            background: true,
            durationMs: result.analytics.durationMs,
            timeToFirstResultMs: result.analytics.timeToFirstResultMs,
            sourceRollup: result.analytics.sourceRollup,
          }).catch((error) => {
            reportBackgroundError('track_complete', error, { searchId, query: term, token });
          });
          await flush().catch((error) => {
            reportBackgroundError('flush_analytics', error, { searchId, query: term, token });
          });
        }

        const savedResult = await saveBackgroundSearchResult(makeSnapshot(false, true));
        if (!savedResult) return;
        await notifySearchCompleted({
          query: term,
          resultCount: liveResults.length,
          sourceCount: result.sourceCount,
          elapsedMs: result.report.totalDurationMs || Date.now() - startedAt,
        }).catch((error) => {
          reportBackgroundError('notify_complete', error, { searchId, query: term, token });
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (message !== 'background_ownership_lost') {
          reportBackgroundError('headless_task', error, { searchId, query: term, token });
        }
        await persistChain;
        if (!ownershipLost && message !== 'background_ownership_lost') {
          await saveBackgroundSearchResult(makeSnapshot(false, true, message)).catch((saveError) => {
            reportBackgroundError('save_failure', saveError, { searchId, query: term, token });
          });
        }
      } finally {
        setBackgroundNetworkMode(false);
        if (token) await stopSearchKeepAlive(token).catch(() => {});
      }
    },
  );
}

export async function startBackgroundSearchHandoff(
  query: string,
  token: number,
  searchId = '',
): Promise<boolean> {
  const { handoffSearchToBackground } = await import('./searchKeepAlive');
  return handoffSearchToBackground(query, token, searchId);
}
