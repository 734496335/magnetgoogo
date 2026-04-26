# Project Nebula 代码迁移建议（契约对齐）

文档版本：V0.1
更新时间：2026-04-16

> 目的：让后续 AI 在“接手现有 Python 引擎代码”的基础上，把产物 `sources.json` 迁移到 `ARCHITECTURE.md` 里约定的契约（`schema_version / rulesets / rules / quality / health / tags` 等），并把现有实现里与“挑战/阻断”相关的能力改造成“替代输出（占位）”，避免引入对抗性实现细节。

## 0. 必读入口与阅读顺序（AI 续写导航）

1. 主架构：`[docs/project-nebula/ARCHITECTURE.md](docs/project-nebula/ARCHITECTURE.md)`
2. 里程碑与验收：`[docs/project-nebula/DEVELOPMENT-PLAN.md](docs/project-nebula/DEVELOPMENT-PLAN.md)`
3. 工程规范：`[docs/project-nebula/CODE-STANDARDS.md](docs/project-nebula/CODE-STANDARDS.md)`
4. 本文：`[docs/project-nebula/CODE-MIGRATION.md](docs/project-nebula/CODE-MIGRATION.md)`

阅读原则：
- 先理解 `sources.json` 契约差异，再改代码字段映射与 schema 校验。
- “待设计模块”只做输出契约与门禁，占位实现不应包含对抗性细节；如需挑战/阻断支持，仅输出 `skip/backoff/user_manual_step` 等策略信号。

## 1. 快速体检：现状与差距

### 1.1 现有 `sources.json` 结构（来自 `magnet/sources.json`）

当前仓库产物形如：
- 根对象：`app_config: { latest_version, force_update_url }`
- `sources: Source[]`
- 每个 `Source`：
  - `url`
  - `search_path`
  - `requires_waf_bypass`
  - `selectors: { list_item, title, magnet, size, date }`
  - `weight`

与 `ARCHITECTURE.md` 中建议的契约差异点包括：
- 缺少 `schema_version/generated_at/meta/rulesets/rules/quality/health` 等结构化字段。
- 现有 `selectors` 是可执行解析配置，但目标契约建议把它“版本化挂载到解析元数据”并通过 schema 演进管理。
- 现有 `requires_waf_bypass` 字段的语义需要调整为“挑战/阻断需求信号”，并把具体策略留在客户端降级逻辑里。

### 1.2 现有 Python 引擎模块职责（与迁移点对齐）

你现在的主要入口与模块为：
- `magnet/main.py`：串联 `Discovery -> get_baits -> Validation -> AIParser -> SourcesManager -> Healer`
- `magnet/discovery/*`
  - `discovery/discovery.py`：聚合搜索引擎发现 + 友情链接嗅探
  - `discovery/search_engine.py`：搜索引擎聚合 + bait 生成
  - `discovery/link_sniffer.py`：递归嗅探友情链接
- `magnet/validation/validation.py`
  - 延迟与搜索可用性测试
  - tags/weight 计算（当前 tags 为本地命名，例如“最新追更/经典收藏/二次元专精”）
  - 与“挑战/阻断”相关逻辑（当前代码存在交互式验证码分支）
- `magnet/ai_parser/ai_parser.py`
  - 生成解析规则：`search_path/selectors/requires_waf_bypass`
  - 具备 LLM 输出解析与启发式回退
- `magnet/utils/sources_manager.py`
  - 保存 `sources.json`，并进行“追加合并 sources[] + weight 排序 + 截断”
- `magnet/crawler/healer.py` 与 `magnet/crawler/extractor.py`
  - 用 selectors 从 HTML 抽取 magnet（并据此生成 heal report）

迁移核心在两条主线：
1. 把“规则生成与质量评分”的输出，改造成 `ARCHITECTURE.md` 的 `rulesets/rules/search/quality/health/tags` 契约。
2. 把现有“挑战/阻断”分支从“可执行接管”改造成“替代输出（占位）”，只保留客户端可消费的策略信号。

## 2. 契约迁移：`sources.json` 字段映射（用条目/要点）

下面给出从现状字段到目标建议字段的映射建议（用于指导实现时的结构重写）。

### 2.1 站点与身份标识
- `sources[].url`
  - 建议映射为：`rulesets[].rules[].site.origin`（或将 origin 拆成 `host`/`scheme` 后重组）
- `rulesets/rules` 需要稳定的 rule 标识
  - 建议新增：`rules[].id`（例如对 origin 做稳定 hash）

### 2.2 搜索请求模板
- `sources[].search_path`（例如 `"/search?q={query}"`）
  - 建议映射为：`rules[].search.request_template`
  - 实现要求：request_template 至少保留“路径模板 + query 占位符”，并可扩展为 host/path/参数映射对象

