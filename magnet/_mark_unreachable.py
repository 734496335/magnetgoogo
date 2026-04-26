import json
import sys
import logging
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message_s',
    handlers=[logging.FileHandler('run.log', encoding='utf-8', mode='a'), logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

SOURCES_FILE = r'D:\lpproduct\magnet\sources.json'

with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

err_domains = [
    'xunlei8.top', 'link.btapp.me', 'btdb.unblockit.li', '1000mag.xyz', 'u3c3.org',
    'movih.com', 'so.proxyit.ga', '7v22.com', 'bthook.club', 'sukebei.nyaa.si',
    'sobt4.vip', 'jukan.xyz', 'uuyter56der.xyz', 'km153.xyz', 'cixing.org',
    'tokyotosho.info', 'wx8811.icu', 'btmovi.icu', 'clmmdz.cyou', 'yingyin.org',
    'seventorrents.unblockit.li', 'ttbt.xyz', 'yhdm33.com', 'seed8.biz', 'berrl.com',
    'cilizhai.com', 'www.cilixingqiu.net', 'www.cilimao.lol', 'www.tiantangcili.net',
    'www.btfan.com', '911173.xyz',
]

now = datetime.now(timezone.utc).isoformat()
updated = 0

for rs in data.get('rulesets', []):
    for rule in rs.get('rules', []):
        origin = rule['site']['origin']
        domain = origin.split('://', 1)[-1].split('/', 1)[0].lower().removeprefix('www.')
        if domain in err_domains and rule['health']['status'] == 'yellow':
            rule['health']['status'] = 'gray'
            rule['health']['status_detail'] = 'unreachable'
            rule['health']['last_checked_at'] = now
            rule['health']['diagnosis'] = '首页探测超时/连接失败，标记不可达'
            updated += 1
            log.info(f'  gray/unreachable: {domain}')

data['generated_at'] = now
with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

green = sum(1 for rs in data['rulesets'] for r in rs['rules'] if r['health']['status'] == 'green')
yellow = sum(1 for rs in data['rulesets'] for r in rs['rules'] if r['health']['status'] == 'yellow')
gray = sum(1 for rs in data['rulesets'] for r in rs['rules'] if r['health']['status'] == 'gray')
log.info(f'标记 {updated} 个源为 gray/unreachable')
log.info(f'当前: green={green} yellow={yellow} gray={gray}')
