# Magnet Googo 增长策略总账

## REVIEW-HOME-TRUST-BASELINE-20261003
- 假设：新版首页视觉冻结后，3个完整日足以建立 `EXP-CRO-HOME-TRUST-002` 的生产基线；满足门禁后仅测试 Hero 下方一行 evergreen trust microcopy，不改其它变量。
- 前置核验：2026-10-03 Growth Daily 完成；L3 App=`OK / operational_verified=true`，完整生产日包含 09-30、10-01、10-02，Analytics 无 unresolved shadow failure。GSC OAuth 仍为 `BLOCKED_EXTERNAL_AUTH`，但本裁决依赖一方 D1/R2 web+app 数据，不以 GSC 为前置。
- 3日 source-stratified matched home baseline：Baidu=83 views / 51 clicks / 61.45%；Google=17 / 11 / 64.71%；Direct=65 / 47 / 72.31%。逐日波动较大，且单次 landing 可产生多次 download click，因此这些 CVR 是点击率型 matched contract，不解释为独立用户安装率；后续 treatment 必须用同一口径比较。
- Backup measurement：`backup_github=15`、`backup_lanzou=8` trusted first-party clicks 已被生产 read model 捕获，证明备用出口测量链存在；当前 read model 未提供 placement×day 明细，因此只作为测量健康护栏，不拿它构造3日转化率。
- 裁决：**SCALE_TO_SINGLE_TREATMENT**。3完整日与 required source strata 均可用，启动唯一 treatment=`无需注册 · 无广告 · 官方签名 APK`，只替换中文 Hero trust line；不改视觉层级、title/meta/H1、CTA文案/位置、备用下载位置、NSQ实验。
- 发布：Cloudflare Pages deployment=`https://fff4c7cf.magnetgoogo-site.pages.dev`；主域已回读 treatment；CN 镜像原子更新 index 并 `nginx -t` PASS。
- 归因可信度：HIGH for experiment state / MEDIUM for effect size。基线和 treatment 都使用同一 prospective source×page contract；Google strata 样本仅17 views，且日级点击可超过 landing views，故最终效果必须等7个完整 treatment 日，不提前宣称提升。
- 状态：`EXP-CRO-HOME-TRUST-002=TREATMENT_ACTIVE_2026-10-03`。下一裁决点：2026-10-10（收齐10-03..10-09七个完整 treatment 日后），目标总体 source-stratified matched homepage download CVR 相对提升>=15%，且 Baidu/Google/Direct 不出现 material degradation。

> 最后更新：2026-10-03 09:25（UTC+8）
> 目标：把所有已经尝试、正在尝试、暂停、失败、取消的增长手段和实际效果长期沉淀，后续增长工作先读本文件，再决定下一步，避免重复试错和凭感觉扩张。

## 0. 记录规则

1. 本文件是增长策略/实验的长期总账，**只追加和更新状态，不删除历史失败与无效尝试**。
2. 每个增长动作至少记录：时间、假设、执行动作、基线、结果、归因可信度、结论、状态、下一裁决点。
3. 结论统一使用：`有效` / `方向性有效` / `无明确提升` / `失败或取消` / `观察中` / `仅基础设施`。
4. 没有用户级归因证据时，禁止把“同期上涨”写成“某策略导致上涨”；只能写 aggregate direction / 方向性相关。
5. GSC、Web、App 三层证据必须区分；外部授权失败时，旧快照只能写 `STALE_LAST_GOOD`，不能冒充实时数据。
6. 后续任何 SEO、GEO、内容、外链、社区、下载漏斗、渠道、留存、转化、推荐、品牌曝光、AI 问答植入、增长自动化等动作，完成后都要更新本文件。
7. 如果某策略连续多次无提升，要记录“为什么失败/是否停止/是否换方向”，禁止以后无证据地重复同一做法。

---

## 1. 当前增长基线（截至 2026-09-16）

### App 最新完整日：2026-09-15

- DAU：268
- Search Devices：259
- DSSU：221
- New Device：54
- New DSSU：45
- Search Activation（近期完整窗）：93.4%
- DSSU / DAU：80.7%
- New DSSU / New Device：82.7%
- Zero-result Search：0.4%
- 成熟 New DSSU 1–7 日复用：38.9%

### Web / 渠道

- Qualified landing views 累计：2872
- Download clicks 累计：2252
- Trusted first-party clicks：745
- 2026-09-08～09-15 全覆盖决策窗口：1688 qualified views
- 该窗口主要来源：
  - Direct：416
  - NSQ / naoshiquan：360
  - Referral（尚未细分的历史/通用部分）：316
  - Baidu：282
  - Internal：205
  - Google：68
  - Yandex：20
  - GitHub：12
  - ChatGPT：2
  - 其他很小

### 当前核心判断

- 产品第一次使用的激活与搜索结果质量已经较强，当前主要增长瓶颈不再是“用户会不会搜”，而是：
  1. 外部新增流量不够大；
  2. 第二次回来的理由不够强；
  3. 渠道 → 页面 → 下载转化刚刚开始具备前瞻精确测量能力。
- 当前优先级：**NSQ 放大 > 百度收割 > 第二外部渠道发现 > 留存回访理由 > GEO 持续观察**。
- 当前策略原则：**Evidence → Experiment → Scale / Kill**。

---

## 2. 到目前为止已经尝试的增长策略与效果

