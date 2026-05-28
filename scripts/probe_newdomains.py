#!/usr/bin/env python3
"""Probe newly discovered domains for known brands."""
import requests, re, urllib3, time, base64
from bs4 import BeautifulSoup
urllib3.disable_warnings()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

QUERY = "spider"
Q_B64 = base64.b64encode(QUERY.encode()).decode()

TARGETS = [
    # 老王磁力 new domains
    ("laowanghv.top", "老王磁力", [
        f"/search?wd={Q_B64}", f"/search?keyword={QUERY}", f"/search?q={QUERY}"
    ]),
    # 磁力狗 new domains
    ("clg.im", "磁力狗", [
        f"/search?wd={Q_B64}", f"/search?keyword={QUERY}", f"/search?q={QUERY}"
    ]),
    ("clg.one", "磁力狗", [
        f"/search?wd={Q_B64}", f"/search?keyword={QUERY}"
    ]),
    ("ciligou.net", "磁力狗", [
        f"/search?wd={Q_B64}", f"/search?keyword={QUERY}"
    ]),
    # SkrBT new domain
    ("skrbtmx.top", "SkrBT", [
        f"/search?wd={Q_B64}", f"/search?keyword={QUERY}"
    ]),
    # 磁力柠檬 new domain
    ("lemonlx.top", "磁力柠檬", [
        f"/search?wd={Q_B64}", f"/search?keyword={QUERY}"
    ]),
    # BT1207 new domain
    ("bt1207mx.top", "BT1207", [
        f"/search?wd={Q_B64}", f"/search?keyword={QUERY}"
    ]),
    # BT哈哈 — trs.bthaha.buzz
    ("trs.bthaha.buzz", "BT哈哈", [
        f"/cn/search?keyword={QUERY}", f"/search?q={QUERY}"
    ]),
]


def probe(domain, brand, paths):
    origin = f"https://{domain}"
    try:
        t0 = time.time()
        r = requests.get(origin, timeout=10, verify=False, headers=H, allow_redirects=True)
        dt = round(time.time() - t0, 2)
    except Exception as e:
        print(f"  x {domain:25s} {brand:8s} {str(e)[:50]}")
        return

    if r.status_code != 200 or len(r.text) < 200:
        cf = "CF" if "cloudflare" in r.text.lower() or "just a moment" in r.text.lower() else ""
        print(f"  x {domain:25s} {brand:8s} status={r.status_code} len={len(r.text)} {cf}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.find("title")
    tt = title.text.strip()[:40] if title else "N/A"
    
    # Check if it's a release page
    if "地址发布" in r.text or "永久地址" in r.text or "最新地址" in r.text[:500]:
        # Extract real domains
        real = re.findall(r'(?:最新|永久|备用)\s*(?:地址|网址)\s*[:：]\s*([a-zA-Z0-9.-]+\.[a-z]{2,})', r.text)
        print(f"  R {domain:25s} {brand:8s} RELEASE PAGE  real={real[:3]}  t={dt}s")
        return
    
    print(f"  ~ {domain:25s} {brand:8s} homepage OK  t={dt}s  {tt}")

    for path in paths:
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
            for sel in ["div.ssbox", "div.search-item", "div.sbar", "div.media-body",
                         "div.layui-colla-item", "li.item", "div.result-item",
                         "table tbody tr", "div.item"]:
                items = soup2.select(sel)
                if len(items) > best_n:
                    best_n = len(items)
                    best_sel = sel

            if best_n >= 3 or len(magnets) >= 3:
                first_item = soup2.select(best_sel)[0] if best_sel else None
                txt = first_item.get_text(strip=True)[:60] if first_item else ""
                print(f"    G {domain:25s} {brand:8s} {path[:40]:40s} "
                      f"magnets={len(magnets)} sel={best_sel}({best_n})")
                print(f"      first: {txt}")
                return
            elif len(r2.text) > 1000 and r2.url.rstrip("/") != origin.rstrip("/"):
                body = soup2.find("body")
                btxt = body.get_text(strip=True)[:80] if body else ""
                # Check for SPA
                scripts = soup2.find_all("script")
                spa = " SPA" if len(scripts) > 5 and len(r2.text) < 5000 else ""
                print(f"    ? {domain:25s} {brand:8s} {path[:40]:40s} "
                      f"len={len(r2.text)} mag={len(magnets)}{spa}")
        except:
            pass
    

if __name__ == "__main__":
    print("Probing new domains for known brands...\n")
    for domain, brand, paths in TARGETS:
        probe(domain, brand, paths)
