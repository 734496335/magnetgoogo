# Media Crawler Oracle Migration Review — 2026-09-10

## Scope

Migrate only the media crawler/compute runtime from Aliyun to Oracle ARM64 while preserving the existing public protocol and two distribution planes:

- R2 remains the primary public media plane.
- Aliyun remains the China static mirror at `https://cn.magnetgoogo.com/media`.
- The App protocol, signing authority, source health governance, and public `current.json` contract stay unchanged.
- Aliyun production timer remains the rollback authority until all Oracle runtime gates pass.

## Production baseline verified before migration work

On 2026-09-10 the Aliyun unattended publish completed successfully and advanced production to:

- pointer revision: `40`
- release: `20261030T000000Z-5888bcc0`
- movies: `421`
- series: `538`
- magnet resources: `6663`
- series freshness group: `4/4`, min_fresh=`2`
- only degraded source: supplemental `dytt8899`
- required degraded sources: none
- failed freshness groups: none

Aliyun `magnet-media-daily.timer` remains enabled and active. No Oracle production timer has been installed or enabled.

## P0 defects found by migration review

### 1. Local filesystem publisher was host-coupled

The previous `media_daily.py` used `FilesystemPublisherBackend(public_root)` as the Aliyun publisher. That was correct only while compute and the Aliyun static mirror were on the same host. Moving compute to Oracle without changing this would write the supposed Aliyun mirror to Oracle local disk.

The formal flow also promoted R2 before the local filesystem pointer, so an Oracle-hosted run could have advanced R2 while Aliyun public `current.json` stayed behind.

### 2. Legacy Aliyun scripts referenced a stale root

Older tools targeted `/var/www/magnetgoogo-site/media`, but the real production Nginx alias currently serves `/var/lib/magnet-media/public`. The stale tree had a different `current.json` hash and must not be treated as authority.

### 3. Oracle data disk would not be used by the old runner contract

`run-media-daily.sh` mounts host `/var/lib/magnet-media` into the container and the hardened systemd unit only allows writes under that path. Merely changing JSON to `/data/...` would either miss the 150 GB data disk or fail under `ProtectSystem=strict`.

### 4. Legacy installer was unsafe for shadow migration

The old installer also configures Nginx and can initialize signing keys. Oracle shadow must not modify Nginx and must never mint a new production signing authority.

## Implemented architecture

### Cross-host Aliyun static mirror publisher

Added `SshStaticMirrorPublisher` plus `deploy/resource-index/remote-static-mirror.py`.

Publication semantics:

1. Build one verified immutable publish plan from the signed release.
2. Query Aliyun for existing immutable files and compare size + SHA-256.
3. Transfer only missing immutable objects.
4. Remote helper accepts only exact planned regular files; extra members, duplicate tar members, symlinks and unsafe paths are rejected.
5. Verify the complete immutable plan again on Aliyun before any pointer promotion.
6. Preflight Aliyun `current.json` against the exact previously observed SHA-256 and require a one-revision advance.
7. Promote R2 current pointer.
8. Promote Aliyun current pointer atomically through the remote helper.
9. If the SSH response is ambiguous, retry the idempotent Aliyun promotion once. If still uncertain, use the signed one-revision control-recovery path.
10. Verify both public planes against the candidate pointer.

The remote mirror root is now fail-closed: it must be an absolute normalized non-root path and cannot contain traversal or unsafe whitespace forms.

### Pointer hardening

The remote helper independently validates:

- SHA values are lowercase 64-character hex strings.
- `release_id` is safe.
- `manifest_path` is exactly `/v1/releases/<release_id>/manifest.json`.
- candidate revision advances exactly one step unless bytes already equal the candidate.
- an equal revision cannot be rebound to different bytes.
- the candidate manifest exists on the mirror and matches `manifest_sha256`.
- stale preflight authority SHA is rejected.

### Oracle shadow deployment

Added a two-stage deployment:

1. `build-media-oracle-image.sh`
   - build-only;
   - requires native `aarch64` host;
   - tags the image with the release name;
   - requires resulting image `linux/arm64`;
   - checks Python runtime imports and `ssh`/`scp` availability;
   - does not call systemd, Nginx or production credentials.

2. `install-media-oracle-shadow.sh`
   - refuses to build an image itself;
   - requires the release-matched ARM64 image to exist and pass runtime checks first;
   - requires `/data` to be a distinct mounted volume;
   - binds `/data/magnet-media/state` to `/var/lib/magnet-media` through a dedicated mount unit;
   - refuses a hidden non-empty legacy `/var/lib/magnet-media` directory before first mount;
   - requires existing production signing material and never generates a key;
   - refuses a production R2 token during shadow mode;
   - installs only `magnet-media-oracle-shadow.service`, which can run only `candidate` mode;
   - installs no production media timers/retry unit and does not touch Nginx.

## State migration

The current production source durable state was re-snapshotted after revision40. The `sources` archive was SHA-256 verified at Aliyun, local transfer and Oracle destination, with 19 source state files present on Oracle.

