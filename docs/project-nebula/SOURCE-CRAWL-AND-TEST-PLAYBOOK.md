# 搜索源发现、爬取、适配与测试权威手册

> **用途**：新增源、找失效品牌新域名、适配 parser/handler、验证 yellow、全面测试现有源时统一按本文执行。
>
> **最高原则**：发现 ≠ 可用；单次出 magnet ≠ green；Python 侧能搜 ≠ App 一定能搜；实时搜索路径禁止 LLM；所有状态升降级先产证据、再人工确认。

---

## 1. 供给侧完整流水线

```text
候选发现
→ 真实域名还原
→ 去重/已知源排除
→ Funnel Stage0 可达性
→ Stage1 页面信号
→ Stage2 HTTP 搜索/详情跟进
→ Stage3 浏览器补刀（高潜才开）
→ crawler_v3 分类/Tier 验证
→ 双 bait 差异化 magnet 证据
→ 人工确认 health 状态
→ contract/pytest/enum
→ 源发布
→ K30S App 真实消费
```

每一层有不同目标，不要跳层。

---

## 2. 候选发现来源

优先顺序：

1. 已知导航站/聚合站；
2. 已知 green 源友情链接；
3. 品牌名 + 官网/最新地址；
4. 搜索引擎 dorking；
5. 失效 `brand_family` 的 rediscovery；
6. 历史候选池复核。

### 导航站不是源

导航站只产生 candidate：

```text
导航首页
→ 内部详情页
→ 外链/中转/base64/data-url/meta refresh/JS location
→ 真实 target origin
```

真实 origin 拿到后必须重新走验证流水线。

### 候选池

未验证域名应进入候选文件/`aux_candidate_pool.json`/pending 结构，不直接写成 green。

---

## 3. 真实外链还原优先级

对导航详情页按：

```text
1. 直接 external <a>
2. /go /jump /redirect 中转
3. url= 明文
4. url= base64
5. data-url / data-href
6. meta refresh
7. window.location / location.href
8. 主体文本 URL
```

还原后：

- normalize scheme/host；
- 去掉 tracking 参数；
- 按 origin 去重；
- 与 `sources.json` 现存 origin/rule id 交叉检查。

---

## 4. Fast Discovery Funnel

当前主入口：

```bat
python magnet/funnel_pipeline.py --candidates <candidates.json> --out funnel_report.json --summary-out funnel_summary.json
```

### Stage0 — reachability

便宜探测：

- HTTP reachable；
- 404；
- WAF；
- timeout/DNS/5xx。

不要在 Stage0 做 selector 结论。

### Stage1 — cheap signals

检查：

- magnet/btih/torrent/磁力/种子关键词；
- search form；
- parking/expired 特征；
- 页面规模。

这一步只判断“值不值得继续”。

### Stage2 — HTTP search

顺序：

```text
首页 form 推断
→ 少量 fallback template
→ 搜索页 evidence
→ interstitial follow
→ detail follow
```

支持：

- direct magnet；
- 40-hex BTIH；
- 32-base32 BTIH；
- detail URL evidence。

### Stage3 — browser verify

默认不开：

```bat
python magnet/funnel_pipeline.py ... --stage3
```

只给：

- JS/SPA；
- WAF 后可交互；
- HTTP 强信号但无结果；
- 详情点击/动态渲染。

必须设置严格预算，不能全量 browser 把跑批拖死。

---

## 5. Funnel 推荐命令

### 快速 0-2

```bat
python magnet/funnel_pipeline.py ^
  --candidates candidates.json ^
  --out funnel_report.json ^
  --summary-out funnel_summary.json
```

### 分批

```bat
python magnet/funnel_pipeline.py ^
  --candidates candidates.json ^
  --start 0 ^
  --limit 50 ^
  --stage0-timeout 3 ^
  --stage2-timeout 8 ^
  --max-seconds-per-site 30 ^
  --stage0-concurrency 120 ^
  --stage2-concurrency 40 ^
  --out funnel_report.json ^
  --summary-out funnel_summary.json
```

### 高潜 browser 补刀

```bat
python magnet/funnel_pipeline.py ^
  --candidates candidates.json ^
  --stage3 ^
  --stage3-timeout 25 ^
  --stage3-concurrency 4 ^
  --max-seconds-per-site 35 ^
  --out funnel_report.json ^
  --summary-out funnel_summary.json
```

### 当前治理要求

`--update-sources` 有写 `sources.json` 能力，但**不要直接作为默认发现流程的一部分**。

推荐：

```text
先 report-only
→ 人工 review green/yellow/gray 建议
→ 用户/开发者批准
→ 再显式修改 sources.json
```

---

## 6. 四种 parse strategy

当前架构认知：

### `list_page`

搜索结果页直接有 magnet/hash。

### `detail_follow`

列表页只有详情链接：

```text
search list
→ detail URL
→ magnet/hash
```

### `spa_xhr`

前端异步渲染：

