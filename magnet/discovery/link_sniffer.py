import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

class LinkSniffer:
    def __init__(self):
        self.visited = set()
        self.base_domains = [
            'https://thepiratebay.org',
            'https://1337x.to',
            'https://rarbg.to',
            'https://limetorrents.info',
            'https://torrentz2.eu'
        ]
    
    def extract_friendship_links(self, url):
        links = set()
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Common friendship link locations
                link_sections = soup.select('div.footer, div.links, ul.footer-links, div.friendship-links')
                
                for section in link_sections:
                    for a in section.find_all('a', href=True):
                        href = a['href']
                        absolute_url = urljoin(url, href)
                        
                        # Extract domain
                        parsed = urlparse(absolute_url)
                        domain = f"{parsed.scheme}://{parsed.netloc}"
                        
                        if domain not in self.visited:
                            links.add(domain)
        except Exception as e:
            print(f"Error extracting links from {url}: {e}")
        
        return links
    
    def recursive_sniff(self, depth=2):
        all_sources = set()
        
        for base_domain in self.base_domains:
            if base_domain not in self.visited:
                self.visited.add(base_domain)
                
                # Extract links from base domain
                links = self.extract_friendship_links(base_domain)
                all_sources.update(links)
                
                # Recursive depth
                if depth > 1:
                    for link in links:
                        if link not in self.visited:
                            self.visited.add(link)
                            deeper_links = self.extract_friendship_links(link)
                            all_sources.update(deeper_links)
        
        return list(all_sources)
