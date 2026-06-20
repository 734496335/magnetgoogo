# Broadcast Engine Post-Fix Review - 2026-06-20

## 结论

本轮 4-loop 修复已经覆盖了大部分上一轮 FR-01~FR-10 问题：task 级 approve/reject、awaiting_approval start guard、createJob 返回 DB row、CF Gateway header secret、server .env 预加载、generation_failed 冷却重试、Dashboard 401 toast 等均有代码证据，并通过语法检查。

仍有 5 个需要继续闭环的问题。其中 2 个 High 会导致别名平台或老库升级路径在真实环境中失效，建议优先交给下一轮 AI 修复。

## 验证摘要

| 项目 | 结果 |
|---|---|
| 语法检查 | PASS: `node --check` 覆盖 config/store/discovery/index/executor/rateLimiter/campaign/server |
| 新空库 createJob | PASS: `twitter/default` 入库为 `x/real_x_profile`，`payload_json` 为 string |
| CF Gateway query secret | PASS: admin secret 只读取 `X-Admin-Secret` header |
| server .env 顺序 | PASS: 在 `ADMIN_SECRET` 读取前执行轻量 `.env` loader |
| v1 老库迁移 | FAIL: `user_version=1` 且缺 FR-10 列时不会补列 |
| twitter-only config | FAIL: job 入库为 `x/default`，rateLimiter 返回 `platform_disabled` |
| campaign twitter alias | FAIL: config 只有 `x` 时，`launchCampaign({ platform: "twitter" })` 抛 `Platform config not found` |

## Issue PF-01 - High - `user_version` 迁移守卫会跳过 FR-10 新列

### 证据

- `admin-server/broadcast/store.js:93-104` 使用 `USER_VERSION = 2`，但 `last_attempt_at` 与 `generation_retry_count` 仍放在 `if (currentVersion < 1)` 内。
- `admin-server/broadcast/store.js:180-181` 身份迁移结束后直接把 `user_version` 设为 2。
- 隔离验证：构造一个 `user_version=1`、`discovered_posts` 缺少 FR-10 列的旧库，加载 `store.js` 后 `user_version` 变为 2，但两个列仍不存在；调用 `updateDiscoveredPost(... last_attempt_at ...)` 报 `no such column: last_attempt_at`。

### 风险

如果线上 DB 曾经被某个中间版本标记到 `user_version=1`，本轮代码会认为迁移已完成，导致 discovery generation_failed 重试路径运行时报 SQL 错误。更糟的是身份迁移会把版本推进到 2，后续自动修复更难触发。

### 修复 workflow

1. 将 schema 迁移拆成按版本递增的 migration steps：
   - v1: jobs retry/defer/task columns。
   - v2: discovered_posts `last_attempt_at`、`generation_retry_count`、`idx_discovered_posts_reply_job_id`。
2. 不要在 FR-01/FR-09 数据迁移 IIFE 内更新 `user_version`；数据迁移使用 `_meta` 自己的幂等标记即可。
3. 每个 schema migration step 使用 `safeAddColumn()` 和 `CREATE INDEX IF NOT EXISTS`，并只在该 step 完成后推进 `user_version`。
4. 加一个启动自检 helper：读取 `PRAGMA table_info(discovered_posts)`，如果缺 retry 列，即使 `user_version >= 2` 也补列并记录 warning。

### 验收

```bash
cd admin-server
node --check broadcast/store.js
```

再跑两个隔离 DB 用例：

1. 空库启动后，`discovered_posts` 包含 `last_attempt_at` 和 `generation_retry_count`，`user_version >= 2`。
2. 人工构造 `user_version=1` 且缺列的旧库，加载 `store.js` 后两个列被补齐，`updateDiscoveredPost()` 不再报错。

## Issue PF-02 - High - config 平台别名没有归一化，`twitter` 配置会被 canonical job 绕开

### 证据

