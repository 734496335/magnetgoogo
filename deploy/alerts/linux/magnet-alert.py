#!/usr/bin/env python3
"""Best-effort production alert state machine for MagnetGoogo.

Primary delivery: Alibaba CloudMonitor external-alert endpoint.
Fallback delivery: QQ Mail SMTP authorization code.

The script is intentionally fail-open for production workloads: delivery errors are
reported to stderr but the process exits 0 unless --strict is supplied.
"""

import argparse
import base64
import hashlib
import json
import os
import smtplib
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path


DEFAULT_STATE = Path("/var/lib/magnet-alerts/state.json")


def _now_epoch():
    return int(time.time())


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _load_state(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    return value


def _atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".%s." % path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, str(path))
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def _cloudmonitor_send(title, message):
    url = os.environ.get("MAGNET_ALERT_CLOUDMONITOR_URL", "").strip()
    access_key = os.environ.get("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_ID", "").strip()
    access_secret = os.environ.get("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_SECRET", "").strip()
    if not url or not access_key or not access_secret:
        return False, "cloudmonitor_not_configured"
    security_word = os.environ.get("MAGNET_ALERT_CLOUDMONITOR_SECURITY_WORD", "").strip()
    body_message = message
    if security_word:
        body_message = "%s\n%s" % (body_message, security_word)
    payload = json.dumps(
        {
            "ruleName": "MagnetGoogo Production Alert",
            "title": title,
            "message": body_message,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "MagnetGoogo-Alert/1.0",
    }
    basic = base64.b64encode((access_key + ":" + access_secret).encode("utf-8")).decode("ascii")
    headers["Authorization"] = "Basic " + basic
    request = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            if int(getattr(response, "status", 200)) != 200:
                return False, "cloudmonitor_http_%s" % getattr(response, "status", "unknown")
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        return False, "cloudmonitor_%s" % type(exc).__name__
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        result = {}
    code = str(result.get("code") or "") if isinstance(result, dict) else ""
    if code and code != "200":
        return False, "cloudmonitor_code_%s" % code
    return True, "cloudmonitor"


def _smtp_send(title, message):
    auth_code = os.environ.get("MAGNET_ALERT_SMTP_AUTH_CODE", "").strip()
    user = os.environ.get("MAGNET_ALERT_SMTP_USER", "").strip()
    recipient = os.environ.get("MAGNET_ALERT_TO", "").strip()
    if not auth_code or not user or not recipient:
        return False, "smtp_not_configured"
    host = os.environ.get("MAGNET_ALERT_SMTP_HOST", "smtp.qq.com").strip()
    try:
        port = int(os.environ.get("MAGNET_ALERT_SMTP_PORT", "465"))
    except ValueError:
        return False, "smtp_port_invalid"
    email = EmailMessage()
    email["Subject"] = title
    email["From"] = user
    email["To"] = recipient
    email.set_content(message)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as client:
            client.login(user, auth_code)
            client.send_message(email)
    except (OSError, smtplib.SMTPException) as exc:
        return False, "smtp_%s" % type(exc).__name__
    return True, "smtp"


def _deliver(title, message, dry_run=False):
    if dry_run:
        print("ALERT_DRY_RUN title=%s" % title)
        return True, "dry_run"
    transport = os.environ.get("MAGNET_ALERT_TRANSPORT", "disabled").strip().lower()
    if transport == "disabled":
        return False, "disabled"
    if transport == "cloudmonitor":
        return _cloudmonitor_send(title, message)
    if transport == "smtp":
        return _smtp_send(title, message)
    if transport == "auto":
        cloud_ok, cloud_detail = _cloudmonitor_send(title, message)
        if cloud_ok:
            return True, cloud_detail
        smtp_ok, smtp_detail = _smtp_send(title, message)
        if smtp_ok:
            return True, smtp_detail
        return False, "%s;%s" % (cloud_detail, smtp_detail)
    return False, "transport_invalid"


def _entry(state, key):
    value = state.get(key)
    if not isinstance(value, dict):
        value = {}
    return value


def record_failure(state_path, key, threshold, severity, title, message, now, dry_run):
    state = _load_state(state_path)
    entry = _entry(state, key)
    previous_status = entry.get("status")
    failures = int(entry.get("consecutive_failures") or 0) + 1 if previous_status == "failed" else 1
    last_alert = int(entry.get("last_alert_epoch") or 0)
    alert_open = bool(entry.get("alert_open"))
    should_send = failures >= threshold and not alert_open
    delivered = False
    provider = "suppressed"
    if should_send:
        delivered, provider = _deliver(title, message, dry_run=dry_run)
        if delivered:
            alert_open = True
            last_alert = now
    entry.update(
        {
            "status": "failed",
            "consecutive_failures": failures,
            "alert_open": alert_open,
            "last_failure_epoch": now,
            "last_failure_at": _iso(now),
            "last_alert_epoch": last_alert,
            "last_alert_at": _iso(last_alert) if last_alert else None,
            "last_delivery": provider,
            "last_message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
            "severity": severity,
        }
    )
    state[key] = entry
    _atomic_write(state_path, state)
    print(
        "ALERT_FAILURE key=%s failures=%s threshold=%s sent=%s provider=%s"
        % (key, failures, threshold, str(delivered).lower(), provider)
    )
    return delivered, provider


def record_success(state_path, key, title, message, now, dry_run):
    state = _load_state(state_path)
    entry = _entry(state, key)
    alert_open = bool(entry.get("alert_open"))
    delivered = False
    provider = "suppressed"
    if alert_open:
        delivered, provider = _deliver(title, message, dry_run=dry_run)
        if delivered:
            alert_open = False
    entry.update(
        {
            "status": "success",
            "consecutive_failures": 0,
            "alert_open": alert_open,
            "last_success_epoch": now,
            "last_success_at": _iso(now),
            "last_delivery": provider,
        }
    )
    state[key] = entry
    _atomic_write(state_path, state)
    print("ALERT_SUCCESS key=%s recovery_sent=%s provider=%s" % (key, str(delivered).lower(), provider))
    return delivered, provider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", choices=("failure", "success", "test"))
    parser.add_argument("--key", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--severity", default="P1")
    parser.add_argument("--threshold", type=int, default=1)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--now-epoch", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if args.threshold < 1:
        raise ValueError("threshold must be >= 1")
    now = args.now_epoch if args.now_epoch is not None else _now_epoch()
    title = "[%s] %s" % (args.severity, args.title)
    message = "%s\n\nTime: %s\nHost: %s" % (
        args.message,
        _iso(now),
        os.uname()[1] if hasattr(os, "uname") else "unknown",
    )
    if args.status == "failure":
        delivered, detail = record_failure(
            args.state_file,
            args.key,
            args.threshold,
            args.severity,
            title,
            message,
            now,
            args.dry_run,
        )
    elif args.status == "success":
        delivered, detail = record_success(args.state_file, args.key, "[恢复] " + args.title, message, now, args.dry_run)
    else:
        delivered, detail = _deliver("[测试] " + args.title, message, dry_run=args.dry_run)
        print("ALERT_TEST sent=%s provider=%s" % (str(delivered).lower(), detail))
    if args.strict and not delivered:
        if args.status == "test" or detail not in ("suppressed", "disabled"):
            return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("magnet-alert: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        raise SystemExit(2 if "--strict" in sys.argv else 0)
