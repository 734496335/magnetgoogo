#!/usr/bin/env python3
"""
Batch Source Probe — 批量探测候选磁力源
========================================
1) 已知域名直接探测
2) 仅品牌名的通过搜索引擎找域名
3) 多类目诱饵词验证
"""

import json, os, sys, re, time, hashlib, logging, urllib.parse
from datetime import datetime, timezone
from collections import OrderedDict

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(BASE_DIR, '..', 'sources.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
}

BAIT = {
    'movie':   ['Avengers Endgame', 'Inception', 'Interstellar'],
    'anime':   ['One Piece', 'Naruto', 'Dragon Ball Super'],
    'game':    ['The Witcher 3', 'Elden Ring', 'Cyberpunk 2077'],
    'xxx':     ['sdde', 'ABP', 'SSIS'],
    'music':   ['Taylor Swift', 'Adele'],
    'software':['Fedora', 'Windows 11'],
    'cn':      ['复仇者联盟', '三体', '战狼'],
    'general': ['Big Buck Bunny', 'Sintel'],
}

HASH_RE = re.compile(r'[0-9A-Fa-f]{40}')
MAGNET_RE = re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')

KNOWN_SOURCES = [
    {'brand': 'BTSOW', 'url': 'https://btsow.pics', 'search': '/search/{query}'},
    {'brand': 'MIX', 'url': 'https://magnetsearch.org', 'search': '/search?q={query}'},
    {'brand': 'ZHONGZISO', 'url': 'https://m.zhongzidi.com', 'search': '/search?q={query}'},
    {'brand': 'LIMETORRENTS', 'url': 'https://www.limetorrents.fun', 'search': '/search/all/{query}/'},
    {'brand': 'THEBAY', 'url': 'https://thepiratebay10.org', 'search': '/search.php?q={query}'},
    {'brand': 'SOLIDTORRENTS', 'url': 'https://solidtorrents.to', 'search': '/search?q={query}'},
    {'brand': 'NYAA', 'url': 'https://nyaa.si', 'search': '/?f=0&q={query}'},
    {'brand': 'TORRENTKITTY', 'url': 'https://www.torrentkitty.red', 'search': '/search/{query}/'},
    {'brand': 'RARBG', 'url': 'https://rargb.to', 'search': '/torrents.php?search={query}'},
    {'brand': 'YHG', 'url': 'https://yhg007.com', 'search': '/search?q={query}'},
    {'brand': 'OMAGNET11', 'url': 'https://0magnet.co', 'search': '/search?q={query}'},
]

BRAND_SEARCH = [
    '0magnet', '1337x', 'AcgRip', 'AniLibria', 'Anime-Time', 'AnimeTosho',
    'AniRena', 'Arab-Torrents', 'AudioBookBay', 'Bangumi', 'BitRu', 'BitSearch',
    'BlueRoms', 'BT4G', 'BTDigg', 'BTDirectory', 'BTSOW', 'CloudTorrents',
    'DonTorrent', 'EZTV', 'ExtraTorrent', 'FitGirlRepack', 'GamesTorrents',
    'Internet Archive', 'ISOHUNT', 'KAT', 'Libgen', 'LimeTorrents',
    'LinuxTracker', 'MagnetDL', 'MikanAni', 'MegaPeer', 'MoviesDVDR',
    'NoNameClub', 'Nyaa', 'OxTorrent', 'PC-Torrents', 'Pirateiro', 'RARBG',
    'RUTOR', 'RuTracker', 'SolidTorrents', 'Subsplease', 'TokyoToshokan',
    'Torlock', 'TorrentKitty', 'TorrentCSV', 'Torrentz2', 'Torrent9',
    'TorrentDownload', 'TorrentGalaxy', 'TPB', 'Uindex', 'Xfsub', 'Yihua',
    'YTS', 'Ext.to', 'GloTorrents', 'TorrentMac', 'Eoubl ibre',
]