```text
browser/network_idle
或 XHR/API 直接解析
```

### `nav_aggregator`

不是搜索源，回到 discovery，不进实时搜索 executor。

新源适配前先判断类型，避免用一个通用 selector 打所有站。

---

## 7. crawler_v3 运行模型

主 CLI：

```bat
python -m magnet.crawler_v3 --help
```

### classify

```bat
python -m magnet.crawler_v3 classify --origin https://example.com
```

用于看源会走什么 Tier。

### search

```bat
python -m magnet.crawler_v3 search "Inception" --origin https://example.com --limit 10
```

### Tier 结构

`orchestrator.py` 当前根据 detector plan 依次尝试：

```text
Tier0 HTTP
Tier1 Cloak/browser
Tier2 specialized handler
Tier3 user-assist stub
```

Tier 初始化 lazy + process cache；某一 Tier `TierError` 才继续 fallback。

不要看到 Tier0 empty 就直接说源死了，先看 plan 是否还有 handler/browser。

---

## 8. specialized handler 与 App 一致性

历史重大事故：

```text
crawler_v3 依据 tier_override/platform 走专用 handler
App 依据 search.handler 走 generic
```

结果：Python 验证通过，用户 App 0 结果。

因此新 handler 必须做**双端契约检查**：

```text
Python crawler_v3 handler
sources.json search.handler / capabilities
App searchRunner/search engine 对应 executor
```

如果是 App 端由统一 Web executor 消费，也要确认规则字段能把它路由到相同行为。

**“crawler PASS”不是 App PASS。最终必须 K30S 搜索。**

---

## 9. BTIH 合法性与结果绑定

当前唯一接受的 BTIH：

```text
40 位 hexadecimal
32 位 base32
```

不接受：

- 32 位 hex；
- 截断 hash；
- 任意 40 字符非 hash；
- `btih:abc` 测试占位。

### title 必须和 magnet 是同条证据

禁止：

```text
页面任意标题 + 页面全局任意 magnet
```

禁止 synthetic 用户标题：

```text
(brute) magnet...
hash: abcdef...
纯 hash
```

最终结果必须有：

- 合法 BTIH；
- 非空 title；
- title 不是 hash placeholder；
- title/magnet 来自同 entry、detail 或 magnet `dn` 自描述证据。

页面级 brute scan 只能在 magnet 自身有可信 `dn` 时转成用户结果。

---

## 10. Cookie / WAF 测试注意

### session cookie

浏览器工具常用：

```text
expires=-1
expires=0
```

表示 session cookie，不是“已经过期”。

### Set-Cookie `Expires`

HTTP：

```text
Expires=Wed, 21 Oct ...
```

中间逗号不能被当成下一 cookie 的简单分隔符。

### Tier1 challenge

Cloudflare/WAF marker 要 case-insensitive；交互验证窗口必须短于 browser 总 timeout。

当前 App/browser timeout 已保证能覆盖约 45s interactive verification，不要重新把 executor timeout 压到 10s。

### interactive verify

```bat
python -m magnet.crawler_v3 verify-interactive --origin https://example.com
```

适合需要人工过挑战后保存 cookie 的源。

测试完成后要验证 cookie store 真能在下一次 request 复用，不是只“浏览器里看起来过了”。

---

## 11. GREEN / YELLOW / GRAY 判定

### GREEN — 唯一当前定义

必须：

```text
reachable
+ bait A 搜出合法 magnet 集合 A
+ bait B 搜出合法 magnet 集合 B
+ overlap(A,B) < 0.8
```

至少两个不同 bait 都要有真实搜索变化。

### YELLOW

例如：

- 单 bait 成功；
- 多 bait 结果高度重合；
- WAF/需要人工适配；
- 页面明显相关但 parser 不稳定；
- detail/SPA 尚未适配。

### GRAY

例如：

- GFW/网络不可达；
- 404；
- 域名停放/过期；
- 当前环境无足够证据；
- 多轮确认不再是搜索站。

### 关于历史 `red`

旧文档中存在 `red` 概念，但**当前 `sources.json` contract 不允许 red**。

确定死亡/停放的源也只能按当前 enum 落到 `gray` + 合法 `status_detail`，细节写 `note/diagnosis`。

---

## 12. bait 策略

优先真实、多类别、可区分结果：

```text
Inception
Spider-Man
Avengers
复仇者联盟
One Piece
流浪地球
ubuntu
mp4（最后兜底）
```

按源类型选 bait，不要用明显不匹配的 query 判死源。

### 为什么至少两个 bait

一些假搜索/停放页会：

- 对任意 query 返回同一首页 magnet；
- 返回固定热门列表；
- query 参数根本没进入后端。

双 bait overlap 是最便宜的 anti-hallucination 证据。

---

## 13. deterministic test 与 live integration 分离

### deterministic gate

```bat
python -m pytest magnet/tests/crawler_v3 -m "not integration" -q
```

该 gate 应稳定，可用于 commit/release。