### 2.3 解析元数据与选择器
- `sources[].selectors`
  - 建议映射方式（两种选择，二选一，需保持 schema 一致）：
    1. 把 selectors 直接作为解析元数据字段挂载：`rules[].search.parse_metadata.selectors_vX`
    2. 在 schema 里为 selectors 预留扩展容器：`rules[].search.parse_metadata: { selectors, ... }`
  - 强制要求：必须引入版本化（例如 `selectors_version` 或 schema_version 升级策略），否则后续客户端难以处理兼容。

### 2.4 排序权威字段：weight / score / priority
- `sources[].weight`
  - 建议作为两级排序来源之一：
    - `rulesets[].priority` 与 `rules[].search` 失败率/成功率共同影响
  - 对齐到架构：你需要在迁移后决定“最终排序以哪个字段为准”：
    - 方案 A：`weight` -> `quality.score`（并保留缩放规则）
    - 方案 B：`weight` -> `rules[].priority`（并在客户端用 priority 降权/过滤）

### 2.5 标签体系：现有 tags -> 架构 tags
- 现有 tags（示例：`最新追更/经典收藏/二次元专精/Scam`）
  - 建议映射为 `ARCHITECTURE.md` 的标签：
    - `追新极客`
    - `经典老库`
    - `垂直专精`
    - `Scam`

### 2.6 health 与可观测证据
- 现有 `validation` 输出中没有明确 `health.status/last_checked_at/fail_count_30d`
  - 建议新增最小可用 health：
    - `health.status = green|yellow|gray`（可由 latency 与搜索成功率映射）
    - `last_checked_at = generated_at` 或当前执行时间
    - `fail_count_30d` 在早期可先置 0，后续再接入统计

### 2.7 高风险字段语义调整（只输出信号，不提供对抗性实现细节）
- `sources[].requires_waf_bypass`
  - 迁移建议：不要保留“bypass”语义
  - 建议替换为“挑战需求信号”占位字段（字段名你可自定，但必须能被客户端策略理解）：
    - `challenge_requirement: { required: boolean, type: "waf_or_captcha"|"unknown" }`
  - 文档门禁：禁止在 `CODE-MIGRATION.md` 中提供任何 cookie/UA 持久化注入、自动化接管、绕过实现细节。

## 3. 代码结构调整建议（按文件：如何改、怎么放、接口怎么抽象）

> 下面的“应该怎么写”是指文档层面的实现指令（给相对便宜的 AI 的可执行改法）。不涉及任何挑战/阻断绕过实现细节。

### 3.1 `magnet/utils/sources_manager.py`：发布与 schema 校验入口

你现在的 `SourcesManager` 做了两件事：
1) 组装旧结构 `{"app_config": ..., "sources": ...}`
2) 合并旧 sources 并按 weight 排序截断

迁移建议：
- 新增 schema 校验入口（最小版本）：
  - 在保存前对 `sources_json`（新结构）进行必填字段检查
  - 如果 schema 不通过，拒绝覆盖旧文件（保持 previous_good）
- 升级发布策略：
  - 由“追加合并 sources[]”升级为“基于 rulesets/rules 的发布 + previous_good 回滚”
  - 早期可以实现双输出：
    - 输出新结构：`sources.json`（遵循 `ARCHITECTURE.md`）
    - 输出旧镜像（可选）：`magnet_sources.json`（用于平滑过渡）
  - 同时输出 manifest（可选但推荐）：让客户端能识别 rulesets 与版本

实现落点建议（不强制具体代码，但给 AI 方向）：
- 把组装逻辑从 `update_sources_json()` 拆成：
  - `build_sources_payload(processed_sources)->new_sources_json`
  - `merge_rulesets(old, new, previous_good)->merged_payload`
  - `save_payload(payload)->void`

### 3.2 `magnet/validation/validation.py`：输出从 `weight/tags` 到 `quality/health`

你现在 `validate_sources()` 的输出是：
- `latency`
- `quality_score`
- `tags`
- `weight`
- `search_url_template`

迁移建议：
- 把输出结构改为更贴近架构的概念：
  - `quality: { score: number, tags: string[] }`
  - `health: { status, last_checked_at, fail_count_30d }`
  - `evidence: 可选（用于可观测追溯）`
- tags 映射：
  - 在 validation 层做“旧 tags -> 新 tags”的映射，保证后续 `sources_manager` 不再关心旧命名。
- 排序字段：
  - 明确是由 `quality.score` 还是 `priority` 作为客户端排序依据（在迁移时先选一个作为权威来源）。

