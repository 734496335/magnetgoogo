import assert from 'node:assert/strict';
import { estimateD1WriteCapacity } from './d1-write-capacity.mjs';

const ops = {
  search_value_funnel: {
    rows: [{
      day: '2026-09-01',
      submitted_searches: 1597,
      completed_searches: 719,
      satisfied_searches: 993,
    }],
  },
};
const row = {
  day: '2026-09-01',
  active_devices: 210,
  search_devices: 200,
  result_devices: 165,
  action_devices: 175,
  sessions: 50,
};
const capacity = estimateD1WriteCapacity(ops, row);
assert(capacity);
assert.equal(capacity.estimated_rows_written, 15836);
assert.equal(capacity.five_thousand_dau_free_tier_safe, false, '5k DAU at current search intensity must never be claimed Free-tier safe');
assert(capacity.conservative_linear_safe_dau >= 700 && capacity.conservative_linear_safe_dau <= 1200, capacity);
assert(capacity.paid_review_trigger_dau < capacity.conservative_linear_safe_dau);
assert(capacity.projected_rows_written_at_5000_dau > capacity.free_daily_limit_rows_written);
assert.equal(capacity.five_thousand_dau_within_paid_included_writes, true, '5k DAU projection should fit inside current Paid included D1 writes');
assert(capacity.projected_rows_written_at_5000_dau_30d < capacity.workers_paid_included_rows_written_month);
assert.equal(estimateD1WriteCapacity({}, null), null);

console.log(JSON.stringify({
  status: 'PASS',
  estimated_rows_written: capacity.estimated_rows_written,
  conservative_linear_safe_dau: capacity.conservative_linear_safe_dau,
  paid_review_trigger_dau: capacity.paid_review_trigger_dau,
  projected_rows_written_at_5000_dau: capacity.projected_rows_written_at_5000_dau,
  five_thousand_dau_free_tier_safe: capacity.five_thousand_dau_free_tier_safe,
  five_thousand_dau_within_paid_included_writes: capacity.five_thousand_dau_within_paid_included_writes,
}));