| 编号 | 时间 | 策略/手段 | 主要动作 | 已观察效果 | 结论 | 当前状态 |
|---|---|---|---|---|---|---|
| G01 | 2026-07-28 起 | 影视资源入口 / 产品内容增长 | App 新增影视资源入口、详情与资源动作 | 上线前 7 日 DAU 均值 105.7 → 上线后 4 个完整日 135.3（+28.0%）；New Device 25.9→46.0（+77.6%）；Returning 79.8→89.3（+11.9%）；Starts 208→307（+47.6%）；Search/day +21.1% | **方向性有效**，主要拉新明显，但留存没有同步变好 | 保留产品能力 |
| G02 | 2026-07～08 | 搜索供给质量扩容 | 可用绿源从早期约 7 扩到 0.2.7 约 18 个优先可用源；慢源降权 | Search Activation 长期约 91.5%～93% ，DSSU/DAU 约 80%+ | **有效但属于产品质量，不是独立获客渠道** | 持续维护，不作为当前主要增长杠杆 |
| G03 | 2026-05～08 | Technical SEO 基础 | robots、sitemap、canonical、hreflang、结构化数据、Baidu verification、pretty URL、URL 清理 | 最终稳定为 987 HTML / 214 indexable / 773 noindex / 214 unique canonical；技术审计持续 PASS | **有效基础设施**，解决抓取/规范化，不单独宣称带来多少 DAU | 已完成，维护 |
| G04 | 2026-05～08 | Programmatic SEO / 品牌替代词截流 | 约 49 个品牌 × 3 类意图，早期约 147/148 pSEO 页面，后续收敛到最终 214 indexable URL 体系 | GSC 出现“种子搜索 / bt1207 / 磁力妹妹 / u3c3”等第一页附近机会；Web 有持续自然流量 | **方向性有效**，但多动作同时上线，不能单独归因到某批页面 | 停止继续铺量，转为收割赢家 |
| G05 | 2026-08 | 多语言 SEO | 中英及多 locale 页面、hreflang/x-default、多语言工具/指南 | 技术门通过；有 Google/Yandex/国际流量，但截至当前规模远小于百度/NSQ | **有覆盖价值，增长效果暂弱** | 保留，不继续大规模扩 URL |
| G06 | 2026-05～09 | naoshiquan.com 内容/权威漏斗 | 建博客、工具对比、状态/替代类内容，多语言内容，指向 Magnet Googo | 2026-09-12～15 仅已细分 NSQ 就有 342 qualified views，约 85.5/day；是当前最大可控外部渠道；`cili-search-tools-2026` 累计下载点击 86，为最强非首页赢家 | **明确有效** | 当前第一放大渠道 |
| G07 | 2026-08～09 | IndexNow / 百度主动推送 | sitemap canonical 推送、IndexNow、百度普通收录推送 | IndexNow 多轮 200；Magnet 214 canonical、NSQ 175 canonical 均能稳定提交；百度成为主要搜索来源之一 | **基础发现有效；单次推送对排名/DAU的独立增量无法严格归因** | 继续用于刷新，不刷垃圾页 |
| G08 | 2026-07～09 | 下载入口统一 / CTA 漏斗 | 文章 CTA 改为动态 `/go/download`，旧版本下载入口恢复到最新版，避免文章硬编码版本 | 当前累计 download clicks 2252；NSQ 多篇文章有明确下载点击 | **有效基础设施**，减少版本更新导致的漏损 | 已长期化 |
| G09 | 2026-08～09 | Analytics / Measurement Truth | 修 DAU、New Device、DSSU、D1 shadow、历史 backfill、Growth API；把 31 天与 partial day 语义理清 | 现在能稳定区分完整日/部分日、真实 DAU、渠道来源；避免把错误数字当增长 | **仅基础设施，但极关键** | 已成为增长决策前提 |
| G10 | 2026-09-01 起 | “种子搜索”信息增益 SEO 实验 | `/guide/zhongzi-sousuo` 只增加 first-party live reachability evidence block，不改 title/CTA | Baseline：201 impressions / 12 clicks / CTR 5.97% / pos 7.02；最后可用快照：202 / 12 / 5.94% / 7.27 | **暂未观察到提升**；GSC 当前授权失效，无法继续用实时数据裁决 | ACTIVE，等待 GSC 恢复或足够替代证据 |
| G11 | 2026-09-06 起 | “磁力妹妹”标题单变量实验 | 只改 title/OG/Twitter title，不改正文/description/CTA | Baseline：63 / 1 / 1.59% / pos 6.90；最后可用快照：71 / 1 / 1.41% / pos 6.73 | **位置略好、CTR 未改善，样本不足** | ACTIVE，但 GSC 为 STALE_LAST_GOOD |
| G12 | 2026-09 | `bt1207` SERP snippet 实验 | 原计划做 snippet intent alignment | 119 impressions / 0 clicks / pos 8.16，但 canonical reset 尚需稳定 | **尚未正式开始**，避免混淆变量 | PREREQUISITE_CANONICAL_RESET |
| G13 | 2026-09 | 首页 CRO 信任/下载实验 | 计划评估 homepage download trust/provenance | 旧 baseline 曾显示 681 views / 217 clicks / 31.86%，后发现 cross-origin Referer 把非首页点击污染进 numerator | **失败/取消**：基线无效，不能用 | CANCELLED；以后必须 page-key matched |
| G14 | 2026-09-07 起 | 全站 acquisition attribution | 214/214 indexable 页面统一 tracker，按有限 source 分类，增加 source×day | 2026-09-08 起完整覆盖；到 09-15 共 8 个完整日、1688 qualified views，渠道 mix 已可方向性决策 | **明确有效（测量能力）** | 长期运行 |
| G15 | 2026-09-11 起 | GEO / AI 问答品牌可发现性 | 稳定 `#organization/#software`、About/Methodology/Status/Reports、GitHub sameAs；允许 OAI-SearchBot/PerplexityBot；跟踪 ChatGPT/Perplexity/Copilot/Gemini/Claude | 09-12～15 共 819 qualified views，其中 ChatGPT referral=2；其余 AI 来源=0 | **观察中，样本过低，不能宣称 GEO 成功** | Gate：≥7 完整日 + ≥10 AI referrals |
| G16 | 2026-09-11 起 | Referral 细分 | generic referral 前瞻拆分为 NSQ/GitHub/Reddit/知乎/V2EX/酷安/52破解/B站/Telegram/ProductHunt/X/YouTube 等有限类别 | 09-12～15：NSQ=342、GitHub=12，其余已自动识别社区=0 | **非常有价值：确认 NSQ 是真赢家，其他社区尚未证明** | DIRECTIONAL_SIGNAL_READY |
| G17 | 2026-09-11～16 | Broadcast / 社区需求截流 | 从旧的较激进自动发现，改为“明确用户需求 + 资源实体 + 14天内 + approval-only”；修复 X 假阳性 job #395 | 错误候选 #395 从未发布；最新真实 discovery 扫 81 条，0 new / 0 enqueued / 0 auto-post | **获客效果尚未证明；安全性显著提升** | 继续低频 discovery，不为凑量降门槛 |
| G18 | 2026-09-16 | NSQ 赢家页放大 | 不新增 URL；NSQ blog 首页新增 5 个已证明赢家的“近期高关注指南”内部入口，IndexNow 刷新 core10 | 放大前 baseline：342/4天 = 85.5 qualified views/day；09-17～22 实际 70.2/day，未到 110/day | **无明确提升**，保留 NSQ 渠道但停止继续加码同一内链策略 | `EXP-CHANNEL-NSQ-SCALE-001` HOLD_NO_LIFT |
| G19 | 2026-09-16 | 百度赢家收割 | 不立即改页面，先把百度作为独立渠道注册并等待 source×page conversion | 09-12～15 Baidu=125，31.25 qualified views/day；目标先到 40/day | **方向性有效的现有渠道，新的放大动作尚未裁决** | `EXP-CHANNEL-BAIDU-HARVEST-001` ACTIVE_MEASUREMENT |
| G20 | 2026-09-16 | 第二外部增长引擎 | 知乎 + Reddit 自动发现但人工审批；V2EX/酷安/52破解在没有安全 adapter 时保持 manual | 多轮扫描仍 0 合格候选 / 0 已分类社区 referral | **尚无增长效果**；2026-09-23 从 4 次/日降为 1 次/日，只保留低成本机会扫描 | `EXP-CHANNEL-SECOND-ENGINE-001` LOW_PRIORITY_DISCOVERY_DAILY |
| G21 | 2026-09-16 | source×page×download 转化归因 | 新增 D1 `growth_attribution_daily_dims`；Magnet session 仅保存有限 source；NSQ 直达 CTA 明确标为 naoshiquan | 已生产上线；第一完整干净日为 2026-09-17 | **仅基础设施，效果待数据成熟** | Gate：≥3完整日 + ≥20 source-attributed clicks |
| G22 | 2026-09-16 | 留存/复用增长诊断 | 用完整日自动判断 Activation、DSSU、New DSSU、zero-result 与 1–7d reuse | Activation 93.4%、DSSU/DAU 80.7%、NewDSSU/NewDevice 82.7%、zero-result 0.4%，但 mature reuse 38.9% | **发现主要问题在“回来理由”而不是第一次搜索成功率** | `RETURN_USE_CASE_GAP_HYPOTHESIS`；目标 45%+；暂不改 App |
| G23 | 2026-09 | GitHub 作为实体/发布证据与 referral | 官网 JSON-LD sameAs GitHub，内容中用 GitHub 作可核验项目/Release 证据 | 09-12～15 GitHub referral=12 | **有小量真实流量，规模暂小** | 保留，不单独大投入 |
| G24 | 2026-09-12 | GEO/SEO 内容事实治理 | 清理 NSQ 伪“实测”、固定源数量、错误开源描述、未来测试日期；全 sitemap fact audit | 175/175 事实审计 PASS；不是直接流量增长，但降低 AI/搜索引用错误与品牌信任风险 | **质量/可信度基础设施** | 永久门禁 BL-057 |

---

## 3. 重要阶段性效果

### 3.1 影视资源入口：拉新很强，但暴露留存问题

上线前后最明显的一次产品增长变化：

- DAU：105.7 → 135.3，约 +28.0%
- New Device/day：25.9 → 46.0，约 +77.6%
- Returning/day：79.8 → 89.3，约 +11.9%
- App starts/day：208 → 307，约 +47.6%
- Searches/day：约 +21.1%
- 但成熟新用户 D1：22.5% → 11.9%
- “做过资源动作”的新用户 D1 曾出现 20% vs 12.6% 的方向性差异，但样本小，只能作为假设。

**结论：**内容入口能够明显带来新用户/更多启动，但“拉进来”不等于“留下来”。之后增长策略必须把 Acquisition 和 Retention 分开看。

### 3.2 SEO：从“铺页面”转为“收割已有赢家”

已完成的 SEO 基础非常多：

- Technical SEO / canonical / sitemap / hreflang / robots / JSON-LD
- pSEO 品牌替代意图页
- 中文 + 多语言页面
- 百度主动推送
- IndexNow
- NSQ 内容漏斗
- GitHub / About / Status / Methodology / Reports 交叉证据

到当前已经形成：

- 987 HTML
- 214 indexable
- 773 noindex
- 214 unique canonical
- 214/214 acquisition tracked
- NSQ sitemap 175

最后可用 GSC 快照中的主要机会：

- `种子搜索`：202 impressions / 12 clicks / CTR 5.94% / pos 7.27
- `bt1207`：119 / 0 / 0% / pos 8.16
- `磁力妹妹`：71 / 1 / 1.41% / pos 6.73
- `u3c3`：81 / 8 / 9.88% / pos 9.10

