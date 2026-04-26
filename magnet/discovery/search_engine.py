import requests
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote
import google.generativeai as genai
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()



class BaitGenerator:
    """动态诱饵库生成器"""
    def __init__(self):
        self.tmdb_api_key = os.getenv("TMDB_API_KEY")

    def get_tmdb_trending(self):
        """获取TMDB今日趋势"""
        if not self.tmdb_api_key:
            return []
        url = f"https://api.themoviedb.org/3/trending/all/day?api_key={self.tmdb_api_key}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get('results', [])
                trending = []
                for item in items[:10]:  # 取前10个
                    if 'title' in item:
                        trending.append(item['title'])
                    elif 'name' in item:
                        trending.append(item['name'])
                return trending
        except Exception as e:
            print(f"Error getting TMDB trending: {e}")
        return []
    
    def get_douban_top250(self):
        """获取豆瓣Top 250"""
        url = "https://movie.douban.com/top250"
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                items = soup.select('.hd')
                top250 = []
                for item in items[:10]:  # 取前10个
                    title = item.select_one('.title').get_text().strip()
                    top250.append(title)
                return top250
        except Exception as e:
            print(f"Error getting Douban Top 250: {e}")
        return []
    
    def get_steam_hot(self):
        """获取Steam热销商品"""
        url = "https://store.steampowered.com/charts/mostplayed"
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                items = soup.select('.weeklytopsellers_Title_2R_eh')
                hot_games = []
                for item in items[:10]:  # 取前10个
                    title = item.get_text().strip()
                    hot_games.append(title)
                return hot_games
        except Exception as e:
            print(f"Error getting Steam hot games: {e}")
        return []
    
    def get_bangumi_daily(self):
        """获取Bangumi每日番组"""
        url = "https://bangumi.tv/calendar"
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                items = soup.select('.bangumi-title')
                daily_anime = []
                for item in items[:10]:  # 取前10个
                    title = item.get_text().strip()
                    daily_anime.append(title)
                return daily_anime
        except Exception as e:
            print(f"Error getting Bangumi daily anime: {e}")
        return []
    
    def generate_baits(self):
        """生成诱饵词库"""
        print("Generating dynamic bait library...")
        
        # 并行获取各平台数据
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_tmdb = executor.submit(self.get_tmdb_trending)
            future_douban = executor.submit(self.get_douban_top250)
            future_steam = executor.submit(self.get_steam_hot)
            future_bangumi = executor.submit(self.get_bangumi_daily)
        
        # 收集结果
        tmdb_trending = future_tmdb.result()
        douban_top250 = future_douban.result()
        steam_hot = future_steam.result()
        bangumi_daily = future_bangumi.result()
        
        # 生成诱饵词
        baits = []
        
        # 最新首发（TMDB趋势 + Steam热销 + Bangumi每日）
        for item in tmdb_trending + steam_hot + bangumi_daily:
            if item:
                baits.append(item + " 磁力")
                baits.append(item + " magnet")
        
        # 长尾经典（豆瓣Top 250）
        for item in douban_top250:
            if item:
                baits.append(item + " 磁力")
                baits.append(item + " magnet")

        # 垂直站 / 成人向索引常用词（区分「无结果」与版面损坏；见 CURSOR_HANDOVER）
        for token in ("SSNI", "sukebei", "jav", "ゲーム cg", "同人志"):
            baits.append(token + " 磁力")
            baits.append(token + " magnet")

        # 去重并限制数量
        baits = list(dict.fromkeys(baits))[:100]
        
        print(f"Generated {len(baits)} bait keywords")
        return baits

