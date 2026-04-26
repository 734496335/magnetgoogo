# Project Nebula 星云引擎架构设计

文档版本：V0.1（由开发规划文档驱动的首版架构草案）
更新时间：2026-04-16

> 说明：本文件覆盖当前阶段可落地的系统设计。高风险或边界不清的能力在对应章节统一标记为「待设计」，并仅给出必要的输入/输出契约与风险边界，避免展开对抗性实现细节。

## 0. 设计目标与原则

### 0.1 目标
- 零运营成本：通过 `sources.json` 规则分发与边缘侧并发编排，降低中心化爬虫/带宽 OPEX。
- AI 驱动：在「数据供给侧」通过 LLM 辅助生成可复用的“解析元数据”，并形成评分/标注闭环。
- 顶级流媒体级体验：Web 客户端以流式增量渲染降低等待焦虑。

### 0.2 约束
- **物理隔离**：供给侧与客户端侧解耦，CDN/静态文件作为唯一强耦合边界之一。
- **可版本化契约**：`sources.json` 与客户端解析器严格 schema 化，并支持向后兼容。
- **默认降级**：对站点阻断（例如 `403`）采用降级策略（重试/换源/跳过/提示），避免引入不确定的对抗性实现细节。

## 1. 系统分层（物理隔离）

将系统拆为 4 个逻辑端：

1. **DataFactory（供给侧）**：抓取/解析/规则提取/评分/导出 `sources.json`
2. **RuleRegistry（规则仓库）**：发布与版本管理（CDN/静态托管）
3. **Client（Web 客户端）**：拉取 `sources.json` -> 并发检索 -> 聚合流式渲染
4. **Business&Risk（商业与风险运营）**：权限、计费、强制更新与内容治理

### 1.1 全局数据流

```mermaid
flowchart TB
  subgraph factory[DataFactory]
    A1[SiteIngestion] --> A2[ParserRuleExtraction]
    A2 --> A3[ScoringAndTagging]
    A3 --> A4[SourcesJsonBuild]
  end
  subgraph registry[RuleRegistry]
    B1[VersionedPublish] --> B2[CDNStaticSourcesJson]
  end
  subgraph client[Client(Web)]
    C1[BootstrapFetchSourcesJson] --> C2[SearchOrchestrator]
    C2 --> C3[ConcurrentRequests]
    C3 --> C4[ResultNormalizer]
    C4 --> C5[IncrementalUI]
  end
  subgraph ops[Business&Risk]
    D1[AuthAndEntitlements] --> D2[ClientFeatureFlags]
    D1 --> D3[ForceUpdateDecision]
  end

  B2 --> C1
  D2 --> C2
  D3 --> C1
```

## 2. `sources.json` 规则与契约

`sources.json` 是客户端的核心输入契约。目标是：
- 让客户端只负责“执行”和“渲染”，供给侧只负责“生成和质量控制”；
- 让规则可版本化、可回滚；
- 让解析与评分元数据可观测。

### 2.1 版本与兼容
- `sources_json_version`：规则文件版本号（建议使用语义化版本 `MAJOR.MINOR.PATCH`）。
- `client_min_compatible_version`：客户端最小兼容版本（按部署滚动策略使用）。
- 规则集按 `ruleset_id` 区分：例如 `base`（基础源库）、`high_speed_private`（高速私有库）。

### 2.2 推荐字段

> 下面为“建议 schema”，实现时应以 TypeScript schema（例如 `zod`）进行校验。

根对象：
- `schema_version`: string
- `generated_at`: ISO-8601 时间
- `rulesets`: Ruleset[]
- `meta`: 可选元数据（例如发布者签名、统计摘要）

Ruleset：
- `ruleset_id`: string（如 `base` / `pro_private_v1`）
- `priority`: number（数字越大优先）
- `max_sources_per_search`: number（客户端并发上限建议）
- `rules`: SourceRule[]

SourceRule：
- `id`: string（规则唯一标识）
- `site`: { `name`: string, `origin`: string }
- `capabilities`: { `supports_search`: boolean, `supports_detail`: boolean }
- `search`: SearchSpec
- `quality`: QualitySpec

SearchSpec：
- `request_template`: RequestTemplate（方法、路径/host 选择、参数映射等）
- `timeout_ms`: number
- `retries`: { `max_attempts`: number, `backoff_ms`: number }