**结论：**SEO 已经证明能产生真实搜索曝光和访问，但过去同时上线过太多变量，无法把 DAU 增量精确归因给某一种 SEO 手段。当前不再继续批量扩 indexable URL，而是只对现有赢家做单变量实验。

### 3.3 NSQ：目前最明确、最可控的外部增长渠道

2026-09-12～15 前瞻细分窗口：

- NSQ：342 qualified views
- 4 天均值：85.5/day
- GitHub：12
- 其他已细分社区：0

NSQ 页面中：

- `nsq:cili-search-tools-2026` 累计下载点击：86
- `nsq:bt-search-engine-status-2026`：29
- `nsq:android-magnet-app-review`：20
- `nsq:magnet-search-backup-10`：18
- `nsq:best-magnet-apps-android-2026`：13

2026-09-16 已开始第一轮 scale：只增加 NSQ blog 首页到这些赢家的内部发现，不改赢家文章标题/意图、不新增 URL。

**结论：明确有效，当前优先放大。**

### 3.4 百度：当前第二个明确的大外部渠道

完整细分窗口 2026-09-12～15：

- Baidu qualified views：125
- 31.25/day
- 当前第一目标：40/day

目前没有直接改页面，因为 source×page×download 归因 9/17 才进入完整日。先等证据判断“百度来的用户在哪个页面最容易点下载”，再只改赢家。

**结论：方向性有效，进入收割实验。**

### 3.5 Google：目前不是最优先增长渠道

2026-09-08～15 完整覆盖窗口：

- Google：68 qualified views
- Baidu：282
- NSQ：360
- generic referral：316

而且 GSC OAuth 当前为：

- 当前 ingest：`BLOCKED_EXTERNAL_AUTH`
- 最后一份授权成功 final snapshot：through 2026-09-06
- 证据状态：`STALE_LAST_GOOD`

**结论：**Google SEO 保持现有实验和技术健康，但在授权恢复前，不继续依据旧排名数据大规模改页面。

### 3.6 GEO：已经产生真实 ChatGPT referral，但还远未证明成功

已经做：

- 稳定 Organization / SoftwareApplication 实体 ID
- Magnet Googo / 磁力古哥统一实体名
- GitHub sameAs
- About / Methodology / Status / Reports 作为可核验引用源
- OAI-SearchBot / PerplexityBot 显式允许且生产 HTTP 200
- ChatGPT / Perplexity / Copilot / Gemini / Claude 前瞻 referral 分类
- ChatGPT `utm_source=chatgpt.com` 映射
- 不做伪评论、不做 AI doorway、不做 `llms.txt` 迷信优化

当前 2026-09-12～15：

- qualified views：819
- ChatGPT referrals：2
- Perplexity/Copilot/Gemini/Claude：0

Gate：

- ≥7 个完整日
- ≥10 AI-referred qualified views

**结论：有真实早期信号，但样本远不足，继续观察，不宣称“已经植入大模型”。**

### 3.7 社区/Broadcast：旧做法风险高，新做法尚未产生获客

旧 discovery 曾较激进：

- 宽泛关键词
- approval_required 曾关闭
- daily cap 较高
- 容易把竞品自荐/无关“打不开”内容当潜在用户

真实出现过错误候选：

- Job #395
- 内容其实是“推特图片/相机打不开”
- 因 query 是“磁力猫 打不开”而误命中
- 最终未发布，并正式 rejected

之后永久收紧：

- 帖子本身必须有磁力/BT/torrent/明确品牌实体
- 必须有明确求推荐/替代/不可用需求
- 自荐/产品发布帖排除
- ≤14 天
- 必须有时间证据
- relevance ≥0.65
- 每轮最多 1 候选
- Reddit Tier1 自动候选=0
- approval_required=true
- 永不自动发帖

2026-09-16 最新真实扫描：

- searched=81
- new=0
- enqueued=0
- auto_post=false
- status=OK

**结论：安全性已建立，但当前没有获客效果。继续低成本发现，不允许为了数据好看而降低门槛。**

### 3.8 留存：当前最值得解决的是“为什么第二次回来”

近期完整窗：

- Search Activation：93.4%
- DSSU/DAU：80.7%
- NewDSSU/NewDevice：82.7%
- Zero-result：0.4%
- Mature 1–7d reuse：38.9%

这说明：

- 用户第一次打开后，大多数会搜；
- 搜索成功率并不差；
- 很多新用户第一天能完成满足动作；
- 但一周内回来复用不足。

因此系统结论固定为：

`RETURN_USE_CASE_GAP_HYPOTHESIS`

当前禁止：

- 为了留存直接加骚扰推送；
- 没证据就重做首页；
- 没证据就加签到/任务体系；
- 把 38.9% 复用问题误判成“搜索不好用”。

目标先做到：**45%+ mature reuse**。

---

## 4. 已经证明“不应该重复”的做法

### 4.1 继续无脑铺 SEO 页面

当前 URL 库已经足够大，且已有第一页附近机会。继续铺量会：

- 分散抓取和权重；
- 加重事实漂移；
- 让实验变量失控；
- 无法判断到底哪个动作有效。

**当前规则：不新增 indexable URL，除非已有证据证明某个新意图值得单独承接。**

### 4.2 用污染 numerator 做 CRO

首页 CRO baseline 曾因为跨域 Referer/page-key 错配，把非首页点击算到 homepage。

**结论：该实验取消，历史 31.86% CTR 不得用于任何决策。**

### 4.3 把旧 GSC 快照当实时排名

OAuth 已过期/撤销。

**结论：只能保留历史实验参考，不可用旧快照指导持续大改。**

### 4.4 社区自动发帖 / 宽松关键词抓机会

已出现 job #395 假阳性。

**结论：只能 approval-only；0 候选也算正常结果，不能为了增长而制造垃圾曝光。**

### 4.5 用伪“实测”增强 GEO/SEO 可信度

历史 NSQ 内容曾出现固定 `80+/100+` 来源数、伪测试、错误开源描述、未来日期测试等。

**结论：已全部转为 evidence-first；真实性不能靠编故事。**

### 4.6 把同期 DAU 上涨直接归因给 SEO/GEO

例如 2026-09-08～10 DAU 均值约 248.7，相比 09-04～07 约 227.5（约 +9.3%），New Device 48.0 vs 41.0（约 +17.1%）。

这些只能写“同期方向性上涨”，因为没有 user-level Web→install join。

**结论：以后必须等 source×page×download，再结合 App aggregate direction，不能伪造用户级因果。**

---

## 5. 当前正在运行的增长实验

### EXP-CHANNEL-NSQ-SCALE-001

- 状态：`ACTIVE_SCALE`
- Baseline：342 / 4 完整日 = 85.5 qualified views/day
- 第一目标：110/day
- 动作：只提高 5 个现有赢家的站内发现性
- Kill/Scale：等新 conversion attribution 成熟后，以 NSQ source-attributed clicks + App aggregate quality 一起裁决

### EXP-CHANNEL-BAIDU-HARVEST-001

- 状态：`ACTIVE_MEASUREMENT`
- Baseline：125 / 4 完整日 = 31.25/day
- 第一目标：40/day
- 动作：暂不乱改页面；等 source×page conversion 找赢家

### EXP-CHANNEL-SECOND-ENGINE-001

- 状态：`ACTIVE_DISCOVERY`
- 自动：知乎、Reddit，approval-only
- 手工：V2EX、酷安、52破解（直到有安全 adapter）
- 当前效果：81 searched / 0 qualified candidate / 0 post

### EXP-RETENTION-NEW-DSSU-REUSE-001

- 状态：`BASELINE_DIAGNOSIS`
- Baseline：38.9% mature 1–7d reuse
- 第一目标：45%+
- 当前判断：回访场景缺口假设
- `app_retention_change_allowed=false`

### GEO attribution gate

- 状态：`BASELINE_COLLECTION`
- 当前：4 完整日 / ChatGPT=2
- Gate：≥7 完整日 + ≥10 AI referrals

### Conversion attribution gate

- 首个完整日：2026-09-17
- Gate：≥3 完整日 + ≥20 source-attributed download clicks
- 禁止历史回填 source

---

## 6. 当前增长优先级

