import os
import json
import re
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

load_dotenv()


def _extract_json_object(text):
    """Parse first top-level JSON object from LLM output (fences or balanced braces)."""
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


class LocalHeuristicParser:
    """本地启发式解析器 - 不依赖任何外部 API"""

    LIST_ITEM_PATTERNS = [
        'tr.torrent', 'tr.torrent_row', 'tr[data-id]', 'div.torrent', 'div.torrent-item',
        'div.search-result', 'div.result', 'div.item', 'li.torrent', 'li.torrent-item',
        'div.torrent_info', 'div.torrent-detail', 'div.torrent-list-item', 'div.search-item',
        'div.card', 'div.list-item', 'div.result-item', 'tr.result', 'table tbody tr',
        'div.data-row', 'tr.data-info', 'a.torrent', 'div.torrents-item', 'tr[class*="torrent"]',
        'div[class*="torrent"]', '.t-row', '.list-row'
    ]

    TITLE_PATTERNS = [
        'a[href*="/torrent/"]', 'a[href*="/view/"]', 'a[href*="/info/"]', 'a[href*="/detail/"]',
        'a.torrent-title', 'a.title', '.title a', '.torrent-title', '.name a',
        'span.name', 'div.name', 'h3 a', 'h2 a', 'td:nth-child(2) a', 'a[title]',
        'a[href*="/magnet/"]', 'a.link-item'
    ]

    MAGNET_PATTERNS = [
        'a[href^="magnet:"]', 'a.magnet', 'a[href*="magnet:"]', 'a[title*="magnet"]',
        'a[href*="magnet:?xt="]', 'a[class*="magnet"]'
    ]

    SIZE_PATTERNS = [
        'span.size', 'div.size', 'td.size', 'span.file-size', 'div.file-size',
        'span.filesize', 'div.filesize', '.size', 'td:nth-child(4)', 'td:nth-child(5)'
    ]

    DATE_PATTERNS = [
        'span.date', 'div.date', 'td.date', 'span.time', 'div.time', 'td.time',
        '.date', '.time', 'td:nth-child(5)', 'td:nth-child(6)', 'span.created',
        'div.created', 'td:nth-child(6)'
    ]

    def __init__(self, url):
        self.url = url
        self.domain = url.rstrip('/')
        self._soup = None

    def parse(self, html):
        """分析 HTML 并通过磁力锚点反向推导解析规则 (Healer V2)"""
        self._soup = BeautifulSoup(html, 'lxml')
        
        # 1. 尝试通过磁力锚点反向归纳结构
        anchored_selectors = self._discover_by_magnet_anchor()
        
        rules = {
            'search_path': self._find_search_path(),
            'selectors': {
                'list_item': anchored_selectors.get('list_item') or self._find_list_item_selector(),
                'title': anchored_selectors.get('title') or self._find_title_selector(),
                'magnet': anchored_selectors.get('magnet') or self._find_magnet_selector(),
                'size': anchored_selectors.get('size') or self._find_size_selector(),
                'date': anchored_selectors.get('date') or self._find_date_selector()
            },
            'requires_waf_bypass': self._detect_waf()
        }
        return rules

    def _discover_by_magnet_anchor(self):
        """核心算法：寻找磁力锚点并回溯父级容器"""
        magnets = self._soup.select('a[href^="magnet:"]')
        if not magnets or len(magnets) < 2:
            return {}

        # 统计父级容器的类名频率
        parent_classes = {}
        for m in magnets:
            curr = m.parent
            depth = 0
            while curr and depth < 5:
                cls = curr.get('class')
                if cls:
                    cls_name = ".".join(cls)
                    key = f"{curr.name}.{cls_name}"
                    parent_classes[key] = parent_classes.get(key, 0) + 1
                curr = curr.parent
                depth += 1

        # 寻找出现频率最高且大于等于 2 的容器作为 list_item
        best_container = None
        max_freq = 0
        for cls, freq in parent_classes.items():
            if freq >= 2 and freq > max_freq:
                max_freq = freq
                best_container = cls

        if not best_container:
            return {}

        results = {'list_item': best_container, 'magnet': 'a[href^="magnet:"]'}
        
        # 在选定的容器内寻找标题锚点
        # 常见规则：包含 /torrent/, /info/, /view/, /detail/ 的链接
        container_sample = self._soup.select(best_container)[0]
        links = container_sample.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            if any(p in href for p in ['/torrent/', '/info/', '/view/', '/detail/']):
                # 构造相对于容器的选择器
                cls = link.get('class')
                if cls:
                    results['title'] = f"a.{'.'.join(cls)}"
                else:
                    results['title'] = f"a[href*='{href.split('?')[0].split('/')[-1]}']"
                break
        
        # 兜底方案：如果没找到符合规则的标题链接，寻找容器内唯一的 a 标签或最长的 a 标签文本
        if 'title' not in results:
            best_a = None
            max_len = 0
            for a in links:
                txt = a.get_text(strip=True)
                if len(txt) > max_len and 'magnet:' not in a.get('href', ''):
                    max_len = len(txt)
                    best_a = a
            if best_a:
                cls = best_a.get('class')
                if cls:
                    results['title'] = f"a.{'.'.join(cls)}"
                else:
                    results['title'] = "a"
        
        return results

    def _find_search_path(self):
        forms = self._soup.find_all('form')
        for form in forms:
            action = form.get('action', '')
            method = form.get('method', 'get').lower()
            if method == 'get' and action:
                inputs = form.find_all('input')
                for inp in inputs:
                    name = inp.get('name', '')
                    if name:
                        return f"{action}?{name}={{query}}"
                if '{query}' not in action:
                    return f"{action}?q={{query}}"
        search_patterns = ['/search', '/torrents', '/browse', '/torrent', '/search.php', '/index.php']
        for a in self._soup.find_all('a', href=True):
            href = a.get('href', '')
            for pat in search_patterns:
                if pat in href:
                    if '{query}' not in href:
                        return f"/search?q={{query}}"
        return "/search?q={query}"

    def _find_list_item_selector(self):
        for pattern in self.LIST_ITEM_PATTERNS:
            try:
                items = self._soup.select(pattern)
                if len(items) >= 3:
                    return pattern
            except:
                pass
        tables = self._soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) >= 3:
                return 'table tr'
        lists = self._soup.find_all(['ul', 'ol'])
        for lst in lists:
            items = lst.find_all('li')
            if len(items) >= 3:
                return f"{lst.name} li"
        return 'div.item'

    def _find_title_selector(self):
        for pattern in self.TITLE_PATTERNS:
            try:
                items = self._soup.select(pattern)
                if len(items) >= 3:
                    hrefs = [a.get('href', '') for a in items if a.name == 'a']
                    if any('/torrent/' in h or '/view/' in h or '/info/' in h for h in hrefs):
                        return pattern
            except:
                pass
        links = self._soup.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            if '/torrent/' in href or '/view/' in href or '/info/' in href:
                parent = link.parent
                if parent:
                    grandparent = parent.parent
                    if grandparent:
                        tag = grandparent.name or 'div'
                        return f"{tag} a[href*='/torrent/'],{tag} a[href*='/view/'],{tag} a[href*='/info/']"
        return 'a[href*="/torrent/"]'

    def _find_magnet_selector(self):
        for pattern in self.MAGNET_PATTERNS:
            try:
                items = self._soup.select(pattern)
                if len(items) >= 1:
                    return pattern
            except:
                pass
        return 'a[href^="magnet:"]'

    def _find_size_selector(self):
        for pattern in self.SIZE_PATTERNS:
            try:
                items = self._soup.select(pattern)
                if len(items) >= 3:
                    return pattern
            except:
                pass
        return 'span.size'

    def _find_date_selector(self):
        for pattern in self.DATE_PATTERNS:
            try:
                items = self._soup.select(pattern)
                if len(items) >= 3:
                    return pattern
            except:
                pass
        return 'span.date'

    def _is_parking_page(self):
        """检测页面是否为域名出售/停靠页面"""
        text = self._soup.get_text().lower()
        parking_keywords = [
            'domain is for sale', 'this domain is for sale', 'purchase this domain',
            'domain parking', 'this website is for sale', '域名售卖', '域名出售',
            'buy this domain', 'sedo', 'dan.com', 'godaddy', 'uniregistry',
            'parking page', 'registered at Namecheap', 'registered at GoDaddy'
        ]
        return any(kw.lower() in text for kw in parking_keywords)

    def _detect_waf(self):
        html_lower = self._soup.get_text().lower()
        waf_keywords = [
            'cloudflare', 'checking your browser', 'ddos protection', 'attention required',
            'fingerprint', 'redirect_link', 'challenge', 'challenge-form', 'ray id',
            'wait 5 seconds', 'sucuri', 'incapsula'
        ]
        # 还要检查 script 标签中的特征
        scripts = self._soup.find_all('script')
        for s in scripts:
            s_content = s.string.lower() if s.string else ""
            if any(kw in s_content for kw in ['fingerprint', 'cryptojs', 'redirect_link']):
                return True
        return any(kw in html_lower for kw in waf_keywords)

    def get_browser_dom(self, url):
        """核心组件：使用浏览器驱动获取真实渲染后的 DOM (V3 Fallback)"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            
            # 考虑环境差异，优先使用 python 环境中的驱动
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            
            print(f"  [Browser] Rendering: {url}")
            driver.get(url)
            
            # 等待几秒让 JS 执行完 (挑战通常需要 5 秒以上)
            import time
            time.sleep(8)
            
            page_source = driver.page_source
            driver.quit()
            return page_source
        except Exception as e:
            print(f"  [Browser] Failure: {e}")
            return None


class AIParser:
    @staticmethod
    def _interactive_captcha_allowed():
        if os.getenv("NEBULA_HEADLESS", "").lower() in ("1", "true", "yes"):
            return False
        if os.getenv("CI", "").lower() in ("1", "true", "yes"):
            return False
        return True

    def __init__(self):
        self.browser = None
        # OpenAI-compatible providers (env; no secrets in repo)
        self._volces_key = os.getenv("VOLCES_API_KEY") or os.getenv("ARK_API_KEY")
        self._volces_url = os.getenv(
            "VOLCES_API_URL",
            "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        )
        self._volces_model = os.getenv("VOLCES_MODEL", "qvq-max-2025-03-25")
        self._openai_key = os.getenv("OPENAI_API_KEY")
        self._openai_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
        self._openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        self._deepseek_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1").rstrip("/")
        self._deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self._gemini_key = os.getenv("GEMINI_API_KEY")
        self._gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        # 备用解析规则（当 LLM 失败时使用）
        self.default_rules = {
            'https://animetosho.org': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.home_list_entry',
                            'title': 'div.link a',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'div.size',
                            'date': 'div.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://btso.cc': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="/info/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://btdb.to': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.result',
                            'title': 'a[href^="/detail/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://btsow.com': {
                'search': {
                    'request_template': '/search/{query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="/info/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://verycd.com': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="/topics/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://extratorrent.ag': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.torrent',
                            'title': 'a[href^="/torrent/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://btfans.com': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="/thread-"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': True
                }
            },
            'https://limetorrents.cc': {
                'search': {
                    'request_template': '/index.php?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'tr.torrent',
                            'title': 'a[href^="/torrent/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'td.size',
                            'date': 'td.date'
                        }
                    },
                    'requires_waf_bypass': True
                }
            },
            'https://bitport.io': {
                'search': {
                    'request_template': '/index.php?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.torrent',
                            'title': 'a[href^="/torrent/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://kickasstorrents.bz': {
                'search': {
                    'request_template': '/search/{query}/',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.torrent',
                            'title': 'a[href^="/torrent/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': True
                }
            },
            'https://btbtt12.com': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="/thread-"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://btcake.com': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="/info/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://cilimao.com': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="/info/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            },
            'https://种子搜索.com': {
                'search': {
                    'request_template': '/search?q={query}',
                    'parse_metadata': {
                        'selectors': {
                            'list_item': 'div.item',
                            'title': 'a[href^="/info/"]',
                            'magnet': 'a[href^="magnet:"]',
                            'size': 'span.size',
                            'date': 'span.date'
                        }
                    },
                    'requires_waf_bypass': False
                }
            }
        }

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

        # 重新初始化浏览器，确保每次处理验证码时都使用新的浏览器实例
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
                    
                    # 关闭浏览器
                    self.browser.quit()
                    self.browser = None
                    
                    return page_source
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
    
    def get_clean_dom(self, url):
        """Get clean HTML DOM tree from a URL"""
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            if response.status_code == 200:
                # 检查是否需要人机验证
                if 'captcha' in response.text.lower() or 'cloudflare' in response.text.lower():
                    print(f"需要人机验证: {url}")
                    if not self._interactive_captcha_allowed():
                        print("  (headless: cannot solve CAPTCHA here)")
                        return None
                    captcha_result = self.handle_captcha(url)
                    if captcha_result:
                        # 使用验证后的页面内容
                        soup = BeautifulSoup(captcha_result, 'lxml')
                        # Remove script and style tags
                        for script in soup(['script', 'style']):
                            script.decompose()
                        return soup.prettify()
                    # 如果验证失败，返回 None
                    return None
                soup = BeautifulSoup(response.text, 'lxml')
                # Remove script and style tags
                for script in soup(['script', 'style']):
                    script.decompose()
                return soup.prettify()
            elif response.status_code == 403:
                print(f"403 禁止访问: {url}")
                if not self._interactive_captcha_allowed():
                    print("  (headless: skipping interactive bypass)")
                    return None
                captcha_result = self.handle_captcha(url)
                if captcha_result:
                    # 使用验证后的页面内容
                    soup = BeautifulSoup(captcha_result, 'lxml')
                    # Remove script and style tags
                    for script in soup(['script', 'style']):
                        script.decompose()
                    return soup.prettify()
                # 如果验证失败，返回 None
                return None
        except Exception as e:
            print(f"Error getting DOM from {url}: {e}")
        return None
    
    def generate_prompt(self, url, dom):
        """Generate prompt for LLM to extract parsing rules"""
        return f"""
