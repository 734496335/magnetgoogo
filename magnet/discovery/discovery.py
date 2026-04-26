from .search_engine import SearchEngine
from .link_sniffer import LinkSniffer

class Discovery:
    def __init__(self):
        self.search_engine = SearchEngine()
        self.link_sniffer = LinkSniffer()
    
    def discover_all(self):
        print("开始发现过程...")
        
        # Step 1: Search engine dorking
        print("\n--- 搜索引擎搜索 ---")
        search_sources = self.search_engine.discover_sources()
        print(f"从搜索引擎发现的磁力源数量: {len(search_sources)}")
        
        # Step 2: 友情链接嗅探
        print("\n--- 友情链接嗅探 ---")
        link_sources = self.link_sniffer.recursive_sniff()
        print(f"从友情链接发现的磁力源数量: {len(link_sources)}")
        
        # Step 3: 合并和去重
        all_sources = list(set(search_sources + link_sources))
        print(f"\n去重后的磁力源总数: {len(all_sources)}")
        
        return all_sources
    
    def get_baits(self):
        """获取动态生成的诱饵词"""
        return self.search_engine.bait_generator.generate_baits()