1. **NSQ：继续放大已经证明的赢家，而不是再造内容数量。**
2. **百度：找到真正能带下载点击的现有 landing page，再做单变量收割。**
3. **第二渠道：保持低风险 discovery，寻找第一个真正可重复的社区获客入口。**
4. **留存：找到自然的第二次回来理由，把 mature reuse 从 38.9% 推到 45%+。**
5. **GEO：继续做实体事实、第三方真实提及、可引用证据，等真实 AI referral 过门槛再扩。**
6. **Google：GSC OAuth 已于 2026-09-23 恢复；以后只依据 fresh final GSC + 实际 referral/downstream conversion 做 SEO 裁决，不再使用 stale snapshot。**

---

## 7. 后续新增记录模板

每次新增增长动作，在本文件追加：

```markdown
## YYYY-MM-DD — <策略/实验名称>

- ID：<EXP-... / 无>
- 状态：观察中 / 有效 / 方向性有效 / 无明确提升 / 失败或取消 / 停止
- 假设：
- 执行动作：
- 变更范围：
- Baseline：
- 观察窗口：
- 实际结果：
- App 质量护栏：
- 归因可信度：严格 / 方向性 / 无法归因
- 结论：
- Scale / Hold / Kill：
- 下一裁决点：
- 相关文件/部署/报告：
```

---

## 2026-09-18 — Windows 增长自动任务去重

- ID：OPS-GROWTH-SCHEDULER-DEDUP-20260918
- 状态：有效
- 假设：多轮开发遗留了同功能的重复 Windows 计划任务，造成命令行频繁弹出、同一 Public Status 流程重复部署/探测，甚至可能并发竞争。
- 执行动作：以 `scripts/register-growth-tasks.ps1` 为权威，保留 `MagnetGoogo-PublicStatus-4h`、`MagnetGoogo-AnalyticsShadowRecovery`、`MagnetGoogo-GrowthDaily`、`MagnetGoogo-GrowthDiscovery`；删除旧 `MagnetGoogo-Growth-Daily`、`MagnetGoogo-Public-Status-4H`、`MagnetGoogo-PublicStatusRefresh`。
- Baseline：去重前共 7 个 `MagnetGoogo-*` 计划任务，其中 Public Status 有 3 套、Growth Daily 有 2 套。
- 实际结果：去重后只剩 4 个权威任务；GrowthDiscovery 仍为 approval-only，不自动发帖；普通 Analytics/Growth/PublicStatus 任务不需要浏览器交互。
- 归因可信度：严格（直接读取 Task Scheduler + 权威注册脚本）。
- 结论：重复任务应删除；以后只通过 `scripts/register-growth-tasks.ps1` 注册/恢复，不再混用历史注册脚本。
- Scale / Hold / Kill：KEEP 4 canonical / KILL 3 duplicate tasks。
- 下一裁决点：观察 24h 内命令行弹窗次数与 PublicStatus 运行稳定性；`GrowthDiscovery` 仍会在 09:30/13:30/17:30/21:30 驱动 OpenCLI 浏览器搜索。

---

## 2026-09-23 — 最近 SEO / 渠道 / GEO 增长效果复盘

- ID：REVIEW-GROWTH-SEO-20260923
- 状态：已裁决
- 数据刷新时间：2026-09-23 19:02（UTC+8）；只用到 2026-09-22 完整日，2026-09-23 视为 partial，不进入前后比较。
- 归因边界：Web→APK sideload→App 没有 user-level join，因此 SEO/渠道到 App 新增只能做 aggregate direction；source×page×download 已满足 6 个完整日 + 259 个已归因下载点击，可用于渠道质量方向性裁决。

### 总体结果

- 2026-09-12～15（放大前）Web qualified views=819，204.8/day；2026-09-17～22=979，163.2/day，约 **-20.3%**。
- 同期 App：09-12～15 DAU=273.8/day、New Device=47.5/day、New DSSU=39.3/day；09-17～22 DAU=256.0/day、New Device=30.7/day、New DSSU=25.8/day，分别约 **-6.5% / -35.4% / -34.2%**。
- 产品质量没有恶化：最近 Search Activation=94.5%、DSSU/DAU=81.6%、NewDSSU/NewDevice=83.6%、zero-result=0.5%。所以近期新增下滑更像 acquisition volume 下滑，而不是搜索体验把用户赶走。
- mature New DSSU 1–7d reuse 从此前 38.9% 升到 **42.2%**，方向改善但仍未达到 45% 目标，不能宣布留存问题已解决。

### 渠道裁决

- **NSQ：渠道本身继续有效，但 09-16 的“首页增加赢家入口”放大动作未达到效果。** Baseline 09-12～15=342 / 85.5/day；干净 post window 09-17～22=421 / 70.2/day，约 -17.9%，未达到110/day目标。同期 source-level download conversion=110/421=26.13%。结论：KEEP NSQ，HOLD/KILL 当前内部入口放大假设，不新增 URL，下一轮必须找真正影响外部流量或 CTA 的变量。
- **百度：高质量、低量，当前“40/day”目标未达到。** Baseline=31.25/day；09-17～22=116 / 19.3/day，约 -38.1%；但 download conversion=47/116=40.52%，且115/116落地在首页、首页CVR=40.87%。结论：不是 CRO 问题，主要是搜索流量规模问题；GSC/百度查询证据不足前不乱改首页。
- **Google：实际 referral 小幅增长且质量高，但不能归因到近期 SEO 实验。** 09-12～15=40 / 10.0/day；09-17～22=71 / 11.8/day，约 +18.3%；download conversion=39.44%。GSC 仍 `BLOCKED_EXTERNAL_AUTH / STALE_LAST_GOOD`，所以不能说“种子搜索/磁力妹妹实验提升了排名”。
- **GEO / ChatGPT：从低样本升级为方向性有效，但绝对规模仍小。** 09-12～22 共13 ChatGPT qualified views，正式超过 ≥7日+≥10 referral 门；09-17～22=11 views / 5 download clicks，CVR=45.45%。但仅占该窗口 qualified views 约1.1%、已归因下载约1.9%，所以是高意图长尾，不是当前增长引擎。
- **GitHub：质量高、规模小。** 09-17～22=21 views / 11 downloads，CVR=52.38%；适合作为实体/信任/Release证据，不值得当主要流量引擎。
- **第二社区渠道：当前没有效果。** 2026-09-23 最新 approval-only discovery 搜71条、0候选、0入队、0发布；截至09-22 Reddit/知乎/V2EX/酷安/52破解/B站/X等已分类 referral 仍全为0。继续4次/日自动搜索的增长收益尚未证明。

### 数据质量注意

- `unknown` source 的历史/不完整 source click 不纳入 clean attributed-download 门，因此不会拿 175 个 unknown clicks 算渠道转化。
- NSQ 的 source-level conversion 可用；但 by_source_page 仍把 Magnet landing page=`home` 与 NSQ origin article click key 分开，暂不能用当前结构计算“某篇 NSQ 文章的严格 landing→click CVR”。
- 发现少量带 SQL 注入探测字符串的 NSQ page-key click，说明点击入口仍有 bot/probe 噪声；不影响 NSQ 作为大渠道的结论，但精细文章级裁决前应进一步收紧 page-key allowlist/清洗。

### Scale / Hold / Kill

- NSQ：**KEEP CHANNEL / HOLD CURRENT SCALE TACTIC**。
- Baidu：**KEEP HIGH-INTENT CHANNEL / HOLD PAGE CHANGES UNTIL QUERY EVIDENCE**。
- Google SEO：**KEEP / NO NEW MASS SEO / restore GSC first**。
- GEO ChatGPT：**SCALE CAREFULLY AS AUTHORITY/DISCOVERY, NOT MASS CONTENT**。
- Community Discovery：**HOLD; no proof of acquisition yet**。
- App retention：**HOLD product changes; reuse 42.2% still below45%**。

---

## 2026-09-23 — GSC OAuth 恢复后的 SEO 二次裁决

