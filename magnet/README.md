# Project Nebula - Cloud Scraper Engine

## 导航站与跳转站工具索引（先读）

当前项目把数据分成两张表处理，避免把“真实磁力源”和“能发现真实磁力源的辅助站”混在一起：

- `sources.json`：只存真实磁力源，包含候选、绿灯、黄灯、灰灯；`health.status` 只能是 `green|yellow|gray`。
- `auxiliary_sites.json`：只存辅助站，当前重点是 `jump` 跳转站与 `navigation` 导航站；这些站本身不要硬塞回 `sources.json`。

工具选择原则：不要用一个通用工具硬套所有导航站。先判断站点类型，再选对应工具；如果通用工具只能证明“这是导航站”但不能抽出真实候选源，就沉淀样本并新增更细的专用工具。

### 1. 跳转站 / 安全跳板站

- 工具：`python magnet/analyze_navigation_sites.py`
- 功能：识别 `security_center_rdata_gate`、中转链接、薄跳板页，把真实候选域名写入 `auxiliary_sites.json` 的 `real_candidate_origins`。
- 边界：适合“页面主要价值是跳到真实站点”的站；不适合 Cloudflare 空壳、广告页、普通资讯页。
- 用法示例：

```bash
python magnet/analyze_navigation_sites.py --update --out navigation_redirect_follow_report.json
```

- 地址发布页：同一工具会识别 `address_publish_page`，用于 `91btbt.com` 这类只公布最新地址/备用域名/随机子域入口的页面；这类页面写入 `auxiliary_sites.json`，不写入 `sources.json`。

### 2. 详情目录型导航站

- 工具：`python magnet/analyze_navigation_sites.py --direct-origin ... --detail-limit ...`
- 功能：分析尚未进入 `sources.json` 的新发现导航站，收集内部详情页样本到 `candidate_origins`，例如 `https://googax.com/sites/*.html`。
- 边界：适合有大量站点详情页、站点卡片、目录分页的导航站；这里只负责发现和沉淀详情页样本，不直接承担所有详情页解析。
- 用法示例：

```bash
python magnet/analyze_navigation_sites.py --direct-origin https://googax.com --detail-limit 80 --update --out direct_navigation_deep_round.json
```

### 2b. 详情目录页真实源提取器

- 工具：`python magnet/extract_detail_directory_candidates.py`
- 功能：把 `auxiliary_sites.json` 中导航站的 `candidate_origins` 详情页样本转成 `real_candidate_origins`。当前已支持从 `og:image` favicon URL 参数、meta/link/query 参数、按钮属性和页面绝对 URL 中提取真实目标。
- 边界：适合 `googax.com/sites/*.html` 这类详情页目录；不负责发现新导航站，也不负责综合导航站的垂直分区定位。
- 降噪边界：详情页抽出的真实候选必须在域名层命中磁力相关 token（如 `bt`、`cili`、`torrent`、`btsow`、`1337x`、`nyaa` 等）。详情页标题或整站品牌里出现“磁力/BT”只能加分，不能单独放行；这是为了过滤 `xhnav`、`ezhentang` 这类通用导航站的品牌污染。
- 用法示例：

```bash
python magnet/extract_detail_directory_candidates.py --origin https://googax.com --limit-details 40 --update --out googax_detail_candidates_round1.json
```

### 3. 首页外链门户型导航站

- 工具：`python magnet/extract_navigation_candidates.py`
- 功能：从已经确认的导航站首页或目录页中提取真实外链候选，生成 `navigation_real_candidates*.json`。
- 边界：适合首页/栏目页直接暴露外链的导航站；不负责发现新导航站，也不负责处理跳板解码或详情页内二次跳转。
- 用法示例：

```bash
python magnet/extract_navigation_candidates.py --out navigation_real_candidates.json
```

### 3b. 代理列表型导航站

- 工具：`python magnet/analyze_navigation_sites.py --direct-origin ...`
- 功能：识别 `torrent proxy list`、`unblock torrent sites`、`mirror sites` 这类国外代理目录页。它们通常没有内部详情页，但会直接列出大量 Pirate Bay、1337x、RARBG、Limetorrents、Torrentz 等代理/镜像外链。
- 边界：适合 `https://torrends.to/proxy/` 这类路径级导航页；发现器必须保留 `/proxy/` 等路径，不能只分析裸域名。
- 用法示例：

```bash
python magnet/analyze_navigation_sites.py --direct-origin https://torrends.to/proxy/ --timeout 45 --update --out torrends_proxy_navigation_report.json
```

### 4. 国外搜索引擎发现器

