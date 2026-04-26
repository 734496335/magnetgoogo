#!/usr/bin/env python3
"""
Encrypt sources.json → sources.enc.json for distribution.

Output format: { "iv": "<hex>", "ct": "<base64>", "sig": "<hex>" }
  - AES-256-CBC encryption
  - HMAC-SHA256 signature over ciphertext

Usage:
  python encrypt_sources.py                     # encrypt sources.json → dist/sources.enc.json
  python encrypt_sources.py --verify            # verify roundtrip
  python encrypt_sources.py --deploy            # encrypt + git push to GitHub Pages repo
"""

import json
import os
import sys
import hashlib
import hmac
import base64
import shutil
from pathlib import Path

# ── Must match crypto.ts key fragments ──
# Regenerate both together with _gen_key.py
KEY_HEX = "0986e63db310b07bffd3ef35c94c8f6d91561588ddaf98db7faa7907106b34de"

# Paths
SCRIPT_DIR = Path(__file__).parent
SOURCES_JSON = SCRIPT_DIR / "sources.json"
DIST_DIR = SCRIPT_DIR / "maggoogo-sources"  # GitHub Pages repo folder
DIST_FILE = DIST_DIR / "sources.enc.json"


def pad_pkcs7(data: bytes, block_size: int = 16) -> bytes:
    """PKCS#7 padding."""
    padding_len = block_size - (len(data) % block_size)
    return data + bytes([padding_len] * padding_len)


def unpad_pkcs7(data: bytes) -> bytes:
    """Remove PKCS#7 padding."""
    padding_len = data[-1]
    if padding_len > 16 or padding_len == 0:
        raise ValueError("Invalid PKCS7 padding")
    for b in data[-padding_len:]:
        if b != padding_len:
            raise ValueError("Invalid PKCS7 padding")
    return data[:-padding_len]


def aes_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-256-CBC encryption using PyCryptodome or fallback."""
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return cipher.encrypt(pad_pkcs7(plaintext))
    except ImportError:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import padding
            padder = padding.PKCS7(128).padder()
            padded = padder.update(plaintext) + padder.finalize()
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            enc = cipher.encryptor()
            return enc.update(padded) + enc.finalize()
        except ImportError:
            raise ImportError(
                "Need pycryptodome or cryptography: pip install pycryptodome"
            )


def aes_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-256-CBC decryption."""
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad_pkcs7(cipher.decrypt(ciphertext))
    except ImportError:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        dec = cipher.decryptor()
        padded = dec.update(ciphertext) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()


def encrypt_sources(sources_path: Path, config_path: Path = None) -> dict:
    """Encrypt sources.json with expiry metadata, return {iv, ct, sig}."""
    key = bytes.fromhex(KEY_HEX)
    iv = os.urandom(16)

    # Load raw sources
    raw = json.loads(sources_path.read_bytes())

    # Read config for expiry settings
    expiry_hours = 72  # default 3 days
    min_app_version = "1.0.0"
    schema_version = 1
    if config_path and config_path.exists():
        cfg = json.loads(config_path.read_text("utf-8"))
        expiry_hours = cfg.get("source_expiry_hours", 72)
        min_app_version = cfg.get("min_version", "1.0.0")
        schema_version = cfg.get("source_schema_version", 1)

    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=expiry_hours)

    # Wrap sources with metadata envelope
    envelope = {
        "schema_version": schema_version,
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "min_app_version": min_app_version,
        "payload": raw,
    }

    plaintext = json.dumps(envelope, ensure_ascii=False).encode("utf-8")

    # AES-256-CBC
    ciphertext = aes_cbc_encrypt(plaintext, key, iv)
    ct_b64 = base64.b64encode(ciphertext).decode("ascii")

    # HMAC-SHA256 over base64 ciphertext (matches CryptoJS.HmacSHA256(ct, key))
    sig = hmac.new(key, ct_b64.encode("utf-8"), hashlib.sha256).hexdigest()

    print(f"  Expiry: {expiry_hours}h → {expires_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Min app version: {min_app_version}")

    return {
        "iv": iv.hex(),
        "ct": ct_b64,
        "sig": sig,
    }