- ID：REVIEW-GSC-RECOVERY-20260923
- 状态：已裁决
- 授权：2026-09-23 21:56（UTC+8）重新授权成功；`magnetgoogo.com` 与 `naoshiquan.com` 均为 `siteOwner`。
- 最新 GSC final snapshot：2026-08-25～2026-09-21，1269 rows，当前 ingest=`OK`，不再存在 `STALE_LAST_GOOD` warning。
- Google 全体 Search Analytics：08-25～09-06 为 1324 impressions / 93 clicks / CTR 7.02% / position 11.22；09-07～09-21 为 647 / 116 / CTR 17.93% / position 9.60。两个窗口长度不同，因此只做方向判断；按日点击约 7.15→7.73（约+8%），展示/日明显下降但 CTR 与平均位置改善，说明 Google 流量更集中于高意图结果，并非“整体 SEO 流量爆发”。
- `EXP-SEO-ZHONGZI-EVIDENCE-001`：14日阶段**无提升**。精确 query `种子搜索` 08-25～08-31=170 impressions /11 clicks /6.47% /pos6.82；09-01～09-21=7 /1 /14.29% /pos39.71。目标页全部 query 同期 186 /11 /5.91% /pos7.03 → 30 /3 /10% /pos20.30。结论=`HOLD_NO_LIFT_14D`；不把下降强行归因到 evidence block，但明确不能继续放大该做法。
- `EXP-SEO-CILIMEI-TITLE-001`：14日阶段**无 CTR 提升**。精确 query/page 08-25～09-05=41 impressions /0 click /0% /pos6.34；09-06～09-21=20 /0 /0% /pos8.30。结论=`HOLD_NO_LIFT_14D`，当前标题不能称为成功。
- 当前更有价值的 fresh query：`u3c3`=164 impressions /11 clicks /CTR6.71% /pos9.01；`cilisousou`=82 /0 /0% /pos6.26；`bt1207`=94 /0 /0% /pos8.30。下一轮 SEO 更应该围绕“已有第一页曝光但低 CTR”的 query 做单变量实验，而不是继续扩 URL。
- Scale / Hold / Kill：Google 技术 SEO=`KEEP`；批量 SEO=`HOLD`；种子搜索 evidence tactic=`HOLD`；磁力妹妹 title tactic=`HOLD`；下一候选优先考虑 `cilisousou` / `bt1207` 这类 fresh low-CTR opportunity，仍坚持单变量和 ≤3 并发实验。

---

## 2026-09-23 — 第二轮增长执行：NSQ 转化优先 + 新分发渠道准备

- ID：`EXEC-GROWTH-ROUND2-20260923`
- 状态：已上线 / 外部分发待人工平台提交
- 假设：Magnet 官网小词 SEO 的可兑现增量过小；当前最大可控池是 NSQ（约 70 qualified visits/day，clean channel CVR 26.13%），而新第三方 App 分发面可能提供比继续优化几十次曝光关键词更大的新增空间。
- 执行动作：
  1. `EXP-CHANNEL-NSQ-SCALE-001` 改为 `HOLD_NO_LIFT`，停止继续加码旧的 NSQ 首页内链放大法。
  2. `cili-search-tools-2026` 首屏新增唯一 `hero_download` APK CTA，注册 `EXP-NSQ-WINNER-HERO-CTA-001`，不改 title/description/canonical/正文排名变量。
  3. GSC ingest 参数化并正式接入 `sc-domain:naoshiquan.com`；GrowthDaily 现在同时采 Magnet + NSQ，另生成 `nsq-opportunities.json`。首个 28 天 NSQ GSC 快照只有 10 rows / 0 个满足 50 impressions + position 3~15 的机会，因此 Google→NSQ 暂不作为主增长杠杆。
  4. GrowthDiscovery 从每天 09:30/13:30/17:30/21:30 四次降为每天 13:30 一次；approval-only / auto_post=false 不变。
  5. 新增 `uptodown`、`alternativeto` 到官网 tracker、Gateway finite source allowlist、GEO/referral audits 和实验 referral gate，为第三方分发做可测量归因；Product Hunt 原分类继续保留。
  6. 建立 `GROWTH-DISTRIBUTION-SUBMISSION-PACK-20260923.md`，准备 Uptodown / AlternativeTo / Product Hunt 的统一事实文案、归因入口和 Scale/Kill 门槛；明确未实际通过平台审核前不得记为上线。
- Baseline：NSQ 09-17～22 = 421 qualified views / 110 attributed downloads / CVR 26.13%；Magnet Google≈39.44%、Baidu≈40.52%，说明 NSQ 还有站后转化提升空间。
- App 质量护栏：最近 Search Activation 94.5%、DSSU/DAU 81.6%、zero-result 0.5%，本轮不改 App 搜索核心。
- 外部分发准备：当前正式本地 APK=`magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk`，release contract PASS：0.2.8 / versionCode12 / `com.magnetgoogo.app`；SHA-256=`2fc09f84e3fc0916cb3ffd82d8a467b1537030d31fe271e7906eb97fa230c27d`；大小 33,637,658 bytes。
- 生产部署：Gateway Worker version=`b49f553e-862b-416e-9d73-769ed20f0d5f`；Magnet Pages=`a632b855-1d42-4b33-af4a-288fc9ff95c3`；NSQ Pages=`12a564c0-7912-4475-bcfe-3cc640dd84ea`；NSQ winner 单 URL IndexNow HTTP200。
- 自动化：Windows `MagnetGoogo-GrowthDiscovery` 下次运行已变为 13:30，每日一次。GrowthDaily 本轮手工实跑在 Analytics shadow preflight 被 Cloudflare `d1_daily_read_quota_exhausted` 阻断；没有绕过门禁，GSC 双站采集已单独实跑 PASS。
- 验证：Magnet GEO audit PASS；SEO Growth 214/214 attribution PASS；NSQ growth SEO audit 175/175 PASS；Gateway `npm test` PASS；release-build contract PASS；Wrangler 4.137.0 dry-run/deploy PASS。
- 归因可信度：部署/任务/测试为严格；未来第三方渠道效果必须等真实 referral/platform download 数据，不提前宣称增长。
- Scale / Hold / Kill：
  - `EXP-NSQ-WINNER-HERO-CTA-001`：7/14 日窗口，目标相对前一可比窗口总页面下载点击 +30%；未提升则撤回/停止。
  - `EXP-NSQ-GSC-HARVEST-001`：`MEASUREMENT_LOW_SAMPLE`，无真实机会前不制造 SEO 工作。
  - `EXP-DISTRIBUTION-UPTODOWN-001`：`PREPARED_PENDING_EXTERNAL_SUBMISSION`；14日>=100 downloads 才 SCALE，<20 则降为被动入口。
  - Community Discovery：低优先级每日一次。
- 下一裁决点：先观察 `hero_download` placement 的真实点击和 NSQ 总下载；站外平台一旦人工提交并通过审核，开始按 `uptodown/alternativeto/producthunt` 独立来源裁决。

---

## 2026-09-29 — 最近埋点 / DAU 核验故障与运营复盘

- ID：`REVIEW-OPS-ANALYTICS-20260929`
- 状态：`ANALYSIS_COMPLETE / DATA_REPAIR_REQUIRED`
- 数据时间：2026-09-29 16:52（UTC+8）；2026-09-29 为 partial，只作为 lower-bound，不参与完整日趋势。
- 权威边界：当前 D1 `exact_state_authority=true`，但 `operational_verified=false`；最近唯一 unresolved failure marker=`2026-09-23T23:56:57.731Z`，failure class=`d1_daily_row_read_quota`。R2 durable raw 仍是审计/修复 authority。

### 为什么后台会出现“好多日活核验失败”

- 这不是每天各自发生一次 DAU 采集失败。当前只有一个未闭合的 shadow failure marker，但 Admin 的 fail-closed 逻辑在 `shadowHealthy=false` 时会把所有日级 rows 统一标为 `partial`，因此此前已经可信的历史日也会在当前界面看起来“核验失败”。
- 2026-09-29 的自动恢复状态=`ERROR: recovery window exceeds 3 receive days; require explicit deep repair`；Windows `MagnetGoogo-AnalyticsShadowRecovery` 与 `MagnetGoogo-GrowthDaily` 最近结果均为1。原自动恢复只允许最多3个 receive-day，首次恢复没有闭合后，从第4天开始会永久停在安全边界，必须人工深度修复，不能继续靠每日任务自愈。
- 既有 LKG（2026-09-23 生成）已严格验证到 2026-09-22：09-17～22 DAU=`236/266/262/257/250/265`，6日均值256.0；这些日不应因为后续 09-23 UTC 的新 marker 被运营解释为“历史数据失效”。
- 当前 D1 observational 09-23～28 DAU=`258/258/261/289/306/308`；09-29 当前 lower-bound=179。09-26～28 同期 Search Devices=`277/292/295`、DSSU=`237/246/253`、New Device=`49/46/50`，多指标同步上升；legacy diagnostic 对 exact identity 的最大 DAU drift 仅5，因此 300+ 更像真实业务增长而不是单一 DAU 重复放大，但在 deep repair 完成前仍不升级为正式 verified。

### 运营结果（09-17～22 verified LKG vs 09-23～28 observational）