- 工具：`python magnet/discover_nav_sites_search.py`
- 功能：用 Google / DuckDuckGo / Bing 思路发现新的导航站种子；当前环境下 DuckDuckGo HTML 最稳定，Google 无 JS 页面经常只返回壳页。该工具也会从榜单/文章页抽出候选外链。
- 边界：国外榜单文章更容易产出“真实磁力源候选”，不一定产出“导航站”；文章页候选要降噪后再进入候选池。
- `--seed-only`：当国外搜索结果已经由人工/外部工具挑出一批中文种子时使用，只复核 `--seed-origin`，跳过默认搜索，避免 DDG 英文榜单和文章结果挤掉中文种子。
- 用法示例：

```bash
python magnet/discover_nav_sites_search.py --top 30 --update --seed-origin https://googax.com --out nav_search_discovery_report.json
python magnet/discover_nav_sites_search.py --seed-only --seed-origin https://www.zjnav.com/sites/24772.html --update --out nav_seed_only_report.json
```

### 5. 辅助候选池与 funnel 验证

- 工具：`python magnet/build_aux_candidate_pool.py` + `python magnet/funnel_pipeline.py`
- 功能：汇总 `auxiliary_sites.json` 中 `jump/navigation` 产出的真实候选源，生成候选池，再用 funnel 把可用站推进到绿灯/黄灯分层。
- 边界：这里只验证候选源可用性，不负责从详情页或跳板页提取新候选。
- 搜索 bait：funnel 同时使用英文与中文 bait（如 `Inception`、`mp4`、`权力的游戏`、`战狼2`、`流浪地球`），用于提高中文磁力站的通用搜索命中率。
- 用法示例：

```bash
python magnet/build_aux_candidate_pool.py --out aux_candidate_pool.json --min-score 7 --min-support 1
python magnet/funnel_pipeline.py --candidates aux_candidate_pool.json --out aux_funnel_report.json --summary-out aux_funnel_summary.json --stage3
```

### 6. 待补专用工具方向

- `googax.com/sites/*.html` 详情页提取器：已先落地为 `extract_detail_directory_candidates.py`，下一步是继续提高 Cloudflare 批量兜底成功率和详情页强证据覆盖率。
- 综合导航站垂直分区提取器：面向 `neednav.com`、`litxdh.com` 这类大而泛的导航站，先定位磁力/BT/下载相关分区，再提取候选，不能直接套详情目录模型。
- 国外榜单页降噪器：面向 PrivacySavvy、Techworm 等文章/榜单页，把资讯站、客户端官网、协议站降权，只保留可能的真实搜索源或下载源。

### 快速决策

- 页面几乎只负责跳转：用跳转站工具，结果写 `auxiliary_sites.json`。
- 页面有很多内部详情页：先用详情目录型导航工具沉淀 `candidate_origins`，再用详情目录页真实源提取器产出 `real_candidate_origins`。
- 页面直接列外部站点：用首页外链门户工具，产出 `real_candidate_origins`。
- 页面是国外 torrent proxy / mirror 列表：保留完整路径，用代理列表型导航站逻辑产出 `real_candidate_origins`。
- 还不知道新站在哪：用国外搜索引擎发现器，优先 DDG 结果和人工种子。
- 已经拿到真实候选源：用辅助候选池 + funnel 验证，只有验证后才推进 `sources.json` 健康状态。

一个自动化爬取最新可用磁力源的工具，为跨平台客户端提供高质量的磁力链接源。

## 项目架构

- **Discovery 模块**: 自动寻找新的磁力源，包括搜索引擎 Dorking 和友链递归嗅探
- **Validation 模块**: 测试源的健康度，包括延迟检测和资源质量验证
- **AI Parser 模块**: 使用 LLM 提取解析规则，包括搜索接口和 CSS 选择器
- **Sources Manager**: 生成和更新 sources.json 文件

## 安装依赖

```bash
pip install -r requirements.txt
```

## 环境变量配置

在 `.env` 文件中配置以下环境变量：

```
# Search Engine API Keys
BING_API_KEY=
DUCKDUCKGO_API_KEY=

# LLM API Keys
GEMINI_API_KEY=
ANTHROPIC_API_KEY=

# Configuration
TIMEOUT=3000
MAX_SOURCES=50
```

## 使用方法

### 本地运行

```bash
python main.py
```

### 定时运行

项目配置了 GitHub Actions 工作流，每天自动执行爬取任务。需要在 GitHub 仓库的 Secrets 中配置以下密钥：

- `BING_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`

## 输出文件

- `sources.json`: 包含所有有效的磁力源及其解析规则

## 技术栈

- Python 3.10+
- requests
- beautifulsoup4
- lxml
- selenium
- google-generativeai
- anthropic
- python-dotenv
