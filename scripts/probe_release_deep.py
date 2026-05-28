#!/usr/bin/env python3
"""
Deep-probe release pages and navigation sites to extract real backend domains.
For each page: fetch HTML → extract all linked domains → probe search capability.
"""
import requests, re, urllib3, time, base64, json
from urllib.parse import urlparse
from bs4 import BeautifulSoup
urllib3.disable_warnings()

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
QUERY = "spider"
Q_B64 = base64.b64encode(QUERY.encode()).decode()

# Known domains already in sources.json (skip these)
KNOWN_DOMAINS = {
    "clg54.top", "clg.im", "clg.one", "ciligou.net", "clgclg.com", "ciligougo.xyz",
    "cilisousuo.co", "cilisousuo.cc", "cilisousuo.net", "cililianjie.cc",
    "0cili.org", "0cili.com", "0cili.nl", "wuji.me",
    "skrbtso.top", "skrbtmx.top", "skrbtfb.top",
    "laowangso.top", "laowanghv.top", "laowangdizhi.net", "laowangzo.top", "laowangcili.top",
    "lemonuo.top", "lemonlx.top", "lemonfb.top",
    "bt1207so.top", "bt1207mx.top", "1207so.top",
    "btsow.pics", "btsow.com", "tellme.pw",
    "btmayi.cc", "btmayi.top", "btbtmayi.com",
    "btlm.cc", "btbtt20.com", "btbtt.me",
    "cache.foxs.top", "btfox.icu", "s83.foxso.top",
    "zzb01.top", "zzb04.top", "zzb05.top", "zzb06.top", "zzb07.top",
    "zhongziba.cc", "seed8.org",
    "cld140.buzz", "529072.xyz", "529073.xyz",
    "cilizhai.com", "cilizhai.net",
    "magnetcatcat.com", "clm50.top", "clm52.top", "clm58.top", "clm59.top",
    "sobt19.top", "sobt22.top", "sobt23.top", "sobt24.top",
    "cltt03.sbs",
    "ahhhhfs.com", "toolsdar.cn", "16map.com", "cilimiao.cn",
    "blog.jackeylea.com", "gatherfind.com", "torrentsites.com",
    # Social/CDN
    "xiaohongshu.com", "zhihu.com", "baidu.com", "google.com", "github.com",
    "bilibili.com", "douyin.com", "weibo.com", "qq.com",
    "pstatp.com", "fileg.top",
}

RELEASE_PAGES = [
    # New release pages to deep-probe
    ("磁力狗", "https://clg.im"),
    ("老王磁力", "https://laowangdizhi.net"),
    ("SkrBT", "https://skrbtfb.top"),
    ("磁力柠檬", "https://lemonfb.top"),
    ("BT1207", "https://1207so.top"),
    ("BT蚂蚁", "https://btbtmayi.com/"),
    ("磁力帝", "https://xn--tfrs1ysrv.xyz/"),
    ("磁力帝备用", "https://cilidi.cyou/"),
    ("磁力猫", "https://xn--vur557cbpe6y0c.lol/"),
    ("磁力天堂", "https://xn--tfrq9jjzak83g.com/"),
    ("52BT", "https://xn--i8sq8r6zst7c.com/"),
    ("BTSOW", "https://tellme.pw/btsow"),
    ("磁力爬", "https://btmirror.neocities.org/"),
    ("搜番", "https://goto.sofan.in/"),
]

NAV_SITES = [
    ("BT蚂蚁导航", "https://btmayi.cc/"),
    ("磁力天堂导航", "https://btlm.cc/"),
    ("磁力猫导航", "https://www.cilimiao.cn/"),
    ("16map排行", "https://16map.com/rankings/sites/cilisousuo"),
]


def extract_domains(html, base_url):
    """Extract all unique domains from HTML links and text."""
    soup = BeautifulSoup(html, "html.parser")
    domains = set()

    # From <a href>
    for a in soup.find_all("a", href=True):
        href = a["href"]
        try:
            if href.startswith("http"):
                d = urlparse(href).netloc.lower().lstrip("www.")
                if d:
                    domains.add(d)
        except:
            pass

    # From text (domain-like patterns)
    domain_re = re.compile(
        r"\b([a-zA-Z0-9][\w-]*\."
        r"(?:com|org|net|info|xyz|top|cc|me|io|co|site|club|sbs|buzz|pics|to|re|rs|lol|cyou|icu|one|im|app|pw)"
        r"(?:\.[a-z]{2})?)\b",
        re.IGNORECASE,
    )
    for m in domain_re.finditer(html):
        d = m.group(1).lower().lstrip("www.")
        domains.add(d)

    # Filter out known
    return sorted(d for d in domains if d not in KNOWN_DOMAINS and len(d) > 4)


