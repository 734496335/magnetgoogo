#!/usr/bin/env python3
"""
Brand to Domain Resolver — 品牌名批量找域名并验证
===================================================
从磁力站品牌名列表出发，通过搜索引擎找真实域名，逐个验证是否能提取磁力。
"""
import sys,os,re,json,time,hashlib,logging,urllib.parse
from datetime import datetime,timezone
from urllib.parse import urljoin,urlparse

sys.stdout.reconfigure(encoding='utf-8',errors='replace')
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',
    handlers=[logging.FileHandler('run.log',encoding='utf-8',mode='a'),logging.StreamHandler(sys.stdout)])
log=logging.getLogger(__name__)

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE=os.path.join(BASE_DIR,'..','sources.json')
HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HASH_RE=re.compile(r'\b[2-9A-Fa-f][0-9A-Fa-f]{39}\b')
MAGNET_RE=re.compile(r'magnet:\?xt=urn:btih:[0-9A-Fa-f]{32,40}')
BAIT_WORDS=['Big Buck Bunny','Inception','One Piece']

BRANDS=[
    {'brand':'SkrBT','queries':['SkrBT 磁力','SkrBT magnet search','skrbt 官网']},
    {'brand':'黑马磁力','queries':['黑马磁力 官网','黑马磁力 搜索']},
    {'brand':'磁力狗','queries':['磁力狗 官网 最新地址','ciligou']},
    {'brand':'SOBT','queries':['SOBT 磁力搜索','sobt torrent']},
    {'brand':'磁力猫','queries':['磁力猫 官网 最新地址','cilimao']},
    {'brand':'磁力柠檬','queries':['磁力柠檬 官网','cililemon']},
    {'brand':'吴签磁力','queries':['吴签磁力 官网','wuqian magnet']},
    {'brand':'老王磁力','queries':['老王磁力 官网','laowang magnet']},
    {'brand':'BT1207','queries':['BT1207 磁力','bt1207 magnet']},
    {'brand':'磁力龟','queries':['磁力龟 官网','ciligui']},
    {'brand':'无限磁力','queries':['无限磁力 官网','wuxian magnet']},
    {'brand':'btfox','queries':['btfox 磁力','btfox.icu','btfox magnet']},
    {'brand':'EZTV','queries':['eztv mirror proxy 最新','eztv.re','eztv.gold']},
    {'brand':'磁力熊猫','queries':['磁力熊猫 官网','cilixiongmao']},
    {'brand':'0Magnet','queries':['0magnet.co','omagnet 官网']},
    {'brand':'CiLiGeGe','queries':['ciligege 磁力','ciligege 官网']},
    {'brand':'种子吧','queries':['种子吧 磁力','zhongziba']},
]

KNOWN_DOMAINS={
    'SkrBT':['skrbt.com','skrbt.xyz','skrbt.top','skrbt.cc','skrbt.me','skrbt.fun'],
    '黑马磁力':['heimacili.com','heimacili.xyz','heimacili.top','heimacili.cc','heima.icu'],
    '磁力狗':['ciligou.art','clg2.clgapp1.xyz','ciligou.ee','ciligou.fun','ciligou.xyz','ciligou.cc'],
    'SOBT':['sobt.com','sobt.xyz','sobt.top','sobt.cc','sobt.fun'],
    '磁力猫':['cilimao.com','cilimao.one','cilimao.xyz','cilimao.fun','cilimao.cc','cili.cat'],
    '磁力柠檬':['cililemon.com','cililemon.xyz','cililemon.top','cililemon.cc'],
    '吴签磁力':['wuqiancili.com','wuqiancili.xyz','wuqiancili.top'],
    '老王磁力':['laowangcili.com','laowangcili.xyz','laowangcili.top','lw-cili.com'],
    'BT1207':['bt1207.com','bt1207.xyz','bt1207.top','bt1207.cc'],
    '磁力龟':['ciligui.com','ciligui.xyz','ciligui.top','ciligui.cc'],
    '无限磁力':['wuxiancili.com','wuxiancili.xyz','wuxiancili.top'],
    'btfox':['btfox.icu','btfox.xyz','btfox.top','btfox.cc','btfox.com'],
    'EZTV':['eztv.re','eztv.gold','eztv.io','eztv.tf'],
    '磁力熊猫':['cilixiongmao.com','cilixiongmao.xyz','cili.panda'],
    '0Magnet':['0magnet.co','0magnet.cc','0magnet.xyz'],
    'CiLiGeGe':['ciligege.com','ciligege.xyz','ciligege.top'],
    '种子吧':['zhongziba.com','zhongziba.xyz','zhongziba.top'],
}

