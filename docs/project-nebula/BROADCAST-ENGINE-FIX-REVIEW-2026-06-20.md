# Broadcast Engine Fix Review 2026-06-20

范围：复核 `broadcast-engine-review-fixes-12` 与 `broadcast-engine-multi-agent-review` 后的实现，重点阅读 `DEV-LOG.md` 最新两条、`admin-server/broadcast/*`、`admin-server/server.js`、`admin_templates/dashboard.html`、`cf-gateway/src/index.js`。

结论：第一轮 12 项 P0/P1/P2 中，X reply 路由、空 body 拒绝、pause/start、failureStreak TTL、defer_count、LLM 失败不发兜底营销文案、语法检查等关键点已经有实质修复。但当前仍存在几处“状态机和身份归一化未闭环”的问题，会导致审批 UI 误操作、限频按错误账号计算、发现帖状态与 job 状态不一致。建议下一轮 AI 按下面 workflow 闭环修复。

## 已确认修复

- `admin-server/broadcast/tieredPost.js:231-247`：`x/twitter + kind=comment + target` 会走 `twitter reply`，不是新帖。
- `admin-server/broadcast/tieredPost.js:179-185`：空 body 会被拒绝。
- `admin-server/broadcast/index.js:399-414`：`/tasks/:id/start` 已把 `paused` jobs 恢复为 `queued`。
- `admin-server/broadcast/index.js:315-317`：手工任务 `ai_smart` 返回明确 400。
- `admin-server/broadcast/index.js:342-365`：`random_template` 每个 item 独立随机选模板并注入 body。
- `admin-server/broadcast/rateLimiter.js:117-133`：failureStreak TTL 已无条件检查，min_gap 返回 `remaining_ms`。
- `admin-server/broadcast/executor.js:314-333`：defer_count 已加入，并有上限。
- `admin-server/broadcast/discovery.js:291-295`：LLM 失败时标记 `generation_failed`，不再创建营销兜底 job。
- `admin-server/server.js:112-121`：broadcast API 不再接受 query secret，未配置 `ADMIN_SECRET` 时返回 503。
- `admin-server/server.js:929`：本地 admin 拉 CF Gateway analytics 改用 `X-Admin-Secret` header。

## 仍需修复

### FR-01 High: account 归一化仍未真正修复，限频账号与 OpenCLI 账号不一致

定位：
- `admin-server/broadcast/store.js:167-168` 只把空 account 归一化为 `'default'`。
- `admin-server/broadcast/index.js:276-280`、`359-365` 多处显式传入 `'default'`。
- `admin-server/broadcast/executor.js:288-305` 中 `account = job.account || pCfg.account_profile`，当 job.account 是 `'default'` 时不会使用真实 profile。
- `admin-server/broadcast/tieredPost.js:160-167` 执行 OpenCLI 时又把 `'default'` 替换为 `pCfg.account_profile`。

影响：rateLimiter、logs、failureStreak、hasRunningJob 使用 `default`；OpenCLI 实际使用 `real_profile/k2dn57uc`。这会让“清除真实账号 failureStreak”的修复失效，也可能导致同一真实账号在不同任务中绕过限频。

修改建议：
- 新建 `identity.js` 或放入 `config.js`：`canonicalPlatform(name)`、`resolveAccount(platform, requestedAccount, cfg)`。
- `createJob()` 入库前就写入真实 account_profile，不存 `'default'`。
- executor、rateLimiter、tieredPost、logs 全部使用同一 canonical platform/account。
- 对历史 DB 中 `account='default'` 的 queued/running/awaiting jobs 做一次启动迁移，按当前平台配置补真实 account。

验证：
- 临时 DB 创建 `platform=x/account=default` job 后，DB 中 account 应为 `k2dn57uc` 或配置 profile。
- `rateLimiter.canAct('x','k2dn57uc')` 与 OpenCLI `--profile` 一致。

### FR-02 High: Dashboard 的“批准/拒绝任务”实际调用 job 接口且传的是 task id

定位：
- `admin_templates/dashboard.html:1518-1519` 在 task 列表上调用 `approveTask(t.id)` / `rejectTask(t.id)`。
- `admin_templates/dashboard.html:2508-2524` 这两个函数请求 `/api/broadcast/jobs/:id/approve|reject`。
- task id 与 job id 不是同一实体。

影响：用户点击 task 的“批准”可能批准同 id 的另一个 job，或者 404；当前没有真正的 task 级审批入口。审批模式下新建的任务无法从 UI 正确放行。

修改建议：
- 增加 `POST /tasks/:id/approve`：把该 task 下 `awaiting_approval` jobs 批量改为 `queued`，task.status 改为 `queued`，同步 discovered_posts `pending_approval -> queued`。
- 增加 `POST /tasks/:id/reject`：把该 task 下 `awaiting_approval` jobs 改为 `rejected`，task.status 改为 `rejected`，同步 discovered_posts。
- Dashboard task 列表按钮调用 task 端点；job 级 approve/reject 放到详情弹窗的子 job 行内。

