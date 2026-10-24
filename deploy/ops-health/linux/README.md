# Host and application health alerts

This component performs read-only probes and sends state changes to the shared Magnet alert outbox. It does not restart applications, change source-health labels, or modify business data.

## Deployment

Install `deploy/alerts/linux` first. Place the host-specific JSON configuration at `/etc/magnet-alerts/ops-health.json` with mode 0600, then run `sudo bash install-ops-health.sh`. The installer preserves existing configuration. Use `ops-health.example.json` for its structure. Only configure units, containers and endpoints verified to belong to this host.

The timer runs 60 seconds after the previous check completes. Regular service/task failures require two observations; network, disk and certificate checks require three. Repeats are limited to one per six hours per check, with one recovery notification. A running oneshot task is not proof of recovery; completion must succeed. An unknown first run since boot does not send a recovery.

Supported arrays are `services` and `timers` (`unit`, optional `label`); `jobs` (`unit`, `max_age_seconds`, `max_run_seconds`); `containers` (`name`); `disks` (`path`, `max_used_percent`); `peers` (`host`, `port`, `label`); `http` (`url`, `label`, optional `json_checks` and `error_field`); and `certificates` (`host`, `label`, `min_days`).

New host-level notifications use `xtuis` by default. This preserves the transport settings of existing applications and avoids sending these new probes through unrelated legacy recipients. All XTUIS events share the host outbox budget. Override `transport` only when the destination and notification policy are known.

## Verification

Run `python3 ops-health-check.py --config /etc/magnet-alerts/ops-health.json --dry-run` to inspect findings without changing incident state or sending messages. Normal runs save the latest findings to `/var/lib/magnet-alerts/ops-health-latest.json` and use `/var/lib/magnet-alerts/ops-health.json` for incident state.

Peer TCP reachability detects network/host access loss; it does not by itself prove remote application health. Each host independently probes its own applications. Simultaneous loss of both hosts or the push provider is outside this two-host design.

## Disable or roll back

Stop and disable `magnet-ops-health.timer`, then wait for an active oneshot to complete before replacing files. Restoring the prior files and configuration must not erase the durable notification outbox or incident history. This component does not require a business service restart.
