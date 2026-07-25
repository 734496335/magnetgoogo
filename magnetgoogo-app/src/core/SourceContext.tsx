import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { loadMeta, loadSources, syncSources, type SourceMeta, type SourceRule } from './secureSourceStore';
import { trackSourceSyncResult } from './analytics';

interface SourceState {
  sources: SourceRule[];
  meta: SourceMeta | null;
  loading: boolean;
  syncing: boolean;
  error: string | null;
  syncToast: string | null;
  refresh: () => Promise<void>;
}

const Ctx = createContext<SourceState>({
  sources: [],
  meta: null,
  loading: true,
  syncing: false,
  error: null,
  syncToast: null,
  refresh: async () => {},
});

export function SourceProvider({ children }: { children: React.ReactNode }) {
  const [sources, setSources] = useState<SourceRule[]>([]);
  const [meta, setMeta] = useState<SourceMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncToast, setSyncToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sourceCountRef = useRef(0);
  const syncInFlightRef = useRef<Promise<void> | null>(null);

  const showToast = useCallback((msg: string, durationMs = 3000) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setSyncToast(msg);
    toastTimer.current = setTimeout(() => setSyncToast(null), durationMs);
  }, []);

  const doSync = useCallback((silent: boolean): Promise<void> => {
    if (syncInFlightRef.current) return syncInFlightRef.current;

    const task = (async () => {
      const startedAt = Date.now();
      setSyncing(true);
      setError(null);
      if (!silent) showToast('正在同步数据源...', 10000);
      try {
        const { sources: fresh, meta: nextMeta } = await syncSources();
        sourceCountRef.current = fresh.length;
        setSources(fresh);
        setMeta(nextMeta);
        if (!silent) showToast(`已同步 ${fresh.length} 个数据源`);
        void trackSourceSyncResult({
          mode: 'remote',
          success: true,
          sourceCount: fresh.length,
          durationMs: Date.now() - startedAt,
        });
      } catch (e: any) {
        const message = e?.message || 'sync_failed';
        setError(message);
        if (!silent) showToast(`同步失败: ${message}`, 4000);
        void trackSourceSyncResult({
          mode: 'remote',
          success: false,
          sourceCount: sourceCountRef.current,
          durationMs: Date.now() - startedAt,
          errorCode: message,
        });
      } finally {
        setSyncing(false);
        syncInFlightRef.current = null;
      }
    })();

    syncInFlightRef.current = task;
    return task;
  }, [showToast]);

  useEffect(() => {
    (async () => {
      try {
        const cached = await loadSources();
        const cachedMeta = await loadMeta();
        if (cached && cached.length > 0) {
          sourceCountRef.current = cached.length;
          setSources(cached);
          if (cachedMeta) setMeta(cachedMeta);
          void trackSourceSyncResult({ mode: 'cache', success: true, sourceCount: cached.length });
          setLoading(false);
          void doSync(true);
          return;
        }
      } catch {
        // fall through to remote sync
      }
      setLoading(false);
      void doSync(false);
    })();
  }, [doSync]);

  const refresh = useCallback(() => doSync(false), [doSync]);

  useEffect(() => () => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
  }, []);

  return (
    <Ctx.Provider value={{ sources, meta, loading, syncing, error, syncToast, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export const useSources = () => useContext(Ctx);
