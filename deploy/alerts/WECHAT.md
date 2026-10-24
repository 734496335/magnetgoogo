# Free personal-WeChat monitoring

This deployment uses the user-configured XTUIS account. Credentials belong only in
root-readable /etc/magnet-alerts/alert.env; never include a token in source, a URL
in a log, a command argument, or an example.

## Components and meaning of success

- magnet-alert.py failure/success maintains an incident state with an exclusive
  lock. With transport=xtuis it durably queues the event; with transport=mirror it
  also independently attempts the existing CloudMonitor route.
- xtuis_outbox.py distinguishes pending, provider accepted (msg_id), and provider
  confirmed. A provider receipt is not proof that the user read the message.
- magnet-alert-outbox.timer flushes every 30 seconds. Same-key incidents are
  ordered so a queued recovery cannot overtake its fault.
- magnet-media-health.timer observes the current Oracle compute and Aliyun
  finalizer services, their timers and completed JSON status. Missing/stale or
  running work cannot falsely clear an incident. Source freshness and redundancy
  are checked from current compute evidence without modifying source ratings.
- magnet-ops-health.timer checks configured services, jobs, containers, disk,
  memory, load, endpoints, certificates and peer TCP reachability every minute.
- Oracle Travel writes new notification digests to a private spool. The host
  relay imports them by stable event ID into the shared queue. The API token is
  never passed into the Travel container. Existing price eligibility, batching,
  and alert-state decisions remain in the application.

## Free quota and time bounds

XTUIS publishes 300 sends/day and 30 sends/minute for the free account:
https://xtuis.cn/ . Limits can change at the provider.

Production budgets are 50 POST attempts/day on Aliyun and 150/day on Oracle,
with at most 10 POST/minute and 4 receipt queries/minute per host. Budgets use
Asia/Shanghai midnight. They include retries; remaining provider allowance is a
buffer, not a separately configured paid service.

Price digests expire after 30 minutes. Ordinary incident messages expire after
24 hours. Up to four POST attempts use bounded backoff and Retry-After. A known
msg_id is only queried, never reposted. A lost POST response may still produce
duplicates because the provider has no request idempotency contract.

An expired price event is recorded but does not fail the sender unit. Unknown
receipts do not count as confirmed; pending work can be inspected with:

    sudo /opt/magnet-alerts/magnet-alert.py status

Successful business checks are silent. Persistent faults repeat after six hours
in the new monitors; the existing source-sync hooks retain their own 12/24-hour
repeat intervals. Recovery is sent once for an open incident.

## Installation and rollback

Install common code with deploy/alerts/linux/install-alerts.sh first. It preserves
an existing private configuration and does not activate the sender unless
MAGNET_ALERT_ENABLE_OUTBOX=1. Media installation requires
MAGNET_MEDIA_HEALTH_ROLE=compute (Oracle) or finalizer (Aliyun), and activates only
with ENABLE_MEDIA_HEALTH_TIMER=1. Ops host examples are in
deploy/ops-health/production; inspect them against current units before use.

The Travel snapshot in this directory corresponds to D:/lpproduct/travel.
Dockerfile.wechat builds one layer FROM the exact existing production image;
it copies the two changed modules to both /app and installed site-packages.
It does not fetch dependencies. Set MAGNET_WECHAT_SPOOL_DIR in the existing
Travel compose environment to /var/lib/travel-fare-monitor/wechat-outbox, and
MAGNET_WECHAT_TTL_SECONDS=1800. Keep the root API credential outside the container.
wechat_spool_checks.py is the copy of Travel tests/test_wechat_spool.py; run it
inside the Travel project together with its notify and engine tests.

Before installing, save the existing private environment, affected scripts,
systemd units and Travel image ID/compose/source under a root-only backup directory.
Rollback can disable the new health/sender/relay timers, restore those files,
retag the saved Travel image, and recreate only the Travel service after checking
that no scan is in progress. Do not restore old price spool files as new events.

## Operational limits

Peer TCP checks can detect a server becoming unreachable while the other server
can still deliver. Simultaneous loss of both servers or of the only WeChat
provider cannot be reported through that same path. The monitor observes the
listed applications and task status; it does not prove every movie URL plays.

Do not read historical fare observations to generate alerts: near-target fares
are intentionally dashboard-only. Only the application's actual send_message
boundary produces a WeChat event.