- `admin-server/broadcast/config.js:50-61` `normalize()` 直接保留 `raw.platforms` 原始 key，没有把 `twitter` 合并到 canonical `x`。
- `admin-server/broadcast/store.js:259-264` `createJob()` 入库前把 `twitter` canonicalize 为 `x`，再用 `resolveAccount("x", ...)`。
- `admin-server/broadcast/rateLimiter.js:87` 只查 `cfg.platforms[canonPlatform]`。
- 隔离验证：config 只有 `platforms.twitter.account_profile = "tw_profile"` 时，`createJob({ platform: "twitter", account: "default" })` 得到 `job.platform = "x"`、`job.account = "default"`，随后 `canAct("x","default")` 返回 `{ allowed:false, reason:"platform_disabled" }`。

### 风险

如果现有配置或 UI 里仍存在 `twitter` key，任务会被入库为 `x`，但配置查找只认 `x`，导致平台禁用、account 归一化失败、rate limit 错误。FR-01/FR-09 只修了 job/lock/key，没有修配置边界。

### 修复 workflow

1. 在 `config.normalize()` 中对平台 key 执行 `canonicalPlatform(name)`。
2. 如果 alias key 与 canonical key 同时存在，明确 merge 策略：canonical key 优先，alias key 只补缺省字段；写入 `saveConfig()` 时只保留 canonical key。
3. `getPlatform(name)` 改为 `cfg.platforms[canonicalPlatform(name)] || null`。
4. `resolveAccount()` 保留 direct + canonical fallback，但在 normalize 后应主要命中 canonical。
5. 写一次配置迁移或保存时规范化，避免 `broadcast-config.json` 长期保留 `twitter`/`x` 双 key。

### 验收

隔离用例：

```js
// config 只有 platforms.twitter
const job = store.createJob({ platform: "twitter", account: "default", payload_json: { body: "b" } });
assert.equal(job.platform, "x");
assert.equal(job.account, "tw_profile");
assert.equal(rateLimiter.canAct(job.platform, job.account).allowed, true);
```

## Issue PF-03 - Medium - campaign 入口仍用原始 platform 查配置

### 证据

- `admin-server/broadcast/campaign.js:28` 使用 `cfg.platforms[platform]`。
- `admin-server/broadcast/campaign.js:45-48` 创建 task 时保存原始 `platform`。
- `admin-server/broadcast/campaign.js:79-82` createJob 传入原始 `platform`，虽然 store 会 canonicalize job，但前面的 config lookup 已经可能失败。
- 隔离验证：config 只有 `platforms.x` 时，`launchCampaign({ platform: "twitter" })` 抛 `Platform config not found for: twitter`。

### 风险

FR-09 声称 `x/twitter` 别名统一，但 campaign API 仍不能接受 `twitter`。这会让 Dashboard/API 的别名入口表现不一致。

### 修复 workflow

1. `campaign.js` 引入 `canonicalPlatform()`。
2. 函数入口立即计算 `const canonPlatform = canonicalPlatform(platform)`。
3. config lookup、task platform、campaign metadata、createJob platform 使用 `canonPlatform`。
4. 如果 `contentGen.generateVariant()` 或 OpenCLI 需要原始平台名，单独传 `cliPlatform` 或 `displayPlatform`，不要污染 DB identity。

### 验收

config 只有 `x` 时：

```js
await campaign.launchCampaign({ platform: "twitter", templateId, count: 1 });
const task = store.listTasks({ source_type: "campaign" })[0];
const job = store.listJobs({ campaign_id: campaignId })[0];
assert.equal(task.platform, "x");
assert.equal(job.platform, "x");
```

## Issue PF-04 - Medium - discovery 新记录仍可保存 alias platform，post/job identity 不一致

### 证据

- `admin-server/broadcast/discovery.js:309` `upsertDiscoveredPost()` 保存 `platform: post.platform`。
- `admin-server/broadcast/discovery.js:355-356` createJob 同样传 `post.platform`，但 store 会 canonicalize job。
- 隔离验证：`enqueueReply({ platform: "twitter" ... })` 后，`discovered_posts.platform = "twitter"`，关联 job 的 `platform = "x"`。