当前测试覆盖：

- orchestrator；
- Tier0；
- Tier1 markers；
- cookie store；
- Tier cookie integration；
- final output validation；
- specialized handlers。

### live provider test

公网会变：

- 站点临时 403；
- 结果数量变；
- DNS/GFW 波动；
- 资源库当前只有 4 条而旧断言写 >=5。

Live 失败要保存证据并分析 provider variability，不能为了变绿盲目重跑到成功。

---

## 14. 全量源静态审计

```bat
python scripts/audit_source_delivery.py sources.json --output scripts/source-delivery-audit.json
```

重点看：

```text
hardFindingCount
warningCount
greenRules
greenPools
executableRules
browserRules
handlerCounts
```

Hard finding 必须清零。

Warning 要逐条判断是否真实债务，不能“只看 return code”。

---

## 15. 源健康巡检的正确用法

旧 `scripts/health_check.py`：

```bat
python scripts/health_check.py
```

可以作为 reachability/report 辅助。

**不要默认运行：**

```text
--update
--deploy
```

因为当前项目明确要求 health 状态人工确认。

另外旧脚本部分策略只用 homepage/单 query/list selector，证据强度低于当前双-bait green 标准，所以不能用它自动升级 green。

---

## 16. `recheck --commit` 的边界

crawler_v3 CLI 有：

```bat
python -m magnet.crawler_v3 recheck ... --commit
```

它属于历史运维能力，**不符合当前“状态人工确认”红线的默认用法**。

正确：

```text
recheck/report
→ 保存结果
→ 人工确认
→ 手工/受控修改 sources.json
→ validate_enum
```

---

## 17. AI/LLM 的边界

### 实时搜索路径

**NO LLM**。

理由：

- 延迟不可接受；
- 成本；
- 不确定性；
- 用户搜索链必须 deterministic enough。

### 离线增强

可以用 LLM/Crawl4AI 帮助：

- selector proposal；
- 页面结构分类；
- brand rediscovery 辅助。

产物只能进入：

```text
proposal/pending
```

必须经过真实抓取证据后才能成为 production rule。

---

## 18. 修改源后完整测试顺序

```text
1. 单源 classify/search
2. 双 bait overlap 证据
3. specialized handler 单测
4. crawler_v3 not-integration 全套
5. audit_source_delivery
6. validate_enum ALL VALID
7. App TypeScript / source相关 adversarial
8. 生成 source pack
9. 公网 authority exact SHA
10. K30S EN + ZH 搜索
11. 需要时 benchmark/validation
```

### App 侧至少执行

```bat
cd magnetgoogo-app
npx tsc --noEmit
node scripts/app-adversarial-tests.mjs
```

源相关永久门禁包括：

- source authority trust order；
- expiry；
- 0-green reject；
- cookie；
- WAF timeout；
- result title/hash legality。

---

## 19. K30S 是最终消费真相

Python desktop 成功后，K30S 至少跑：

```bat
python scripts/test_k30s_search.py --compact --only "EN movie" --only "ZH movie" --output scripts/k30s-source-smoke.json
```

高风险源变更：

```bat
python scripts/test_k30s_search.py --benchmark --compact --output scripts/k30s-source-benchmark.json
```

必须：

```text
completed
hard=0
hash-placeholder=0
合理 loaded hosts/pools
没有全池异常 skipped
```

---

## 20. 失败证据保存

任何非预期失败：

```text
docs/project-nebula/_failures/YYYYMMDD-HHMM-<topic>.log
```

保存原始 stdout/stderr / provider response summary。

不能：

- 删除第一次失败证据；
- 只保留后来成功的一轮；
- provider 波动时反复重跑到满足旧阈值。

长期批处理同时写：

```text
magnet/run.log
```

---

## 21. 源适配 review 清单

```text
[ ] 这是搜索源，不是导航站
[ ] origin canonical
[ ] parse_strategy 合理
[ ] request template query 真生效
[ ] handler 路由 Python/App 一致
[ ] BTIH 只 40hex/32base32
[ ] title 与 magnet 同条证据
[ ] 不生成 synthetic/hash title
[ ] detail follow 不被 malformed magnet 阻止
[ ] cookie 生命周期正确
[ ] WAF/browser 有界 timeout
[ ] 两个 bait 都出 magnet
[ ] overlap < 0.8 才 green
[ ] status 修改有人确认
[ ] pytest pass
[ ] audit hard=0
[ ] enum ALL VALID
[ ] K30S real search pass
```

---

## 22. 相关文档

- `SOURCE-RELEASE-PLAYBOOK.md`
- `K30S-TEST-PLAYBOOK.md`
- `CRAWLER-ARCHITECTURE.md` — 架构演进背景
- `FAST-DISCOVERY-FUNNEL.md` — Funnel 参数细节
- `SOURCE-DISCOVERY-AND-VERIFICATION-STRATEGY.md` — 历史发现经验
- `USER-IMPACT-INCIDENTS.md`