class SearchEngine:
    def __init__(self):
        self.bing_api_key = os.getenv('BING_API_KEY')
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        
        # 初始化 Gemini（模型可配置，避免已弃用 ID）
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel(
                os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            )
        
        # 初始化诱饵生成器
        self.bait_generator = BaitGenerator()
        
        # 扩展的搜索引擎列表
        self.search_engines = {
            'baidu': self.search_baidu,
            'sogou': self.search_sogou,
            'so': self.search_so,
            'sm': self.search_sm,
            'google': self.search_google
        }
        
        # 检查 Bing 是否可用
        if self.bing_api_key and self.is_engine_available('bing'):
            self.search_engines['bing'] = self.search_bing
        
        # 过滤掉的域名
        self.filtered_domains = [
            'baike.so.com', 'wenku.so.com', 'fanyi.so.com', 'so.com',
            '360kuai.com', 'info.so.com', 'xinzhi.wenda.so.com',
            'csdn.net', 'pc6.com', 'downza.cn', 'javascript://',
            'baidu.com', 'sogou.com', 'sm.cn', 'microsoft.com'
        ]
        

        
        self.discovered_keywords = set()
        self.visited_urls = set()
        self.available_engines = list(self.search_engines.keys())
    
    def is_engine_available(self, engine_name):
        """检查搜索引擎是否可用"""
        test_urls = {
            'bing': 'https://www.bing.com',
            'baidu': 'https://www.baidu.com',
            'sogou': 'https://www.sogou.com',
            'so': 'https://www.so.com',
            'sm': 'https://www.sm.cn',
            'google': 'https://www.google.com'
        }
        
        test_url = test_urls.get(engine_name)
        if not test_url:
            return False
        
        try:
            response = requests.get(test_url, timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"{engine_name} is not available: {e}")
            return False
    
    def search_bing(self, query, count=10):
        if not self.bing_api_key:
            return []
        
        url = 'https://api.bing.microsoft.com/v7.0/search'
        headers = {'Ocp-Apim-Subscription-Key': self.bing_api_key}
        params = {'q': query, 'count': count, 'responseFilter': 'Webpages'}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'webPages' in data and 'value' in data['webPages']:
                    return [item['url'] for item in data['webPages']['value']]
        except Exception as e:
            print(f"Bing search error: {e}")
        return []
    
    def search_baidu(self, query):
        url = 'https://www.baidu.com/s'
        params = {'wd': query}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                results = []
                for a in soup.select('h3.t a'):
                    href = a.get('href')
                    if href:
                        # 处理百度跳转链接
                        if 'http' not in href:
                            continue
                        results.append(href)
                print(f"Baidu returned {len(results)} results for '{query}'")
                return results[:10]
            else:
                print(f"Baidu returned status code: {response.status_code}")
        except Exception as e:
            print(f"Baidu search error: {e}")
        return []
    
    def search_sogou(self, query):
        url = 'https://www.sogou.com/web'
        params = {'query': query}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                results = []
                for a in soup.select('h3 a'):
                    href = a.get('href')
                    if href:
                        results.append(href)
                print(f"Sogou returned {len(results)} results for '{query}'")
                return results[:10]
            else:
                print(f"Sogou returned status code: {response.status_code}")
        except Exception as e:
            print(f"Sogou search error: {e}")
        return []
    
    def search_so(self, query):
        url = 'https://www.so.com/s'
        params = {'q': query}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                results = []
                for a in soup.select('h3 a'):
                    href = a.get('href')
                    if href:
                        results.append(href)
                print(f"360 Search returned {len(results)} results for '{query}'")
                return results[:10]
            else:
                print(f"360 Search returned status code: {response.status_code}")
        except Exception as e:
            print(f"360 Search error: {e}")
        return []
    
    def search_sm(self, query):
        url = 'https://www.sm.cn/s'
        params = {'q': query}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                results = []
                for a in soup.select('h3 a'):
                    href = a.get('href')
                    if href:
                        results.append(href)
                print(f"Shenma returned {len(results)} results for '{query}'")
                return results[:10]
            else:
                print(f"Shenma returned status code: {response.status_code}")
        except Exception as e:
            print(f"Shenma search error: {e}")
        return []
    
    def search_google(self, query):
        url = 'https://www.google.com/search'
        params = {'q': query}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                results = []
                for a in soup.select('h3 a'):
                    href = a.get('href')
                    if href and 'http' in href:
                        # 处理 Google 跳转链接
                        if '/url?q=' in href:
                            import urllib.parse
                            parsed = urllib.parse.urlparse(href)
                            query_params = urllib.parse.parse_qs(parsed.query)
                            if 'q' in query_params:
                                href = query_params['q'][0]
                        results.append(href)
                print(f"Google returned {len(results)} results for '{query}'")
                return results[:10]
            else:
                print(f"Google returned status code: {response.status_code}")
        except Exception as e:
            print(f"Google search error: {e}")
        return []
    
    def analyze_page(self, url):
        """分析网页内容，提取信息"""
        # 使用 requests 获取页面内容
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                # 提取标题和元描述
                title = soup.title.string if soup.title else ''
                meta_desc = ''
                meta_tag = soup.find('meta', {'name': 'description'})
                if meta_tag:
                    meta_desc = meta_tag.get('content', '')
                # 提取页面文本
                text = soup.get_text(separator=' ', strip=True)
                return {'title': title, 'meta_desc': meta_desc, 'text': text[:1000]}
        except Exception as e:
            print(f"Error analyzing page {url}: {e}")
        return None
    
    def generate_new_keywords(self, content):
        """使用LLM生成新的搜索词"""
        if not self.gemini_api_key:
            return []
        
        try:
            prompt = f"""
Analyze the following webpage content and generate 5-10 new search keywords that could help find more torrent/magnet link search sites. The keywords should be in both English and Chinese.

Title: {content.get('title', '')}
Meta Description: {content.get('meta_desc', '')}
Page Text: {content.get('text', '')}

Output only the keywords, one per line, no additional text.
"""
            response = self.gemini_model.generate_content(prompt)
            keywords = response.text.strip().split('\n')
            return [k.strip() for k in keywords if k.strip()]
        except Exception as e:
            print(f"Error generating keywords: {e}")
        return []
    
    def extract_domain(self, url):
        """提取域名"""
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return url
    
    def is_valid_magnet_site(self, url, content):
        """判断是否为有效的磁力搜索站点"""
        # 检查域名是否在过滤列表中
        domain = self.extract_domain(url)
        for filtered in self.filtered_domains:
            if filtered in domain:
                print(f"Filtered domain: {domain}")
                return False
        
        # 检查页面内容是否包含磁力搜索相关特征
        if content:
            text = (content.get('title', '') + ' ' + content.get('meta_desc', '') + ' ' + content.get('text', '')).lower()
            # 更宽松的关键词匹配
            magnet_keywords = ['magnet', 'torrent', 'bt', '种子', '磁力', 'p2p', '下载', 'search', '搜索', '资源', '分享']
            # 至少匹配一个关键词
            matched_keywords = [keyword for keyword in magnet_keywords if keyword in text]
            print(f"URL: {url}")
            print(f"Matched keywords: {matched_keywords}")
            if len(matched_keywords) >= 1:
                print(f"Found valid magnet site: {domain}")
                return True
        
        print(f"Not a valid magnet site: {domain}")
        return False
    
    def extract_recent_resources(self, url):
        """从海盗湾 recent 页面提取最新资源名称"""
        resources = []
        
        # 使用 requests 获取页面内容
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                # 尝试不同的选择器来找到资源列表
                selectors = [
                    'tr[class^="alt"]',
                    'tr',
                    'div[class*="torrent"]',
                    'div[class*="item"]'
                ]
                
                for selector in selectors:
                    items = soup.select(selector)
                    if items:
                        for item in items:
                            # 尝试不同的选择器来提取标题
                            title_selectors = [
                                'a[href^="/torrent/"]',
                                'a[href*="torrent"]',
                                'a.title',
                                'h3 a'
                            ]
                            
                            for title_selector in title_selectors:
                                title_elem = item.select_one(title_selector)
                                if title_elem:
                                    title = title_elem.get_text().strip()
                                    # 过滤掉非资源名称信息
                                    if title and len(title) > 10:
                                        resources.append(title)
                                    break
                        if resources:
                            break
                
                print(f"Extracted {len(resources)} recent resources from {url}")
        except Exception as e:
            print(f"Error extracting recent resources: {e}")
        return resources
    
    def discover_sources(self):
        sources = set()
        
        print("\n=== 开始磁力源发现过程 ===")
        
        # 扩展的已知磁力搜索站点列表（优先国内站点，减少对国外站点的依赖）
        known_sites = [
            # 国内磁力站点（高优先级）
            'https://btso.cc',
            'https://btsow.com',
            'https://btbtt12.com',
            'https://btfans.com',
            'https://btdb.to',
            'https://verycd.com',
            'https://cilimao.com',
            'https://ciligou.com',
            'https://种子搜索.com',
            'https://磁力搜.com',
            'https://磁力吧.com',
            'https://磁力狗.com',
            'https://磁力猫.com',
            'https://磁力熊.com',
            'https://磁力兔.com',
            'https://btmulu.me',
            'https://btcherry.com',
            'https://btcili.com',
            'https://bt天堂.com',
            'https://btlooker.com',
            'https://btbook.me',
            'https://btxiong.com',
            'https://bt5200.com',
            'https://bt1314.net',
            'https://bt365.im',
            'https://bt888.cc',
            'https://bt990.com',
            'https://bt5156.com',
            'https://bt5211.com',
            'https://bt530.com',
            'https://bt5566.net',
            'https://bt6688.net',
            'https://bt7777.com',
            'https://bt8899.com',
            'https://bt9988.com',
            'https://bt1688.com',
            'https://bt2222.com',
            'https://bt3333.com',
            'https://bt4444.com',
            'https://bt5555.com',
            'https://bt6666.com',
            'https://bt7777.com',
            'https://bt8888.com',
            'https://bt9999.com',
            
            # 磁力导航站
            'https://ciligou.com',
            'https://cilimao.com',
            'https://cilixiong.com',
            'https://cilitu.com',
            'https://磁力搜.com',
            'https://磁力吧.com',
            'https://磁力狗.com',
            'https://磁力猫.com',
            'https://磁力熊.com',
            'https://磁力兔.com',
            
            # 稳定的国外站点（低优先级）
            'https://animetosho.org',
            'https://nyaa.si',
            'https://anidex.info',
            'https://fitgirl-repacks.site',
            'https://skidrowreloaded.com',
            'https://extratorrent.ag',
            'https://bitlord.com',
            'https://bitport.io',
            'https://etree.org',
            'https://bt.etree.org'
        ]
        
        print("Testing known magnet sites...")
        
        # 使用多线程并行测试已知站点
        def test_site(site):
            try:
                # 分析页面
                content = self.analyze_page(site)
                # 检查是否为有效的磁力搜索站点
                if content and self.is_valid_magnet_site(site, content):
                    # 提取域名
                    domain = self.extract_domain(site)
                    print(f"Found valid magnet site: {domain}")
                    return domain
            except Exception as e:
                print(f"Error testing {site}: {e}")
            return None
        
        # 限制并发数量
        max_workers = 10
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_site = {executor.submit(test_site, site): site for site in known_sites}
            
            # 处理结果
            for future in as_completed(future_to_site):
                site = future_to_site[future]
                try:
                    domain = future.result()
                    if domain:
                        sources.add(domain)
                except Exception as e:
                    print(f"Error processing {site}: {e}")
        
        # 从海盗湾 recent 页面提取最新资源，并搜索相关磁力链接
        print("\nExtracting recent resources from The Pirate Bay...")
        recent_url = 'https://m.thepiratebay0.org/recent'
        recent_resources = self.extract_recent_resources(recent_url)
        
        # 对每个资源进行搜索
        for resource in recent_resources[:10]:  # 只处理前10个资源
            # 提取关键词
            keywords = resource.split()[:5]  # 取前5个词作为关键词
            search_query = ' '.join(keywords) + ' magnet'
            print(f"Searching for: {search_query}")
            
            # 在所有可用搜索引擎中搜索
            for engine_name, search_func in self.search_engines.items():
                try:
                    results = search_func(search_query)
                    for url in results[:3]:  # 只处理前3个结果
                        if url not in self.visited_urls and 'http' in url:
                            self.visited_urls.add(url)
                            # 分析页面
                            content = self.analyze_page(url)
                            # 检查是否为有效的磁力搜索站点
                            if content and self.is_valid_magnet_site(url, content):
                                # 提取域名
                                domain = self.extract_domain(url)
                                sources.add(domain)
                                print(f"Found valid magnet site: {domain}")
                except Exception as e:
                    print(f"Error with {engine_name}: {e}")
                
                # 避免请求过于频繁
                time.sleep(1)
        
        # 生成动态诱饵词
        baits = self.bait_generator.generate_baits()
        
        # 同时使用搜索引擎搜索
        keywords_to_search = baits
        processed_keywords = set()
        
        try:
            # 检查所有搜索引擎的可用性
            available_engines = {}
            for engine_name, search_func in self.search_engines.items():
                if self.is_engine_available(engine_name):
                    available_engines[engine_name] = search_func
            
            print(f"\nAvailable search engines: {list(available_engines.keys())}")
            
            # 限制搜索关键词数量
            max_keywords = 10
            keyword_count = 0
            
            while keywords_to_search and keyword_count < max_keywords:
                keyword = keywords_to_search.pop(0)
                if keyword in processed_keywords:
                    continue
                
                processed_keywords.add(keyword)
                keyword_count += 1
                print(f"Searching with bait: {keyword}")
                
                for engine_name, search_func in available_engines.items():
                    try:
                        results = search_func(keyword)
                        # 限制每个搜索引擎的结果数量
                        for url in results[:3]:  # 只处理前3个结果
                            if url not in self.visited_urls and 'http' in url:
                                self.visited_urls.add(url)
                                # 分析页面
                                content = self.analyze_page(url)
                                # 检查是否为有效的磁力搜索站点
                                if content and self.is_valid_magnet_site(url, content):
                                    # 提取域名
                                    domain = self.extract_domain(url)
                                    sources.add(domain)
                                    print(f"✓ Found valid magnet site: {domain}")
                    except Exception as e:
                        print(f"Error with {engine_name}: {e}")
                    
                    # 避免请求过于频繁
                    time.sleep(1)
            
            # 搜索导航站
            print("\n--- 搜索导航站 ---")
            navigation_queries = [
                '磁力导航', 'BT导航', '种子搜索导航', '磁力链接导航',
                'bt导航网站', '磁力搜索导航', 'bt网址导航', '磁力链接导航网站'
            ]
            
            for query in navigation_queries:
                print(f"Searching for navigation site: {query}")
                for engine_name, search_func in available_engines.items():
                    try:
                        results = search_func(query)
                        print(f"{engine_name} returned {len(results)} results for '{query}'")
                        for url in results[:3]:  # 只处理前3个结果
                            if url not in self.visited_urls and 'http' in url:
                                self.visited_urls.add(url)
                                # 分析导航站页面，提取磁力源
                                try:
                                    response = requests.get(url, timeout=10, headers={
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                                    })
                                    if response.status_code == 200:
                                        # 提取页面中的磁力源链接
                                        soup = BeautifulSoup(response.text, 'lxml')
                                        links = soup.find_all('a', href=lambda href: href and 'http' in href)
                                        for link in links[:20]:  # 只处理前20个链接
                                            href = link.get('href')
                                            if href:
                                                domain = self.extract_domain(href)
                                                if domain not in self.visited_urls:
                                                    self.visited_urls.add(domain)
                                                    # 分析页面
                                                    content = self.analyze_page(href)
                                                    # 检查是否为有效的磁力搜索站点
                                                    if content and self.is_valid_magnet_site(href, content):
                                                        sources.add(domain)
                                                        print(f"✓ Found valid magnet site from navigation: {domain}")
                                except Exception as e:
                                    print(f"Error analyzing navigation site {url}: {e}")
                    except Exception as e:
                        print(f"Error searching {engine_name} for navigation: {e}")
                    
                    # 避免请求过于频繁
                    time.sleep(1)
            
            # 搜索论坛
            print("\n--- 搜索论坛 ---")
            forum_queries = [
                '磁力搜索论坛', 'BT论坛', '种子搜索论坛', '磁力链接论坛',
                'bt论坛 磁力', '磁力搜索 论坛', 'bt种子 论坛', '磁力链接 论坛'
            ]
            
            for query in forum_queries:
                print(f"Searching for forum: {query}")
                for engine_name, search_func in available_engines.items():
                    try:
                        results = search_func(query)
                        print(f"{engine_name} returned {len(results)} results for '{query}'")
                        for url in results[:3]:  # 只处理前3个结果
                            if url not in self.visited_urls and 'http' in url:
                                self.visited_urls.add(url)
                                # 分析论坛页面，提取磁力源
                                try:
                                    response = requests.get(url, timeout=10, headers={
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                                    })
                                    if response.status_code == 200:
                                        # 提取页面中的磁力源链接
                                        soup = BeautifulSoup(response.text, 'lxml')
                                        links = soup.find_all('a', href=lambda href: href and 'http' in href)
                                        for link in links[:20]:  # 只处理前20个链接
                                            href = link.get('href')
                                            if href:
                                                domain = self.extract_domain(href)
                                                if domain not in self.visited_urls:
                                                    self.visited_urls.add(domain)
                                                    # 分析页面
                                                    content = self.analyze_page(href)
                                                    # 检查是否为有效的磁力搜索站点
                                                    if content and self.is_valid_magnet_site(href, content):
                                                        sources.add(domain)
                                                        print(f"✓ Found valid magnet site from forum: {domain}")
                                except Exception as e:
                                    print(f"Error analyzing forum {url}: {e}")
                    except Exception as e:
                        print(f"Error searching {engine_name} for forum: {e}")
                    
                    # 避免请求过于频繁
                    time.sleep(1)
        except Exception as e:
            print(f"Critical error in discover_sources: {e}")
        
        print(f"\nTotal sources found: {len(sources)}")
        return list(sources)