def quick_search_probe(domain):
    """Quick probe if a domain has search capability."""
    origin = f"https://{domain}"
    try:
        r = requests.get(origin, timeout=8, verify=False, headers=H, allow_redirects=True)
        if r.status_code != 200 or len(r.text) < 200:
            return None
    except:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.find("title")
    tt = title.text.strip()[:40] if title else "N/A"

    # Skip if it's a safety center or release page
    if "安全中心" in r.text or "地址发布" in r.text:
        return {"domain": domain, "type": "release_page", "title": tt}

    # Check for search form
    forms = soup.find_all("form")
    has_search = False
    for form in forms:
        inputs = form.find_all("input")
        for inp in inputs:
            name = inp.get("name", "").lower()
            if name in ("q", "keyword", "wd", "word", "s", "search"):
                has_search = True

    # Try search
    search_paths = [
        f"/search?q={QUERY}", f"/search?keyword={QUERY}",
        f"/search?word={Q_B64}", f"/search?wd={Q_B64}",
        f"/search/{QUERY}",
    ]
    for path in search_paths:
        try:
            r2 = requests.get(origin + path, timeout=8, verify=False, headers=H)
            if r2.status_code != 200 or len(r2.text) < 1000:
                continue
            magnets = re.findall(r"magnet:\?xt=urn:btih:", r2.text)
            hashes = re.findall(r"(?<![a-fA-F0-9])[a-fA-F0-9]{40}(?![a-fA-F0-9])", r2.text)
            soup2 = BeautifulSoup(r2.text, "html.parser")
            
            best_sel, best_n = "", 0
            for sel in ["li.item", "div.ssbox", "div.search-item", "div.sbar",
                         "div.media-body", "div.Search_title_wrapper",
                         "div.layui-colla-item", "table tbody tr", "div.item"]:
                n = len(soup2.select(sel))
                if n > best_n:
                    best_n = n
                    best_sel = sel

            if best_n >= 3 or len(magnets) >= 1:
                return {
                    "domain": domain, "type": "SEARCH_ENGINE", "title": tt,
                    "path": path, "magnets": len(magnets), "hashes": len(hashes),
                    "selector": best_sel, "items": best_n,
                }
        except:
            pass

    if has_search:
        return {"domain": domain, "type": "has_search_form", "title": tt}

    return {"domain": domain, "type": "homepage_only", "title": tt}


def probe_page(label, url):
    """Fetch a release/nav page and extract new domains."""
    print(f"\n{'='*60}")
    print(f"  {label}: {url}")
    print(f"{'='*60}")
    try:
        r = requests.get(url, timeout=10, verify=False, headers=H, allow_redirects=True)
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}")
            return []
        final_url = r.url
        if final_url != url:
            print(f"  → Redirected to: {final_url}")
    except Exception as e:
        print(f"  ERR: {str(e)[:60]}")
        return []

    new_domains = extract_domains(r.text, url)
    if not new_domains:
        print(f"  No new domains found (len={len(r.text)})")
        return []

    print(f"  Found {len(new_domains)} new domains:")
    results = []
    for d in new_domains[:20]:  # Cap at 20
        info = quick_search_probe(d)
        if info:
            tag = info["type"]
            if tag == "SEARCH_ENGINE":
                print(f"    🟢 {d:30s} SEARCH! path={info['path']} mag={info['magnets']} sel={info['selector']}({info['items']})")
            elif tag == "has_search_form":
                print(f"    🟡 {d:30s} has search form. title={info['title']}")
            elif tag == "release_page":
                print(f"    📄 {d:30s} release/safety page. title={info['title']}")
            else:
                print(f"    ⚪ {d:30s} homepage only. title={info['title']}")
            results.append(info)
        else:
            print(f"    ❌ {d:30s} unreachable")
        time.sleep(0.3)

    return results


if __name__ == "__main__":
    print("Deep-probing release pages and navigation sites...\n")
    all_results = {}

    print("\n" + "=" * 70)
    print("  PHASE 1: RELEASE PAGES")
    print("=" * 70)
    for label, url in RELEASE_PAGES:
        results = probe_page(label, url)
        if results:
            all_results[label] = results

    print("\n" + "=" * 70)
    print("  PHASE 2: NAVIGATION SITES")
    print("=" * 70)
    for label, url in NAV_SITES:
        results = probe_page(label, url)
        if results:
            all_results[label] = results

    # Summary
    print("\n\n" + "=" * 70)
    print("  SUMMARY: Potential new search engines")
    print("=" * 70)
    found_any = False
    for label, results in all_results.items():
        engines = [r for r in results if r["type"] == "SEARCH_ENGINE"]
        forms = [r for r in results if r["type"] == "has_search_form"]
        if engines or forms:
            found_any = True
            print(f"\n  [{label}]")
            for e in engines:
                print(f"    🟢 {e['domain']} → {e['path']}  mag={e['magnets']} items={e['items']}")
            for f in forms:
                print(f"    🟡 {f['domain']} → has search form")

    if not found_any:
        print("\n  No new search engines discovered.")

    # Save
    with open("scripts/release_probe_report.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved to scripts/release_probe_report.json")
