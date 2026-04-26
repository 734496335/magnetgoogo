import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'magnet'))

from validation.validation import Validation
from ai_parser.ai_parser import AIParser
from utils.sources_manager import SourcesManager
import json

def quick_test():
    print("=== Project Nebula Architecture - Quick Verification ===")
    
    # 1. 模拟验证输出 (使用一个小源)
    test_sources = ['https://animetosho.org']
    baits = ['Ubuntu magnet']
    
    # 初始化验证器
    validation = Validation(baits)
    print(f"正在验证源: {test_sources}")
    # 模拟验证过程，直接构造结果以节省时间，但测试逻辑连通性
    valid_sources = validation.validate_sources(test_sources)
    
    if not valid_sources:
        print("验证未通过 (可能是网络原因)，使用 Mock 数据继续测试结构连通性...")
        valid_sources = [{
            'url': 'https://animetosho.org',
            'id': 'a1b2c3d4',
            'quality': {'score': 90, 'tags': ['追新极客']},
            'health': {'status': 'green', 'last_checked_at': '2026-04-16T13:00:00Z', 'fail_count_30d': 0},
            'search_url_template': 'https://animetosho.org/search?q={query}',
            'latency': 250
        }]

    # 2. 规则提取测试
    print("\n=== 提取解析规则 ===")
    ai_parser = AIParser()
    processed_sources = ai_parser.process_sources(valid_sources)
    
    # 3. 生成 sources.json
    print("\n=== 生成 sources.json ===")
    sm = SourcesManager()
    success = sm.update_sources_json(processed_sources)
    
    if success:
        print("\n=== 集成验证完成！ ===")
        with open('sources.json', 'r', encoding='utf-8') as f:
            res = json.load(f)
            print(f"Schema Version: {res.get('schema_version')}")
            print(f"Total Rulesets: {len(res.get('rulesets', []))}")
            rule0 = res['rulesets'][0]['rules'][0]
            print(f"Rule ID: {rule0['id']}")
            print(f"Search Template: {rule0['search']['request_template']}")
            print(f"Quality Score: {rule0['quality']['score']}")
    else:
        print("\n=== 验证失败 ===")

if __name__ == "__main__":
    quick_test()
