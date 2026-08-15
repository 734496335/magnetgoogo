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
| [CH-006](#challenge-006--resource-index-live-抓取可复现性与数据不退化) | Resource Index live 抓取可复现性与数据不退化 | **blocker** | solved ✅ | 2026-07-25 R6 complete; independent re-review pending |
| [CH-007](#challenge-007--resource-index-跨电脑长任务编排与恢复) | Resource Index 跨电脑长任务编排与恢复 | **blocker** | solved in implementation | 2026-07-25 portable latest runner complete |
| [CH-008](#challenge-008--搜索资源大小单位与合并权威不一致) | 搜索资源大小单位与合并权威不一致 | high | solved ✅ | 2026-08-01 148源大小/日期/文件数闭环 |
| [CH-009](#challenge-009--四评分跨协议缓存与ui量纲一致性) | 四评分跨协议、缓存与UI量纲一致性 | high | solved ✅ | 2026-08-03 v0.2.5旧缓存迁移真机闭环 |
| [CH-010](#challenge-010--匿名设备标识与r2小对象埋点链路) | 匿名设备标识与R2小对象埋点链路 | high | piloting | 2026-08-15 Gateway/Admin已生产化，等待0.2.6 K30S终验 |

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

## CHALLENGE-006 — Resource Index live 抓取可复现性与数据不退化

- **严重程度**：**blocker**
- **状态**：open
- **首次记录**：2026-07-25
- **业务影响**：JavBus happy path 已能入库真实内容，但 commit `48688bc` 在 clean Windows worktree 中出现 18 个 Fixture hash 失败；部分重解析会清空已有演员/标签；未知异常会留下永久 `running` run。当前无法把内容库作为长期可信数据源，也不应继续扩第二站。
- **当前方案 & 缺陷**：
  - Fixture 和 migration checksum 直接绑定 checkout 原始换行字节，LF/CRLF 不可移植；
  - live policy 在库层自动 enabled/acknowledged，CLI `--yes` 不是能力边界；
  - relation update 使用 delete-and-replace，无法区分“未观察到”和“确认为空”；
  - HTTP 5xx、预算、age-gate 中断和 run terminal state 语义未闭合；
  - registry listing 路径仍硬编码 JavBus 类。
- **已尝试**：
  - 2026-07-25 commit-bound clean worktree 复验：真实详情 1/21/2/9 与关键词 2/44 均成功；正常幂等成立；资源索引测试 28 passed / 18 failed；多项故障注入反例复现。
- **下一步**：
  1. R1：先修 EOL/checksum 可复现性和显式依赖；
  2. R2：修 policy/输入/URL 来源边界；
  3. R3：修终态、HTTP 错误和真实请求预算；
  4. R4：修集合 completeness 和 warning 可观测；
  5. R5：用 fake second source 证明 registry 后再加真实第二站。
- **审查证据**：`RESOURCE-INDEX-JAVBUS-LIVE-REVIEW-2026-07-25.md`
- **更新日志**：2026-07-25 —— 创建；结论为 happy path PASS、稳定性与可复现性 FAIL。

### CHALLENGE-006 closure update — 2026-07-25

- **Status**: solved ✅ for controlled local one-shot live crawl.
- Closed LF/CRLF Fixture and migration checksum portability, true default-off policy, 10s minimum delay, full request budgeting, 5xx retry/non-2xx rejection, age-gate hard-stop, URL/redirect fencing, terminal run states, empty-run failure, relation non-regression, warning observability and generic listing registry.
- Verification: resource_index 66 passed; all magnet non-integration Python tests 127 passed / 2 deselected; real SSIS-960 first crawl 1/21/2/9 and repeat 0 new/21 updated with all observations seen_count=2.
- Evidence: `RESOURCE-INDEX-JAVBUS-LIVE-HARDENING-2026-07-25.md`.
- Unattended scheduler, crash-recovery checkpoints and a second real source remain future scope, not part of this solved defect.

### CHALLENGE-006 second-review update — 2026-07-25

- **Status**: reopened.
- `max_pages` counts logical documents rather than physical retry attempts; transport retries bypass the 10-second interval.
- Automatic redirects are followed before target validation; origin fencing does not restrict effective port.
- `KeyboardInterrupt` leaves a permanent `running` ingest run.
- A second source writing the same content creates a hybrid canonical row with source-A identity and source-B URL/parser/title.
- Happy path and clean-checkout reproducibility remain PASS, but robustness, request-policy enforcement, redirect security and second-source readiness are FAIL.
- Evidence: `RESOURCE-INDEX-JAVBUS-LIVE-REREVIEW-2026-07-25.md`.
- Next: execute R6-T1 through R6-T5 as one complete hardening batch before another independent review.

### CHALLENGE-006 R6 implementation update — 2026-07-25

- **Status**: solved in implementation; independent clean-worktree re-review still required.
- Physical request budget now counts every retry and redirect; `ingest_runs.http_requests` records the exact count.
- Every retry and redirect is spaced by at least 10 seconds; cancellation during the wait does not consume a request.
- Redirects are followed manually with pre-request scheme/host/effective-port and DNS-address validation.
- `KeyboardInterrupt` reaches a durable `cancelled` terminal state; stale `running` runs are recovered on the next live ingest.
- Schema `0002` adds `content_observations`; canonical content fields are selected as one source-coherent record by source priority, metadata completeness and recency.
- Added self-contained `python magnet/validate_enum.py`; root source metadata is synchronized to 241 rules.
- Automated evidence: R6 adversarial 22 passed, resource_index 88 passed, all magnet non-integration 151 passed / 2 deselected.
- Live evidence: budget=2 stopped at exactly 2 requests; SSIS-960 used 3 requests and returned 1/21/2/9; SSIS limit=2 used 6 requests and returned 2/44.
- Evidence: `RESOURCE-INDEX-JAVBUS-LIVE-R6-CLOSEOUT-2026-07-25.md`.

---

## CHALLENGE-007 — Resource Index 跨电脑长任务编排与恢复

- **严重程度**：**blocker**
- **状态**：solved in implementation；独立复验待执行
- **首次记录**：2026-07-25
- **业务影响**：上一次最新 100 条最终数据完整，但 21 个成功 run 共发出 285 次详情 HTTP；按冻结快照只需 218 次，因 502 回传失败和人工重放额外访问 67 次，额外开销约 30.7%。临时 `python -c` 无法作为另一台电脑上的稳定部署方案。
- **根因**：
  - 外部命令通道与实际抓取进程的生命周期耦合；
  - 无 durable snapshot/job/item 状态；
  - 无数据库级单实例锁；
  - 完成判定依赖命令结果，不依赖实际 URL 覆盖；
  - 无正式 setup/doctor/status/resume 入口；
  - 全局依赖、相对路径和覆盖式日志不利于跨电脑复制。
- **已实现**：
  - schema `0003`：`latest_crawl_jobs + latest_crawl_items`；
  - 冻结最新列表快照，重复番号不同 URL 保留；
  - 小批次、每次启动每条最多尝试一次、跨启动最多三次；
  - exact detail URL 覆盖对账，中断后只补缺失记录；
  - 完成后的同快照重复运行零 ingest run、零 HTTP；
  - DB 路径绑定的单实例锁和同机死 PID 恢复；
  - 原子 Feed、追加日志、无网络 status；
  - Windows 最小虚拟环境、冻结直接依赖、doctor 和 bat/PowerShell 入口。
- **验证**：
  - latest runner 对抗测试 16 passed；
  - resource_index 105 passed；全 magnet 非集成 168 passed / 2 deselected；
  - 全新 Python 3.10 与 3.13 虚拟环境冻结依赖安装与 doctor 均 PASS；
  - 真网 count=3：先切片 2/3，再只补 rank 3，完成后重复命令 runs=2、requests=8 保持不变。
- **证据**：`RESOURCE-INDEX-PORTABLE-LATEST-RUNNER-2026-07-25.md`
- **剩余边界**：SQLite 不支持多机共享目录并发 writer；当前不是 Windows Service；最终推广前需独立 clean-worktree 复验。

### CHALLENGE-007 SixV implementation update — 2026-07-25

- **Status**: solved in implementation for a second real latest source; commit-bound clean-worktree verification pending.
- Added `sixv` as the second real live latest adapter and upgraded schema `0003 -> 0004` with isolated `movie_items/movie_resources`; normal movies no longer contaminate adult-only tables.
- Real source structure is frozen as `/dy/` plus `/dy/index_2.html`, exactly 50 records in source order; red title DOM is persisted as `recommended=true` and `highlight_labels=["推荐"]`.
- Closed three real detail-template variants, GB2312/GB18030 decoding, compact multi-field paragraphs, alias labels, malformed `片\">` fragments and controlled listing-genre fallback when the detail omits category.
- Movie upsert preserves prior non-empty arrays when a later parse is incomplete; `--reparse-incomplete` repairs only current SixV records missing genres or synopsis.
- Windows stale PID probing now treats `SystemError` from `os.kill(pid, 0)` as a dead process; Ctrl+C and source hard-stop leave unvisited ranks pending and pause the invocation.
- Real latest-50 result: 50 movies, 9 red recommendations, 134 resources (71 magnets + 63 cloud links), zero missing title/cover/resource/genre/synopsis, zero duplicate URL, zero running or failed item.
- Two DevSpace 502 disconnects were handled by inspecting lock/PID/job state instead of blindly replaying; final normal rerun kept ingest runs and HTTP counts unchanged.
- Verification: SixV 13 passed; resource_index 119 passed; all magnet non-integration 182 passed / 2 deselected; schema 0004 doctor, PowerShell 4/4, fresh Python 3.13 deployment and outside-project doctor/status PASS.
- Evidence: `RESOURCE-INDEX-SIXV-LATEST50-2026-07-25.md`.
- Remaining: cover image bytes are not cached in SQLite; App/API integration, local image storage and an independent final adversarial audit remain future scope.

---

## CHALLENGE-008 — 搜索资源大小单位与合并权威不一致

- **严重程度**：high
- **状态**：solved ✅
- **首次记录**：2026-08-01
- **业务影响**：SSBC平台曾把KiB当bytes，使23.5GB显示为24.7MB；通用详情页又会把Hash、文件名、热度和关联推荐文本粘入大小，产生7B、44.35GB、27801.01GB、10872.03GB等严重错误。日期栏同时存在Unix时间戳、大小、计数和相对时间原样泄漏，文件数量有丢失和误猜。
- **根因**：
  - `fetchSsbc()` 对`size="24672993"`按bytes格式化，实际字段为KiB；
  - `$('body').text()`丢失DOM边界，详情页回退又覆盖了正确的列表绑定大小；
  - 宽泛`dd` selector固定取第一个元素，Hash内部`7B/89B`被正则识别为容量；
  - “同Hash取最大值”能修小值但会放大巨大误解析；
  - 日期无法识别时原样透传，文件数又会从纯数字日期猜测；
  - legacy dedup对同一来源重复结果也会虚增来源数。
- **修复**：
  - `resourceSize.ts`统一单位、边界、标签和来源观测；SSBC保留KiB专用换算；
  - 详情大小优先使用搜索列表绑定值，DOM文本保留节点分隔，Hash/文件名内部伪大小被拒绝；
  - 前台、后台和legacy去重统一采用独立来源聚类共识，不再取首值/末值/最大值；
  - BTSOW、CiliMo、CLKD、Lulutang数值字段统一按各自API语义格式化，并恢复明确的文件数量；
  - 新增`resourceDate.ts`，标准化时间戳、中英文/俄文/相对日期，未知字段不展示；
  - 文件数量只接受明确字段或Files标签，同一来源重复Hash不增加来源票数。
- **验证**：
  - K30S对`流浪地球`、`Ubuntu`、`SSIS-001`、`Inception`执行4轮148源穷尽；后置共2,131条逐源结果；
  - 大小非法值0，4倍以上同Hash冲突0；原3组影视冲突和5组ISO冲突全部关闭；
  - `Inception`非法日期由158降为0，277条有效日期、70条文件数量、异常计数0；
  - App对抗54/54、流畅性17/17、全部资源/媒体/发布门禁、TypeScript、Debug构建与K30S均PASS，Fatal/ANR为0。
- **证据**：`TEST-RESULT-20260801-搜索资源大小跨源充分审计与关联字段修复.md`。
- **边界**：当前正式0.2.3 APK不包含这些客户端解析修复，需随下一App版本发布；线上源包、源健康状态、池策略和影视Feed未改变。
- **更新日志**：2026-08-01 —— 从SSBC单点扩展至148源大小、日期、文件数量与来源共识闭环。

---

## CHALLENGE-009 — 四评分跨协议、缓存与UI量纲一致性

- **严重程度**：medium
- **状态**：solved ✅
- **首次记录**：2026-08-01
- **业务影响**：媒体供给侧已能写回IMDb、豆瓣、烂番茄和Bangumi，但0.2.3客户端只消费前两种；新增评分会在catalog、detail或本地缓存任一层被丢弃，百分制烂番茄还可能被错误套用十分制阈值。
- **根因**：
  - release协议和`MovieFeedItem`没有新增字段；
  - catalog映射、detail水合、离线bundle标准化均只处理IMDb/豆瓣；
  - UI只适配两枚评分胶囊，没有四项布局和空值规则；
  - 排序、推荐和高分强调的评分权威未显式冻结。
- **修复**：
  - 协议、feed模型和缓存对象完整保留四种评分及RT URL、Bangumi subject ID等详情元数据；
  - 抽出无原生依赖的`mediaReleaseMapping.ts`，对catalog→列表、detail→缓存执行测试；
  - 列表和详情固定豆瓣→IMDb→烂番茄→Bangumi，统一使用0.2.3紧凑胶囊并自然换行；空值与越界值不展示；
  - 排序固定release rank，精品推荐固定服务端recommended；高分主评分优先级为豆瓣→IMDb→Bangumi→烂番茄；
  - 十分制阈值6.0/8.0，烂番茄阈值60%/80%。
- **验证**：
  - 冻结签名release有200条唯一媒体卡，IMDb153/豆瓣99/RT82/Bangumi96；5条唯一媒体可同时展示四评分；
  - 线上revision8有444条唯一媒体、RT62、Bangumi0，证明客户端能力已就绪但线上Bangumi供给尚未发布；
  - 协议、缓存、网络、UI、旧revision与空值测试全部PASS；App对抗54/54、流畅性17/17；
  - K30S在线列表/详情与断网冷启动缓存恢复PASS，Fatal/ANR为0。
- **证据**：`TEST-RESULT-20260801-v0.2.4四评分客户端消费与兼容性.md`。
- **边界**：0.2.4尚未发布；公网v0.2.3和线上revision8未修改。Bangumi实际线上展示依赖后续评分写回与新revision发布。
- **更新日志**：
  - 2026-08-01 —— 四评分客户端消费、量纲、UI、缓存和业务口径闭环。
  - 2026-08-03 —— 正式0.2.3保留数据升级复验发现同revision旧Feed缓存不会补齐RT/Bangumi；Feed/Detail消费缓存升级为`/3`，旧`/2`离线保留、在线同revision自动用原始Catalog重映射。K30S不清数据后“超级少女”成功补齐烂番茄52%，断网强杀仍恢复三评分、简介和资源，Fatal/ANR为0。证据：`TEST-RESULT-20260803-v0.2.5正式包K30S充分验收.md`。
  - 2026-08-04 —— 根据K30S视觉反馈移除详情页两列大评分卡，恢复0.2.3同款紧凑胶囊；四评分字段、顺序、量纲、主评分规则和缓存均不变。

---

## CHALLENGE-010 — 匿名设备标识与R2小对象埋点链路

- **严重程度**：high
- **状态**：piloting（Gateway/Admin 已生产化，App 0.2.6 自动化 PASS；K30S Debug 安装仍需 MIUI 端确认）
- **首次记录**：2026-08-05
- **业务影响**：现有 DAU 只能识别 AsyncStorage 安装 ID，卸载重装会重复计数；新用户、搜索次数和留存口径失真。后台每 20 分钟重读两天 R2 小对象，按当前量估算约消耗 361 万次 Class B/月，且高峰日存在静默截断。
- **当前方案 & 缺陷**：
  - 旧客户端：随机 `mg_device_id`、逐事件持久化、完整源明细、无批次幂等；
  - 旧 Worker：R2 每批一对象、忽略 batch_id、无 event.id 去重、读取完整性不显式；
  - 旧后台：UTC 日界线、把首次出现当新增、只统计旧 `search`、Debug 流量混入。
- **已尝试**：
  - 2026-08-05：完成 device/install/legacy 三标识、SHA-256 应用域匿名设备 ID、安装时间派生安装 ID；
  - 2026-08-05：完成 24 KiB 字节切批、队列持久化串行化、搜索摘要与 10% 源样本；
  - 2026-08-05：完成 Worker 事件/批次幂等、旧客户端稳定批次 ID、日+游标分页、Debug 过滤与 Asia/Shanghai 聚合；
  - 2026-08-05：生产 R2 `events/` 已启用 30 天过期规则。
- **候选方案**：
  - 当前规模：继续 R2 原始事件 + 一小时增量回读，成本低且改造最小；
  - 增长到当前约 8 倍：迁移 D1 设备/安装表和每日聚合，R2 仅保留短期原始事件；
  - 更大规模：Queues/Pipelines 汇聚后写 Parquet/R2 Data Catalog，避免小对象逐条回读。
- **下一步**：K30S 确认一次 USB 安装后，验证 Resource focus/foreground/offline recovery、Debug 本地埋点、搜索/复制/打开完整链路及 Fatal/ANR；App 通过后再决定 0.2.6 正式 APK 发布。
- **更新日志**：2026-08-05 —— V2 自动化、Debug APK 和 R2 生命周期完成；K30S 当时不在线。
- **更新日志**：2026-08-15 —— Gateway 已经 canary 后生产化；日游标 page100 + fail-closed R2 object read，Admin 2日 refresh 38页/~132s/complete=true，并加入瞬时 429/5xx 有界重试及 technical-only cohort 排除。K30S 当前在线，但 MIUI 返回 `INSTALL_FAILED_USER_RESTRICTED`，等待设备端一次安装确认。

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
