#!/usr/bin/env python3
"""
根据深度验证报告更新 sources.json
"""
import sys
import os
import json
import urllib.parse
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
SOURCES_FILE = os.path.join(ROOT_DIR, 'sources.json')
REPORT_FILE = os.path.join(ROOT_DIR, 'deep_verify_report.json')

with open(REPORT_FILE, 'r', encoding='utf-8') as f:
    report = json.load(f)

with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 从报告构建 name→verdict 映射
verdicts = {}
for r in report:
    verdicts[r['name']] = r

# 判定逻辑
def get_new_status(name, r):
    if not r:
        return None  # 不在报告中的不修改

    v = r['verdict']

    # → green: 搜索成功
    if v == 'WORKING':
        return ('green', 'ok', 'deep_verify_working')

    # Contract: no red. Dead/parked/empty are represented as gray/expired (plus diagnosis).
    if v in ('DEAD', 'PARKED', 'EMPTY'):
        return ('gray', 'expired', f'deep_verify_{v.lower()}')

    # Redirect to irrelevant site: keep yellow unless confirmed expired/empty.
    if v == 'REDIRECT':
        final = r.get('final_url', '')
        # 跳转到 cloaked.com (隐私服务) = 非磁力
        if 'cloaked.com' in final:
            return ('yellow', 'parsing_failed', 'deep_verify_redirect_irrelevant')
        # 跳转到 dayunav.top (导航站) = 非磁力源本身
        if 'dayunav.top' in final:
            return ('yellow', 'parsing_failed', 'deep_verify_redirect_navigation')
        # 跳转到自己但无内容 = 空壳
        if r['page_size'] < 1000:
            return ('gray', 'expired', 'deep_verify_redirect_empty')
        return None  # 保持不变

    # Non-magnet content: keep as yellow/parsing_failed with diagnosis
    if name == 'mr.sofan1.cc':
        # 区块链资源站
        return ('yellow', 'parsing_failed', 'deep_verify_non_magnet_content')
    if name == 'pirateproxy.tube':
        # 代理列表站，不是搜索源
        return ('yellow', 'parsing_failed', 'deep_verify_proxy_list_not_source')

    # → yellow: REDIRECT_MAGNET, PROMISING, NEEDS_PATH, UNKNOWN
    return None  # 保持不变


changes = []
for rs in data['rulesets']:
    for rule in rs['rules']:
        name = rule['site']['name']
        r = verdicts.get(name)
        decision = get_new_status(name, r)
        if not decision:
            continue
        new_status, new_detail, diag_tag = decision
        if rule['health']['status'] != new_status or rule['health'].get('status_detail') != new_detail:
            old = rule['health']['status']
            rule['health']['status'] = new_status
            rule['health']['status_detail'] = new_detail
            rule['health']['last_checked_at'] = datetime.now(timezone.utc).isoformat()

            # 更新诊断信息
            if r:
                rule['health']['diagnosis'] = r.get('reason', diag_tag)
                sr = r.get('search_result')
                if new_status == 'green' and sr:
                    rule['health']['diagnosis'] = f"搜索验证通过: {sr.get('magnets')} magnets (path={sr.get('path')} q={sr.get('query')})"
                if diag_tag:
                    rule['health']['note'] = (rule['health'].get('note', '') + '; ' + diag_tag).strip('; ')

            changes.append(f'{name}: {old} → {new_status}/{new_detail} ({r["verdict"] if r else "?"})')

# 保存
with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f'更新了 {len(changes)} 个源:')
for c in changes:
    print(f'  {c}')

# 统计
from collections import Counter
statuses = Counter()
for rs in data['rulesets']:
    for rule in rs['rules']:
        statuses[rule['health']['status']] += 1

print(f'\n当前状态统计:')
for s, c in statuses.most_common():
    print(f'  {s}: {c}')
