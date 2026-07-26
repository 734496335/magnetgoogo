import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  ALL_LANGS,
  getTranslations,
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
import { extractInfoHash } from '../src/core/dedup.ts';
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
import {
  BACKGROUND_SEARCH_TASK_TIMEOUT_MS,
  backgroundSnapshotMatches,
  isBackgroundSearchTerminal,
  mergeBackgroundSearchResults,
  parseBackgroundSearchSnapshot,
} from '../src/core/backgroundSearchProtocol.ts';

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
    assert.equal(typeof translation.searchingStatus(1, 2, 3), 'string');
    assert.equal(typeof translation.searchDoneStatus(2, 2, 3), 'string');
    assert.equal(typeof translation.fileCount(4), 'string');
  }
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

await test('M3', 'binary and byte size formats share one numeric parser', () => {
  assert.equal(parseSizeLabel('size=1.5 GiB'), '1.5 GB');
  assert.equal(parseSizeBytes('1.5 GiB'), 1.5 * 1024 ** 3);
  assert.equal(parseSizeBytes('1024 bytes'), 1024);
  assert.equal(toResultCardModel({ title: 'x', magnet: 'm', size: '700 MiB' }, 0).sizeBytes, 700 * 1024 ** 2);
});

await test('M4', 'comprehensive ranking understands binary units', () => {
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

await test('M5', 'stable IDs ignore tracker order for btih magnets', () => {
  const hash = 'ABCDEF0123456789ABCDEF0123456789ABCDEF01';
  const a = getResultStableId({ title: 'A', magnet: `magnet:?xt=urn:btih:${hash}&tr=one` });
  const b = getResultStableId({ title: 'B', magnet: `magnet:?xt=urn:btih:${hash.toLowerCase()}&tr=two` });
  assert.equal(a, b);
});

await test('P1', 'source startup effect is stable and sync is single-flight', () => {
  const code = read('src/core/SourceContext.tsx');
  assert.match(code, /syncInFlightRef/);
  assert.match(code, /if \(syncInFlightRef\.current\) return syncInFlightRef\.current/);
  assert.doesNotMatch(code, /\}, \[showToast, sources\.length\]\)/);
  assert.match(code, /if \(!silent\) showToast\(`已同步/);
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
  assert.match(code, /Promise\.allSettled\(\[\s*addHistory\(normalizedTerm\),\s*loadSourceStats\(\)/s);
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
  assert.equal(merged[0].size, '1 GiB');
  assert.equal(merged[0].seeders, 8);
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

await test('U2', 'bottom navigation and search hero respect the usable screen area', () => {
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
  assert.match(home, /useBottomTabBarHeight/);
  assert.match(home, /styles\.heroStage, \{ paddingTop: tabBarHeight \+ secondaryHeight \}/);
  assert.match(home, /handleSecondaryLayout/);
  assert.match(home, /justifyContent: 'center'/);
  assert.doesNotMatch(home, /SCREEN_H \* 0\.18/);
});

await test('U3', 'movie and regional series channels form one lightweight discovery experience', () => {
  const screen = read('app/(tabs)/resources.tsx');
  const detail = read('app/movie/[movieId].tsx');
  const ratings = read('src/core/movieRatings.ts');
  const tagRow = read('src/components/MovieTagRow.tsx');
  const copy = read('src/core/resourceCopy.ts');
  assert.match(screen, /keyExtractor=\{resourceFeedItemKey\}/);
  assert.match(screen, /item\.recommended/);
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
  assert.match(screen, /更新至\$\{updating\[1\]\}集/);
  assert.match(screen, /colors=\{\['#ff7a3d', '#ef3f24'\]\}/);
  assert.match(screen, /updateOverlayText: \{ color: '#fff', fontSize: 13[\s\S]*?fontWeight: '900'/);
  assert.doesNotMatch(screen, /排行榜|热播榜|榜第\s*\d/);
  assert.match(screen, /loadResourceFeed\(kind, forceRefresh\)/);
  assert.match(screen, /key=\{activeChannel\}/);
  assert.equal((screen.match(/<FlatList/g) || []).length, 1);
  assert.match(screen, /item\.update_status \|\| item\.episode_label/);
  assert.match(screen, /cache: 'force-cache'/);
  assert.doesNotMatch(screen, /\{copy\.title\}/);
  assert.match(screen, /CHANNEL_CODES/);
  assert.match(screen, /colors=\{active \? \['#4e8aff', '#2c63f4'\]/);
  assert.match(screen, /channelButton: \{[\s\S]*?width: 102[\s\S]*?height: 66/);
  assert.match(screen, /channelTextActive: \{ fontSize: 20, fontWeight: '900' \}/);
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
  assert.match(tagRow, /rating\.value\.toFixed\(1\)/);
  assert.match(tagRow, /rating\.tier === 'high'/);
  assert.ok(tagRow.indexOf('ratings.map') < tagRow.indexOf('tags.map'));
  assert.doesNotMatch(tagRow, /tierLabel|精品|高分/);
  assert.doesNotMatch(copy, /featuredScore|highScore|精品|高分/);
  assert.match(copy, /recommendedTitle: '近期好片'/);
  assert.match(screen, /getMovieScoreTier/);
  assert.match(screen, /hasProminentScore \? '#dc2626' : colors\.text/);
  assert.match(detail, /getMovieScoreTier/);
  assert.match(detail, /hasProminentScore \? '#dc2626' : colors\.text/);
  assert.match(ratings, /FEATURED_SCORE_THRESHOLD = 6\.0/);
  assert.match(ratings, /HIGH_SCORE_THRESHOLD = 8\.0/);
  assert.match(ratings, /value > 0 && value <= 10/);
  assert.doesNotMatch(screen, /item\.douban_rating\.toFixed|name="star" size=\{11\}/);
  assert.doesNotMatch(detail, /scorePill|movie\.douban_rating\.toFixed|name="star" size=\{14\}/);
  assert.match(detail, /qualityTags=\{movie\.quality_tags\.slice\(0, 5\)\}/);
  assert.match(detail, /synopsis\.length > 0/);
  assert.match(detail, /detailInfoRows\.length > 0/);
  assert.match(detail, /castRows\.length > 0/);
  assert.match(detail, /magnetResources\.length > 0/);
  assert.match(detail, /copy\.detailSynopsis/);
  assert.match(detail, /copy\.detailResources/);
  assert.match(detail, /pathname: '\/search'/);
  assert.match(detail, /loadMediaById\(requestedKind, movieId\)/);
  assert.match(detail, /loadMediaByIdAcrossFeeds\(movieId\)/);
  assert.match(detail, /movie\.content_kind === 'series'/);
  assert.match(detail, /inferSeriesSeason\(movie\.title, movie\.season_number\)/);
  assert.match(detail, /seriesStatusForDisplay/);
  assert.match(detail, /resourceDisplayTitle\(resource, seasonNumber\)/);
});

await test('U4', 'movie detail exposes only prominent magnet cards with search-equivalent actions', () => {
  const detail = read('app/movie/[movieId].tsx');
  const copy = read('src/core/resourceCopy.ts');
  assert.match(detail, /filter\(\(resource\) => resource\.resource_type === 'magnet'\)/);
  assert.match(detail, /MagnetResourceCard/);
  assert.match(detail, /t\.copyMagnet/);
  assert.match(detail, /t\.openMagnet/);
  assert.match(detail, /trackCopy\(\)/);
  assert.match(detail, /trackOpen\(\)/);
  assert.match(detail, /colors=\{\['#4e8aff', '#2c63f4'\]\}/);
  assert.match(detail, /colors=\{\['#ff8a4c', '#f06529'\]\}/);
  assert.match(detail, /borderColor: colors\.accent/);
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

await test('D2', 'config race accepts only structurally valid payloads', () => {
  const code = read('src/core/configChecker.ts');
  assert.match(code, /if \(!isRemoteConfig\(data\)\) throw new Error\('invalid_config'\)/);
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
