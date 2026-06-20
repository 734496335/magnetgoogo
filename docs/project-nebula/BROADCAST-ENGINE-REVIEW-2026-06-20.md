# Broadcast Engine Review 2026-06-20

范围：`docs/project-nebula/_progress.txt`、`docs/project-nebula/DEV-LOG.md`、`docs/project-nebula/BROADCAST-HANDOFF.md`、`admin-server/broadcast/*`、`admin-server/server.js`、`admin_templates/dashboard.html`、`broadcast-config.json`。

结论：传播引擎主链路已经搭起来，但当前存在几处会导致真实发帖目标错位、任务永远卡住、限频状态污染、鉴权密钥泄露和测试误判的问题。下面按优先级列出，供后续 AI 逐项修改。

## P0 必须先修

### 1. X/Twitter 目标回复会被当成新帖发布

定位：
- `admin-server/broadcast/discovery.js:301-308` 创建发现回复 job 时写入 `{ kind: 'comment', target, body }`。
- `admin-server/broadcast/index.js:300-303` 手工任务也默认写入 `kind: item.kind || 'comment'`。
- `admin-server/broadcast/tieredPost.js:223-230` 对 `x/twitter` 只有 `kind === 'reply' && target` 才走 `twitter reply`，否则走 `twitter post`。

影响：发现流和 Dashboard 手工任务明明带了目标 URL，却会执行 `twitter post <body>`，不是回复原帖。这会造成投放行为偏离设计，也更容易触发平台风控。

修改建议：
- 增加统一 payload 归一化函数，例如 `normalizeJobPayload(platform, payload)`。
- 对 `x/twitter`：`kind === 'comment'` 且存在 `target` 时归一化为 `reply`；没有 target 才允许 `post`。
- 对 `zhihu`：`comment`/`answer` 必须有 target。
- 对 `reddit`：明确 OpenCLI 需要 post/comment id 还是 URL，若需要 id，则在入队前解析或拒绝 URL。
- `buildOpenCLIArgs()` 对空 body、缺 target 的 comment/reply 一律返回非重试错误，不能进入 OpenCLI。

建议验证：
- 单测覆盖 `x + {kind:'comment', target:'https://x.com/...'}` 生成 `['twitter','reply',target,body]`。
- 单测覆盖 `x + {kind:'post', target:null}` 才生成 `twitter post`。

### 2. 任务暂停后无法恢复

定位：
- `admin-server/broadcast/index.js:354-364` 暂停任务时把 queued jobs 改成 `paused`。
- `admin-server/broadcast/index.js:337-347` 开始任务只把 `draft` 或 `failed` 改回 `queued`，没有处理 `paused`。
- `admin-server/broadcast/executor.js:353-355` executor 只扫描 `status='queued'`。

影响：用户点击暂停后，再点击开始，task 状态变成 queued，但子 jobs 仍是 paused，executor 永远不会执行。

修改建议：
- `POST /tasks/:id/start` 应把 `paused` jobs 也改回 `queued`。
- 更稳的方案：暂停只改 task.status，子 jobs 保持 queued，由 `prepareJob()` 的 task paused 检查跳过；恢复时只改 task.status。
- 如果保留 job.status='paused'，则 `refreshTaskCounts()` 和 Dashboard 状态展示也要把 paused 纳入未完成态。

建议验证：
- 创建任务 -> pause -> start -> 断言所有 paused jobs 回到 queued。
- 调用 `executor.pollAndExecute()` 后至少一个 runnable job 被执行或被限频 defer。

### 3. Dashboard 声称“随机模板/AI 智能回复”，但后端实际创建空正文 job

定位：
- `admin_templates/dashboard.html:2499-2519` 只把 URL 转为 `items = [{ target_url }]`，没有传 `template_id`，也没有 body。
- `admin-server/broadcast/index.js:286-308` `/tasks` 接口忽略 `reply_style`，只写入 `{ kind, target, body: item.body || '' }`。
- `admin-server/broadcast/executor.js:287-290` 只有 job.template_id 存在时才读取模板；手工任务没有写 template_id。
- `docs/project-nebula/DEV-LOG.md:64` 记录“POST /tasks API 自动注入模板正文”，但当前代码未实现。

影响：手工创建的任务大概率会进入 OpenCLI 时携带空 body。轻则发帖失败并反复重试，重则平台执行异常。UI 的“随机模板 / AI 智能回复”只是保存到 task.payload_json，executor 完全不用。

