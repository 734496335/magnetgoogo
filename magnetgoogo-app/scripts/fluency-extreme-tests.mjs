#!/usr/bin/env node
/**
 * Fluency & card-load extreme condition tests (logic layer).
 * Mirrors magnetgoogo-app/app/search.tsx session sync / sort / debounce behavior.
 *
 * Run: node scripts/fluency-extreme-tests.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { extractInfoHash } from '../src/core/dedup.ts';
import { computeRelevance, getResultStableId, parseSizeBytes, toResultCardModel } from '../src/core/types.ts';
import {
  createSearchResultAccumulatorState,
  mergePendingSearchResults,
  rebuildSearchCardModels,
} from '../src/core/searchResultAccumulator.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, 'fluency-extreme-report.json');

// ─── production-backed helpers ──────────────────────────────────────
function toCard(r, query) {
  return {
    ...toResultCardModel(r, 0, query),
    bestSeeders: r.bestSeeders || r.seeders || 0,
  };
}

// ─── session simulator (search.tsx syncFromSession + debouncedSync) ──
function createSession(query) {
  return {
    query,
    rawResults: [],
    searching: true,
    sourceCount: 0,
    doneCount: 0,
    ...createSearchResultAccumulatorState(),
    notifyCount: 0,
    syncCount: 0,
    topKHistory: [],
  };
}

const accumulatorDeps = {
  extractInfoHash,
  getStableId: getResultStableId,
  computeRelevance,
  parseSizeBytes,
};

function rebuildSessionCards(s, forceFullSort) {
  rebuildSearchCardModels(s, {
    searching: s.searching,
    forceFullSort,
    query: s.query,
    extractInfoHash,
    getStableId: getResultStableId,
    buildCard: (result) => toCard(result, s.query),
  });
}

function processNewResults(s) {
  const listChanged = mergePendingSearchResults(s, s.rawResults, s.query, accumulatorDeps);
  if (!listChanged) return false;
  rebuildSessionCards(s, !s.searching && !s._finalSorted);
  return true;
}

function syncFromSession(s) {
  const hadNew = processNewResults(s);
  if (!hadNew && !s.searching && !s._finalSorted && s._dedupMap.size > 0) {
    rebuildSessionCards(s, true);
  }
  s.syncCount++;
  const top = s._cardModels.slice(0, 20).map((c) => c.id);
  s.topKHistory.push(top);
  return s._cardModels;
}

/** Debounce 500ms like app */
function makeDebouncedSync(s, delayMs = 500) {
  let timer = null;
  let pending = false;
  return {
    notify() {
      s.notifyCount++;
      if (timer) {
        pending = true;
        return;
      }
      timer = setTimeout(() => {
        timer = null;
        syncFromSession(s);
        if (pending) {
          pending = false;
          // trailing: schedule one more after delay (app only keeps one window)
          // match app: if already scheduled skip; trailing not re-armed until next notify
        }
      }, delayMs);
    },
    flush() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      syncFromSession(s);
    },
  };
}

// ─── data generators ─────────────────────────────────────────────────
function hashOf(i) {
  return i.toString(16).padStart(40, '0');
}

function magnetOf(i) {
  return `magnet:?xt=urn:btih:${hashOf(i)}&dn=title`;
}

function makeItem(i, source, overrides = {}) {
  return {
    title: overrides.title ?? `Inception 2010 1080p BluRay ${i}`,
    magnet: overrides.magnet ?? magnetOf(i),
    size: overrides.size ?? `${(i % 20) + 1}.${i % 9} GB`,
    seeders: overrides.seeders ?? (i % 50),
    leechers: overrides.leechers ?? 0,
    score: overrides.score ?? 0,
    fileCount: overrides.fileCount,
    source,
    site_name: source,
    date: overrides.date ?? '2024-01-01',
  };
}

// ─── metrics ─────────────────────────────────────────────────────────
function topKChurn(history, k = 20) {
  if (history.length < 2) return { moves: 0, samples: 0, rate: 0 };
  let moves = 0;
  let samples = 0;
  for (let t = 1; t < history.length; t++) {
    const prev = history[t - 1];
    const cur = history[t];
    const pos = new Map(cur.map((id, i) => [id, i]));
    for (let i = 0; i < Math.min(k, prev.length); i++) {
      const id = prev[i];
      if (!pos.has(id)) {
        moves += 1; // left topK
        samples++;
        continue;
      }
      const j = pos.get(id);
      if (Math.abs(j - i) >= 3) moves += 1; // jumped ≥3 slots
      samples++;
    }
  }
  return { moves, samples, rate: samples ? moves / samples : 0 };
}

