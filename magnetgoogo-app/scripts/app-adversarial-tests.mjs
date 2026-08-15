import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  ALL_LANGS,
  SEARCH_STATUS_DOTS_TOKEN,
  getTranslations,
  splitSearchingStatus,
} from '../src/core/i18n.ts';
import {
  extractTags,
  getResultStableId,
  guessKind,
  parseSizeBytes,
  parseSizeLabel,
  toResultCardModel,
  computeRelevance,
} from '../src/core/types.ts';
import { deduplicateResults, extractInfoHash } from '../src/core/dedup.ts';
import { parseResourceDateLabel } from '../src/core/resourceDate.ts';
import {
  mergeResourceFileCount,
  parseBoundFileCount,
  parseExplicitFileCount,
} from '../src/core/resourceFileCount.ts';
import {
  formatResourceSize,
  formatSsbcSize,
  parseFirstResourceSizeLabel,
  parseResourceSizeLabel,
  parseLabeledResourceSizeLabel,
  resolveBoundDetailResourceSize,
  resolveResourceSizeConsensus,
} from '../src/core/resourceSize.ts';
import {
  isHashPlaceholderTitle,
  recoverResultTitle,
} from '../src/core/searchResultTitle.ts';
import {
  createSearchResultAccumulatorState,
  mergePendingSearchResults,
  rebuildSearchCardModels,
} from '../src/core/searchResultAccumulator.ts';
import {
  sanitizeFavoriteItems,
  sanitizeHistoryItems,
} from '../src/core/storageSanitizers.ts';
import { compareSemver, isRemoteConfig } from '../src/core/configValidation.ts';
import { normalizeSearchTerm } from '../src/core/searchTerm.ts';
import { fetchAuthorityThenFallback } from '../src/core/sourceDeliveryPolicy.ts';
import {
  BACKGROUND_SEARCH_TASK_TIMEOUT_MS,
  backgroundSnapshotMatches,
  isBackgroundSearchTerminal,
  mergeBackgroundSearchResults,
  parseBackgroundSearchSnapshot,
} from '../src/core/backgroundSearchProtocol.ts';
import { buildAppShareMessage } from '../src/core/appShare.ts';
import {
  buildSourcePoolPlans,
  classifyQueryProfile,
  computeSourceLearningBoost,
  getSourceBenchmarkBoost,
  getSourcePoolKey,
  getSearchProgressStage,
  HIGH_RELEVANCE_THRESHOLD,
  summarizeSourceQuality,
} from '../src/core/searchQuality.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const read = (relative) => fs.readFileSync(path.join(ROOT, relative), 'utf8');
const results = [];

async function test(id, name, fn) {
  try {
    await fn();
    results.push({ id, name, pass: true });
    console.log(`  PASS  ${id}  ${name}`);
  } catch (error) {
    results.push({ id, name, pass: false, error: error instanceof Error ? error.message : String(error) });
    console.log(`  FAIL  ${id}  ${name}`);
    console.log(`        ${error instanceof Error ? error.stack || error.message : String(error)}`);
  }
}

console.log('=== App adversarial tests ===\n');

await test('Q1', 'search terms trim and collapse all whitespace', () => {
  assert.equal(normalizeSearchTerm('  Inception\n\t  2010  '), 'Inception 2010');
  assert.equal(normalizeSearchTerm(null), '');
});

await test('Q2', 'search term limit is 100 Unicode code points', () => {
  const value = normalizeSearchTerm(`${'😀'.repeat(120)}tail`);
  assert.equal(Array.from(value).length, 100);
  assert.equal(value, '😀'.repeat(100));
});

await test('S1', 'history sanitizer survives valid-but-wrong JSON shapes', () => {
  assert.deepEqual(sanitizeHistoryItems({ query: 'bad' }), []);
  const cleaned = sanitizeHistoryItems([
    null,
    { query: '  ubuntu  ', timestamp: 12 },
    { query: 'ubuntu', timestamp: 99 },
    { query: '', timestamp: 3 },
    { query: 'inception', timestamp: Number.NaN },
  ]);
  assert.deepEqual(cleaned, [
    { query: 'ubuntu', timestamp: 12 },
    { query: 'inception', timestamp: 0 },
  ]);
});

await test('S2', 'favorite sanitizer drops malformed and duplicate records', () => {
  const cleaned = sanitizeFavoriteItems([
    { magnet: '', title: 'bad' },
    { magnet: ' magnet:?xt=urn:btih:abc ', title: ' A ', id: '', size: 3 },
    { magnet: 'magnet:?xt=urn:btih:abc', title: 'duplicate' },
    { magnet: 'magnet:?xt=urn:btih:def', title: '', addedAt: -1 },
  ]);
  assert.equal(cleaned.length, 2);
  assert.equal(cleaned[0].title, 'A');
  assert.equal(cleaned[0].size, '');
  assert.equal(cleaned[1].title, 'magnet:?xt=urn:btih:def');
  assert.equal(cleaned[1].addedAt, 0);
});

await test('C1', 'semver comparison handles missing and prerelease parts', () => {
  assert.equal(compareSemver('0.1.14', '0.1.15'), -1);
  assert.equal(compareSemver('1.2', '1.2.0'), 0);
  assert.equal(compareSemver('2.0.0-beta.1', '1.9.9'), 1);
});

await test('C2', 'remote config rejects HTTP-200 garbage', () => {
  assert.equal(isRemoteConfig({ latest_version: '1.0.0' }), false);
  assert.equal(isRemoteConfig({ latest_version: '1', min_version: '1', download: { primary: '', mirrors: [3] } }), false);
  assert.equal(isRemoteConfig({
    latest_version: '1.0.0',
    min_version: '0.1.0',
    download: { primary: 'https://example.test/app.apk', mirrors: [] },
    announcement: '',
    source_expiry_hours: 24,
    source_schema_version: 1,
    updated_at: '2026-07-25T00:00:00Z',
  }), true);
});

await test('I1', 'all 10 languages expose every translation key', () => {
  const base = getTranslations('zh');
  const baseKeys = Object.keys(base).sort();
  for (const lang of ALL_LANGS) {
    const translation = getTranslations(lang);
    assert.deepEqual(Object.keys(translation).sort(), baseKeys, `${lang} key mismatch`);
    assert.equal(typeof translation.searchingStatus('fast', 3), 'string');
    assert.equal(typeof translation.searchingStatus('expanding', 3), 'string');
    assert.equal(typeof translation.searchingStatus('tail', 3), 'string');
    assert.equal(typeof translation.searchDoneStatus(3), 'string');
    assert.equal(typeof translation.fileCount(4), 'string');
  }
});

