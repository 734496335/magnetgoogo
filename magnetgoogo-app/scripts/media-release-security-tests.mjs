import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {
  assertMediaPointerTransition,
  classifyMediaCurrentState,
  mediaPointerIdentity,
  MediaReleaseValidationError,
  parseCatalog,
  parseDetail,
  selectMediaCurrentCandidate,
} from '../src/core/mediaReleaseProtocol.ts';
import {
  mediaFeedItemFromCatalogCard,
  mergeMediaDetailIntoFeedItem,
} from '../src/core/mediaReleaseMapping.ts';

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
const revision5Candidate = candidate('https://api.naoshiquan.com/media', revision5Pointer, '6'.repeat(64));
const revision5 = selectMediaCurrentCandidate([revision5Candidate], acceptedRevision4);
assert.equal(revision5.pointer.pointer_revision, 5);
assert.equal(classifyMediaCurrentState([
  candidate('https://media.magnetgoogo.com'),
  revision5Candidate,
], acceptedRevision4), 'changed');
assert.equal(classifyMediaCurrentState([
  candidate('https://media.magnetgoogo.com'),
], acceptedRevision4), 'same');
assert.equal(classifyMediaCurrentState([
  candidate('https://media.magnetgoogo.com', revision3Pointer, '3'.repeat(64)),
], acceptedRevision4), 'same');

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

const objectRef = (prefix) => ({
  path: `/v1/objects/${prefix}/${prefix.repeat(64).slice(0, 64)}.json`,
  hash: prefix.repeat(64).slice(0, 64),
  size: 128,
});
const ratingCard = {
  media_id: `movie:${'c'.repeat(64)}`,
  content_kind: 'movie',
  title: 'Four Rating Test',
  countries: ['CN'],
  genres: ['Drama'],
  imdb_rating: 7.6,
  douban_rating: 8.2,
  rotten_tomatoes_rating: 91,
  bangumi_rating: 8.4,
  recommended: false,
  highlight_labels: [],
  quality_tags: [],
  resource_count: 1,
  cover: { ...objectRef('a'), mime_type: 'image/jpeg' },
  detail_object: objectRef('b'),
};
const parsedRatingCatalog = parseCatalog({
  schema_version: 'media-catalog/1',
  channel: 'movie',
  role: 'latest',
  page: 1,
  count: 1,
  items: [ratingCard],
});
assert.equal(parsedRatingCatalog.items[0].rotten_tomatoes_rating, 91);
assert.equal(parsedRatingCatalog.items[0].bangumi_rating, 8.4);
const legacyCard = { ...ratingCard };
delete legacyCard.rotten_tomatoes_rating;
delete legacyCard.bangumi_rating;
const parsedLegacyCatalog = parseCatalog({
  schema_version: 'media-catalog/1',
  channel: 'movie',
  role: 'latest',
  page: 1,
  count: 1,
  items: [legacyCard],
});
assert.equal(parsedLegacyCatalog.items[0].rotten_tomatoes_rating, null);
assert.equal(parsedLegacyCatalog.items[0].bangumi_rating, null);

const ratingDetail = {
  schema_version: 'media-detail/1',
  media_id: ratingCard.media_id,
  content_kind: 'movie',
  title: ratingCard.title,
  countries: ['CN'],
  genres: ['Drama'],
  languages: ['zh'],
  directors: [],
  actors: [],
  imdb_rating: 7.6,
  imdb_rating_text: '7.6/10',
  douban_rating: 8.2,
  douban_rating_text: '8.2/10',
  rotten_tomatoes_rating: 91,
  rotten_tomatoes_rating_text: '91%',
  rotten_tomatoes_url: 'https://www.rottentomatoes.com/m/four_rating_test',
  bangumi_rating: 8.4,
  bangumi_rating_text: '8.4/10',
  bangumi_subject_id: '123456',
  bangumi_url: 'https://bgm.tv/subject/123456',
  resource_object: { ...objectRef('d'), encrypted: false },
};
const parsedRatingDetail = parseDetail(ratingDetail);
assert.equal(parsedRatingDetail.rotten_tomatoes_rating_text, '91%');
assert.equal(parsedRatingDetail.bangumi_subject_id, '123456');
const legacyDetail = { ...ratingDetail };
delete legacyDetail.rotten_tomatoes_rating;
delete legacyDetail.rotten_tomatoes_rating_text;
delete legacyDetail.rotten_tomatoes_url;
delete legacyDetail.bangumi_rating;
delete legacyDetail.bangumi_rating_text;
delete legacyDetail.bangumi_subject_id;
delete legacyDetail.bangumi_url;
const parsedLegacyDetail = parseDetail(legacyDetail);
assert.equal(parsedLegacyDetail.rotten_tomatoes_rating, null);
assert.equal(parsedLegacyDetail.bangumi_rating, null);

const mappedCard = mediaFeedItemFromCatalogCard(
  parsedRatingCatalog.items[0],
  1,
  'https://media.magnetgoogo.com',
  releaseId,
);
assert.equal(mappedCard.rotten_tomatoes_rating, 91);
assert.equal(mappedCard.rotten_tomatoes_rating_text, '91%');
assert.equal(mappedCard.bangumi_rating, 8.4);
assert.equal(mappedCard.bangumi_rating_text, '8.4');
const mappedLegacyCard = mediaFeedItemFromCatalogCard(
  parsedLegacyCatalog.items[0],
  1,
  'https://media.magnetgoogo.com',
  releaseId,
);
assert.equal(mappedLegacyCard.rotten_tomatoes_rating, null);
assert.equal(mappedLegacyCard.bangumi_rating, null);

