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
| [CH-008](#challenge-008--dytt旧资源域名失效导致100条资源可靠性不足) | DYTT旧资源域名失效导致100条资源可靠性不足 | **high** | open | 2026-07-30 100条在线审计FAIL |
| [CH-009](#challenge-009--影视自动发布二次失败缺少外部主动告警) | 影视自动发布二次失败缺少外部主动告警 | medium | open | 2026-08-05 已有一次自动重试，待接外部通知 |

---

## CHALLENGE-009 — 影视自动发布二次失败缺少外部主动告警

- **严重程度**：medium
- **状态**：open
- **首次记录**：2026-08-05
- **业务影响**：每日正式发布失败后会在30分钟后自动重试一次；如果第二次仍失败，数据门禁会保持旧revision安全可用，但运维人员目前只能通过systemd journal和`latest-publish.json`被动发现，可能延迟数小时或数天才处理停更。
- **当前方案 & 缺陷**：已具备`OnFailure → magnet-media-retry.service`、结构化失败状态、run历史和周审计。自动重试不会循环，也不会误提升current；缺陷是没有企业微信、飞书、邮件或短信等独立于服务器的主动通知通道。
- **已尝试**：2026-08-05现场将重试延迟缩短为1秒，确认存在较新成功状态时自动取消，不会重复发布；连续失败场景的状态与日志契约已有测试覆盖。
- **候选方案**：优先使用无需在App内暴露凭证的服务器端企业微信/飞书机器人；备选为SMTP邮件、阿里云云监控或轻量Webhook中继。通知内容只包含run ID、错误码、失败阶段、当前revision和日志定位，不发送密钥或影视资源内容。
- **下一步**：选择一个外部通知通道，增加失败通知与恢复通知，执行“首次失败→自动重试→二次失败告警→人工恢复→恢复通知”完整演练。
- **更新日志**：2026-08-05 —— 主流水线已通过单源回退、双端无变化验证、评分确定性、主锁/发布锁心跳、容器清理及一次性延迟重试终审；本项成为唯一剩余无人值守运维缺口。

---

## CHALLENGE-008 — DYTT旧资源域名失效导致100条资源可靠性不足

- **严重程度**：high
- **状态**：open
- **首次记录**：2026-07-30
- **业务影响**：DYTT可以稳定抓取100条标题和封面，但大量旧条目依赖`a.gbl.114s.com` FTP资源；国内系统DNS无法解析，阿里公共DNS返回Status=3。该入口不能作为100条可靠电影资源补充源自动晋级。
- **当前方案 & 缺陷**：新页面M3U8和HTTP直链已正确还原并可用；旧FTP地址也能从Jianpian包装中提取，但资源主机不可达。仅修解析器不能修复上游资源失效。
- **已尝试**：完成100条抓取、400封面验证、20条M3U8在线验证、20条FTP桌面探针、K30S国内DNS和阿里DoH复核；另外抽检DYTT其他电影分类，仍以相同FTP为主。
- **候选方案**：将DYTT降级为元数据/HLS观察源；接入另一个经过100条同门槛验证的电影资源补充站；或等待DYTT更换可解析资源域名后重新资格审计。
- **下一步**：禁止DYTT旧FTP计入可靠资源数，不做正式资源源晋级；下一候选站必须执行100条结构、封面、在线资源和零网络重放全门禁。
- **更新日志**：2026-07-30 —— `AUDIT=HOLD_WITH_3_OF_4_ENTRIES_PASS`，详见`RESOURCE-INDEX-NEW-SOURCE-100-RELIABILITY-20260730.md`。

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

### CHALLENGE-006 multi-source 100-record update — 2026-07-30

- **Status**: solved ✅ for the four production media entries.
- SixV movie, Meijumi series and SixV series each passed 100 real records with title/cover/resource omissions zero, 100 unique decoded covers and zero-request deterministic replay.
- DYTT cannot use its latest 100 pages directly because older records are dominated by unreachable FTP or player-only resources. The production strategy now scans 250 candidates and emits the latest 100 records with title, cover and magnet/cloud resources.
- Real DYTT evidence: 249 details succeeded, one stale page returned permanent 404, 115 candidates qualified, and the final 100 records contain 159 unique magnets with no cross-item duplication.
- Explicit 404 maps to terminal `NOT_FOUND`; content-identical Feed replay preserves file bytes and cannot create a false revision through timestamp churn.
- Four-source final aggregation passed with 436 entities and 4,468 globally unique resources; title/cover/empty-resource drops and invalid resources are zero.
- Verification: 2026-07-31 independent replay reached Resource Index 295 passed / 1 skipped; enum 241 rules / ALL VALID.
- The non-magnet online probe now treats a magnet-only qualified Feed as network-not-applicable PASS while an actually empty resource scope remains FAIL, closing a false-negative gate found during independent re-verification.
- Evidence: `RESOURCE-INDEX-NEW-SOURCE-100-RELIABILITY-20260730.md`.

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

## CHALLENGE-008 — 电影多来源低频自动化与站点隔离

- **严重程度**：major
- **状态**：solved in implementation；独立复验待执行
- **首次记录**：2026-07-26
- **业务影响**：继续按站点复制完整 Runner 会造成锁、预算、恢复和 Feed 逻辑漂移；反过来用一个通用 CSS 解析器兼容所有电影站，又会让单站改版拖垮全部来源。
- **架构裁决**：共享 `MovieLatestRunner`、自动化预算和持久化状态；SixV、DYTT8899 分别维护列表/详情适配器和来源边界。
- **安全策略**：单并发；SixV 10 秒、DYTT 15 秒请求间隔；网络检查至少 12 小时；每日预算 80/50；失败退避 24/48/72 小时；403/429/挑战立即暂停；不绕过验证码、WAF、登录或延迟资源释放。
- **边界修复**：电影来源不再注册到旧 `crawl_query/crawl_detail_urls` 协议；共享内核在快照前校验 HTTPS、注册域名、公开路径、连续 rank、唯一 URL 和 source key。
- **DYTT真实证据**：正式快照 25/25 完成；25 部均有标题、封面和简介，保存 48 条公开 `jianpian://` 资源；仅《杀手正在召唤》源站没有可可靠获取的类型，保守留空；完成后重跑 0 请求。
- **自动化证据**：完成快照检查仅 1 个列表请求，预留 12/实际 1/退款 11；立即再次调用因 12 小时门禁零网络跳过。
- **验证**：Resource Index 134 passed；全 magnet 非集成 197 passed / 2 deselected；schema 0006、PowerShell 7/7、ScheduledTasks IgnoreNew/PT6H、Python 3.13最小环境和项目外 doctor/status/safe PASS。
- **证据**：`RESOURCE-INDEX-MOVIE-MULTISOURCE-AUTOMATION-2026-07-26.md`
- **剩余边界**：无法承诺永不触发反爬；SQLite仍为单机单写；站点改版会暂停该来源但不应影响其他来源；App 是否接入 DYTT Feed 属于后续产品批次。

---

## CHALLENGE-009 — 影视品牌镜像识别与跨品牌内容去重

- **严重程度**：major
- **状态**：solved in implementation；独立复验待执行
- **首次记录**：2026-07-26
- **业务影响**：按域名逐站抓取会把同品牌镜像重复计数；只按站名判断品牌又会把DYTT8、电影天堂导航等不同模板误当镜像。不同品牌之间缺少统一身份时，同一电影/剧集会重复展示，资源也无法互补。
- **架构裁决**：建立`movie-source-brands/1`注册表，保存品牌、端点角色、证据、模板、优先级、内容类型和最后验证时间；正式适配器与候选探测分离。
- **同品牌闭环**：SixV三旧版域经发布页和相同内容指纹确认；DY2018通过两次物理请求跳转到DYTT8899且内容指纹一致。Runner按稳定source_item_key切换镜像，不按完整URL重复抓详情。
- **跨品牌闭环**：schema 0007加入movie/series、季集、brand和endpoint字段；media-feed/1按电影标题+年份、剧名+季去重，IMDb只作辅助别名，一边缺季数时仅在唯一兼容候选下合并。
- **正式数据**：SixV电影50、DYTT电影25、美剧迷50、SixV电视剧50，共175条原始记录聚合为158条，识别17组跨品牌重合，合并后保留2345条资源和全部source_variants。
- **剧集证据**：美剧迷50/50、1740资源；SixV电视剧50/50、417资源；《犯罪心理：演变》《谜探休格》《龙之家族》等16组剧集实现双品牌资源合并。
- **验证**：Resource Index 147 passed；全magnet非集成210 passed / 2 deselected；真实镜像切换、零重放、12小时门禁、schema 0007和正式四源聚合PASS。
- **证据**：`RESOURCE-INDEX-BRAND-FAMILY-MEDIA-2026-07-26.md`
- **剩余边界**：候选站只有通过解析器、健康和安全门禁后才能升为正式源；App统一电影/电视剧展示属于后续批次。

---

## CHALLENGE-010 — 分类型最新100、预算误分类与迁移版本碰撞

- **严重程度**：blocker
- **状态**：solved；exact-commit clean-worktree复验PASS
- **首次记录**：2026-07-26
- **业务影响**：全局limit无法保证电影/电视剧各100；本地预算耗尽被当作HTTP限流会产生假退避；并行分支复用迁移版本号会让数据库“显示已升级但缺关键字段”。
- **聚合裁决**：正式抓取池扩大到SixV100+DYTT50、SixV电视剧50+美剧迷100；聚合器使用独立movie/series配额和严格不足门禁，磁力按info_hash去重。
- **身份裁决**：明确季/年份先合并；未知季分量仅在所有标题/IMDb别名都指向唯一明确候选时并入，关闭传递桥接不同季。
- **预算裁决**：新增`LIVE_REQUEST_BUDGET_EXHAUSTED`，与403/429的`LIVE_RATE_LIMITED`分离；默认批次5条预留12次物理请求。
- **迁移裁决**：生产SQL版本必须连续且唯一；历史0007 IMDb变体只有精确checksum和完整结构指纹同时满足时才归档，随后执行正式0007品牌迁移。
- **正式结果**：可用电影147、电视剧131；严格输出100+100，200条共2865资源，22条跨来源；缺标题/封面/简介/资源和重复身份均为0。
- **恢复证据**：旧库直接复用50/25/50条且冻结详情请求0；完成后SixV/DYTT/美剧迷重复运行均0 HTTP；四正式库integrity=ok。
- **验证**：Resource Index 158 passed；全magnet非集成221 passed / 2 deselected；PowerShell 7/7；枚举241/241。
- **证据**：`RESOURCE-INDEX-MEDIA-LATEST100-2026-07-26.md`
- **剩余边界**：App尚未消费100+100目录；SQLite仍是单机单写；当前未发布、未部署。

---

## CHALLENGE-011 — 离线Feed语义污染、封面依赖与一键数据库误选

- **严重程度**：blocker
- **状态**：solved；exact-commit clean-worktree复验PASS
- **首次记录**：2026-07-26
- **业务影响**：脏类型/国家破坏频道筛选；资源标题丢集数；多季页面污染明确季；电视剧依赖远程封面；一键脚本可能因同名partial库抢占完整历史库而重复抓取。
- **数据裁决**：所有来源在聚合前执行纯规则标签和季集归一化；明确季只接受同季资源，未知/跨季资源进入可审计隔离清单；失去可靠资源的候选被淘汰后从更大池补位。
- **封面裁决**：电影和电视剧统一生成内容哈希本地Bundle；全部封面完成并通过哈希/尺寸/解码审计后才替换最终Feed，重复构建0 HTTP。
- **App裁决**：完整Feed保留公开资源证据，App Bundle只接受magnet/cloud并自动补位，客户端协议不因脏源放宽。
- **运行裁决**：`run-media-offline.bat`首次安装环境后完成四源恢复、聚合、隔离、封面和离线审计；运行链无LLM。数据库按完整任务、成功rank、内容数和quick_check选择，活跃锁整体阻断。
- **评分裁决**：schema 0008预留烂番茄/Bangumi可空字段；独立评分工具回写后，爬虫空值更新不得清空。
- **真实结果**：隔离2155资源（1469 mismatch、686 unknown），淘汰21候选；电影146/电视剧109可用，严格输出100+100；200张本地封面PASS。
- **验证**：Resource Index 178；全magnet非集成241/2；App对抗36/36；TypeScript/Expo PASS；PowerShell 8/8；doctor 4/4 schema0008；一键全链0源请求、0封面请求复用PASS。
- **证据**：`RESOURCE-INDEX-OFFLINE-FEED-P0-2026-07-26.md`
- **剩余边界**：P1日剧来源、真实排行榜和评分工具回写仍为独立批次；当前未发布。

---

## CHALLENGE-012 — 本地爬虫无人值守、自动发布与免费容量闭环

- **严重程度**：major（原blocker已关闭）
- **状态**：resolved / production monitoring；阿里云每日自动抓取与双端自动发布已启用
- **首次记录**：2026-07-26
- **业务影响**：核心无人值守阻塞已关闭；影视数据由阿里云每日抓取并在全部质量、签名、回归和双端验证通过后自动成为客户端可见revision。当前剩余风险转为生产监控、源多样性和2C2G容量余量。
- **内核证据**：Resource Index 178 passed；全magnet非集成241 passed / 2 deselected；中断恢复、请求预算、镜像切换、质量和离线Bundle专项56 passed；四正式任务分别100/100、50/50、50/50、100/100，均无pending/running/failed。
- **运行阻塞**：Windows任务`MagnetGoogo Movie Sources Safe Crawl`实查未安装；模板`StartWhenAvailable=true`但`WakeToRun=false`；个人电脑关机、睡眠或断网会推迟更新。
- **发布链进展**：App已支持签名远程revision、内容寻址Catalog/Detail/Resource和长期本地缓存；Revision 8已在R2/阿里云双端上线。专用production-auto Worker和正式签名链已完成无人值守提升current。
- **来源边界**：SixV电影和剧集共享品牌/模板，DYTT备用仍依赖同一主站，美剧迷只有单正式端点；核心来源故障时旧目录不会损坏，但可能无法形成新一轮100+100。
- **服务器实查**：2核CPU负载极低，但约2GB内存仅约514MB可用且已使用约501MB Swap；静态Nginx余量大，不适合继续增加常驻爬虫、数据库或动态搜索服务。
- **证书闭环**：2026-07-31确认HTTP-01被外网上游`Beaver / 403`阻断；已改用Let’s Encrypt TLS-ALPN-01签发，新证书有效至2026-10-29。`acme-cn-magnetgoogo-renew.timer`已enabled/active并实跑SUCCESS，旧`certbot-renew.timer`已停用。
- **免费容量裁决**：资源页与搜索不经过中心服务器；当前Worker/R2事件模型下保守支持3,000—5,000 DAU，正常使用约8,000—10,000 DAU；现有约100 DAU远低于容量。
- **容量放大项**：每次启动配置和源规则各竞速6端点且不取消输家，缓存有效仍后台同步，客户端发送`no-cache`，分析每批写一个永久R2对象；这些行为将免费容量压缩约2—4倍。
- **2026-07-31自动流水线进展**：`media-daily`已接入仅磁力、四评分持久状态、每日40+40限额轮转、完整签名candidate、死PID/跨重启锁恢复、7/30/3/30历史保留、磁盘门禁和7日Soak计数；评分源失败降级且不清空旧值。Revision 7真实回放恢复584/584个有效评分/身份字段。
- **2026-07-31服务器实查**：`ecs.e-c1m1.large`，2核/1.8GiB，约461MiB可用，Swap已用约541MiB，磁盘余约18GiB；静态镜像PASS，正式自动发布HOLD。证书阻塞已通过TLS-ALPN和独立systemd续期Timer关闭。
- **2026-07-31候选部署加固**：容器已限制为768MiB/1 CPU/1280MiB含Swap/256 PID；Nginx切换会逐对象验证revision 7并原子迁移；候选使用非生产私钥、上一Manifest独立使用0.2.3正式公钥；冷启种子417文件/37,583,895字节，四库integrity=ok，二次候选封面请求0。真实候选为214电影、220剧集、3561磁力、0 cloud且无上一版回归。
- **2026-08-01正式自动发布**：候选审计确认217电影、227剧集、3597唯一磁力、0 cloud、0非法/重复hash和0回归；部署`media-auto-publisher.magnetgoogo.com`专用Worker，未授权401、授权200；正式私钥与0.2.3公钥一致。Revision 8已双端发布，pointer SHA=`36cd24b62a2d2041c3a2f045bb4186193886bd0d5e9c1f4da1bdac5edd454ab6`，Manifest SHA=`83b9763f59d8759e9a1a699032b6671cabfce6738e32b694aac6eb1deecaa5c6`，1,302对象独立复验PASS。
- **剩余风险**：尚无外部heartbeat与主动告警；2C2G只批准当前每日一次、40+40评分和现有来源规模；核心来源仍存在品牌/主站相关性。0.2.4还需升级或失效旧Detail缓存schema以立即展示烂番茄/Bangumi。
- **下一步**：观察下一次自然Timer的自动发布/no-change结果；增加失败告警和双端Pointer漂移告警；继续监控耗时、内存、Swap、磁盘和R2调用量。
- **证据**：`RESOURCE-INDEX-STABILITY-CAPACITY-REVIEW-2026-07-26.md`、`MEDIA-ALIYUN-AUTOMATION-CAPACITY-AUDIT-20260731.md`、`ALIYUN-CERTIFICATE-RENEWAL-FIX-20260731.md`、`MEDIA-DAILY-MAGNET-ONLY-FOUR-RATING-20260731.md`、`MEDIA-DAILY-CANDIDATE-SOAK-HARDENING-20260731.md`、`MEDIA-DAILY-AUTO-PUBLISH-REVISION8-20260801.md`

---

## CHALLENGE-013 — 影视运营漏斗缺失与搜索指标口径错误

- **严重程度**：major
- **状态**：open；原始数据可重算，生产Dashboard与App埋点待修复
- **首次记录**：2026-08-02
- **业务影响**：影视资源上线后DAU与新增显著增长，但当前不能直接计算资源Tab曝光、卡片点击、详情转化、单影视消费和revision增量；运营后台又遗漏0.2.x的`search_submitted`，会把新版搜索量低估约10倍，可能导致错误产品决策。
- **数据证据**：阿里云原始缓存36,187批次、419,673事件、1,057设备。上线后平均DAU+28.0%、日均新增+77.6%，但成熟新用户D1由22.5%降至11.9%。0.2.x活跃241台，仅23台产生可推断的影视详情资源动作，设备转化9.5%。
- **口径缺陷**：生产`/opt/admin-server/server.js`仍使用`searches: counts.search || 0`，未合并`search_submitted`；后台按UTC切日，国内运营应另提供UTC+8视图。
- **埋点缺陷**：缺少`resource_tab_view`、`media_card_click`、`media_detail_load_result`、`media_resource_open/copy`、`media_feed_sync_result`；现有动作不带media ID、频道、位置和release ID。
- **安全边界**：仅上传匿名media ID哈希、枚举频道、位置桶、缓存命中、耗时和错误码；禁止上传完整标题、磁力URL或可识别个人信息。
- **下一步**：先修Dashboard口径并从原始批次回填最近30天；在0.2.4补齐影视曝光→详情→资源动作漏斗；上线后按revision、版本、渠道和cohort建立D1/D7看板。
- **证据**：`影视资源上线后运营增长埋点分析-20260802.md`

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
