#!/usr/bin/env python3
"""Import new Travel notifications into the host's shared WeChat outbox."""
import argparse
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

ACCEPTED_LINES = {
    "ALERT_ENQUEUE accepted=true provider=xtuis_queued",
    "ALERT_ENQUEUE accepted=true provider=xtuis_queued_duplicate",
}
NAME_RE = re.compile(r"travel-[0-9a-f]{32}\.json\Z")
TEXT_LIMIT_BYTES = 47000
TITLE_LIMIT_BYTES = 512
SPOOL_LIMIT_BYTES = 300000


def read_event(path, expected_uid=1001):
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    if stat.S_ISLNK(path.lstat().st_mode):
        raise ValueError("invalid file type")
    fd = os.open(str(path), flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("invalid file type")
        if expected_uid is not None and info.st_uid != expected_uid:
            raise ValueError("unexpected producer")
        raw = stream.read(SPOOL_LIMIT_BYTES + 1)
    if len(raw) > SPOOL_LIMIT_BYTES:
        raise ValueError("oversized file")
    event = json.loads(raw.decode("utf-8"))
    if not isinstance(event, dict):
        raise ValueError("invalid schema")
    if type(event.get("version")) is not int or event["version"] != 1:
        raise ValueError("invalid schema version")
    if event.get("event_id") != path.stem:
        raise ValueError("invalid event identity")
    if event.get("key") != "travel-low-price":
        raise ValueError("invalid notification key")
    title, message = event.get("title"), event.get("message")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("invalid title")
    if not isinstance(message, str):
        raise ValueError("invalid message")
    if len(title.encode("utf-8")) > TITLE_LIMIT_BYTES:
        raise ValueError("oversized title")
    if len((title + message).encode("utf-8")) > TEXT_LIMIT_BYTES:
        raise ValueError("oversized notification")
    created, expires = event.get("created_at_epoch"), event.get("expires_at_epoch")
    if type(created) is not int or type(expires) is not int:
        raise ValueError("invalid timestamps")
    if not 60 <= expires - created <= 7200:
        raise ValueError("invalid lifetime")
    if created > int(time.time()) + 120:
        raise ValueError("future event")
    return event


def submit(event, notifier):
    remaining = event["expires_at_epoch"] - int(time.time())
    if remaining <= 0:
        return "expired"
    result = subprocess.run(
        [sys.executable, notifier, "enqueue", "--key", event["key"],
         "--title", event["title"], "--message", event["message"],
         "--event-id", event["event_id"], "--ttl-seconds", str(remaining), "--strict"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        timeout=20, check=False)
    if result.returncode == 0 and ACCEPTED_LINES.intersection(result.stdout.splitlines()):
        return "accepted"
    return "retry"


def remove_file(path):
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def reject_file(path):
    try:
        os.replace(str(path), str(path.with_suffix(".rejected")))
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def relay_once(spool, notifier, expected_uid=1001, max_items=50):
    counts = {"accepted": 0, "expired": 0, "rejected": 0, "retry": 0}
    try:
        spool_info = spool.lstat()
    except FileNotFoundError:
        return counts
    if not stat.S_ISDIR(spool_info.st_mode):
        raise ValueError("invalid spool directory")
    if type(max_items) is not int or not 1 <= max_items <= 100:
        raise ValueError("invalid batch size")
    candidates = []
    for path in spool.iterdir():
        if not NAME_RE.fullmatch(path.name):
            continue
        try:
            candidates.append((path.lstat().st_mtime, path.name, path))
        except FileNotFoundError:
            continue
    for _, _, path in sorted(candidates)[:max_items]:
        try:
            event = read_event(path, expected_uid)
        except FileNotFoundError:
            continue
        except (OSError, ValueError, UnicodeError):
            if reject_file(path):
                counts["rejected"] += 1
            else:
                counts["retry"] += 1
            continue
        try:
            outcome = submit(event, notifier)
        except (OSError, subprocess.TimeoutExpired):
            outcome = "retry"
        counts[outcome] += 1
        if outcome in ("accepted", "expired") and not remove_file(path):
            counts["retry"] += 1
    return counts


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid arguments")


def main(argv=None):
    try:
        parser = QuietParser()
        parser.add_argument("--spool-dir", required=True)
        parser.add_argument("--notifier", default="/opt/magnet-alerts/magnet-alert.py")
        parser.add_argument("--expected-uid", type=int, default=1001)
        parser.add_argument("--max-items", type=int, default=50)
        args = parser.parse_args(argv)
        if args.expected_uid < 0:
            raise ValueError("invalid producer UID")
        counts = relay_once(Path(args.spool_dir), args.notifier,
                            expected_uid=args.expected_uid, max_items=args.max_items)
        print(json.dumps(counts, sort_keys=True))
        return 1 if counts["retry"] or counts["rejected"] else 0
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
