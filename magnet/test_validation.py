#!/usr/bin/env python3
"""Test script for magnet source validation"""

from validation.validation import Validation
from ai_parser.ai_parser import AIParser
from utils.sources_manager import SourcesManager

# 预定义的磁力源列表
test_sources = [
    'https://animetosho.org',
    'https://btso.cc',
    'https://btdb.to',
    'https://limetorrents.cc',
    'https://btfans.com',
    'https://limetorrents.fun',  # 主域名
    'https://limetorrents.asia',  # 代理域名
    'https://limetorrents.co',   # 代理域名
    'https://limetorrents.zone', # 代理域名
    'https://limetor.com'        # 代理域名
]

# 预定义的诱饵词
test_baits = [
    '肖申克的救赎 磁力',
    '这个杀手不太冷 磁力',
    '阿甘正传 磁力',
    '楚门的世界 magnet',
    '泰坦尼克号 磁力',
    '星际穿越 magnet',
    '盗梦空间 磁力',
    '千与千寻 magnet',
    '美丽人生 磁力',
    '霸王别姬 magnet'
]

def test_validation():
    print("=== 测试磁力源访问和质量验证功能 ===")
    print(f"测试的磁力源数量: {len(test_sources)}")
    
    # 初始化验证器
    validation = Validation(test_baits)
    
    # 验证磁力源
    valid_sources = validation.validate_sources(test_sources)
    
    print(f"\n=== 验证结果 ===")
    print(f"通过验证的磁力源数量: {len(valid_sources)}")
    if valid_sources:
        print("通过验证的磁力源:")
        for source in valid_sources:
            score = source.get('quality', {}).get('score', 0)
            print(f"- {source['url']} (评分: {score}%)")
    
    if not valid_sources:
        print("未找到有效磁力源，退出测试。")
        return
    
    # 使用 LLM 提取解析规则
    print("\n=== 提取解析规则 ===")
    ai_parser = AIParser()
    processed_sources = ai_parser.process_sources(valid_sources)
    
    print(f"\n=== 规则提取结果 ===")
    print(f"成功提取解析规则的磁力源数量: {len(processed_sources)}")
    if processed_sources:
        print("成功提取解析规则的磁力源:")
        for source in processed_sources:
            print(f"- {source['url']}")
    
    if not processed_sources:
        print("未找到具有解析规则的磁力源，退出测试。")
        return
    
    # 生成 sources.json
    print("\n=== 生成 sources.json ===")
    sources_manager = SourcesManager()
    success = sources_manager.update_sources_json(processed_sources)
    
    if success:
        print("\n=== 测试完成！ ===")
        print(f"最终成功获取到的可用磁力源数量: {len(processed_sources)}")
        print("这些磁力源已经通过诱饵库测试，能正确解析找到磁力源的搜索框、进行搜索，并返回正确磁力链。")
    else:
        print("\n=== 测试失败！ ===")
        print("无法更新 sources.json 文件。")

if __name__ == "__main__":
    test_validation()
