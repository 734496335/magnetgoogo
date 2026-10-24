"""Durably hand new notifications to the host relay without an API credential."""
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

TEXT_LIMIT_BYTES = 47000


def enqueue_wechat(title, message, env=None, now=None):
    env = os.environ if env is None else env
    configured = env.get("MAGNET_WECHAT_SPOOL_DIR", "").strip()
    if not configured:
        return None
    temporary = None
    try:
        directory = Path(configured)
        if not directory.is_absolute() or directory.is_symlink():
            raise ValueError("invalid spool directory")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not directory.is_dir():
            raise ValueError("invalid spool directory")
        ttl = int(env.get("MAGNET_WECHAT_TTL_SECONDS", "1800"))
        if not 60 <= ttl <= 7200:
            raise ValueError("invalid message lifetime")
        if not isinstance(title, str) or not title.strip() or len(title.encode("utf-8")) > 512:
            raise ValueError("invalid title")
        if not isinstance(message, str) or len((title + message).encode("utf-8")) > TEXT_LIMIT_BYTES:
            raise ValueError("invalid message")
        if sum(1 for _ in directory.glob("*.json")) >= 1000:
            raise ValueError("spool capacity reached")
        created = int(time.time() if now is None else now)
        event_id = "travel-" + uuid.uuid4().hex
        payload = {
            "version": 1, "event_id": event_id, "key": "travel-low-price",
            "title": title, "message": message, "created_at_epoch": created,
            "expires_at_epoch": created + ttl,
        }
        fd, temporary = tempfile.mkstemp(prefix=".pending-", suffix=".tmp", dir=str(directory))
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, str(directory / (event_id + ".json")))
        temporary = None
        if os.name == "posix":
            directory_fd = os.open(str(directory), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return True
    except (OSError, TypeError, ValueError) as exc:
        logging.getLogger(__name__).warning("WeChat spool failed: %s", type(exc).__name__)
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