function positionVariance(history, id) {
  const positions = [];
  for (const snap of history) {
    const i = snap.indexOf(id);
    if (i >= 0) positions.push(i);
  }
  if (positions.length < 2) return 0;
  const mean = positions.reduce((a, b) => a + b, 0) / positions.length;
  return positions.reduce((a, p) => a + (p - mean) ** 2, 0) / positions.length;
}

// ─── tests ───────────────────────────────────────────────────────────
const results = [];
function pass(id, name, detail = {}) {
  results.push({ id, name, ok: true, ...detail });
  console.log(`  PASS  ${id}  ${name}`);
}
function fail(id, name, reason, detail = {}) {
  results.push({ id, name, ok: false, reason, ...detail });
  console.log(`  FAIL  ${id}  ${name} — ${reason}`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function testD1_debounceCoalescing() {
  const s = createSession('Inception');
  const d = makeDebouncedSync(s, 50);
  // 30 notifies in <50ms window
  for (let i = 0; i < 30; i++) {
    s.rawResults.push(makeItem(i, `src${i % 5}`));
    d.notify();
  }
  await sleep(80);
  d.flush();
  // notify=30, sync should be ~1-2 not 30
  if (s.notifyCount === 30 && s.syncCount <= 3) {
    pass('D1', 'debounce coalesces burst notifies', {
      notifyCount: s.notifyCount,
      syncCount: s.syncCount,
    });
  } else {
    fail('D1', 'debounce coalesces burst notifies', `notify=${s.notifyCount} sync=${s.syncCount}`);
  }
}

async function testD2_idStabilityOnMerge() {
  const s = createSession('Inception');
  const d = makeDebouncedSync(s, 10);
  const shared = magnetOf(42);
  for (let src = 0; src < 15; src++) {
    s.rawResults.push(
      makeItem(42, `mirror${src}`, {
        magnet: shared,
        title: `Inception 1080p source ${src}`,
        seeders: src * 3,
      }),
    );
    d.notify();
    await sleep(15);
  }
  d.flush();
  const cards = s._cardModels.filter((c) => c.id === hashOf(42));
  if (cards.length === 1 && cards[0].sourceCount === 15 && cards[0].id === hashOf(42)) {
    pass('D2', 'same btih keeps stable id under multi-source merge', {
      sourceCount: cards[0].sourceCount,
      cardId: cards[0].id,
    });
  } else {
    fail('D2', 'same btih keeps stable id under multi-source merge', JSON.stringify({
      n: cards.length,
      sc: cards[0]?.sourceCount,
    }));
  }
}

async function testD2_uniqueSourceCount() {
  const s = createSession('Inception');
  const shared = magnetOf(77);
  s.rawResults.push(makeItem(77, 'same-source', { magnet: shared }));
  syncFromSession(s);
  const first = s._cardModels[0];

  s.rawResults.push(makeItem(77, 'same-source', { magnet: shared }));
  syncFromSession(s);
  const afterDuplicate = s._cardModels[0];
  const sameSourceStable =
    afterDuplicate === first &&
    afterDuplicate.sourceCount === 1 &&
    afterDuplicate.sourceNames.length === 1;

  s.rawResults.push(makeItem(77, 'second-source', { magnet: shared }));
  syncFromSession(s);
  const card = s._cardModels[0];
  if (sameSourceStable && card !== first && card.sourceCount === 2 && card.sourceNames.length === 2) {
    pass('D2b', 'sourceCount tracks unique sources and ignores identical duplicate rows');
  } else {
    fail('D2b', 'sourceCount tracks unique sources', JSON.stringify({
      duplicateKeptReference: afterDuplicate === first,
      secondSourceRefreshed: card !== first,
      sourceCount: card.sourceCount,
      sourceNames: card.sourceNames,
    }));
  }
}

async function testD3_topKChurnUnderDrip() {
  const s = createSession('Inception');
  // While searching: first-seen order — merges must NOT thrash top20
  for (let wave = 0; wave < 40; wave++) {
    for (let j = 0; j < 10; j++) {
      const id = (wave * 3 + j) % 120;
      s.rawResults.push(
        makeItem(id, `src${wave}`, {
          seeders: (wave * 7 + j) % 200,
          size: `${(id % 15) + 1}.0 GB`,
          title: `Inception 2010 ${id % 2 === 0 ? '1080p' : '720p'} #${id}`,
        }),
      );
    }
    syncFromSession(s);
  }
  const churnSearching = topKChurn(s.topKHistory, 20);
  // Finish search → one re-rank allowed
  s.searching = false;
  s._finalSorted = false;
  syncFromSession(s);
  // Expect near-zero thrash while searching (only appends of new ids)
  if (churnSearching.rate <= 0.35) {
    pass('D3', 'top20 churn while searching stays low (stable order)', {
      rate: Number(churnSearching.rate.toFixed(3)),
      moves: churnSearching.moves,
      samples: churnSearching.samples,
      syncs: s.syncCount,
      cards: s._cardModels.length,
    });
  } else {
    fail(
      'D3',
      'top20 churn while searching stays low (stable order)',
      `churn rate ${churnSearching.rate.toFixed(3)} too high`,
      churnSearching,
    );
  }
  return s;
}

async function testJ1_stableOrderWhileSearching() {
  const s = createSession('Inception');
  for (let i = 0; i < 15; i++) {
    s.rawResults.push(makeItem(i, 's0', { seeders: 1, size: '1.0 GB' }));
  }
  syncFromSession(s);
  const o1 = s._cardModels.map((c) => c.id);
  // Heavy merge upgrades — must keep order
  for (let i = 0; i < 15; i++) {
    s.rawResults.push(makeItem(i, 's1', { seeders: 500 - i, size: '50.0 GB' }));
  }
  syncFromSession(s);
  const o2 = s._cardModels.map((c) => c.id);
  s.rawResults.push(makeItem(99, 's2'));
  syncFromSession(s);
  const o3 = s._cardModels.map((c) => c.id);
  const stable =
    o1.join() === o2.join() &&
    o3.slice(0, 15).join() === o1.join() &&
    o3[o3.length - 1] === hashOf(99);
  if (stable) pass('J1fix', 'first-seen order frozen while searching (anti-jump)');
  else fail('J1fix', 'first-seen order frozen while searching (anti-jump)', 'order changed on merge');
}

async function testD4_cacheReuseUnlessDirty() {
  const s = createSession('test');
  s.rawResults.push(makeItem(1, 'a'));
  syncFromSession(s);
  const first = s._cardModels[0];
  s.rawResults.push(makeItem(2, 'b'));
  syncFromSession(s);
  const still = s._cardModels.find((c) => c.id === hashOf(1));
  // item 1 not dirty → same object reference from cache
  if (still === first) {
    pass('D4', 'card model cache reuses object when not dirty');
  } else {
    // implementation maps new array but cache should return same ref
    const cached = s._cardModelCache.get(hashOf(1));
    if (cached === first) pass('D4', 'card model cache reuses object when not dirty', { via: 'cache' });
    else fail('D4', 'card model cache reuses object when not dirty', 'cache miss rebuild');
  }
}

async function testD4_dirtyCardGetsFreshModel() {
  const s = createSession('Inception');
  const shared = magnetOf(88);
  s.rawResults.push(makeItem(88, 's1', {
    magnet: shared,
    title: 'misc release',
    size: '',
    date: '',
  }));
  syncFromSession(s);
  const first = s._cardModels[0];

  s.rawResults.push(makeItem(88, 's2', {
    magnet: shared,
    title: 'Inception 2010 1080p BluRay REMUX',
    size: '42 GB',
    date: '2026-07-24',
    fileCount: 12,
  }));
  syncFromSession(s);
  const refreshed = s._cardModels[0];
  const ok =
    refreshed !== first &&
    refreshed.id === first.id &&
    refreshed.title.includes('Inception') &&
    refreshed.sizeLabel === '42 GB' &&
    refreshed.dateLabel === '2026-07-24' &&
    refreshed.fileCountLabel.includes('12') &&
    refreshed.kind === 'movie' &&
    refreshed.tags.includes('1080P') &&
    refreshed.tags.includes('REMUX') &&
    refreshed.relevance === 100;
  if (ok) {
    pass('D4b', 'dirty card keeps stable id but refreshes object and derived fields');
  } else {
    fail('D4b', 'dirty card refreshes object and derived fields', JSON.stringify({
      sameRef: refreshed === first,
      idStable: refreshed.id === first.id,
      title: refreshed.title,
      size: refreshed.sizeLabel,
      date: refreshed.dateLabel,
      fileCount: refreshed.fileCountLabel,
      kind: refreshed.kind,
      tags: refreshed.tags,
      relevance: refreshed.relevance,
    }));
  }
}

async function testD5_noHashItems() {
  const s = createSession('x');
  s.rawResults.push({
    title: 'nohash item',
    magnet: 'magnet:?xt=urn:ed2k:abc&dn=x',
    size: '1 GB',
    source: 's1',
  });
  s.rawResults.push({
    title: 'nohash item duplicate',
    magnet: 'magnet:?xt=urn:ed2k:abc&dn=duplicate',
    size: '2 GB',
    source: 's1',
  });
  s.rawResults.push({
    title: 'missing magnet card',
    magnet: '',
    size: '',
    source: 's3',
  });
  s.rawResults.push(makeItem(9, 's2'));
  syncFromSession(s);
  const ids = s._cardModels.map((c) => c.id);
  const uniqueIds = new Set(ids).size === ids.length;
  const missingMagnetId = ids.find((id) => id.startsWith('no-magnet:s3:'));
  if (
    s._dedupMap.size === 1 &&
    s._noHashResults.length === 2 &&
    s._cardModels.length === 3 &&
    uniqueIds &&
    missingMagnetId
  ) {
    pass('D5', 'no-btih items dedupe with stable unique fallback ids');
  } else {
    fail('D5', 'no-btih items dedupe with stable ids', JSON.stringify({
      map: s._dedupMap.size,
      nohash: s._noHashResults.length,
      cards: s._cardModels.length,
      ids,
    }));
  }
}

async function testD6_sortStabilitySameKeys() {
  const s = createSession('Inception');
  // Identical sort keys → order should be deterministic across rebuilds
  for (let i = 0; i < 30; i++) {
    s.rawResults.push(
      makeItem(i, 's', {
        size: '10.0 GB',
        seeders: 10,
        title: `Inception 1080p copy ${i}`,
      }),
    );
  }
  syncFromSession(s);
  const a = s._cardModels.map((c) => c.id);
  // rebuild from scratch
  Object.assign(s, createSearchResultAccumulatorState());
  s.searching = false; // force full sort path for determinism check
  syncFromSession(s);
  const b = s._cardModels.map((c) => c.id);
  if (a.join() === b.join() && new Set(a).size === a.length) {
    pass('D6', 'rebuild yields deterministic order and complete membership', { n: a.length });
  } else {
    fail('D6', 'rebuild yields deterministic order and membership', `a=${a.join()} b=${b.join()}`);
  }
}

async function testJ3_largeSetPerf() {
  const s = createSession('big');
  const t0 = Date.now();
  for (let i = 0; i < 800; i++) {
    s.rawResults.push(makeItem(i, `src${i % 40}`, { size: `${(i % 50) + 1}.0 GB` }));
    if (i % 25 === 24) syncFromSession(s);
  }
  syncFromSession(s);
  const ms = Date.now() - t0;
  if (s._cardModels.length >= 800 && ms < 5000) {
    pass('J3', '800-item drip sync completes under 5s (logic)', { ms, n: s._cardModels.length });
  } else {
    fail('J3', '800-item drip sync completes under 5s (logic)', `ms=${ms} n=${s._cardModels.length}`);
  }
}

async function testJ7_sessionReplaceNoCrossTalk() {
  const s1 = createSession('A');
  s1.rawResults.push(makeItem(1, 's', { title: 'Movie A 1080p' }));
  syncFromSession(s1);
  const s2 = createSession('B');
  s2.rawResults.push(makeItem(2, 's', { title: 'Movie B 720p' }));
  syncFromSession(s2);
  if (
    s1._cardModels.every((c) => c.title.includes('A') || c.title.includes('Inception')) &&
    s2._cardModels[0].title.includes('B') &&
    s1._cardModels[0].id !== s2._cardModels[0].id
  ) {
    pass('J7', 'separate sessions do not cross-talk');
  } else {
    fail('J7', 'separate sessions do not cross-talk', 'titles mixed');
  }
}

async function testC4_indexAnimationRisk() {
  // When top-8 ids change between syncs, FlatList remount risk is high if keys change
  // We assert: ids are stable so keyExtractor shouldn't remount on title-only updates
  const s = createSession('Inception');
  for (let i = 0; i < 12; i++) s.rawResults.push(makeItem(i, 's1'));
  syncFromSession(s);
  const ids1 = s._cardModels.slice(0, 8).map((c) => c.id);
  // merge more sources onto same hashes — upgrade sourceCount only
  for (let i = 0; i < 12; i++) {
    s.rawResults.push(makeItem(i, 's2', { seeders: 99 }));
  }
  syncFromSession(s);
  const ids2 = s._cardModels.slice(0, 8).map((c) => c.id);
  const sameKeys = ids1.every((id) => ids2.includes(id));
  if (sameKeys) {
    pass('C4', 'top-8 ids remain stable on merge (animation remount risk low)', {
      ids1,
      ids2,
    });
  } else {
    fail('C4', 'top-8 ids remain stable on merge', 'top8 membership churned on merge-only update', {
      ids1,
      ids2,
    });
  }
}

async function testJ2_idNeverUsesArrayIndex() {
  const s = createSession('q');
  s.rawResults.push(makeItem(7, 'a'));
  s.rawResults.push(makeItem(3, 'b'));
  syncFromSession(s);
  const ids = s._cardModels.map((c) => c.id);
  if (ids.every((id) => /^[0-9a-f]{40}$/.test(id)) && !ids.includes('0') && !ids.includes('1')) {
    pass('J2', 'card id is btih not list index');
  } else {
    fail('J2', 'card id is btih not list index', ids.join(','));
  }
}

async function testS2_churnDiagnostic() {
  // Produce report metric for scroll-time updates: how bad is top10 thrash on heavy merge waves
  const s = createSession('Inception');
  for (let wave = 0; wave < 25; wave++) {
    for (let j = 0; j < 20; j++) {
      const id = j; // only 20 unique — heavy re-rank by seeders
      s.rawResults.push(
        makeItem(id, `w${wave}`, {
          seeders: Math.floor(Math.random() * 500),
          size: `${(j % 8) + 1}.0 GB`,
        }),
      );
    }
    syncFromSession(s);
  }
  const churn = topKChurn(s.topKHistory, 10);
  // This scenario is intentionally thrashy; pass always but flag if rate>0.5 for manual UI risk
  const risk = churn.rate > 0.5 ? 'HIGH' : churn.rate > 0.25 ? 'MED' : 'LOW';
  pass('S2', 'scroll-time rank thrash diagnostic (seeders random re-rank)', {
    rate: Number(churn.rate.toFixed(3)),
    risk,
    note: risk === 'HIGH' ? 'UI will jump unless sort is frozen while scrolling' : 'ok',
  });
}

async function testL1_restoreSessionShape() {
  // Simulate unmount: session kept; remount reads same card models
  const s = createSession('restore');
  for (let i = 0; i < 5; i++) s.rawResults.push(makeItem(i, 's'));
  syncFromSession(s);
  const snapshot = s._cardModels.map((c) => c.id);
  // "remount" only re-sync without clearing
  const again = syncFromSession(s).map((c) => c.id);
  if (snapshot.join() === again.join()) pass('L1', 'session restore yields same order');
  else fail('L1', 'session restore yields same order', 'mismatch');
}

async function testProductionContracts() {
  const searchPath = path.join(__dirname, '..', 'app', 'search.tsx');
  const accumulatorPath = path.join(__dirname, '..', 'src', 'core', 'searchResultAccumulator.ts');
  const runnerPath = path.join(__dirname, '..', 'src', 'core', 'searchRunner.ts');
  const source = fs.readFileSync(searchPath, 'utf8');
  const accumulator = fs.readFileSync(accumulatorPath, 'utf8');
  const runner = fs.readFileSync(runnerPath, 'utf8');
  const checks = {
    searchUsesSharedAccumulator:
      /mergePendingSearchResults\(s, s\.rawResults/.test(source) &&
      /rebuildSearchCardModels\(s/.test(source),
    noInPlaceCardMutation:
      !/cached\.(?:title|sourceCount|sizeLabel)\s*=/.test(source + accumulator),
    dirtyRebuildsThroughProductionMapper:
      /const model = options\.buildCard\(result, index\)/.test(accumulator) &&
      /state\._cardModelCache\.set\(key, model\)/.test(accumulator),
    comprehensiveUsesSessionOrder:
      /if \(sortKey === 'comprehensive'\) \{\s*return results;\s*\}/m.test(source),
    uniqueSourceCount:
      /existing\.sourceCount = existing\.sourceNames\.length/.test(accumulator),
    noHashStableDedup:
      /state\._noHashKeys\.has\(key\)/.test(accumulator) &&
      /deps\.getStableId\(result\)/.test(accumulator),
    dirtyOnlyWhenDataChanges:
      /if \(existingChanged\) \{\s*existing\._dirty = true;\s*listChanged = true;/m.test(accumulator),
    stopHonorsScrollDeferral:
      /One-shot comprehensive order on stop; honor scroll deferral\.\s*syncFromSession\(\);/m.test(source),
    runnerKeepsRankingMetadata:
      /seeders: r\.seeders/.test(runner) &&
      /leechers: r\.leechers/.test(runner) &&
      /score: r\.score/.test(runner),
  };
  const failedChecks = Object.entries(checks).filter(([, ok]) => !ok).map(([name]) => name);
  if (failedChecks.length === 0) {
    pass('PROD', 'production search path enforces immutable refresh and single-rank contracts', checks);
  } else {
    fail('PROD', 'production search path contracts', failedChecks.join(', '), checks);
  }
}

async function testPerfSyncCost() {
  const s = createSession('perf');
  for (let i = 0; i < 500; i++) s.rawResults.push(makeItem(i, `s${i % 10}`));
  const times = [];
  let complete = true;
  for (let k = 0; k < 10; k++) {
    Object.assign(s, createSearchResultAccumulatorState());
    s.searching = true;
    const t0 = process.hrtime.bigint();
    syncFromSession(s);
    const t1 = process.hrtime.bigint();
    times.push(Number(t1 - t0) / 1e6);
    complete = complete && s._cardModels.length === 500;
  }
  const avg = times.reduce((a, b) => a + b, 0) / times.length;
  if (complete && avg < 200) {
    pass('PERF', 'fresh full rebuild of 500 cards avg <200ms', { avgMs: Number(avg.toFixed(2)), times });
  } else {
    fail('PERF', 'fresh full rebuild of 500 cards avg <200ms', `complete=${complete} avg=${avg.toFixed(2)}ms`);
  }
}

// ─── main ────────────────────────────────────────────────────────────
async function main() {
  console.log('=== Fluency / card-load extreme tests ===\n');
  await testD1_debounceCoalescing();
  await testD2_idStabilityOnMerge();
  await testD2_uniqueSourceCount();
  await testJ1_stableOrderWhileSearching();
  await testD3_topKChurnUnderDrip();
  await testD4_cacheReuseUnlessDirty();
  await testD4_dirtyCardGetsFreshModel();
  await testD5_noHashItems();
  await testD6_sortStabilitySameKeys();
  await testJ3_largeSetPerf();
  await testJ7_sessionReplaceNoCrossTalk();
  await testC4_indexAnimationRisk();
  await testJ2_idNeverUsesArrayIndex();
  await testS2_churnDiagnostic();
  await testL1_restoreSessionShape();
  await testProductionContracts();
  await testPerfSyncCost();

  const failed = results.filter((r) => !r.ok);
  const report = {
    generated_at: new Date().toISOString(),
    total: results.length,
    passed: results.length - failed.length,
    failed: failed.length,
    results,
  };
  fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
  console.log(`\n=== ${report.passed}/${report.total} passed ===`);
  console.log(`report → ${OUT}`);
  if (failed.length) {
    console.log('\nFailed:');
    for (const f of failed) console.log(`  - ${f.id}: ${f.reason}`);
  }

  // Print UI risk summary from S2/D3
  const s2 = results.find((r) => r.id === 'S2');
  const d3 = results.find((r) => r.id === 'D3');
  console.log('\n--- UI risk summary ---');
  if (d3) console.log(`  D3 top20 churn rate: ${d3.rate} (lower better)`);
  if (s2) console.log(`  S2 re-rank thrash risk: ${s2.risk} (rate=${s2.rate})`);
  console.log('  Manual device tests still required for S1/C2/L2 (GPU/Choreographer).');

  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