def verify_roundtrip(enc_payload: dict) -> bool:
    """Decrypt and verify the payload matches original."""
    key = bytes.fromhex(KEY_HEX)
    iv = bytes.fromhex(enc_payload["iv"])
    ct = base64.b64decode(enc_payload["ct"])

    # Verify HMAC
    expected_sig = hmac.new(
        key, enc_payload["ct"].encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if expected_sig != enc_payload["sig"]:
        print("✗ HMAC verification FAILED")
        return False

    # Decrypt
    plaintext = aes_cbc_decrypt(ct, key, iv)
    envelope = json.loads(plaintext)

    # Handle envelope format (with metadata) or raw format
    if "payload" in envelope:
        print(f"  Schema v{envelope.get('schema_version', '?')}")
        print(f"  Issued:  {envelope.get('issued_at', '?')}")
        print(f"  Expires: {envelope.get('expires_at', '?')}")
        print(f"  Min app: {envelope.get('min_app_version', '?')}")
        data = envelope["payload"]
    else:
        data = envelope

    # Count sources
    rules = data
    if isinstance(data, dict):
        if data.get("rulesets") and data["rulesets"][0].get("rules"):
            rules = data["rulesets"][0]["rules"]
        elif data.get("rulesets"):
            rules = data["rulesets"]
        elif data.get("sources"):
            rules = data["sources"]
        else:
            rules = []

    count = len(rules) if isinstance(rules, list) else 0
    green = sum(
        1 for s in rules
        if isinstance(s, dict) and s.get("health", {}).get("status") == "green"
    )

    print(f"✓ Roundtrip OK — {count} sources ({green} green), {len(plaintext):,} bytes")
    return True


def main():
    if not SOURCES_JSON.exists():
        print(f"✗ {SOURCES_JSON} not found")
        sys.exit(1)

    config_path = DIST_DIR / "config.json"
    print(f"Encrypting {SOURCES_JSON} ...")
    payload = encrypt_sources(SOURCES_JSON, config_path)

    # Ensure dist directory
    DIST_DIR.mkdir(exist_ok=True)

    # Write encrypted file
    enc_json = json.dumps(payload)
    DIST_FILE.write_text(enc_json, encoding="utf-8")
    print(f"✓ Written {DIST_FILE} ({len(enc_json):,} bytes)")

    # Also create an index.html so GitHub Pages doesn't 404
    index_html = DIST_DIR / "index.html"
    if not index_html.exists():
        index_html.write_text(
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>MagGoogo Sources</title></head><body>"
            "<p>MagGoogo source distribution endpoint.</p>"
            "</body></html>",
            encoding="utf-8",
        )

    # Verify roundtrip
    print("\nVerifying roundtrip ...")
    if not verify_roundtrip(payload):
        sys.exit(1)

    if "--deploy" in sys.argv:
        deploy_to_github()


def deploy_to_github():
    """Git add, commit, push the dist folder."""
    import subprocess

    os.chdir(DIST_DIR)

    # Initialize git if needed
    if not (DIST_DIR / ".git").exists():
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "branch", "-M", "main"], check=True)
        print("\n⚠  Git repo initialized. You need to add a remote:")
        print(f"  cd {DIST_DIR}")
        print("  git remote add origin https://github.com/<YOUR_USER>/maggoogo-sources.git")
        print("  Then re-run: python encrypt_sources.py --deploy")
        return

    subprocess.run(["git", "add", "-A"], check=True)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], capture_output=True
    )
    if result.returncode == 0:
        print("No changes to deploy.")
        return

    subprocess.run(
        ["git", "commit", "-m", f"Update encrypted sources"],
        check=True,
    )
    subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
    print("✓ Deployed to GitHub")


if __name__ == "__main__":
    main()
