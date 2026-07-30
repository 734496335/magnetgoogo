import assert from 'node:assert/strict';
import test from 'node:test';

import { maxObjectBytesFor, validateCurrentCandidate } from './worker.mjs';

const ONE_MIB = 1024 * 1024;
const TWO_MIB = 2 * 1024 * 1024;

test('allows a signed release manifest up to two MiB', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/releases/20260729T000000Z-b07630f3/manifest.json',
      'manifest',
      'application/json; charset=utf-8',
    ),
    TWO_MIB,
  );
});

test('keeps normal objects at one MiB', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/objects/detail/example.json',
      'detail',
      'application/json; charset=utf-8',
    ),
    ONE_MIB,
  );
});

test('does not grant the manifest limit to a disguised object kind', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/releases/20260729T000000Z-b07630f3/manifest.json',
      'detail',
      'application/json; charset=utf-8',
    ),
    ONE_MIB,
  );
});

test('does not grant the manifest limit to a disguised path', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/objects/detail/manifest.json',
      'manifest',
      'application/json; charset=utf-8',
    ),
    ONE_MIB,
  );
});

test('accepts a monotonic signed pointer shape for promotion', () => {
  const candidate = {
    schema_version: 'media-current/1',
    release_id: '20260730T000000Z-1234abcd',
    pointer_revision: 7,
    manifest_path: '/v1/releases/20260730T000000Z-1234abcd/manifest.json',
    manifest_sha256: 'a'.repeat(64),
    min_app_version: '0.2.1',
  };
  const existing = {
    ...candidate,
    release_id: '20260729T000000Z-8765dcba',
    pointer_revision: 6,
    manifest_path: '/v1/releases/20260729T000000Z-8765dcba/manifest.json',
    manifest_sha256: 'b'.repeat(64),
  };
  assert.equal(validateCurrentCandidate(candidate, existing), null);
});

test('rejects rollback and same-revision conflicts', () => {
  const existing = {
    schema_version: 'media-current/1',
    release_id: '20260730T000000Z-1234abcd',
    pointer_revision: 7,
    manifest_path: '/v1/releases/20260730T000000Z-1234abcd/manifest.json',
    manifest_sha256: 'a'.repeat(64),
    min_app_version: '0.2.1',
  };
  assert.match(validateCurrentCandidate({ ...existing, pointer_revision: 6 }, existing), /rollback/);
  assert.match(
    validateCurrentCandidate({ ...existing, release_id: '20260730T010000Z-deadbeef', manifest_path: '/v1/releases/20260730T010000Z-deadbeef/manifest.json' }, existing),
    /same revision/,
  );
});

test('does not grant the manifest limit to a non-JSON payload', () => {
  assert.equal(
    maxObjectBytesFor(
      'v1/releases/20260729T000000Z-b07630f3/manifest.json',
      'manifest',
      'application/octet-stream',
    ),
    ONE_MIB,
  );
});
