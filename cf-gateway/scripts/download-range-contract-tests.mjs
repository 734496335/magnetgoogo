import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const source = fs.readFileSync(path.resolve('src/index.js'), 'utf8');

assert.match(source, /env\.RELEASES\.get\(r2Key,\s*\{[\s\S]*?range:\s*request\.headers/);
assert.match(source, /headers\.set\('Accept-Ranges',\s*'bytes'\)/);
assert.match(source, /headers\.set\('Content-Range',\s*`bytes \$\{partialRange\.offset\}-\$\{rangeEnd\}\/\$\{obj\.size\}`\)/);
assert.match(source, /status:\s*partialRange \? 206 : 200/);
assert.match(source, /request\.method === 'HEAD' \? null : obj\.body/);
assert.match(source, /https:\/\/github\.com\/734496335\/magnetgoogo\/releases\/download/);
assert.doesNotMatch(source, /734496335\/maggoogo-sources\/releases\/download/);
assert.doesNotMatch(source, /await\s+obj\.arrayBuffer\(|await\s+upstream\.arrayBuffer\(/);

console.log(JSON.stringify({
  status: 'PASS',
  r2_range_passthrough: true,
  partial_status: 206,
  streaming: true,
  github_fallback_repository: 'magnetgoogo',
}));
