# Resource Index Phase-2 Plan

Document status: **Planning only — not approved for implementation**  
Date: 2026-07-25 (UTC+8)  
Depends on: Phase-1 PASS (`RESOURCE-INDEX-PHASE1-REVIEW-2026-07-25.md`)  
Product: Project Nebula / Magnet Googo  

> Phase-2 does **not** start until product explicitly approves a track below.  
> Phase-1 success does **not** authorize full-site crawl, public adult feed, or App production navigation.

---

## 0. Entry gates (all required)

| # | Gate | Evidence |
|---|------|----------|
| G1 | Phase-1 automated review PASS | Review doc + 45 tests green |
| G2 | Product chooses **one primary track** (P2-A … P2-D) | Written approval |
| G3 | Legal/compliance note for any **live** source | Owner + date recorded |
| G4 | No mixing with dirty App/`sources.json` release work | Isolated branch/worktree |
| G5 | Adult content remains isolated unless scope=adult + feature flag | Architecture review |

If any gate fails → stay on Phase-1 maintenance only.

---

## 1. Goals and non-goals

### 1.1 Goals

1. Move from “offline fixture lab” to **controlled production-adjacent index service**.
2. Support **more than one adapter**, including non-adult content types.
3. Provide a **stable read API** for future App/Web experiments.
4. Keep real-time search (`sources.json` / App handlers) working **unchanged** until dual-path fusion is deliberate.

### 1.2 Non-goals (still forbidden unless separate RFC)

- Public SEO pages for adult catalog.
- Unattended full-site historical crawl of robots-disallowed sites.
- Auto-promote adult feed to the six CDN endpoints.
- Deleting App/Web JavBus handlers before API parity proof.
- LLM-in-the-hot-path for every item.

---

## 2. Recommended track order

Do **not** parallelize all tracks. Suggested sequence:

```text
P2-A  Multi-adapter + non-adult domain expansion (offline-first)
  → P2-B  Persistence scale (PostgreSQL) + jobs/checkpoints
    → P2-C  Center Resource Read API
      → P2-D  App dual-path experiment (feature-flagged)
```

Live acquisition for JavBus remains a **side track** (P2-L) with highest compliance bar; it is **not** on the critical path for non-adult value.

---

## 3. Track definitions

### P2-A — Multi-adapter & content types (priority)

**Why first:** Proves domain model is site-agnostic without compliance risk.

**Deliverables**

- `ContentType` expansion: e.g. `movie`, `tv_episode`, `anime`, `software` (exact enum TBD).
- Second adapter (candidate: open metadata + magnet index that allows fixture/API use).
- Adapter registry: `source_id → ResourceSourceAdapter`.
- Fixture packs under `tests/fixtures/resource_index/<source>/`.
- Feed scopes: `general` and `adult` **never mixed** in one export.

**Acceptance**

- Domain still free of site CSS.
- Adult CHECK constraint remains for adult rows; general rows must `adult=0` with explicit schema migration (cannot silently insert adult into general feed).
- ≥1 non-adult fixture end-to-end ingest.
- Phase-1 JavBus fixtures still green.

**Estimate:** 3–6 days focused work.

---

### P2-B — PostgreSQL + jobs + checkpoints

**Why:** SQLite is fine for lab; multi-writer / server deploy needs stronger store.

**Deliverables**

- `PostgresResourceRepository` implementing the same `ResourceRepository` protocol.
- Migration tool (Alembic or plain SQL numbered migrations) **separate DB** from admin-server.
- Job runner (stdlib or lightweight queue): `ingest_run`, stream checkpoints.
- Enable `crawl_checkpoints` for listing cursors / last detail key.
- Backfill: SQLite dump → Postgres import script.

**Acceptance**

- Protocol tests run against both SQLite and Postgres (docker optional in CI).
- Transaction boundaries unchanged (single content atomic).
- Checkpoint resume without duplicate content/resource rows.

**Estimate:** 5–8 days.

---

### P2-C — Center Resource Read API

**Why:** App/Web must not write SQLite; read path needs stable contract.

**Deliverables**

- Read-only HTTP API (Workers / small Node/Python service — choose one stack in kickoff).
- Endpoints (draft):

```text
GET /v1/content/{content_code}
GET /v1/content/{content_code}/resources
GET /v1/search?q=
GET /v1/feed?scope=general|adult&limit=
```

- Auth: service token for internal; adult scope requires explicit header + server flag.
- Response schema versioned; **no cookies, no raw HTML, default no full magnet** (magnet behind elevated permission or deep-link token).

**Acceptance**

- OpenAPI or equivalent published in `docs/project-nebula/`.
- Contract tests with frozen fixtures.
- Adult endpoints refuse when `ADULT_API_ENABLED=0`.

**Estimate:** 4–7 days.

---

### P2-D — App dual-path experiment

**Why:** Product value only after read API exists.

**Deliverables**