QualitySpec（来自评分引擎）：
- `score`: number（0-100）
- `tags`: string[]（例如 `追新极客`、`经典老库`、`垂直专精`、`Scam`）
- `health`: { `status`: `green|yellow|gray`, `last_checked_at`: string, `fail_count_30d`: number }
- `evidence`: 可选（用于可观测追溯，如探测摘要哈希）

### 2.3 `tags` 体系

- `追新极客`：高时效性、高命中率（诱饵命中率指标）
- `经典老库`：长期稳定、高覆盖率
- `垂直专精`：在特定领域（动漫/游戏/影视）表现更佳
- `Scam`：疑似欺诈/恶意内容（客户端侧应显式降权或默认禁用）

### 2.4 客户端降级与容错
- 对网络异常或阻断：遵循 `timeout_ms` 与 `retries`；
- 对连续失败：按 `health.status` 动态调整参与排序；
- 对规则 schema 不合法：跳过该规则并上报（不影响整体可用性）。

## 3. DataFactory

DataFactory 是“规则生产线”。关键是可复用、可测试、可审计。

### 3.1 动态测试诱饵库（Dynamic Bait）

目标：
- 使用公开榜单/开放数据源生成“测试词”；
- 把“测试词 -> 探测 -> 命中 -> 评分”形成数据管道；
输出：
- `bait_list`: string[]（测试词）
- `bait_context`: 可选（来源、领域、时间窗口）
- `bait_run_id`: string（用于追溯）

### 3.2 敏捷 AI 站点入库（LLM 辅助提取）

职责分界：
- LLM 负责：生成“解析元数据/选择器/接口模板”的**通用候选**；
- 系统负责：对候选进行结构化校验、抽样验证、回退策略；
- 禁止 LLM 生成并用于执行任何自动化绕过/接管实现细节。

建议输出契约（供给侧内部使用，最终会被映射为 `sources.json`）：
- `parse_metadata`：字段映射、容错策略、字段提取路径
- `selector_candidates`：候选选择器列表 + 置信度
- `request_candidate`：请求模板（host/path/param 映射）候选 + 置信度

### 3.3 多维测试与智能打分（Scoring & Tagging）

建议指标（供给侧实现可观测）：
- 命中率：诱饵词返回有效结果的比例
- 时效性：结果新鲜度（如发布时间/版本号差）
- 可靠性：连续失败率、超时率
- 风险标记：疑似欺诈/恶意文件类型（通过内容治理与启发式规则）

输出：
- `score`: 0-100
- `tags`: string[]
- `health`: green/yellow/gray

### 3.4 规则部署流水线（Deployment）

目标：
- 发布 `sources.json` 前进行 schema 校验与抽样探测；
- 支持回滚（保留 `previous_good` 版本指针）；
- 基础源库与高速私有库的发布节奏可不同。

关键机制：
- `ruleset_id` 分离（基础/私有）
- 版本化发布（CDN 缓存策略 + manifest）

## 4. Client（Web 客户端）

本项目在“Web 优先”落地：提供极简检索体验，并实现流式增量渲染。

### 4.1 组件划分（建议）
- `SearchBootstrap`: 获取 manifest + 拉取 `sources.json`
- `SearchOrchestrator`: 并发请求队列、取消与降级策略
- `SourceExecutor`: 根据 `SourceRule.search` 生成请求并执行
- `ResultNormalizer`: 统一结果结构（文件名、链接、大小、hash 等）
- `StreamingRenderer`: 增量渲染与状态条更新

### 4.2 并发编排模型
- 并发上限：由 `ruleset.max_sources_per_search` 与客户端全局上限共同决定
- 超时：每个规则按 `timeout_ms`
- 重试：按 `retries`
- 取消：用户停止搜索时，通过 `AbortController` 取消未完成请求

### 4.3 智能本地探针（Ping Routing）

建议做法：
- 在发起请求前，对规则对应域名进行轻量连通性探测；
- 使用探测结果进行路由降权/跳过；
- 明确探针仅用于性能与体验，不用于绕过站点风控。

输入：
- `rules[*].site.origin`
- `ping_budget_ms`（例如 1000ms）

输出：
- `routing_decisions`: { rule_id -> allowed:boolean, reason:string }

