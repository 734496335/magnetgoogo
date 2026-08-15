import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

const policyPath = path.resolve('src/core/analyticsPolicy.ts');
const source = fs.readFileSync(policyPath, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    strict: true,
  },
}).outputText;
const module = { exports: {} };
new Function('module', 'exports', compiled)(module, module.exports);
const {
  classifyQuery,
  compactSourceRollup,
  dedupeEventsById,
  deterministicSample,
  selectBatchByBytes,
  utf8ByteLength,
} = module.exports;

assert.equal(classifyQuery('消失的人'), 'cjk');
assert.equal(classifyQuery('Inception'), 'latin');
assert.equal(classifyQuery('SSIS-001'), 'code');
assert.equal(classifyQuery('海贼王 One Piece'), 'mixed');
assert.equal(utf8ByteLength('abc'), 3);
assert.equal(utf8ByteLength('中文'), 6);
assert.equal(utf8ByteLength('😀'), 4);

const deduped = dedupeEventsById([
  { id: 'a', e: 'copy_magnet', ts: 1 },
  { id: 'a', e: 'copy_magnet', ts: 1 },
  { id: 'b', e: 'open_magnet', ts: 2 },
]);
assert.deepEqual(deduped.map((event) => event.id), ['a', 'b']);

const rollup = Array.from({ length: 60 }, (_, index) => ({
  src: `source-${index}`,
  cat: 'http',
  pool: `pool-${index % 10}`,
  called: 1,
  ok: index % 3 === 0 ? 1 : 0,
  empty: index % 3 === 1 ? 1 : 0,
  fail: index % 3 === 2 ? 1 : 0,
  results: index,
  unique_results: Math.floor(index / 2),
  relevant_results: Math.floor(index / 3),
  relevant_precision: 0.75,
  hit_searches: index > 0 ? 1 : 0,
  ms: 100 + index,
}));
const compact = compactSourceRollup(rollup, true, 48);
assert.equal(compact.summary.called, 60);
assert.equal(compact.sample.length, 48);
assert.ok(JSON.stringify(compact).length < JSON.stringify(rollup).length / 2);

const events = Array.from({ length: 40 }, (_, index) => ({
  id: `event-${index}`,
  e: 'copy_magnet',
  ts: index,
  padding: 'x'.repeat(700),
}));
const envelope = { schema_v: 2, batch_id: 'b2_test', device_id: 'dv2_test' };
const selected = selectBatchByBytes(events, envelope, 24 * 1024, 40);
assert.ok(selected.length > 0 && selected.length < 40);
assert.ok(utf8ByteLength(JSON.stringify({ ...envelope, events: selected })) <= 24 * 1024);

const sampleDecisions = Array.from({ length: 100 }, (_, index) => deterministicSample(`search-${index}`, 10));
const sampled = sampleDecisions.filter(Boolean).length;
assert.ok(sampled >= 4 && sampled <= 18, `unexpected deterministic sample count: ${sampled}`);
assert.equal(deterministicSample('same-key', 10), deterministicSample('same-key', 10));

const analyticsSource = fs.readFileSync(path.resolve('src/core/analytics.ts'), 'utf8');
assert.match(analyticsSource, /Application\.getAndroidId\(\)/);
assert.match(analyticsSource, /magnetgoogo:device:v2/);
assert.match(analyticsSource, /magnetgoogo:install:v2/);
assert.match(analyticsSource, /Application\.getInstallationTimeAsync\(\)/);
assert.match(analyticsSource, /legacy_did: identity\.legacyDid/);
assert.match(analyticsSource, /MAX_BATCH_BYTES = 24 \* 1024/);
assert.match(analyticsSource, /EXPO_PUBLIC_ANALYTICS_ENDPOINT/);
assert.match(analyticsSource, /finally \{\s*clearTimeout\(timer\);\s*\}/, 'analytics request timeout timer must be cleared even when fetch throws');
assert.match(analyticsSource, /first_open/);
assert.match(analyticsSource, /resources_tab_view/);
assert.match(analyticsSource, /resource_feed_refresh_result/);
assert.match(analyticsSource, /ResourceRefreshReason/);
assert.match(analyticsSource, /\.\.\.persisted, \.\.\._queue/);
assert.match(analyticsSource, /build_type/);
assert.match(analyticsSource, /device_id_kind/);
assert.doesNotMatch(analyticsSource, /\bq:\s*params\.term/);

console.log(JSON.stringify({
  status: 'PASS',
  compact_sample_entries: compact.sample.length,
  compact_bytes: utf8ByteLength(JSON.stringify(compact)),
  original_rollup_bytes: utf8ByteLength(JSON.stringify(rollup)),
  selected_batch_events: selected.length,
  sampled_per_100: sampled,
}, null, 2));
