import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { applyReleaseSigning } = require('../plugins/with-release-signing.js');
const {
  buildSourceBootstrap,
  decryptBootstrap,
  summarizeCanonical,
} = require('../plugins/with-source-bootstrap.js');

const generated = `android {
    namespace 'com.magnetgoogo.app'
    signingConfigs {
        debug {
            storeFile file('debug.keystore')
            storePassword 'android'
            keyAlias 'androiddebugkey'
            keyPassword 'android'
        }
    }
    buildTypes {
        debug {
            signingConfig signingConfigs.debug
        }
        release {
            // Caution! In production, you need to generate your own keystore file.
            // see https://reactnative.dev/docs/signed-apk-android.
            signingConfig signingConfigs.debug
        }
    }
}
`;

const patched = applyReleaseSigning(generated);
assert.match(patched, /MAGNETGOOGO_RELEASE_SIGNING_V1/);
assert.match(patched, /System\.getenv\("RELEASE_STORE_PASSWORD"\)/);
assert.match(patched, /System\.getenv\("RELEASE_KEY_ALIAS"\)/);
assert.match(patched, /System\.getenv\("RELEASE_KEY_PASSWORD"\)/);
assert.match(patched, /magnetgoogo-release-new\.keystore/);
assert.match(patched, /signingConfig signingConfigs\.release/);
assert.match(patched, /applicationIdSuffix '\.debug'/);
assert.doesNotMatch(patched, /MagGoogo20/);
assert.equal(applyReleaseSigning(patched), patched);

const appJson = JSON.parse(fs.readFileSync(path.resolve('app.json'), 'utf8'));
assert.equal(appJson.expo.version, '0.2.5');
assert.equal(appJson.expo.android.versionCode, 9);
assert.equal(appJson.expo.android.package, 'com.magnetgoogo.app');
assert.ok(appJson.expo.android.permissions.includes('android.permission.REQUEST_INSTALL_PACKAGES'));
assert.ok(appJson.expo.plugins.includes('./plugins/with-release-signing'));
assert.ok(appJson.expo.plugins.includes('./plugins/with-source-bootstrap'));
const buildPropertiesPlugin = appJson.expo.plugins.find(
  (plugin) => Array.isArray(plugin) && plugin[0] === 'expo-build-properties',
);
assert.deepEqual(buildPropertiesPlugin?.[1]?.android?.buildArchs, ['arm64-v8a']);
assert.equal(buildPropertiesPlugin?.[1]?.android?.abis, undefined);

const canonicalSources = JSON.parse(fs.readFileSync(path.resolve('..', 'sources.json'), 'utf8'));
const canonicalAudit = summarizeCanonical(canonicalSources);
const sourceBootstrap = buildSourceBootstrap({
  sourcePath: path.resolve('..', 'sources.json'),
  configPath: path.resolve('..', 'mg-data', 'config.json'),
  now: new Date('2026-07-28T00:00:00.000Z'),
  iv: Buffer.alloc(16, 7),
});
assert.deepEqual(sourceBootstrap.audit, canonicalAudit);
assert.equal(canonicalAudit.allRules, 357);
assert.equal(canonicalAudit.greenRules, 147);
assert.equal(canonicalAudit.greenPools, 51);
assert.equal(sourceBootstrap.expiresAt, '2026-07-31T00:00:00.000Z');
const bootstrapEnvelope = decryptBootstrap(sourceBootstrap.encoded);
assert.equal(bootstrapEnvelope.schema_version, 1);
assert.equal(bootstrapEnvelope.min_app_version, '0.1.10');
assert.equal(JSON.parse(sourceBootstrap.encoded).gz, true);
assert.deepEqual(Object.keys(JSON.parse(sourceBootstrap.encoded)).sort(), ['ct', 'gz', 'iv', 'sig']);
assert.equal(bootstrapEnvelope.payload.rulesets.flatMap((ruleset) => ruleset.rules).length, 357);
assert.doesNotMatch(sourceBootstrap.encoded, /btsow\.pics|proxyit\.de|pool_id/);

const cacheSource = fs.readFileSync(path.resolve('src/core/mediaReleaseCache.ts'), 'utf8');
const clientSource = fs.readFileSync(path.resolve('src/core/mediaReleaseClient.ts'), 'utf8');
const sourceStore = fs.readFileSync(path.resolve('src/core/secureSourceStore.ts'), 'utf8');
assert.match(cacheSource, /media-release-cache-v2/);
assert.match(cacheSource, /media-app-detail-cache\/2/);
assert.doesNotMatch(cacheSource, /CryptoJS|SecureStore|CACHE_EXPIRY/);
assert.match(clientSource, /Application\.applicationId\?\.endsWith\('\.debug'\)/);
assert.match(clientSource, /console\.log\('\[MediaReleaseEvidence\]'/);
assert.doesNotMatch(clientSource, /console\.warn\('\[MediaReleaseEvidence\]'/);
assert.match(sourceStore, /Paths\.bundle,[\s\S]*?'source-bootstrap',[\s\S]*?'bootstrap-sources\.enc\.json'/);
assert.match(sourceStore, /nativeBootstrap \|\| JSON\.stringify\(bootstrapPayload\)/);

console.log(JSON.stringify({
  status: 'PASS',
  version: appJson.expo.version,
  version_code: appJson.expo.android.versionCode,
  package: appJson.expo.android.package,
  signing_env_only: true,
  plugin_idempotent: true,
  source_bootstrap_green_rules: sourceBootstrap.audit.greenRules,
  source_bootstrap_pools: sourceBootstrap.audit.greenPools,
  legacy_envelope_min_app: bootstrapEnvelope.min_app_version,
  legacy_envelope_schema: bootstrapEnvelope.schema_version,
}));