修改建议：
- `/tasks` 请求 schema 增加 `template_id` 或明确使用 task.payload_json.reply_style。
- `random_template`：入队时从 `approved` 模板池随机取一条，把 `template_id` 和 body 写入 job payload。
- `ai_smart`：如果只是 URL，当前没有抓取帖子上下文能力，应先拒绝并提示“不支持纯 URL AI 智能回复”；或者实现 target 页面内容获取后调用 `generateReply()`。
- `tieredPost.validateArg()` 必须拒绝空 body，例如 `body.trim().length < 2` 返回错误。
- DEV-LOG 中已记录的“模板注入”需要和实现对齐。

建议验证：
- 通过 `/api/broadcast/tasks` 创建 `random_template` 任务后，查询子 jobs，确认 `payload_json.body` 非空。
- 没有可用模板时接口返回 400，不创建空 job。

### 4. 发现回复在“入队”时就标记 replied，失败后永久去重

定位：
- `admin-server/broadcast/discovery.js:317-321` 入队成功后把 discovered_posts.status 改为 `queued`。
- `admin-server/broadcast/index.js:252-266` 手动 `/discovery/reply/:id` 创建 job 后立即 `status: 'replied'`。
- `admin-server/broadcast/discovery.js:167-172` 和 `255-260` 会跳过 status='replied' 的 URL。
- `admin-server/broadcast/index.js:260-266` 中 `store.createJob()` 返回的是 job 对象，但变量名 `jobId` 被当成 id 使用，`reply_job_id` 可能写成对象字符串。

影响：手动回复接口会把尚未执行的 job 当成已回复；如果后续 OpenCLI 失败，该 URL 也不会再进入回复队列。`reply_job_id` 还可能写入 `[object Object]`。

修改建议：
- `/discovery/reply/:id` 改为 `const job = store.createJob(...)`，返回和写入 `job.id`。
- 入队后状态统一为 `queued` 或 `reply_queued`，只有 executor 成功后才改为 `replied` 并写 `replied_at`。
- executor 完成 job 时，如果 job payload.target 对应 discovered_posts.post_url，则同步更新 discovered_posts 状态：成功 `replied`，失败 `failed`。
- `filterResults()` 只跳过 `replied` 和正在执行的 `queued/running`，不要跳过 failed。

建议验证：
- 手动 reply 后 discovered post 为 queued，job 成功后才变 replied。
- job 失败后同 URL 可重新审批/重试。

## P1 高优先级

### 5. Rate limiter 的 defer 逻辑会过度延迟，且旧失败状态会污染新任务

定位：
- `docs/project-nebula/_progress.txt:15` 已记录“rate limiter min_gap 问题（旧任务状态阻塞新任务）”。
- `admin-server/broadcast/rateLimiter.js:116-127` failureStreak 会把 min_gap 放大到最多 8 倍。
- `admin-server/broadcast/executor.js:81-85` 遇到 `min_gap_not_elapsed` 时直接从当前时刻再延迟一个完整 `min_gap`，没有计算剩余时间。
- `admin-server/broadcast/executor.js:95-105` 有 `daily_cap_reached` 延迟计算，但 `prepareJob()` 的 deferReasons 没包含 daily cap，实际会 skip。

影响：如果刚好还差 1 分钟满足间隔，代码会再推迟 20/30/60 分钟。旧失败 streak 又会放大间隔，新任务看起来一直 queued。daily cap 到达时 job 被 skipped，而不是次日自动继续。

修改建议：
- `canAct()` 返回结构增加 `retry_at` 或 `remaining_ms`，由 rateLimiter 统一计算。
- `min_gap_not_elapsed` 应使用 `lastActionTs + effectiveGap - now + jitter`，不是完整 min_gap。
- failureStreak 增加 TTL，例如超过 1-2 小时自动清理；成功、人工 start task、或平台配置变更时可清理相关 streak。
- `daily_cap_reached` 加入 deferReasons，排到次日窗口后执行，而不是 skipped。
- Dashboard 增加“清理限频状态/失败 streak”的受控按钮，并写 log。

建议验证：
- 模拟 lastActionTs 为 19 分钟前、min_gap=20，defer 应约 1 分钟而不是 20 分钟。
- daily cap reached 后 job.status 保持 queued，scheduled_at 为次日。

### 6. 鉴权密钥硬编码在后端和前端源码

定位：
- `admin-server/server.js:29` 写死 `ADMIN_SECRET = 'maggoogo-admin-2026'`。
- `admin_templates/dashboard.html:1644` 前端写死同一个 `x-admin-secret`。
- `admin-server/server.js:108-114` 允许 query secret。

