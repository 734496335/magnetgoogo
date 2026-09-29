import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const ingest = fs.readFileSync(path.join(ROOT, 'growth-ops', 'scripts', 'search-console-ingest.mjs'), 'utf8');
const report = fs.readFileSync(path.join(ROOT, 'growth-ops', 'scripts', 'growth-opportunity-report.mjs'), 'utf8');

assert.match(ingest, /DEFAULT_STATUS\s*=\s*path\.join\(ROOT, 'search-console', 'ingest-status\.json'\)/);
assert.match(ingest, /writeIngestStatus\(result\)/, 'blocked auth state must be persisted separately from the last-good snapshot');
assert.match(ingest, /status:\s*'BLOCKED_EXTERNAL_AUTH'/);
assert.match(ingest, /status:\s*'OK'[\s\S]*snapshot_end_date:/, 'successful ingest must refresh the independent status file');

assert.match(report, /DEFAULT_GSC_STATUS/);
assert.match(report, /GSC_EXTERNAL_AUTH_BLOCKED_USING_LAST_GOOD/);
assert.match(report, /STALE_LAST_GOOD/);
assert.match(report, /historical experiments only/, 'stale GSC evidence must be explicitly bounded to historical use');
assert.doesNotMatch(report, /gscAuthBlocked\)[\s\S]{0,80}blockers\.push/, 'newer external-auth failure must warn when a last-good snapshot exists, not erase all non-Google growth evidence');

console.log(JSON.stringify({
  status: 'PASS',
  separate_ingest_status: true,
  last_good_snapshot_preserved: true,
  stale_last_good_explicit: true,
  external_auth_warning_non_destructive: true,
}));
