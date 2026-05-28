#!/usr/bin/env python3
"""Final round: probe newly discovered candidates."""
import requests, re, urllib3, time
from bs4 import BeautifulSoup
urllib3.disable_warnings()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

TARGETS = [
    # From ahhhhfs.com
    ("cililianjie.cc", ["/search?q=spider", "/search?keyword=spider"]),
    # From btmayi.cc nav — 磁力树
    ("cilishu.top", ["/search?keyword=spider", "/search?wd=spider"]),
    ("cilishu.com", ["/search?keyword=spider"]),
    # BT之家
    ("btbtt20.com", ["/search?keyword=spider"]),
    ("btbtt.me", ["/search?keyword=spider"]),
    # 迷客电影
    ("mkvdo.com", ["/search?keyword=spider"]),
    ("makebt.com", ["/search/spider"]),
    # GatherFind 
    ("gatherfind.com", ["/search?q=spider"]),
    # 学霸盘
    ("xuebaip.com", ["/search?keyword=spider"]),
    # Unblockit
    ("unblockit.how", [""]),
]


def probe(domain, paths):
    origin = f"https://{domain}"
    try:
        t0 = time.time()
        r = requests.get(origin, timeout=10, verify=False, headers=H, allow_redirects=True)
        dt = round(time.time() - t0, 2)
        if r.status_code != 200 or len(r.text) < 200:
            print(f"  x {domain:25s} status={r.status_code} len={len(r.text)}")
            return
    except Exception as e:
        print(f"  x {domain:25s} {str(e)[:50]}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.find("title")
    title_text = title.text.strip()[:50] if title else "N/A"
    print(f"  ~ {domain:25s} homepage OK  t={dt}s  title={title_text}")

    for path in paths:
        if not path:
            continue
        try:
            url = origin + path
            r2 = requests.get(url, timeout=10, verify=False, headers=H, allow_redirects=True)
            if r2.status_code != 200:
                continue

            soup2 = BeautifulSoup(r2.text, "html.parser")
            magnets = re.findall(r"magnet:\?xt=urn:btih:", r2.text)
            hashes = re.findall(r"(?<![a-fA-F0-9])[a-fA-F0-9]{40}(?![a-fA-F0-9])", r2.text)

            best_sel = ""
            best_n = 0
            for sel in ["li.item", "div.ssbox", "div.search-item", "div.sbar",
                         "div.media-body", "div.result-item", "div.item",
                         "div.layui-colla-item", "table tbody tr", "div.search-result"]:
                items = soup2.select(sel)
                if len(items) > best_n:
                    best_n = len(items)
                    best_sel = sel

            if best_n >= 3 or len(magnets) >= 3:
                first = soup2.select(best_sel)[0] if best_sel and best_n else None
                txt = first.get_text(strip=True)[:60] if first else ""
                print(f"    G {domain:25s} {path:30s} magnets={len(magnets)} "
                      f"sel={best_sel}({best_n}) '{txt}'")
                return
            elif len(r2.text) > 1000:
                body = soup2.find("body")
                btxt = body.get_text(strip=True)[:80] if body else ""
                print(f"    ? {domain:25s} {path:30s} len={len(r2.text)} "
                      f"magnets={len(magnets)} hashes={len(hashes)} '{btxt}'")
        except:
            pass


if __name__ == "__main__":
    print("Final probe round...\n")
    for domain, paths in TARGETS:
        probe(domain, paths)