### 风险

同一条传播链路里 discovered post 与 job 平台身份不同。当前状态同步主要靠 URL/`reply_job_id`，所以不一定立刻炸，但列表过滤、后续平台统计、迁移增量数据都会出现 `twitter`/`x` 混存。

### 修复 workflow

1. `discovery.js` 入口为每个 post 计算 `canonPlatform = canonicalPlatform(post.platform)`。
2. `upsertDiscoveredPost()`、`createJob()`、task platform 使用 canonical platform。
3. 如 search/opencli 需要 `twitter` 命令，保留单独的 `cliPlatform`，但 DB/storage/filter 使用 canonical。
4. `store.listDiscoveredPosts({ platform })` 也应 canonicalize filter.platform。

### 验收

```js
const res = await discovery.enqueueReply({ platform: "twitter", url, title, excerpt, relevance: 0.9 }, false);
const post = store.getDiscoveredByUrl(url);
const job = store.getJob(post.reply_job_id);
assert.equal(post.platform, "x");
assert.equal(job.platform, "x");
```

## Issue PF-05 - Medium - job 级 approve/reject 仍会绕过 discovered/task 状态同步

### 证据

- `admin-server/broadcast/index.js:162-170` `/jobs/:id/approve` 只把 job 设为 `queued`。
- `admin-server/broadcast/index.js:176-184` `/jobs/:id/reject` 只把 job 设为 `rejected`。
- task 级 approve/reject 已经同步 discovered post 与 task counts，但 job 级 API 仍公开存在。

### 风险

Dashboard 主路径已经改到 task API，但外部调用或旧 UI 仍可调用 job API。这样会出现 job 已 queued/rejected，而 discovered post 仍停在 `pending_approval`，task status/counts 也可能不刷新。

### 修复 workflow

1. 抽一个 `transitionJobApproval(jobId, nextStatus)` helper，内部统一：
   - 更新 job status。
   - 通过 `getDiscoveredByReplyJobId()` 同步 discovered post。
   - 如果 job 有 `task_id`，刷新 task counts，并按所有子 job 状态推导 task status。
2. task approve/reject 与 job approve/reject 共用该 helper。
3. 如果决定废弃 job 级审批 API，则让 `/jobs/:id/approve|reject` 返回 409，并提示使用 `/tasks/:id/approve|reject`；不要保留静默不同步路径。

### 验收

创建一个 discovery reply job 后分别调用 job/task approve：

```js
assert.equal(store.getDiscoveredByReplyJobId(job.id).status, "queued");
```

reject 同理应为 `rejected`，且 task counts/status 不滞后。

## 建议修复顺序

1. **Loop 1: Schema migration hardening** - 先修 PF-01，避免所有后续 discovery 重试被老库 schema 卡死。
2. **Loop 2: Identity boundary normalization** - 合并 PF-02/PF-03/PF-04，一次性把 config/campaign/discovery/list filters 全部 canonical。
3. **Loop 3: Approval transition unification** - 修 PF-05，把 job/task/discovered 状态转移收敛到一个 helper。
4. **Loop 4: Regression tests** - 加隔离 DB 测试覆盖空库、v1 老库、twitter-only config、campaign alias、discovery alias、job-level approve/reject。

## 已确认闭环项

- FR-02 Dashboard task approve/reject 主路径已改 task API。
- FR-03 `/tasks/:id/start` 对 `awaiting_approval` 返回 409，Dashboard 自动 start 有状态 guard。
- FR-06 `createJob()` 返回 `getJob(id)`，payload_json shape 与 DB 一致。
- FR-07 CF Gateway 不再接受 query secret。
- FR-08 server 在读取 `ADMIN_SECRET` 前加载 `.env`。
- FR-10 新空库 generation retry 字段存在，enqueueReply 有 `{ created, status }` 结构化返回。
