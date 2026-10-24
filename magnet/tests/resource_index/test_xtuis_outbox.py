import importlib.util
import io
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "deploy" / "alerts" / "linux" / "xtuis_outbox.py"


@pytest.fixture
def box(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("outbox_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("MAGNET_ALERT_OUTBOX_DB", str(tmp_path / "queue.sqlite3"))
    monkeypatch.setenv("MAGNET_ALERT_XTUIS_TOKEN", "test-token-123")
    monkeypatch.setenv("MAGNET_ALERT_XTUIS_DAILY_LIMIT", "100")
    monkeypatch.setenv("MAGNET_ALERT_XTUIS_PER_MINUTE", "10")
    monkeypatch.setenv("MAGNET_ALERT_XTUIS_STATUS_PER_MINUTE", "4")
    def forbid(*_args, **_kwargs):
        raise AssertionError("unexpected network access")
    monkeypatch.setattr(module, "_http_json", forbid)
    return module


def add(box, event, stream=None, now=100, ttl=86400):
    return box.enqueue(event, "body", event_id=event, stream_key=stream or event,
        now=now, ttl_seconds=ttl)


def test_durable_dedup_without_token(box, monkeypatch):
    monkeypatch.delenv("MAGNET_ALERT_XTUIS_TOKEN")
    assert add(box, "one") == (True, "xtuis_queued")
    assert add(box, "one") == (True, "xtuis_queued_duplicate")
    assert box.status(now=100)["counts"] == {"pending": 1}
    assert box.flush(now=100)["error"] == "xtuis_not_configured"
    assert box.status(now=100)["counts"] == {"pending": 1}


def test_fault_recovery_keep_order_and_receipts_separate(box, monkeypatch):
    add(box, "failure", stream="health")
    add(box, "recovery", stream="health")
    sent = []
    def post(_token, title, _body):
        sent.append(title)
        return "accepted", "wx_%s" % len(sent), 30, "provider_accepted"
    monkeypatch.setattr(box, "_post", post)
    monkeypatch.setattr(box, "_receipt", lambda _id: ("confirmed", 0, "provider_confirmed"))
    assert box.flush(now=100)["queued_to_provider"] == 1
    assert sent == ["failure"]
    assert box.status(now=100)["counts"] == {"accepted": 1, "pending": 1}
    assert box.flush(now=130)["confirmed"] == 1
    assert sent == ["failure", "recovery"]
    box.flush(now=160)
    assert box.status(now=160)["counts"] == {"confirmed": 2}


def test_network_retry_is_bounded_and_not_business_callback_dependent(box, monkeypatch):
    add(box, "fault")
    calls = []
    def post(*_args):
        calls.append(1)
        return "retry", None, 120, "network_uncertain"
    monkeypatch.setattr(box, "_post", post)
    for now in (100, 220, 460, 940, 2000):
        box.flush(now=now)
    assert len(calls) == 4
    assert box.status(now=2000)["counts"] == {"failed": 1}


def test_known_msg_id_never_reposts_while_receipt_unknown(box, monkeypatch):
    add(box, "fault")
    posts = []
    monkeypatch.setattr(box, "_post", lambda *_: (posts.append(1) or "accepted", "wx_one", 30, "provider_accepted"))
    monkeypatch.setattr(box, "_receipt", lambda _: ("accepted", 120, "receipt_unknown"))
    for now in (100, 130, 250, 1000):
        box.flush(now=now)
    assert len(posts) == 1
    assert box.status(now=1000)["counts"] == {"accepted": 1}


@pytest.mark.parametrize("payload,expected", [
    ({"code": 200}, "retry"),
    ({"code": True, "msg_id": "wx_good"}, "retry"),
    ({"code": 200, "msg_id": "https://other.invalid/secret"}, "retry"),
    ({"code": "200", "msg_id": "wx_good"}, "accepted"),
    ({"code": 403}, "failed"),
])
def test_post_requires_valid_acceptance(box, monkeypatch, payload, expected):
    monkeypatch.setattr(box, "_http_json", lambda *_: (200, payload, 60, None))
    assert box._post("test-token-123", "title", "body")[0] == expected


def test_form_encoding_and_no_secret_in_result(box, monkeypatch):
    captured = {}
    def request(url, data):
        captured.update(url=url, data=data)
        return 200, {"code": 200, "msg_id": "wx_good"}, 60, None
    monkeypatch.setattr(box, "_http_json", request)
    result = box._post("test-token-123", "测试 & 标题", "首行\n第二行=值")
    assert urllib.parse.parse_qs(captured["data"].decode("utf-8")) == {
        "text": ["测试 & 标题"], "desp": ["首行\n第二行=值"]}
    assert "test-token-123" not in str(result)


def test_global_429_cooldown_blocks_other_messages(box, monkeypatch):
    add(box, "one")
    add(box, "two")
    calls = []
    def post(*_args):
        calls.append(1)
        return "retry", None, 900, "rate_limited"
    monkeypatch.setattr(box, "_post", post)
    box.flush(now=100)
    box.flush(now=999)
    assert len(calls) == 1
    box.flush(now=1000)
    assert len(calls) == 2


def test_daily_budget_and_shanghai_midnight_reset(box, monkeypatch):
    monkeypatch.setenv("MAGNET_ALERT_XTUIS_DAILY_LIMIT", "2")
    for name in ("a", "b", "c"):
        add(box, name)
    posts = []
    def post(*_args):
        posts.append(1)
        return "accepted", "wx_%s" % len(posts), 30, "provider_accepted"
    monkeypatch.setattr(box, "_post", post)
    monkeypatch.setattr(box, "_receipt", lambda _: ("confirmed", 0, "provider_confirmed"))
    box.flush(now=100, max_messages=10)
    box.flush(now=200, max_messages=10)
    assert len(posts) == 2
    assert box.status(now=200)["post_attempts_today"] == 2
    box.flush(now=57600, max_messages=10)
    assert len(posts) == 3
    assert box.status(now=57600)["post_attempts_today"] == 1


def test_query_limit_is_four_per_rolling_minute(box, monkeypatch):
    for number in range(5):
        add(box, str(number))
    post_ids = []
    def post(*_args):
        post_ids.append(1)
        return "accepted", "wx_%s" % len(post_ids), 30, "provider_accepted"
    queries = []
    monkeypatch.setattr(box, "_post", post)
    monkeypatch.setattr(box, "_receipt", lambda _: (queries.append(1) or "confirmed", 0, "provider_confirmed"))
    box.flush(now=100, max_messages=10)
    box.flush(now=130)
    box.flush(now=131)
    assert len(queries) == 4
    box.flush(now=191)
    assert len(queries) == 5


def test_expired_price_notice_is_not_sent(box):
    add(box, "price", ttl=10)
    result = box.flush(now=110)
    assert result["network_requests"] == 0
    assert result["failed"] == 0
    assert result["expired"] == 1
    assert box.status(now=110)["counts"] == {"failed": 1}


def test_dry_run_has_no_network_or_files(box, tmp_path):
    result = box.flush(now=100, dry_run=True)
    assert result == {"dry_run": True, "network_requests": 0}
    assert list(tmp_path.iterdir()) == []


def test_http_429_honors_header_even_with_invalid_body(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("outbox_http_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class Opener:
        def open(self, request, timeout):
            assert timeout == 10
            raise urllib.error.HTTPError(request.full_url, 429, "private", {"Retry-After": "900"}, io.BytesIO(b"not json"))
    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *_: Opener())
    result = module._http_json("https://example.invalid/test-token-123")
    assert result == (429, {}, 900, "response_invalid")
    assert "test-token-123" not in str(result)


def test_network_error_redacts_secret(monkeypatch):
    spec = importlib.util.spec_from_file_location("outbox_http_error_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class Opener:
        def open(self, request, timeout):
            raise OSError("failed https://example.invalid/test-token-123")
    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *_: Opener())
    result = module._http_json("https://example.invalid/test-token-123")
    assert result == (0, {}, 120, "network_uncertain")
    assert "test-token-123" not in str(result)


def test_failed_receipt_is_never_confirmed(box, monkeypatch):
    monkeypatch.setattr(box, "_http_json", lambda *_: (200, {"msg_id": "wx_one", "status": "failed"}, 60, None))
    assert box._receipt("wx_one")[0] == "failed"
    monkeypatch.setattr(box, "_http_json", lambda *_: (200, {"msg_id": "wx_other", "status": "success"}, 60, None))
    assert box._receipt("wx_one")[0] == "accepted"
