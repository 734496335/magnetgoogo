"""URL helpers."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse


def absolutize(base: str, href: str | None) -> str | None:
    if href is None:
        return None
    text = href.strip()
    if not text:
        return None
    return urljoin(base, text)


def path_key(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path


def external_key_from_path(url: str, prefixes: tuple[str, ...]) -> str | None:
    path = path_key(url)
    for prefix in prefixes:
        p = prefix if prefix.startswith("/") else f"/{prefix}"
        if path.startswith(p.rstrip("/") + "/") or path == p.rstrip("/"):
            rest = path[len(p.rstrip("/")) :].lstrip("/")
            if rest:
                return rest.split("/")[0]
    return None
