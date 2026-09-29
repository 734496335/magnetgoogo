export const D1_FREE_DAILY_ROWS_WRITTEN = 100_000;
export const D1_ENGINEERING_ROWS_WRITTEN_BUDGET = 70_000;
export const D1_PAID_INCLUDED_ROWS_WRITTEN_MONTH = 50_000_000;

export function estimateD1WriteCapacity(ops, row) {
  if (!row?.day) return null;
  const funnel = (ops?.search_value_funnel?.rows || []).find((item) => item.day === row.day) || {};
  const active = Math.max(0, Number(row.active_devices || 0));
  const searched = Math.max(0, Number(row.search_devices || 0));
  const result = Math.max(0, Number(row.result_devices || 0));
  const action = Math.max(0, Number(row.action_devices || 0));
  const sessions = Math.max(0, Number(row.sessions || 0));
  const submitted = Math.max(0, Number(funnel.submitted_searches ?? row.searches_submitted ?? 0));
  const completed = Math.max(0, Number(funnel.completed_searches ?? row.searches_completed ?? 0));
  const satisfied = Math.max(0, Number(funnel.satisfied_searches || 0));

  // Conservative physical-row estimate under the current schema. D1 charges
  // secondary-index maintenance as rows written. Legacy ops_daily counters are
  // rebuild-only and intentionally absent from the live hot path.
  const components = {
    alias_mapping_rows: active * 2,
    device_latest_rows: active * 3,
    device_day_rows: (active + searched + result + action) * 2,
    session_rows: sessions,
    search_state_rows: (submitted + completed + satisfied) * 4,
  };
  const estimated = Object.values(components).reduce((sum, value) => sum + value, 0);
  const safeDau = active > 0 && estimated > 0
    ? Math.floor(active * D1_ENGINEERING_ROWS_WRITTEN_BUDGET / estimated)
    : null;
  const projected5000 = active > 0 ? Math.round(estimated * 5000 / active) : null;
  const projected5000Month = projected5000 === null ? null : projected5000 * 30;
  return {
    estimation_version: 'd1-hot-path-v2-20260902',
    note: 'Conservative planning estimate; Cloudflare D1 Row Metrics remains billing authority.',
    day: row.day,
    components,
    estimated_rows_written: estimated,
    free_daily_limit_rows_written: D1_FREE_DAILY_ROWS_WRITTEN,
    engineering_budget_rows_written: D1_ENGINEERING_ROWS_WRITTEN_BUDGET,
    free_limit_pct: Math.round(estimated / D1_FREE_DAILY_ROWS_WRITTEN * 1000) / 10,
    conservative_linear_safe_dau: safeDau,
    paid_review_trigger_dau: safeDau ? Math.max(1, Math.floor(safeDau * 0.8)) : null,
    projected_rows_written_at_5000_dau: projected5000,
    five_thousand_dau_free_tier_safe: projected5000 !== null && projected5000 <= D1_ENGINEERING_ROWS_WRITTEN_BUDGET,
    workers_paid_included_rows_written_month: D1_PAID_INCLUDED_ROWS_WRITTEN_MONTH,
    projected_rows_written_at_5000_dau_30d: projected5000Month,
    five_thousand_dau_within_paid_included_writes: projected5000Month !== null && projected5000Month <= D1_PAID_INCLUDED_ROWS_WRITTEN_MONTH,
  };
}
