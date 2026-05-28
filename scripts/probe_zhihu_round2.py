#!/usr/bin/env python3
"""Probe new brands discovered from Zhihu/go2think searches."""
import requests, re, urllib3, time, base64
from bs4 import BeautifulSoup
urllib3.disable_warnings()

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
Q = "spider"
Q_B64 = base64.b64encode(Q.encode()).decode()

TARGETS = [
    # CiliMo — DHT search engine (English interface)
    ("cilimo.com", "CiliMo", ["/en/search?q={q}", "/search?q={q}", "/en/search?keyword={q}"]),
    # ABCTorrents
    ("abctorrents.litxdh.com", "ABCTorrents", ["/search?q={q}", "/search?keyword={q}"]),
    # BTSearch.love
    ("btsearch.love", "BTSearch", ["/en/search?q={q}", "/search?q={q}"]),
    # 吴签磁力 — multiple domains
    ("wuqianso.top", "吴签磁力", ["/search?keyword={q}", "/search?wd={b64}", "/search?q={q}"]),
    ("wuqianci.top", "吴签磁力", ["/search?keyword={q}", "/search?wd={b64}"]),
    ("wuqianox.top", "吴签磁力", ["/search?keyword={q}", "/search?wd={b64}"]),
    # 磁力熊
    ("cilixiong.org", "磁力熊", ["/search?keyword={q}", "/search?q={q}", "/search?wd={b64}"]),
    ("cilixiong.com", "磁力熊", ["/search?keyword={q}", "/search?q={q}"]),
    # 磁力星球
    ("so2.xingqiu.icu", "磁力星球", ["/search?keyword={q}", "/search?q={q}", "/search?wd={b64}"]),
    ("so5.xingqiu.icu", "磁力星球", ["/search?keyword={q}", "/search?q={q}"]),
    # 超人搜索
    ("chaorenso.info", "超人搜索", ["/search?keyword={q}", "/search?q={q}"]),
    # 爱恋动漫/KissSub
    ("kisssub.org", "爱恋动漫", ["/search?keyword={q}", "/search.php?keyword={q}", "/search?q={q}"]),
    # iDope
    ("idope.se", "iDope", ["/torrent-list/{q}/", "/search/{q}", "/search?q={q}"]),
    # 噜噜糖
    ("lulutang.com", "噜噜糖", ["/search?keyword={q}", "/search?q={q}"]),
    # 吴签发布页 — extract real domains
    ("sowuqian.top", "吴签发布页", []),
    ("wuqianbt.com", "吴签发布页", []),
]


def probe(domain, brand, paths):
    origin = f"https://{domain}"
    try:
        t0 = time.time()
        r = requests.get(origin, timeout=10, verify=False, headers=H, allow_redirects=True)
        dt = round(time.time() - t0, 2)
    except Exception as e:
        print(f"  x {brand:12s} {domain:30s} {str(e)[:50]}")
        return

    if r.status_code != 200 or len(r.text) < 200:
        cf = " CF" if "cloudflare" in r.text.lower() or "just a moment" in r.text.lower() else ""
        print(f"  x {brand:12s} {domain:30s} status={r.status_code} len={len(r.text)}{cf}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.find("title")
    tt = title.text.strip()[:40] if title else "N/A"
    
    # Detect release/redirect pages
    if r.url.replace("https://","").replace("http://","").split("/")[0] != domain:
        real = r.url.replace("https://","").replace("http://","").split("/")[0]
        print(f"  R {brand:12s} {domain:30s} → {real} ({tt})")
        # Extract domains from page
        domain_re = re.compile(r'https?://([a-zA-Z0-9][\w.-]*\.[a-z]{2,})', re.I)
        found = set(m.group(1).lower() for m in domain_re.finditer(r.text))
        found = [d for d in found if d != domain and 'baidu' not in d and 'qq.com' not in d]
        if found:
            print(f"    domains found: {found[:5]}")
        return

    if "安全中心" in r.text or "地址发布" in r.text:
        domain_re = re.compile(r'https?://([a-zA-Z0-9][\w.-]*\.[a-z]{2,})', re.I)
        found = set(m.group(1).lower() for m in domain_re.finditer(r.text))
        found = [d for d in found if d != domain]
        print(f"  R {brand:12s} {domain:30s} RELEASE page. domains={found[:5]}")
        return

    print(f"  ~ {brand:12s} {domain:30s} OK  t={dt}s  {tt}")

    # Forms
    for form in soup.find_all("form"):
        action = form.get("action", "")
        inputs = [(inp.get("name",""), inp.get("type","text")) for inp in form.find_all("input") if inp.get("name")]
        if inputs:
            print(f"    form: action={action} inputs={inputs}")

    # Try searches
    for path_tmpl in paths:
        path = path_tmpl.replace("{q}", Q).replace("{b64}", Q_B64)
        try:
            url = origin + path
            r2 = requests.get(url, timeout=10, verify=False, headers=H, allow_redirects=True)
            if r2.status_code != 200:
                continue
            if len(r2.text) < 500:
                continue

            soup2 = BeautifulSoup(r2.text, "html.parser")
            magnets = re.findall(r"magnet:\?xt=urn:btih:", r2.text)
            hashes = re.findall(r"(?<![a-fA-F0-9])[a-fA-F0-9]{40}(?![a-fA-F0-9])", r2.text)

            best_sel, best_n = "", 0
            for sel in ["li.item", "div.ssbox", "div.search-item", "div.sbar",
                         "div.media-body", "div.Search_title_wrapper",
                         "div.layui-colla-item", "table tbody tr", "div.item",
                         "div.result-item", "div.data-list", "div.search-result",
                         "div.result", "tr.default", "div.card", "div.torrent-item"]:
                n = len(soup2.select(sel))
                if n > best_n:
                    best_n = n
                    best_sel = sel

            detail_links = []
            for a in soup2.find_all("a", href=True):
                href = a["href"]
                if any(p in href for p in ["/information/", "/magnet/", "/detail/",
                                            "/hash/", "/seed/", "/doc/", "/torrent/"]):
                    if href not in detail_links:
                        detail_links.append(href)

            if best_n >= 3 or len(magnets) >= 1:
                print(f"    🟢 {path[:45]:45s} mag={len(magnets)} hash={len(hashes)} sel={best_sel}({best_n})")
                if detail_links:
                    print(f"       detail: {detail_links[:2]}")
                # Check detail page
                if detail_links and len(magnets) == 0:
                    dl = detail_links[0]
                    if dl.startswith("/"):
                        dl = origin + dl
                    try:
                        r3 = requests.get(dl, timeout=10, verify=False, headers=H)
                        dmag = re.findall(r"magnet:\?xt=urn:btih:[a-fA-F0-9]+", r3.text)
                        print(f"       detail page: mag={len(dmag)}")
                        if dmag:
                            print(f"       {dmag[0][:60]}")
                    except:
                        pass
                return
            elif len(r2.text) > 2000:
                body = soup2.find("body")
                btxt = body.get_text(strip=True)[:60] if body else ""
                print(f"    ? {path[:45]:45s} len={len(r2.text)} mag={len(magnets)} '{btxt[:50]}'")
        except Exception as e:
            pass


if __name__ == "__main__":
    print("Probing new brands from Zhihu/web searches...\n")
    for domain, brand, paths in TARGETS:
        probe(domain, brand, paths)