- DAU：256.0/day → 280.0/day，约 **+9.4%**；其中 09-26～28 已到 301/day。
- New Device：30.7/day → 44.3/day，约 **+44.6%**；New DSSU：25.8/day → 36.8/day，约 **+42.6%**。增长首先发生在拉新，不是旧用户突然增加造成的假繁荣。
- 新用户首日满足率 NewDSSU/NewDevice：84.2% → 83.1%，基本稳定；09-26～28 为85.5%。说明新增量上升时首次价值没有明显恶化。
- Search Activation：前窗94.9%；后窗受09-23/24低值拖累为92.1%，但09-26～28恢复到95.7%；DSSU/DAU 同样在最近3日恢复到81.5%。当前搜索核心仍健康，不支持重做搜索产品。
- Mature New DSSU 1–7d reuse 最新成熟到09-22；09-15～22 加权约 **39.7%**，低于此前42.2%和45%目标。拉新已经重新变强，但“第二次回来”的问题仍没有解决。

### 渠道解释

- Web qualified views：09-17～22=`979`（163.2/day）→09-23～28=`1231`（205.2/day），约 **+25.7%**，与 App 新增上升方向一致，但没有 user-level join，不能写成严格因果。
- **Baidu 是最明显的新增量来源**：116→235 views（约+103%），attributed downloads 47→92，CVR 40.52%→39.15%，即流量翻倍而质量基本没降。当前瓶颈更像百度流量规模，不是首页 CRO。
- **Direct 明显增长但不可当作独立渠道成功**：164→284（约+73%）。Direct 混合了真实直达、Referer 丢失和部分分享场景，只能视为“未细分的高位新增”。
- **NSQ 流量没有放大，但转化显著变好**：421→420 views 基本持平；已归因 downloads 110→166（约+50.9%），source-level CVR 26.13%→39.52%。这给 09-23 上线的 winner hero CTA 提供强方向性支持，但文章级 denominator 语义仍不完美，所以先保持当前设计，不追加第二变量。
- Google 71→61 views（-14%）但 conversion 39.44%→54.10%，是高质量小量渠道；ChatGPT 11→13、downloads 5→6，继续是高意图长尾，不是规模引擎。
- `alternativeto` tracker 从09-24开始出现 23 views / 5 attributed downloads（09-23～28），但总账上一状态仍是 `PREPARED_PENDING_EXTERNAL_SUBMISSION`；在确认真实上架/来源前不得把这23次访问当作平台分发成功。

### 数据质量警告

- 09-25/26 出现 `unknown` download clicks=`200/183`，远高于对应可归因流量，导致 raw total downloads 会出现“下载数 > landing views”的假象。渠道分析继续只用 finite-source attributed clicks / trusted first-party clicks；最近6日 trusted first-party clicks 237→322（约+35.9%），真实下载意图仍是上升的。
- 当前最需要修的是 **Analytics verification / recovery**，不是 App 搜索或渠道本身。deep repair 必须先做 R2 receive-day checkpoint + D1 write/read budget 评估，再分段闭合，禁止删除 failure marker 或把 observational 强行改成 verified。

### Scale / Hold / Kill

- Baidu：`SCALE / PRESERVE CONVERSION`，优先研究为何 09-26 放大，不盲改首页。
- NSQ：`KEEP / CTA DIRECTIONALLY POSITIVE`，等完整7/14日窗口再裁决，不同时叠加新变量。
- Search core：`KEEP`，最近3日产品质量护栏健康。
- Retention：`PRIORITY PROBLEM`，mature reuse 39.7% 仍低于45%。
- Analytics verification：`P0 DATA OPS REPAIR`；完成前把09-23～28标为 observational，而不是丢弃，也不能宣称正式 verified。

---

## 2026-09-29 — 首页 CRO 与下一阶段增长优先级复盘

- ID：`REVIEW-HOME-CRO-GROWTH-PRIORITY-20260929`
- 状态：已分析 / 首页新实验尚未启动。
- 首页最近窗口（2026-09-23～28，finite-source、page=home）：Baidu=235 views /92 clicks /39.15%；Google=52/28/53.85%；Direct=151/55/36.42%；NSQ→home=419/85/20.29%；ChatGPT=13/6/46.15%；GitHub=11/9；AlternativeTo=23/5。主要已归因 source 合计约904 views /280 primary downloads，约31.0%。
- 判断：首页不是当前首要瓶颈。搜索/直达用户 CVR 已较强，且现有 `hero` placement 在 trusted clicks 中明显占主导，因此不做大改版、不增加更多重复 CTA、不动 title/H1/SEO metadata。
- 测量缺口：首页 GitHub/蓝奏 `data-backup-download` 当前只改 href，未进入 download attribution；因此现有 homepage CVR 是 primary tracked download 的下限。正式 CRO 前应先补备用下载点击归因，外观不变，积累至少3个完整日基线。
- Proposed experiment：`EXP-CRO-HOME-TRUST-002`（未启动）。只改 Hero CTA 下的一行 evergreen trust microcopy，例如“无需注册 · 无广告 · 官方签名 APK”，保持标题、截图、CTA 文案/位置、SEO metadata、备用下载位置不变。目标 7日 source-stratified homepage download rate 相对提升≥15%（约31%→35%+），且 Baidu/Google/Direct 各自不恶化。
- 预期上限：按当前约151 clean home landings/day，绝对 CVR +3pp 约多4.5 tracked downloads/day；+5pp 约多7.5/day。说明首页 CRO 值得做，但单靠它不可能把约300 DAU推到500。
- NSQ winner CTA：`cili-search-tools-2026` 9/17～22 为19 clicks（3.2/day）；变更后完整日 9/24～28 为39 clicks（7.8/day），方向约+146%，但尚未完成7日裁决且存在流量结构混杂。继续冻结其它变量，到7/14日门后再决定是否复制到第二/第三赢家页。
- Acquisition priority：最近6完整日相较前6日，Baidu views 116→235（+103%）且CVR仍约39%；NSQ views 421→420基本持平但 attributed downloads 110→166（+51%）。因此增长主线继续是“放大高意图流量 + 复制已验证 CTA”，而不是重新设计搜索核心。
- Retention：成熟 New DSSU 1–7d reuse 仍约39.7%，低于45%目标。下一产品增长实验应围绕真实回访理由（收藏/历史/追更资源更新等）选一个单变量，不做泛推送或大改App。
- Scale / Hold / Kill：Homepage=`MICRO-CRO ONLY`；Baidu=`SCALE TRAFFIC / KEEP HOME METADATA FROZEN`；NSQ=`KEEP CTA TEST / SCALE ONLY AFTER GATE`；mass SEO=`HOLD`；community discovery=`LOW PRIORITY`；retention=`NEXT PRODUCT LEVER`。

---

## 2026-09-29 — 最优增长方案执行：Analytics deep repair + 首页测量前置

