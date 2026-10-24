from __future__ import annotations

import base64
import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

import apprise

from .destination_catalog import destination_name
from .models import FareCandidate
from .wechat_spool import enqueue_wechat


class Notifier:
    def __init__(self, urls: tuple[str, ...]):
        self.urls = urls
        self.app = apprise.Apprise()
        self.valid_url_count = sum(1 for url in urls if self.app.add(url))
        self.cloudmonitor_url = os.environ.get("MAGNET_ALERT_CLOUDMONITOR_URL", "").strip()
        self.cloudmonitor_security_word = os.environ.get("MAGNET_ALERT_CLOUDMONITOR_SECURITY_WORD", "").strip()
        self.cloudmonitor_access_key = os.environ.get("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_ID", "").strip()
        self.cloudmonitor_access_secret = os.environ.get("MAGNET_ALERT_CLOUDMONITOR_ACCESS_KEY_SECRET", "").strip()
        self.cloudmonitor_configured = bool(self.cloudmonitor_url)
        self.smtp_user = os.environ.get("MAGNET_ALERT_SMTP_USER", "").strip()
        self.smtp_auth_code = os.environ.get("MAGNET_ALERT_SMTP_AUTH_CODE", "").strip()
        self.smtp_to = os.environ.get("MAGNET_ALERT_TO", "").strip()
        self.smtp_host = os.environ.get("MAGNET_ALERT_SMTP_HOST", "smtp.qq.com").strip()
        self.smtp_port = os.environ.get("MAGNET_ALERT_SMTP_PORT", "465").strip()
        self.smtp_configured = bool(self.smtp_user and self.smtp_auth_code and self.smtp_to)
        self.configured = (self.valid_url_count > 0 or self.cloudmonitor_configured or self.smtp_configured
                           or bool(os.environ.get("MAGNET_WECHAT_SPOOL_DIR", "").strip()))

    def _send_cloudmonitor(self, title: str, body: str) -> bool:
        if not self.cloudmonitor_configured:
            return False
        if bool(self.cloudmonitor_access_key) != bool(self.cloudmonitor_access_secret):
            return False
        message = body
        if self.cloudmonitor_security_word:
            message = f"{message}\n{self.cloudmonitor_security_word}"
        payload = json.dumps(
            {
                "ruleName": "Travel Fare Monitor",
                "title": title,
                "message": message,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Travel-Fare-Monitor/1.0",
        }
        if self.cloudmonitor_access_key and self.cloudmonitor_access_secret:
            raw = f"{self.cloudmonitor_access_key}:{self.cloudmonitor_access_secret}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        request = urllib.request.Request(self.cloudmonitor_url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw_response = response.read()
                if int(getattr(response, "status", 200)) != 200:
                    return False
        except (OSError, TimeoutError, urllib.error.URLError):
            return False
        try:
            result = json.loads(raw_response.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return True
        if isinstance(result, dict):
            code = str(result.get("code") or "")
            if code and code != "200":
                return False
        return True

    def _send_smtp(self, title: str, body: str) -> bool:
        if not self.smtp_configured:
            return False
        try:
            port = int(self.smtp_port)
        except ValueError:
            return False
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.smtp_user
        message["To"] = self.smtp_to
        message.set_content(body)
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_host, port, timeout=20, context=context) as client:
                client.login(self.smtp_user, self.smtp_auth_code)
                client.send_message(message)
        except (OSError, smtplib.SMTPException):
            return False
        return True

    def _send_legacy_message(self, title: str, body: str) -> bool:
        if self.valid_url_count > 0 and self.app.notify(title=title, body=body):
            return True
        if self._send_cloudmonitor(title, body):
            return True
        return self._send_smtp(title, body)

    def send_message(self, title: str, body: str) -> bool:
        wechat_result = enqueue_wechat(title, body)
        if wechat_result is None:
            return self._send_legacy_message(title, body)
        try:
            self._send_legacy_message(title, body)
        except Exception as exc:
            logging.getLogger(__name__).warning("Legacy notification failed: %s", type(exc).__name__)
        return wechat_result

    def send(self, candidate: FareCandidate) -> bool:
        return self.send_batch([candidate])

    def send_batch(self, candidates: list[FareCandidate]) -> bool:
        """Send one digest for all newly alertable fares in a scan.

        A provider may return many qualifying date combinations for the same
        route. Sending one message per exact trip creates a mail storm. Keep
        exact-trip alert state, but collapse delivery into one digest so every
        new low fare is still represented without flooding the inbox.
        """
        if not candidates:
            return False

        best_by_trip: dict[str, FareCandidate] = {}
        for candidate in candidates:
            existing = best_by_trip.get(candidate.alert_key)
            if existing is None or candidate.price < existing.price:
                best_by_trip[candidate.alert_key] = candidate
        unique = sorted(
            best_by_trip.values(),
            key=lambda item: (item.origin, item.destination, item.price, item.departure_date, item.return_date),
        )

        if len(unique) == 1:
            candidate = unique[0]
            origin_name = destination_name(candidate.origin) or "未收录出发城市"
            destination_city = destination_name(candidate.destination) or "未收录目的城市"
            title = f"发现低价往返机票：{origin_name} → {destination_city}"
            body = (
                f"监控：{candidate.monitor_name}\n"
                f"航线：{origin_name} → {destination_city}\n"
                f"去程：{candidate.departure_date.isoformat()}\n"
                f"返程：{candidate.return_date.isoformat()}\n"
                f"旅行时长：{candidate.duration_days} 天\n"
                f"往返总价：{candidate.price:.0f} {candidate.currency}\n"
                f"数据源：{candidate.provider}"
            )
            return self.send_message(title, body)

        route_groups: dict[tuple[str, str, str], list[FareCandidate]] = {}
        for candidate in unique:
            origin_name = destination_name(candidate.origin) or candidate.origin
            destination_city = destination_name(candidate.destination) or candidate.destination
            route_groups.setdefault((origin_name, destination_city, candidate.currency), []).append(candidate)

        if len(route_groups) == 1:
            (origin_name, destination_city, currency), rows = next(iter(route_groups.items()))
            cheapest = min(item.price for item in rows)
            title = f"发现{len(unique)}个低价往返：{origin_name} → {destination_city}，最低 {cheapest:.0f} {currency}"
        else:
            cheapest = min(item.price for item in unique)
            currency = unique[0].currency
            title = f"发现{len(unique)}个低价往返机票（{len(route_groups)}条航线），最低 {cheapest:.0f} {currency}"

        lines = [
            f"监控：{unique[0].monitor_name}",
            f"本轮共有 {len(unique)} 个新低价行程，已合并为 1 封提醒。",
            "",
        ]
        for (origin_name, destination_city, currency), rows in route_groups.items():
            lines.append(f"【{origin_name} → {destination_city}】")
            for index, candidate in enumerate(sorted(rows, key=lambda item: (item.price, item.departure_date, item.return_date)), 1):
                lines.append(
                    f"{index}. {candidate.departure_date.isoformat()} → {candidate.return_date.isoformat()}"
                    f" · {candidate.duration_days}天 · {candidate.price:.0f} {currency} · {candidate.provider}"
                )
            lines.append("")
        lines.append("同一轮扫描中的相近低价会合并发送；具体全部机会仍可在监控后台查看。")
        return self.send_message(title, "\n".join(lines).rstrip())
