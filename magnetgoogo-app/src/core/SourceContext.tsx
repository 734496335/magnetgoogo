import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import {
  loadSources,
  loadMeta,
  syncSources,
  SourceMeta,
  SourceRule,
} from './secureSourceStore';

interface SourceState {
  sources: SourceRule[];
  meta: SourceMeta | null;
  loading: boolean;
  syncing: boolean;
  error: string | null;
  /** Transient toast message for sync events (auto-clears). */
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

  const showToast = useCallback((msg: string, durationMs = 3000) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setSyncToast(msg);
    toastTimer.current = setTimeout(() => setSyncToast(null), durationMs);
  }, []);

  const doSync = useCallback(async (silent: boolean) => {
    setSyncing(true);
    setError(null);
    if (!silent) showToast('正在同步数据源…', 10000);
    try {
      const { sources: fresh, meta: m } = await syncSources();
      setSources(fresh);
      setMeta(m);
      showToast(`已同步 ${fresh.length} 个数据源`);
    } catch (e: any) {
      setError(e.message);
      showToast(`同步失败: ${e.message}`, 4000);
    } finally {
      setSyncing(false);
    }
  }, [showToast]);

  // Load cached sources on mount; auto-sync if empty or expired
  useEffect(() => {
    (async () => {
      try {
        const cached = await loadSources();
        const m = await loadMeta();
        if (cached && cached.length > 0) {
          setSources(cached);
          if (m) setMeta(m);
          setLoading(false);
          return;
        }
      } catch (e: any) {
        console.log(`[SourceContext] Cache load error: ${e.message}`);
      }
      // No cached sources or cache expired → auto-sync
      setLoading(false);
      doSync(false);
    })();
  }, [doSync]);

  const refresh = useCallback(() => doSync(false), [doSync]);

  return (
    <Ctx.Provider value={{ sources, meta, loading, syncing, error, syncToast, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export const useSources = () => useContext(Ctx);