const mappedDetail = mergeMediaDetailIntoFeedItem(
  mappedCard,
  parsedRatingDetail,
  {
    schema_version: 'media-resources/1',
    media_id: ratingCard.media_id,
    items: [{
      resource_type: 'magnet',
      provider: 'magnet',
      url: `magnet:?xt=urn:btih:${'e'.repeat(40)}`,
      info_hash: 'e'.repeat(40),
      display_title: '1080p',
      extraction_code: null,
      quality_tags: ['1080p'],
    }],
  },
  'https://media.magnetgoogo.com',
);
assert.equal(mappedDetail.rotten_tomatoes_rating_text, '91%');
assert.equal(mappedDetail.rotten_tomatoes_url, ratingDetail.rotten_tomatoes_url);
assert.equal(mappedDetail.bangumi_rating_text, '8.4/10');
assert.equal(mappedDetail.bangumi_subject_id, '123456');
assert.equal(mappedDetail.bangumi_url, ratingDetail.bangumi_url);

const mappedLegacyDetail = mergeMediaDetailIntoFeedItem(
  mappedCard,
  parsedLegacyDetail,
  {
    schema_version: 'media-resources/1',
    media_id: ratingCard.media_id,
    items: [],
  },
  'https://media.magnetgoogo.com',
);
assert.equal(mappedLegacyDetail.rotten_tomatoes_rating, 91);
assert.equal(mappedLegacyDetail.bangumi_rating, 8.4);

const cacheSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseCache.ts'), 'utf8');
const clientSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseClient.ts'), 'utf8');
const mappingSource = fs.readFileSync(path.join(process.cwd(), 'src/core/mediaReleaseMapping.ts'), 'utf8');
assert.match(cacheSource, /pointer_sha256/);
assert.match(cacheSource, /manifest_sha256/);
assert.match(cacheSource, /media-app-cache-index\/2/);
assert.match(cacheSource, /media-app-feed-cache\/2/);
assert.match(cacheSource, /media-app-catalog-cache\/2/);
assert.match(cacheSource, /media-app-detail-cache\/2/);
assert.match(cacheSource, /writeJsonAtomically/);
assert.match(cacheSource, /const targetFile = \(\) => new File\(directory, name\)/);
assert.match(cacheSource, /targetFile\(\)\.move\(backupFile\(\)\)/);
assert.match(cacheSource, /temporaryFile\(\)\.move\(targetFile\(\)\)/);
assert.match(cacheSource, /if \(!temporaryMoved\) deleteIfExists\(temporaryFile\(\)\)/);
assert.match(cacheSource, /backupFile\(\)\.move\(targetFile\(\)\)/);
assert.doesNotMatch(cacheSource, /target\.move\(backup\)[\s\S]*temporary\.move\(target\)/);
assert.match(cacheSource, /readJsonResilient/);
assert.match(cacheSource, /assertMediaPointerTransition\(identity, existing\?\.identity \?\? null\)/);
assert.match(cacheSource, /envelope\.detail_hash !== currentItem\.remote_detail_hash/);
assert.doesNotMatch(cacheSource, /CryptoJS|SecureStore|CACHE_EXPIRY/);
assert.match(clientSource, /selectMediaCurrentCandidate\(candidates, acceptedIdentity\)/);
assert.match(clientSource, /cachedMediaPointerIdentity\(\)/);
assert.match(clientSource, /Promise\.race\(\[request, timeout\]\)/);
assert.match(clientSource, /manifest_refresh_skipped: true/);
assert.match(clientSource, /function detailSyncKey\(item: MovieFeedItem\)/);
assert.match(clientSource, /item\.content_kind[\s\S]*item\.movie_id[\s\S]*item\.remote_release_id[\s\S]*item\.remote_detail_hash/);
assert.match(clientSource, /const syncKey = detailSyncKey\(item\)/);
assert.doesNotMatch(clientSource, /detailSyncs\.get\(item\.movie_id\)/);
assert.match(clientSource, /from '\.\/mediaReleaseMapping'/);
assert.match(mappingSource, /rotten_tomatoes_rating: card\.rotten_tomatoes_rating \?\? null/);
assert.match(mappingSource, /bangumi_rating: card\.bangumi_rating \?\? null/);
assert.match(mappingSource, /detail\.rotten_tomatoes_rating \?\? item\.rotten_tomatoes_rating/);
assert.match(mappingSource, /detail\.bangumi_rating \?\? item\.bangumi_rating/);

console.log(JSON.stringify({
  status: 'PASS',
  mirrored_same_revision: true,
  same_revision_conflict_rejected: true,
  rollback_rejected: true,
  single_endpoint_higher_revision_accepted: true,
  cache_identity_fields: true,
  atomic_shard_contract: true,
  content_addressed_catalog_cache: true,
  plaintext_media_cache: true,
  four_rating_protocol: true,
  legacy_rating_compatibility: true,
  client_rating_mapping: true,
  detail_singleflight_release_scoped: true,
}));
