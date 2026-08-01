import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const appRoot = process.cwd();
const repoRoot = path.resolve(appRoot, '..');
const mgConfig = JSON.parse(fs.readFileSync(path.join(repoRoot, 'mg-data', 'config.json'), 'utf8'));
const siteConfigPath = path.join(repoRoot, 'magnetgoogo-site', 'config.json');
const siteDownloadsPath = path.join(repoRoot, 'magnetgoogo-site', 'site-config.json');
const siteConfig = fs.existsSync(siteConfigPath)
  ? JSON.parse(fs.readFileSync(siteConfigPath, 'utf8'))
  : null;
const siteDownloads = fs.existsSync(siteDownloadsPath)
  ? JSON.parse(fs.readFileSync(siteDownloadsPath, 'utf8'))
  : null;

const gatewayUrl = 'https://api.naoshiquan.com/download/v0.2.3/magnetgoogo-v0.2.3.apk';
const lanzouUrl = 'https://wwbdy.lanzn.com/iDcyE3zn4rcf';
const githubUrl = 'https://github.com/734496335/magnetgoogo/releases/download/v0.2.3/magnetgoogo-v0.2.3.apk';

for (const config of [mgConfig, siteConfig].filter(Boolean)) {
  assert.equal(config.download.primary, gatewayUrl);
  assert.deepEqual(config.download.mirrors, [lanzouUrl, githubUrl]);
  assert.ok(config.download.primary.endsWith('.apk'));
  assert.ok(config.download.mirrors[0].includes('lanzn.com'));
  assert.ok(config.download.mirrors.at(-1).includes('github.com'));
}

if (siteDownloads) {
  assert.equal(siteDownloads.download_url, gatewayUrl);
  assert.equal(siteDownloads.backup_url, lanzouUrl);
  assert.deepEqual(
    siteDownloads.backup_downloads.map((item) => item.label),
    ['蓝奏云', 'GitHub'],
  );
}

const policySource = fs.readFileSync(path.join(appRoot, 'src', 'core', 'updateDownloadPolicy.ts'), 'utf8');
const downloadSource = fs.readFileSync(path.join(appRoot, 'src', 'core', 'updateDownload.ts'), 'utf8');
const configCheckerSource = fs.readFileSync(path.join(appRoot, 'src', 'core', 'configChecker.ts'), 'utf8');
const forceModalSource = fs.readFileSync(path.join(appRoot, 'src', 'components', 'ForceUpdateModal.tsx'), 'utf8');
const optionalModalSource = fs.readFileSync(path.join(appRoot, 'src', 'components', 'OptionalUpdateModal.tsx'), 'utf8');

assert.match(policySource, /case 'lanzou':[\s\S]*return 0/);
assert.match(policySource, /case 'github':[\s\S]*return 4/);
assert.match(policySource, /getEmergencyBrowserFallbacks/);
assert.match(policySource, /\['lanzou', 'github'\]/);
assert.match(downloadSource, /for \(let index = 0; index < candidates\.length; index \+= 1\)/);
assert.match(downloadSource, /invalid_apk_size/);
assert.match(downloadSource, /invalid_apk_signature/);
assert.match(downloadSource, /all_download_candidates_failed/);
assert.match(configCheckerSource, /orderUpdateMirrors/);

for (const modalSource of [forceModalSource, optionalModalSource]) {
  assert.match(modalSource, /downloadApkFromCandidates/);
  assert.match(modalSource, /buildDirectDownloadCandidates/);
  assert.match(modalSource, /getEmergencyBrowserFallbacks/);
  assert.match(modalSource, /getUpdateMirrorLabel/);
  assert.match(modalSource, /orderedMirrors\.map/);
}

console.log(JSON.stringify({
  status: 'PASS',
  primary: gatewayUrl,
  mirror_order: ['Lanzou', 'GitHub'],
  direct_fallback_enabled: true,
  apk_integrity_guard: ['min_size', 'zip_magic'],
}));