`bundles`, ratings and rating-cache are reusable performance state, not publication authority. A larger refreshed archive was locally verified but further transfer was blocked by the execution layer. Oracle already contains the previous verified bundle snapshot; a full shadow candidate must rebuild/verify final bundles before any cutover.

Historical `runs`, `withhold-test` and similar bulk runtime artifacts are intentionally not required for migration correctness.

## Security posture

- A dedicated Oracle-to-Aliyun Ed25519 deployment key was generated for the media mirror.
- The runtime no longer logs in as Aliyun `admin`. It uses a dedicated `magnetmedia` user that is not a sudo/wheel group member and owns no media mirror files.
- Direct ACL write access was rejected during review because newly created immutable files would become writable/owned by the deploy user. The final design removes deploy-user ACL access from the media tree and permits only passwordless execution of the fixed root-owned helper through one sudoers rule.
- The privileged helper independently refuses any root other than `/var/lib/magnet-media/public`, so restricted sudo cannot be redirected to another filesystem tree.
- The runtime no longer uploads a Python helper. It calls fixed root-owned `/usr/local/libexec/magnet-media-remote-static-mirror.py`; plans/payloads remain unprivileged temporary inputs and every immutable path/hash is validated before root-owned promotion.
- The key authorization is restricted to the Oracle public source IP with OpenSSH `restrict`, and agent/port/X11 forwarding plus PTY are unavailable.
- Aliyun host keys were independently scanned from both sides and matched before a fixed known_hosts file was prepared.
- No R2 production upload token has been copied to Oracle during shadow preparation.
- No signing private key value was printed into logs or chat.

## Verification completed

Latest local gates after all hardening changes:

- migration/resource-index targeted suite: `104 passed`
- full Resource Index suite: `495 passed, 1 skipped`
- `python magnet/validate_enum.py`: `rules=241`, `ALL VALID`
- Python compile: PASS
- Linux shell syntax: PASS
- Git whitespace/diff check: PASS
- PowerShell current-promotion syntax: PASS

Tests cover at least:

- remote Aliyun configuration completeness and safe path validation;
- immutable delta reuse and conflict rejection;
- unplanned tar member rejection;
- duplicate tar member rejection;
- one-revision pointer promotion;
- stale authority SHA rejection;
- release/manifest path binding;
- idempotent already-promoted recovery;
- remote Aliyun preflight before any current-pointer promotion;
- ambiguous SSH promotion retry + recovery;
- Oracle build-only side-effect boundary;
- Oracle candidate-only service and data-volume contract;
- dedicated Aliyun mirror-user least-privilege installer with no direct media-tree ACL/ownership;
- fixed privileged helper restricted to the exact production mirror root;
- Oracle six-source live-chain probe that cannot be satisfied by durable `minimum_interval` state;
- required-freshness sources treated as degraded when the current crawl/feed contributes zero magnets;
- Oracle candidate acceptance that freezes R2/Aliyun pointer bytes before/after and validates aggregate quality, magnet-only counts and cover audits;
- App live-only network mode for validating the current public release when historical local revision4 fixtures are absent;
- legacy Aliyun tools using the live `/var/lib/magnet-media/public` authority.

## Runtime gates still required before cutover

The following are explicitly NOT marked passed yet:

1. install and verify the fixed root-owned Aliyun mirror helper plus dedicated `magnetmedia` user and helper-only sudo rule using the Oracle deploy public key;
2. native Oracle ARM64 Docker image build and image inspection;
3. execute the new six-source live-chain probe covering listing -> detail -> magnet for all six configured sources;
4. secure installation of the existing production signing material on Oracle;
5. execute `run-media-oracle-shadow-acceptance.sh`, which freezes both public pointers, runs mirror/source probes plus the full signed `candidate`, captures after-pointers even on candidate failure, and requires byte-for-byte no-publication evidence;
6. final quality gates: required freshness, all four migration freshness members, aggregate accepted-output quality, magnet-only, covers and counts;
7. App media compatibility/network/security test suites against the Oracle candidate; current revision40 live public network/security checks already pass locally;
8. cross-host publication fault injection, including interrupted Aliyun pointer promotion;
9. only after all above pass: copy the minimum production R2 credential, install the production Oracle timer, stop (do not delete) the Aliyun timer and execute one formal Oracle publish;
10. verify R2 and Aliyun pointer + manifest/object convergence after that formal publish.

## Current blocker

The connected execution layer currently rejects or blocks multiple classes of nested SSH operations involving Docker, HTTP probes and signing-private-key transfer before those commands reach Oracle. This is a tooling execution blocker, not evidence that Oracle or the source sites failed.

Do not weaken security or encode/print secrets to bypass this blocker. Runtime gates remain pending until they can be executed normally.

## Rollback rule

Until the first verified Oracle formal publish is complete, Aliyun remains the production compute authority. Do not disable its daily timer.

After cutover, keep the Aliyun release, image, systemd units, durable state and signing/public control state intact so rollback is simply: stop Oracle media timer, re-enable Aliyun media timer, verify the two public pointers, then resume Aliyun compute.