NON_SEARCH={
    'bing.com','www.bing.com','cn.bing.com',
    'baidu.com','www.baidu.com','m.baidu.com',
    'sogou.com','www.sogou.com','so.com','www.so.com',
    'google.com','www.google.com','googleusercontent.com',
    'zhihu.com','www.zhihu.com','zhuanlan.zhihu.com',
    'weibo.com','www.weibo.com','tieba.baidu.com',
    'bilibili.com','www.bilibili.com','douban.com','www.douban.com',
    'youtube.com','www.youtube.com','youtu.be',
    'github.com','www.github.com','github.io',
    'wikipedia.org','www.wikipedia.org'
}


def normalize_domain(url):
    try:
        if not url.startswith(('http://','https://')): url='http://'+url
        p=urlparse(url);d=p.netloc.lower()
        if d.startswith('www.'): d=d[4:]
        return d
    except: return ''


def load_existing():
    with open(SOURCES_FILE,'r',encoding='utf-8') as f: data=json.load(f)
    existing=set()
    for rs in data.get('rulesets',[]):
        for r in rs.get('rules',[]):
            existing.add(normalize_domain(r['site']['origin']))
    return existing,data


def http_get(url,timeout=10):
    import requests
    try: return requests.get(url,timeout=timeout,headers=HEADERS,allow_redirects=True)
    except: return None


def extract_magnets(html,url=''):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'lxml')
    magnets,seen=[],set()
    for a in soup.find_all('a',href=lambda h:h and h.startswith('magnet:')):
        m=MAGNET_RE.match(a['href'])
        if m:
            ih=re.search(r'btih:([0-9A-Fa-f]{32,40})',a['href'],re.I)
            if ih:
                hh=ih.group(1).upper()
                if hh in seen: continue
                seen.add(hh)
        title=a.get_text(strip=True)[:80]
        magnets.append({'title':title,'magnet':a['href'][:150]})
    if not magnets:
        for a in soup.find_all('a',href=True):
            m=HASH_RE.search(a['href'])
            if m:
                hh=m.group(0).upper()
                if hh in seen: continue
                seen.add(hh)
                title=a.get_text(strip=True)[:80]
                magnets.append({'title':title,'magnet':f'magnet:?xt=urn:btih:{hh}'})
    if not magnets:
        for m in HASH_RE.finditer(soup.get_text()):
            hh=m.group(0).upper()
            if hh not in seen:
                seen.add(hh)
                magnets.append({'title':f'Hash {hh[:8]}...','magnet':f'magnet:?xt=urn:btih:{hh}'})
    return magnets


def search_bing(query,count=15):
    import requests
    url=f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={count}"
    try:
        resp=requests.get(url,timeout=12,headers={**HEADERS,'Accept-Language':'zh-CN,zh;q=0.9'})
        if resp and resp.status_code==200:
            from bs4 import BeautifulSoup
            s=BeautifulSoup(resp.text,'lxml')
            domains=[]
            for a in s.find_all('a',href=True):
                h=a['href']
                if not h.startswith('http'): continue
                d=normalize_domain(h)
                if d and d not in NON_SEARCH:
                    domains.append((d,h,a.get_text(strip=True)[:60]))
            return domains
    except: pass
    return []




BRAND_QUERY_MAP={item['brand']:item['queries'][:] for item in BRANDS}


def looks_like_magnet_title(title):
    tl=(title or '').lower()
    return any(kw in tl for kw in ['magnet','种子','磁力','bt','torrent','搜索','dht'])


def get_brand_queries(brand):
    return BRAND_QUERY_MAP.get(brand, [])[:]


def get_known_domains_for_brand(brand):
    return KNOWN_DOMAINS.get(brand, [])[:]


def guess_brand(name='', desc=''):
    haystack=' '.join([name or '', desc or '']).lower()
    if not haystack.strip():
        return ''
    for brand in BRAND_QUERY_MAP:
        if brand.lower() in haystack:
            return brand
    for brand, queries in BRAND_QUERY_MAP.items():
        for q in queries:
            token=(q or '').strip().lower()
            if len(token) >= 3 and token in haystack:
                return brand
    return ''


def probe_known_domains(brand, existing=None, timeout=5, sleep_s=0.2):
    existing=existing or set()
    out=[]
    for domain in get_known_domains_for_brand(brand):
        nd=normalize_domain(domain)
        if not nd or nd in existing:
            continue
        url=f'https://{domain}'
        resp=http_get(url,timeout=timeout)
        if resp and resp.status_code==200 and len(resp.text or '')>200:
            out.append({'domain':nd,'url':url,'brand':brand,'source':'known'})
        time.sleep(sleep_s)
    return out


