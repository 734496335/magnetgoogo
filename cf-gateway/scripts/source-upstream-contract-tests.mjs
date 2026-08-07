import assert from 'node:assert/strict';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('../src/index.js', import.meta.url), 'utf8');
const fnStart = source.indexOf('async function fetchUpstream');
const fnEnd = source.indexOf('// ── Parse common request headers', fnStart);
const fn = source.slice(fnStart, fnEnd);

assert.ok(fnStart >= 0 && fnEnd > fnStart, 'fetchUpstream function not found');
const rawFetch = 'response = await fetch(url';
const pagesFetch = 'response = await fetch(`${CF_PAGES_BASE}${path}`';
assert.ok(fn.includes(rawFetch), 'GitHub Raw fetch missing');
assert.ok(fn.includes(pagesFetch), 'Cloudflare Pages fallback missing');
assert.ok(fn.indexOf(rawFetch) < fn.indexOf(pagesFetch), 'GitHub Raw must be attempted before Pages');
assert.match(fn, /GitHub Raw is refreshed automatically by mg-data/);

console.log(JSON.stringify({
  status: 'PASS',
  source_authority: 'GitHub Raw',
  fallback: 'Cloudflare Pages',
}));
