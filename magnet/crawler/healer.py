import requests
import json
import os
import time
import copy
from bs4 import BeautifulSoup
from crawler.extractor import MagnetExtractor
from ai_parser.ai_parser import LocalHeuristicParser


class Healer:
    BAIT_REGISTRY = {
        'ANIME': ['One Piece', 'Naruto', 'Bleach', 'Solo Leveling', 'Dragon Ball'],
        'CHINESE': ['Inception', 'Avatar', 'Big Buck Bunny', 'The Dark Knight'],
        'TECH': ['Windows 11', 'Python', 'VS Code', 'Debian', 'Fedora'],
        'GENERAL': ['Inception', 'Interstellar', 'The Dark Knight', 'Dune', 'Avatar', 'Big Buck Bunny'],
        'DEFAULT': ['Inception', 'Interstellar', 'Big Buck Bunny']
    }

    def __init__(self):
        self.report_file = 'heal_report.json'
        self.timeout = 30
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

    def _get_category(self, url):
        url_lower = url.lower()
        if any(kw in url_lower for kw in ['anime', 'tosho', 'dmhy', 'nyaa', 'bangumi', 'anidex']):
            return 'ANIME'
        if any(kw in url_lower for kw in ['fitgirl', 'skidrow', 'repack']):
            return 'TECH'
        if any(kw in url_lower for kw in [
            'bt', 'cili', 'btdb', 'btso', 'btsow', 'verycd',
            'btcake', 'btfans', 'btbtt', 'limetorrent', 'kickass',
            'extratorrent', 'bitport', 'etree', 'bitlord'
        ]):
            return 'CHINESE'
        return 'GENERAL'

    def discover_new_domain(self, site_name):
        print(f"  [Plan] Seeking new domain for: {site_name}")
        return None

    def _detect_waf(self, resp):
        html_lower = resp.text.lower()
        status = resp.status_code
        waf_signatures = [
            'cloudflare', 'cf-browser-verification', 'cf_chl_opt',
            'ray id', 'challenge-platform', 'please wait',
            'checking your browser', 'ddos protection',
            'attention required', 'just a moment',
            'please complete the security check'
        ]
        if status in (403, 503):
            if any(sig in html_lower for sig in waf_signatures):
                return True
        if status == 200 and any(sig in html_lower for sig in waf_signatures[:4]):
            body_len = len(resp.text.strip())
            if body_len < 5000:
                return True
        return False

    def _detect_parking(self, html):
        html_lower = html.lower()
        parking_signatures = [
            'domain for sale', 'buy this domain', 'domainpark',
            'sedo.com', 'godaddy.com/parking', 'parking-creator',
            'this domain is for sale', 'make an offer',
            'domain is expired', 'domain has expired',
            'register4less', 'afternic', 'dan.com',
            'this domain name has been'
        ]
        return any(sig in html_lower for sig in parking_signatures)

    def heal_and_retry(self, source_config, query=None):
        url = source_config.get('url') or source_config.get('site', {}).get('origin')
        site_name = source_config.get('site', {}).get('name', 'Unknown')

        if not url:
            return {'status': 'error', 'error': 'missing origin url'}

        search_cfg = source_config.get('search', {})
        search_path = search_cfg.get('request_template') or source_config.get('search_path', '/search?q={query}')
        selectors = search_cfg.get('parse_metadata', {}).get('selectors') or source_config.get('selectors', {})

        category = self._get_category(url)
        baits = self.BAIT_REGISTRY.get(category, self.BAIT_REGISTRY['DEFAULT'])

        test_queries = [query] if query else baits

        html = None
        last_test_query = test_queries[0]
        last_status_code = None

        for test_query in test_queries:
            test_url = url.rstrip('/') + search_path.replace('{query}', test_query)
            try:
                resp = requests.get(test_url, timeout=self.timeout, headers=self.headers)
                last_status_code = resp.status_code
                last_test_query = test_query

                if resp.status_code == 404:
                    return {'status': '404', 'url': url, 'error': 'Page Not Found (404)', 'status_code': 404}

                if self._detect_waf(resp):
                    return {
                        'status': 'waf', 'url': url,
                        'error': f'WAF blocked (HTTP {resp.status_code})',
                        'status_code': resp.status_code
                    }

                if resp.status_code >= 500:
                    html = resp.text
                    continue

                if resp.status_code == 200:
                    html = resp.text

                    if self._detect_parking(html):
                        self.discover_new_domain(site_name)
                        return {
                            'status': 'expired', 'url': url,
                            'error': 'Domain expired/parking/for sale'
                        }

                    extractor = MagnetExtractor(source_config)
                    magnets = extractor.extract_magnets(html, base_url=url)

                    if magnets:
                        return {
                            'status': 'ok',
                            'url': url,
                            'magnets_found': len(magnets),
                            'sample': magnets[0],
                            'selectors': selectors,
                            'bait_used': test_query,
                            'method': 'http'
                        }

            except requests.exceptions.Timeout:
                return {'status': 'unreachable', 'url': url, 'error': 'Timeout (Network/GFW)'}
            except requests.exceptions.ConnectionError:
                return {'status': 'unreachable', 'url': url, 'error': 'DNS/Connection Failure'}
            except Exception as e:
                return {'status': 'error', 'url': url, 'error': f'fetch failed: {e}'}

            time.sleep(0.5)

        if not html:
            return {
                'status': 'unreachable', 'url': url,
                'error': f'All queries failed (last HTTP {last_status_code})'
            }

        local_parser = LocalHeuristicParser(url)
        local_parser._soup = BeautifulSoup(html, 'lxml')

        if local_parser._is_parking_page():
            self.discover_new_domain(site_name)
            return {'status': 'expired', 'url': url, 'error': 'Domain expired/parking'}

        new_rules = local_parser.parse(html)
        new_selectors = new_rules.get('selectors', {})

        if new_selectors.get('list_item'):
            healed_config = self._inject_selectors(source_config, new_selectors)
            healed_extractor = MagnetExtractor(healed_config)
            magnets = healed_extractor.extract_magnets(html, base_url=url)

            if magnets:
                return {
                    'status': 'healed',
                    'url': url,
                    'original_selectors': selectors,
                    'healed_selectors': new_selectors,
                    'magnets_found': len(magnets),
                    'sample': magnets[0],
                    'bait_used': last_test_query,
                    'method': 'http_heuristic'
                }

        print(f"  [V3] HTTP parsing gap for {url}, attempting Browser Fallback...")
        browser_html = local_parser.get_browser_dom(
            url.rstrip('/') + search_path.replace('{query}', last_test_query)
        )

        if browser_html:
            extractor = MagnetExtractor(source_config)
            magnets = extractor.extract_magnets(browser_html, base_url=url)

            if magnets:
                return {
                    'status': 'ok',
                    'url': url,
                    'magnets_found': len(magnets),
                    'sample': magnets[0],
                    'selectors': selectors,
                    'bait_used': last_test_query,
                    'method': 'browser'
                }

            local_parser._soup = BeautifulSoup(browser_html, 'lxml')
            new_rules = local_parser.parse(browser_html)
            new_selectors = new_rules.get('selectors', {})

            if new_selectors.get('list_item'):
                healed_config = self._inject_selectors(source_config, new_selectors)
                healed_extractor = MagnetExtractor(healed_config)
                magnets = healed_extractor.extract_magnets(browser_html, base_url=url)

                if magnets:
                    return {
                        'status': 'healed',
                        'url': url,
                        'original_selectors': selectors,
                        'healed_selectors': new_selectors,
                        'magnets_found': len(magnets),
                        'sample': magnets[0],
                        'bait_used': last_test_query,
                        'method': 'browser_heuristic'
                    }

        return {
            'status': 'parsing_failed',
            'url': url,
            'error': 'page accessible but parsing failed (http + browser)',
            'selectors_tried': selectors
        }

    def _inject_selectors(self, source_config, new_selectors):
        healed_config = copy.deepcopy(source_config)
        if 'search' not in healed_config:
            healed_config['search'] = {}
        if 'parse_metadata' not in healed_config['search']:
            healed_config['search']['parse_metadata'] = {}
        healed_config['search']['parse_metadata']['selectors'] = new_selectors
        return healed_config

    def heal_all_sources(self, rules):
        results = []
        for rule in rules:
            origin = rule.get('site', {}).get('origin', rule.get('url', 'Unknown'))
            print(f"Healing: {origin}")
            result = self.heal_and_retry(rule)
            results.append(result)
            status = result.get('status', 'unknown')
            magnets = result.get('magnets_found', 0)
            print(f"  -> {status}, magnets={magnets}")
        return results

    def save_report(self, results):
        report = {
            'total': len(results),
            'ok': sum(1 for r in results if r.get('status') == 'ok'),
            'healed': sum(1 for r in results if r.get('status') == 'healed'),
            'failed': sum(1 for r in results if r.get('status') == 'parsing_failed'),
            'expired': sum(1 for r in results if r.get('status') in ('expired', '404', 'unreachable')),
            'waf': sum(1 for r in results if r.get('status') == 'waf'),
            'results': results
        }
        try:
            with open(self.report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"Heal report saved to {self.report_file}")
        except Exception as e:
            print(f"Error saving heal report: {e}")
        return report