- ID：`EXEC-GROWTH-OPTIMAL-20260929`
- 状态：`LOCAL_READY / PRODUCTION_BLOCKED_CF_OAUTH`
- 假设：当前首要风险是 Analytics verification 未闭合；首页真正适合的是测量先行的小 CRO，而不是大改版。生产写操作必须在 Cloudflare 写权限恢复后再执行。
- Analytics deep repair：新增 `cf-gateway/scripts/repair-analytics-shadow-deep.mjs`，只允许当前 `d1_daily_row_read_quota` 且 failure receive-day 与显式 checkpoint day 一致时执行；使用 09-23 已完整 R2 checkpoint（7061 batches / fingerprint `7061:dd3440c8`）做 exact receive-day replay，不伪造31日 full backfill。dry-run=`READY`，valid events=8914，conservative physical-write upper bound=10169，低于70k工程预算。
- Gateway integrity：新增 `shadow_repair_complete` 专用元数据语义；只有 `r2CheckpointVerified=true`、`failureReceivedAt` 精确匹配当前 R2 marker、`repairedReceiveDays` 覆盖 failure day 时才恢复 `repaired_by_incremental_checkpoint`。cached unresolved snapshot 检测到该状态时必须强制刷新 D1 rows，不能把旧 cache 直接改标签。
- Gateway 验证：`analytics-ops-failure-contract-tests.mjs` 新增 incremental checkpoint repair contract；`npm test` PASS；Wrangler 4.137.0 `deploy --dry-run` PASS，bindings 正常。
- 首页 measurement patch：`growth-attribution.js` 为现有 GitHub/蓝奏 `data-backup-download` 增加 sideband tracking；原外站 href/target 不变，同时向 `/go/download` 发 `redirect=manual + keepalive` GET，placement=`backup_github` / `backup_lanzou`，只传有限 `page/locale/source/placement`，不跟随主 APK 302。
- 首页验证：`geo-audit.js` 新增两个 mirror contract；GEO audit PASS；SEO Growth `214/214` PASS；SEO audit=`987 HTML / 214 indexable / 773 noindex / 214 canonical` PASS。
- 实验注册：`EXP-CRO-HOME-TRUST-002` 已进入 `MEASUREMENT_PRECONDITION_READY_LOCAL_BLOCKED_CF_AUTH`；信任文案 treatment **尚未启动**。生产 tracking 上线后需至少3个完整日 matched baseline，再只测试一行 evergreen trust microcopy。
- 生产阻塞：当前 Wrangler OAuth token 只剩 `offline_access/connectivity`，缺 `workers:write / d1:write / pages:write` 等；`versions list` 和 `whoami` 均返回权限不足。已实际触发 `wrangler login`，浏览器 OAuth 页成功打开，但120秒内未完成 callback；再次 `whoami` 仍未恢复写权限。因此本轮没有部署 Gateway、没有执行 D1 `--apply`、没有部署 Pages，生产保持原状。
- 归因可信度：本地代码、R2 checkpoint、预算、单测/全测与站点审计为严格；生产效果仍为0，因为写权限硬阻塞且未绕过。
- Scale / Hold / Kill：Analytics deep repair=`READY / WAIT CF AUTH`；homepage backup attribution=`READY / WAIT CF AUTH`；homepage trust copy=`HOLD UNTIL 3 CLEAN DAYS`；Baidu=`KEEP/DO NOT TOUCH HOME SEO`；NSQ hero CTA=`KEEP UNTIL 7/14D GATE`。
- 下一裁决点：Cloudflare OAuth 恢复后，顺序固定为 Gateway deploy → 09-23 deep repair apply → 公网 `operational_verified=true` readback → Pages deploy measurement patch → 3完整日 baseline → 再决定是否启动 trust-copy treatment。

---

## 2026-09-29 — 首页视觉刷新：功能优先的精品化基线

- ID：`EXEC-HOME-VISUAL-REFRESH-20260929`
- 状态：`LOCAL_VISUAL_BASELINE_FROZEN / PRODUCTION_BLOCKED_CF_OAUTH`
- 目标：在不动 title / description / canonical / H1 语义、不改主下载目标、不污染 NSQ 现有实验的前提下，把首页从普通软件下载页提升为更克制、更可信的精品工具官网；下载便利性优先于装饰。
- 视觉动作：Hero 改为白+浅冷灰+品牌蓝体系；桌面保留双设备层叠预览，手机仅保留单设备，避免样机压过 CTA；功能区、截图区、底部下载区统一圆角/留白/阴影层级；去除首页旧紫红渐变感，保留轻量动态并兼容 reduced-motion。
- 下载动作：Hero 主下载 URL/page/placement 保持不变；GitHub/蓝奏均保留；移动端顶部导航新增始终可见的 `placement=nav` 下载触点，360～430px 均为80×44px；Hero 主下载58px，备用下载46px，满足移动端易点按要求。
- 移动节奏：第一轮390px Hero=978px / page=3936px；审查后收敛为 Hero=854px / page=3416px（约缩短13%），主下载仍在 y≈260，GitHub/蓝奏在 y≈364/418，全部处于首屏下载路径内。
- 响应式实测：360×800、390×844、430×932、1280×900、1440×1000 均 `horizontalOverflow=false`；360px 顶栏专门收紧品牌至132×32、语言80×38、下载80×44，无重叠。
- 真实 HTTP 渲染：五视口全部 `consoleErrors=[]`，字体 loaded；不是只用 file:// 假通过。桌面首屏 Hero=808px，主 CTA=154×58，两个备用入口各255×48；移动端 Hero≈850px，主/备用下载均可直接操作。
- 视觉密度审查：桌面首屏保持高留白（约85%高亮区域）以形成精品工具感，移动端因真实 App 截图提升视觉锚点与层次，不再堆额外卡片/文案；未继续为了“更炫”增加粒子、3D或营销装饰。
- 回归：GEO audit PASS；SEO Growth 214/214 PASS；SEO audit 987 HTML / 214 indexable / 773 noindex / 214 canonical PASS。
- 实验隔离：`EXP-CRO-HOME-TRUST-002` treatment 仍未开始。此次视觉刷新与备用下载测量必须一起生产上线并冻结，随后重新积累至少3个完整日 post-refresh baseline，再单独测试 trust microcopy；禁止拿旧31%直接作为 treatment baseline。
- 生产状态：Cloudflare `whoami` 于21:04仍因 OAuth 权限/过期失败；本轮未部署 Pages，因此公网首页仍是旧版。没有绕过权限、没有虚报上线。
- Scale / Hold / Kill：视觉基线=`FREEZE`；下载可发现性=`KEEP`；首页 SEO metadata=`FREEZE`；trust microcopy=`HOLD UNTIL 3 CLEAN DAYS`；继续避免多变量 CRO。

---

## 2026-09-29 — 首页 V1 正式发布 + 下载链路全量验收

- ID：`DEPLOY-HOME-VISUAL-V1-20260929`
- 状态：`PRODUCTION_LIVE / BASELINE_COLLECTING`
- Cloudflare：OAuth 重新授权成功；Gateway Worker 发布成功，version=`4e14dfe6-dbdc-4de1-8429-bab02323ec9d`；Pages 发布成功，deployment=`https://2a179c31.magnetgoogo-site.pages.dev`，主域 `https://magnetgoogo.com/` 已回读到 `home-redesign`。
- Analytics：09-23 exact R2 checkpoint deep repair 实际执行39条 D1 queries，rows read=558768 / rows written=2663；脚本最终返回 `PASS_REPAIRED / operational_verified=true / repaired_by_incremental_checkpoint`。后续只读稳定返回 `PASS_NOOP / operational_verified=true` 且 exit0；期间修复了 Node24/Windows 成功分支强制 `process.exit(0)` 触发 libuv assertion 的假失败问题（BL-062），未发生第二次 D1 写入。
- 国内镜像：阿里云 `/var/www/magnetgoogo-site` 仅原子替换 `index.html / style.css / js/growth-attribution.js`，备份留在 `/home/admin/magnetgoogo-deploy-20260929T2125/backup`；远端 SHA 与本地一致，`sudo nginx -t` PASS，服务器侧 `https://cn.magnetgoogo.com/` 回读 `home-redesign`，CSS/JS=200。
- 主下载严格验证：生产 `/go/download?page=home&locale=zh-CN&placement=hero` 完整下载 APK=33,637,658 bytes，SHA-256=`2fc09f84e3fc0916cb3ffd82d8a467b1537030d31fe271e7906eb97fa230c27d`，与本地正式 release APK 完全一致。
- GitHub 备用：`releases/latest` HTTP200，最终落到 `v0.2.8`；GitHub asset `app-release.apk` 完整下载同样为33,637,658 bytes且 SHA-256 与正式 APK 完全一致。
- 蓝奏备用：当前页面 HTTP200 / 入口可达；其下载为动态反自动化桥接，本轮自动化未取得可信的完整 APK 字节流，因此只记 `PAGE_REACHABLE`，不虚报 full-byte PASS。
- 公网完整性：主域首页含 GitHub/蓝奏两个 `data-backup-download`；style.css=200；`js/growth-attribution.js`=200；首页实际引用33个同源资源全部成功、0 broken refs；正式 `verify-deploy.ps1` 9/9 PASS；GEO/SEO Growth/SEO audit 仍为 PASS。
- 实验状态：`EXP-CRO-HOME-TRUST-002` 改为 `BASELINE_COLLECTING_PRODUCTION`。2026-09-29 是晚间部署 partial day，不进入 clean baseline；第一个完整日为 2026-09-30，至少收集 3 个完整日后再单独测试 trust microcopy。当前视觉、SEO metadata、CTA 位置继续冻结。
- Scale / Hold / Kill：视觉 V1=`FREEZE`；backup measurement=`LIVE`；trust copy=`HOLD >=3 COMPLETE DAYS`；Baidu=`KEEP SCALE / SEO METADATA FREEZE`；下载链路=`PRIMARY+GITHUB PASS / LANZOU PAGE_REACHABLE`。

---

## 2026-09-29 — 首页生产乱版热修：静态资源缓存错配

