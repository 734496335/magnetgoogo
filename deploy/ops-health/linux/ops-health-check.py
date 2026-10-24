#!/usr/bin/env python3
"""Read-only host/app probes; notifications use the shared durable alert queue."""
import argparse
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def command(args, timeout=12, env=None):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=timeout, env=env)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def unit_state(name):
    properties = "LoadState,ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestampMonotonic,ExecMainExitTimestampMonotonic"
    code, output = command(["systemctl", "show", name, "--no-pager", "--property=" + properties])
    if code:
        return {}
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def finding(key, label, healthy, detail, threshold=2):
    return {"key": "ops-" + key, "label": label, "healthy": healthy,
            "detail": detail, "threshold": threshold}


def job_finding(item, state, uptime):
    unit = item["unit"]
    label = item.get("label", unit)
    key = "job-" + unit
    if state.get("LoadState") != "loaded":
        return finding(key, label, False, "Task unit unavailable")
    active = state.get("ActiveState")
    try:
        start = float(state.get("ExecMainStartTimestampMonotonic") or 0) / 1000000
        end = float(state.get("ExecMainExitTimestampMonotonic") or 0) / 1000000
        exit_code = int(state.get("ExecMainStatus") or 0)
    except (ValueError, TypeError):
        return finding(key, label, False, "Task state is not readable")
    if active in ("active", "activating"):
        if not start or start > uptime:
            return finding(key, label, False, "Running task start time is unknown")
        running = max(0, uptime - start)
        limit = int(item.get("max_run_seconds", 7200))
        return finding(key, label, None if running <= limit else False,
                       "Running for %ss; limit %ss; completion still pending" % (int(running), limit))
    if active == "failed" or state.get("Result") not in ("success", "") or exit_code:
        return finding(key, label, False,
                       "Task failed: result=%s exit=%s" % (state.get("Result", "unknown"), exit_code))
    max_age = int(item.get("max_age_seconds", 129600))
    if not end:
        if uptime < max_age:
            return finding(key, label, None, "No completed run since boot; awaiting its schedule")
        return finding(key, label, False, "No completed run since boot")
    if end > uptime:
        return finding(key, label, False, "Task completion time is invalid")
    age = max(0, uptime - end)
    return finding(key, label, age <= max_age,
                   "Last successful completion %ss ago; limit %ss" % (int(age), max_age))


