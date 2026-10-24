#!/usr/bin/env python3
"""Read-only compute/finalizer watchdog. Python 3.6+, no external packages."""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROFILES = {
    "compute": ("magnet-media-oracle-compute", "/var/lib/magnet-media/status/latest-compute.json", 4.25, "影视计算"),
    "finalizer": ("magnet-media-compute-finalizer", "/var/lib/magnet-media/status/latest-compute-finalizer-publish.json", 2.25, "影视发布"),
}
PROPERTIES = ("LoadState", "ActiveState", "SubState", "Result", "ExecMainStatus", "ExecMainStartTimestampMonotonic")


def observation(key, state, title, message, severity="P1"):
    return {"key": key, "state": state, "title": title, "message": message, "severity": severity}


def parse_finished(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+0000"
    elif re.search(r"[+-]\d\d:\d\d$", normalized):
        normalized = normalized[:-3] + normalized[-2:]
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(normalized, fmt).timestamp()
        except ValueError:
            pass
    return None


def safe_code(document):
    error = document.get("error")
    if isinstance(error, dict):
        for field in ("error_code", "code"):
            value = error.get(field)
            if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", value):
                return value
    return "UNCLASSIFIED"


def identifier_list(values):
    return ",".join(x for x in values[:10] if isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,40}", x))


def source_checks(document, evidence_ok):
    prefix = "media-source"
    if not evidence_ok:
        return [observation(prefix + "-observation", "failure", "影视源健康证据缺失", "没有本周期有效的来源健康证据；保留此前来源告警，未判定恢复。")]
    required = document.get("required_degraded_sources")
    failed = document.get("failed_freshness_groups")
    groups = document.get("freshness_groups")
    valid = isinstance(required, list) and isinstance(failed, list) and isinstance(groups, dict) and bool(groups)
    parsed = []
    if valid:
        valid = all(isinstance(x, str) for x in required + failed)
        for name, group in groups.items():
            if not isinstance(group, dict):
                valid = False
                break
            values = [group.get(x) for x in ("fresh_count", "member_count", "min_fresh")]
            if any(isinstance(x, bool) or not isinstance(x, int) for x in values):
                valid = False
                break
            fresh, members, minimum = values
            if not (0 <= fresh <= members and 1 <= minimum <= members) or group.get("status") not in ("pass", "failed", "fail"):
                valid = False
                break
            parsed.append((fresh, members, minimum, group.get("status")))
    if not valid:
        return [observation(prefix + "-observation", "failure", "影视源健康状态未知", "来源健康字段缺失或不完整；保留此前告警，未判定恢复。")]
    checks = [observation(prefix + "-observation", "success", "影视源健康证据恢复", "已取得本周期完整来源健康证据。")]
    blocked = bool(required or failed or any(f < minimum or status != "pass" for f, m, minimum, status in parsed))
    redundancy = any(f < m for f, m, minimum, status in parsed)
    checks.append(observation(prefix + "-freshness", "failure" if blocked else "success",
                              "影视源新鲜度不足" if blocked else "影视源新鲜度恢复",
                              "必需源异常=%s；不满足来源组=%s。" % (identifier_list(required) or "无", identifier_list(failed) or ("存在" if blocked else "无"))))
    checks.append(observation(prefix + "-redundancy", "failure" if redundancy else "success",
                              "影视来源冗余不足" if redundancy else "影视来源冗余恢复",
                              "来源组新鲜数量=%s；未修改来源评级。" % ",".join("%s/%s" % (f, m) for f, m, minimum, status in parsed), "P2"))
    return checks


def evaluate(role, document, mtime, unit, timer, now, monotonic_now, max_age_hours=30.0):
    base, _, max_runtime, label = PROFILES[role]
    key = "media-compute" if role == "compute" else "media-publish"
    scheduled = timer.get("LoadState") == "loaded" and timer.get("ActiveState") == "active"
    checks = [observation(key + "-schedule", "success" if scheduled else "failure",
                          label + ("调度恢复" if scheduled else "调度异常"),
                          "定时器正常。" if scheduled else "定时器未加载或未启用；可能不会按时执行。")]
    running = unit.get("ActiveState") in ("active", "activating") and unit.get("SubState") != "exited"
    try:
        started = float(unit.get("ExecMainStartTimestampMonotonic") or 0) / 1000000
    except (TypeError, ValueError):
        started = 0
    elapsed = monotonic_now - started
    if unit.get("LoadState") != "loaded":
        state, reason = "failure", "业务服务未加载或无法读取状态。"
    elif running:
        if started <= 0 or elapsed < -5:
            state, reason = "failure", "业务正在执行，但无法确认启动时间；未判定健康。"
        elif elapsed > max_runtime * 3600:
            state, reason = "failure", "业务执行超过 %.2f 小时。" % max_runtime
        else:
            return checks + [observation(key, "pending", label + "运行中", "等待当前任务结束；不发送恢复通知。")]
    elif unit.get("ActiveState") == "failed" or unit.get("Result") not in ("success", "") or str(unit.get("ExecMainStatus", "0")) != "0":
        state, reason = "failure", "业务进程报告失败。错误代码=%s。" % safe_code(document)
    else:
        state, reason = "success", "任务已完成。"
    finished = parse_finished(document.get("finished_at"))
    correct_mode = document.get("mode") == ("compute" if role == "compute" else "publish")
    current_run = started <= 0 or (finished is not None and finished >= now - elapsed - 5)
    evidence_ok = (finished is not None and mtime is not None and correct_mode and current_run
                   and unit.get("LoadState") == "loaded" and not running
                   and document.get("status") in ("success", "failed")
                   and -300 <= now - finished <= max_age_hours * 3600
                   and -300 <= now - mtime <= max_age_hours * 3600)
    if state == "success":
        if not evidence_ok:
            state, reason = "failure", "没有 %.0f 小时内有效的任务完成记录（缺失、过期或格式异常）；未判定恢复。" % max_age_hours
        elif document.get("status") == "failed":
            state, reason = "failure", "最近任务失败。错误代码=%s。" % safe_code(document)
        else:
            reason = "最近任务已成功完成，完成记录在有效期内。"
    checks.append(observation(key, state, label + ("恢复" if state == "success" else "异常"), reason,
                              "P0" if role == "finalizer" else "P1"))
    if role == "compute":
        checks.extend(source_checks(document, evidence_ok))
    return checks


def manifest_capacity_checks(public_root, publisher_source):
    """Observe published size against the installed local publisher cap only."""
    unknown = observation("media-publish-capacity-observation", "failure",
                          "影视发布容量检查异常",
                          "无法可靠读取发布端容量或当前公开清单；保留此前容量告警，未判定恢复。", "P2")
    try:
        source = Path(publisher_source)
        if not source.is_file() or source.stat().st_size > 128 * 1024:
            return [unknown]
        module = ast.parse(source.read_text(encoding="utf-8"))
        assignments = []
        for node in module.body:
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
            if any(isinstance(target, ast.Name) and target.id == "_MAX_MANIFEST_BYTES" for target in targets):
                assignments.append(node)
        if (len(assignments) != 1 or not isinstance(assignments[0], ast.Assign)
                or len(assignments[0].targets) != 1):
            return [unknown]

        def integer_product(node, depth=0):
            if depth > 12:
                raise ValueError("unsupported capacity expression")
            if isinstance(node, ast.Num) and type(node.n) is int:
                value = node.n
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
                value = integer_product(node.left, depth + 1) * integer_product(node.right, depth + 1)
            else:
                raise ValueError("unsupported capacity expression")
            if not 0 < value <= 64 * 1024 * 1024:
                raise ValueError("invalid capacity")
            return value

        limit = integer_product(assignments[0].value)
        root = Path(public_root).resolve()
        pointer_path = (root / "v1" / "current.json").resolve()
        pointer_path.relative_to(root)
        if not pointer_path.is_file() or pointer_path.stat().st_size > 64 * 1024:
            return [unknown]
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        manifest_key = pointer.get("manifest_path") if isinstance(pointer, dict) else None
        revision = pointer.get("pointer_revision") if isinstance(pointer, dict) else None
        if (not isinstance(manifest_key, str)
                or not re.fullmatch(r"/v1/releases/[A-Za-z0-9][A-Za-z0-9._-]{0,127}/manifest\.json", manifest_key)
                or type(revision) is not int or revision < 1):
            return [unknown]
        manifest_path = (root / manifest_key.lstrip("/")).resolve()
        manifest_path.relative_to(root)
        if not manifest_path.is_file():
            return [unknown]
        size = manifest_path.stat().st_size
        if size <= 0:
            return [unknown]
    except (OSError, ValueError, SyntaxError, TypeError, RecursionError):
        return [unknown]
    near_limit = size * 100 >= limit * 80
    message = "公开版本%d，清单%d字节；本机发布客户端上限%d字节，占用%.2f%%。" % (
        revision, size, limit, 100.0 * size / limit)
    if near_limit:
        message += "已达到80%预警线，请在后续增长阻断发布前处理容量；未修改发布门禁。"
    return [
        observation("media-publish-capacity-observation", "success", "影视发布容量检查恢复",
                    "已可靠读取当前公开清单和本机发布客户端上限。", "P2"),
        observation("media-publish-capacity", "failure" if near_limit else "success",
                    "影视发布清单容量预警" if near_limit else "影视发布清单容量恢复",
                    message, "P2"),
    ]


def query_unit(name):
    try:
        result = subprocess.run(["systemctl", "show", name, "--no-page", "--property=" + ",".join(PROPERTIES)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def read_status(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {}, None
        return value, path.stat().st_mtime
    except (OSError, ValueError):
        return {}, None


def dispatch(checks, alert_bin, state_root, dry_run=False):
    if dry_run:
        print(json.dumps({"dry_run": True, "checks": checks}, ensure_ascii=False, sort_keys=True))
        return 0
    failed = False
    for item in checks:
        if item["state"] == "pending":
            continue
        args = [sys.executable, str(alert_bin), item["state"], "--key", item["key"],
                "--state-file", str(state_root / (item["key"] + ".json")),
                "--severity", item["severity"], "--title", item["title"], "--message", item["message"],
                "--threshold", "1", "--repeat-hours", "6", "--strict"]
        try:
            result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=30)
            failed = failed or result.returncode != 0
            print("MEDIA_HEALTH key=%s state=%s notifier_exit=%s" % (item["key"], item["state"], result.returncode))
        except (OSError, subprocess.TimeoutExpired) as exc:
            failed = True
            print("MEDIA_HEALTH key=%s notifier_error=%s" % (item["key"], type(exc).__name__))
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=tuple(PROFILES), default=os.environ.get("MAGNET_MEDIA_HEALTH_ROLE"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.role not in PROFILES:
        print("MEDIA_HEALTH disabled_or_invalid_role")
        return 2
    unit_name, default_status, _, _ = PROFILES[args.role]
    status_file = Path(os.environ.get("MAGNET_MEDIA_HEALTH_STATUS_FILE") or default_status)
    document, mtime = read_status(status_file)
    try:
        max_age = float(os.environ.get("MAGNET_MEDIA_HEALTH_MAX_AGE_HOURS", "30"))
    except ValueError:
        return 2
    if not 24 <= max_age <= 72:
        return 2
    checks = evaluate(args.role, document, mtime, query_unit(unit_name + ".service"),
                      query_unit(unit_name + ".timer"), time.time(), time.monotonic(), max_age)
    if args.role == "finalizer":
        checks.extend(manifest_capacity_checks(
            os.environ.get("MAGNET_MEDIA_HEALTH_PUBLIC_ROOT", "/var/lib/magnet-media/public"),
            os.environ.get("MAGNET_MEDIA_HEALTH_PUBLISHER_SOURCE", "/opt/magnet-media-finalizer/app/magnet/resource_index/publish/worker_bridge.py")))
    return dispatch(checks, Path(os.environ.get("MAGNET_ALERT_BIN", "/opt/magnet-alerts/magnet-alert.py")),
                    Path(os.environ.get("MAGNET_MEDIA_HEALTH_STATE_DIR", "/var/lib/magnet-alerts")), args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
