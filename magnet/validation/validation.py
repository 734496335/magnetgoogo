import requests
import time
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime
import json
import hashlib

load_dotenv()

class Validation:
    @staticmethod
    def _interactive_captcha_allowed():
        if os.getenv('NEBULA_HEADLESS', '').lower() in ('1', 'true', 'yes'):
            return False
        if os.getenv('CI', '').lower() in ('1', 'true', 'yes'):
            return False
        return True

    def __init__(self, baits=None):
        self.timeout = int(os.getenv('TIMEOUT', 3000)) / 1000
        self.test_query = 'Inception'
        self.baits = baits or []
        self.browser = None
    
    def _init_browser(self):
        """初始化浏览器驱动"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(60)  # 延长超时时间，给用户足够的时间完成验证
            return driver
        except Exception as e:
            print(f"Error initializing browser: {e}")
            return None
    
    def handle_captcha(self, url):
        """处理人机验证"""
        if not self._interactive_captcha_allowed():
            print("Skipping interactive browser captcha (NEBULA_HEADLESS or CI).")
            return None

        try:
            if self.browser:
                self.browser.quit()
        except Exception:
            pass

        self.browser = self._init_browser()
        if not self.browser:
            print("Failed to initialize browser, skipping captcha handling")
            return None
        
        try:
            print(f"打开浏览器进行人机验证: {url}")
            self.browser.get(url)
            
            # 等待用户完成验证
            print("请在浏览器中完成人机验证，完成后按回车键继续...")
            print("如果页面上没有人机验证（比如域名过期），请直接按回车键继续...")
            input("按回车键继续...")
            
            # 尝试获取页面内容
            try:
                # 检查浏览器是否仍然打开
                if self.browser:
                    page_source = self.browser.page_source
                    
                    # 获取 cookies
                    cookies = self.browser.get_cookies()
                    cookie_string = '; '.join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
                    
                    # 获取 user agent
                    user_agent = self.browser.execute_script("return navigator.userAgent")
                    
                    # 关闭浏览器
                    self.browser.quit()
                    self.browser = None
                    
                    return {
                        'page_source': page_source,
                        'cookies': cookie_string,
                        'user_agent': user_agent
                    }
                else:
                    print("Browser is not available")
                    return None
            except Exception as browser_error:
                print(f"无法获取页面内容: {browser_error}")
                # 关闭浏览器
                try:
                    if self.browser:
                        self.browser.quit()
                        self.browser = None
                except:
                    pass
                return None
        except Exception as e:
            print(f"Error handling captcha: {e}")
            # 关闭浏览器
            try:
                if self.browser:
                    self.browser.quit()
                    self.browser = None
            except:
                pass
            return None
    
    def test_latency(self, url):
        """Test the latency of a source"""
        start_time = time.time()
        
        try:
            response = requests.get(url, timeout=self.timeout)
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            if response.status_code == 200:
                return {
                    'status': 'alive',
                    'latency': response_time,
                    'url': url
                }
            else:
                return {
                    'status': 'error',
                    'latency': response_time,
                    'url': url,
                    'error': f"HTTP {response.status_code}"
                }
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return {
                'status': 'error',
                'latency': response_time,
                'url': url,
                'error': str(e)
            }
    
    def ai_reverse_engineer(self, url):
        """逆向分析搜索接口"""
        try:
            response = requests.get(url, timeout=self.timeout, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })

            if response.status_code == 200:
                html = response.text

                from ai_parser.ai_parser import LocalHeuristicParser
                parser = LocalHeuristicParser(url)
                rules = parser.parse(html)
                search_path = rules.get('search_path', '')

                if search_path:
                    test_url = url.rstrip('/') + search_path.replace('{query}', self.test_query)
                    try:
                        test_response = requests.get(test_url, timeout=self.timeout)
                        if test_response.status_code == 200:
                            return {
                                'status': 'success',
                                'search_url_template': url.rstrip('/') + search_path
                            }
                    except:
                        pass

            return self.traditional_search_path_discovery(url)

        except Exception as e:
            print(f"Reverse engineering error: {e}")
            return self.traditional_search_path_discovery(url)
    
    def traditional_search_path_discovery(self, url):
        """传统搜索路径发现"""
        # Try common search path patterns
        search_paths = [
            f'/search?q={self.test_query}',
            f'/search/{self.test_query}',
            f'/torrents/search/{self.test_query}',
            f'/browse?q={self.test_query}',
            f'/search.php?q={self.test_query}',
            f'/index.php?q={self.test_query}',
            f'/search?query={self.test_query}',
            f'/torrents?q={self.test_query}'
        ]
        
        for path in search_paths:
            test_url = url.rstrip('/') + path
            
            try:
                response = requests.get(test_url, timeout=self.timeout)
                if response.status_code == 200:
                    # 提取搜索 URL 模板
                    search_url_template = test_url.replace(self.test_query, '{query}')
                    return {
                        'status': 'success',
                        'search_url_template': search_url_template
                    }
            except Exception as e:
                continue
        
        return {
            'status': 'error',
            'error': 'No working search path found'
        }
    
    def test_search(self, url, search_url_template=None):
        """Test search functionality and resource quality"""
        # 尝试多个搜索路径模板
        search_templates = []
        if search_url_template:
            search_templates.append(search_url_template)
        
        # 添加常见的搜索路径模板
        domain = url.rstrip('/')
        common_templates = [
            f"{domain}/search?q={{query}}",
            f"{domain}/search/{{query}}",
            f"{domain}/index.php?q={{query}}",
            f"{domain}/torrents/search/{{query}}",
            f"{domain}/search.php?q={{query}}",
            f"{domain}/browse?q={{query}}"
        ]
        
        for template in common_templates:
            if template not in search_templates:
                search_templates.append(template)
        
        # 尝试多个测试查询
        test_queries = ['Inception', 'Movie', 'Game', 'Anime', '磁力', 'torrent']
        
        # 尝试每个搜索模板
        for template in search_templates:
            for test_query in test_queries:
                test_url = template.replace('{query}', test_query)
                try:
                    # 增加重试机制
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            response = requests.get(test_url, timeout=self.timeout, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.5',
                                'Accept-Encoding': 'gzip, deflate',
                                'Connection': 'keep-alive',
                                'Upgrade-Insecure-Requests': '1'
                            })
                            break
                        except Exception as e:
                            if attempt == max_retries - 1:
                                print(f"Error testing {test_url}: {e}")
                            else:
                                time.sleep(1)
                                continue
                    
                    if response and response.status_code == 200:
                        # 检查是否需要人机验证
                        if 'captcha' in response.text.lower() or 'cloudflare' in response.text.lower():
                            print(f"需要人机验证: {test_url}")
                            if not self._interactive_captcha_allowed():
                                continue
                            captcha_result = self.handle_captcha(test_url)
                            if captcha_result:
                                # 使用验证后的页面内容和 AI 提取的磁力链接进行分析
                                magnet_links = captcha_result.get('magnet_links', None)
                                result = self.analyze_search_results(captcha_result['page_source'], test_url, magnet_links)
                                if result['status'] == 'valid':
                                    return result
                            # 如果验证失败，继续测试其他查询
                            continue
                        result = self.analyze_search_results(response.text, test_url)
                        if result['status'] == 'valid':
                            return result
                    elif response and response.status_code == 403:
                        print(f"403 禁止访问: {test_url}")
                        if not self._interactive_captcha_allowed():
                            continue
                        captcha_result = self.handle_captcha(test_url)
                        if captcha_result:
                            # 使用验证后的页面内容和 AI 提取的磁力链接进行分析
                            magnet_links = captcha_result.get('magnet_links', None)
                            result = self.analyze_search_results(captcha_result['page_source'], test_url, magnet_links)
                            if result['status'] == 'valid':
                                return result
                        # 如果验证失败，继续测试其他查询
                        continue
                except Exception as e:
                    print(f"Error testing {test_url}: {e}")
                    pass
        
        return {'status': 'error', 'message': 'No valid search results found'}
    
    def traditional_search_test(self, url):
        """传统搜索测试"""
        # Try common search path patterns
        search_paths = [
            f'/search?q={self.test_query}',
            f'/search/{self.test_query}',
            f'/torrents/search/{self.test_query}',
            f'/browse?q={self.test_query}'
        ]
        
        for path in search_paths:
            test_url = url.rstrip('/') + path
            
            try:
                response = requests.get(test_url, timeout=self.timeout)
                if response.status_code == 200:
                    return self.analyze_search_results(response.text, test_url)
            except Exception as e:
                continue
        
        return {
            'status': 'error',
            'url': url,
            'error': 'No working search path found'
        }
    
    def analyze_search_results(self, html, url, magnet_links=None):
        """Analyze search results for resource quality"""
        # 如果提供了磁力链接，直接使用
        if magnet_links and len(magnet_links) > 0:
            return {
                'status': 'valid',
                'url': url,
                'quality_score': 100,
                'total_resources': len(magnet_links),
                'valid_resources': len(magnet_links)
            }
        
        soup = BeautifulSoup(html, 'lxml')
        
        # 首先尝试直接查找所有磁力链接
        magnet_links = []
        # 使用更广泛的选择器来查找磁力链接
        magnet_selectors = [
            'a[href^="magnet:"]', 'a[href*="magnet:"]', 'a[href*="magnet:?xt="]',
            'a.magnet', 'a[title*="magnet"]', 'a[title*="磁力"]',
            'a[class*="magnet"]', 'a[rel*="magnet"]', 'a[title="磁力链接"]'
        ]
        
        for selector in magnet_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href and 'magnet:' in href:
                    magnet_links.append(href)
        
        # 如果找到磁力链接，直接认为是有效的
        if magnet_links:
            return {
                'status': 'valid',
                'url': url,
                'quality_score': 100,
                'total_resources': len(magnet_links),
                'valid_resources': len(magnet_links)
            }
        
        # 尝试找到种子项目
        torrent_selectors = [
            'div.torrent', 'tr.torrent', 'div.search-result', 'div.item',
            'div.result', 'li.torrent', 'div.torrent-item', 'tr.torrent-row',
            'div.torrent_info', 'div.torrent-detail', 'li.torrent-item',
            'div.torrent-list-item', 'div.search-item', 'div.card',
            'div.list-item', 'div.result-item', 'tr.result'
        ]
        
        torrent_items = []
        for selector in torrent_selectors:
            items = soup.select(selector)
            if items:
                torrent_items.extend(items)
                if len(torrent_items) >= 10:  # 最多取10个
                    break
        
        if not torrent_items:
            from ai_parser.ai_parser import LocalHeuristicParser
            parser = LocalHeuristicParser(url)
            rules = parser.parse(html)
            selectors = rules.get('selectors', {})
            list_item_sel = selectors.get('list_item', 'div.item')
            magnet_sel = selectors.get('magnet', 'a[href^="magnet:"]')

            try:
                items = BeautifulSoup(html, 'lxml').select(list_item_sel)
                if items:
                    torrent_items = items
            except:
                pass

            if not torrent_items:
                try:
                    items = BeautifulSoup(html, 'lxml').select(magnet_sel)
                    if items:
                        magnet_links = [a.get('href') for a in items if a.get('href') and 'magnet:' in a.get('href', '')]
                        if magnet_links:
                            print(f"Local parser extracted {len(magnet_links)} magnet links")
                            return {
                                'status': 'valid',
                                'url': url,
                                'quality_score': 100,
                                'total_resources': len(magnet_links),
                                'valid_resources': len(magnet_links)
                            }
                except:
                    pass

            return {
                'status': 'error',
                'url': url,
                'error': 'No torrent items or magnet links found'
            }
        
        # 分析资源质量
        valid_resources = 0
        total_resources = len(torrent_items)
        small_files = 0
        magnet_found = False
        
        for item in torrent_items[:10]:  # Limit to first 10 items
            # 检查磁力链接
            for selector in magnet_selectors:
                magnet_links = item.select(selector)
                if magnet_links:
                    for link in magnet_links:
                        href = link.get('href')
                        if href and 'magnet:' in href:
                            valid_resources += 1
                            magnet_found = True
                            break
                    if magnet_found:
                        break
            
            # 检查文件大小信息
            size_elements = item.select('span.size, div.size, td.size, span.file-size, div.file-size, span.filesize, div.filesize')
            for size_elem in size_elements:
                size_text = size_elem.get_text().strip().lower()
                # 过滤掉非常小的文件（可能是假的）
                if any(unit in size_text for unit in ['kb', 'kib']) and '100' not in size_text:
                    small_files += 1
                    continue
                valid_resources += 1
                break
        
        # 如果找到磁力链接，直接认为是有效的
        if magnet_found:
            quality_score = 100
        else:
            quality_score = (valid_resources / total_resources) * 100 if total_resources > 0 else 0
        
        # 检测恶意欺诈 (Scam)
        if small_files > total_resources * 0.8:
            return {
                'status': 'scam',
                'url': url,
                'quality_score': 0,
                'total_resources': total_resources,
                'valid_resources': valid_resources,
                'error': 'Too many small files (likely scam)'
            }
        
        return {
            'status': 'valid' if (quality_score > 20 or magnet_found) else 'low_quality',
            'url': url,
            'quality_score': quality_score,
            'total_resources': total_resources,
            'valid_resources': valid_resources
        }
    
    def validate_sources(self, sources):
        """Validate a list of sources"""
        print("\n=== 开始磁力源验证过程 ===")
        print(f"待验证的磁力源数量: {len(sources)}")
        valid_sources = []
        
        for source in sources:
            print(f"\nValidating: {source}")
            
            # Test latency
            latency_result = self.test_latency(source)
            print(f"Latency test: {latency_result['status']} ({latency_result['latency']:.2f}ms)")
            
            if latency_result['status'] == 'alive' and latency_result['latency'] <= int(os.getenv('TIMEOUT', 3000)):
                # AI 逆向接口分析
                reverse_result = self.ai_reverse_engineer(source)
                print(f"AI reverse engineering: {reverse_result['status']}")
                
                if reverse_result['status'] == 'success':
                    search_url_template = reverse_result['search_url_template']
                    print(f"Found search URL template: {search_url_template}")
                    
                    # 测试搜索功能
                    search_result = self.test_search(source, search_url_template)
                    print(f"Search test: {search_result['status']}")
                    
                    if search_result['status'] == 'valid':
                        # 多维测试与智能打分矩阵
                        tags = self.generate_tags(source, search_url_template)
                        # quality.score should be 0-100
                        score = min(100, int(search_result['quality_score'] * (100 / max(10, latency_result['latency']))))
                        
                        source_info = {
                            'url': source,
                            'id': hashlib.md5(source.encode('utf-8')).hexdigest()[:12] if 'hashlib' in globals() else source,
                            'quality': {
                                'score': score,
                                'tags': tags
                            },
                            'health': {
                                'status': 'green' if score > 70 else ('yellow' if score > 30 else 'gray'),
                                'last_checked_at': datetime.utcnow().isoformat() + "Z",
                                'fail_count_30d': 0
                            },
                            'search_url_template': search_url_template,
                            'latency': latency_result['latency']
                        }
                        valid_sources.append(source_info)
                        print(f"Valid source with score: {score}% and tags: {', '.join(tags)}")
                    elif search_result['status'] == 'scam':
                        print(f"Scam source detected: {source}")
        
        # Sort by score (higher is better)
        valid_sources.sort(key=lambda x: x['quality']['score'], reverse=True)
        
        print(f"\nTotal valid sources: {len(valid_sources)}")
        return valid_sources
    
    def generate_tags(self, url, search_url_template):
        """生成动态标签"""
        tags = []
        
        # 测试最新热门诱饵
        recent_baits = self.baits[:5]  # 取前5个最新诱饵
        recent_hits = 0
        
        for bait in recent_baits:
            try:
                test_url = search_url_template.replace('{query}', bait.split()[0])  # 只取诱饵词的第一个词
                response = requests.get(test_url, timeout=self.timeout)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'lxml')
                    torrent_items = soup.select('div.torrent, tr.torrent, div.search-result, div.item')
                    if torrent_items:
                        recent_hits += 1
            except Exception as e:
                pass
        
        # 测试经典诱饵
        classic_baits = self.baits[-5:]  # 取后5个经典诱饵
        classic_hits = 0
        large_files = 0
        
        for bait in classic_baits:
            try:
                test_url = search_url_template.replace('{query}', bait.split()[0])  # 只取诱饵词的第一个词
                response = requests.get(test_url, timeout=self.timeout)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'lxml')
                    torrent_items = soup.select('div.torrent, tr.torrent, div.search-result, div.item')
                    if torrent_items:
                        classic_hits += 1
                        
                        # 检查文件大小
                        for item in torrent_items[:5]:
                            size_elements = item.select('span.size, div.size, td.size')
                            for size_elem in size_elements:
                                size_text = size_elem.get_text().strip().lower()
                                if 'gb' in size_text and any(num in size_text for num in ['10', '20', '30', '40', '50']):
                                    large_files += 1
            except Exception as e:
                pass
        
        # 生成标签
        if recent_hits >= 4:
            tags.append('追新极客')
        if classic_hits >= 4 and large_files >= 3:
            tags.append('经典老库')
        if '动漫' in ' '.join(self.baits) and recent_hits >= 3 and classic_hits < 2:
            tags.append('垂直专精')
        
        return tags

    def calculate_score(self, latency_result, search_result, tags):
        """计算得分 (0-100)"""
        # 基础分
        base_score = search_result['quality_score']
        
        # 延迟加权 (延迟越低分越高，基准为 1s)
        latency_factor = min(1.2, 1000 / max(100, latency_result['latency']))
        
        # 标签加分
        tag_bonus = 0
        for tag in tags:
            if tag == '追新极客':
                tag_bonus += 10
            elif tag == '经典老库':
                tag_bonus += 5
            elif tag == '垂直专精':
                tag_bonus += 5
        
        final_score = (base_score * latency_factor) + tag_bonus
        return min(100, int(final_score))
