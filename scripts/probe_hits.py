#!/usr/bin/env python3
"""Deep probe the HITS from release page discovery."""
import requests, re, urllib3, base64
from bs4 import BeautifulSoup
urllib3.disable_warnings()

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
Q = "spider"
Q_B64 = base64.b64encode(Q.encode()).decode()


def deep_probe(label, domain, extra_paths=None):
    print(f"\n{'='*60}")
    print(f"  {label}: {domain}")
    print(f"{'='*60}")
    origin = f"https://{domain}"

    # Homepage
    try:
        r = requests.get(origin, timeout=10, verify=False, headers=H, allow_redirects=True)
        print(f"  Homepage: {r.status_code} len={len(r.text)} url={r.url[:60]}")
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("title")
        print(f"  Title: {title.text.strip()[:60] if title else 'N/A'}")

        # Forms
        for form in soup.find_all("form"):
            action = form.get("action", "")
            method = form.get("method", "GET")
            inputs = [(inp.get("name",""), inp.get("type","text")) for inp in form.find_all("input") if inp.get("name")]
            print(f"  Form: action={action} method={method} inputs={inputs}")
    except Exception as e:
        print(f"  ERR homepage: {str(e)[:60]}")
        return

    # Try searches
    paths = [
        f"/search?q={Q}", f"/search?keyword={Q}",
        f"/search?word={Q_B64}", f"/search?wd={Q_B64}",
        f"/search/{Q}", f"/search-{Q}-0-0-1.html",
    ]
    if extra_paths:
        paths = extra_paths + paths

    for path in paths:
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
                         "div.result-item", "div.row", "div.data-list"]:
                n = len(soup2.select(sel))
                if n > best_n:
                    best_n = n
                    best_sel = sel

            # Detail links
            detail_links = []
            for a in soup2.find_all("a", href=True):
                href = a["href"]
                if any(p in href for p in ["/information/", "/magnet/", "/detail/",
                                            "/doc/", "/seed/", "/hash/"]):
                    if href not in detail_links:
                        detail_links.append(href)

            status = "HIT" if (best_n >= 3 or len(magnets) >= 1) else "miss"
            print(f"  [{status}] {path[:50]:50s} len={len(r2.text)} mag={len(magnets)} "
                  f"hash={len(hashes)} sel={best_sel}({best_n})")
            if detail_links:
                print(f"    detail links: {detail_links[:3]}")

            if status == "HIT":
                # Check first detail page
                if detail_links:
                    dlink = detail_links[0]
                    if dlink.startswith("/"):
                        dlink = origin + dlink
                    try:
                        r3 = requests.get(dlink, timeout=10, verify=False, headers=H)
                        dmag = re.findall(r"magnet:\?xt=urn:btih:[a-fA-F0-9]+", r3.text)
                        print(f"    detail page: {r3.status_code} len={len(r3.text)} magnets={len(dmag)}")
                        if dmag:
                            print(f"    magnet: {dmag[0][:70]}")
                    except:
                        pass
                break
        except:
            pass

    # Also try POST
    for data_key in ["word", "keyword", "q", "wd"]:
        try:
            val = Q_B64 if data_key in ("word", "wd") else Q
            r4 = requests.post(origin + "/", data={data_key: val}, timeout=10,
                               verify=False, headers=H, allow_redirects=True)
            if r4.status_code == 200 and len(r4.text) > 2000 and r4.url != origin + "/":
                print(f"  [POST {data_key}={val[:10]}] → {r4.url[:60]} len={len(r4.text)}")
        except:
            pass


# === TARGETS ===
# Phase 1 hits
deep_probe("磁力狗备用域名 ciligou.app", "ciligou.app")
deep_probe("ØMagnet 0mag.biz", "0mag.biz")
deep_probe("BT蚂蚁 1230150.xyz", "1230150.xyz")
deep_probe("BT蚂蚁 1230151.xyz", "1230151.xyz")
deep_probe("巴士资源站 bs5.org", "bs5.org")
deep_probe("磁力帝 1122137.xyz", "1122137.xyz")
deep_probe("磁力帝 1122138.xyz", "1122138.xyz")
deep_probe("磁力帝 cld123.com", "cld123.com")
deep_probe("磁力帝 cldcld.cc", "cldcld.cc")
deep_probe("搜番 dobt.top", "dobt.top")
deep_probe("磁力多 duo6.top", "duo6.top")

# Navigation hits
deep_probe("磁力狐发布页 btfox.cyou", "btfox.cyou")
deep_probe("BT哈哈 bthaha.top", "bthaha.top")
deep_probe("BT樱桃 btcherries.xyz", "btcherries.xyz")
deep_probe("磁力帝新域名 529952.xyz", "529952.xyz")
deep_probe("2048bt.top", "2048bt.top")
