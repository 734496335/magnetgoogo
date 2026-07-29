import assert from 'node:assert/strict';
import test from 'node:test';

import { maxObjectBytesFor } from './worker.mjs';

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