- Feature flag `resource_index_discovery` (config.json + remote config).
- Hidden/experimental entry under Settings or long-press — **not** default home tab.
- Age gate for adult scope; general scope only by default.
- Keep existing real-time search as primary path.
- Analytics events: `ri_open`, `ri_content_view`, `ri_copy_magnet` (no PII).

**Acceptance**

- Flag off → zero RI UI code paths in release UX.
- K30S checklist for flag on/off.
- No adult content in general UI surfaces.

**Estimate:** 5–10 days after P2-C.

---

### P2-L — Live acquisition (optional, high bar)

**Only if** source policy allows automated fetch.

**Hard requirements**

```text
MAGNET_RESOURCE_LIVE_FETCH_ENABLED=1
--acknowledge-source-policy
robots/ToS reviewed and recorded
concurrency=1, delay>=10s, max_pages small
stop on 403/429/challenge/age-gate
cookies memory-only
no UA/proxy rotation as “bypass”
```

**JavBus specifically:** robots `Disallow: /` → **default remains fixture-only** until written legal/product exception.

**Acceptance**

- Policy tests remain green.
- Live path never required for CI.
- Manual one-shot log + ingest run audit.

**Estimate:** 2–4 days after policy approval (not including legal).

---

### P2-M — Handler consolidation (late)

**Goal:** Reduce App/Web JavBus duplication via center service.

**Preconditions:** P2-C parity for search-by-code + magnet list; latency budget documented.

**Acceptance**

- Shadow mode: App compares center vs local handler samples.
- Only then feature-flag cutover; keep local fallback one release.

---

## 4. Architecture deltas from Phase-1

```text
Phase-1:
  Fixture → Adapter → Domain → SQLite → CLI / adult test feed

Phase-2 target:
  Fixture | Manual capture | (Optional live one-shot)
       → Adapter registry
       → Domain (multi ContentType)
       → Repository protocol
            ├─ SQLite (dev)
            └─ Postgres (server)
       → Jobs / checkpoints
       → Read API
       → App feature-flag UI (experimental)
```

**Unchanged principles**

- Domain does not import site selectors.
- Parser does not network or write DB.
- Real-time `sources.json` remains the free-search path until dual fusion is explicit.
- Adult isolation is a schema + feed + API concern, not a CSS class.

---

## 5. Schema / migration foreshadow

Phase-2 migrations (illustrative only):

| Version | Change |
|---------|--------|
| 0002 | Allow `adult IN (0,1)`; check content_type allow-list |
| 0003 | `risk_status` indexes; takedown table |
| 0004 | Job / checkpoint enrichment |
| 0005 | Soft-delete / tombstone for content |

No migration may touch admin-server `broadcast.db` or App AsyncStorage formats.

---

## 6. Testing strategy

| Layer | Phase-2 requirement |
|-------|---------------------|
| Unit | New adapter parsers + normalizers |
| Contract | Repository protocol × SQLite/Postgres |
| API | Pact or OpenAPI response tests |
| CI | Still default offline; live marked `@integration` |
| Device | K30S only for P2-D |

Minimum: keep Phase-1 suite green forever as regression core.

---

## 7. Risk register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Adult leak into general feed/API | High | Separate scope checks at export + API + App |
| Legal exposure on disallowed crawl | High | P2-L gated; fixture default |
| Dual search UX confusion | Medium | Flag off by default; primary = live search |
| Postgres ops cost | Medium | Stay SQLite until API needs multi-writer |
| Handler rewrite thrash | Medium | Shadow compare before cutover |

---

## 8. Decision checklist for product (fill before coding)

```text
[ ] Primary track: P2-A / P2-B / P2-C / P2-D / P2-L
[ ] Non-adult first source candidate: ________
[ ] Postgres target environment: local / aliyun / other
[ ] Adult API ever exposed externally? yes/no
[ ] App experiment timeline: ________
[ ] Owner for compliance of any live source: ________
```

---

## 9. First implementation slice (when approved)

Recommended kickoff after approval of **P2-A**:

1. T0: branch `feat/resource-index-phase2-a` from clean base.
2. T1: ContentType expansion + schema 0002 + adult constraint redesign tests.
3. T2: Adapter registry + second offline adapter + fixtures.
4. T3: Feed export dual-scope isolation tests.
5. T4: Review + stop (no App, no publish).

Stop again for review before P2-B.

---

## 10. Explicit out-of-scope reminders

- Do not auto-run green expansion loops into resource_index.
- Do not put adult catalog into `content-engine` SEO pipeline.
- Do not change `javbus_com_001` health in `sources.json` as part of RI work.
- Do not treat Phase-1 PASS as license to scrape JavBus continuously.

---

## 11. References

- Phase-1 architecture: `计划-20260724-JavBus资源站内容索引第一阶段技术架构与开发执行指导.md`
- Phase-1 review: `RESOURCE-INDEX-PHASE1-REVIEW-2026-07-25.md`
- AI rules: `AI-RULES.md`
- Progress: `_progress.txt`