EXISTING_DOMAINS = {
    'animetosho.org', 'torrentdownload.info', '6v520.com', 'seedhub.cc',
    'animetime.cc', 'btsow.com', 'btsow.pics', 'limetorrents.fun',
    'thepiratebay10.org', 'solidtorrents.to', 'nyaa.si', 'torrentkitty.red',
    'rargb.to', '0magnet.co', 'dummy-site.com', 'btso.cc', 'btdb.to',
    'verycd.com', 'extratorrent.ag', 'btfans.com', 'limetorrents.cc',
    'bitport.io', 'kickasstorrents.bz', 'btbtt12.com', 'btcake.com',
    'cilimao.com', 'legacy-site.pw', '6v520.com', 'seedhub.cc',
    'yhg007.com', 'magnetsearch.org', 'zhongzidi.com',
}

CATEGORY_MAP = {
    'BTSOW': 'general', 'MIX': 'general', 'ZHONGZISO': 'cn', 'LIMETORRENTS': 'general',
    'THEBAY': 'general', 'SOLIDTORRENTS': 'general', 'NYAA': 'anime', 'TORRENTKITTY': 'xxx',
    'RARBG': 'movie', 'YHG': 'cn', 'OMAGNET11': 'general',
    '0magnet': 'general', '1337x': 'general', 'AcgRip': 'anime', 'AniLibria': 'anime',
    'Anime-Time': 'anime', 'AnimeTosho': 'anime', 'AniRena': 'anime', 'Arab-Torrents': 'general',
    'AudioBookBay': 'general', 'Bangumi': 'anime', 'BitRu': 'general', 'BitSearch': 'general',
    'BlueRoms': 'game', 'BT4G': 'general', 'BTDigg': 'general', 'BTDirectory': 'general',
    'CloudTorrents': 'general', 'DonTorrent': 'general', 'EZTV': 'general',
    'ExtraTorrent': 'general', 'FitGirlRepack': 'game', 'GamesTorrents': 'game',
    'Internet Archive': 'general', 'ISOHUNT': 'general', 'KAT': 'general',
    'Libgen': 'general', 'LimeTorrents': 'general', 'LinuxTracker': 'software',
    'MagnetDL': 'general', 'MikanAni': 'anime', 'MegaPeer': 'general',
    'MoviesDVDR': 'movie', 'NoNameClub': 'general', 'Nyaa': 'anime',
    'OxTorrent': 'general', 'PC-Torrents': 'software', 'Pirateiro': 'general',
    'RARBG': 'movie', 'RUTOR': 'general', 'RuTracker': 'general',
    'SolidTorrents': 'general', 'Subsplease': 'anime', 'TokyoToshokan': 'anime',
    'Torlock': 'general', 'TorrentKitty': 'xxx', 'TorrentCSV': 'general',
    'Torrentz2': 'general', 'Torrent9': 'general', 'TorrentDownload': 'general',
    'TorrentGalaxy': 'general', 'TPB': 'general', 'Uindex': 'general',
    'Xfsub': 'anime', 'Yihua': 'cn', 'YTS': 'movie', 'GloTorrents': 'general',
    'TorrentMac': 'software', 'Eoubl ibre': 'general', 'Ext.to': 'general',
}