def search_brand_domains(brand, existing=None, max_queries=2, count=15, sleep_s=0.8):
    existing=existing or set()
    out=[]
    seen=set()
    for query in get_brand_queries(brand)[:max_queries]:
        results=search_bing(query,count=count)
        for domain,url,title in results:
            if not domain or domain in existing or domain in seen:
                continue
            if not looks_like_magnet_title(title):
                continue
            seen.add(domain)
            out.append({'domain':domain,'url':url,'brand':brand,'source':f'bing:{query}','title':title})
        time.sleep(sleep_s)
    return out


def verify_source(url,domain):
    resp=http_get(url,timeout=10)
    if not resp or resp.status_code!=200: return None
    if len(resp.text)<300: return None

    for bait in BAIT_WORDS:
        for sp in [f'/search/{urllib.parse.quote(bait)}',f'/search?q={urllib.parse.quote(bait)}',
                    f'/?q={urllib.parse.quote(bait)}',f'/?s={urllib.parse.quote(bait)}',
                    f'/search?keyword={urllib.parse.quote(bait)}',f'/search?query={urllib.parse.quote(bait)}',
                    f'/search/{urllib.parse.quote(bait)}/1/',f'/s/{urllib.parse.quote(bait)}']:
            try:
                r2=http_get(url.rstrip('/')+sp,timeout=8)
                if r2 and r2.status_code==200 and len(r2.text)>200:
                    magnets=extract_magnets(r2.text,url)
                    if magnets:
                        return {'magnets':len(magnets),'path':sp,'bait':bait,'samples':magnets[:3]}
            except: pass
        time.sleep(0.2)

    lower=resp.text[:15000].lower()
    if any(kw in lower for kw in ['magnet:','torrent','种子','磁力','btih']):
        return {'magnets':0,'path':'','bait':'','samples':[],'has_kw':True}
    return None


def add_to_sources(verified):
    if not verified: return 0
    existing,data=load_existing()
    ruleset=data['rulesets'][0]
    added=0
    for v in verified:
        d=v['domain']
        if d in existing: continue
        existing.add(d)
        rule_id=hashlib.md5(v['url'].encode()).hexdigest()[:12]
        rule={
            'id':rule_id,
            'site':{'name':d,'origin':v['url'].rstrip('/'),'countries':['china']},
            'capabilities':{'supports_search':True,'supports_detail':False},
            'search':{
                'request_template':v.get('path','/search?q={query}'),
                'timeout_ms':15000,
                'retries':{'max_attempts':3,'backoff_ms':1000},
                'requires_waf_bypass':False,
                'requires_browser':v.get('requires_browser',False),
                'parse_metadata':{'selectors':{
                    'list_item':'div.item','title':'a[href^="magnet:"]',
                    'magnet':'a[href^="magnet:"]','size':'span.size','date':'span.date',
                }}
            },
            'quality':{'score':70,'tags':['追新极客']},
            'health':{
                'status':'green','status_detail':'ok',
                'last_checked_at':datetime.now(timezone.utc).isoformat(),
                'magnets_found':v.get('magnets',0),
                'sample_title':v.get('samples',[{}])[0].get('title','')[:80] if v.get('samples') else '',
            },
        }
        if v.get('brand'): rule['site']['brand']=v['brand']
        ruleset['rules'].append(rule)
        added+=1
        log.info(f"  Added: {d} ({v.get('magnets',0)} magnets)")
    data['meta']['total_rules']=sum(len(rs.get('rules',[])) for rs in data.get('rulesets',[]))
    data['generated_at']=datetime.now(timezone.utc).isoformat()
    with open(SOURCES_FILE,'w',encoding='utf-8') as f:
        json.dump(data,f,indent=2,ensure_ascii=False)
    return added