await test('I1B', 'search progress copy fits a single-line mobile status row in every language', () => {
  const screen = read('app/search.tsx');
  for (const lang of ALL_LANGS) {
    const translation = getTranslations(lang);
    for (const stage of ['fast', 'expanding', 'tail']) {
      const text = translation.searchingStatus(stage, 9999);
      const tokenCount = text.split(SEARCH_STATUS_DOTS_TOKEN).length - 1;
      assert.equal(tokenCount, 1, `${lang}/${stage} must contain exactly one animated-dots token: ${text}`);
      assert.doesNotMatch(text, /…/, `${lang}/${stage} must not contain a second static ellipsis`);
      const { before, after } = splitSearchingStatus(text);
      assert.equal(`${before}${after}`, text.replace(SEARCH_STATUS_DOTS_TOKEN, ''));
      assert.ok([...`${before}${after}`].length <= 30, `${lang}/${stage} too long: ${text}`);
    }
    assert.ok([...translation.searchDoneStatus(9999)].length <= 26, `${lang}/done too long`);
    assert.ok([...translation.stopSearch].length <= 6, `${lang}/stop too long`);
  }
  assert.deepEqual(splitSearchingStatus('before...after...duplicate'), {
    before: 'before',
    after: 'afterduplicate',
  });
  assert.match(screen, /\{t\.stopSearch\}/);
  assert.match(screen, /<SearchingStatus text=\{t\.searchingStatus\(progressStage, results\.length\)\} \/>/);
  assert.equal((screen.match(/<BouncingDots \/>/g) || []).length, 1);
  assert.match(screen, /searchingStatusCopy: \{[\s\S]*?flex: 1,[\s\S]*?minWidth: 0/);
  assert.match(screen, /cancelBtn: \{[\s\S]*?flexShrink: 0/);
});

await test('I2', 'home share action is localized, concise and uses the canonical website URL', () => {
  const component = read('src/components/FeedbackFAB.tsx');

  for (const lang of ALL_LANGS) {
    const translation = getTranslations(lang);
    const message = buildAppShareMessage(translation.shareMessage, 'https://magnetgoogo.com');
    assert.ok(translation.shareBtn.length > 0, `${lang} share button missing`);
    assert.ok(translation.shareDialogTitle.length > 0, `${lang} share title missing`);
    assert.ok(translation.shareFailed.length > 0, `${lang} share failure text missing`);
    assert.equal(message, `${translation.shareMessage}\nhttps://magnetgoogo.com`);
    assert.equal((message.match(/https:\/\/magnetgoogo\.com/g) || []).length, 1);
  }

  assert.match(component, /\bShare\.share\(/);
  assert.match(component, /buildAppShareMessage\(t\.shareMessage, WEBSITE_URL\)/);
  assert.match(component, /title: t\.shareDialogTitle/);
  assert.match(component, /showToast\(t\.shareFailed\)/);
  assert.match(component, /testID="home-feedback-button"/);
  assert.match(component, /testID="home-share-button"/);
  assert.ok(component.indexOf('home-feedback-button') < component.indexOf('home-share-button'));
  assert.equal((component.match(/style=\{styles\.fab\}/g) || []).length, 2);
  assert.doesNotMatch(component, /shareFab|shareFabLabel|#6DEDAD|#0B5D46/);
  assert.match(component, /fabRow: \{[\s\S]*?right: 16[\s\S]*?bottom: 24[\s\S]*?flexDirection: 'row'/);
  assert.match(component, /stage: 'open_native_share'/);
  assert.match(component, /error_code: 'NATIVE_SHARE_FAILED'/);
});

await test('I3', 'favorites are a persistent top utility and history stays below search', () => {
  const home = read('app/(tabs)/index.tsx');
  const favoriteIndex = home.indexOf('testID="home-favorites-button"');
  const heroIndex = home.indexOf('style={[styles.heroStage');
  const buttonIndex = home.indexOf('<FlowingGradientButton onPress={handleSearch}');
  const historyIndex = home.indexOf('{history.length > 0 && (');
  const feedbackIndex = home.indexOf('<FeedbackFAB />');

  assert.ok(favoriteIndex >= 0);
  assert.ok(heroIndex > favoriteIndex);
  assert.ok(buttonIndex > heroIndex);
  assert.ok(historyIndex > buttonIndex);
  assert.ok(feedbackIndex > historyIndex);
  assert.equal((home.match(/testID="home-favorites-button"/g) || []).length, 1);
  assert.equal((home.match(/\{history\.length > 0 && \(/g) || []).length, 1);
  assert.match(home, /onPress=\{\(\) => router\.push\('\/favorites'\)\}/);
  assert.match(home, /favorites\.length > 99 \? '99\+' : favorites\.length/);
  assert.match(home, /topUtilityBar: \{[\s\S]*?alignItems: 'flex-end'/);
  assert.match(home, /favoriteShortcut: \{[\s\S]*?minHeight: 38[\s\S]*?maxWidth: '72%'/);
  assert.match(home, /historyWrap: \{[\s\S]*?marginTop: 18/);
  assert.doesNotMatch(home, /secondaryArea|favEntry|handleSecondaryLayout/);
});

await test('I4', 'search results default to relevance and expose no comprehensive sort option', () => {
  const screen = read('app/search.tsx');
  assert.match(screen, /type SortKey = 'relevance' \| 'size' \| 'date';/);
  assert.match(screen, /useState<SortKey>\('relevance'\)/);
  assert.match(screen, /setSortKey\('relevance'\)/);
  assert.match(screen, /arr\.sort\(\(a, b\) => b\.relevance - a\.relevance\)/);
  assert.match(screen, /<SortChip label=\{t\.sortRelevance\} k="relevance" \/>/);
  assert.doesNotMatch(screen, /k="comprehensive"|sortComprehensive/);
  assert.match(screen, /if \(isScrollingRef\.current && !opts\?\.forceList\)/);
});

await test('M1', 'software version names are not misclassified as movies', () => {
  assert.equal(guessKind('Office2021 Professional Plus x64'), 'software');
  assert.equal(guessKind('Ubuntu2204 LTS amd64.iso'), 'software');
  assert.equal(guessKind('Photoshop2024 Portable x64'), 'software');
  assert.equal(guessKind('SSIS001 1080p'), 'movie');
});

await test('M2', 'DTS and resolution tags are both detected', () => {
  assert.deepEqual(extractTags('Movie DTS-HD MA 1080p'), ['1080P', 'DTS']);
});

await test('M3', 'binary, Chinese and bound detail sizes share one numeric authority', () => {
  assert.equal(parseSizeLabel('size=1.5 GiB'), '1.5 GB');
  assert.equal(parseSizeBytes('1.5 GiB'), 1.5 * 1024 ** 3);
  assert.equal(parseSizeBytes('1024 bytes'), 1024);
  assert.equal(parseResourceSizeLabel('183 Bytes'), '');
  assert.equal(parseExplicitFileCount('Files 13 related title 106.36 GB'), 13);
  assert.equal(parseExplicitFileCount('File Count: 2'), 2);
  assert.equal(parseExplicitFileCount('文件数量：8'), 8);
  assert.equal(parseExplicitFileCount('File Size 771.59 MB'), undefined);
  assert.equal(parseExplicitFileCount('Files 8.14 GB'), undefined);
  assert.equal(parseBoundFileCount('13'), 13);
  assert.equal(parseBoundFileCount('771.59 MB'), undefined);
  assert.equal(resolveBoundDetailResourceSize({
    hint: '',
    localText: '720p BluRay File size 1.07 GB',
    selectorTexts: ['720p', '1080p'],
    bodyText: 'File size 1.07 GB File size 1.85 GB',
    magnetCount: 2,
  }), '1.07 GB');
  assert.equal(resolveBoundDetailResourceSize({
    hint: '',
    localText: '',
    selectorTexts: ['720p', '1080p'],
    bodyText: 'File size 1.07 GB File size 1.85 GB',
    magnetCount: 2,
  }), '');
  assert.equal(resolveBoundDetailResourceSize({
    hint: '',
    localText: '',
    selectorTexts: [],
    bodyText: 'File size 1.07 GB',
    magnetCount: 1,
  }), '1.07 GB');
  const fileCountEngine = read('src/core/searchEngine.ts');
  assert.match(fileCountEngine, /detailSelectors\.fileCount[\s\S]*parseBoundFileCount/);
  assert.doesNotMatch(fileCountEngine, /parseExplicitFileCount\(getBodyText\(\)\)/);
  assert.match(fileCountEngine, /foundMagnets: Array<\{ magnet: string; element: any \| null \}>/);
  assert.match(fileCountEngine, /resolveBoundDetailResourceSize\(/);
  assert.match(fileCountEngine, /bodyText: foundMagnets\.length === 1 \? getBodyText\(\) : ''/);
  assert.deepEqual(mergeResourceFileCount(2, 2), { fileCount: 2, conflict: false });
  assert.deepEqual(mergeResourceFileCount(2, 8), { fileCount: undefined, conflict: true });
  assert.deepEqual(mergeResourceFileCount(undefined, 8, true), { fileCount: undefined, conflict: true });
  assert.equal(formatResourceSize(183), '');
  assert.equal(parseSizeLabel('样片 24.7MB / 种子总大小 23.5GB'), '23.5 GB');
  assert.equal(parseSizeBytes('总大小：23.5吉字节'), 23.5 * 1024 ** 3);
  assert.equal(parseSizeBytes('4K HDR'), 0);
  assert.equal(parseFirstResourceSizeLabel('bd55ff89a12f9f476c50fb046e0330402a7b5308'), '');
  assert.equal(parseFirstResourceSizeLabel('movie.mp44.32 GB'), '');
  assert.equal(parseFirstResourceSizeLabel('hash value 3f89b5eb5efd55ad8fc1461ebe3d3c588447f407 4.35 GB'), '4.35 GB');
  assert.equal(
    parseLabeledResourceSizeLabel('Size : 3.91 GB Files 13 related title 106.36 GB'),
    '3.91 GB',
  );
  assert.equal(formatSsbcSize('24672993', 'Movie.2160p'), '23.5 GB');
  assert.equal(formatSsbcSize('1556920320', 'Inception.2010_HDRip.avi'), '1.45 GB');
  assert.equal(formatSsbcSize('14504761241', 'Inception.2010.BDRip.1080p.mkv'), '13.5 GB');
  assert.equal(formatSsbcSize('1048576'), '');
  const engine = read('src/core/searchEngine.ts');
  assert.match(engine, /const size = formatSsbcSize\(t\.size, name\)/);
  assert.match(engine, /rejectedInvalidMagnets/);
  assert.match(engine, /INVALID_RESULT_MAGNET_PARSE/);
  assert.match(engine, /const infoHash = extractInfoHash\(item\.magnet\)/);
  assert.match(engine, /input\[value\^="magnet:"\]/);
  assert.match(engine, /\$\(el\)\.attr\('value'\)/);
  assert.match(engine, /\$\(el\)\.attr\('data-magnet'\)/);
  assert.doesNotMatch(engine, /const sizeBytes = parseInt\(t\.size, 10\)/);
  assert.match(engine, /const size = resolveBoundDetailResourceSize\(\{/);
  assert.match(engine, /localText: localSizeText/);
  assert.match(engine, /magnetCount: foundMagnets\.length/);
  assert.doesNotMatch(engine, /\$\(detailSelectors\.size\)\.first\(\)\.text\(\)/);
  assert.match(engine, /formatResourceSize\(Number\(item\.length\)\)/);
  assert.match(engine, /formatResourceSize\(Number\(item\.torrentSize\)\)/);
  assert.match(engine, /formatResourceSize\(Number\(item\.size\)\)/);
  assert.equal(parseResourceSizeLabel('49357914.48 GB'), '');
  assert.equal(parseSizeBytes('49357914.48 GB'), 0);
  assert.match(engine, /fileCount: Math\.max\(0, Math\.trunc\(Number\(row\.file_count/);
  assert.match(engine, /if \(Array\.isArray\(files\) && files\.length > 0\) fileCount = files\.length/);
  const runner = read('src/core/searchRunner.ts');
  assert.match(runner, /fileCount: item\.fileCount/);
  assert.equal(toResultCardModel({ title: 'x', magnet: 'm', size: '700 MiB' }, 0).sizeBytes, 700 * 1024 ** 2);
});

await test('M3D', 'date authority converts known formats and rejects field leakage', () => {
  assert.equal(parseResourceDateLabel('1339547627'), '2012-06-13');
  assert.equal(parseResourceDateLabel("May. 19th  '15"), '2015-05-19');
  assert.equal(parseResourceDateLabel('26 Июн 26'), '2026-06-26');
  assert.equal(parseResourceDateLabel('4 days, 21 hours', Date.UTC(2026, 7, 1)), '2026-07-27');
  assert.equal(parseResourceDateLabel('2026-08-03', Date.UTC(2026, 7, 1)), '2026-08-03');
  assert.equal(parseResourceDateLabel('2026/08/03', Date.UTC(2026, 7, 1)), '2026-08-03');
  assert.match(read('src/core/searchEngine.ts'), /finalized\.push\(\{ \.\.\.item, title, date: cleanDate\(item\.date\) \}\)/);
  assert.equal(parseResourceDateLabel('2026-08-04', Date.UTC(2026, 7, 1)), '');
  assert.equal(parseResourceDateLabel('1893456000', Date.UTC(2026, 7, 1)), '');
  assert.equal(parseResourceDateLabel('1.85 GB'), '');
  assert.equal(parseResourceDateLabel('148'), '');
  const leaked = toResultCardModel({ title: 'x', magnet: 'm', date: '148' }, 0);
  assert.equal(leaked.dateLabel, '');
  assert.equal(leaked.fileCountLabel, '');
  const explicit = toResultCardModel({ title: 'x', magnet: 'm', date: '148', fileCount: 6 }, 0);
  assert.equal(explicit.fileCountLabel, '文件数 6');
});

await test('M4', 'final model tie-break ranking understands binary units', () => {
  const state = createSearchResultAccumulatorState();
  const raw = [
    { title: 'A', magnet: `magnet:?xt=urn:btih:${'a'.repeat(40)}`, size: '900 MB', source: 's1' },
    { title: 'B', magnet: `magnet:?xt=urn:btih:${'b'.repeat(40)}`, size: '1 GiB', source: 's2' },
  ];
  mergePendingSearchResults(state, raw, 'x', {
    extractInfoHash,
    getStableId: getResultStableId,
    computeRelevance,
    parseSizeBytes,
  });
  rebuildSearchCardModels(state, {
    searching: false,
    forceFullSort: true,
    query: 'x',
    extractInfoHash,
    getStableId: getResultStableId,
    buildCard: (result, index) => toResultCardModel(result, index, 'x'),
  });
  assert.equal(state._cardModels[0].title, 'B');
});

await test('M4B', 'same-hash merges use source consensus instead of first or maximum size', () => {
  const hash = 'd'.repeat(40);
  const magnet = `magnet:?xt=urn:btih:${hash}`;
  const items = [
    { title: '消失的人 2160p', magnet, size: '27801.01 GB', source: 'glued-detail' },
    { title: '消失的人 2160p', magnet, size: '7 B', source: 'hash-fragment' },
    { title: '消失的人 2160p', magnet, size: '3.91 GB', source: 'source-a' },
    { title: '消失的人 2160p', magnet, size: '3.91 GB', source: 'source-b' },
    { title: '消失的人 2160p', magnet, size: '3.91 GB', source: 'source-c' },
  ];
  const state = createSearchResultAccumulatorState();
  mergePendingSearchResults(state, items, '消失的人', {
    extractInfoHash,
    getStableId: getResultStableId,
    computeRelevance,
    parseSizeBytes,
  });
  assert.equal(state._dedupMap.get(hash)?.size, '3.91 GB');
  const deduped = deduplicateResults(items);
  assert.equal(deduped[0].size, '3.91 GB');
  assert.equal(deduped[0].sourceCount, 5);
  const repeatedSource = deduplicateResults([items[2], { ...items[2] }]);
  assert.equal(repeatedSource[0].sourceCount, 1);
  assert.equal(resolveResourceSizeConsensus([
    { label: '24.7 MB', source: 'ssbc-old' },
    { label: '23.5 GB', source: 'ssbc-fixed' },
  ]), '23.5 GB');
  assert.equal(resolveResourceSizeConsensus([
    { label: '241367 B', source: 'bad-a' },
    { label: '10 GB', source: 'bad-b' },
    { label: '2.29 GB', source: 'good-a' },
    { label: '2.29 GB', source: 'good-b' },
    { label: '2.29 GB', source: 'good-c' },
  ]), '2.29 GB');
  const ambiguousRealWorld = [
    { label: '347.07 MB', source: '16mag' },
    { label: '8.14 GB', source: 'kd705' },
  ];
  assert.equal(resolveResourceSizeConsensus(ambiguousRealWorld), '');
  assert.equal(resolveResourceSizeConsensus([...ambiguousRealWorld].reverse()), '');
  const ambiguousExtreme = [
    { label: '10.49 GB', source: 'wuji' },
    { label: '1451.23 GB', source: '16mag' },
  ];
  assert.equal(resolveResourceSizeConsensus(ambiguousExtreme), '');
  assert.equal(resolveResourceSizeConsensus([...ambiguousExtreme].reverse()), '');
});

await test('M5', 'stable IDs canonicalize hex, Base32 and tracker order', () => {
  const hash = 'ABCDEF0123456789ABCDEF0123456789ABCDEF01';
  const a = getResultStableId({ title: 'A', magnet: `magnet:?xt=urn:btih:${hash}&tr=one` });
  const b = getResultStableId({ title: 'B', magnet: `magnet:?xt=urn:btih:${hash.toLowerCase()}&tr=two` });
  assert.equal(a, b);
  const base32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const canonical = extractInfoHash(`magnet:?xt=urn:btih:${base32}`);
  assert.ok(canonical);
  assert.equal(
    getResultStableId({ title: 'Base32', magnet: `magnet:?xt=urn:btih:${base32}` }),
    getResultStableId({ title: 'Hex', magnet: `magnet:?xt=urn:btih:${canonical}` }),
  );
});

await test('M5B', 'search title normalization removes malformed Unicode without restoring bad raw text', () => {
  const engine = read('src/core/searchEngine.ts');
  assert.match(engine, /function stripInvalidUnicode/);
  assert.match(engine, /codePoint !== 0xfffd/);
  assert.match(engine, /codePoint >= 0xd800 && codePoint <= 0xdfff/);
  assert.match(engine, /stripInvalidUnicode\(raw\)/);
  assert.doesNotMatch(engine, /\.trim\(\) \|\| raw/);
});

await test('M6', 'hash placeholders are recovered or rejected before reaching users', () => {
  const hash = '051EE026133C57DBAABBCCDDEEFF001122334455';
  const magnet = `magnet:?xt=urn:btih:${hash}`;
  const namedMagnet = `${magnet}&dn=Inception.2010.1080p.BluRay`;

  assert.equal(isHashPlaceholderTitle('Hash: 051EE026133C...', magnet), true);
  assert.equal(isHashPlaceholderTitle('586b35d6aecdd2976d8777b6952fa56f', magnet), true);
  assert.equal(isHashPlaceholderTitle(hash, magnet), true);
  assert.equal(isHashPlaceholderTitle(magnet, magnet), true);
  assert.equal(isHashPlaceholderTitle('Inception.2010.1080p', magnet), false);
  assert.equal(recoverResultTitle('Hash: 051EE026133C...', namedMagnet), 'Inception.2010.1080p.BluRay');
  assert.equal(recoverResultTitle('Download', namedMagnet), 'Inception.2010.1080p.BluRay');
  assert.equal(recoverResultTitle('https://bad.example/detail', namedMagnet), 'Inception.2010.1080p.BluRay');
  assert.equal(recoverResultTitle('Inception�2010', namedMagnet), 'Inception.2010.1080p.BluRay');
  assert.equal(recoverResultTitle(`${hash} - Inception.2010.1080p`, magnet), 'Inception.2010.1080p');
  assert.equal(recoverResultTitle('Hash: 051EE026133C...', magnet), null);
  assert.equal(recoverResultTitle('Download', magnet), null);
  assert.equal(recoverResultTitle(`(brute) magnet:?xt=urn:btih:${hash}`, magnet), null);
  assert.equal(recoverResultTitle('1917.2019.1080p', magnet), '1917.2019.1080p');

  const engine = read('src/core/searchEngine.ts');
  assert.doesNotMatch(engine, /title:\s*`Hash:/);
  assert.match(engine, /function magnetFromLooseValue/);
  assert.match(engine, /function parseStructuredSearchPayload/);
  assert.match(engine, /unresolvedHashCount/);
  assert.match(engine, /unboundEvidenceCount/);
  assert.match(engine, /rawMagnetEvidenceCount/);
  assert.match(engine, /const bareHashes = new Set/);
  assert.match(engine, /throw new Error\('EMPTY_SEARCH_RESPONSE'\)/);
  assert.match(engine, /Selector drift recovery/);
  assert.match(engine, /titleFromLooseValue/);
  assert.match(engine, /article\.item/);
  assert.match(engine, /tr\.list-entry/);
  assert.match(engine, /div\.bg-white\.rounded-lg\.border/);
  assert.match(engine, /recoverResultTitle\(candidate, m\[0\]\)/);
  assert.match(engine, /throw new Error\('INVALID_RESULT_TITLE_PARSE'\)/);
  assert.match(engine, /return finalizeSearchResults\(merged\)\.slice\(0, 20\)/);
  assert.doesNotMatch(engine, /const mag = `magnet:\?xt=urn:btih:\$\{hashHex\}`/);

  const sources = read('../sources.json');
  const sourcePayload = JSON.parse(sources);
  const proxyitRules = sourcePayload.rulesets
    .flatMap((ruleset) => ruleset.rules || [])
    .filter((rule) => rule?.quality?.pool_id === 'proxyit.de');
  assert.equal(proxyitRules.length, 85);
  assert.equal(proxyitRules.filter((rule) => rule?.health?.status === 'green').length, 0);
  assert.equal(proxyitRules.filter((rule) => (
    rule?.health?.status === 'yellow'
    && rule?.health?.status_detail === 'parsing_failed'
  )).length, 85);
  assert.match(sources, /tr\.list-entry:has\(a\[href\^=\\"magnet:/);
  assert.match(sources, /div\.bg-white\.rounded-lg\.border:has\(a\[href\^='magnet:'\]\)/);
  assert.match(sources, /h3 a\[href\^='\/torrent\/'\]/);

  const deviceTest = read('../scripts/test_k30s_search.py');
  assert.match(deviceTest, /def is_hash_placeholder_title/);
  assert.match(deviceTest, /Hash placeholder title gate: 0/);
  assert.match(deviceTest, /hash_placeholder_title_count/);
  assert.match(deviceTest, /audit_payload/);
  assert.match(deviceTest, /result_quality/);
  assert.match(deviceTest, /raise SystemExit\(2\)/);
});

await test('SQ1', 'source quality counts unique high-relevance results instead of raw volume', () => {
  const relevantHash = '1'.repeat(40);
  const summary = summarizeSourceQuality([
    { title: 'Inception 2010 1080p', magnet: `magnet:?xt=urn:btih:${relevantHash}` },
    { title: 'Inception duplicate mirror title', magnet: `magnet:?xt=urn:btih:${relevantHash}&tr=x` },
    { title: 'Unrelated Ubuntu ISO', magnet: `magnet:?xt=urn:btih:${'2'.repeat(40)}` },
    { title: 'Random archive', magnet: `magnet:?xt=urn:btih:${'3'.repeat(40)}` },
  ], 'Inception', computeRelevance);
  assert.equal(summary.uniqueResultCount, 3);
  assert.equal(summary.relevantResultCount, 1);
  assert.equal(summary.exactResultCount, 1);
  assert.equal(summary.relevancePrecision, 1 / 3);
  assert.equal(HIGH_RELEVANCE_THRESHOLD, 30);
});

await test('SQ2', 'pool plans collapse mirror hosts and preserve evidence-ranked candidate order', () => {
  const plans = buildSourcePoolPlans([
    {
      id: 'tpb-fallback',
      site: { origin: 'https://piratebay.party', brand: 'TPB' },
      quality: { pool_id: 'tpb', pool_role: 'fallback' },
    },
    {
      id: 'knaben-primary',
      site: { origin: 'https://knaben.eu' },
      quality: { pool_id: 'knaben', pool_role: 'primary' },
    },
    {
      id: 'tpb-primary',
      site: { origin: 'https://apibay.org' },
      quality: { pool_id: 'tpb', pool_role: 'primary' },
    },
  ]);
  assert.equal(plans.length, 2);
  const tpb = plans.find((plan) => plan.poolId === 'tpb');
  assert.ok(tpb);
  assert.equal(tpb.candidates.length, 2);
  assert.equal(tpb.candidates[0].id, 'tpb-fallback');
  assert.equal(tpb.candidates[1].id, 'tpb-primary');
  assert.equal(getSourcePoolKey(tpb.candidates[1]), 'tpb');
  assert.equal(getSourcePoolKey({
    site: { origin: 'https://thepiratebay.rocks', brand: 'The Pirate Bay' },
    quality: {},
  }), 'tpb');
  assert.equal(getSourcePoolKey({
    site: { origin: 'https://apibay.org', brand: 'TPB' },
    quality: {},
  }), 'tpb');
});

await test('SQ2B', 'trusted bait priors adapt cold-start pool ranking to query profile', () => {
  const btsow = { site: { origin: 'https://btsow.pics' }, quality: { pool_id: 'btsow' } };
  const tpb = { site: { origin: 'https://thepiratebay.bond' }, quality: { pool_id: 'tpb' } };
  const nyaa = { site: { origin: 'https://nyaa.digital' }, quality: { pool_id: 'nyaa' } };
  const proxyit = { site: { origin: 'https://zh.proxyit.de' }, quality: { pool_id: 'proxyit.de' } };
  assert.ok(getSourceBenchmarkBoost(btsow, '流浪地球') > getSourceBenchmarkBoost(tpb, '流浪地球'));
  assert.ok(getSourceBenchmarkBoost(tpb, 'Inception') > getSourceBenchmarkBoost(tpb, '流浪地球'));
  assert.ok(getSourceBenchmarkBoost(nyaa, '海贼王') > getSourceBenchmarkBoost(proxyit, '海贼王'));
  assert.ok(getSourceBenchmarkBoost(btsow, 'SSIS-001') > 0);
});

await test('SQ3', 'relevance yield and precision beat a noisy high-volume source', () => {
  const useful = computeSourceLearningBoost({
    successRate: 0.9,
    emptyRate: 0.05,
    failRate: 0.05,
    challengeRate: 0,
    avgMs: 900,
    relevantYield: 8,
    precision: 0.8,
    qualitySamples: 8,
  });
  const noisy = computeSourceLearningBoost({
    successRate: 1,
    emptyRate: 0,
    failRate: 0,
    challengeRate: 0,
    avgMs: 700,
    relevantYield: 1,
    precision: 0.02,
    qualitySamples: 8,
  });
  assert.ok(useful > noisy, `useful=${useful} noisy=${noisy}`);
});

await test('SQ4', 'search progress stages preserve the first 10-second fast window and switch to tail near completion', () => {
  assert.equal(classifyQueryProfile('SSIS-001'), 'code');
  assert.equal(classifyQueryProfile('流浪地球'), 'cjk');
  assert.equal(classifyQueryProfile('One Piece 海贼王'), 'mixed');
  assert.equal(getSearchProgressStage(9_999, 11, 53), 'fast');
  assert.equal(getSearchProgressStage(10_000, 5, 53), 'expanding');
  assert.equal(getSearchProgressStage(5_000, 12, 53), 'expanding');
  assert.equal(getSearchProgressStage(20_000, 40, 53), 'tail');
});

await test('SQ5', 'search execution completes every content pool and only falls back after a real failure', () => {
  const runner = read('src/core/searchRunner.ts');
  const stats = read('src/core/sourceStats.ts');
  assert.match(runner, /buildSourcePoolPlans\(allSources\)/);
  assert.match(runner, /for \(let index = 0; index < plan\.candidates\.length/);
  assert.match(runner, /if \(outcome !== 'failed'\)/);
  assert.doesNotMatch(runner, /isSearchSatisfied/);
  assert.doesNotMatch(runner, /MAX_HOST_ATTEMPTS_PER_POOL/);
  assert.match(runner, /relevant_results: qualitySummary\.relevantResultCount/);
  assert.match(runner, /getSourcePerfBoost\(a, term, ignoreLocalLearning\) - aTier \* 6/);
  assert.doesNotMatch(runner, /if \(aTier !== bTier\) return aTier - bTier;/);
  assert.match(stats, /const STORAGE_KEY = 'mg_source_stats_v1'/);
  assert.match(stats, /setTimeout\(async \(\) =>/);
  assert.match(stats, /classifyQueryProfile\(params\.query\)/);
  assert.doesNotMatch(stats, /rawQuery|queryHistory|searchTerms/);
});

await test('SQ5B', 'K30S benchmark mode exhaustively tests hosts without polluting user analytics', () => {
  const runner = read('src/core/searchRunner.ts');
  const screen = read('app/search.tsx');
  const k30s = read('../scripts/test_k30s_search.py');
  assert.match(runner, /exhaustive\s*\?\s*allSources\.map/);
  assert.doesNotMatch(runner, /isSearchSatisfied/);
  assert.equal((runner.match(/if \(!exhaustive\) \{\s*recordSourceRun\(rule,/g) || []).length, 2);
  assert.match(screen, /const exhaustiveBenchmark = benchmark === '1'/);
  assert.match(screen, /exhaustive: exhaustiveBenchmark/);
  assert.match(screen, /ignoreLocalLearning: coldStartTest/);
  assert.match(screen, /if \(!exhaustiveBenchmark\) \{\s*try \{\s*session\.searchId = await trackSearchSubmitted/s);
  assert.match(k30s, /BENCHMARK_QUERIES = \[/);
  assert.match(k30s, /\("Code title", "SSIS-001"\)/);
  assert.match(k30s, /uri \+= "&benchmark=1"/);
  assert.match(k30s, /uri \+= "&cold=1"/);
  assert.match(k30s, /--cold-start/);
  assert.match(k30s, /quoted_uri = shlex\.quote\(uri\)/);
});

await test('SQ5C', 'benchmark reports distinguish loaded inventory from attempted hosts and pools', () => {
  const runner = read('src/core/searchRunner.ts');
  const logger = read('src/core/searchDebugLogger.ts');
  const bench = read('src/core/sourceBenchRunner.ts');
  const debugServer = read('src/core/debugSearchServer.ts');
  const k30s = read('../scripts/test_k30s_search.py');
  assert.match(runner, /loadedPoolCount = new Set\(allSources\.map/);
  assert.match(runner, /sourcePackOrigin: sourceMeta\?\.remoteUrl/);
  assert.match(runner, /visibleItems = orderedUniqueItems\.filter\(\(\{ relevance \}\) => relevance >= HIGH_RELEVANCE_THRESHOLD\)/);
  assert.match(runner, /hash: extractInfoHash\(item\.magnet\) \|\| ''/);
  assert.doesNotMatch(runner, /hash: \(item\.magnet\.match\(\/btih:/);
  assert.match(logger, /canonical 40-char lowercase btih/);
  assert.match(logger, /attemptedHostCount: this\.sourceResults\.length/);
  assert.match(logger, /attemptedPoolCount: new Set/);
  assert.match(bench, /const hash = extractInfoHash\(r\.magnet\)/);
  assert.match(debugServer, /hash: extractInfoHash\(i\.magnet \|\| ''\) \|\| ''/);
  assert.equal(extractInfoHash('magnet:?xt=urn:btih:ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'), '00443214c74254b635cf84653a56d7c675be77df');
  assert.match(k30s, /--append/);
  assert.match(k30s, /runtime_loaded_host_counts/);
});

await test('SQ5D', 'aborted handoffs stay partial and search reports are Debug-package only', () => {
  const runner = read('src/core/searchRunner.ts');
  const logger = read('src/core/searchDebugLogger.ts');
  const k30s = read('../scripts/test_k30s_search.py');
  assert.match(runner, /debugReport\.finish\(!aborted\(\)\)/);
  assert.match(logger, /Application\.applicationId\?\.endsWith\('\.debug'\) === true/);
  assert.match(logger, /finish\(completed = true\)/);
  assert.match(logger, /this\._upsertCurrent\(completed\)/);
  assert.match(k30s, /report_data\.get\("completed"\) is True/);
  assert.match(k30s, /svc", "power", "stayon", "true"/);
});

await test('SQ6', 'final model rank keeps high-relevance results above low-relevance multi-source noise', () => {
  const state = createSearchResultAccumulatorState();
  const relevant = { title: 'Inception 2010', magnet: `magnet:?xt=urn:btih:${'4'.repeat(40)}`, source: 'good' };
  const noisyHash = '5'.repeat(40);
  const noisy = [
    { title: 'Random Ubuntu ISO', magnet: `magnet:?xt=urn:btih:${noisyHash}`, source: 'n1' },
    { title: 'Random Ubuntu ISO', magnet: `magnet:?xt=urn:btih:${noisyHash}&tr=x`, source: 'n2' },
    { title: 'Random Ubuntu ISO', magnet: `magnet:?xt=urn:btih:${noisyHash}&tr=y`, source: 'n3' },
  ];
  mergePendingSearchResults(state, [relevant, ...noisy], 'Inception', {
    extractInfoHash,
    getStableId: getResultStableId,
    computeRelevance,
    parseSizeBytes,
  });
  rebuildSearchCardModels(state, {
    searching: false,
    forceFullSort: true,
    query: 'Inception',
    extractInfoHash,
    getStableId: getResultStableId,
    buildCard: (result, index) => toResultCardModel(result, index, 'Inception'),
  });
  assert.equal(state._cardModels[0].title, 'Inception 2010');
});

await test('P1', 'source startup effect is stable and sync is single-flight', () => {
  const code = read('src/core/SourceContext.tsx');
  assert.match(code, /syncInFlightRef/);
  assert.match(code, /if \(syncInFlightRef\.current\) return syncInFlightRef\.current/);
  assert.doesNotMatch(code, /\}, \[showToast, sources\.length\]\)/);
  assert.match(code, /if \(!silent\) showToast\(`已同步/);
});

await test('P1B', 'expired encrypted source packs are rejected on disk, debug override and remote sync', () => {
  const code = read('src/core/secureSourceStore.ts');
  assert.match(code, /function assertFreshEnvelope/);
  assert.match(code, /assertFreshEnvelope\(raw, 'disk source cache'\)/);
  assert.match(code, /assertFreshEnvelope\(envelope, 'debug source pack'\)/);
  assert.match(code, /assertFreshEnvelope\(raw, `remote source pack from \$\{base\}`\)/);
  assert.match(code, /SOURCE_EXPIRY_GRACE_MS/);
  assert.doesNotMatch(code, /source-quarantine\.json/);
  const canonicalSources = JSON.parse(read('../sources.json'));
  const u3c3 = canonicalSources.rulesets.flatMap((ruleset) => ruleset.rules)
    .find((rule) => rule.id === 'magnet_u3c3_com');
  assert.equal(u3c3?.health?.status, 'yellow');
  assert.equal(u3c3?.health?.status_detail, 'parsing_failed');
});

await test('P1C', 'source renewal cannot let a fast stale mirror beat a healthy authority tier', async () => {
  const code = read('src/core/secureSourceStore.ts');
  assert.match(code, /const authoritativeEndpoints = url[\s\S]*?\[CN_BASE, RAW_BASE, GATEWAY_BASE\]/);
  assert.match(code, /const fallbackEndpoints = url[\s\S]*?\[CN_ALI, CDN_BASE, GATEWAY_OLD\]/);
  assert.match(code, /fetchAuthorityThenFallback\(/);
  assert.doesNotMatch(code, /\[CN_BASE, GATEWAY_BASE, CDN_BASE, RAW_BASE, GATEWAY_OLD, CN_ALI\]/);

  const healthyOrder = [];
  const fresh = await fetchAuthorityThenFallback(
    ['authority-a', 'authority-b'],
    ['stale-fast-mirror'],
    async (endpoint) => {
      healthyOrder.push(endpoint);
      if (endpoint === 'authority-a') {
        return new Promise((resolve) => setTimeout(() => resolve('fresh-authority'), 40));
      }
      return new Promise((resolve) => setTimeout(() => resolve('stale-mirror'), 5));
    },
  );
  assert.equal(fresh, 'fresh-authority');
  assert.deepEqual(healthyOrder, ['authority-a']);

  const validationOrder = [];
  const recoveredAuthority = await fetchAuthorityThenFallback(
    ['invalid-fast-authority', 'fresh-slow-authority'],
    ['stale-fast-mirror'],
    async (endpoint) => {
      validationOrder.push(endpoint);
      if (endpoint === 'invalid-fast-authority') {
        await new Promise((resolve) => setTimeout(resolve, 5));
        throw new Error('expired-envelope');
      }
      if (endpoint === 'fresh-slow-authority') {
        return new Promise((resolve) => setTimeout(() => resolve('fresh-slow-authority'), 40));
      }
      return 'stale-mirror';
    },
  );
  assert.equal(recoveredAuthority, 'fresh-slow-authority');
  assert.deepEqual(validationOrder, ['invalid-fast-authority', 'fresh-slow-authority']);

  const fallbackOrder = [];
  const recovered = await fetchAuthorityThenFallback(
    ['authority-a', 'authority-b'],
    ['mirror-a', 'mirror-b'],
    async (endpoint) => {
      fallbackOrder.push(endpoint);
      if (endpoint === 'mirror-b') return 'mirror-b-fresh';
      throw new Error(`${endpoint}-down`);
    },
  );
  assert.equal(recovered, 'mirror-b-fresh');
  assert.deepEqual(fallbackOrder, ['authority-a', 'authority-b', 'mirror-a', 'mirror-b']);
});

await test('P2', 'Chinese sync failures use the error visual state', () => {
  const code = read('app/_layout.tsx');
  assert.match(code, /includes\('失败'\)/);
  assert.doesNotMatch(code, /澶辫触/);
});

await test('R1', 'new searches invalidate stale asynchronous starts', () => {
  const code = read('app/search.tsx');
  assert.match(code, /let _searchGeneration = 0/);
  assert.match(code, /const generation = \+\+_searchGeneration/);
  assert.match(code, /_session !== session \|\| generation !== _searchGeneration/);
  assert.match(code, /Promise\.allSettled\(\[\s*exhaustiveBenchmark \? Promise\.resolve\(\) : addHistory\(normalizedTerm\),\s*loadSourceStats\(\)/s);
});

await test('R2', 'analytics failures cannot block searches', () => {
  const code = read('app/search.tsx');
  assert.match(code, /Analytics must never block the actual search/);
  assert.match(code, /trackSearchCompleted\([\s\S]*?\)\.catch\(\(\) => \{\}\)/);
});

await test('R3', 'route, history, engine and analytics use canonical search terms', () => {
  const code = read('app/search.tsx');
  assert.match(code, /const normalizedTerm = normalizeSearchTerm\(term\)/);
  assert.match(code, /term: normalizedTerm/);
  assert.match(code, /query: normalizedTerm/);
  assert.match(code, /const routeQuery = normalizeSearchTerm\(q\)/);
});

await test('R4', 'native keepalive stop is token-aware', () => {
  const js = read('src/core/searchKeepAlive.ts');
  const module = read('android/app/src/main/java/com/magnetgoogo/app/SearchKeepAliveModule.kt');
  const service = read('android/app/src/main/java/com/magnetgoogo/app/SearchKeepAliveService.kt');
  assert.match(js, /nativeModule\.start\([^\n]+token\)/);
  assert.match(js, /nativeModule\.stop\(token\)/);
  assert.match(module, /EXTRA_TOKEN, tokenInt/);
  assert.match(service, /requestedToken != activeToken/);
});

await test('B1', 'background snapshots preserve partial results and terminal state', () => {
  const snapshot = parseBackgroundSearchSnapshot({
    query: ' Inception ',
    token: 7,
    searchId: 'search-1',
    updatedAt: '2026-07-25T00:00:00.000Z',
    sourceCount: 100,
    doneCount: 12,
    completedPoolCount: 9,
    totalPoolCount: 53,
    searching: true,
    completed: false,
    results: [
      { title: 'Inception 2010', magnet: `magnet:?xt=urn:btih:${'a'.repeat(40)}` },
      null,
    ],
  });
  assert.ok(snapshot);
  assert.equal(snapshot.query, 'Inception');
  assert.equal(snapshot.resultCount, 1);
  assert.equal(snapshot.completedPoolCount, 9);
  assert.equal(snapshot.totalPoolCount, 53);
  assert.equal(backgroundSnapshotMatches(snapshot, 'Inception', 7), true);
  assert.equal(backgroundSnapshotMatches(snapshot, 'Inception', 8), false);
  assert.equal(backgroundSnapshotMatches(snapshot, 'Inception', 0), false);
  assert.equal(isBackgroundSearchTerminal(snapshot), false);
  const terminal = parseBackgroundSearchSnapshot({ ...snapshot, searching: false, completed: true });
  assert.ok(terminal);
  assert.equal(isBackgroundSearchTerminal(terminal), true);
});

await test('B2', 'background result merge is stable and deduplicates repeated sources', () => {
  const hash = 'b'.repeat(40);
  const merged = mergeBackgroundSearchResults(
    [{ title: 'Short', magnet: `magnet:?xt=urn:btih:${hash}`, seeders: 2 }],
    [
      { title: 'Longer title', magnet: `magnet:?xt=urn:btih:${hash}&tr=x`, size: '1 GiB', seeders: 8 },
      { title: 'Other', magnet: `magnet:?xt=urn:btih:${'c'.repeat(40)}` },
    ],
    getResultStableId,
  );
  assert.equal(merged.length, 2);
  assert.equal(merged[0].title, 'Longer title');
  assert.equal(merged[0].size, '1 GB');
  assert.equal(merged[0].seeders, 8);

  let sizeConflict = mergeBackgroundSearchResults(
    [{ title: 'Same', magnet: `magnet:?xt=urn:btih:${hash}`, size: '27801.01 GB', source: 'bad-a' }],
    [{ title: 'Same', magnet: `magnet:?xt=urn:btih:${hash}`, size: '7 B', source: 'bad-b' }],
    getResultStableId,
  );
  sizeConflict = mergeBackgroundSearchResults(sizeConflict, [
    { title: 'Same', magnet: `magnet:?xt=urn:btih:${hash}`, size: '3.91 GB', source: 'good-a' },
    { title: 'Same', magnet: `magnet:?xt=urn:btih:${hash}`, size: '3.91 GB', source: 'good-b' },
    { title: 'Same', magnet: `magnet:?xt=urn:btih:${hash}`, size: '3.91 GB', source: 'good-c' },
  ], getResultStableId);
  assert.equal(sizeConflict[0].size, '3.91 GB');
  assert.equal(sizeConflict[0]._sizeObservations?.length, 5);
});

await test('B3', 'background observation does not expire after twenty seconds', () => {
  const screen = read('app/search.tsx');
  const background = read('src/core/backgroundSearch.ts');
  assert.equal(BACKGROUND_SEARCH_TASK_TIMEOUT_MS, 30 * 60 * 1000);
  assert.match(screen, /BACKGROUND_SEARCH_TASK_TIMEOUT_MS/);
  assert.match(screen, /subscribeBackgroundSearch/);
  assert.match(screen, /claimBackgroundSearch\(handoffSnapshot\)/);
  assert.doesNotMatch(screen, /setTimeout\([\s\S]{0,120}20000/);
  assert.match(background, /resultCount: liveResults\.length/);
  assert.match(background, /results: liveResults/);
  assert.match(background, /mergeBackgroundSearchResults\(liveResults, items, getResultStableId\)/);
});

await test('B4', 'headless task receives analytics identity and has token-aware cleanup', () => {
  const js = read('src/core/searchKeepAlive.ts');
  const module = read('android/app/src/main/java/com/magnetgoogo/app/SearchKeepAliveModule.kt');
  const service = read('android/app/src/main/java/com/magnetgoogo/app/SearchHeadlessService.kt');
  assert.match(js, /nativeModule\.handoff\(query\.trim\(\), token, searchId\)/);
  assert.match(module, /EXTRA_SEARCH_ID, searchId/);
  assert.match(module, /SearchHeadlessService\.ACTION_STOP/);
  assert.match(service, /requestedToken == activeToken/);
  assert.match(service, /putString\(EXTRA_SEARCH_ID, searchId\)/);
});

await test('B5', 'new background owners fence stale task progress and results', () => {
  const screen = read('app/search.tsx');
  const background = read('src/core/backgroundSearch.ts');
  const service = read('android/app/src/main/java/com/magnetgoogo/app/SearchHeadlessService.kt');
  assert.match(background, /const OWNER_KEY = 'mg_background_search_owner'/);
  assert.match(background, /if \(!ownerMatches\(owner, normalized\)\) return false/);
  assert.match(background, /let ownershipLost = false/);
  assert.match(background, /shouldAbort: \(\) => ownershipLost/);
  assert.match(screen, /clearBackgroundSearchState\(previousQuery, previousToken\)/);
  assert.match(screen, /previousToken \? stopSearchKeepAlive\(previousToken\)/);
  assert.match(service, /ignore stale stop token=/);
  assert.match(service, /return START_NOT_STICKY/);
});

await test('B6', 'background native bridge is represented by a tracked Expo prebuild plugin', () => {
  const appConfig = read('app.json');
  const plugin = read('plugins/with-search-background.js');
  assert.match(appConfig, /\.\/plugins\/with-search-background/);
  assert.match(plugin, /withAndroidManifest/);
  assert.match(plugin, /withMainApplication/);
  assert.match(plugin, /withDangerousMod/);
  assert.match(plugin, /add\(SearchKeepAlivePackage\(\)\)/);
  assert.match(plugin, /FOREGROUND_SERVICE_DATA_SYNC/);
  for (const file of [
    'SearchKeepAlivePackage.kt',
    'SearchKeepAliveModule.kt',
    'SearchKeepAliveService.kt',
    'SearchHeadlessService.kt',
  ]) {
    assert.equal(
      fs.existsSync(path.join(ROOT, 'plugins', 'search-background', `${file}.template`)),
      true,
      `${file} template missing`,
    );
  }
});

await test('B7', 'immediate background after search submission still triggers handoff', () => {
  const screen = read('app/search.tsx');
  assert.match(screen, /const handoffActiveSessionToBackground = useCallback/);
  assert.match(screen, /if \(next === 'background'\) \{\s*void handoffActiveSessionToBackground\(\)/s);
  assert.match(screen, /if \(AppState\.currentState !== 'active'\) \{\s*const handedOff = await handoffActiveSessionToBackground\(session\)/s);
  assert.match(screen, /if \(handedOff\) return/);
});

await test('B8', 'native cleanup cannot leave ghost keepalive services', () => {
  const module = read('plugins/search-background/SearchKeepAliveModule.kt.template');
  const keepAlive = read('plugins/search-background/SearchKeepAliveService.kt.template');
  assert.match(module, /headless stop failed token=/);
  assert.match(module, /val intent = Intent\(reactContext, SearchKeepAliveService::class\.java\)/);
  assert.doesNotMatch(keepAlive, /return START_STICKY/);
  assert.match(keepAlive, /return START_NOT_STICKY/);
});

await test('B9', 'process restarts cannot reuse stale background snapshot identity', () => {
  const keepAlive = read('src/core/searchKeepAlive.ts');
  const screen = read('app/search.tsx');
  const background = read('src/core/backgroundSearch.ts');
  assert.match(keepAlive, /const MAX_NATIVE_TOKEN = 2_147_483_646/);
  assert.match(keepAlive, /Math\.random\(\)/);
  assert.match(keepAlive, /const token = nextSearchToken\(\)/);
  assert.doesNotMatch(keepAlive, /const token = \+\+_activeToken/);
  assert.match(screen, /!expectedQuery \|\| !expectedToken \|\| !backgroundSnapshotMatches/);
  assert.doesNotMatch(screen, /\|\| normalizeSearchTerm\(q\)/);
  assert.match(background, /await AsyncStorage\.removeItem\(RESULT_KEY\)/);
});

await test('B10', 'foreground-service start/stop races cannot crash the app', () => {
  const module = read('plugins/search-background/SearchKeepAliveModule.kt.template');
  const service = read('plugins/search-background/SearchKeepAliveService.kt.template');
  assert.match(module, /latestKeepAliveToken/);
  assert.match(module, /claimKeepAliveStop\(tokenInt\)/);
  assert.match(module, /ignore duplicate\/stale keepalive stop/);
  assert.match(service, /override fun onCreate\(\)[\s\S]*?startForeground\(/);
  assert.match(service, /stopSelfResult\(startId\)/);
  assert.match(service, /ignore superseded stop/);
  assert.doesNotMatch(service, /\bstopSelf\(\)/);
});

await test('U1', 'home gradient animation stops whenever the Search tab loses focus', () => {
  const code = read('app/(tabs)/index.tsx');
  assert.match(code, /useFocusEffect\(/);
  assert.match(code, /flow\.setValue\(0\)/);
  assert.match(code, /return \(\) => animation\.stop\(\)/);
});

await test('U1S', 'startup overlay is native, lifecycle-safe and standalone-debug capable', () => {
  const appConfig = read('app.json');
  const rootLayout = read('app/_layout.tsx');
  const plugin = read('plugins/with-startup-overlay.js');
  const activity = read('plugins/startup-overlay/MainActivity.kt.template');
  const overlay = read('plugins/startup-overlay/StartupOverlayView.kt.template');
  const bridge = read('src/core/startupOverlay.ts');
  const packageJson = read('package.json');
  assert.match(appConfig, /\.\/plugins\/with-startup-overlay/);
  assert.match(plugin, /debuggableVariants = standaloneDebug \? \[\] : \["debug"\]/);
  assert.match(plugin, /BuildConfig\.DEBUG && !BuildConfig\.STANDALONE_DEBUG/);
  assert.match(plugin, /buildConfigField "boolean", "STANDALONE_DEBUG"/);
  assert.match(packageJson, /android:k30s/);
  assert.match(packageJson, /-PstandaloneDebug=true/);
  assert.match(activity, /STARTUP_WATCHDOG_MS = 12_000L/);
  assert.match(activity, /hideStartupOverlayInternal\("js_ready"\)/);
  assert.match(activity, /override fun onDestroy\(\)/);
  assert.match(overlay, /private const val GRID_SIZE = 5/);
  assert.match(overlay, /RING_INDICES = intArrayOf/);
  assert.match(overlay, /ValueAnimator\.ofFloat/);
  assert.match(overlay, /text = "Loading"/);
  assert.match(overlay, /override fun onDetachedFromWindow\(\)/);
  assert.doesNotMatch(rootLayout, /sourcesLoading \|\| !configChecked/);
  assert.match(rootLayout, /hideStartupOverlay\(\)/);
  assert.match(bridge, /STARTUP_OVERLAY_HIDE_FAILED/);
});

await test('U2', 'bottom navigation, top favorites and search hero respect the usable screen area', () => {
  const layout = read('app/(tabs)/_layout.tsx');
  const home = read('app/(tabs)/index.tsx');
  const appConfig = read('app.json');
  assert.match(layout, /name="index"/);
  assert.match(layout, /name="resources"/);
  assert.match(layout, /name="settings"/);
  assert.equal((layout.match(/<Tabs\.Screen/g) || []).length, 3);
  assert.match(appConfig, /"edgeToEdgeEnabled": false/);
  assert.doesNotMatch(layout, /AdaptiveTabBar|ANDROID_NAVIGATION_FALLBACK_INSET|useSafeAreaInsets/);
  assert.doesNotMatch(layout, /height:\s*62|paddingBottom:\s*7/);
  assert.match(home, /useSafeAreaInsets/);
  assert.match(home, /paddingTop: insets\.top/);
  assert.match(home, /useBottomTabBarHeight/);
  assert.match(home, /styles\.heroStage, \{ paddingTop: tabBarHeight \}/);
  assert.match(home, /topUtilityBar: \{[\s\S]*?minHeight: 46/);
  assert.match(home, /justifyContent: 'center'/);
  assert.doesNotMatch(home, /secondaryHeight|handleSecondaryLayout|SCREEN_H \* 0\.18/);
});

await test('U3', 'movie and regional series channels form one lightweight discovery experience', () => {
  const screen = read('app/(tabs)/resources.tsx');
  const feedClient = read('src/core/resourceFeed.ts');
  const mediaClient = read('src/core/mediaReleaseClient.ts');
  const detail = read('app/movie/[movieId].tsx');
  const ratings = read('src/core/movieRatings.ts');
  const tagRow = read('src/components/MovieTagRow.tsx');
  const copy = read('src/core/resourceCopy.ts');
  assert.match(screen, /keyExtractor=\{resourceFeedItemKey\}/);
  assert.match(screen, /sort\(compareMediaFeedRank\)/);
  assert.match(screen, /filter\(isServerRecommendedMovie\)/);
  assert.match(screen, /pathname: '\/movie\/\[movieId\]'/);
  assert.match(screen, /params: \{ movieId: item\.movie_id, kind: item\.content_kind \}/);
  assert.match(screen, /useState<MediaChannel>\('movie'\)/);
  assert.match(screen, /const CHANNELS: MediaChannel\[\] = \['movie', 'us', 'uk', 'china', 'korea', 'japan'\]/);
  assert.match(screen, /copy\.mediaMovies/);
  assert.doesNotMatch(screen, /channel === 'series'|copy\.mediaSeries/);
  assert.match(screen, /copy\.mediaUsSeries/);
  assert.match(screen, /copy\.mediaKoreanSeries/);
  assert.match(screen, /copy\.mediaJapaneseSeries/);
  assert.match(screen, /copy\.mediaChineseSeries/);
  assert.match(screen, /matchesChannel/);
  assert.match(screen, /countries\.has\('美国'\)/);
  assert.match(screen, /countries\.has\('韩国'\)/);
  assert.match(screen, /countries\.has\('日本'\)/);
  assert.match(screen, /seriesUpdatingTitle/);
  assert.match(screen, /isCompletedSeries/);
  assert.match(screen, /function prominentUpdateLabel/);
  assert.match(screen, /seriesStatusForDisplay/);
  assert.match(screen, /function latestEpisodeNumber/);
  assert.match(screen, /return `更新至\$\{episode\}集`/);
  assert.match(screen, /function listUpdateLabel/);
  assert.match(screen, /return season \? `\$\{season\} · 更新至第\$\{episode\}集` : `更新至第\$\{episode\}集`/);
  assert.match(screen, /colors=\{\['#ff7a3d', '#ef3f24'\]\}/);
  assert.match(screen, /updateOverlay: \{[\s\S]*?left: 8[\s\S]*?bottom: 8/);
  assert.doesNotMatch(screen, /updateOverlay: \{[\s\S]*?shadowOpacity|updateOverlay: \{[\s\S]*?elevation/);
  assert.match(screen, /updateOverlayText: \{ color: '#fff', fontSize: 13[\s\S]*?fontWeight: '900'/);
  assert.match(screen, /mediaStatus: \{[\s\S]*?fontSize: 13[\s\S]*?fontWeight: '400'/);
  assert.match(screen, /rowFooter: \{[\s\S]*?justifyContent: 'space-between'/);
  assert.match(screen, /resourceText: \{[\s\S]*?fontSize: 10[\s\S]*?fontWeight: '500'/);
  assert.match(screen, /\{!!seriesStatus && \(/);
  assert.ok(screen.indexOf('{seriesStatus}') < screen.indexOf('{resourceLabel(magnetCount)}'));
  assert.doesNotMatch(screen, /overlayLabel=\{item\.content_kind === 'series' \? status : null\}/);
  assert.doesNotMatch(screen, /排行榜|热播榜|榜第\s*\d/);
  assert.match(screen, /loadResourceFeed\(kind, forceRefresh\)/);
  assert.match(screen, /useFocusEffect\(/);
  assert.match(screen, /AppState\.addEventListener\('change'/);
  assert.match(screen, /AppState\.currentState === 'active'/);
  assert.match(screen, /setInterval\(\(\) => \{/);
  assert.match(screen, /RESOURCE_AUTO_SYNC_FOREGROUND_INTERVAL_MS/);
  assert.match(screen, /'foreground_interval'/);
  assert.match(screen, /clearInterval\(interval\)/);
  assert.match(screen, /new ResourceAutoSyncGate\(\)/);
  assert.match(screen, /autoSyncGate\.current\.tryStart\(kind\)/);
  assert.match(screen, /autoSyncGate\.current\.complete\(kind, succeeded\)/);
  assert.match(screen, /sameRemoteResourceRelease\(previous, loaded\.feed\)/);
  assert.doesNotMatch(screen, /previous\.snapshot_captured_at === loaded\.feed\.snapshot_captured_at/);
  assert.match(screen, /loaded\.refreshSucceeded/);
  assert.doesNotMatch(screen, /loaded\.origin === 'network'/);
  assert.match(screen, /autoSyncGate\.current\.markSuccess\(kind\)/);
  assert.match(screen, /auto_sync_reason: reason/);
  assert.match(screen, /trackResourcesTabView\(activeKind\)/);
  assert.match(screen, /trackResourceFeedRefreshResult\(/);
  assert.match(screen, /resourceFeedReleaseId\(loaded\.feed\)/);
  assert.doesNotMatch(screen, /backgroundSyncStarted/);
  assert.match(feedClient, /refreshSucceeded: result\.remoteRevalidated/);
  assert.match(feedClient, /MEDIA_REMOTE_REVALIDATION_UNAVAILABLE/);
  assert.match(feedClient, /refreshSucceeded: false/);
  assert.match(feedClient, /refreshErrorCode: 'MEDIA_FORCE_REFRESH_FAILED'/);
  assert.match(screen, /succeeded = loaded\.refreshSucceeded/);
  assert.match(mediaClient, /remoteRevalidated: pointerState === 'same'/);
  assert.match(mediaClient, /remoteRevalidated: true/);
  assert.match(screen, /key=\{activeChannel\}/);
  assert.equal((screen.match(/<FlatList/g) || []).length, 1);
  assert.match(screen, /item\.update_status \|\| item\.episode_label/);
  assert.match(screen, /cache: 'force-cache'/);
  assert.doesNotMatch(screen, /\{copy\.title\}/);
  assert.doesNotMatch(screen, /CHANNEL_CODES|MOVIE|>US<|>UK<|>CN<|>KR<|>JP</);
  assert.match(screen, /channelViewport/);
  assert.match(screen, /backgroundColor: colors\.card, borderColor: colors\.border/);
  assert.match(screen, /channelViewport: \{[\s\S]*?height: 62[\s\S]*?borderRadius: 20[\s\S]*?overflow: 'hidden'/);
  assert.match(screen, /channelContent: \{ paddingHorizontal: 5, paddingVertical: 5, alignItems: 'center' \}/);
  assert.match(screen, /channelButton: \{[\s\S]*?minWidth: 78[\s\S]*?height: 52/);
  assert.match(screen, /channelSegment: \{[\s\S]*?paddingHorizontal: 10/);
  assert.match(screen, /colors=\{\['#3867f5', '#2753d7'\]\}/);
  assert.match(screen, /channelDivider/);
  assert.match(screen, /channelActiveMark/);
  assert.match(screen, /channelTextActive: \{ color: '#fff', fontSize: 18, fontWeight: '900' \}/);
  assert.doesNotMatch(screen, /channelButton: \{[\s\S]*?shadowOpacity|channelButton: \{[\s\S]*?elevation/);
  assert.match(screen, /useState<string \| null>\(null\)/);
  assert.match(screen, /genreOptions/);
  assert.match(screen, /normalizedGenres\(item\)\.includes\(activeGenre\)/);
  assert.match(screen, /function normalizeGenreLabel/);
  assert.match(screen, /function normalizeCountryLabel/);
  assert.match(screen, /new Set\(normalizedCountries\(item\)\)/);
  assert.match(screen, /replace\(\/\^\[\\s:：·\|\/\]\+\//);
  assert.match(screen, /replace\(\/\\s\+片\$\/, '片'\)/);
  assert.match(screen, /genreChip: \{[\s\S]*?borderRadius: 999/);
  assert.match(copy, /genreAll: '全部'/);
  assert.match(screen, /spotlightSection: \{ marginTop: 14, marginBottom: 10 \}/);
  assert.match(screen, /latestTitle: \{ marginTop: 0, marginBottom: 0 \}/);
  assert.match(screen, /resource\.resource_type === 'magnet'/);
  assert.doesNotMatch(screen, /copy\.subtitle|copy\.updatedAt|generatedAt/);
  assert.doesNotMatch(screen, /content_code|MY-1065|javbus/i);
  assert.match(screen, /MovieTagRow/);
  assert.match(detail, /MovieTagRow/);
  assert.match(tagRow, /getVisibleMovieRatings/);
  assert.match(tagRow, /rating\.source/);
  assert.match(tagRow, /rating\.displayValue/);
  assert.match(tagRow, /rating\.tier === 'high'/);
  assert.match(tagRow, /styles\.tag/);
  assert.match(tagRow, /\{rating\.source\} \{rating\.displayValue\}/);
  assert.doesNotMatch(tagRow, /ratingVariant|ratingGrid|ratingDetail|ratingSource|ratingValue|flexBasis/);
  assert.match(tagRow, /rotten_tomatoes_rating/);
  assert.match(tagRow, /bangumi_rating/);
  assert.ok(tagRow.indexOf('ratings.map') < tagRow.indexOf('tags.map'));
  assert.doesNotMatch(tagRow, /tierLabel|精品|高分/);
  assert.doesNotMatch(copy, /featuredScore|highScore/);
  assert.match(copy, /recommendedTitle: '精品推荐'/);
  assert.match(screen, /getMovieScoreTier/);
  assert.match(screen, /hasProminentScore \? '#dc2626' : colors\.text/);
  assert.match(detail, /getMovieScoreTier/);
  assert.match(detail, /hasProminentScore \? '#dc2626' : colors\.text/);
  assert.match(ratings, /FEATURED_SCORE_THRESHOLD = 6\.0/);
  assert.match(ratings, /HIGH_SCORE_THRESHOLD = 8\.0/);
  assert.match(ratings, /FEATURED_PERCENT_THRESHOLD = 60/);
  assert.match(ratings, /HIGH_PERCENT_THRESHOLD = 80/);
  assert.match(ratings, /MEDIA_LIST_SORT_POLICY = 'release-rank'/);
  assert.match(ratings, /MEDIA_RECOMMENDATION_POLICY = 'server-recommended'/);
  assert.match(ratings, /MOVIE_PRIMARY_SCORE_PRIORITY = \['douban', 'imdb', 'bangumi', 'rotten_tomatoes'\]/);
  assert.match(ratings, /definition\.scale === 100 \? value \/ 10 : value/);
  assert.doesNotMatch(screen, /item\.douban_rating\.toFixed|name="star" size=\{11\}/);
  assert.doesNotMatch(detail, /scorePill|movie\.douban_rating\.toFixed|name="star" size=\{14\}/);
  assert.match(detail, /qualityTags=\{movie\.quality_tags\.slice\(0, 5\)\}/);
  assert.doesNotMatch(detail, /ratingVariant="detail"/);
  assert.match(detail, /synopsis\.length > 0/);
  assert.match(detail, /detailInfoRows\.length > 0/);
  assert.match(detail, /castRows\.length > 0/);
  assert.match(detail, /magnetResources\.length > 0/);
  assert.match(detail, /copy\.detailSynopsis/);
  assert.match(detail, /copy\.detailResources/);
  assert.match(detail, /pathname: '\/search'/);
  assert.match(detail, /loadMediaCardById\(requestedKind, movieId\)/);
  assert.match(detail, /loadMediaCardByIdAcrossFeeds\(movieId\)/);
  assert.match(detail, /setMovie\(card\)/);
  assert.match(detail, /hydrateMediaItem\(card\)/);
  assert.ok(detail.indexOf('setMovie(card)') < detail.indexOf('hydrateMediaItem(card)'));
  assert.match(detail, /movie\.content_kind === 'series'/);
  assert.match(detail, /inferSeriesSeason\(movie\.title, movie\.season_number\)/);
  assert.match(detail, /seriesStatusForDisplay/);
  assert.match(detail, /resourceDisplayTitle\(resource, seasonNumber\)/);
  assert.match(screen, /import \* as Clipboard from 'expo-clipboard'/);
  assert.match(screen, /const TITLE_COPY_TOAST_MS = 2000/);
  assert.match(detail, /const TITLE_COPY_TOAST_MS = 2000/);
  assert.match(screen, /const CopyableMediaTitle = memo/);
  assert.match(screen, /event\.stopPropagation\(\)/);
  assert.match(screen, /Clipboard\.setStringAsync\(title\)/);
  assert.match(screen, />\s*\{title\}\s*<\/Text>/);
  assert.doesNotMatch(screen, /copied \? copiedLabel : title/);
  assert.match(screen, /titleCopyToastNonce > 0/);
  assert.match(screen, /styles\.copyToastLayer/);
  assert.match(screen, /styles\.copyToast/);
  assert.match(screen, /copy\.copiedAction/);
  assert.match(screen, /borderRadius: 999/);
  assert.equal((screen.match(/<CopyableMediaTitle/g) || []).length, 2);
  assert.match(screen, /<View style=\{styles\.spotlightCard\}>/);
  assert.match(screen, /<View style=\{\[styles\.mediaRow/);
  assert.match(screen, /mediaDetailTouch/);
  assert.match(screen, /mediaChevronTouch/);
  assert.match(detail, /const \[titleCopyToastNonce, setTitleCopyToastNonce\] = useState\(0\)/);
  assert.match(detail, /Clipboard\.setStringAsync\(movie\.title\)/);
  assert.match(detail, /stage: 'copy_media_title'/);
  assert.match(detail, />\s*\{movie\.title\}\s*<\/Text>/);
  assert.doesNotMatch(detail, /copiedTitle \? copy\.copiedAction : movie\.title/);
  assert.match(detail, /titleCopyToastNonce > 0/);
  assert.match(detail, /styles\.copyToastLayer/);
  assert.match(detail, /styles\.copyToast/);
  assert.match(detail, /copy\.copiedAction/);
});

await test('U4', 'movie detail exposes only prominent magnet cards with search-equivalent actions', () => {
  const detail = read('app/movie/[movieId].tsx');
  const copy = read('src/core/resourceCopy.ts');
  assert.match(detail, /filter\(\(resource\) => resource\.resource_type === 'magnet'\)/);
  assert.match(detail, /MagnetResourceCard/);
  assert.match(detail, /t\.copyMagnet/);
  assert.match(detail, /t\.openMagnet/);
  assert.match(detail, /trackCopy\(\{ surface: 'media_detail', action: 'single' \}\)/);
  assert.match(detail, /trackCopy\(\{ surface: 'media_detail', action: 'all' \}\)/);
  assert.match(detail, /trackOpen\(\{ surface: 'media_detail', action: 'single' \}\)/);
  assert.match(detail, /resourceList/);
  assert.match(detail, /isLast=\{index === visibleMagnetResources\.length - 1\}/);
  assert.match(detail, /borderBottomWidth: StyleSheet\.hairlineWidth/);
  assert.match(detail, /resourceList: \{[\s\S]*?marginTop: 10[\s\S]*?borderRadius: 16[\s\S]*?overflow: 'hidden'/);
  assert.match(detail, /resourceCard: \{[\s\S]*?minHeight: 72[\s\S]*?paddingVertical: 8[\s\S]*?flexDirection: 'row'/);
  assert.match(detail, /resourceMain: \{ flex: 1, minWidth: 0, paddingRight: 10 \}/);
  assert.match(detail, /resourceTitle: \{ fontSize: 13, lineHeight: 18/);
  assert.match(detail, /resourceActions: \{[\s\S]*?width: 116[\s\S]*?flexDirection: 'row'[\s\S]*?gap: 6/);
  assert.match(detail, /actionButton: \{[\s\S]*?width: 55[\s\S]*?height: 32[\s\S]*?borderRadius: 999[\s\S]*?borderWidth: 1/);
  assert.match(detail, /filter\(\(tag\) => !normalizedTitle\.includes/);
  assert.doesNotMatch(detail, /actionTouch|\['#ff8a4c', '#f06529'\]/);
  const compactCardStyle = detail.match(/resourceCard: \{[\s\S]*?\n  \},\n  resourceMain:/)?.[0] ?? '';
  assert.doesNotMatch(compactCardStyle, /marginTop|borderRadius|shadowOpacity|elevation/);
  assert.match(copy, /detailResources: '资源'/);
  assert.match(copy, /viewResources: \(value\) => `查看资源（\$\{value\}）`/);
  assert.match(detail, /scrollToResources/);
  assert.match(detail, /resourceSectionVisible/);
  assert.match(detail, /onLayout=\{\(event\) =>/);
  assert.match(detail, /showResourceShortcut/);
  assert.match(detail, /copy\.viewResources\(magnetResources\.length\)/);
  assert.match(detail, /borderRadius: 999/);
  assert.match(detail, /left: 64/);
  assert.match(detail, /right: 64/);
  assert.match(detail, /visibleResourceLimit/);
  assert.match(detail, /magnetResources\.slice\(0, visibleResourceLimit\)/);
  assert.match(detail, /AUTO_LOAD_THRESHOLD = 360/);
  assert.match(detail, /viewportBottom >= contentSize\.height - AUTO_LOAD_THRESHOLD/);
  assert.match(detail, /current \+ RESOURCE_BATCH_SIZE/);
  assert.doesNotMatch(detail, /showMoreResources|moreResourcesButton|再显示/);
  assert.match(detail, /sortMediaResources/);
  assert.match(detail, /uniqueMagnetResources/);
  assert.match(detail, /magnetBatchText\(magnetResources\)/);
  assert.match(detail, /Clipboard\.setStringAsync\(batchText\)/);
  assert.match(detail, /stage: 'copy_all_magnets'/);
  assert.match(copy, /copyAllMagnets: '复制全部磁力'/);
  assert.match(copy, /copiedAllMagnets: \(value\) => `已复制 \$\{value\} 条`/);
  assert.match(copy, /copyAction: '复制'/);
  assert.match(copy, /copiedAction: '已复制'/);
  assert.match(copy, /openAction: '打开'/);
  assert.match(detail, /copyActionLabel=\{copy\.copyAction\}/);
  assert.match(detail, /openActionLabel=\{copy\.openAction\}/);
  assert.match(detail, /footerActions: \{[\s\S]*?flexDirection: 'row'/);
  assert.match(detail, /footerButton: \{[\s\S]*?borderRadius: 999/);
  assert.match(detail, /movie\.content_kind === 'series' && magnetResources\.length > 1/);
  assert.ok(detail.indexOf('copy.detailSynopsis') < detail.indexOf('copy.detailResources'));
  assert.ok(detail.indexOf('copy.detailInfo') < detail.indexOf('copy.detailResources'));
  assert.ok(detail.indexOf('copy.detailCast') < detail.indexOf('copy.detailResources'));
  assert.doesNotMatch(detail, /magnetLabel|resourceIcon|resourceType|name="magnet"|providerMagnet/);
  assert.doesNotMatch(detail, /providerXunlei|providerQuark|providerBaidu|cloudResourceHint|extractionCode/);
  assert.doesNotMatch(detail, /movie\.resources\.map|movie\.resources\.length/);
});

await test('U5', 'movie and series bundles are offline-first and exclude the legacy adult feed', () => {

  const loader = read('src/core/resourceFeed.ts');
  const protocol = read('src/core/resourceFeedProtocol.ts');
  const plugin = read('plugins/with-resource-feed.js');
  assert.match(loader, /resource-index', 'sixv'/);
  assert.match(loader, /resource-index', 'series'/);
  assert.match(loader, /movieCoverUri/);
  assert.match(loader, /if \(item\.cover_asset_path\)/);
  assert.match(loader, /return item\.cover_source_url/);
  assert.match(protocol, /movie-app-feed\/1/);
  assert.match(protocol, /media-app-feed\/1/);
  assert.match(protocol, /content_kind: MediaKind/);
  assert.match(protocol, /LEGACY_ADULT_FIELD/);
  assert.match(plugin, /sixv_app_bundle/);
  assert.match(plugin, /series_latest_100_feed\.json/);
  assert.match(plugin, /normalizeSeriesFeed/);
  assert.match(plugin, /resource\.resource_type !== 'magnet'/);
  assert.match(plugin, /remote covers use App cache until local cover assets are supplied/);
  assert.match(read('src/core/mediaResourceTitle.ts'), /S\(\\d\{1,2\}\)E\(\\d\{1,3\}\)/);
  assert.match(read('src/core/mediaResourceTitle.ts'), /decodeMagnetDisplayName/);
  assert.match(plugin, /rmSync\(legacyAdultFeed/);
  assert.doesNotMatch(plugin, /javbus_latest_100\.db/);
});

await test('D1', 'stored history/favorites are sanitized before entering caches', () => {
  assert.match(read('src/core/searchHistory.ts'), /sanitizeHistoryItems/);
  assert.match(read('src/core/favorites.ts'), /sanitizeFavoriteItems/);
});

await test('D2', 'config race validates payloads and cannot let stale CDN beat authorities', () => {
  const code = read('src/core/configChecker.ts');
  assert.match(code, /if \(!isRemoteConfig\(data\)\) throw new Error\('invalid_config'\)/);
  assert.match(code, /const authoritativeUrls = \[/);
  assert.match(code, /const fallbackUrls = \[`\$\{CDN_BASE\}\/config\.json`\]/);
  assert.match(code, /config = await loadFirstValid\(authoritativeUrls\)/);
  assert.match(code, /config = await loadFirstValid\(fallbackUrls\)/);
  assert.ok(code.indexOf('loadFirstValid(authoritativeUrls)') < code.indexOf('loadFirstValid(fallbackUrls)'));
});

const passed = results.filter((item) => item.pass).length;
const report = {
  generatedAt: new Date().toISOString(),
  passed,
  total: results.length,
  failed: results.filter((item) => !item.pass),
  results,
};
fs.writeFileSync(path.join(HERE, 'app-adversarial-report.json'), `${JSON.stringify(report, null, 2)}\n`);

console.log(`\n=== ${passed}/${results.length} passed ===`);
console.log(`report → ${path.join(HERE, 'app-adversarial-report.json')}`);
if (passed !== results.length) process.exitCode = 1;
