import assert from 'node:assert/strict';
import {
  RESOURCE_AUTO_SYNC_FOREGROUND_INTERVAL_MS,
  RESOURCE_AUTO_SYNC_MIN_INTERVAL_MS,
  ResourceAutoSyncGate,
  resourceFeedReleaseId,
  sameRemoteResourceRelease,
} from '../src/core/resourceAutoSync.ts';

function test(name, fn) {
  try {
    fn();
    console.log(`PASS  ${name}`);
  } catch (error) {
    console.error(`FAIL  ${name}`);
    throw error;
  }
}

test('foreground polling is low-frequency and materially longer than focus cooldown', () => {
  assert.equal(RESOURCE_AUTO_SYNC_FOREGROUND_INTERVAL_MS, 15 * 60_000);
  assert.ok(RESOURCE_AUTO_SYNC_FOREGROUND_INTERVAL_MS >= RESOURCE_AUTO_SYNC_MIN_INTERVAL_MS * 10);
});

test('failed network attempt is immediately retryable', () => {
  const gate = new ResourceAutoSyncGate();
  assert.equal(gate.tryStart('movie', 1_000), true);
  gate.complete('movie', false, 1_100);
  assert.equal(gate.tryStart('movie', 1_101), true);
});

test('successful sync throttles focus churn but not later visits', () => {
  const gate = new ResourceAutoSyncGate();
  assert.equal(gate.tryStart('movie', 1_000), true);
  gate.complete('movie', true, 2_000);
  assert.equal(gate.tryStart('movie', 2_001), false);
  assert.equal(gate.tryStart('movie', 2_000 + RESOURCE_AUTO_SYNC_MIN_INTERVAL_MS - 1), false);
  assert.equal(gate.tryStart('movie', 2_000 + RESOURCE_AUTO_SYNC_MIN_INTERVAL_MS), true);
});

test('single-flight blocks duplicate focus and foreground syncs', () => {
  const gate = new ResourceAutoSyncGate();
  assert.equal(gate.tryStart('series', 5_000), true);
  assert.equal(gate.tryStart('series', 5_001), false);
  gate.complete('series', false, 5_002);
  assert.equal(gate.tryStart('series', 5_003), true);
});

test('movie and series refresh gates are independent', () => {
  const gate = new ResourceAutoSyncGate();
  assert.equal(gate.tryStart('movie', 10_000), true);
  assert.equal(gate.tryStart('series', 10_000), true);
  gate.complete('movie', true, 10_100);
  gate.complete('series', false, 10_100);
  assert.equal(gate.tryStart('movie', 10_101), false);
  assert.equal(gate.tryStart('series', 10_101), true);
});

test('manual refresh success shares the same cooldown', () => {
  const gate = new ResourceAutoSyncGate();
  gate.markSuccess('movie', 20_000);
  assert.equal(gate.tryStart('movie', 20_001), false);
  assert.equal(gate.tryStart('movie', 20_000 + RESOURCE_AUTO_SYNC_MIN_INTERVAL_MS), true);
});

test('wall-clock rollback cannot suppress refresh indefinitely', () => {
  const gate = new ResourceAutoSyncGate();
  gate.markSuccess('movie', 100_000);
  assert.equal(gate.tryStart('movie', 90_000), true);
});

test('different immutable release IDs replace feed even when timestamps and counts match', () => {
  const previous = {
    generated_at: '2026-08-13T00:00:00Z',
    snapshot_captured_at: '2026-08-13T00:00:00Z',
    items: [{ remote_release_id: 'release-13' }],
  };
  const next = {
    generated_at: previous.generated_at,
    snapshot_captured_at: previous.snapshot_captured_at,
    items: [{ remote_release_id: 'release-14' }],
  };
  assert.equal(resourceFeedReleaseId(previous), 'release-13');
  assert.equal(resourceFeedReleaseId(next), 'release-14');
  assert.equal(sameRemoteResourceRelease(previous, next), false);
});

test('same immutable release ID suppresses redundant feed replacement', () => {
  const previous = { items: [{ remote_release_id: 'release-14' }] };
  const next = { items: [{ remote_release_id: 'release-14' }] };
  assert.equal(sameRemoteResourceRelease(previous, next), true);
  assert.equal(sameRemoteResourceRelease({ items: [{}] }, next), false);
});

console.log('RESOURCE_AUTO_SYNC_TESTS_PASS');
