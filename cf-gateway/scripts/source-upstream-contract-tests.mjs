import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const source = fs.readFileSync(path.resolve('src/index.js'), 'utf8');
const start = source.indexOf('async function fetchUpstream');
const end = source.indexOf('// ── Parse common request headers', start);
assert.ok(start >= 0 && end > start, 'fetchUpstream function not found');

const block = source.slice(start, end);
const githubFetch = block.indexOf('response = await fetch(url');
const pagesFetch = block.indexOf('response = await fetch(`${CF_PAGES_BASE}${path}`');

assert.ok(githubFetch >= 0, 'GitHub Raw upstream fetch missing');
assert.ok(pagesFetch >= 0, 'CF Pages fallback fetch missing');
assert.ok(githubFetch < pagesFetch, 'GitHub Raw must be attempted before CF Pages');
assert.match(block, /GitHub Raw is the auto-renewed source authority/);
assert.match(block, /if \(!response\.ok\) throw new Error\(`GitHub Raw \$\{response\.status\}`\)/);
assert.doesNotMatch(block, /Try CF Pages first/);

console.log(JSON.stringify({
  status: 'PASS',
  source_authority: 'GitHub Raw',
  fallback: 'Cloudflare Pages',
  github_before_pages: true,
}));
