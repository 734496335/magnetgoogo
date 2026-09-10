# Media Crawler Oracle Migration Review — 2026-09-10

## Final architecture

Production cutover is complete.

Final topology:

`Oracle ARM64 compute-only -> verified SSH handoff -> Aliyun signer/finalizer -> R2 primary + Aliyun China static mirror`

The App protocol, public URLs, signing authority, pointer monotonicity and dual-plane verification contract are unchanged.

Oracle performs crawl/aggregate/magnet-only/rating/cover/quality work only. It has no production Ed25519 private key and no R2 upload token. Aliyun retains the production signing private key, R2 upload token, finalizer, and China static mirror. R2 remains the primary public media plane.

## Why the architecture changed

The original host-coupled pipeline used `FilesystemPublisherBackend(public_root)` as the Aliyun publisher. Moving that pipeline unchanged to Oracle could have written the supposed Aliyun mirror to Oracle local disk and created R2/Aliyun split-brain.

A first migration design added Oracle->Aliyun SSH static publication. Runtime review then found a better trust boundary: keep all signing and public publication on Aliyun, and make Oracle compute-only. This also avoids copying the production signing key or R2 token to Oracle.

The first compute/finalizer draft used an Aliyun localhost port-forward to Oracle outbox port 18766. The existing Travel SSH key intentionally had `permitopen=127.0.0.1:8765`, so 18766 forwarding was administratively rejected. The final design therefore does not widen that key. Aliyun directly executes restricted non-PTY SSH `cat -- <exact outbox path>` over the already pinned Travel identity and streams the handoff locally. No new public port or forwarding permission is required.

## Handoff security and reliability

The compute handoff contains status, final movie/series feeds and cover bundles. Its manifest binds exact SHA-256 and size for every member.

Fail-closed checks cover:

- safe relative archive paths only;
- regular files only, no symlinks;
- duplicate member rejection;
- duplicate manifest descriptor rejection;
- exact archive member-set equality;
- SHA-256 and size verification;
- atomic Oracle outbox pointer replacement;
- Aliyun streamed download with strict `known_hosts` and BatchMode;
- remote commands restricted to exact `cat -- /var/lib/magnet-media/outbox/...` paths;
- local atomic inbox installation;
- exact SHA/size reuse of an already downloaded package;
- required timezone-aware `finished_at`;
- default maximum handoff age 12h;
- >15 minute future clock skew rejection.

A repeated already-finalized handoff is an idempotent no-op and reports `published=false`.

## Publication safety

Aliyun finalizer validates compute status, quality, freshness, cover audits and count floors before signing. It reconciles both current public planes before building a revision+1 candidate.

Formal publication order remains:

1. publish immutable objects to Aliyun static mirror;
2. publish immutable objects to R2;
3. verify Aliyun local current is still the exact preflight pointer;
4. promote R2 `current.json`;
5. promote Aliyun `current.json`;
6. recover deterministically if Aliyun pointer promotion is ambiguous/fails;
7. verify both public endpoints against the exact candidate pointer;
8. only then persist finalizer idempotency state.

Same-revision rebinding, rollback, stale handoff revision and unexpected pointer mutation remain hard failures.

## Runtime proof

### Oracle compute

Native image:

- platform: `linux/arm64`
- verified image SHA from migration run: `sha256:2df7195fdfeb4a42b2a51dc7df45a69fa987aceb2a158676aab40890bf771e11`

First accepted compute handoff:

- run: `20260910T045933Z-fb9b9e38`
- previous revision: 40
- movies: 421
- series: 538
- resources: 6663
- package bytes: 67,624,960
- package SHA-256: `93a2fa10a0cfd55b67e10c9aecd78730457f1a3514eeeefa2997c2f165f5606f`
- required degraded sources: none
- failed freshness groups: none
- series freshness: 4/4

Six configured sources had successful durable crawl state and non-zero current magnet evidence in the accepted compute status: sixv 120 resources, dytt8899 179, meijumi 1471, sixv-series 604, bitba-series 396, mjf-series 57. A direct live sixv listing->detail->magnet probe also passed. Some additional single-source live probe invocations were blocked by the execution layer and are not falsely claimed as independent live-probe PASS.

### Candidate

Aliyun candidate from the first handoff:

- candidate revision: 41
- release: `20261030T000000Z-f9d2f301`
- `candidate_verified=true`
- `published=false`
- 421 movies / 538 series / 6663 resources
- 2831 signed objects verified
- no quality regressions
- R2/Aliyun revision40 pointer bytes unchanged before/after candidate

### Formal cutover publish

At 2026-09-10 17:01 CST the finalizer formally published revision41:

- release: `20261030T000000Z-f9d2f301`
- pointer SHA-256: `6715cf6681380ac6618e642efbe1b6860f9d73990736d12d3cb97269b23a4bdc`
- both R2 and Aliyun verified exact revision41 convergence
- each plane reused 2808 immutable objects and uploaded only 24 new objects

After revision41 App live protocol/security verification passed, timers were cut over:

- Oracle `magnet-media-oracle-compute.timer`: enabled + active
- Aliyun `magnet-media-compute-finalizer.timer`: enabled + active
- old Aliyun `magnet-media-daily.timer`: disabled + inactive, not deleted
- Travel tunnel/service remained healthy
- obsolete media 18766 tunnel unit: disabled + inactive

### First post-cutover production cycle

A full production cycle was then manually triggered through the exact new architecture.

Oracle produced:

- run: `20260910T092021Z-ed7c0acb`
- previous revision: 41
- movies: 421
- series: 539
- resources: 6672
- handoff bytes: 67,737,600
- handoff SHA-256: `68d5aaf1d86b868656c365eb844abe8c99674f3cbfd5f5d2ebfcc4029ef41b66`

Aliyun fetched it over the production SSH streaming path (`reused=false`), verified it, signed it and automatically published revision42 at 18:11:25 CST:

- revision: 42
- release: `20261030T000000Z-64a9354f`
- manifest SHA-256: `b1704b65cb6556ae6bddb2215f128977617ec2dd413ddcd52e637d9ba652ef89`
- pointer SHA-256: `96fdc8d3ef5daf36641167cb25d55692a7f9402aa59cb2e0285cfe4312715c96`
- counts: 421 movies / 539 series / 6672 resources
- R2 and Aliyun exact convergence verified by the finalizer and independent App live tests
- finalizer durable state records run `20260910T092021Z-ed7c0acb`, revision42 and the same release id

## Test gates

Final local gates after all migration/finalizer changes:

- full Resource Index: `538 passed, 2 skipped`
- enum: `rules=241 / ALL VALID`
- Python compileall: PASS
- all Linux deployment shell syntax: PASS
- Git diff whitespace: PASS
- finalizer/transport/P3 targeted suites: PASS

P3/fault coverage includes tampered handoff, stale/aged handoff, duplicate/missing/extra archive members, malformed quality/freshness, missing R2 credential, local pointer changed before promotion, fixed R2-before-Aliyun ordering, Aliyun promotion recovery, recovery failure, idempotent repeat and safe existing-package reuse.

Revision42 App validation:

- live R2 media chain: PASS
- live Aliyun media chain: PASS
- exact cross-plane pointer equality: PASS
- signature/manifest/catalog/detail/resource/cover hash chain: PASS
- media-security: PASS
- resource-feed M1-M7: PASS
- M8: existing local-fixture-only SKIP
- release-build contract: PASS

No App rebuild was performed.

## Secrets and isolation

Verified after cutover:

- Oracle production signing private key: absent
- Oracle R2 upload token: absent
- Oracle outbox: loopback-only
- Travel container: healthy
- Aliyun keeps production signer and R2 token
- old Aliyun crawler units/image/state are preserved for rollback

## Remaining observation gate

CH-014 remains `piloting`, not `solved`, until the first natural scheduled cycle has executed: Oracle compute around 03:00 Asia/Shanghai followed by the Aliyun finalizer retry window beginning 04:30. The manually triggered post-cutover full production cycle already proves the complete production topology.

## Rollback

If a later scheduled cycle fails:

1. disable/stop `magnet-media-oracle-compute.timer` on Oracle;
2. disable/stop `magnet-media-compute-finalizer.timer` on Aliyun;
3. enable/start old Aliyun `magnet-media-daily.timer`;
4. verify R2 and Aliyun current pointers are identical and signed;
5. leave revision42 immutable objects/state intact;
6. diagnose the new path without deleting the old Aliyun image, units or state.

Do not copy production secrets to Oracle as part of rollback or troubleshooting.
