#!/usr/bin/env python3
"""
MagGoogo Admin Dashboard — local operations panel.

Usage:
  python admin.py              # Start on http://localhost:5000
  python admin.py --port 8080  # Custom port

No server needed. Manages config.json + sources via GitHub API.
"""

import json
import os
import sys
import subprocess
import webbrowser
import hashlib
import hmac as hmac_mod
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
from functools import wraps

import requests as http_requests
from flask import Flask, render_template, request, jsonify, send_from_directory

# ── Paths ──
BASE_DIR = Path(__file__).parent
SOURCES_JSON = BASE_DIR / "sources.json"
DIST_DIR = BASE_DIR / "maggoogo-sources"
CONFIG_FILE = DIST_DIR / "config.json"
ENC_FILE = DIST_DIR / "sources.enc.json"
APP_DIR = BASE_DIR / "magnetgoogo-app"
APK_PATH = APP_DIR / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
SETTINGS_FILE = BASE_DIR / ".admin_settings.json"

GITHUB_REPO = "734496335/maggoogo-sources"
JSDELIVR_BASE = f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@main"
GATEWAY_BASE = "https://maggoogo-gateway.734496335lp.workers.dev"
ADMIN_SECRET = "maggoogo-admin-2026"

app = Flask(__name__, template_folder=str(BASE_DIR / "admin_templates"))


# ── Settings persistence ──
def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text("utf-8"))
    return {}


