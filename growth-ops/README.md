# MagnetGoogo Growth Ops

This directory is the minimal, evidence-first growth operations layer defined by the authoritative SEO growth strategy.

## Hard rules

- Do not create new indexable URLs from automation.
- R2 remains the raw website-growth fact source; D1 is a rebuildable compact read model.
- CRO/SEO experiments consume `trusted_first_party` clicks only as a lower-bound website signal. Direct/unverified traffic is diagnostic only.
- Search Console is L1 search evidence; `/go/download` is L2 website-action evidence; App New Device/New DSSU/reuse is L3 aggregate outcome evidence. Never claim user-level web-to-install attribution.
- 2026-08-26 through 2026-08-29 remain partial for App-side causal comparisons.
- Missing Google authorization is `BLOCKED_EXTERNAL_AUTH`, never zero traffic.
- Experiments remain proposals until their evidence gates are satisfied. Automation must not silently publish page changes.
- D1 Free is an operating tier, not a 5k-DAU capacity target: keep a 70k rows-written/day engineering budget below the 100k/day hard limit and surface the Paid-review trigger before capacity is tight.
- Full 31-day D1 apply is disaster recovery only. Normal shadow repair must use verified receive-day incremental replay; unbounded full apply is budget-guarded.
- Acquisition channel mix is fail-closed: every indexable sitemap URL must load the privacy-safe tracker, and historical low-coverage `bySource` remains diagnostic. Directional channel-mix decisions start only from complete post-full-coverage operational days whose source totals equal qualified landing-view totals; current gate starts with the first clean day 2026-09-08 (UTC+8), requires 3 complete days and >=200 qualified views.

## Files

- `experiments.json` — experiment registry and evidence gates.
- `search-console/latest.json` — generated only after a real authorized Search Console ingest succeeds.
- `scripts/search-console-ingest.mjs` — official Search Analytics API ingest.
- `scripts/growth-opportunity-report.mjs` — combines Search Console with first-party trusted website clicks and emits ranked proposals.
- `scripts/analytics-shadow-recover.mjs` — fail-closed D1 shadow recovery. Same-UTC-day D1 Free quota failures stop with `BLOCKED_PLATFORM_QUOTA`; after the UTC reset it refreshes the verified 31-day R2 cache and replays only the affected receive-day checkpoint(s) into D1.
- `../scripts/analytics_shadow_recovery.ps1` — Windows Task Scheduler wrapper. Production schedule is 08:05 local, five minutes after the 00:00 UTC D1 Free quota reset.

## D1 capacity gate

- 2026-09-01 verified-cache audit after hot-path no-op optimization: conservative steady-state estimate ≈15.9k rows written/day at ~210 observed receive-day devices, about 15.9% of the Free hard limit.
- Conservative 70% engineering-budget crossover at the same usage intensity is ~923 DAU; Paid-plan review begins around ~742 DAU so migration happens before the hard limit.
- 5000 DAU projects to roughly 0.38M rows written/day / ~11.3M per 30 days at the current search intensity. This is not Free-tier safe, but is below the current Workers Paid included 50M D1 rows written/month. Do not redesign exact analytics merely to force 5k DAU onto Free.
- `cf-gateway/scripts/analytics-ops-write-budget-audit.mjs --day=YYYY-MM-DD` is the reproducible planning audit; Cloudflare Row Metrics remains the billing authority.

## Current experiment gate

The original homepage trust CRO is `CANCELLED_INVALID_BASELINE_AND_POLICY_CONFLICT`: its frozen 31.86% figure mixed non-home clicks into the homepage numerator and must never be used as a valid baseline. Any future homepage CRO must start from a fresh page-key-matched baseline and use evergreen trust/install guidance only. Current SEO experiments remain evidence-gated on existing URLs; automation creates no new indexable URL and publishes no page change automatically.
