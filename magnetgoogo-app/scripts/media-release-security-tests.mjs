import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {
  assertMediaPointerTransition,
  mediaPointerIdentity,
  MediaReleaseValidationError,
  parseCatalog,
  parseDetail,
  selectMediaCurrentCandidate,
} from '../src/core/mediaReleaseProtocol.ts';

const releaseId = '20260726T000000Z-b8c702d5';
const pointer = {
  schema_version: 'media-current/1',
  pointer_revision: 4,
  release_id: releaseId,
  manifest_path: `/v1/releases/${releaseId}/manifest.json`,
  manifest_sha256: '4'.repeat(64),
  min_app_version: '0.2.1',
  published_at: '2026-07-26T00:00:00Z',
  signature_key_id: 'media-ed25519-test',
  signature: 'test-signature',
};
const pointerBytes = Buffer.from(JSON.stringify(pointer), 'utf8');
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

const objectRef = {
  path: `/v1/objects/${'a'.repeat(64)}.json`,
  hash: 'a'.repeat(64),
  size: 128,
};
const catalogWithFutureRatings = parseCatalog({
  schema_version: 'media-catalog/1',
  channel: 'movie',
  role: 'latest',
  page: 1,
  count: 1,
  items: [{
    media_id: 'movie:test',
    content_kind: 'movie',
    title: 'Test Movie',
    countries: ['US'],
    genres: ['Drama'],
    imdb_rating: 7.8,
    douban_rating: 8.1,
    rotten_tomatoes_rating: 91,
    bangumi_rating: 7.4,
    recommended: false,
    highlight_labels: [],
    quality_tags: [],
    resource_count: 1,
    cover: { ...objectRef, path: `/v1/covers/${'a'.repeat(64)}.jpg`, mime_type: 'image/jpeg' },
    detail_object: objectRef,
  }],
});
assert.equal(catalogWithFutureRatings.items[0].imdb_rating, 7.8);
assert.equal(catalogWithFutureRatings.items[0].douban_rating, 8.1);
assert.equal('rotten_tomatoes_rating' in catalogWithFutureRatings.items[0], false);
assert.equal('bangumi_rating' in catalogWithFutureRatings.items[0], false);

const detailWithFutureRatings = parseDetail({
  schema_version: 'media-detail/1',
  media_id: 'movie:test',
  content_kind: 'movie',
  title: 'Test Movie',
  countries: ['US'],
  genres: ['Drama'],
  languages: ['English'],
  directors: [],
  actors: [],
  imdb_rating: 7.8,
  imdb_rating_text: '7.8/10',
  douban_rating: 8.1,
  douban_rating_text: '8.1/10',
  rotten_tomatoes_rating: 91,
  rotten_tomatoes_rating_text: '91%',
  rotten_tomatoes_url: 'https://www.rottentomatoes.com/m/test_movie',
  bangumi_rating: 7.4,
  bangumi_rating_text: '7.4/10',
  bangumi_subject_id: '123',
  bangumi_url: 'https://bgm.tv/subject/123',
  resource_object: { ...objectRef, encrypted: false },
});
assert.equal(detailWithFutureRatings.imdb_rating, 7.8);
assert.equal(detailWithFutureRatings.douban_rating, 8.1);
assert.equal('rotten_tomatoes_rating' in detailWithFutureRatings, false);
assert.equal('bangumi_rating' in detailWithFutureRatings, false);

console.log(JSON.stringify({
  status: 'PASS',
  mirrored_same_revision: true,
  same_revision_conflict_rejected: true,
  rollback_rejected: true,
  single_endpoint_higher_revision_accepted: true,
  cache_identity_fields: true,
  atomic_backup_contract: true,
  future_rating_fields_ignored_safely_by_v023: true,
}));
