# Project Nebula — 技术难点追踪 & 突破调研

> **目的**：把当下卡住业务的技术难题集中记录，定期（每 2 周）扫一遍 GitHub Trending / HackerNews / arXiv，找现成方案做窄替换。
> **写入规则**：每个难题一节，一个难题失效或被解决 → 改 status 为 ✅，**不删除**（保留为档案）。
> **与 DEV-LOG 关系**：DEV-LOG 是会话级流水账；本文是难题级长生命周期文档。难点突破后在 DEV-LOG 写实施记录，本文同步更新 status。

---

## 文档结构 / 模板

每个难题用以下骨架：

```
### CHALLENGE-{编号} — {一句话标题}
- **严重程度**：[blocker | high | medium | low]
- **状态**：[open | researching | piloting | solved ✅ | abandoned]
- **首次记录**：YYYY-MM-DD
- **业务影响**：（一段话，量化最好：影响多少 % 流量/源/转化）
- **当前方案 & 缺陷**：
- **已尝试**（按时间倒序）：
- **候选方案**（GitHub/论文/产品 + 简评 + 难度估计）：
- **下一步**：
- **更新日志**：YYYY-MM-DD —— xxx
```

---

## 当前难点列表（按严重度）

| ID | 标题 | 严重 | 状态 | 最新动作 |
|---|---|---|---|---|
| [CH-001](#challenge-001--页面解析在 spa--非标准列表站上失败) | 页面解析在 SPA / 非标准列表站上失败 | **blocker** | researching | 2026-05-21 调研完成 |
| [CH-002](#challenge-002--cloudflare-turnstile-交互式-captcha-无法绕过) | Cloudflare Turnstile 交互式 CAPTCHA 无法绕过 | high | piloting | Scrapling StealthyFetcher 已集成（v2） |
| [CH-003](#challenge-003--中国大陆环境-海外-bt-站-dns-污染--gfw-阻断) | ~~GFW 阻断~~ → **健康检查误判** | low | partially-debunked | 2026-05-21 实测：GFW 影响 0%，误判 48% |
| [CH-004](#challenge-004--llm-修复-selector-成本--延迟) | LLM 修复 selector 成本/延迟过高 | medium | open | — |
| [CH-005](#challenge-005--域名漂移--死链发现滞后) | 域名漂移 / 死链发现滞后 | medium | open | — |

---

## CHALLENGE-001 — 页面解析在 SPA / 非标准列表站上失败

- **严重程度**：**blocker**（爬虫 V2 突破 WAF 后的真正瓶颈）
- **状态**：researching → 准备 piloting AutoScraper
- **首次记录**：2026-05-21
- **业务影响**：
  - V1 healer 对 yellow 源的 `parsing_failed` 占比约 30%（基于 yellow 池抽样）
  - V2 引入 Scrapling 后把 V1 标的 WAF 源解锁了（5/8 → 拿到 200 HTML），但其中**没有一个能解析出 magnet**——卡在选择器
  - 直接拖累 yellow→green 晋级率
- **当前方案 & 缺陷**：
  - `magnet/ai_parser/ai_parser.py::LocalHeuristicParser` 启发式找 `tr.torrent / table tbody tr / div.torrent-item` 等固定模式
  - 失败时调 LLM（Volces/OpenAI/DeepSeek/Gemini）让模型读 5KB DOM 输出 selector JSON
  - **缺陷一**：固定 fallback selector 列表覆盖不了非主流站（导航站、SPA、自定义 class）
  - **缺陷二**：LLM 兜底贵且不稳定（5KB DOM 截断丢失关键结构 / 偶发非法 CSS 抛异常 → 整个 healer 崩溃）
  - **缺陷三**：每个 query 重新解析一次，没有"学一次用多次"的机制

### 已尝试（按时间倒序）

1. **2026-05-16** CloakBrowser + 启发式解析（cloak_yellow_verify.py）—— 提升 2 个源到 green，但泛化性差
2. **2026-05-21** Scrapling StealthyFetcher 突破 WAF —— HTML 拿到了，解析仍失败（确认瓶颈在解析器）
3. 多 LLM 接力 fallback —— 偶发 selector `Expected a selector at position 0` 崩溃

### 候选方案 — 实证 Bake-off（2026-05-21）

通过 `_bench_parsers.py` 和 `_bench_parsers_v2.py` 在真实 magnet 站上做了 head-to-head 对比。

#### 实测对比矩阵

| 工具 | 0cili.nl (74 行预期) | 0cili.nl Inception (5 行预期) | fitgirl Witcher | 评价 |
|---|---|---|---|---|
| `v1` LocalHeuristicParser | 0 | 0 | 7 hashes | 硬编码 URL pattern 不通用 |
| AutoScraper (`alirezamika`) | 0 | 0 | 0 | 文本相似度模式，**不识别 URL pattern** |
| Trafilatura | 0 | 0 | 0 | **错的工具** — 文章正文提取，扔掉列表 |
| 全文 regex 40-char hash | 0 | 0 | 15 | 仅适合 hash 直接出现的站 |
| **Smart List Detector（自研，50 行）** | **74 ✓** | **5 ✓** | 0 (search 命中数<阈值) | ⭐ **完胜** |

#### ⭐⭐⭐ 最终选择：自研 Smart List Detector（`magnet/crawler_v2/smart_list.py`）

**核心思想（业界 wrapper-induction 经典思路 + 我们场景定制）**：
1. **URL path-shape 归纳**：`/!bfUI`→`/!N`、`/torrent/123`→`/torrent/N`、`/view/abc.html`→`/view/N.html`
2. **同结构兄弟节点聚类**：`(tag, anchor-path-shapes)` 相同的元素聚为一组 = 候选列表行
3. **三重过滤**：
   - 行 anchor href 都相同 → 重复 CTA banner，剔除
   - 中位行文本 < 30 字符 → 侧边栏/归档 widget，剔除
   - 最终去重 detail_url 后 < 3 行 → 误检，返回空
4. **评分** `n^0.7 × median_text_len`，平衡数量与单行内容质量
5. **行内 title 提取**：长文本优先 + CTA 关键词惩罚（donate/login/share/...）

**为什么完胜其它候选**：
- 对 0cili.nl 这种**短 ID URL（`/!XXXX`）的 SPA 模式**，v1 的硬编码 `['/torrent/','/view/','/info/'...]` 完全识别不了，AutoScraper 因为基于文本相似度也学不会，Smart Detector 通过 URL 结构归纳直接命中
- 不依赖外部库（仅 BS4 + 标准库）、不需要训练数据、不调 LLM
- 单文件 ~110 行，可读可维护

#### ⭐⭐ 备选：Trafilatura（adbar/trafilatura）—— 仅用于辅助任务

- 不用于列表提取（实证失败）
- **可用**：强化 `_detect_parking()` 判断（基于"无主体内容"信号比关键字匹配准确）
- **可用**：HTML 预处理，去 nav/footer 后再让 LLM healer 读，减少 token

#### ⭐ 调研后排除（详细理由）

- **AutoScraper（alirezamika）**：基于文本-XPath 匹配，对 URL-pattern 类列表（如 0cili.nl 的 `/!XXXX`）失效；且 sources.json 中现有 sample_title 是陈旧的、跟当前 query 不匹配
- **Crawl4AI**（unclecode/crawl4ai）：和 Scrapling 严重重叠，默认产出 markdown 仍需 LLM 二次提取
- **ScrapeGraphAI**：核心是 Pydantic schema + LLM，付费且成本不可控
- **Firecrawl**：hosted SaaS，对"上千个不同站"经济性差
- **LLM Scraper**（mishushakov）：纯 TypeScript，栈不匹配
- **Reader-LM (Jina, 1.5B) / MarkItDown / dragnet / dude**：HTML→Markdown 或 article extractors，不是 list extractors

### 已交付

- ✅ `magnet/crawler_v2/smart_list.py` — Smart List Detector 主模块（empirical-winner）
- ✅ `magnet/_bench_parsers.py` / `_bench_parsers_v2.py` — bake-off 工具（可重跑回归）
- ⏭ TODO：把 `detect_list_rows()` 接入 `crawler_v2/extractor.py` 作为启发式之前的优先路径
- ⏭ TODO：对 detail_url 做二次抓取以提取 magnet（v1 已有 `_fetch_detail_page` 逻辑可复用）
- ⏭ TODO：用 trafilatura 重写 `_detect_parking()`

### 更新日志

- 2026-05-21 09:00 —— 创建条目，调研结论：AutoScraper 为首选
- 2026-05-21 09:30 —— **实证推翻**：AutoScraper / Trafilatura 在我们的真实场景都 0 命中；自研 Smart List Detector（结构归纳 + 启发式得分）经 bake-off 验证完胜。首选改为自研模块。

---

## CHALLENGE-002 — thatcdn 平台自定义 captcha（原 CF Turnstile，重新定性）

- **严重程度**：high
- **状态**：tier-routed（已在 crawler_v3 架构层留路由位，等 Tier 2 handler 逆向）
- **首次记录**：2026-05-16
- **重新定性时间**：2026-05-28（v3 探针确认）
- **业务影响**：4 个 yellow 源被阻挡（xiongmaogb / lemonun / wuqianso / laowangzo）

### 关键发现（2026-05-28 v3 探针）

之前一直把这事当作"Turnstile"是误判。**实际不是 Cloudflare Turnstile**，而是 thatcdn 平台共用模板 + 服务端的自定义 anti-bot：

| 测试 | URL | 现象 |
|---|---|---|
| 直接 GET 搜索 URL | `https://xiongmaogb.top/search?keyword=spider` | **3.5KB 首页**而非搜索结果 |
| CloakBrowser headless + humanize=True | 同上 | 同样返回首页表单（CF Turnstile 不存在） |
| CloakBrowser 0.3.31 + Chromium 146.0.7680.177.5 | 同上 | 30s 内无变化 |

**结论**：服务端通过未知校验（cookie / referer / JS-set 头）决定是否返回真实结果。CloakBrowser 即使过指纹也无效，因为它根本不是浏览器指纹问题。

同样模式覆盖：xiongmaogb.top / lemonun.top / wuqianso.org / laowangzo.top（共用 `prod.b5.thatcdn.com` CDN + Bootstrap 3.3.7 + 自研 anti-bot）。

### 已尝试（按时间倒序）

1. **2026-05-28** v3 + CloakBrowser 0.3.31 + humanize=True → 仍失败（**确认 CloakBrowser 无效**，跟 v1 结论一致）
2. **2026-05-21** Scrapling StealthyFetcher（Patchright + browserforge） → HTML 拿到了，是首页表单不是结果（确认是服务端逻辑而非指纹）
3. **2026-05-16** CloakBrowser 0.3.x stealth 注入 → 对 CF JS Challenge 有效，对 thatcdn 自定义 anti-bot **无效**

### 当前方案（v3 架构）

`magnet/crawler_v3/handlers/thatcdn.py` 占位 handler 已注册。`sources.json` 4 个 thatcdn yellow 源已配置 `tier_override: tier2_handler/thatcdn`。
路由：`Tier 2 Handler → Tier 0 → Tier 1`（前者未实现就降级，框架已工作）。

### 候选方案

- ⭐⭐⭐ **JS 逆向 thatcdn one.js**（首选，hello_js_reverse_skill + js-reverse-mcp）：
  - 用 Camoufox 进入 xiongmaogb.top，DevTools Network 抓表单提交后真实请求
  - 找到 cookie / token 生成逻辑，翻译成 Python
  - 4 个源一锅端 + 未来同平台新源零成本接入
  - 估算 1–3 天，硬截止 3 天
- **flaresolverr**：对自定义 anti-bot 不一定有效（专门针对 CF）
- **2captcha / capsolver**：thatcdn 不是标准 captcha，付费打码用不上
- **放弃 4 个源**：影响低（同平台总产出 < 5%），但不专业

### 下一步

1. 用 hello_js_reverse_skill workflow 对 thatcdn one.js 做完整逆向
2. 实现 `magnet/crawler_v3/handlers/thatcdn.py::thatcdn_search`
3. 跑 `python -m magnet.crawler_v3 verify-yellow "蜘蛛侠"` 验证 4/4 通过
4. 4 yellow → green，更新 sources.json health.status

### 更新日志

- 2026-05-16 —— 初建（误判为 Turnstile）
- 2026-05-28 —— v3 探针重新定性为 thatcdn 平台自定义 anti-bot；状态改 piloting → tier-routed

---

## CHALLENGE-003 — 中国大陆环境 GFW 阻断海外 BT 站

- **严重程度**：~~high~~ → **downgraded to low**（2026-05-21 实测后）
- **状态**：~~open~~ → **partially-debunked**（核心假设被实测推翻）
- **业务影响**：（修正）实测样本中 GFW 阻断 = 0%；真正问题是**健康检查误判** + **海外站域名真死**
- **当前方案 & 缺陷**：客户端不直接访问海外站；naoshiquan.com CF Workers 反代

### 实测数据（`magnet/_bench_gfw_proxy.py`，2026-05-21）

对 25 个 `gray + unreachable` 源做 noproxy vs TW VPN 对比：

| 类别 | 数量 | 含义 |
|---|---:|---|
| proxy 救活 | **0** | GFW 阻断**不是**主因 |
| 两边都活 = **误判** | **12** | 国内 HTTP 200 但被错标 unreachable |
| 两边都死 = 真死 | 13 | 域名失效，TW 节点也连不上 |

**12 个被误判的源**：`btso.cc`, `btsow.com`, `btcake.com`, `种子搜索.com`, `6v520.com`, `seedhub.cc`, `btsow.pics`, `btlm.work`, `cilimao.de`, `ciligou.de`, `1000mag.xyz`, `u3c3.org` —— 全部国内可访问 HTTP 200

**13 个真死的源**（域名级失效，全球不可达）：`btdb.to`, `extratorrent.ag`, `limetorrents.cc`, `kickasstorrents.bz`, `legacy-site.pw`, `torrentdownload.info`, `arab-torrents.com`, `btsow.live`, `xunlei8.top`, `link.btapp.me`, `torrentkitty.de`, `btdb.unblockit.li`, `laoniubt.com`

### 真正的根源问题

**health_check 误判机制**——可能是：
- 单次失败即标 unreachable（无重试）
- 超时阈值太短
- User-Agent / TLS 指纹被某些站点临时拒绝（→ CHALLENGE-001 的解决方案 Scrapling Fetcher 顺手能修）
- 检查时点 server 临时抖动

### 下一步

1. ⏭ 立即用 `_bench_gfw_proxy.py` 全量扫所有 73 个 `unreachable` 源（vs 当前抽样 25）
2. ⏭ 把"两边都活"的批量重检 + 提升回 yellow/green
3. ⏭ 把"两边都死"的批次永久打 `expired` 标记（域名级失效）
4. ⏭ health_check 加 **最少 2 次重试 + 8s 超时 + TLS-impersonate UA**（与 v2 Fetcher 一致）

### 更新日志

- 2026-05-21 —— 初建条目（假设 GFW 是主因）
- 2026-05-21 实测后 —— **假设被证伪**：GFW 阻断 0%，误判 48%，真死 52%；严重度从 high→low，重点改为修健康检查

---

## CHALLENGE-004 — LLM 修复 selector 成本 / 延迟

- **严重程度**：medium
- **状态**：open
- **业务影响**：每次 healer 兜底调一次 LLM ~ ¥0.001-0.01 + 5-15s 延迟；若 CHALLENGE-001 解决则触发频率自然下降
- **候选方案**：
  - **Reader-LM 1.5B**（Jina AI）本地部署：HTML 压缩到 markdown，token 数减少 70%+
  - **MarkItDown**（Microsoft）：纯 HTML→md 转换器
  - **Volces/Doubao 缓存**（Volces 平台支持 prompt cache）
- **下一步**：CHALLENGE-001 解决后再评估

---

## CHALLENGE-005 — 域名漂移 / 死链发现滞后

- **严重程度**：medium
- **状态**：open
- **业务影响**：BT 站常换域名（DNS 投毒/版权追查），现有发现漏斗滞后 1-2 周
- **候选方案**：
  - 监听 t.me 频道（中文 BT 圈常发新域名）
  - 关键 brand 关键字 Google Alerts
  - **GitHub trending search**：监听 `magnet bt site list` 等 awesome-list 仓库的 commit
- **下一步**：未排期

---

## 调研流程 SOP

每 2 周（建议每月 1/15 号）做一次：

1. **GitHub Trending**：浏览 [github.com/trending/python](https://github.com/trending/python) 和 `/typescript`，重点看 `web-scraping` / `crawler` / `parsing` topic
2. **GitHub Topics**：扫
   - https://github.com/topics/llm-scraping
   - https://github.com/topics/web-scraping
   - https://github.com/topics/anti-bot
3. **HackerNews 搜索**：`site:news.ycombinator.com scraping`、`site:news.ycombinator.com bypass cloudflare`
4. **arXiv**：每月扫 `cs.IR` 类目下 "wrapper induction" / "web extraction" 关键字
5. **同行项目**：观察 prowlarr / jackett / qbittorrent-search-plugins 的 commit
6. **更新本文**：候选方案塞进对应 CHALLENGE 的 "候选方案" 列表，标注难度评估
7. **DEV-LOG 同步**：本次调研结果写入当天 DEV-LOG 简短摘要

### 评估候选方案的标准

- ✅ 与现有 Python 栈兼容（不引入 Node/Rust 子进程除非必要）
- ✅ 可窄替换（不要求重写 pipeline）
- ✅ License 友好（MIT/Apache）
- ✅ 中国大陆可用（不依赖被墙的服务）
- ⚠ 维护活跃度 > 0（最近 6 个月有 commit）
- ⚠ Issue/PR 关闭率 > 50%
- ❌ Hosted SaaS（除非免费额度足够覆盖我们规模）
