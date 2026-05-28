#!/usr/bin/env python3
"""
Benchmark V1 vs V2 crawler on yellow sources.

For each yellow source, run both Healer (v1) and HealerV2 (v2), measure:
  - Outcome (status: ok/healed/waf/...)
  - Magnets found
  - Time taken
  - Method (http / browser / stealth_browser / ...)

Does NOT write sources.json — pure dry-run comparison.

Usage:
  python magnet/_bench_v1_vs_v2.py                    # all yellow, NO PROXY (国内环境)
  python magnet/_bench_v1_vs_v2.py --limit 10         # first 10
  python magnet/_bench_v1_vs_v2.py --limit 10 --skip-v1   # only v2 (faster)
  python magnet/_bench_v1_vs_v2.py --limit 5 --shuffle    # random sample
  python magnet/_bench_v1_vs_v2.py --limit 5 --proxy http://127.0.0.1:33210   # 走 VPN
  python magnet/_bench_v1_vs_v2.py --limit 5 --tag noproxy --shuffle --seed 7
  python magnet/_bench_v1_vs_v2.py --limit 5 --tag tw --proxy http://127.0.0.1:33210 --shuffle --seed 7
  # 上面两跳同样 seed 同样 limit →可直接对比两份 report
"""

import sys
import os
import json
import time
import copy
import argparse
import random
import logging

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SOURCES_FILE = os.path.join(ROOT_DIR, 'sources.json')
REPORT_FILE_TPL = os.path.join(os.path.dirname(__file__), '_bench_v1_vs_v2_report{tag}.json')


def run_one(healer, rule_copy, label):
    """Run a single source through a healer; return result dict + timing."""
    t0 = time.time()
    try:
        result = healer.heal_and_retry(rule_copy)
    except Exception as e:
        result = {'status': 'crashed', 'error': str(e)[:200]}
    elapsed = time.time() - t0
    result['_elapsed'] = round(elapsed, 2)
    result['_label'] = label
    return result


