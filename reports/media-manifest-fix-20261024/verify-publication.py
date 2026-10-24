"""Read-only audit of a completed cross-server media publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from magnet.resource_index.pipeline.media_daily import load_media_daily_config
from magnet.resource_index.release.builder import verify_media_release


def fetch(url: str, expected_size: int) -> bytes:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={
        "user-agent": "MagnetGoogo-Media-Publisher/0.2.1",
        "accept-encoding": "identity",
        "cache-control": "no-cache",
    })
    with opener.open(request, timeout=45) as response:
        body = response.read(expected_size + 1)
    if len(body) != expected_size:
        raise RuntimeError("Public object size mismatch: " + url)
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--expected-run", required=True)
    parser.add_argument("--minimum-revision", type=int, required=True)
    args = parser.parse_args()
    cfg = load_media_daily_config(args.config)
    status_path = cfg.state_root / "status/latest-compute-finalizer-publish.json"
    status = json.loads(status_path.read_text())
    result = status["result"]
    assert status["status"] == "success" and status["mode"] == "publish"
    assert result["published"] is True and result["compute_run_id"] == args.expected_run
    assert result["current_revision"] >= args.minimum_revision

    release_dir = Path(result["release"]["release_dir"])
    current_path = Path(result["release"]["current_path"])
    local_report = verify_media_release(release_dir, cfg.public_key_path, current_path)
    current_bytes = current_path.read_bytes()
    current = json.loads(current_bytes)
    manifest_path = release_dir / current["manifest_path"].lstrip("/")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    refs = {ref["path"]: ref for ref in manifest["objects"]}

    # Exercise all catalogue pages and representative detail/resource/cover
    # objects, including newly uploaded objects. Full local closure is checked
    # above; remote publisher receipts cover every immutable object.
    selected: dict[str, dict] = {}
    for kind in ("catalog", "detail", "resources", "covers"):
        prefix = "/v1/covers/" if kind == "covers" else "/v1/objects/" + kind + "/"
        group = sorted((ref for ref in refs.values() if ref["path"].startswith(prefix)), key=lambda row: row["path"])
        chosen = group if kind == "catalog" else group[:4] + group[-4:]
        selected.update({ref["path"]: ref for ref in chosen})

    receipt_summary = {}
    for name in ("aliyun", "r2"):
        published = result["publish"][name]
        receipt = json.loads(Path(published["receipt_path"]).read_text())
        assert receipt["status"] == "success" and receipt["release_id"] == result["release_id"]
        assert len(receipt["objects"]) == len(refs) + 1
        receipt_summary[name] = {
            key: published[key] for key in ("object_count", "uploaded_count", "reused_count", "manifest_uploaded", "receipt_path")
        }
        if name == "r2":
            newly_uploaded = [row for row in receipt["objects"] if row["uploaded"] and "/" + row["key"] in refs]
            for kind in ("catalog", "detail", "resources", "cover"):
                for row in [row for row in newly_uploaded if row["object_kind"] == kind][:8]:
                    selected["/" + row["key"]] = refs["/" + row["key"]]

    checks = []
    controls = []
    for base in (cfg.r2_public_base, cfg.aliyun_public_base):
        remote_current = fetch(base + "/v1/current.json", len(current_bytes))
        assert remote_current == current_bytes
        remote_manifest = fetch(base + current["manifest_path"], len(manifest_bytes))
        assert remote_manifest == manifest_bytes
        controls.append({
            "base": base,
            "pointer_revision": current["pointer_revision"],
            "pointer_sha256": hashlib.sha256(remote_current).hexdigest(),
            "manifest_size": len(remote_manifest),
            "manifest_sha256": hashlib.sha256(remote_manifest).hexdigest(),
        })
        checks.extend((base, ref) for ref in selected.values())

    def check(item: tuple[str, dict]) -> dict:
        base, ref = item
        body = fetch(base + ref["path"], ref["size"])
        digest = hashlib.sha256(body).hexdigest()
        if digest != ref["hash"]:
            raise RuntimeError("Public object hash mismatch: " + base + ref["path"])
        return {"base": base, "path": ref["path"], "size": len(body), "sha256": digest, "status": "pass"}

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as executor:
        public_objects = list(executor.map(check, checks))
    print(json.dumps({
        "schema_version": "media-publication-audit/1",
        "status": "pass",
        "compute_run_id": args.expected_run,
        "revision": current["pointer_revision"],
        "release_id": current["release_id"],
        "finalizer_started_at": status["started_at"],
        "finalizer_finished_at": status["finished_at"],
        "local_full_release": local_report,
        "receipts": receipt_summary,
        "public_controls": controls,
        "public_sample_distinct_objects": len(selected),
        "public_object_reads": len(public_objects),
        "public_object_read_seconds": round(time.monotonic() - start, 2),
        "public_objects": public_objects,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
