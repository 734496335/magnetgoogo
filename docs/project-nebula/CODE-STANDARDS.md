# Project Nebula 代码规范

文档版本：V0.1
更新时间：2026-04-16

> 说明：本文件主要约束「供给侧规则生产」与「Web 客户端执行/渲染」两条主链路，并把 `sources.json` 契约作为中心。高风险或边界不清的能力仅保持占位，不展开可执行的对抗性实现细节。

## 1. 工程范围与目标

本规范要求工程满足：
- 契约优先：`sources.json` 与客户端解析器必须 schema 化、可回滚
- 可观测：任何失败都可追溯到 `search_id` / `rule_id` / 错误类型
- 安全治理：默认安全（禁用高风险预览、输出转义、最小权限）
- 文档联动：关键改动必须更新 `DEV-LOG.md`

不在本规范提供的内容：
- 高风险能力的实现细节（包括对抗/规避类能力）。相关部分仅保留“待设计”接口与门禁要求。

## 2. 代码风格与结构

### 2.1 语言与类型系统
- Web 客户端优先使用 TypeScript。
- 所有外部数据（`sources.json`、接口返回、LLM 输出）必须经过 schema 校验后进入业务逻辑。

### 2.2 目录结构建议（按模块拆分）
- `apps/web/`：Next.js/React Web 客户端
- `packages/sources-schema/`：`sources.json` schema 与共享类型（供供给侧和客户端复用）
- `services/data-factory/`：供给侧规则生产流水线（脚本/服务）
- `services/rule-registry/`：规则发布与 manifest 生成（可用静态托管 + manifest）
- `packages/ui/`：可复用的 UI 组件（状态条、结果卡片、标签药丸等）

> 如果你的仓库尚未成型，可先只建立 `packages/sources-schema/`，其它模块按实际进度创建。

## 3. `sources.json` 契约规范

### 3.1 Schema 版本策略
- `schema_version`：当字段语义/类型发生不可兼容变更才升级 MAJOR。
- `client_min_compatible_version`：当客户端不再兼容某些规则时提升 MINOR/MAJOR，并在客户端侧给出明确提示。

### 3.2 向后兼容规则
- 客户端必须允许规则对象携带未知字段（不因未知字段失败）。
- 缺失的可选字段使用明确默认值（禁止默默“猜测”影响语义的字段）。
- 废弃字段需要在文档中标注替代字段，并保留至少一个兼容周期。

### 3.3 质量与健康字段约束
- `quality.score` 必须在 0-100 范围内。
- `health.status` 仅允许 `green|yellow|gray`。
- `health.status_detail` 用于记录细粒度状态：`ok|healed|waf|404|expired|unreachable|parsing_failed`。
- 客户端执行时必须把 `health` 参与排序或降权，并在 UI 层体现状态灯语义。

## 4. 架构编码规范

### 4.1 纯函数优先
- 规则解析、结果归一化、标签提取（正则/启发式）应尽可能为纯函数；
- 纯函数输入输出必须可单元测试，不依赖浏览器全局状态。

### 4.2 可测试性
- 为以下核心逻辑建立单测（至少覆盖 happy path + 异常路径）：
  - `sources.json` schema 校验失败时的错误对象结构
  - 并发队列在取消情况下不会泄漏/重复渲染
  - 结果去重逻辑（按 hash 或唯一键）
  - 标签提取与安全渲染（XSS 防护）

## 5. 错误处理与可观测性

### 5.1 错误类型与错误上下文
- 任何异常必须携带上下文：
  - `search_id`
  - `rule_id`
  - `stage`（如 `bootstrap|execute|normalize|render`）
  - `error_code`（稳定可枚举）

### 5.2 日志与指标命名
- 日志：结构化 JSON（禁止拼接字符串日志作为主要载体）
- 指标：建议使用以下维度：
  - `ruleset_id`
  - `health.status`
  - `http_status`（若与请求相关）
  - `error_code`

### 5.3 失败降级优先级
- 首先降级：跳过不可用规则，尽量产出部分结果
- 再降级：降低并发、延长 backoff
- 最后降级：提示用户当前不可用原因，并建议刷新/更换关键词

## 6. Web 客户端并发规范

- 使用 `AbortController` 实现取消；
- 并发上限必须可配置，默认不超过 `ruleset.max_sources_per_search` 与全局上限的最小值；
- 每条请求必须有明确的超时；
- 结果渲染必须“增量 + 去重”，不能等待全部完成后再一次性渲染。

## 7. 安全治理规范

### 7.1 输出编码与渲染
- 所有来自 `sources.json` 或解析结果的文本必须进行 HTML 转义；
- 链接仅允许显式的 URL 安全检查（协议白名单如 `http/https`），并加上 `rel="noopener noreferrer"`；
- 页面渲染禁止 `dangerouslySetInnerHTML`（除非有严格的白名单 sanitizer，且需在 PR 中说明）。

### 7.2 文件类型与预览禁用
- 任何疑似可执行文件扩展名（例如 `.exe`）必须默认禁用预览；
- 对未知类型使用保守策略：只展示文本元信息，不做富预览。

### 7.3 机密与密钥
- 客户端侧不得暴露需要长期保密的密钥；
- 任何密钥只能存在于服务端并通过受控接口下发必要最小范围的能力（如果后续引入服务端）。

## 8. AI 交互规范（供给侧）

### 8.1 Prompt 与输出契约
- LLM 输出必须为严格 JSON；
- 输出 JSON 必须经过 schema 校验（同样复用共享 schema 或单独的 LLM 输出 schema）；
- 当置信度低于阈值时，必须触发人工复核流程或回退到安全默认策略。

### 8.2 审计记录
- 保存最小审计信息（避免保存敏感数据）：
  - prompt 模板版本
  - 输入摘要（可脱敏）
  - 结构化输出摘要（可脱敏）
  - schema 校验结果（通过/失败 + 错误路径）



## 9. 文档联动（强制）
- 任何新增/修改会影响 `sources.json` 契约、错误类型或 UI 状态机的代码变更，必须在 `DEV-LOG.md` 追加记录。

