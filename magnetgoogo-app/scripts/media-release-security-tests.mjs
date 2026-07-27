import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {
  assertMediaPointerTransition,
  mediaPointerIdentity,
  MediaReleaseValidationError,
  selectMediaCurrentCandidate,
} from '../src/core/mediaReleaseProtocol.ts';

const repoRoot = path.resolve(process.cwd(), '..');
const releaseId = '20260726T000000Z-b8c702d5';
const pointerPath = path.join(
  repoRoot,
  'data/resource_index/media_releases_m1_final/staging/pointers',
  `00000000000000000004-${releaseId}.json`,
);
const pointerBytes = fs.readFileSync(pointerPath);
const pointer = JSON.parse(pointerBytes.toString('utf8'));
const pointerSha = crypto.createHash('sha256').update(pointerBytes).digest('hex');
const alternateSha = 'f'.repeat(64) === pointerSha ? 'e'.repeat(64) : 'f'.repeat(64);

function candidate(endpoint, value = pointer, sha = pointerSha) {
  return {
    endpoint,
    pointer: value,
    pointer_revision: value.pointer_revision,
    pointer_sha256: sha,
    release_id: value.release_id,
    manifest_sha256: value.manifest_sha256,
  };
}

function expectCode(code, action) {
  assert.throws(action, (error) => {
    assert.ok(error instanceof MediaReleaseValidationError);
    assert.equal(error.code, code);
    return true;
  });
}

const mirrored = [
  candidate('https://media.magnetgoogo.com'),
  candidate('https://cn.magnetgoogo.com/media'),
];
const mirroredWinner = selectMediaCurrentCandidate(mirrored);
assert.equal(mirroredWinner.pointer_sha256, pointerSha);
assert.equal(mirroredWinner.pointer.pointer_revision, 4);

expectCode('MEDIA_POINTER_SAME_REVISION_CONFLICT', () => selectMediaCurrentCandidate([
  candidate('https://media.magnetgoogo.com'),
  candidate('https://cn.magnetgoogo.com/media', pointer, alternateSha),
]));

const acceptedRevision4 = mediaPointerIdentity(candidate('cache'));
const revision3Pointer = { ...pointer, pointer_revision: 3 };
expectCode('MEDIA_POINTER_ROLLBACK_REJECTED', () => selectMediaCurrentCandidate([
  candidate('https://media.magnetgoogo.com', revision3Pointer, '3'.repeat(64)),
], acceptedRevision4));

const revision5Pointer = {
  ...pointer,
  pointer_revision: 5,
  release_id: `${releaseId}-next`,
  manifest_sha256: '5'.repeat(64),
};
const revision5 = selectMediaCurrentCandidate([
  candidate('https://media.magnetgoogo.com', revision5Pointer, '6'.repeat(64)),
], acceptedRevision4);
assert.equal(revision5.pointer.pointer_revision, 5);

assert.doesNotThrow(() => assertMediaPointerTransition(acceptedRevision4, acceptedRevision4));
expectCode('MEDIA_POINTER_SAME_REVISION_CONFLICT', () => assertMediaPointerTransition({
  ...acceptedRevision4,
  pointer_sha256: alternateSha,
}, acceptedRevision4));
expectCode('MEDIA_POINTER_SAME_REVISION_CONFLICT', () => assertMediaPointerTransition({
  ...acceptedRevision4,
  release_id: `${releaseId}-conflict`,
}, acceptedRevision4));
expectCode('MEDIA_POINTER_SAME_REVISION_CONFLICT', () => assertMediaPointerTransition({
  ...acceptedRevision4,
  manifest_sha256: 'a'.repeat(64),
}, acceptedRevision4));

const cacheSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseCache.ts'), 'utf8');
const clientSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseClient.ts'), 'utf8');
assert.match(cacheSource, /pointer_sha256: string/);
assert.match(cacheSource, /manifest_sha256: string/);
assert.match(cacheSource, /media\.cache\.backup\.enc\.json/);
assert.match(cacheSource, /restoreBackupToPrimary/);
assert.match(cacheSource, /temporary\.move\(primary\)/);
assert.match(cacheSource, /temporaryMoved = true/);
assert.match(cacheSource, /if \(!temporaryMoved\) deleteIfExists\(temporary\)/);
assert.match(cacheSource, /new File\(primary\.uri\)\.move\(backup\)/);
assert.match(cacheSource, /assertMediaPointerTransition\(identity, existingIdentity\)/);
assert.match(clientSource, /selectMediaCurrentCandidate\(candidates, acceptedIdentity\)/);
assert.match(clientSource, /cachedMediaPointerIdentity\(\)/);
assert.match(clientSource, /Promise\.race\(\[request, timeout\]\)/);
assert.match(clientSource, /MEDIA_CACHE_COMMIT_FAILED/);

console.log(JSON.stringify({
  status: 'PASS',
  mirrored_same_revision: true,
  same_revision_conflict_rejected: true,
  rollback_rejected: true,
  single_endpoint_higher_revision_accepted: true,
  cache_identity_fields: true,
  atomic_backup_contract: true,
}));
