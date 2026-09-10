from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import tarfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from magnet.resource_index.errors import PUBLISH_CONFIG_ERROR, PUBLISH_REMOTE_ERROR, ResourceIndexError
from magnet.resource_index.publish.orchestrator import MediaPublishConfig, MediaPublishResult, build_media_publish_plan
from magnet.resource_index.release.protocol import canonical_json_bytes, sha256_file

_TARGET_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class SshStaticMirrorConfig:
    target: str
    remote_root: str
    identity_file: Path
    known_hosts_file: Path
    staging_root: Path
    remote_helper_path: str = "/usr/local/libexec/magnet-media-remote-static-mirror.py"
    port: int = 22
    connect_timeout_seconds: int = 15
    command_timeout_seconds: int = 900


class SshStaticMirrorPublisher:
    def __init__(self, config: SshStaticMirrorConfig) -> None:
        self.config = config
        if not _TARGET_RE.fullmatch(config.target):
            raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "Aliyun SSH target is invalid", {"target": config.target})
        remote_root_parts = config.remote_root.split("/")
        if (
            len(remote_root_parts) < 3
            or remote_root_parts[0] != ""
            or any(not part or part in {".", ".."} for part in remote_root_parts[1:])
            or any(char.isspace() or ord(char) < 32 for char in config.remote_root)
        ):
            raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "Aliyun remote mirror root is invalid", {"root": config.remote_root})
        if not 1 <= config.port <= 65535:
            raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "Aliyun SSH port is invalid", {"port": config.port})
        if (
            not config.remote_helper_path.startswith("/")
            or "\n" in config.remote_helper_path
            or "\r" in config.remote_helper_path
            or " " in config.remote_helper_path
        ):
            raise ResourceIndexError(
                PUBLISH_CONFIG_ERROR,
                "Aliyun remote helper path is invalid",
                {"path": config.remote_helper_path},
            )
        for name, path in (
            ("identity_file", config.identity_file),
            ("known_hosts_file", config.known_hosts_file),
        ):
            if not path.is_file():
                raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "Aliyun SSH publisher file is missing", {"name": name, "path": str(path)})
        config.staging_root.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "ssh-filesystem-mirror"

    @property
    def destination(self) -> str:
        return f"{self.config.target}:{self.config.remote_root}"

    def _ssh_options(self) -> list[str]:
        return [
            "-p",
            str(self.config.port),
            "-i",
            str(self.config.identity_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.config.known_hosts_file}",
            "-o",
            f"ConnectTimeout={self.config.connect_timeout_seconds}",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
        ]

    def _scp_options(self) -> list[str]:
        options = self._ssh_options()
        options[0] = "-P"
        return options

    def _run(self, args: list[str], *, label: str, timeout: int | None = None) -> str:
        try:
            result = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.config.command_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ResourceIndexError(PUBLISH_REMOTE_ERROR, f"{label} failed", {"error": type(exc).__name__}) from exc
        if result.returncode != 0:
            raise ResourceIndexError(
                PUBLISH_REMOTE_ERROR,
                f"{label} failed",
                {
                    "returncode": result.returncode,
                    "stderr": result.stderr[-2000:],
                },
            )
        return result.stdout

    def _ssh(self, command: str, *, label: str) -> str:
        return self._run(["ssh", *self._ssh_options(), self.config.target, command], label=label)

    def _scp(self, sources: list[Path], destination: str, *, label: str) -> None:
        self._run(
            ["scp", *self._scp_options(), *(str(path) for path in sources), f"{self.config.target}:{destination}"],
            label=label,
        )

    @staticmethod
    def _parse_json(output: str, *, label: str) -> dict[str, Any]:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            raise ResourceIndexError(PUBLISH_REMOTE_ERROR, f"{label} returned no JSON", {})
        try:
            value = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise ResourceIndexError(PUBLISH_REMOTE_ERROR, f"{label} returned invalid JSON", {"output": lines[-1][-1000:]}) from exc
        if not isinstance(value, dict) or value.get("status") != "pass":
            raise ResourceIndexError(PUBLISH_REMOTE_ERROR, f"{label} did not pass", {"result": value})
        return value

    @staticmethod
    def _plan_payload(plan: Any, requests: list[Any]) -> dict[str, Any]:
        return {
            "schema_version": "media-publish-plan/1",
            "release_id": plan.release_id,
            "pointer_revision": plan.pointer_revision,
            "manifest_sha256": plan.manifest_sha256,
            "total_file_count": len(requests),
            "total_bytes": sum(request.size for request in requests),
            "files": [
                {
                    "key": request.key,
                    "sha256": request.sha256,
                    "size": request.size,
                    "object_kind": request.object_kind,
                }
                for request in requests
            ],
        }

    def _remote_command(self, remote_helper: str, command: str, *args: str) -> str:
        parts = ["sudo", "-n", "/usr/bin/python3.11", remote_helper, command, *args]
        return " ".join(shlex.quote(part) for part in parts)

    def healthcheck(self) -> dict[str, Any]:
        output = self._ssh(
            self._remote_command(
                self.config.remote_helper_path,
                "healthcheck",
                "--root",
                self.config.remote_root,
            ),
            label="Aliyun SSH mirror healthcheck",
        )
        return self._parse_json(output, label="Aliyun SSH mirror healthcheck")

    def publish_release(self, publish_config: MediaPublishConfig) -> MediaPublishResult:
        if publish_config.upload_pointer_candidate:
            raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "Aliyun production mirror must not upload pointer candidates", {})
        plan = build_media_publish_plan(publish_config)
        requests = list(plan.requests)
        run_id = uuid.uuid4().hex
        local_stage = self.config.staging_root / f"ssh-mirror-{run_id}"
        remote_stage = f"/tmp/magnet-media-mirror-{run_id}"
        local_stage.mkdir(parents=True, exist_ok=False)
        full_plan_path = local_stage / "publish-plan.json"
        delta_plan_path = local_stage / "delta-plan.json"
        archive_path = local_stage / "payload.tar"
        receipt_path = publish_config.receipt_dir.resolve() / f"ssh-filesystem-mirror-{run_id}.json"
        remote_helper = self.config.remote_helper_path
        try:
            full_plan_path.write_bytes(canonical_json_bytes(self._plan_payload(plan, requests)))
            self._ssh(
                f"rm -rf {shlex.quote(remote_stage)} && mkdir -m 700 {shlex.quote(remote_stage)}",
                label="Aliyun SSH mirror staging create",
            )
            self._scp([full_plan_path], remote_stage + "/", label="Aliyun SSH mirror plan upload")
            diff_output = self._ssh(
                self._remote_command(
                    remote_helper,
                    "diff",
                    "--root",
                    self.config.remote_root,
                    "--plan",
                    f"{remote_stage}/publish-plan.json",
                ),
                label="Aliyun SSH mirror diff",
            )
            diff = self._parse_json(diff_output, label="Aliyun SSH mirror diff")
            missing_keys = diff.get("missing")
            if not isinstance(missing_keys, list) or any(not isinstance(item, str) for item in missing_keys):
                raise ResourceIndexError(PUBLISH_REMOTE_ERROR, "Aliyun SSH mirror diff returned invalid missing list", {})
            by_key = {request.key: request for request in requests}
            try:
                missing_requests = [by_key[key] for key in missing_keys]
            except KeyError as exc:
                raise ResourceIndexError(PUBLISH_REMOTE_ERROR, "Aliyun SSH mirror diff returned an unknown key", {"key": str(exc)}) from exc
            if missing_requests:
                delta_plan_path.write_bytes(canonical_json_bytes(self._plan_payload(plan, missing_requests)))
                with tarfile.open(archive_path, "w") as archive:
                    for request in missing_requests:
                        archive.add(request.source_path, arcname=f"payload/{request.key}", recursive=False)
                self._scp([delta_plan_path, archive_path], remote_stage + "/", label="Aliyun SSH mirror delta upload")
                apply_command = self._remote_command(
                    remote_helper,
                    "promote-archive",
                    "--root",
                    self.config.remote_root,
                    "--plan",
                    f"{remote_stage}/delta-plan.json",
                    "--archive",
                    f"{remote_stage}/payload.tar",
                )
                promote_output = self._ssh(apply_command, label="Aliyun SSH mirror delta promotion")
                self._parse_json(promote_output, label="Aliyun SSH mirror delta promotion")
            verify_output = self._ssh(
                self._remote_command(
                    remote_helper,
                    "verify",
                    "--root",
                    self.config.remote_root,
                    "--plan",
                    f"{remote_stage}/publish-plan.json",
                ),
                label="Aliyun SSH mirror full verification",
            )
            verified = self._parse_json(verify_output, label="Aliyun SSH mirror full verification")
            receipt = {
                "schema_version": "media-publish-receipt/1",
                "status": "success",
                "backend": self.name,
                "destination": self.destination,
                "release_id": plan.release_id,
                "pointer_revision": plan.pointer_revision,
                "object_count": plan.object_count,
                "uploaded_count": len(missing_requests),
                "reused_count": len(requests) - len(missing_requests),
                "manifest_uploaded": True,
                "pointer_uploaded": False,
                "current_promoted": False,
                "verified": verified,
            }
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(canonical_json_bytes(receipt))
            return MediaPublishResult(
                status="success",
                backend=self.name,
                destination=self.destination,
                release_id=plan.release_id,
                pointer_revision=plan.pointer_revision,
                object_count=plan.object_count,
                uploaded_count=len(missing_requests),
                reused_count=len(requests) - len(missing_requests),
                manifest_uploaded=True,
                pointer_uploaded=False,
                current_promoted=False,
                receipt_path=str(receipt_path),
            )
        finally:
            try:
                self._ssh(f"rm -rf {shlex.quote(remote_stage)}", label="Aliyun SSH mirror staging cleanup")
            except ResourceIndexError:
                pass
            shutil.rmtree(local_stage, ignore_errors=True)

    def _current_operation(self, current_path: str | Path, *, expected_existing_sha256: str, promote: bool) -> dict[str, Any]:
        source = Path(current_path).resolve()
        if not source.is_file():
            raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "current pointer candidate is missing", {"path": str(source)})
        if len(expected_existing_sha256) != 64:
            raise ResourceIndexError(PUBLISH_CONFIG_ERROR, "expected existing current SHA-256 is invalid", {})
        run_id = uuid.uuid4().hex
        remote_stage = f"/tmp/magnet-media-current-{run_id}"
        remote_helper = self.config.remote_helper_path
        remote_candidate = f"{remote_stage}/candidate.json"
        try:
            self._ssh(
                f"rm -rf {shlex.quote(remote_stage)} && mkdir -m 700 {shlex.quote(remote_stage)}",
                label="Aliyun current staging create",
            )
            self._scp([source], remote_stage + "/", label="Aliyun current candidate upload")
            uploaded_name = source.name
            if uploaded_name != "candidate.json":
                self._ssh(
                    f"mv {shlex.quote(remote_stage + '/' + uploaded_name)} {shlex.quote(remote_candidate)}",
                    label="Aliyun current candidate normalize",
                )
            command = "promote-current" if promote else "preflight-current"
            output = self._ssh(
                self._remote_command(
                    remote_helper,
                    command,
                    "--root",
                    self.config.remote_root,
                    "--candidate",
                    remote_candidate,
                    "--expected-existing-sha256",
                    expected_existing_sha256,
                ),
                label=f"Aliyun current {command}",
            )
            result = self._parse_json(output, label=f"Aliyun current {command}")
            candidate_sha = sha256_file(source)
            if result.get("candidate_sha256") != candidate_sha:
                raise ResourceIndexError(PUBLISH_REMOTE_ERROR, "Aliyun current candidate SHA mismatch", {})
            return result
        finally:
            try:
                self._ssh(f"rm -rf {shlex.quote(remote_stage)}", label="Aliyun current staging cleanup")
            except ResourceIndexError:
                pass

    def preflight_current(self, current_path: str | Path, *, expected_existing_sha256: str) -> dict[str, Any]:
        return self._current_operation(current_path, expected_existing_sha256=expected_existing_sha256, promote=False)

    def promote_current(self, current_path: str | Path, *, expected_existing_sha256: str) -> dict[str, Any]:
        return self._current_operation(current_path, expected_existing_sha256=expected_existing_sha256, promote=True)
