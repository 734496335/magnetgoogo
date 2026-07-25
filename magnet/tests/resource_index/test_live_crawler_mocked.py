"""Mocked live crawler unit tests (no real network)."""

from __future__ import annotations

from dataclasses import dataclass

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.javbus.live_crawler import JavBusLiveCrawler


@dataclass
class _FakeResp:
    url: str
    status_code: int
    text: str
    headers: dict


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._cookies: dict[str, str] = {}

    def cookies_snapshot(self) -> dict[str, str]:
        return dict(self._cookies)

    def clear_cookies(self) -> None:
        self._cookies.clear()

    def _body_for(self, url: str) -> str:
        u = url.lower()
        if "uncledatools" in u:
            return AJAX_HTML
        if "/search/" in u:
            return LISTING_HTML
        if u.rstrip("/").endswith("tst-999") or "/tst-999" in u:
            return DETAIL_HTML
        # home / session
        return LISTING_HTML

    def get(self, url: str, **kwargs):
        self.calls.append(f"GET {url}")
        return _FakeResp(url=url, status_code=200, text=self._body_for(url), headers={})

    def post(self, url: str, **kwargs):
        self.calls.append(f"POST {url}")
        return _FakeResp(url=url, status_code=200, text=LISTING_HTML, headers={})

    def request(self, method: str, url: str, **kwargs):
        if method.upper() == "POST":
            return self.post(url, **kwargs)
        return self.get(url, **kwargs)


LISTING_HTML = """
<html><body>
<a class="movie-box" href="https://www.javbus.com/TST-999">
  <div class="photo-info"><span>TST-999 Fixture</span><date>TST-999</date></div>
</a>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<script>var gid = 42; var uc = 0;</script>
<h3>TST-999 Fixture Live</h3>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <span style="color:#CC0000;">TST-999</span></p>
  <p><span class="header">發行日期:</span> 2026-07-01</p>
  <p><span class="header">長度:</span> 100分鐘</p>
  <p><span class="header">製作商:</span> <a href="/studio/x">Live Maker</a></p>
  <p><span class="header">類別:</span> <span class="genre"><a href="/genre/a">TagA</a></span></p>
  <p><span class="header">演員:</span> <span class="genre"><a href="/star/p1">Person A</a></span></p>
</div>
<a class="bigImage" href="https://fixtures.invalid/c.jpg"><img src="https://fixtures.invalid/c_s.jpg"></a>
</body></html>
"""

AJAX_HTML = """
<html><body><table>
<tr>
  <td><a href="magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&dn=TST-999">TST-999 HD</a></td>
  <td>1.2GB</td>
  <td>2026-07-02</td>
</tr>
</table></body></html>
"""


def test_mocked_crawl_query_to_bundle():
    client = _FakeClient()
    policy = LiveFetchPolicy(
        enabled=True,
        acknowledged=True,
        max_pages=20,
        request_delay_seconds=0.5,
    )
    crawler = JavBusLiveCrawler(policy=policy, client=client)  # type: ignore[arg-type]
    crawler.client = client  # type: ignore[assignment]
    crawler.fetcher.client = client  # type: ignore[assignment]

    items = crawler.crawl_query("TST-999", limit=1)
    assert len(items) == 1
    item = items[0]
    assert item.error_code is None, (item.error_code, item.error_message)
    assert item.bundle is not None
    assert item.bundle.content.content_code == "TST-999"
    assert len(item.bundle.resources) == 1
    assert item.bundle.resources[0].info_hash == "a" * 40