def save_settings(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Helpers ──
def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    return {
        "latest_version": "1.0.0",
        "min_version": "1.0.0",
        "download": {"primary": "", "mirrors": []},
        "announcement": "",
        "source_expiry_hours": 72,
        "source_schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_config(cfg: dict):
    cfg["updated_at"] = datetime.now(timezone.utc).isoformat()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_source_stats() -> dict:
    """Parse sources.json and return stats."""
    if not SOURCES_JSON.exists():
        return {"total": 0, "green": 0, "yellow": 0, "gray": 0, "exists": False}

    raw = json.loads(SOURCES_JSON.read_bytes())
    rules = raw
    if isinstance(raw, dict):
        if raw.get("rulesets") and isinstance(raw["rulesets"], list):
            if raw["rulesets"] and isinstance(raw["rulesets"][0], dict) and "rules" in raw["rulesets"][0]:
                rules = raw["rulesets"][0]["rules"]
            else:
                rules = raw["rulesets"]
        elif raw.get("sources"):
            rules = raw["sources"]

    if not isinstance(rules, list):
        rules = []

    stats = {"total": len(rules), "green": 0, "yellow": 0, "gray": 0, "exists": True}
    for r in rules:
        status = r.get("health", {}).get("status", "gray") if isinstance(r, dict) else "gray"
        if status in stats:
            stats[status] += 1
    return stats


def get_enc_info() -> dict:
    """Get info about the encrypted sources file."""
    if not ENC_FILE.exists():
        return {"exists": False}

    stat = ENC_FILE.stat()
    return {
        "exists": True,
        "size_kb": round(stat.st_size / 1024, 1),
        "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def git_push_dist(message: str) -> dict:
    """Git add, commit, push the dist folder."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(DIST_DIR), check=True, capture_output=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(DIST_DIR), capture_output=True,
        )
        if result.returncode == 0:
            return {"ok": True, "message": "No changes to push"}

        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(DIST_DIR), check=True, capture_output=True,
        )
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=str(DIST_DIR), check=True, capture_output=True, text=True,
        )
        return {"ok": True, "message": f"Pushed: {message}"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "message": f"Git error: {e.stderr or str(e)}"}


def run_encrypt() -> dict:
    """Run encrypt_sources.py and return result."""
    try:
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "encrypt_sources.py")],
            cwd=str(BASE_DIR),
            capture_output=True, text=True, timeout=30,
        )
        return {
            "ok": result.returncode == 0,
            "output": result.stdout + result.stderr,
        }
    except Exception as e:
        return {"ok": False, "output": str(e)}


# ── Routes ──
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/overview")
def api_overview():
    config = load_config()
    stats = get_source_stats()
    enc = get_enc_info()
    apk_info = {
        "exists": APK_PATH.exists(),
        "size_mb": round(APK_PATH.stat().st_size / (1024 * 1024), 1) if APK_PATH.exists() else 0,
        "modified": datetime.fromtimestamp(APK_PATH.stat().st_mtime, timezone.utc).isoformat() if APK_PATH.exists() else None,
    }
    return jsonify({
        "config": config,
        "sources": stats,
        "encrypted": enc,
        "apk": apk_info,
        "github_repo": GITHUB_REPO,
        "jsdelivr_base": JSDELIVR_BASE,
    })


@app.route("/api/config", methods=["POST"])
def api_config_save():
    data = request.json
    cfg = load_config()
    cfg.update({
        "latest_version": data.get("latest_version", cfg["latest_version"]),
        "min_version": data.get("min_version", cfg["min_version"]),
        "announcement": data.get("announcement", cfg.get("announcement", "")),
        "source_expiry_hours": int(data.get("source_expiry_hours", cfg.get("source_expiry_hours", 72))),
        "source_schema_version": int(data.get("source_schema_version", cfg.get("source_schema_version", 1))),
    })
    if "download" in data:
        cfg["download"] = data["download"]
    save_config(cfg)
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/encrypt", methods=["POST"])
def api_encrypt():
    result = run_encrypt()
    if result["ok"]:
        enc = get_enc_info()
        result["encrypted"] = enc
    return jsonify(result)


@app.route("/api/publish", methods=["POST"])
def api_publish():
    """Encrypt sources + push config + enc to GitHub."""
    # Step 1: encrypt
    enc_result = run_encrypt()
    if not enc_result["ok"]:
        return jsonify({"ok": False, "message": f"Encrypt failed: {enc_result['output']}"})

    # Step 2: push
    push_result = git_push_dist("Update sources + config")
    push_result["encrypt_output"] = enc_result["output"]
    return jsonify(push_result)


@app.route("/api/push-config", methods=["POST"])
def api_push_config():
    """Push only config.json to GitHub."""
    result = git_push_dist("Update config")
    return jsonify(result)


@app.route("/api/sources/details")
def api_source_details():
    """Return detailed source list."""
    if not SOURCES_JSON.exists():
        return jsonify({"rules": []})

    raw = json.loads(SOURCES_JSON.read_bytes())
    rules = raw
    if isinstance(raw, dict):
        if raw.get("rulesets") and isinstance(raw["rulesets"], list):
            if raw["rulesets"] and isinstance(raw["rulesets"][0], dict) and "rules" in raw["rulesets"][0]:
                rules = raw["rulesets"][0]["rules"]
            else:
                rules = raw["rulesets"]

    # Extract key info only
    summary = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        summary.append({
            "id": r.get("id", "?"),
            "site_name": r.get("site_name", "?"),
            "brand": r.get("brand", ""),
            "base_url": r.get("base_url", ""),
            "status": r.get("health", {}).get("status", "gray"),
            "status_detail": r.get("health", {}).get("status_detail", ""),
        })

    return jsonify({"rules": summary})


@app.route("/api/feedback")
def api_feedback_list():
    """Proxy feedback list from CF Worker KV."""
    try:
        resp = http_requests.get(
            f"{GATEWAY_BASE}/api/feedback",
            params={"secret": ADMIN_SECRET},
            timeout=10,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e), "items": [], "count": 0})


@app.route("/api/feedback/<fb_id>", methods=["DELETE"])
def api_feedback_delete(fb_id):
    """Delete a feedback entry from CF Worker KV."""
    try:
        resp = http_requests.delete(
            f"{GATEWAY_BASE}/api/feedback/{fb_id}",
            headers={"X-Admin-Secret": ADMIN_SECRET},
            timeout=10,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ── Main ──
def main():
    port = 5000
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        port = int(sys.argv[idx + 1])

    print(f"\n{'='*50}")
    print(f"  MagGoogo Admin Dashboard")
    print(f"  http://localhost:{port}")
    print(f"{'='*50}\n")

    # Auto-open browser
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