- ID：`HOTFIX-HOME-CACHE-BUST-20260929`
- 状态：`PRODUCTION_FIXED / BASELINE_START_UNCHANGED_2026-09-30`
- 现象：首页视觉 V1 发布后，用户端出现全页乱版；冷缓存自动化验收却正常。
- 根因：生产 `style.css` / growth tracker JS 旧响应允许浏览器缓存4小时；HTML 结构与 CSS 同批大改时，已有用户可能加载新 HTML + 旧 CSS。线上文件 SHA、Tailwind runtime 均正常，因此不是错误文件或脚本被拦截。
- 修复：HTML 引用改为 `style.css?v=3c68ec22`、`/js/growth-attribution.js?v=c8addc6b`；SEO Growth audit 支持 tracker 路径带版本 query；Pages 与 CN 镜像同步。
- 严格视觉证据：同一 Chrome/390×844 同时截 localhost 与公网，平均像素差0.16 / RMS1.73；1440公网与冻结基线平均像素差0.19。说明生产视觉恢复为冻结 V1，而不是另做一版。
- 下载护栏：Hero 主下载再次 GET 为302→v0.2.8 APK；本次 hotfix 不改 CTA、下载目的地、SEO metadata 或 trust microcopy。
- 实验影响：09-29 本来就是 partial deployment day，因此不作为 baseline；clean baseline 仍从09-30开始，至少3个完整日。此次 hotfix 只修资源一致性，不新开 CRO 变量。
- 永久门禁：以后 HTML 与 CSS/JS 结构性同发必须使用内容指纹/版本化 URL，并增加 warm-cache 发布验收。仅检查200、SHA一致或冷缓存截图不再足够。
- Scale / Hold / Kill：视觉 V1=`KEEP/FREEZE`；cache-bust=`KEEP AS RELEASE CONTRACT`；trust microcopy=`HOLD UNTIL 3 CLEAN DAYS`。

---

## 2026-09-30 — 当前增长主线全量执行（排除收藏留存）

- ID：`EXEC-GROWTH-MAINLINE-20260930`
- 用户裁决：执行当前全部增长主线，但**不做第4项收藏/追更留存实验**；本轮不修改 App 留存功能。
- Analytics：发现新的 unresolved shadow failure=`2026-09-29T23:59:44.417Z`。使用 verified R2 receive-day checkpoint `7384:6d43d524` 做 exact replay；41 条 SQL 分2块执行，最终 `PASS_REPAIRED / operational_verified=true / repaired_by_incremental_checkpoint`，latest_day=`2026-09-30`。因此增长数据重新恢复正式裁决资格。
- Growth Daily：09-30 重新执行 Search Console ingest、NSQ Search Console ingest、NSQ opportunities、Growth KPI、Opportunity Report，5/5 PASS；L3 App 状态恢复 `OK / operational_verified=true`。
- 首页 CRO：`EXP-CRO-HOME-TRUST-002` 继续 `BASELINE_COLLECTING_PRODUCTION`。09-30 是新版首页第一个完整 baseline 日，视觉/SEO metadata/H1/CTA位置/信任文案全部冻结；至少到10-03拥有3个完整日后才允许单独启动 trust-copy treatment。
- Baidu：执行 `EXP-CHANNEL-BAIDU-HARVEST-001` 的 existing-URL harvest，不新增 URL、不改首页。普通收录 API 两组高意图 canonical 共10条全部 accepted（4/4 + 6/6），当日 quota 10→0；日志保存在 `magnetgoogo-site/.baidu-push-log/`。当前 source×page conversion 仍显示 Baidu 几乎全部价值集中在 home，因此不制造额外页面改动。
- NSQ：`EXP-NSQ-WINNER-HERO-CTA-001` 保持唯一变量；当前 `nsq:cili-search-tools-2026` source-attributed page-click diagnostic=70。09-30 尚未形成完整 post-change 第7日，故状态继续 ACTIVE、禁止复制到第二/第三页；最早10-01按完整7日窗口裁决。
- Uptodown：正式 APK preflight PASS：0.2.8(12)、package=`com.magnetgoogo.app`、33,637,658 bytes、SHA-256=`2fc09f84e3fc0916cb3ffd82d8a467b1537030d31fe271e7906eb97fa230c27d`；icon与4张截图存在。平台已迁移至 `https://www.uptodown.dev/`，Developers Console 已在用户电脑打开。当前唯一未闭合步骤是平台认证会话+人工审核；在平台确认前严禁记录为 submitted/live。
- Retention：`EXP-RETENTION-NEW-DSSU-REUSE-001` 改为 `HOLD_NO_FAVORITES_RETENTION_CHANGE`。保留39.3% reuse诊断数据，但本轮不实现收藏/追更等 App 留存功能。
- 归因可信度：Analytics / Baidu API / Growth Daily 为强证据；NSQ 仍等待完整7日因果窗口；Uptodown 仅完成本地与入口 preflight，尚无平台 submission receipt。
- Scale / Hold / Kill：Analytics=`RESTORED`；Homepage=`FREEZE/MEASURE`；Baidu=`SCALE EXISTING URL HARVEST`；NSQ=`KEEP TEST / NO COPY BEFORE GATE`；Uptodown=`READY_AUTHENTICATED_SUBMISSION`；Favorites retention=`HOLD / USER DECLINED`。
- 下一裁决点：10-01 裁决 NSQ 7日 CTA；10-03 裁决首页3日 baseline 是否足够稳定进入 trust-copy test；Uptodown 以平台实际提交/审核回执为唯一上线依据。

---

## 2026-10-01 — NSQ winner Hero CTA 7日裁决

- ID：`REVIEW-NSQ-WINNER-HERO-CTA-7D-20261001`
- 实验：`EXP-NSQ-WINNER-HERO-CTA-001`
- 状态：`HOLD_NO_REPLICATION_7D_TRAFFIC_GUARDRAIL`
- 数据权威：10-01 重新执行 Growth Daily 后，L3 App=`OK / operational_verified=true`，最新完整日=2026-09-30；Growth D1/R2 integrity 无 unresolved shadow failure。Search Console 当次 OAuth 为 `BLOCKED_EXTERNAL_AUTH`，但本实验裁决使用一方 D1/R2 landing/download 数据，不依赖 GSC；GSC 仅保留09-30 last-good，不影响本次 CTA 门禁。
- 可比窗口：baseline 使用变更前完整日 2026-09-17..22（6日）；09-23 23:40 才上线 CTA，09-23 为混合日故排除；post 使用 2026-09-24..30（7个完整日）。
- NSQ qualified views：baseline=421（70.17/day）；post=415（59.29/day），日均 **-15.51%**。因此明确违反 success_rule 中“without reducing NSQ channel qualified views”的流量护栏。
- NSQ channel downloads：baseline=110 / CVR26.13%；post=144 / CVR34.70%，CVR 相对 **+32.80%**，下载日均约 +12.21%。这是正向转化信号，但不能覆盖流量护栏失败。
- Winner page `nsq:cili-search-tools-2026` downloads：baseline=19（3.17/day）；post=43（6.14/day），日均 **+93.98%**，显著超过 +30% 点击提升目标。
- 裁决：**7日 gate 不通过，禁止复制 CTA 到第二/第三赢家页**。原因不是 CTA 无效，而是实验合同要求“点击提升 + 渠道 qualified views 不下降”同时成立；当前只满足前者。不得为了追求规模放宽既定门禁。
- 动作：不新增 indexable URL，不改第二/第三页，不改 title/body/canonical；当前 winner 页继续保持唯一 Hero CTA 变量冻结，等待14日 checkpoint（2026-10-07完整日结束后）再看流量是否恢复。若14日仍未同时满足两项条件，则停止扩量并按实验合同决定撤回/结束；在此之前不叠加新变量。
- 归因可信度：页面点击/渠道 landing/download 为 production D1 read model + R2 raw audit 的强方向证据；文章级 landing denominator 仍不能伪造，因此 winner 页使用 click/day，渠道流量护栏使用 NSQ source qualified views/day。
- Scale / Hold / Kill：CTA current winner=`KEEP FROZEN TO 14D`；replication=`HOLD`；new NSQ page changes=`HOLD`。
- 下一裁决点：2026-10-08 上午，以截至10-07的完整日做14日 checkpoint；不提前复制。

---

## 8. 长期原则

增长的第一目标不是“做更多动作”，而是找到**可重复、可测量、可扩大的新增 + 复用路径**。

已经证明的东西要继续放大；没有效果的东西要停；无法归因的东西先补测量；样本不足的东西继续观察；任何失败都必须留下记录，避免下一次从头再试。
