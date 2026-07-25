"""Generate sanitized JavBus fixtures (run once from repo root)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "javbus"


def write(rel: str, content: str) -> str:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def listing_page(items: list[tuple[str, str, str]]) -> str:
    parts = []
    for code, title, path in items:
        parts.append(
            f"""
<a class="movie-box" href="https://www.javbus.com/{path}">
  <div class="photo-frame">
    <img src="https://fixtures.invalid/thumbs/{code}.jpg" title="{code}">
  </div>
  <div class="photo-info">
    <span>{code} {title}</span>
    <date>{code}</date>
  </div>
</a>"""
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Fixture Listing</title></head>
<body>
<div id="waterfall">
{''.join(parts)}
</div>
</body></html>
"""


def detail_page(
    code: str,
    title: str,
    *,
    maker: bool = True,
    series: bool = True,
    multi_actor: bool = False,
    director: bool = True,
    gid: str = "100001",
    uc: str = "0",
    duration: str = "120分鐘",
    date: str = "2026-07-01",
) -> str:
    maker_html = (
        '<p><span class="header">製作商:</span> <a href="/studio/fixture-maker">Fixture Maker</a></p>'
        if maker
        else ""
    )
    series_html = (
        '<p><span class="header">系列:</span> <a href="/series/fixture-series">Fixture Series</a></p>'
        if series
        else ""
    )
    dir_html = (
        '<p><span class="header">導演:</span> <a href="/director/fixture-dir">Fixture Director</a></p>'
        if director
        else ""
    )
    if multi_actor:
        actors = """<p><span class="header">演員:</span>
      <span class="genre"><a href="/star/person-one">Fixture Person One</a></span>
      <span class="genre"><a href="/star/person-two">Fixture Person Two</a></span>
    </p>"""
    else:
        actors = """<p><span class="header">演員:</span>
      <span class="genre"><a href="/star/person-one">Fixture Person One</a></span>
    </p>"""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{code}</title></head>
<body>
<script>
var gid = {gid};
var uc = {uc};
var img = 'https://fixtures.invalid/cover/{code}.jpg';
</script>
<div class="container">
  <h3>{code} {title}</h3>
  <div class="col-md-3 info">
    <p><span class="header">識別碼:</span> <span style="color:#CC0000;">{code}</span></p>
    <p><span class="header">發行日期:</span> {date}</p>
    <p><span class="header">長度:</span> {duration}</p>
    {dir_html}
    {maker_html}
    <p><span class="header">發行商:</span> <a href="/label/fixture-pub">Fixture Publisher</a></p>
    {series_html}
    <p><span class="header">類別:</span>
      <span class="genre"><a href="/genre/tag-a">Fixture Tag A</a></span>
      <span class="genre"><a href="/genre/tag-b">Fixture Tag B</a></span>
    </p>
    {actors}
  </div>
  <a class="bigImage" href="https://fixtures.invalid/cover/{code}.jpg">
    <img src="https://fixtures.invalid/cover/{code}_s.jpg" alt="{code}">
  </a>
  <div id="sample-waterfall">
    <a class="sample-box" href="https://fixtures.invalid/sample/{code}_1.jpg"></a>
  </div>
</div>
</body></html>
"""


def resource_table(rows: list[tuple[str, str, str, str]]) -> str:
    trs = []
    for magnet, title, size, date in rows:
        trs.append(
            f"""
<tr>
  <td><a href="{magnet}">{title}</a></td>
  <td>{size}</td>
  <td>{date}</td>
</tr>"""
        )
    return f"""<!DOCTYPE html>
<html><body>
<table>
{''.join(trs)}
</table>
</body></html>
"""


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    docs: list[dict] = []

    h1 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    h2 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    h3 = "cccccccccccccccccccccccccccccccccccccccc"
    h4 = "dddddddddddddddddddddddddddddddddddddddd"
    h5 = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    h6 = "ffffffffffffffffffffffffffffffffffffffff"
    b32 = base64.b32encode(bytes.fromhex("1111111111111111111111111111111111111111")).decode().rstrip("=")

    items1 = [
        ("TST-001", "Fixture Title One", "TST-001"),
        ("TST-002", "Fixture Title Two", "TST-002"),
        ("TST-003", "Fixture Title Three", "TST-003"),
        ("TST-001", "Duplicate Same URL", "TST-001"),
        ("TST-004", "Fixture Title Four", "TST-004"),
    ]
    digest = write("listing/listing_page_1.html", listing_page(items1))
    docs.append(
        {
            "name": "listing_page_1",
            "type": "listing",
            "path": "listing/listing_page_1.html",
            "sha256": digest,
            "source_url": "https://www.javbus.com/page/1",
            "expected": "expected/listing_page_1.json",
        }
    )

    items2 = [
        ("TST-005", "Fixture Title Five", "TST-005"),
        ("TST-006", "Fixture Title Six", "TST-006"),
    ]
    digest = write("listing/listing_page_2.html", listing_page(items2))
    docs.append(
        {
            "name": "listing_page_2",
            "type": "listing",
            "path": "listing/listing_page_2.html",
            "sha256": digest,
            "source_url": "https://www.javbus.com/page/2",
        }
    )

    digest = write(
        "listing/listing_empty.html",
        '<!DOCTYPE html><html><body><div class="alert">沒有結果</div></body></html>\n',
    )
    docs.append(
        {
            "name": "listing_empty",
            "type": "listing",
            "path": "listing/listing_empty.html",
            "sha256": digest,
            "source_url": "https://www.javbus.com/search/none",
        }
    )

    digest = write(
        "listing/age_gate.html",
        """<!DOCTYPE html><html><body>
