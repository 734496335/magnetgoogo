#!/usr/bin/env python3
import argparse
import base64
import gzip
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding


def load_key():
    value = os.environ.get("SOURCE_ENCRYPTION_KEY_HEX", "").strip()
    if len(value) != 64:
        raise ValueError("SOURCE_ENCRYPTION_KEY_HEX must contain 64 hexadecimal characters")
    key = bytes.fromhex(value)
    if len(key) != 32:
        raise ValueError("SOURCE_ENCRYPTION_KEY_HEX must decode to 32 bytes")
    return key


def parse_time(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError("missing %s" % field)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+0000"
    elif len(text) >= 6 and text[-3] == ":" and text[-6] in "+-":
        text = text[:-3] + text[-2:]
    parsed = None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError("invalid %s" % field)
    return parsed.astimezone(timezone.utc)


def decrypt(path, key):
    wrapper = json.loads(path.read_text(encoding="utf-8"))
    if set(wrapper) != {"iv", "ct", "sig", "gz"} or wrapper.get("gz") is not True:
        raise ValueError("%s: encrypted wrapper contract mismatch" % path.name)
    iv = bytes.fromhex(str(wrapper["iv"]))
    if len(iv) != 16:
        raise ValueError("%s: AES IV length is invalid" % path.name)
    ciphertext_text = str(wrapper["ct"])
    expected_sig = hmac.new(key, ciphertext_text.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, str(wrapper["sig"])):
        raise ValueError("%s: HMAC verification failed" % path.name)
    ciphertext = base64.b64decode(ciphertext_text, validate=True)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    compressed = unpadder.update(padded) + unpadder.finalize()
    envelope = json.loads(gzip.decompress(compressed).decode("utf-8"))
    if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
        raise ValueError("%s: source envelope schema is invalid" % path.name)
    if not isinstance(envelope.get("payload"), dict):
        raise ValueError("%s: source envelope payload is invalid" % path.name)
    if not isinstance(envelope.get("min_app_version"), str) or not envelope["min_app_version"].strip():
        raise ValueError("%s: min_app_version is invalid" % path.name)
    return wrapper, envelope


def counts(payload):
    rules = [
        rule
        for ruleset in payload.get("rulesets") or []
        if isinstance(ruleset, dict)
        for rule in ruleset.get("rules") or []
        if isinstance(rule, dict)
    ]
    green = sum(1 for rule in rules if (rule.get("health") or {}).get("status") == "green")
    return len(rules), green


def validate(path, key, now, min_remaining_hours):
    _, envelope = decrypt(path, key)
    issued_at = parse_time(envelope.get("issued_at"), "issued_at")
    expires_at = parse_time(envelope.get("expires_at"), "expires_at")
    if issued_at > now.replace(microsecond=0) and (issued_at - now).total_seconds() > 600:
        raise ValueError("%s: issued_at is implausibly in the future" % path.name)
    lifetime_hours = (expires_at - issued_at).total_seconds() / 3600.0
    if lifetime_hours < 24 or lifetime_hours > 96:
        raise ValueError("%s: envelope lifetime is outside 24-96 hours" % path.name)
    remaining_hours = (expires_at - now).total_seconds() / 3600.0
    if remaining_hours < min_remaining_hours:
        raise ValueError(
            "%s: only %.2f validity hours remain; minimum is %.2f"
            % (path.name, remaining_hours, min_remaining_hours)
        )
    rule_count, green_count = counts(envelope["payload"])
    if rule_count < 100 or green_count < 100 or green_count > rule_count:
        raise ValueError(
            "%s: source counts are implausible rules=%s green=%s"
            % (path.name, rule_count, green_count)
        )
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "remaining_hours": round(remaining_hours, 3),
        "min_app_version": envelope["min_app_version"],
        "rules": rule_count,
        "green": green_count,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", required=True, type=Path)
    parser.add_argument("--green", type=Path)
    parser.add_argument("--min-remaining-hours", type=float, default=12.0)
    args = parser.parse_args()
    if args.min_remaining_hours < 0 or args.min_remaining_hours > 48:
        raise ValueError("min-remaining-hours must be between 0 and 48")
    key = load_key()
    now = datetime.now(timezone.utc)
    full = validate(args.full, key, now, args.min_remaining_hours)
    result = {"status": "pass", "checked_at": now.isoformat(), "full": full}
    if args.green is not None:
        green = validate(args.green, key, now, args.min_remaining_hours)
        for field in ("issued_at", "expires_at", "min_app_version"):
            if full[field] != green[field]:
                raise ValueError("full/green source packs disagree on %s" % field)
        if green["rules"] > full["rules"] or green["green"] != full["green"]:
            raise ValueError("full/green source pack counts are inconsistent")
        result["green"] = green
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("verify-source-packs: %s: %s" % (type(exc).__name__, exc), file=os.sys.stderr)
        raise SystemExit(1)
