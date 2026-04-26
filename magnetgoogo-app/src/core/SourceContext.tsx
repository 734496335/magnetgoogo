import React, { createContext, useContext, useEffect, useState } from 'react';
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
  refresh: () => Promise<void>;
}

const Ctx = createContext<SourceState>({
  sources: [],
  meta: null,
  loading: true,
  syncing: false,
  error: null,
  refresh: async () => {},
});

export function SourceProvider({ children }: { children: React.ReactNode }) {
  const [sources, setSources] = useState<SourceRule[]>([]);
  const [meta, setMeta] = useState<SourceMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load cached sources on mount
  useEffect(() => {
    (async () => {
      try {
        const cached = await loadSources();
        const m = await loadMeta();
        if (cached) setSources(cached);
        if (m) setMeta(m);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const refresh = async () => {
    setSyncing(true);
    setError(null);
    try {
      const { sources: fresh, meta: m } = await syncSources();
      setSources(fresh);
      setMeta(m);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <Ctx.Provider value={{ sources, meta, loading, syncing, error, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export const useSources = () => useContext(Ctx);
