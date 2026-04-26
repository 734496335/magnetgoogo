# Project Nebula: Self-Healing Magnet Crawler
**Cursor AI Handover Document**

Hello Cursor! This document provides all the necessary context to seamlessly pick up the development of this project. The previous AI session was paused due to API quota exhaustion (Google Free Tier 429 limits). 

## 1. 核心业务架构与目标 (Project Goal)
本项目是一个“自愈式磁力聚合爬虫引擎”，旨在摆脱传统静态爬虫极易失效的痛点。
- **动态寻址与探针**：在本地模拟访问各大磁力源（如 `1337x`, `nyaa`, `bitsearch`）。
- **惰性自愈 (Lazy Healing)**：爬虫平时使用存储的静态 CSS 选择器。一旦检测到版面变更或失效（搜不到数据），将报错 HTML 传递给大语言模型（Gemini GenAI），让 AI 分析新的版面并重新生成 CSS 选择器规则，实现“结构自愈”。
- **反爬突破 (WAF Bypass)**：由于爬虫经常遭遇 Cloudflare（五秒盾），系统内置了 Playwright 实现真机/人工辅助绕过，再将 Cookie/UA 接力给底层的 HTTPX 客户端，最大限度降低爬取开销并在云端阻拦前取得真实 HTML 以供解析。

## 2. 核心文件与模块状态 (Module Status)
目前基础拓荒层（模块一）已完成 90% 以上的工作流编写与调优。

- **`ai_parser.py` (AI 解析大脑)**：
  - **职责**：封装 Google GenAI 客户端，向 AI 发送被屏蔽或结构失效站点的 HTML，获取结构化的 JSON 选择器（`list_item`, `title`, `magnet`, `size`, `date` 等）。
  - **当前特性**：实现了完备的多模型回退机制 (Fallback Cascade)，能自动在 `gemini-2.5-flash` 和开源模型（如 `gemma-3`）之间切换以对抗限流。具有 CF 盾牌防御，遇到无意义的 Challenge 页面会中止请求拒绝浪费额度。
- **`scoring_engine.py` (站点评分探针引擎)**：
  - **职责**：负责实机请求和分数测定评估。
  - **当前特性**：完善的 WAF 检测，以及最底层的 Playwright Fallback，能够动态监听 `networkidle` 并捕获重定向后的真实页面结构。新增了 **二段式详情页解析逻辑 (2-Step Extraction)**，处理某些只在内页暴露 Magnet 链接的网站。
- **`bait_generator.py` (探针诱饵生成器)**：
  - **职责**：提供高质量的检索诱饵（包含欧美大片、最新流媒体、经典中文版）。
  - **当前特性**：已加入业界泛用成人诱饵（如 `SSNI`），以供如 `sukebei.nyaa.si` 这类垂直站探测。
- **`test_extraction.py` (主测试流沙盒)**：
  - **职责**：全节点遍历验证。
  - **当前特性**：通过对失败诱饵更换以及自愈流程进行实弹演练。一旦 AI 提供新规则，立即持久化回 `tracker_db.json`。
- **`tracker_db.json` (数据库持久层)**：记录各个站点的最新健康分数、上次检查时间及当前可用的抽取选择器。

## 3. 最后解决的几个技术难点 (Recently Solved Issues)
为了防范之后重复踩坑，请注意以下已解决的核心难点：
1. **纯详情页结构 (1337x 缺陷)**：`1337x` 列表页并没有放置原生磁力链，只放置了 `/torrent/xxx` 内页链接。现已在提取器中重构，发现解析到非 `"magnet:?"` 的 `href` 对象时，自动请求详情页获取磁力链。
2. **特殊垂直源零结果报错 (Sukebei 缺陷)**：使用常规电影名在成人源中搜索为空，爬虫曾误判为“规则失效”从而白白消耗 AI 额度。如今已经在探测池补入特定关键字，确保有效区分“无结果”和“结构损毁”。
3. **Playwright 竞态条件崩溃**：过早采集页面遇到了 `Execution context was destroyed` 的报错，现代码已增加安全的 `attempt` 轮询和异常处理，捕获到包含 `table/list` 实量 DOM 后才会终止模拟。

## 4. 后续开发核心诉求 (Next Objectives for Cursor)
接手后，你首先需要跟用户确认/推进这几件事：

*   [ ] **API Quota 瓶颈**：当前用户的免费 Gemini 账户已限流崩溃 (429 RESOURCE_EXHAUSTED)。可尝试转为使用 Cursor 提供的代理大模型，或帮助用户切换至 DeepSeek / OpenAI / 其他免费 LLM 提供商来驱动 `ai_parser.py`。
*   [ ] **无头化运维 (Headless Deployment)**：目前的 Playwright 绕过默认使用 `headless=False` 强依赖人工界面（如果遇到强验证码）。如果该脚本是在远端运行，需要植入诸如 `playwright-stealth` 结合代理池的纯无头解法。
*   [ ] **主引擎串联**：将散落在 `test_extraction.py` 和 `scoring_engine.py` 的精调逻辑整合进入主流程服务 `pipeline_runner.py`。
*   [ ] **开始模块二 (APP & API)**：本项目最终目的是供给移动端消费这些发现的有效种子源。接下来是实现定时任务，对外输出干净整合的 `magnet_sources.json` 和开发 React Native / Flutter 移动端。

> Happy Coding! 🚀
