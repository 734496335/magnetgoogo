# Resource Index Phase-1 Independent Review

Date: 2026-07-25 (UTC+8)  
Blueprint: `计划-20260724-JavBus资源站内容索引第一阶段技术架构与开发执行指导.md`  
Scope: `magnet/resource_index/**` + tests/fixtures only  

## Verdict

**PHASE-1 PASS (implementation + automated gates)**  
Ready for human/product go/no-go on Phase-2 entry.  
Still **blocked** for: live acquisition, App UI, six-endpoint adult feed publish.

---

## §20 Acceptance checklist

### Architecture

| Gate | Result |
|------|--------|
| resource_index vs crawler_v3 / App / Web boundary | PASS — no imports of SearchResult / crawler_v3 / searchEngine |
| Parser no network / no DB write | PASS — adapters only parse RawDocumentEnvelope |
| Repository no JavBus | PASS — store has no site selectors/origins |
| Domain no JavBus CSS | PASS — no movie-box etc.; `source_prefix` required from adapter |
| Adult isolation from schema | PASS — `adult CHECK (adult = 1)`, feed scope=adult only |

### Data

| Gate | Result |
|------|--------|
| ≥6 detail fixtures ingested | PASS — 6 |
| ≥4 resource tables | PASS — 5 content-linked + empty |
| ≥1 content without resources | PASS — TST-006 |
| content_code unique | PASS — UNIQUE(content_type, content_code) |
| info_hash unique | PASS — UNIQUE(info_hash) |
| cross-content hash conflict blocked | PASS — ConflictError + rollback test |
| double ingest row-stable | PASS — idempotency tests + CLI demo |

### Quality

| Gate | Result |
|------|--------|
| Structured parser errors | PASS — ResourceIndexError + error_code |
| No bare `except:` | PASS |
| Offline tests only | PASS |
| No real adult image binaries | PASS — fixtures.invalid URLs only |
| No cookie/secrets in logs | PASS — log_event redacts cookie/magnet keys |
| validate_enum ALL VALID | PASS |
| crawler_v3 regression | PASS — 68 passed |
| git diff --check (module paths) | PASS (LF/CRLF warnings only) |

### Publish

| Gate | Result |
|------|--------|
| Six endpoints unchanged by this work | PASS — no mg-data/site deploy |
| App navigation unchanged | PASS — no app UI files in this module |
| Adult feed not published | PASS — local CLI only |
| Live fetch default off | PASS — javbus.json `enabled: false` |
| _progress + DEV-LOG updated | PASS |

---

## §21 Review findings (15 points)

| # | Risk | Status | Notes |
|---|------|--------|-------|
| 1 | JavBus pollutes domain | Fixed | Removed default `source_prefix="javbus"`; adapter must pass prefix |
| 2 | SearchResult.extra smuggling | PASS | No SearchResult usage |
| 3 | Hidden network/DB in parser | PASS | None |
| 4 | Null overwrite of good fields | PASS | `_coalesce` + unit test |
| 5 | Dedupe by full magnet string | PASS | Dedupe by info_hash only |
| 6 | Merge different hashes by title | PASS | Not done in phase-1 |
| 7 | Duplicate relations on re-import | PASS | Idempotency counts stable |
| 8 | Silent cross-content rebind | PASS | ConflictError |
| 9 | Real images / unsanitized HTML | PASS | Sanitized fixtures + hash check |
| 10 | Live fetch default on | PASS | Disabled |
| 11 | Swallow age-gate/403/DOM drift | PASS | Structured errors + tests |
| 12 | sources.json / prod publish | PASS for this module | Pre-existing dirty tree may have other edits; **do not commit them with this feature** |
| 13 | Log leak cookie/magnet/path | PASS | Filtered fields |
| 14 | Feed adult/scope | PASS | schema_version + scope=adult |
| 15 | Only happy-path tests | PASS | age-gate, empty, drift, conflict, invalid magnet, general scope reject |

---

## Commands re-run (2026-07-25)

```text
python -m pytest magnet/tests/resource_index -q          # 45 passed
python -m pytest magnet/tests/crawler_v3 -m "not integration" -q  # 68 passed
python validate_enum.py                                  # ALL VALID
```

---

## Recommended commit set (when user asks to commit)

```text
.gitignore
magnet/resource_index/
magnet/tests/resource_index/
magnet/tests/fixtures/resource_index/
docs/project-nebula/_progress.txt
docs/project-nebula/DEV-LOG.md
docs/project-nebula/RESOURCE-INDEX-PHASE1-REVIEW-2026-07-25.md
```

Do **not** include pre-existing dirty paths (`searchEngine.ts`, `sources.json`, etc.).

---

## Phase-2 entry (still gated)

Only after explicit product approval:

1. Authorized live source with robots/policy clearance  
2. Optional PostgreSQL  
3. Non-adult adapters  
4. Center Resource API  
5. App feature-flag discovery UI  

Do not start full-site crawl or public adult feed from this PASS alone.