验证：
- approval_required=true 创建 manual task 后，点 task 批准，所有子 jobs 从 awaiting_approval 变 queued。
- 不允许 task id 误调用 job approve。

### FR-03 High: createTask 后 Dashboard 自动 start 会破坏审批状态

定位：
- `admin_templates/dashboard.html:2566-2567` 创建任务后无条件 `startTask(data.taskId)`。
- `admin-server/broadcast/index.js:399-414` `startTask` 会把 task.status 改为 queued，但不会处理 awaiting_approval jobs。

影响：`approval_required=true` 时，后端刚创建 `task.status='awaiting_approval'`，前端马上把 task 改成 `queued`，而子 jobs 仍为 `awaiting_approval`。列表显示排队中，executor 不会执行，审批按钮也消失。

修改建议：
- 前端只有当返回 task/job 初始状态是 `queued` 时才 auto-start。
- 或后端 `/tasks/:id/start` 拒绝 `awaiting_approval` task，返回 409 `approval_required`。
- task start 只用于 draft/paused/failed 重启，不用于审批放行。

验证：
- approval_required=true 时 createTask 后 task 仍 awaiting_approval，UI 显示批准/拒绝按钮。
- approval_required=false 时可自动 start 或直接 queued。

### FR-04 High: `/discovery/reply/:id` 手动回复仍把 awaiting_approval 的帖子标成 queued

定位：
- `admin-server/broadcast/index.js:275-283` 创建 job 时遵守 `approval_required`，但 discovered_posts 总是 `{ status: 'queued' }`。
- `admin-server/broadcast/discovery.js:322-326` 自动 discovery 已正确使用 `pending_approval`，两条路径不一致。

影响：手动回复在审批模式下会出现 `post.status=queued`、`job.status=awaiting_approval` 的不一致；Dashboard/过滤逻辑会误判该帖已排队执行。

修改建议：
- 复用一个 helper：`discoveredStatusForJobStatus(job.status)`。
- `/discovery/reply/:id` 和 `enqueueReply()` 都调用同一 helper。

验证：
- approval_required=true 调 `/discovery/reply/:id` 后，post.status 必须是 `pending_approval`。

### FR-05 High: Campaign 创建 task 后无条件标 queued，绕过审批状态展示

定位：
- `admin-server/broadcast/campaign.js:77` 子 jobs 会按 `approval_required` 设置 awaiting_approval。
- `admin-server/broadcast/campaign.js:115` task 无条件 `status: 'queued'`。

影响：campaign 在审批模式下子 jobs 等待审批，但 task 列表显示 queued。用户看不到待审批入口，executor 也不会执行 awaiting jobs。

修改建议：
- campaign task 状态应跟 jobs 初始状态一致：`awaiting_approval` 或 `queued`。
- 创建 task 时就传入正确 status，避免先 draft 后 queued。

验证：
- approval_required=true launchCampaign 后 task.status=awaiting_approval。

### FR-06 Medium: `store.createJob()` 返回对象与数据库对象 shape 不一致

定位：
- `admin-server/broadcast/store.js:172-177` 入库时 `toJson(j.payload_json)`，返回时 `...j` 又把 `payload_json` 覆盖成原始 object。

影响：直接把 `createJob()` 返回值传给 `tieredPost.buildOpenCLIArgs()` 会 `JSON.parse([object Object])` 崩溃。真实 executor 从 DB 读暂时不触发，但 API 返回、测试和后续复用都容易踩坑。

修改建议：
- `createJob()` 返回 `getJob(lastInsertRowid)`，保证与 DB shape 一致。
- 或构造返回值时使用 `payload_json: toJson(j.payload_json)`，且不要让 `...j` 覆盖。

验证：
- `typeof store.createJob({payload_json:{...}}).payload_json === 'string'`。

### FR-07 Medium: CF Gateway admin GET 仍接受 query secret

定位：
- `cf-gateway/src/index.js:294-300` feedback list 仍允许 `?secret=...`。
- `cf-gateway/src/index.js:407-413` events GET 仍允许 `?secret=...`。

影响：本地代理已改为 header，但 Worker 自身仍支持 URL secret，仍可能进入浏览器历史、日志或 Referer。

修改建议：
- 移除 query secret，仅接受 `X-Admin-Secret`。
- 对 OPTIONS 不回显敏感 header 之外的宽泛 CORS，admin GET 可限制 origin。

验证：
- `GET /api/events?secret=xxx` 必须 401；header 正确时才 200。

### FR-08 Medium: Admin server 不加载 `.env`，start-admin 默认会禁用 broadcast

定位：
- `admin-server/server.js:29-33` 直接读 `process.env.ADMIN_SECRET`。
- `start-admin.bat` 只执行 `node server.js`，没有加载 `.env`。
- `admin-server/package.json` 未引入 dotenv。