def main():
    log.info("="*60)
    log.info("  Brand Resolver — 品牌名批量找域名并验证")
    log.info("="*60)

    existing,_=load_existing()
    log.info(f"  已有源: {len(existing)}")

    all_candidates=[]

    for b in BRANDS:
        brand=b['brand']
        log.info(f"\n--- {brand} ---")

        candidates=[]

        # 1. Try known domains first
        for d in KNOWN_DOMAINS.get(brand,[]):
            url=f'https://{d}'
            log.info(f"  已知域名: {d}")
            resp=http_get(url,timeout=5)
            if resp and resp.status_code==200 and len(resp.text)>200:
                log.info(f"    OK ({len(resp.text)} bytes)")
                candidates.append({'domain':d,'url':url,'brand':brand,'source':'known'})
            else:
                log.info(f"    不可达")
            time.sleep(0.2)

        # 2. Search engine
        for q in b['queries'][:2]:
            results=search_bing(q,15)
            seen_d=set()
            for d,url,title in results:
                if d in existing or d in seen_d: continue
                seen_d.add(d)
                # filter out obviously unrelated
                tl=title.lower()
                if any(kw in tl for kw in ['magnet','种子','磁力','bt','torrent','搜索']):
                    candidates.append({'domain':d,'url':url,'brand':brand,'source':f'bing:{q}'})
            time.sleep(0.8)

        # dedupe
        seen=set()
        unique=[]
        for c in candidates:
            if c['domain'] not in seen:
                seen.add(c['domain'])
                unique.append(c)
        all_candidates.extend(unique)
        log.info(f"  候选: {len(unique)}")
        for c in unique:
            log.info(f"    {c['domain']:30s} from {c['source']}")

    log.info(f"\n{'='*60}")
    log.info(f"  总候选: {len(all_candidates)}")
    log.info(f"{'='*60}")

    # Verify
    verified=[]
    need_browser=[]
    failed=[]

    for i,c in enumerate(all_candidates):
        d=c['domain']
        if d in existing:
            log.info(f"  [{i+1}/{len(all_candidates)}] {d}: 已存在")
            continue

        log.info(f"  [{i+1}/{len(all_candidates)}] {d}")
        r=verify_source(c['url'],d)
        if r and r.get('magnets',0)>0:
            log.info(f"    OK! {r['magnets']} magnets path={r['path']}")
            verified.append({**c,'magnets':r['magnets'],'path':r['path'],
                           'bait':r['bait'],'samples':r.get('samples',[])})
        elif r and r.get('has_kw'):
            log.info(f"    有磁力关键词但HTTP未提取到，需浏览器验证")
            need_browser.append(c)
        else:
            reason='无磁力内容' if r is None else '有关键词但搜索无结果'
            log.info(f"    跳过 ({reason})")
            failed.append((c,reason))
        time.sleep(0.3)

    # Selenium verify
    if need_browser:
        log.info(f"\n  Selenium 验证 {len(need_browser)} 个候选...")
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts=Options()
        opts.add_argument('--headless');opts.add_argument('--disable-gpu');opts.add_argument('--no-sandbox')
        opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        drv=webdriver.Chrome(options=opts)
        drv.set_page_load_timeout(20)
        for c in need_browser:
            log.info(f"    {c['domain']}: ",end='',flush=True)
            for bait in BAIT_WORDS[:2]:
                for sp in [f'/search/{urllib.parse.quote(bait)}',f'/search?q={urllib.parse.quote(bait)}',
                            f'/?q={urllib.parse.quote(bait)}']:
                    try:
                        drv.get(c['url'].rstrip('/')+sp)
                        time.sleep(5)
                        magnets=extract_magnets(drv.page_source,c['url'])
                        if magnets:
                            log.info(f"OK! {len(magnets)} magnets")
                            verified.append({**c,'magnets':len(magnets),'path':sp,
                                           'bait':bait,'samples':magnets[:3],'requires_browser':True})
                            break
                        from bs4 import BeautifulSoup
                        hashes=set()
                        for m in HASH_RE.finditer(BeautifulSoup(drv.page_source,'lxml').get_text()):
                            hashes.add(m.group(0).upper())
                        if len(hashes)>=2:
                            log.info(f"OK! {len(hashes)} hashes")
                            verified.append({**c,'magnets':len(hashes),'path':sp,
                                           'bait':bait,'samples':[],'requires_browser':True})
                            break
                    except: pass
                if verified and verified[-1].get('domain')==c['domain']: break
            else:
                log.info(f"未提取到")
            time.sleep(0.3)
        drv.quit()

    # Summary
    log.info(f"\n{'='*60}")
    log.info(f"  最终结果")
    log.info(f"{'='*60}")
    log.info(f"  验证通过: {len(verified)}")
    for v in verified:
        log.info(f"    + {v['domain']:25s} {v.get('magnets',0):3d} magnets [{v['brand']}]")
    log.info(f"  需人工确认: {len(need_browser)}")
    log.info(f"  失败: {len(failed)}")

    added=add_to_sources(verified)
    log.info(f"\n  新增 {added} 个源到 sources.json")
    log.info("="*60)


if __name__=='__main__':
    main()
