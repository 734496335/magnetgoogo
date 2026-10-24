#!/usr/bin/env python3
"""Private, bounded XTUIS outbox; Python 3.6+, standard library only.
Queued, accepted and confirmed are separate states; none means human-read.
A lost POST response can duplicate during bounded retries. Known msg_id is never reposted.
"""
import contextlib
import email.utils
import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_DB = Path("/var/lib/magnet-alerts/xtuis.sqlite3")
MSG_ID_RE = re.compile(r"^wx_[A-Za-z0-9_-]{1,120}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,256}$")


def db_path():
    return Path(os.environ.get("MAGNET_ALERT_OUTBOX_DB", str(DEFAULT_DB)))


def _limit(name, default, maximum):
    try:
        return max(1, min(int(os.environ.get(name, str(default))), maximum))
    except ValueError:
        return default


@contextlib.contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.fdopen(os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600), "a+b")
    locked = False
    try:
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        try:
            if locked and os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif locked:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _connect(path):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.close(os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600))
    os.chmod(str(path), 0o600)
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS outbox(
      id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
      stream_key TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL, next_at INTEGER NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, receipt_attempts INTEGER NOT NULL DEFAULT 0,
      msg_id TEXT, accepted_at INTEGER, last_code TEXT, updated_at INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS outbox_due ON outbox(state,next_at,id);
    CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY AUTOINCREMENT,
      kind TEXT NOT NULL, at INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS requests_time ON requests(kind,at);
    CREATE TABLE IF NOT EXISTS cooldowns(kind TEXT PRIMARY KEY, until_at INTEGER NOT NULL);
    """)
    conn.commit()
    return conn


def enqueue(title, body, event_id=None, stream_key="default",
            ttl_seconds=86400, now=None, path=None):
    now = int(time.time()) if now is None else int(now)
    path = db_path() if path is None else Path(path)
    title, body = str(title).strip(), str(body)
    if not title or len(title.encode("utf-8")) > 1024:
        return False, "xtuis_title_invalid"
    if len((title + body).encode("utf-8")) > 48000:
        return False, "xtuis_message_too_large"
    try:
        ttl_seconds = int(ttl_seconds)
    except (TypeError, ValueError):
        return False, "xtuis_ttl_invalid"
    if not 1 <= ttl_seconds <= 172800:
        return False, "xtuis_ttl_invalid"
    identity = str(event_id) if event_id is not None else title + "\0" + body
    identity = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    try:
        with contextlib.closing(_connect(path)) as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                if conn.execute("SELECT id FROM outbox WHERE event_id=?", (identity,)).fetchone():
                    return True, "xtuis_queued_duplicate"
                count = conn.execute("SELECT count(*) FROM outbox WHERE state IN ('pending','accepted')").fetchone()[0]
                if count >= 1000:
                    return False, "xtuis_queue_full"
                conn.execute(
                    "INSERT INTO outbox(event_id,stream_key,title,body,created_at,expires_at,next_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (identity,str(stream_key)[:256],title,body,now,now+ttl_seconds,now,now))
        return True, "xtuis_queued"
    except (OSError, sqlite3.Error):
        return False, "xtuis_queue_unavailable"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _retry_seconds(raw):
    if raw is None:
        return None
    try:
        return max(1, int(float(raw)))
    except (ValueError, TypeError, OverflowError):
        try:
            return max(1, int(email.utils.parsedate_to_datetime(str(raw)).timestamp() - time.time()))
        except (ValueError, TypeError, OverflowError, AttributeError):
            return None


def _http_json(url, data=None):
    headers = {"User-Agent": "MagnetGoogo-Alert/2.0"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        try:
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=10) as response:
                status, raw, response_headers = int(response.status), response.read(65537), response.headers
        except urllib.error.HTTPError as exc:
            status, raw, response_headers = int(exc.code), exc.read(65537), exc.headers
    except (OSError, ValueError, urllib.error.URLError):
        return 0, {}, 120, "network_uncertain"
    header_delay = _retry_seconds(response_headers.get("Retry-After") if response_headers else None)
    try:
        payload = json.loads(raw.decode("utf-8")) if len(raw) <= 65536 else None
    except (ValueError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        return status, {}, header_delay or 120, "response_invalid"
    delay = header_delay or _retry_seconds(payload.get("retry_after_seconds")) or 60
    return status, payload, delay, None


def _post(token, title, body):
    data = urllib.parse.urlencode({"text":title,"desp":body}).encode("utf-8")
    status, payload, delay, error = _http_json("https://wx.xtuis.cn/"+token+".send", data)
    if status == 429 or str(payload.get("code")) == "429":
        return "retry", None, delay, "rate_limited"
    if status in (400,401,403,404):
        return "failed", None, 0, "http_%s" % status
    if error:
        return "retry", None, delay, error
    msg_id = payload.get("msg_id")
    if status == 200 and str(payload.get("code")) == "200" and isinstance(msg_id,str) and MSG_ID_RE.fullmatch(msg_id):
        return "accepted", msg_id, 30, "provider_accepted"
    if status == 200 and str(payload.get("code")) in ("400","401","403","404"):
        return "failed", None, 0, "provider_rejected"
    return "retry", None, 120, "response_invalid"


def _receipt(msg_id):
    status, payload, delay, error = _http_json("https://msgstatus.xtuis.cn/status/"+msg_id)
    if status == 429:
        return "accepted", delay, "receipt_rate_limited"
    if error or status != 200 or payload.get("msg_id") != msg_id:
        return "accepted", max(120,delay), "receipt_unknown"
    if payload.get("status") == "success":
        return "confirmed", 0, "provider_confirmed"
    if payload.get("status") in ("failed","failure","error"):
        return "failed", 0, "provider_failed"
    return "accepted", max(30,delay), "provider_pending"


def _day_start(now):
    return ((int(now)+28800)//86400)*86400-28800


def _due(conn, kind, now, minute_limit, daily=None):
    cooldown = conn.execute("SELECT until_at FROM cooldowns WHERE kind=?", (kind,)).fetchone()
    if cooldown is not None and cooldown[0] > now:
        return False
    minute = conn.execute("SELECT count(*) FROM requests WHERE kind=? AND at>?", (kind,now-60)).fetchone()[0]
    if minute >= minute_limit:
        return False
    if daily is not None:
        count = conn.execute("SELECT count(*) FROM requests WHERE kind=? AND at>=?", (kind,_day_start(now))).fetchone()[0]
        if count >= daily:
            return False
    return True


def _request(conn, kind, now):
    with conn:
        conn.execute("INSERT INTO requests(kind,at) VALUES(?,?)", (kind,now))


def _cooldown(conn, kind, until_at):
    with conn:
        conn.execute("INSERT OR REPLACE INTO cooldowns(kind,until_at) VALUES(?,?)", (kind,until_at))


def _finish(conn, row_id, state, code, now, next_at=0):
    with conn:
        conn.execute(
            "UPDATE outbox SET state=?,last_code=?,updated_at=?,next_at=?,"
            "body=CASE WHEN ? IN ('confirmed','failed') THEN '' ELSE body END WHERE id=?",
            (state,code,now,next_at,state,row_id))


def flush(path=None, now=None, max_messages=4, dry_run=False):
    path = db_path() if path is None else Path(path)
    if dry_run:
        return {"dry_run":True,"network_requests":0}
    token = os.environ.get("MAGNET_ALERT_XTUIS_TOKEN","").strip()
    if not TOKEN_RE.fullmatch(token):
        return {"error":"xtuis_not_configured","network_requests":0}
    clock = (lambda:int(time.time())) if now is None else (lambda:int(now))
    post_limit = _limit("MAGNET_ALERT_XTUIS_PER_MINUTE",10,10)
    daily_limit = _limit("MAGNET_ALERT_XTUIS_DAILY_LIMIT",100,200)
    query_limit = _limit("MAGNET_ALERT_XTUIS_STATUS_PER_MINUTE",4,4)
    max_messages = max(1,min(int(max_messages),10))
    result = {"queued_to_provider":0,"confirmed":0,"failed":0,"expired":0,"network_requests":0}
    with file_lock(str(path)+".worker.lock"):
        with contextlib.closing(_connect(path)) as conn:
            current = clock()
            with conn:
                result["expired"] += conn.execute(
                    "UPDATE outbox SET state='failed',last_code='expired_before_send',body='',updated_at=?"
                    " WHERE state='pending' AND expires_at<=?",(current,current)).rowcount
                conn.execute("DELETE FROM requests WHERE at<?",(current-259200,))
                conn.execute("DELETE FROM outbox WHERE state IN ('confirmed','failed') AND updated_at<?",(current-604800,))
            receipts = conn.execute(
                "SELECT * FROM outbox WHERE state='accepted' AND next_at<=? ORDER BY next_at,id LIMIT 4",(clock(),)).fetchall()
            for row in receipts:
                current = clock()
                if current-row["accepted_at"] >= 86400 or row["receipt_attempts"] >= 20:
                    _finish(conn,row["id"],"failed","receipt_unconfirmed",current)
                    result["failed"] += 1
                    continue
                if not _due(conn,"query",current,query_limit):
                    break
                _request(conn,"query",current)
                with conn:
                    conn.execute("UPDATE outbox SET receipt_attempts=receipt_attempts+1 WHERE id=?",(row["id"],))
                result["network_requests"] += 1
                state,delay,code = _receipt(row["msg_id"])
                if code == "receipt_rate_limited":
                    _cooldown(conn, "query", clock() + delay)
                delay = max(delay,min(3600,30*(2**min(row["receipt_attempts"],7))))
                _finish(conn,row["id"],state,code,clock(),clock()+delay)
                if state in ("confirmed","failed"):
                    result[state] += 1
            for _ in range(max_messages):
                current = clock()
                if not _due(conn,"post",current,post_limit,daily_limit):
                    break
                row = conn.execute(
                    "SELECT a.* FROM outbox a WHERE a.state='pending' AND a.next_at<=?"
                    " AND NOT EXISTS(SELECT 1 FROM outbox b WHERE b.stream_key=a.stream_key"
                    " AND b.id<a.id AND b.state IN ('pending','accepted')) ORDER BY a.id LIMIT 1",(current,)).fetchone()
                if row is None:
                    break
                if row["expires_at"] <= current:
                    _finish(conn, row["id"], "failed", "expired_before_send", current)
                    result["expired"] += 1
                    continue
                if row["attempts"] >= 4:
                    _finish(conn,row["id"],"failed","retry_exhausted",current)
                    result["failed"] += 1
                    continue
                _request(conn,"post",current)
                with conn:
                    conn.execute("UPDATE outbox SET attempts=attempts+1 WHERE id=?",(row["id"],))
                result["network_requests"] += 1
                state,msg_id,delay,code = _post(token,row["title"],row["body"])
                if code == "rate_limited":
                    _cooldown(conn, "post", clock() + delay)
                if state == "accepted":
                    with conn:
                        conn.execute(
                            "UPDATE outbox SET state='accepted',msg_id=?,accepted_at=?,next_at=?,last_code=?,updated_at=? WHERE id=?",
                            (msg_id,clock(),clock()+30,code,clock(),row["id"]))
                    result["queued_to_provider"] += 1
                elif state == "failed" or row["attempts"]+1 >= 4:
                    _finish(conn,row["id"],"failed",code if state=="failed" else "retry_exhausted_"+code,clock())
                    result["failed"] += 1
                else:
                    delay = max(delay,min(3600,120*(2**row["attempts"])))
                    _finish(conn,row["id"],"pending",code,clock(),clock()+delay)
    return result


def status(path=None, now=None):
    path = db_path() if path is None else Path(path)
    now = int(time.time()) if now is None else int(now)
    if not path.exists():
        return {"counts":{},"oldest_pending_age_seconds":0,"post_attempts_today":0}
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)) as conn:
        counts = dict(conn.execute("SELECT state,count(*) FROM outbox GROUP BY state").fetchall())
        oldest = conn.execute("SELECT min(created_at) FROM outbox WHERE state IN ('pending','accepted')").fetchone()[0]
        attempts = conn.execute("SELECT count(*) FROM requests WHERE kind='post' AND at>=?",(_day_start(now),)).fetchone()[0]
        return {"counts":counts,"oldest_pending_age_seconds":max(0,now-oldest) if oldest is not None else 0,"post_attempts_today":attempts}