挑战/阻断门禁：
- 现有代码存在交互式 captcha 分支与可能的会话处理。
- 在 `CODE-MIGRATION.md` 中你只需要指导新契约如何表达“挑战需求”：
  - validation 遇到阻断时返回 `challenge_requirement.required=true`
  - 同时返回 `health.status=gray` 或 `yellow`（看失败原因分类）
  - 不允许继续向下输出任何“用于绕过/接管”的字段到契约里

错误对象统一：
- 建议引入最小错误对象（便于后续客户端可观测）：
  - `{ search_id, rule_id, stage, error_code, details }`
  - 如果引入会影响现有代码结构太大，可先在文档中只要求“日志格式与字段名统一”，不要强制立刻改契约。

### 3.3 `magnet/ai_parser/ai_parser.py`：解析元数据契约（request_template + parse_metadata）

你现在 LLM/启发式的解析结果是：
- `search_path`
- `selectors`
- `requires_waf_bypass`

迁移建议：
- 把返回值改造成“解析元数据”：
  - `request_template`：至少包含 path 模板与 query 占位符（与 `ARCHITECTURE.md` 对齐）
  - `parse_metadata.selectors`：选择器集合（需版本化）
  - `challenge_requirement`：占位信号（从旧 requires_waf_bypass 抽象）
- 为 schema 演进增加门禁：
  - LLM 输出必须先结构化解析，再做 schema 校验
  - 校验失败必须回退到启发式解析或拒绝生成对应 rule（取决于你的容错策略）

### 3.4 `magnet/main.py` 与 `magnet/pipeline_runner.py`：把 pipeline 抽象成可追踪阶段

你现在 `main.py` 串联流程是顺序式打印。

迁移建议：
- 抽象成“阶段化 pipeline”，让每个阶段输出包含 run/search 标识（用于后续 DEV-LOG/可观测性对齐）。
- 建议阶段：
  - `Discovery -> DynamicBait -> Validation -> ParsingRules -> ScoringTagging -> SourcesJsonBuild -> SelfHealing -> Publish`
- 由于当前仓库没有明确 `search_id` 概念，迁移时可先做：
  - `run_id`：一次 pipeline 执行标识
  - `rule_id`：每个站点 rule 的稳定 id

### 3.5 `magnet/crawler/healer.py` 与 `magnet/crawler/extractor.py`：health 证据输出与契约对齐

你现在 healer 报告结构是：
- `status: ok/healed/failed`
- `magnets_found` 等

迁移建议：
- 在 healer 输出里加入 `rule_id`（来自 `sources_manager` 的稳定映射）
- 把 healer 的结果映射为 `health.status` 的证据（至少保证：
  - magnets_found > 0 -> health.green
  - magnets_found == 0 -> health.gray/yellow，具体由失败类型决定）

## 4. 待设计模块“占位与门禁”（明确：文档不提供对抗性实现细节）

请在本节只保留占位契约与门禁要求，强制引用主架构的占位章节：
- 引用：`ARCHITECTURE.md` 的 `7. 待设计模块（占位）`

占位要求（可直接照抄到你的新字段设计里）：
- 当遇到阻断/挑战：
  - 输出 `challenge_requirement.required=true`
  - 输出 `strategy` 只能属于：
    - `skip`
    - `backoff`
    - `user_manual_step`
 
- 客户端侧如何消费：
  - 若 `required=true`，则降权或跳过该 rule，并用 UI 展示失败原因统计（在架构里已定义为 `health` 状态灯与全局状态栏）

## 5. 测试与验收建议（对齐 `DEVELOPMENT-PLAN.md`）

建议你在现有的 `magnet/test_validation.py` 上补充/调整断言目标：
1. `sources.json` 新结构生成成功
2. `schema_version` 与必填字段存在（至少检查 `generated_at`、`rulesets[].rules[].quality/health/tags`）
3. tags 映射正确（旧标签名不再直接出现在输出中；应转为 `追新极客/经典老库/垂直专精/Scam`）
4. health.status 合理（绿色/黄色/灰色至少有对应输入分支）

## 6. 预计的目录/结构重组（可选）

当前仓库是纯 Python，尚缺 `shared schema 工程` 与 `web 客户端`。

为了让后续 Web 客户端能更容易复用契约，建议（只做建议，不强制在第一轮实现）：
- 新增目录：
  - `magnet/schemas/`：存放 `sources.json` schema 与校验逻辑（或仅放 Python 侧校验器）
  - `magnet/types/`：定义稳定的数据结构（方便 pipeline 阶段之间交换）

## 7. 跟踪与文档联动（强制）

当你完成任何契约字段迁移或错误码/错误对象结构变化时：
- 更新：`ARCHITECTURE.md` 对应字段描述
- 更新：`CODE-STANDARDS.md`（尤其是契约与错误上下文字段要求）
- 追加：`DEV-LOG.md` 新记录（必须包含关键改动摘要与未决项）

