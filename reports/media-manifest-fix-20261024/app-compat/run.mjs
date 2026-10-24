// Run the frozen App protocol snapshot with the project's installed dependencies.
// Usage (Node 24+): MEDIA_APP_DEPENDENCY_ROOT=/path/to/magnetgoogo-app node --experimental-strip-types run.mjs
import assert from 'node:assert/strict';
import { createRequire, registerHooks } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const appRoot = process.env.MEDIA_APP_DEPENDENCY_ROOT;
assert.ok(appRoot, 'MEDIA_APP_DEPENDENCY_ROOT must point to the existing magnetgoogo-app directory');
const appRequire = createRequire(path.resolve(appRoot, 'package.json'));
const dependencies = ['crypto-js', 'tweetnacl'];
// Resolve before registering hooks, so createRequire.resolve cannot recurse into this hook.
const urls = new Map(dependencies.map((name) => [name, pathToFileURL(appRequire.resolve(name)).href]));
const versions = dependencies.map((name) => ({ name, version: appRequire(name + '/package.json').version }));
registerHooks({
  resolve(specifier, context, nextResolve) {
    return nextResolve(urls.get(specifier) ?? specifier, context);
  },
});
console.log(JSON.stringify({ started_at: new Date().toISOString(), node: process.version, dependencies: versions }));
if (process.env.MEDIA_IMPORT_ONLY === '1') {
  await Promise.all([import('./src/core/mediaReleaseProtocol.ts'), import('./src/core/mediaResourceTitle.ts')]);
  console.log(JSON.stringify({ parser_import: 'PASS' }));
} else {
  await import('./scripts/media-live-full-compat-tests.mjs');
  console.log(JSON.stringify({ finished_at: new Date().toISOString() }));
}
