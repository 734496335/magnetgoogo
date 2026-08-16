# Project Nebula 文档总索引

> **这是项目执行类文档的总入口。** 后续 AI/开发者开始 App、K30S、源、发版任务时，先从这里进入对应权威手册，不要直接从 DEV-LOG 里拼流程。
>
> `DEV-LOG.md` 是历史流水账；`TECH-CHALLENGES.md` 是难题追踪；下面标记为 **AUTHORITATIVE** 的 Playbook 才是当前执行路径。

---

## 1. 开始任何工作先读

1. 根 `AGENTS.md`
2. `docs/project-nebula/_progress.txt`
3. `docs/project-nebula/DEV-LOG.md` 顶部最新条目
4. `docs/project-nebula/TECH-CHALLENGES.md` 当前 open/researching
5. 本索引中与任务对应的 **AUTHORITATIVE** 文档

Python crawler 任务另外读：

```text
magnet/AGENTS.md
CODE-STANDARDS.md
```

---

# 2. App / Android / K30S

## `RELEASE-CHECKLIST.md` — **AUTHORITATIVE**

**何时读**：构建正式 APK、签名、归档、上传 R2/GitHub/阿里云/蓝奏云、改 config、官网发布、生产更新 E2E。

覆盖：

- 正式签名 authority
- forced final Release build
- `verify_release_apk.py`
- exact-SHA K30S Gate
- `releases/` 归档
- R2/GitHub/Aliyun/Lanzou 渠道
- 当前 config trust order
- Pages/mg-data/官网部署
- 旧版→新版生产更新 E2E
- rollback

## `K30S-INSTALL-PLAYBOOK.md` — **AUTHORITATIVE**

**何时读**：需要“安装到 K30S”“为什么没弹安装”“覆盖升级”“MIUI installer”。

覆盖：

- `adb install -r` 标准路径
- Gradle Debug install
- App 内 `content:// + ACTION_VIEW` 用户升级路径
- shell caller 为什么会被 MIUI 拒绝
- installed base.apk SHA
- `firstInstallTime`
- Git Bash `/sdcard` path conversion
- deep link `&` quote
- `run-as` Release 边界

## `K30S-TEST-PLAYBOOK.md` — **AUTHORITATIVE**

**何时读**：需要“全面测 App”“做主流程”“验证搜索/资源/详情/更新/生命周期”。

覆盖：

- Debug vs Formal 证据边界
- 4 query / 8 benchmark / 24 validation
- search report / result quality
- repeated same-query freshness
- Debug private cache smoke
- Formal WindowManager/framebuffer/logcat 测试
- HOT/COLD/force-stop
- Fatal/ANR/exit-info
- App 内生产更新 E2E

## `APP-SIGNING.md`

签名证书、指纹和历史迁移背景。**执行时不要把其中敏感字段复制到聊天/日志；构建变量以受保护本地环境为准。**

## Release 制品清单

- `../../releases/RELEASE-v0.2.6.md` — 当前 v0.2.6 正式 APK SHA/签名/K30S 验收与 public-release 状态。

## 历史真机证据

- `TEST-RESULT-20260803-v0.2.5正式包K30S充分验收.md`
- `TEST-RESULT-20260804-v0.2.3到v0.2.5-App内更新全链路.md`
- `TEST-RESULT-20260805-v0.2.5全链路公开发布与0.2.3公网升级验收.md`
- `TEST-RESULT-20260816-v0.2.6全链路公开发布.md` — v0.2.6 R2/GitHub/Aliyun/Lanzou/Pages/config 收敛与生产更新控制面证据；发布后 K30S old→new E2E 明确记录为工具安全层未执行。

这些用于查历史事实，不替代当前 Playbook。

---

# 3. 搜索源 / Crawler / 发布

## `SOURCE-CRAWL-AND-TEST-PLAYBOOK.md` — **AUTHORITATIVE**

**何时读**：找源、爬源、适配 handler/parser、验证 yellow、跑 crawler、全面源测试。

覆盖：

- candidate discovery
- 导航站真实外链还原
- Funnel Stage0-3
- parse strategy
- crawler_v3 Tier
- specialized handler Python/App 一致性
- BTIH/title binding
- Cookie/WAF
- 当前 GREEN 双 bait + overlap 标准
- deterministic vs live tests
- manual status governance
- K30S 最终消费验证

## `SOURCE-RELEASE-PLAYBOOK.md` — **AUTHORITATIVE**

**何时读**：源规则已改，要加密/发布；source envelope 快过期；端点不同步；App 拉不到最新源。

覆盖：

- content publish vs envelope-only renewal
- `sources.json` contract
- `encrypt_sources.py`
- `mg-data`
- 当前 authority/fallback trust order
- Pages/Gateway/Aliyun
- exact SHA convergence
- 8h/32h/72h renewal workflow
- App 30m/6h source refresh
- K30S consumption gate

## `SOURCE-SECURITY.md`

加密协议、安全设计背景。操作步骤以 `SOURCE-RELEASE-PLAYBOOK.md` 为准。

