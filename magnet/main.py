#!/usr/bin/env python3
"""Main script for Project Nebula - Cloud Scraper Engine"""

from discovery.discovery import Discovery
from validation.validation import Validation
from ai_parser.ai_parser import AIParser
from utils.sources_manager import SourcesManager
from crawler.healer import Healer

def main():
    print("=== Project Nebula - Cloud Scraper Engine ===")
    print("启动自动化磁力源发现和验证流程...\n")
    
    # 测试模式，限制运行时间
    print("=== 测试模式: 优化运行时间 ===")
    
    # Step 1: 发现新磁力源
    print("\n=== 步骤 1: 发现新磁力源 ===")
    discovery = Discovery()
    sources = discovery.discover_all()
    
    print(f"\n=== 发现结果 ===")
    print(f"发现的磁力源数量: {len(sources)}")
    if sources:
        print("前 5 个发现的磁力源:")
        for source in sources[:5]:
            print(f"- {source}")
    
    if not sources:
        print("未发现磁力源，退出程序。")
        return
    
    # 获取动态生成的诱饵词
    print("\n=== 步骤 2: 生成动态诱饵词 ===")
    baits = discovery.get_baits()
    print(f"生成的诱饵词数量: {len(baits)}")
    if baits:
        print("前 5 个生成的诱饵词:")
        for bait in baits[:5]:
            print(f"- {bait}")
    
    # Step 3: 验证磁力源
    print("\n=== 步骤 3: 验证磁力源 ===")
    validation = Validation(baits)
    valid_sources = validation.validate_sources(sources)
    
    print(f"\n=== 验证结果 ===")
    print(f"通过验证的磁力源数量: {len(valid_sources)}")
    if valid_sources:
        print("通过验证的磁力源:")
        for source in valid_sources:
            score = source.get('quality', {}).get('score', 0)
            print(f"- {source['url']} (评分: {score}%)")
    
    if not valid_sources:
        print("未找到有效磁力源，退出程序。")
        return
    
    # Step 4: 使用 LLM 提取解析规则
    print("\n=== 步骤 4: 使用 LLM 提取解析规则 ===")
    ai_parser = AIParser()
    processed_sources = ai_parser.process_sources(valid_sources)
    
    print(f"\n=== 规则提取结果 ===")
    print(f"成功提取解析规则的磁力源数量: {len(processed_sources)}")
    if processed_sources:
        print("成功提取解析规则的磁力源:")
        for source in processed_sources:
            print(f"- {source['url']}")
    
    if not processed_sources:
        print("未找到具有解析规则的磁力源，退出程序。")
        return
    
    # Step 5: 生成/更新 sources.json
    print("\n=== 步骤 5: 生成/更新 sources.json ===")
    sources_manager = SourcesManager()
    success = sources_manager.update_sources_json(processed_sources)

    if not success:
        print("\n=== 处理失败！ ===")
        print("无法更新 sources.json 文件。")
        return

    # Step 6: 自愈验证（确保每个源真能抽出磁力）
    print("\n=== 步骤 6: 自愈验证 ===")
    healer = Healer()
    heal_results = healer.heal_all_sources(processed_sources)
    heal_report = healer.save_report(heal_results)

    ok_count = heal_report['ok']
    healed_count = heal_report['healed']
    failed_count = heal_report['failed']

    print(f"\n=== 自愈结果 ===")
    print(f"直接成功: {ok_count}, 自愈成功: {healed_count}, 失败: {failed_count}")

    valid_final = [
        r for r in heal_results
        if r.get('status') in ('ok', 'healed') and r.get('magnets_found', 0) > 0
    ]

    if valid_final:
        final_sources = []
        for r in valid_final:
            url = r.get('url')
            for src in processed_sources:
                if src.get('url') == url:
                    merged = {**src}
                    if r.get('healed_selectors'):
                        # Update the nested selectors
                        if 'search' not in merged:
                            merged['search'] = {'parse_metadata': {'selectors': {}}}
                        merged['search']['parse_metadata']['selectors'] = r['healed_selectors']
                    final_sources.append(merged)
                    break
        sources_manager.update_sources_json(final_sources)
        print(f"\n=== 最终有效磁力源: {len(final_sources)} ===")
    else:
        print("\n=== 没有通过自愈验证的磁力源 ===")

    print("\n=== 处理完成！ ===")

if __name__ == "__main__":
    main()
