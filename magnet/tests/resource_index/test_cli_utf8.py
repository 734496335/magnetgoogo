from __future__ import annotations

import io
from types import SimpleNamespace

from magnet.resource_index import cli


def test_print_json_emits_ascii_safe_json_bytes(monkeypatch) -> None:
    buffer = io.BytesIO()
    fake_stdout = SimpleNamespace(buffer=buffer)
    monkeypatch.setattr(cli.sys, "stdout", fake_stdout)

    cli._print_json({"label": "豆瓣", "title": "葬送的芙莉莲"}, pretty=True)

    payload = buffer.getvalue()
    text = payload.decode("ascii")
    assert text.endswith("\n")
    assert "\\u8c46\\u74e3" in text
    assert "\\u846c\\u9001" in text
    assert __import__("json").loads(text) == {"label": "豆瓣", "title": "葬送的芙莉莲"}