def categorize(status):
    if status == 'ok':
        return 'OK'
    if status == 'healed':
        return 'HEALED'
    if status in ('404', 'expired', 'unreachable'):
        return 'DEAD'
    if status == 'waf':
        return 'WAF'
    if status == 'parsing_failed':
        return 'PARSE_FAIL'
    return 'OTHER'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=10, help='Number of yellow sources to test (0=all)')
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--shuffle', action='store_true')
    ap.add_argument('--skip-v1', action='store_true', help='Only run v2')
    ap.add_argument('--skip-v2', action='store_true', help='Only run v1')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--status', default='yellow', help='Source health status to test (yellow/green/...)')
    ap.add_argument('--proxy', default='', help='HTTP proxy URL, e.g. http://127.0.0.1:33210 (default: NO proxy = realistic CN env)')
    ap.add_argument('--tag', default='', help='Suffix for report filename, e.g. "noproxy" or "tw"')
    args = ap.parse_args()

    # ---- proxy setup (env-based; affects requests + curl_cffi/Scrapling Fetcher) ----
    if args.proxy:
        os.environ['HTTP_PROXY'] = args.proxy
        os.environ['HTTPS_PROXY'] = args.proxy
        os.environ['http_proxy'] = args.proxy
        os.environ['https_proxy'] = args.proxy
        # 不要让 localhost / sources.json 本地 走代理
        os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
        log.info(f'\u26a1 PROXY ON: {args.proxy}')
    else:
        # 明确清理，避免从 shell 继承
        for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
            os.environ.pop(k, None)
        log.info('\U0001f1e8\U0001f1f3 NO PROXY (CN environment baseline)')

    from crawler.healer import Healer
    from crawler_v2.healer import HealerV2

    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    yellow_rules = []
    for rs in data.get('rulesets', []):
        for r in rs.get('rules', []):
            if r.get('health', {}).get('status') == args.status:
                yellow_rules.append(r)

    if args.shuffle:
        random.seed(args.seed)
        random.shuffle(yellow_rules)

    if args.limit > 0:
        yellow_rules = yellow_rules[args.start:args.start + args.limit]
    elif args.start > 0:
        yellow_rules = yellow_rules[args.start:]

    log.info('=' * 70)
    log.info(f'  Bench V1 vs V2 — {len(yellow_rules)} yellow sources')
    log.info('=' * 70)

    v1_healer = Healer() if not args.skip_v1 else None
    v2_healer = HealerV2() if not args.skip_v2 else None

    rows = []
    for idx, rule in enumerate(yellow_rules):
        origin = rule['site']['origin']
        brand = rule.get('site', {}).get('brand', '') or rule.get('site', {}).get('name', '')
        log.info(f'\n[{idx + 1}/{len(yellow_rules)}] {brand} ({origin})')

        row = {
            'idx': idx + 1,
            'origin': origin,
            'brand': brand,
            'id': rule.get('id', ''),
            'v1': None,
            'v2': None,
        }

        if v1_healer:
            log.info('  -- V1 (requests + Selenium) --')
            r1 = run_one(v1_healer, copy.deepcopy(rule), 'v1')
            log.info(f'  V1: {r1.get("status")} magnets={r1.get("magnets_found", 0)} '
                     f'method={r1.get("method", "-")} time={r1["_elapsed"]}s')
            row['v1'] = r1

        if v2_healer:
            log.info('  -- V2 (Scrapling Fetcher + StealthyFetcher) --')
            r2 = run_one(v2_healer, copy.deepcopy(rule), 'v2')
            log.info(f'  V2: {r2.get("status")} magnets={r2.get("magnets_found", 0)} '
                     f'method={r2.get("method", "-")} time={r2["_elapsed"]}s')
            row['v2'] = r2

        # Verdict for this source
        v1_ok = row['v1'] and row['v1'].get('status') in ('ok', 'healed')
        v2_ok = row['v2'] and row['v2'].get('status') in ('ok', 'healed')
        if v1_ok and v2_ok:
            verdict = 'BOTH_OK'
        elif v2_ok and not v1_ok:
            verdict = 'V2_WINS'
        elif v1_ok and not v2_ok:
            verdict = 'V1_WINS'
        elif row['v1'] and row['v2']:
            verdict = 'BOTH_FAIL'
        else:
            verdict = 'PARTIAL'
        row['verdict'] = verdict
        log.info(f'  >>> verdict: {verdict}')
        rows.append(row)

    # ── Summary ──
    log.info('\n' + '=' * 70)
    log.info('  Summary')
    log.info('=' * 70)

    def tally(label, results):
        cats = {}
        total_time = 0
        for r in results:
            if r is None:
                continue
            cats[categorize(r.get('status'))] = cats.get(categorize(r.get('status')), 0) + 1
            total_time += r.get('_elapsed', 0)
        return cats, total_time

    v1_results = [r['v1'] for r in rows if r['v1']]
    v2_results = [r['v2'] for r in rows if r['v2']]

    if v1_results:
        cats, total = tally('V1', v1_results)
        log.info(f'V1: total_time={total:.1f}s  {cats}')
    if v2_results:
        cats, total = tally('V2', v2_results)
        log.info(f'V2: total_time={total:.1f}s  {cats}')

    verdicts = {}
    for r in rows:
        verdicts[r['verdict']] = verdicts.get(r['verdict'], 0) + 1
    log.info(f'Verdicts: {verdicts}')

    v2_wins = verdicts.get('V2_WINS', 0)
    v1_wins = verdicts.get('V1_WINS', 0)
    log.info('')
    if v2_wins > v1_wins:
        log.info(f'  >>> V2 rescued {v2_wins} sources V1 missed (vs {v1_wins} V1-only wins)')
    elif v1_wins > v2_wins:
        log.info(f'  >>> V1 still better on {v1_wins} sources (V2-only wins: {v2_wins})')
    else:
        log.info(f'  >>> Tie: {v1_wins} each')

    # ── Save report ──
    tag_suffix = ('_' + args.tag) if args.tag else ''
    report_file = REPORT_FILE_TPL.format(tag=tag_suffix)
    report = {
        'total': len(rows),
        'verdicts': verdicts,
        'proxy': args.proxy or None,
        'rows': rows,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f'Report saved: {report_file}')


if __name__ == '__main__':
    main()