def probe_http(item):
    request = urllib.request.Request(item["url"], headers={"User-Agent": "MagnetGoogo-Health/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        if not 200 <= response.status < 300:
            return False, "HTTP status %s" % response.status
        if item.get("json_checks") or item.get("error_field"):
            data = json.loads(response.read(1024 * 1024).decode("utf-8"))
            if not isinstance(data, dict):
                return False, "Expected an object in the health response"
            for key, expected in item.get("json_checks", {}).items():
                if key not in data or data[key] != expected:
                    return False, "Health field %s is missing or abnormal" % key
            field = item.get("error_field")
            if field and field not in data:
                return False, "Health error field is missing"
            if field and data.get(field):
                return False, "Application reports an error; details remain in its local logs"
    return True, "Endpoint responded successfully"


def memory_finding(item):
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            parts = line.split()
            if parts and parts[0] in ("MemTotal:", "MemAvailable:"):
                values[parts[0].rstrip(":")] = int(parts[1])
        available = 100.0 * values["MemAvailable"] / values["MemTotal"]
        minimum = float(item.get("min_available_percent", 5))
        return finding("memory", "可用内存", available >= minimum,
                       "Available memory %.1f%%; minimum %.1f%%" % (available, minimum), 3)
    except (OSError, ValueError, KeyError, IndexError, ZeroDivisionError):
        return finding("memory", "可用内存", False, "Memory availability is unknown", 3)


def load_finding(item):
    try:
        ratio = os.getloadavg()[2] / (os.cpu_count() or 1)
        maximum = float(item.get("max_load_per_cpu", 2))
        return finding("load", "持续系统负载", ratio < maximum,
                       "15-minute load per CPU %.2f; limit %.2f" % (ratio, maximum), 3)
    except (OSError, ValueError, AttributeError):
        return finding("load", "持续系统负载", False, "System load is unknown", 3)


def collect(config, uptime=None):
    if uptime is None:
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    results = []
    states = {}
    def state(name):
        if name not in states:
            states[name] = unit_state(name)
        return states[name]
    for item in config.get("services", []):
        name = item["unit"]
        value = state(name)
        healthy = value.get("LoadState") == "loaded" and value.get("ActiveState") == "active"
        results.append(finding("service-" + name, item.get("label", name), healthy,
                               "Service state=%s/%s" % (value.get("ActiveState", "unknown"),
                                                        value.get("SubState", "unknown"))))
    for item in config.get("timers", []):
        name = item["unit"]
        value = state(name)
        healthy = value.get("LoadState") == "loaded" and value.get("ActiveState") == "active"
        results.append(finding("timer-" + name, item.get("label", name), healthy,
                               "Timer state=%s" % value.get("ActiveState", "unknown")))
    for item in config.get("jobs", []):
        results.append(job_finding(item, state(item["unit"]), uptime))
    for item in config.get("containers", []):
        name = item["name"]
        code, output = command(["docker", "inspect", "--format", "{{json .State}}", name])
        try:
            value = json.loads(output) if not code else {}
            running = value.get("Running") is True
            health = (value.get("Health") or {}).get("Status")
            healthy = running and health in (None, "healthy")
            detail = "Container running=%s health=%s" % (running, health or "no_healthcheck")
        except (ValueError, TypeError, AttributeError):
            healthy, detail = False, "Container state is unreadable"
        results.append(finding("container-" + name, item.get("label", name), healthy, detail))
    for item in config.get("disks", []):
        path = item["path"]
        try:
            usage = shutil.disk_usage(path)
            used = 100.0 * usage.used / usage.total
            limit = float(item.get("max_used_percent", 90))
            healthy = used < limit
            detail = "Disk %s used %.1f%%; limit %.1f%%" % (path, used, limit)
        except (OSError, ZeroDivisionError):
            healthy, detail = False, "Disk usage is unavailable"
        results.append(finding("disk-" + path.replace("/", "_"), item.get("label", path),
                               healthy, detail, threshold=3))
    if config.get("memory") is not None:
        results.append(memory_finding(config["memory"]))
    if config.get("load") is not None:
        results.append(load_finding(config["load"]))
    for item in config.get("peers", []):
        try:
            with socket.create_connection((item["host"], int(item.get("port", 22))), timeout=5):
                pass
            healthy, detail = True, "Peer TCP endpoint is reachable"
        except OSError as exc:
            healthy, detail = False, "Peer TCP probe failed: " + type(exc).__name__
        results.append(finding("peer-" + item["label"], item["label"] + "连通性",
                               healthy, detail, threshold=3))
    for item in config.get("http", []):
        try:
            healthy, detail = probe_http(item)
        except (OSError, ValueError, TypeError) as exc:
            healthy, detail = False, "Endpoint health probe failed: " + type(exc).__name__
        results.append(finding("http-" + item["label"], item["label"],
                               healthy, detail, threshold=3))
    for item in config.get("certificates", []):
        host = item["host"]
        try:
            context = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=5) as raw:
                with context.wrap_socket(raw, server_hostname=host) as conn:
                    cert = conn.getpeercert()
            remaining = (ssl.cert_time_to_seconds(cert["notAfter"]) - time.time()) / 86400
            limit = int(item.get("min_days", 14))
            healthy = remaining >= limit
            detail = "Certificate has %.1f days remaining; threshold %s days" % (remaining, limit)
        except (OSError, ValueError, KeyError) as exc:
            healthy, detail = False, "Certificate check failed: " + type(exc).__name__
        results.append(finding("certificate-" + host, item.get("label", host),
                               healthy, detail, threshold=3))
    return results


def notify(config, results, dry_run):
    calls = 0
    for item in results:
        if item["healthy"] is None or dry_run:
            continue
        healthy = item["healthy"]
        title = "%s %s%s" % (config.get("host_label", "服务器"), item["label"],
                            "已恢复" if healthy else "异常")
        arguments = [
            config.get("python_bin", sys.executable),
            config.get("alert_bin", "/opt/magnet-alerts/magnet-alert.py"),
            "success" if healthy else "failure",
            "--key", item["key"],
            "--state-file", config.get("state_file", "/var/lib/magnet-alerts/ops-health.json"),
            "--title", title, "--message", item["detail"],
            "--severity", "P1", "--repeat-hours", "6",
            "--threshold", str(item["threshold"]), "--strict"]
        environment = dict(os.environ)
        environment["MAGNET_ALERT_TRANSPORT"] = config.get("transport", "xtuis")
        code, _output = command(arguments, timeout=25, env=environment)
        if code:
            print("OPS_NOTIFY_ERROR key=%s" % item["key"], file=sys.stderr)
        calls += 1
    return calls


def save_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".ops-health.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, str(path))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/etc/magnet-alerts/ops-health.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not config.get("host_label"):
        raise ValueError("Invalid ops health configuration")
    results = collect(config)
    report = {"observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "host_label": config["host_label"], "checks": results}
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        notify(config, results, False)
        save_report(config.get("report_file", "/var/lib/magnet-alerts/ops-health-latest.json"), report)
        failed = [item["key"] for item in results if item["healthy"] is False]
        print("OPS_HEALTH checks=%s failed=%s keys=%s" % (len(results), len(failed), ",".join(failed)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError) as error:
        print("OPS_HEALTH_ERROR " + type(error).__name__, file=sys.stderr)
        raise SystemExit(2)