影响：源码中存在可直接调用传播 API 的固定密钥，且 Dashboard HTML 会把密钥暴露给任何能访问本地管理面板的人。AI-RULES 的凭证规则要求密钥从 `.env`/环境变量读取，不能硬编码。

修改建议：
- 后端改为 `process.env.ADMIN_SECRET`，本地 `.env` 加载由统一 env loader 完成；未配置时禁止启动 broadcast 路由或生成随机一次性 secret。
- 前端不要硬编码 secret。可选方案：本地启动时设置 HTTP-only cookie/session，或 dashboard 首次访问输入 secret 后只保存在 sessionStorage。
- 移除 `req.query.secret`，避免日志/浏览器历史泄露。
- `.gitignore` 已忽略 `.env`，不要把真实 secret 写入仓库。

建议验证：
- `rg -n "maggoogo-admin-2026|ADMIN_SECRET =" admin-server admin_templates` 无命中。
- 未设置 ADMIN_SECRET 时 `/api/broadcast/status` 返回 503 或 broadcast disabled。

### 7. SessionStore 明文保存 cookies/tokens，且 sessions 目录未忽略

定位：
- `admin-server/broadcast/sessionStore.js:101-106` 直接 `JSON.stringify(data)` 写入 session 文件。
- `.gitignore` 仅忽略 `admin-server/broadcast.db*`，没有忽略 `admin-server/sessions/`。

影响：如果后续 Tier2/Tier3 使用 SessionStore，平台 cookie/token 会以明文落盘并可能被误提交。

修改建议：
- 在 `.gitignore` 增加 `admin-server/sessions/`。
- SessionStore 写入前使用本地密钥加密，密钥来自 `.env`，至少使用 AES-256-GCM 并带 auth tag。
- 如果暂不实现加密，先禁止保存 tokens，仅保存非敏感 metadata，并在代码注释里明确“未启用持久 session”。

建议验证：
- `git check-ignore admin-server/sessions/x_default.json` 返回被忽略。
- session 文件内容不出现 cookie 名或 token 明文。

### 8. discovery API 会绕过审批模式

定位：
- `admin-server/broadcast/index.js:260-264` `/discovery/reply/:id` 创建 job 时没有根据 `cfg.global.approval_required` 设置 status。
- `admin-server/broadcast/discovery.js:301-310` 自动 discovery 入队也未读取 approval_required，默认 `createJob()` 状态是 queued。
- `admin-server/broadcast/campaign.js:77` campaign 已正确处理 approval_required，可作为参考。

影响：全局审批模式打开时，campaign 会等待审批，但 discovery 仍会直接 queued，绕过人工确认。

修改建议：
- 新增 helper `initialJobStatus(cfg)`，所有 createJob 入口共用。
- discovery 自动入队和手动 `/discovery/reply/:id` 都应遵守 `approval_required`。
- Dashboard posts 审批按钮只应把 discovered_post 标记 approved，不应直接创建 queued job，除非全局允许。

建议验证：
- `approval_required=true` 时 discovery 创建的 job.status 为 `awaiting_approval`。

## P2 中优先级

### 9. store.js 有重复 hasRunningJob 定义，且 account 语义不稳定

定位：
- `admin-server/broadcast/store.js:259-267` `hasRunningJob()` 定义了两次，后一版覆盖前一版。
- `admin-server/broadcast/rateLimiter.js:87-91` 使用平台默认 account。
- `admin-server/broadcast/executor.js:276` job.account 为空时使用平台默认 account，但 jobs 表里的 account 可能是 null/default/真实 profile 混用。

影响：重复定义增加维护风险。account 混用会让 running 检查和限频日志不一致，尤其是 job.account=null 但实际 OpenCLI profile 使用 `k2dn57uc` 时。

修改建议：
- 删除重复函数，只保留一个。
- 创建 job 时就把 account 归一化为真实 profile，不要存 null。
- `createJob()` 或 route 层调用 `resolveAccount(platform, account, cfg)`。
- 对历史 null account 可做一次迁移或在查询中兼容。

建议验证：
- 同平台同 profile 并发两个 job，第二个必须被 defer。
- logs.account、jobs.account、OpenCLI `--profile` 三者一致。

### 10. 测试脚本会污染真实配置/数据库，且断言已过期