## `CRAWLER-ARCHITECTURE.md`

Crawler 架构演进和技术背景。不是操作 SOP。

## `FAST-DISCOVERY-FUNNEL.md`

Funnel 设计与参数历史细节。**状态枚举、GREEN 证据、是否允许自动写 status，以当前 AI-RULES + `SOURCE-CRAWL-AND-TEST-PLAYBOOK.md` 为准。**

## `SOURCE-DISCOVERY-AND-VERIFICATION-STRATEGY.md`

早期导航/候选发现经验。文中历史 `red` 状态不再属于当前 `sources.json` enum；执行时使用当前 Playbook。

## `MIGRATION-mg-data.md`

mg-data 迁移历史。旧 `Promise.any` 端点描述不再代表 v0.2.6 运行时 authority 逻辑。

---

# 4. 用户影响事故与经验

## `USER-IMPACT-INCIDENTS.md` — **AUTHORITATIVE / MUST-READ BEFORE RELEASE**

**何时读**：

- 任何 bug 修复；
- 全面代码审计；
- App 发版；
- 源发布；
- 看到“以前好像遇到过类似问题”。

记录：

- 用户症状
- 用户影响
- 根因
- 为什么漏测
- 修复
- 永久测试门禁
- 禁止复发规则

新用户影响 bug 修完必须追加到这里。

---

# 5. 当前状态与历史

## `_progress.txt` — **当前状态 authority**

只放当前 phase / 已完成 Gate / 阻塞，≤30 行。

## `DEV-LOG.md` — **历史实施流水账**

每次工作在顶部追加。适合追“某 bug 当时具体怎么修”，不适合从几千行里自己拼当前 SOP。

## `TECH-CHALLENGES.md`

长期难题/方案研究。

## `_failures/`

失败原始证据。遇到类似失败先查这里，尤其：

- Gradle / Release build
- K30S MIUI/UIAutomator
- DevSpace 502
- provider live fluctuation
- signing/installation

---

# 6. 安全与代码规范

## `CODE-STANDARDS.md`

Python/TypeScript/结构化错误/日志规范。

## 根 `AGENTS.md`

m023 工作区行为红线、Plan-Act-Verify、状态契约。

## 主项目 `D:\lpproduct\magnet\docs\project-nebula\AI-RULES.md`

跨项目最高规范与物理拓扑。若其中某个旧操作描述与当前代码/本索引 Playbook 不一致，**先核对当前代码并更新文档，不要静默采用明显过期流程**。

---

# 7. 按任务快速跳转

| 用户/任务说法 | 先读 |
|---|---|
| “安装正式版到 K30S” | `K30S-INSTALL-PLAYBOOK.md` → `K30S-TEST-PLAYBOOK.md` |
| “全面测试 App” | `K30S-TEST-PLAYBOOK.md` + `USER-IMPACT-INCIDENTS.md` |
| “发 0.x.x” | `RELEASE-CHECKLIST.md` + `USER-IMPACT-INCIDENTS.md` |
| “我上传蓝奏云” | `RELEASE-CHECKLIST.md` 的归档/Lanzou/config 顺序 |
| “更新 config / 用户收不到更新” | `RELEASE-CHECKLIST.md` |
| “源更新/发布” | `SOURCE-RELEASE-PLAYBOOK.md` |
| “源要过期了” | `SOURCE-RELEASE-PLAYBOOK.md` renewal |
| “找新源/救活源” | `SOURCE-CRAWL-AND-TEST-PLAYBOOK.md` |
| “Python 能搜 App 不能搜” | `SOURCE-CRAWL-AND-TEST-PLAYBOOK.md` handler 一致性 + incidents |
| “历史搜索不刷新” | `USER-IMPACT-INCIDENTS.md` INC-20260816-09 + K30S test freshness |
| “这个失败以前见过吗” | `USER-IMPACT-INCIDENTS.md` + `_failures/` |

---

# 8. 文档冲突处理规则

文档很多，历史条目一定可能落后。冲突时按：

```text
1. 根 AGENTS / 主项目 AI-RULES 的红线
2. 当前代码真实行为
3. 本索引标 AUTHORITATIVE 的 Playbook
4. _progress 当前状态
5. DEV-LOG 最新证据
6. 旧设计/迁移/测试报告
```

如果第 1 项中的**操作性描述**已经与当前代码事实冲突（例如历史多端点 `Promise.any`），不要反向把代码改回旧行为；先确认这是已修复事故，再更新规范/Playbook。

---

# 9. 文档维护 Gate

每次改变以下业务链时，同步更新对应 Playbook：

```text
Android 安装方式              → K30S-INSTALL
真机测试脚本/证据方式          → K30S-TEST
App build/config/channel       → RELEASE-CHECKLIST
source encryption/authority    → SOURCE-RELEASE
crawler/handler/green criteria → SOURCE-CRAWL-AND-TEST
用户影响 bug                  → USER-IMPACT-INCIDENTS
```

不能只改代码/DEV-LOG，不改长期 Playbook。