### 4.4 流式渲染体验

- 全局状态栏：展示已尝试节点数、已完成数、累计结果数
- 增量结果队列：先返回的源优先渲染并去重
- 交错渐显：对新批次结果使用轻量动画（避免影响可访问性）

### 4.5 预览与恶意文件治理
- 文件类型识别：对疑似可执行文件（如 `.exe`）默认隐藏/禁用预览
- 文本安全：结果字段统一做 HTML 转义，避免 XSS
- 访问安全：下载触发通过用户显式操作（不做后台自动下载）

## 5. 商业逻辑层

### 5.1 免费与 Pro 的权限模型
- 免费：限制每日搜索次数、仅拉取 `base` 规则集
- Pro：免广告、解锁 `pro_private` 规则集、跨设备收藏同步

### 5.2 鉴权与计费接口（抽象）

建议将服务端实现抽象为以下接口：
- `GET /entitlements/me`：返回用户当前权限与配额
- `POST /usage/consume`：扣减一次搜索额度（或返回余额）
- `GET /manifest`：返回 force_update_url 与当前可用 ruleset 映射

## 6. 风控运营层

### 6.1 强制热更新机制（UX 与版本契约）

- 客户端冷启动拉取 manifest；
- 如果检测到 `force_update_url` 存在且版本号需要更新，则弹窗说明并强制更新；
- 不允许“跳过更新”的弱提示：要么更新、要么终止可用功能（以产品规则方式解释原因）。

## 7. 待设计模块（占位）



### 7.1 WAF/验证码穿透与交互接管机制（待设计）
- 待补齐输入：
  - 阻断响应信息：HTTP 状态码（如 `403`）、响应头/页面摘要
  - 站点挑战类型分类（抽象枚举）
  - 客户端可用的替代策略集合（例如跳过/更换源/人工引导）
- 待补齐输出：
  - 处理策略：`skip` / `backoff` / `switch_source` / `user_manual_step`
  - 体验与可观测指标：失败原因聚合、策略命中率

### 7.2 Cookie/User-Agent 劫持与持久化注入（待设计）
- 待补齐输入：
  - 会话管理需求（例如用户手动登录后会话如何用于后续请求）
  - 用户同意与隐私约束（最小化持有、最短生命周期）
- 待补齐输出：
  - 会话模型（明确哪些字段只在用户手动步骤后使用）
  - 安全审计条款（字段级脱敏、日志策略）

### 7.3 应用商店“暗门”隐藏关键功能（待设计）
- 待补齐输入：
  - 目标发布渠道与其要求清单
  - 功能披露策略：哪些功能对审核可见，哪些默认关闭
- 待补齐输出：
  - 发布配置矩阵（渠道 -> 功能开关 -> 文案与隐私说明）
  - 版本发布与强制更新路径

### 7.4 核心网络请求深度混淆实现细节（待设计）
- 待补齐输入：
  - 需要保护的资产范围（例如 API keys/付费接口的最小暴露面）
  - 可接受的安全威胁模型（避免“对抗绕过”的实现细节）
- 待补齐输出：
  - 安全架构选择：服务端鉴权与签名、客户端最小化暴露策略
  - 风险评估：可维护性、调试成本、性能影响

## 8. 可观测性与质量门禁（建议）
- 数据供给侧：
  - **KPI: 页面解析成功率**：对于能够正常访问（非 404/Expired/Unreachable）且有磁力资源展示的域名，其磁力解析失败率需 **低于 8%**。
  - 抽样验证通过率、解析成功率、评分分布与健康度分布
  - 规则 schema 变更影响范围（按 MAJOR/MINOR 标记）
- 客户端侧：
  - 规则跳过原因统计、超时/失败率、去重率
  - 流式渲染延迟（从开始搜索到首批结果渲染时间）

---

## 追加：本文件如何被后续 AI 续写
- 当你实现某个模块时，必须把“新增/修改的 `sources.json` 字段与契约”同步反映到本文件对应字段区；
- 对待设计模块，除“占位契约与风险边界”，不应添加任何可执行的对抗性细节。

## 阅读入口（给 AI 续写）
- 现有代码如何迁移到本契约：`[docs/project-nebula/CODE-MIGRATION.md](docs/project-nebula/CODE-MIGRATION.md)`