You are an expert web scraper and parser. I need you to analyze the following website and extract the necessary information to build a torrent search parser.

Website URL: {url}

HTML DOM:
{dom[:5000]}...  # Truncated for brevity

Please extract the following information in JSON format:

1. search_path: The URL path for searching torrents. It should include a {{query}} placeholder for the search term.
   Example: "/search?q={{query}}" or "/torrents/search/{{query}}"

2. selectors: CSS selectors for the following elements:
   - list_item: The main container for each torrent result
   - title: The element containing the torrent title
   - magnet: The element containing the magnet link (href attribute)
   - size: The element containing the file size
   - date: The element containing the upload date (optional)

3. requires_waf_bypass: Boolean indicating if the site uses Cloudflare or other WAF protection

Format your response as a JSON object with no additional text:

{{
  "search_path": "...",
  "selectors": {{
    "list_item": "...",
    "title": "...",
    "magnet": "...",
    "size": "...",
    "date": "..."
  }},
  "requires_waf_bypass": false
}}
"""
    
    def _post_openai_compatible_chat(self, api_key, chat_url, model, prompt):
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2000,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(chat_url, headers=headers, json=data, timeout=60)
        if response.status_code != 200:
            print(f"Chat API error {response.status_code}: {response.text[:500]}")
            return None
        response_data = response.json()
        choices = response_data.get("choices") or []
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content") or ""
        return _extract_json_object(content)

    def _parse_with_gemini(self, url, dom):
        if not self._gemini_key:
            return None
        try:
            import google.generativeai as genai
        except ImportError:
            return None
        try:
            genai.configure(api_key=self._gemini_key)
            model = genai.GenerativeModel(self._gemini_model)
            prompt = self.generate_prompt(url, dom)
            r = model.generate_content(prompt)
            text = (getattr(r, "text", None) or "").strip()
            return _extract_json_object(text)
        except Exception as e:
            print(f"Gemini parse error: {e}")
        return None

    def parse_with_llm_fallback(self, url, dom):
        """Try Volces/ARK → OpenAI → DeepSeek → Gemini until one returns valid JSON rules."""
        prompt = self.generate_prompt(url, dom)
        if self._volces_key:
            rules = self._post_openai_compatible_chat(
                self._volces_key, self._volces_url, self._volces_model, prompt
            )
            if rules and isinstance(rules, dict) and rules.get("selectors"):
                print("LLM: Volces/ARK OK")
                return rules
        if self._openai_key:
            chat_url = f"{self._openai_base}/chat/completions"
            rules = self._post_openai_compatible_chat(
                self._openai_key, chat_url, self._openai_model, prompt
            )
            if rules and isinstance(rules, dict) and rules.get("selectors"):
                print("LLM: OpenAI-compatible OK")
                return rules
        if self._deepseek_key:
            chat_url = f"{self._deepseek_base}/chat/completions"
            rules = self._post_openai_compatible_chat(
                self._deepseek_key, chat_url, self._deepseek_model, prompt
            )
            if rules and isinstance(rules, dict) and rules.get("selectors"):
                print("LLM: DeepSeek OK")
                return rules
        rules = self._parse_with_gemini(url, dom)
        if rules and isinstance(rules, dict) and rules.get("selectors"):
            print("LLM: Gemini OK")
            return rules
        if not any(
            [self._volces_key, self._openai_key, self._deepseek_key, self._gemini_key]
        ):
            print(
                "No LLM API key set (VOLCES/ARK, OPENAI, DEEPSEEK, or GEMINI); "
                "skipping remote rule extraction."
            )
        return None
    
    def extract_parsing_rules(self, url):
        """Extract parsing rules for a source. Returns structured Search object."""
        print(f"\nExtracting parsing rules for: {url}")

        rules_data = None
        for domain, rules in self.default_rules.items():
            if domain in url:
                print("Using default parsing rules")
                rules_data = rules
                break

        if not rules_data:
            dom = self.get_clean_dom(url)
            if dom:
                parser = LocalHeuristicParser(url)
                rules_data = parser.parse(dom)

        if rules_data:
            # Wrap into Project Nebula structure
            # Handle if rules_data is already nested (from default_rules) or flat (from parser)
            if 'search' in rules_data:
                return rules_data['search']
            
            return {
                'request_template': rules_data.get('search_path', '/search?q={query}'),
                'parse_metadata': {
                    'selectors': rules_data.get('selectors', {})
                },
                'requires_waf_bypass': rules_data.get('requires_waf_bypass', False)
            }

        print("No rules extracted")
        return None
    
    def process_sources(self, valid_sources):
        """Process multiple sources to extract parsing rules"""
        print("\n=== 开始 LLM 规则提取过程 ===")
        print(f"待处理的有效磁力源数量: {len(valid_sources)}")
        processed_sources = []
        
        for source in valid_sources:
            search_rules = self.extract_parsing_rules(source['url'])
            if search_rules:
                source['search'] = search_rules
                # For backward compatibility within this script
                source['search_path'] = search_rules['request_template']
                source['selectors'] = search_rules['parse_metadata']['selectors']
                source['requires_waf_bypass'] = search_rules['requires_waf_bypass']
                processed_sources.append(source)
        
        print(f"\nTotal sources with parsing rules: {len(processed_sources)}")
        return processed_sources