<div>driver-verify age check</div>
<p>請確認您已滿18歲 / Please confirm you are over 18</p>
</body></html>
""",
    )
    docs.append(
        {
            "name": "age_gate",
            "type": "age_gate",
            "path": "listing/age_gate.html",
            "sha256": digest,
            "source_url": "https://www.javbus.com/doc/driver-verify",
        }
    )

    digest = write(
        "listing/listing_dom_drift.html",
        '<!DOCTYPE html><html><body><div class="card-item"><a href="/x">no movie-box</a></div></body></html>\n',
    )
    docs.append(
        {
            "name": "listing_dom_drift",
            "type": "listing",
            "path": "listing/listing_dom_drift.html",
            "sha256": digest,
            "source_url": "https://www.javbus.com/drift",
        }
    )

    details = [
        ("TST-001", "Fixture Title One", {"multi_actor": False, "gid": "100001"}),
        ("TST-002", "Fixture Title Two", {"series": False, "gid": "100002"}),
        ("TST-003", "Fixture Title Three", {"maker": False, "multi_actor": True, "gid": "100003"}),
        (
            "TST-004",
            "Fixture Title Four",
            {"director": False, "duration": "90分钟", "date": "2026/07/02", "gid": "100004"},
        ),
        ("TST-005", "Fixture Title Five", {"gid": "100005", "uc": "1"}),
        ("TST-006", "Fixture Title Six No Resources", {"gid": "100006"}),
    ]
    for code, title, kw in details:
        rel = f"detail/{code.lower().replace('-', '_')}.html"
        digest = write(rel, detail_page(code, title, **kw))
        links = [] if code == "TST-006" else [f"resource_{code.lower().replace('-', '_')}"]
        docs.append(
            {
                "name": f"detail_{code.lower().replace('-', '_')}",
                "type": "detail",
                "path": rel,
                "sha256": digest,
                "source_url": f"https://www.javbus.com/{code}",
                "content_code": code,
                "links_to": links,
            }
        )

    digest = write(
        "detail/detail_missing_title.html",
        """<!DOCTYPE html><html><body>
<script>var gid = 9; var uc = 0;</script>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <span>TST-BAD</span></p>
</div>
</body></html>
""",
    )
    docs.append(
        {
            "name": "detail_missing_title",
            "type": "other",
            "path": "detail/detail_missing_title.html",
            "sha256": digest,
            "source_url": "https://www.javbus.com/TST-BAD",
        }
    )

    def mag(h: str, dn: str) -> str:
        return f"magnet:?xt=urn:btih:{h}&dn={dn}&tr=udp%3A%2F%2Ftracker.fixtures.invalid%3A80"

    resources = {
        "TST-001": [
            (mag(h1, "TST-001-HD"), "TST-001 [HD]", "1.5GB", "2026-07-02"),
            (mag(h2, "TST-001-SUB"), "TST-001 字幕", "2.0 GiB", "2026-07-03"),
            (mag(h1, "TST-001-HD-dup"), "TST-001 [HD] dup", "1.5GB", "2026-07-02"),
        ],
        "TST-002": [
            (mag(h3, "TST-002"), "TST-002", "800MB", "2026-07-04"),
        ],
        "TST-003": [
            (f"magnet:?xt=urn:btih:{b32}&dn=TST-003-B32", "TST-003 Base32", "500MB", "2026-07-05"),
            (mag(h4, "TST-003-2"), "TST-003 second", "1GB", "2026-07-05"),
        ],
        "TST-004": [
            (mag(h5, "TST-004"), "TST-004", "1.2GB", "2026-07-06"),
        ],
        "TST-005": [
            (mag(h6, "TST-005"), "TST-005", "3TB", "2026-07-07"),
        ],
    }
    for code, rows in resources.items():
        name = f"resource_{code.lower().replace('-', '_')}"
        rel = f"resource_table/{name}.html"
        digest = write(rel, resource_table(rows))
        docs.append(
            {
                "name": name,
                "type": "resource_table",
                "path": rel,
                "sha256": digest,
                "source_url": "https://www.javbus.com/ajax/uncledatoolsbyajax.php?gid=x&uc=0",
                "content_code": code,
            }
        )

    digest = write(
        "resource_table/resource_empty.html",
        "<!DOCTYPE html><html><body><table><tr><td>No magnets</td></tr></table></body></html>\n",
    )
    docs.append(
        {
            "name": "resource_empty",
            "type": "resource_table",
            "path": "resource_table/resource_empty.html",
            "sha256": digest,
            "source_url": "https://www.javbus.com/ajax/empty",
            "content_code": "TST-006",
        }
    )

    digest = write(
        "resource_table/resource_invalid_magnet.html",
        """<!DOCTYPE html><html><body><table>
<tr><td><a href="magnet:?xt=urn:btih:ZZZZ">bad</a></td><td>1GB</td><td>2026-07-01</td></tr>
</table></body></html>
""",
    )
    docs.append(
        {
            "name": "resource_invalid_magnet",
            "type": "other",
            "path": "resource_table/resource_invalid_magnet.html",
            "sha256": digest,
            "source_url": "https://www.javbus.com/ajax/bad",
        }
    )

    expected = {"candidates": 4, "codes": ["TST-001", "TST-002", "TST-003", "TST-004"]}
    (ROOT / "expected").mkdir(parents=True, exist_ok=True)
    (ROOT / "expected/listing_page_1.json").write_text(
        json.dumps(expected, indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "fixture_schema": "1.0",
        "source_id": "javbus",
        "captured_at": "2026-07-24T00:00:00Z",
        "sanitized": True,
        "documents": docs,
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("docs", len(docs))
    print("details", sum(1 for d in docs if d["type"] == "detail"))
    print("resources", sum(1 for d in docs if d["type"] == "resource_table"))


if __name__ == "__main__":
    main()
