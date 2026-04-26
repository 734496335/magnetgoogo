'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SearchOrchestrator } from '@/core/orchestrator';
import { MagnetResult } from '@/core/types';
import { DeviceFrame } from '@/features/magnetgoogo/components/DeviceFrame';
import { HomeScreen } from '@/features/magnetgoogo/components/HomeScreen';
import { ResultsScreen } from '@/features/magnetgoogo/components/ResultsScreen';
import { dedupeResults, SiteStatus, sortResults } from '@/features/magnetgoogo/models';

const orchestrator = new SearchOrchestrator();

export default function Home() {
  const [query, setQuery] = useState('');
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<MagnetResult[]>([]);
  const [statuses, setStatuses] = useState<Record<string, SiteStatus>>({});
  const [copiedMagnet, setCopiedMagnet] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const visibleResults = useMemo(() => sortResults(results).slice(0, 24), [results]);

  const stopTimer = useCallback(() => {
    if (!timerRef.current) return;
    clearInterval(timerRef.current);
    timerRef.current = null;
  }, []);

  const startTimer = useCallback(() => {
    const startedAt = Date.now();
    setElapsed(0);
    timerRef.current = setInterval(() => {
      setElapsed(Date.now() - startedAt);
    }, 120);
  }, []);

  useEffect(() => () => stopTimer(), [stopTimer]);

  const handleSearch = async (event?: React.FormEvent) => {
    event?.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || searching) return;

    setSearched(true);
    setSearching(true);
    setResults([]);
    setStatuses({});
    startTimer();

    try {
      await orchestrator.search(
        trimmed,
        (batch) => {
          const normalized = batch.map((result) => ({
            ...result,
            relevance: result.relevance ?? 0,
          }));
          setResults((previous) => dedupeResults(previous, normalized));
        },
        (site, status) => {
          setStatuses((previous) => ({ ...previous, [site]: status }));
        },
      );
    } catch (error) {
      console.error(error);
    } finally {
      stopTimer();
      setSearching(false);
    }
  };

  const handleResetSearch = useCallback(() => {
    orchestrator.cancel();
    stopTimer();
    setQuery('');
    setSearched(false);
    setSearching(false);
    setResults([]);
    setStatuses({});
    setElapsed(0);
  }, [stopTimer]);

  const handleCopyMagnet = useCallback(async (magnet: string) => {
    await navigator.clipboard.writeText(magnet);
    setCopiedMagnet(magnet);
    window.setTimeout(() => setCopiedMagnet(null), 1800);
  }, []);

  return (
    <main className="magnetgoogo-stage">
      <div className="magnetgoogo-noise" />
      <div className="magnetgoogo-aura magnetgoogo-aura-left" />
      <div className="magnetgoogo-aura magnetgoogo-aura-right" />
      <section className="mx-auto flex min-h-screen w-full max-w-[1420px] items-center justify-center px-4 py-8 md:px-10">
        <div className="grid w-full items-center gap-10 xl:grid-cols-[minmax(0,420px)_minmax(0,420px)] xl:justify-center xl:gap-16">
          <DeviceFrame>
            <HomeScreen
              query={query}
              onChange={setQuery}
              onSubmit={handleSearch}
              searching={searching}
            />
          </DeviceFrame>

          <DeviceFrame>
            <ResultsScreen
              query={query}
              searching={searching}
              searched={searched}
              results={visibleResults}
              copiedMagnet={copiedMagnet}
              elapsed={elapsed}
              statuses={statuses}
              onSubmit={handleSearch}
              onQueryChange={setQuery}
              onClear={handleResetSearch}
              onCopy={handleCopyMagnet}
            />
          </DeviceFrame>
        </div>
      </section>
    </main>
  );
}