影响：如果用户把 `ADMIN_SECRET` 放在项目 `.env`，后台启动后 broadcast API 仍 503。修复“硬编码密钥”后缺少本地启动闭环。

修改建议：
- 在 `server.js` 顶部加入轻量 `.env` loader，复用 `contentGen.js` 的解析逻辑或引入 `dotenv`。
- 查找顺序：`admin-server/.env`、项目根 `.env`。
- 启动日志只提示是否配置，不打印 secret。

验证：
- 根 `.env` 设置 `ADMIN_SECRET=...`，运行 `node admin-server/server.js` 后 `/api/broadcast/status` 不再 503。

### FR-09 Medium: x/twitter 平台别名仍未 canonicalize

定位：
- `admin-server/broadcast/executor.js:50-52` lock key 使用原始 platform。
- `admin-server/broadcast/rateLimiter.js:11-13` key 使用原始 platform。
- `admin-server/broadcast/store.js:265-267` hasRunningJob 使用原始 platform。

影响：`x` 和 `twitter` 可同时绕过同一真实账号的并发锁与限频窗口。

修改建议：
- `canonicalPlatform('twitter') => 'x'` 或反过来，全模块统一。
- DB 入库、logs、rateLimiter key、platformLocks 全部使用 canonical platform。

验证：
- 一个 `x` running job 存在时，`twitter` job 应返回 account_busy。

### FR-10 Medium: discovery 失败/生成失败没有 retry workflow，且 runDiscovery 计数会误报

定位：
- `admin-server/broadcast/discovery.js:291-295` LLM 失败标记 `generation_failed`。
- `admin-server/broadcast/discovery.js:402-408` 无论 `enqueueReply()` 是否实际创建 job，都 `totalEnqueued++`。
- `admin-server/broadcast/discovery.js:397-404` 任何 existing post 都跳过，包括 `generation_failed`。

影响：一次 LLM 失败会永久阻止该 URL 重试；统计还会显示 enqueued 增加，但没有 job。

修改建议：
- `enqueueReply()` 返回 `{createdJob:boolean,status}`，runDiscovery 根据返回值增加 enqueued。
- discovered_posts 增加 `generation_retry_count`、`next_retry_at` 或放入 payload_json。
- 过滤 existing 时允许 `generation_failed` 到期后重试。

验证：
- mock LLM 失败后 enqueued 不增加。
- retry window 到期后同 URL 可再次生成。

## 建议修复 Loop / Workflow

### Loop A: 状态机闭环
1. 写失败测试：manual task、campaign、discovery 三个入口在 `approval_required=true/false` 下的 task/job/discovered_post 状态矩阵。
2. 实现 helper：
   - `initialJobStatus(cfg)`
   - `taskStatusForJobs(jobs)`
   - `discoveredStatusForJobStatus(status)`
3. 新增 task approve/reject API，并让 job approve/reject 调用同一同步函数。
4. Dashboard：task 按钮调 task API；子 job 按钮放到详情弹窗。
5. 验证：创建、批准、拒绝、暂停、恢复、执行成功/失败后状态全链路一致。

### Loop B: 身份与限频归一化
1. 写失败测试：`x/default`、`x/k2dn57uc`、`twitter/default` 应落到同一个 `(platform, account)` key。
2. 实现 `canonicalPlatform()` 和 `resolveAccount()`，入库前执行。
3. 迁移历史 queued/running/awaiting jobs 的 `default` account。
4. 将 executor lock、rateLimiter、logs、tieredPost 全部改用 canonical 值。
5. 验证：同一真实账号不可能并发发两条；failureStreak 清理命中真实账号。

### Loop C: 安全与启动闭环
1. 写 smoke test：根 `.env` 有 `ADMIN_SECRET` 时 broadcast API 可用；无时 503。
2. 移除 CF Gateway query secret。
3. 将 Dashboard secret 从 sessionStorage 改为内存变量，取消 prompt 后本会话不重复弹窗。
4. 限制 admin-server CORS 到 localhost。
5. 后续再处理非 broadcast API 全局认证。

### Loop D: Discovery 重试闭环
1. `enqueueReply()` 返回结构化结果，不再让 runDiscovery 误计数。
2. discovered_posts 增加生成失败重试计数与冷却时间。
3. Dashboard 增加 `generation_failed` 列表与“重试生成/放弃”按钮。
4. 验证 LLM 失败不会创建 job、不会永久封死 URL。

## 本次验证

- `node -c admin-server/broadcast/index.js executor.js rateLimiter.js store.js discovery.js tieredPost.js admin-server/server.js`：语法通过。
- `rg` 确认旧硬编码 `maggoogo-admin-2026` 未命中，但发现 `cf-gateway` 仍有 query secret。
- 临时 DB 验证 `x + comment + target` 从 DB 读取后会生成 `twitter reply` 参数。
- 同一临时验证发现 `createJob()` 返回对象的 `payload_json` 是 object，而 DB 中是 string，记录为 FR-06。
