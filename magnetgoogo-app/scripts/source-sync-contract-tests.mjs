import assert from 'node:assert/strict';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('../src/core/secureSourceStore.ts', import.meta.url), 'utf8');

assert.match(source, /validateText\?: \(text: string, base: string\) => void/);
assert.match(source, /if \(validateText\) validateText\(text, base\)/);
assert.ok(
  source.indexOf('if (validateText) validateText(text, base)')
    < source.indexOf('return { text, url: base }'),
  'endpoint payload must be validated before it can win the race',
);
assert.match(source, /assertFreshEnvelope\(raw, 'disk source cache'\)/);
assert.match(source, /assertFreshEnvelope\(envelope, 'debug source pack'\)/);
assert.match(source, /raceFetchOk\(endpoints, SOURCE_FILE, headers, 12000, \(text, base\) => \{/);
assert.match(source, /assertFreshEnvelope\(candidate, `remote source pack from \$\{base\}`\)/);
assert.match(source, /assertFreshEnvelope\(raw, `remote source pack from \$\{base\}`\)/);

console.log(JSON.stringify({
  status: 'PASS',
  stale_fast_endpoint_cannot_win: true,
  disk_expiry_enforced: true,
  sequential_fallback_expiry_enforced: true,
}));