定位：
- `admin-server/broadcast/test_m2_m3.js:56-72` 直接备份/改写仓库根 `broadcast-config.json` 和真实 `admin-server/broadcast.db`。
- `broadcast-config.json` 当前已经残留 `testplatform` 和多条测试 campaign。
- `admin-server/broadcast/test_m2_m3.js:157-165` Windows 断言仍期望 `cmd.exe /c opencli`，但 `tieredPost.js:23-27` 当前实现是 `process.execPath + main.js`。
- `admin-server/broadcast/test_m2_m3.js:183-192` 仍期望 min_gap job 被 skipped，但 executor 现已改为 deferred。

影响：测试结果不可信，且会污染生产配置。后续 AI 如果运行该测试，可能误以为实现坏了，或者把测试残留提交。

修改建议：
- 支持 `BROADCAST_CONFIG_PATH` 和 `BROADCAST_DB_PATH` 环境变量，让测试使用临时目录。
- 测试结束删除临时 DB/config，不改真实文件。
- 更新断言：Windows 期望 `process.execPath`，args 前缀包含 opencli main.js；min_gap 期望 `status='queued'` 且 `scheduled_at` 被推迟、log.status='deferred'。
- 清理 `broadcast-config.json` 中的 testplatform 和测试 campaigns。

建议验证：
- `node admin-server/broadcast/test_m2_m3.js` 前后 `git diff -- broadcast-config.json admin-server/broadcast.db` 无变化。

### 11. LLM 调用没有超时控制，Campaign/Discovery 可能长时间挂起

定位：
- `admin-server/broadcast/contentGen.js:170-180` 和 `307-317` 调用 `fetch()` 未传 AbortSignal。
- `admin-server/broadcast/campaign.js:92-98` 顺序等待每次 LLM；500 个 job 最坏会阻塞很久。
- `admin-server/broadcast/discovery.js:281-289` LLM 失败后落入兜底文案。

影响：外部 LLM 网络卡住时，HTTP 请求和任务创建会长期不返回。Campaign 批量生成也可能占用 Node 进程事件链很久。

修改建议：
- 为 LLM fetch 增加 `AbortController`，默认 30-60s 超时，超时按 retryable 错误处理。
- Campaign 改成先创建 `awaiting_generation`/`queued` jobs，再由后台 worker 生成内容，避免路由请求等待全部 LLM。
- 或限制单次 campaign count 更低，并返回异步 task id。

建议验证：
- mock fetch 永不 resolve，generateReply 在配置超时内抛出明确错误。

### 12. 兜底回复违反“非营销口吻”要求

定位：
- `admin-server/broadcast/contentGen.js:271-279` 明确禁止 “check out / worth trying / I recommend / you might find useful” 等营销表达。
- `admin-server/broadcast/discovery.js:292-295` LLM 失败时兜底为 `You might find MagGoogo useful...`。

影响：一旦 LLM key 缺失或调用失败，就会生成项目自己禁止的广告式英文回复，并且没有根据原帖语言适配。

修改建议：
- LLM 失败时不要自动发产品文案。更安全做法：把 discovered_post 标记 `generation_failed`，不创建 job。
- 如果必须兜底，使用平台/语言无产品提及的普通回复，并把 job 标记 `awaiting_approval`。
- 兜底文案要复用 contentGen 的禁用词检测。

建议验证：
- unset LLM key 后 runDiscoveryCycle 不创建 queued 发帖 job，而是留下可人工处理的 failed/generation_failed 记录。

## 建议修复顺序

1. 先修 P0-1、P0-2、P0-3，确保“发到哪里、能不能恢复、是否有正文”正确。
2. 再修 P1-5、P1-8，解决当前进度文件记录的 rate limiter 阻塞与审批绕过。
3. 同步修 P1-6、P1-7，避免凭证/会话安全债继续扩大。
4. 最后修测试隔离与超时，确保后续 AI 能安全验证。

## 建议新增测试清单

- `buildOpenCLIArgs()`：x comment+target -> twitter reply。
- `/tasks`：random_template 创建非空 body job；无模板时 400。
- task pause/start：paused jobs 可恢复为 queued。
- rate limiter：min_gap 只 defer 剩余时间；daily cap defer 到次日。
- discovery reply：入队为 queued，成功后才 replied，失败可重试。
- approval_required：jobs/campaign/discovery 三个入口状态一致。
- auth：源码无硬编码 secret，未配置 env 时 broadcast API 不可用。
- test isolation：测试使用临时 DB/config，运行前后工作区无配置 diff。
