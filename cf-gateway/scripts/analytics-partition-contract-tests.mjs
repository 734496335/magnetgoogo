import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const source = fs.readFileSync(path.resolve('src/index.js'), 'utf8');

assert.match(source, /mode === 'inventory_page'/, 'analytics cursor inventory mode missing');
assert.match(source, /mode === 'page'/, 'analytics cursor data page mode missing');
assert.match(source, /const limit = Math\.min\(Math\.max\(parseInt\(url\.searchParams\.get\('limit'\)\) \|\| 250, 1\), 250\)/,
  'inventory-page reads must stay bounded to one <=250-key R2.list per Worker invocation');
assert.match(source, /env\.ANALYTICS\.list\(\{ prefix, cursor, limit, include: \[\] \}\)/,
  'inventory-page mode must issue exactly one lean R2.list page');
assert.match(source, /const limit = Math\.min\(Math\.max\(parseInt\(url\.searchParams\.get\('limit'\)\) \|\| 20, 1\), 25\)/,
  'page reads must stay <=25 objects per Worker invocation to fit the 10ms CPU budget');
assert.match(source, /nextCursor: listed\.truncated \? listed\.cursor : null/,
  'page mode must expose the R2 cursor');
assert.match(source, /complete: !listed\.truncated/,
  'page mode must expose explicit completeness');
assert.match(source, /function analyticsUploadedBeforeMs\(url\)/,
  'analytics recovery must support an immutable uploadedBefore snapshot cutoff');
assert.match(source, /analyticsObjectsAtCutoff\(listed\.objects, uploadedBefore\)/,
  'inventory/data pages must filter R2 objects against the same snapshot cutoff');
assert.match(source, /uploadedBefore: uploadedBefore \|\| null/,
  'snapshot cutoff must be echoed for auditability');
const inventoryPageBlock = source.slice(source.indexOf('async function handleEventsInventoryPage'), source.indexOf('async function handleEventsPage'));
assert.match(inventoryPageBlock, /count: objects\.length/,
  'inventory page must expose the current R2.list object count');
assert.match(inventoryPageBlock, /firstKey: objects\.length \? objects\[0\]\.key : ''/,
  'inventory page must expose its lexicographic first key');
assert.match(inventoryPageBlock, /lastKey: objects\.length \? objects\[objects\.length - 1\]\.key : ''/,
  'inventory page must expose its lexicographic last key');
assert.match(inventoryPageBlock, /nextCursor: listed\.truncated \? listed\.cursor : null/,
  'inventory page must expose the R2 cursor');
assert.doesNotMatch(inventoryPageBlock, /for \(|\.map\(|\.reduce\(|\.sort\(|ANALYTICS\.get/,
  'inventory-page Worker path must not iterate object content or perform object GETs');

for (const field of [
  'schema_v', 'batch_id', 'legacy_did', 'device_id', 'device_id_kind',
  'install_id', 'version_code', 'package_name', 'build_type', 'distribution', 'session_id',
]) {
  assert(source.includes(`'${field}'`), `V2 batch metadata passthrough missing: ${field}`);
}

const postStart = source.indexOf('async function handleEventsPost');
const getStart = source.indexOf('async function handleEventsGet', postStart);
assert(postStart >= 0 && getStart > postStart, 'events post block missing');
const postBlock = source.slice(postStart, getStart);
const durableWrite = postBlock.indexOf('await env.ANALYTICS.put(id');
assert(durableWrite >= 0, 'R2 analytics durable write missing');
assert.doesNotMatch(postBlock, /env\.EVENTS\.(?:get|put)\(dedupeKey/,
  'analytics ingestion must never depend on per-event KV dedupe quota');
assert.match(postBlock, /checkRateLimit\(`ev_\$\{data\.did\}`, 1\)/,
  'analytics rate limit must allow the App to drain queued batches at ~1.2s cadence');
for (const metadataField of ['legacy_did', 'device_id', 'device_id_kind', 'schema_v', 'op_day_min', 'op_day_max']) {
  assert(postBlock.includes(`${metadataField}:`), `R2 compact audit metadata missing: ${metadataField}`);
}

console.log(JSON.stringify({
  status: 'PASS',
  analytics_read_model: 'cursor inventory pages + bounded cursor data pages',
  max_page_objects: 25,
  v2_batch_metadata_preserved: true,
  kv_dedupe_hot_path: false,
}));