def normalize_domain(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        from urllib.parse import urlparse
        p = urlparse(url)
        d = p.netloc.lower()
        if d.startswith('www.'):
            d = d[4:]
        return d
    except:
        return ''


def extract_magnets(html, base_url=''):
    soup = BeautifulSoup(html, 'lxml')
    magnets = []
    seen = set()
    for a in soup.find_all('a', href=lambda h: h and h.startswith('magnet:')):
        href = a['href']
        m = MAGNET_RE.match(href)
        if m:
            h = re.search(r'btih:([0-9A-Fa-f]{32,40})', href, re.I)
            if h:
                hh = h.group(1).upper()
                if hh in seen:
                    continue
                seen.add(hh)
        title = ''
        parent = a.parent
        for _ in range(4):
            if parent:
                for ta in parent.find_all('a', href=True):
                    txt = ta.get_text(strip=True)
                    if txt and len(txt) > 3 and 'magnet:' not in ta['href']:
                        title = txt[:120]
                        break
                if title:
                    break
                parent = parent.parent
        if not title:
            title = a.get_text(strip=True)[:120]
        magnets.append({'title': title, 'magnet': href[:150], 'source': base_url})
    if not magnets:
        for a in soup.find_all('a', href=True):
            m = HASH_RE.search(a['href'])
            if m:
                hh = m.group(1).upper()
                if hh in seen:
                    continue
                seen.add(hh)
                title = a.get_text(strip=True)[:120]
                magnets.append({
                    'title': title,
                    'magnet': f'magnet:?xt=urn:btih:{hh}',
                    'source': base_url,
                })
    return magnets


def get_bait_for(brand):
    cat = CATEGORY_MAP.get(brand, 'general')
    words = BAIT.get(cat, BAIT['general'])
    return words[0]


def probe_source(src, timeout=8):
    url = src['url']
    search_tmpl = src.get('search', '/search?q={query}')
    brand = src.get('brand', normalize_domain(url))
    bait = src.get('bait') or get_bait_for(brand)
    results = {'brand': brand, 'url': url, 'status': 'unknown', 'magnets_found': 0, 'bait': bait}

    log.info(f"  Probing {brand}: {url} (bait: {bait})")

    # Step 1: homepage
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        results['http_status'] = resp.status_code
        results['final_url'] = resp.url
        if resp.status_code != 200:
            results['status'] = 'http_error'
            results['reason'] = f'HTTP {resp.status_code}'
            log.info(f"    FAIL: HTTP {resp.status_code}")
            return results
        results['html_len'] = len(resp.text)
    except requests.exceptions.Timeout:
        results['status'] = 'timeout'
        results['reason'] = 'connection timeout'
        log.info(f"    FAIL: timeout")
        return results
    except requests.exceptions.ConnectionError as e:
        results['status'] = 'connection_error'
        results['reason'] = str(e)[:80]
        log.info(f"    FAIL: connection error")
        return results
    except Exception as e:
        results['status'] = 'error'
        results['reason'] = str(e)[:80]
        log.info(f"    FAIL: {e}")
        return results

    homepage_html = resp.text

    # Step 2: search with bait
    search_paths = [search_tmpl]
    if '{query}' not in search_tmpl:
        search_paths = ['/search?q={query}', '/search/{query}', '/?q={query}', '/?s={query}']

    all_magnets = []
    working_path = None

    for sp in search_paths:
        test_url = url.rstrip('/') + '/' + sp.lstrip('/').replace('{query}', urllib.parse.quote(bait))
        if test_url.count('//') > 2:
            test_url = url.rstrip('/') + sp.replace('{query}', urllib.parse.quote(bait))
        try:
            resp = requests.get(test_url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        magnets = extract_magnets(resp.text, url)
        if magnets:
            all_magnets.extend(magnets)
            working_path = sp
            break

    # Step 2b: try different search paths if default didn't work
    if not all_magnets:
        alt_paths = [
            '/search?q={query}', '/search/{query}', '/?q={query}', '/?s={query}',
            '/search.php?q={query}', '/?f=0&q={query}', '/search/{query}/1/',
            '/torrents.php?search={query}', '/search/all/{query}/',
        ]
        for sp in alt_paths:
            if sp in search_paths:
                continue
            test_url = url.rstrip('/') + sp.replace('{query}', urllib.parse.quote(bait))
            try:
                resp = requests.get(test_url, timeout=timeout, headers=HEADERS, allow_redirects=True)
            except Exception:
                continue
            if resp.status_code != 200:
                continue
            magnets = extract_magnets(resp.text, url)
            if magnets:
                all_magnets.extend(magnets)
                working_path = sp
                break

    # Step 2c: try second bait word
    if not all_magnets:
        cat = CATEGORY_MAP.get(brand, 'general')
        baits = BAIT.get(cat, BAIT['general'])
        for alt_bait in baits[1:]:
            for sp in (search_paths[0:1] + ['/search?q={query}', '/search/{query}', '/?q={query}']):
                test_url = url.rstrip('/') + '/' + sp.lstrip('/').replace('{query}', urllib.parse.quote(alt_bait))
                try:
                    resp = requests.get(test_url, timeout=timeout, headers=HEADERS, allow_redirects=True)
                except Exception:
                    continue
                if resp.status_code != 200:
                    continue
                magnets = extract_magnets(resp.text, url)
                if magnets:
                    all_magnets.extend(magnets)
                    working_path = sp
                    bait = alt_bait
                    break
            if all_magnets:
                break

    # Step 2d: try a different category bait
    if not all_magnets:
        for cat_name, baits in [('movie', BAIT['movie']), ('anime', BAIT['anime']), ('software', BAIT['software'])]:
            for alt_bait in baits:
                for sp in ['/search?q={query}', '/search/{query}', '/?q={query}']:
                    test_url = url.rstrip('/') + sp.replace('{query}', urllib.parse.quote(alt_bait))
                    try:
                        resp = requests.get(test_url, timeout=timeout, headers=HEADERS, allow_redirects=True)
                    except Exception:
                        continue
                    if resp.status_code != 200:
                        continue
                    magnets = extract_magnets(resp.text, url)
                    if magnets:
                        all_magnets.extend(magnets)
                        working_path = sp
                        bait = alt_bait
                        break
                if all_magnets:
                    break
            if all_magnets:
                break

    if all_magnets:
        results['status'] = 'ok'
        results['magnets_found'] = len(all_magnets)
        results['sample_title'] = all_magnets[0].get('title', '')[:80]
        results['sample_magnet'] = all_magnets[0].get('magnet', '')[:80]
        results['working_path'] = working_path
        results['bait'] = bait
        log.info(f"    OK: {len(all_magnets)} magnets (path={working_path}, bait={bait})")
        log.info(f"      sample: {results['sample_title']}")
    else:
        results['status'] = 'no_magnets'
        results['reason'] = 'search returned no magnet links'
        log.info(f"    FAIL: no magnets found")

    return results


def search_brand_domain(brand):
    known_urls = {
        '1337x': ['https://1337x.to', 'https://1337x.st', 'https://x1337x.se', 'https://1337x.gd'],
        'AcgRip': ['https://acg.rip'],
        'AnimeTosho': ['https://animetosho.org'],
        'Nyaa': ['https://nyaa.si'],
        'LimeTorrents': ['https://limetorrents.fun', 'https://limetorrents.lol', 'https://limetorrents.pro'],
        'SolidTorrents': ['https://solidtorrents.to', 'https://solidtorrents.nl'],
        'RARBG': ['https://rargb.to', 'https://rarbg.to', 'https://rarbg.is'],
        'TPB': ['https://thepiratebay.org', 'https://thepiratebay10.org', 'https://tpb.party'],
        'YTS': ['https://yts.mx', 'https://yts.am'],
        'EZTV': ['https://eztv.re', 'https://eztv.io'],
        'ExtraTorrent': ['https://extratorrent.st', 'https://extratorrent.ag'],
        'MagnetDL': ['https://magnetdl.com', 'https://magnetdl.org'],
        'Subsplease': ['https://subsplease.org'],
        'KAT': ['https://kickasstorrents.to', 'https://katcr.co', 'https://kat.sx'],
        'TorrentDownload': ['https://www.torrentdownload.info', 'https://torrentdownload.info'],
        'TorrentGalaxy': ['https://torrentgalaxy.to', 'https://torrentgalaxy.mx'],
        'RuTracker': ['https://rutracker.org', 'https://rutracker.net'],
        'RUTOR': ['http://rutor.info', 'http://rutor.is'],
        'ISOHUNT': ['https://isohunt.to', 'https://isohunt.tv'],
        'BTDigg': ['https://btdigg.org'],
        'Torlock': ['https://torlock.com', 'https://torlock.info'],
        'TorrentKitty': ['https://www.torrentkitty.red', 'https://www.torrentkitty.net'],
        'BTSOW': ['https://btsow.pics', 'https://btsow.one', 'https://btso.cc'],
        'Torrentz2': ['https://torrentz2eu.org', 'https://torrentz2.is'],
        'Torrent9': ['https://torrent9.st', 'https://www.torrent9.nl'],
        'MikanAni': ['https://mikanani.me'],
        'AniRena': ['https://www.anirena.com'],
        'Anime-Time': ['https://animetime.cc', 'https://animetime.xyz'],
        'TokyoToshokan': ['https://www.tokyotosho.info'],
        'BitSearch': ['https://bitsearch.to'],
        'BT4G': ['https://bt4g.org', 'https://bt4g.pr0x.org'],
        'AniLibria': ['https://www.anilibria.tv'],
        'Libgen': ['https://libgen.is', 'https://libgen.li'],
        'Internet Archive': ['https://archive.org'],
        '0magnet': ['https://0magnet.co', 'https://0magnet.cc'],
        'OxTorrent': ['https://www.oxtorrent.co', 'https://oxtorrent.nz'],
        'Yihua': ['https://www.yhg007.com', 'https://yhg007.com'],
        'Xfsub': ['https://xfsub.com'],
        'MegaPeer': ['https://megapeer.com'],
        'Ext.to': ['https://ext.to'],
        'GloTorrents': ['https://glotorrents.pro', 'https://glodls.to'],
        'CloudTorrents': ['https://cloudtorrents.com'],
        'AudioBookBay': ['https://audiobookbay.is'],
        'AudioBookBay': ['https://audiobookbay.lu'],
        'DonTorrent': ['https://dontorrent.xxx', 'https://dontorrent.in'],
        'FitGirlRepack': ['https://fitgirl-repacks.site'],
        'GamesTorrents': ['https://www.gamestorrents.fm'],
        'LinuxTracker': ['https://linuxtracker.org'],
        'BlueRoms': ['https://blueroms.com'],
        'PC-Torrents': ['https://pc-torrents.com'],
        'Pirateiro': ['https://pirateiro.com'],
        'NoNameClub': ['https://nnmclub.to'],
        'MoviesDVDR': ['https://www.moviesdvdr.co'],
        'BTDirectory': ['https://btdirectory.org'],
        'Arab-Torrents': ['https://arab-torrents.com'],
        'TorrentOyunindir': ['https://www.torrentoyunindir.com'],
        'TorrentCSV': ['https://torrentcsv.com'],
        'Uindex': ['https://uindex.net'],
        'TorrentMac': ['https://www.torrentmac.net'],
        'Eoubl ibre': ['https://www.eoublicre.com'],
        'Bangumi': ['https://bangumi.moe'],
        'BitRu': ['https://bitru.org'],
    }

    if brand in known_urls:
        return known_urls[brand]
    return []


def main():
    log.info("=" * 70)
    log.info("  BATCH SOURCE PROBE v1")
    log.info("=" * 70)

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    existing = set()
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            existing.add(normalize_domain(r['site']['origin']))

    log.info(f"  Existing sources: {len(existing)}")

    # Phase 1: probe known URLs
    log.info("\n" + "=" * 70)
    log.info("  PHASE 1: Known URL Sources")
    log.info("=" * 70)

    all_sources = list(KNOWN_SOURCES)

    # Phase 2: brand name lookup
    log.info("\n" + "=" * 70)
    log.info("  PHASE 2: Brand Name Domain Lookup")
    log.info("=" * 70)

    for brand in BRAND_SEARCH:
        urls = search_brand_domain(brand)
        if urls:
            log.info(f"  {brand}: {len(urls)} known domains")
            for u in urls:
                d = normalize_domain(u)
                already = False
                for s in all_sources:
                    if normalize_domain(s['url']) == d:
                        already = True
                        break
                if not already and d not in existing:
                    all_sources.append({'brand': brand, 'url': u, 'search': '/search?q={query}'})
        else:
            log.info(f"  {brand}: no known domain, skipping")

    log.info(f"\n  Total sources to probe: {len(all_sources)}")

    # Phase 3: probe all
    log.info("\n" + "=" * 70)
    log.info("  PHASE 3: Probing All Sources")
    log.info("=" * 70)

    results = []
    for i, src in enumerate(all_sources):
        d = normalize_domain(src['url'])
        if d in existing:
            log.info(f"\n[{i+1}/{len(all_sources)}] {src.get('brand','')}: {d} - ALREADY EXISTS")
            continue

        log.info(f"\n[{i+1}/{len(all_sources)}] {src.get('brand','?')}: {src['url']}")
        r = probe_source(src)
        results.append(r)
        time.sleep(0.3)

    # Summary
    ok = [r for r in results if r['status'] == 'ok']
    fail = [r for r in results if r['status'] != 'ok']

    log.info("\n" + "=" * 70)
    log.info("  RESULTS")
    log.info("=" * 70)
    log.info(f"  Probed: {len(results)}")
    log.info(f"  WORKING: {len(ok)}")
    for r in ok:
        log.info(f"    + {r['brand']:20s} {r['url']:40s} {r['magnets_found']:3d} magnets (bait={r['bait']})")
        log.info(f"      path={r.get('working_path','')}  sample={r.get('sample_title','')[:60]}")
    log.info(f"  FAILED: {len(fail)}")
    for r in fail:
        log.info(f"    - {r['brand']:20s} {r['url']:40s} {r['status']}: {r.get('reason','')}")

    # Add working sources to sources.json
    if ok:
        ruleset = data['rulesets'][0] if data.get('rulesets') else {
            'ruleset_id': 'base', 'priority': 1, 'max_sources_per_search': 10, 'rules': []
        }
        added = 0
        for r in ok:
            d = normalize_domain(r['url'])
            if d in existing:
                continue
            existing.add(d)
            rule_id = hashlib.md5(r['url'].encode()).hexdigest()[:12]
            rule = {
                'id': rule_id,
                'site': {'name': d, 'origin': r['url'].rstrip('/')},
                'capabilities': {'supports_search': True, 'supports_detail': False},
                'search': {
                    'request_template': r.get('working_path', '/search?q={query}'),
                    'timeout_ms': 15000,
                    'retries': {'max_attempts': 3, 'backoff_ms': 1000},
                    'requires_waf_bypass': False,
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="magnet:"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date',
                        }
                    }
                },
                'quality': {'score': 70, 'tags': ['追新极客']},
                'health': {
                    'status': 'green',
                    'status_detail': 'ok',
                    'last_checked_at': datetime.now(timezone.utc).isoformat(),
                    'magnets_found': r['magnets_found'],
                    'sample_title': r.get('sample_title', ''),
                },
            }
            ruleset['rules'].append(rule)
            added += 1
            log.info(f"  Added to sources.json: {d}")

        data['meta']['total_rules'] = sum(len(rs.get('rules', [])) for rs in data.get('rulesets', []))
        data['generated_at'] = datetime.now(timezone.utc).isoformat()

        with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        log.info(f"\n  {added} new sources added. Total: {data['meta']['total_rules']}")

    log.info("=" * 70)


if __name__ == '__main__':
    main()
