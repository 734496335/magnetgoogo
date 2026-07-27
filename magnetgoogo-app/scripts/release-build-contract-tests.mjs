import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { applyReleaseSigning } = require('../plugins/with-release-signing.js');

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
assert.doesNotMatch(patched, /MagGoogo20/);
assert.equal(applyReleaseSigning(patched), patched);

const appJson = JSON.parse(fs.readFileSync(path.resolve('app.json'), 'utf8'));
assert.equal(appJson.expo.version, '0.2.1');
assert.equal(appJson.expo.android.versionCode, 5);
assert.equal(appJson.expo.android.package, 'com.magnetgoogo.app');
assert.ok(appJson.expo.plugins.includes('./plugins/with-release-signing'));

const cacheSource = fs.readFileSync(path.resolve('src/core/mediaReleaseCache.ts'), 'utf8');
const clientSource = fs.readFileSync(path.resolve('src/core/mediaReleaseClient.ts'), 'utf8');
assert.match(cacheSource, /media\.cache\.backup\.enc\.json/);
assert.match(clientSource, /Application\.applicationId\?\.endsWith\('\.debug'\)/);

console.log(JSON.stringify({
  status: 'PASS',
  version: appJson.expo.version,
  version_code: appJson.expo.android.versionCode,
  package: appJson.expo.android.package,
  signing_env_only: true,
  plugin_idempotent: true,
}));
