# Broadcast Engine PF Closure Review - 2026-06-20

## 结论

复核最新代码后，PF-01~PF-04 已确认闭环；PF-05 的核心修复也部分闭环：job 级 approve/reject 会同步 linked `discovered_posts.status`，并调用 `refreshTaskCounts()`。

但仍发现 1 个残留问题：job 级 approve/reject 后父 task 的状态没有从 `awaiting_approval` 推导到新的真实状态；job 级 reject 也不会更新 `failed_items` 或等价的 rejected 计数。这会让旧调用方或 API 直接审批单个 job 后，Dashboard/task 列表继续显示“待审批”。

## 验证摘要

| 验证项 | 结果 |
|---|---|
| PF-01: `user_version=1` 老库补齐 FR-10 列 + self-heal | PASS |
| PF-02: `getPlatform("twitter")` 与 `getPlatform("x")` 返回同一配置 | PASS |
| PF-03: `launchCampaign({ platform: "twitter" })` 不抛异常，入库为 `x` | PASS |
| PF-04: `enqueueReply({ platform: "twitter" })` 后 `discovered_posts.platform = x` | PASS |
| PF-05: job approve 同步 discovered_post | PASS |
| PF-05: job approve/reject 推导父 task status | FAIL |
| PF-05: job reject 反映到 task counts | FAIL |

## Issue PFC-01 - Medium - job 级 approve/reject 后父 task 状态与计数仍滞后

### 证据

- `admin-server/broadcast/index.js:14-27` 的 `_transitionJobApproval(jobId, newStatus)` 只更新 job、linked discovered_post，并调用 `store.refreshTaskCounts(job.task_id)`。
- `admin-server/broadcast/store.js:497-511` 的 `refreshTaskCounts()` 只统计 `done` 与 `failed`，不会把 `queued/rejected/awaiting_approval` 映射到 task 状态，也不会把 `rejected` 计入失败/拒绝计数。
- 隔离验证结果：

```json
{
  "pf01": "PASS",
  "pf02": "PASS",
  "pf03": "PASS",
  "pf04": "PASS",
  "pf05": "PASS",
  "pf05_task_status_after_job_approve": "awaiting_approval"
}
```

job 级 reject 复核：

```json
{
  "httpStatus": 200,
  "jobStatus": "rejected",
  "postStatus": "rejected",
  "taskStatus": "awaiting_approval",
  "failedItems": 0,
  "totalItems": 1
}
```

### 风险

Dashboard 主路径当前使用 task 级 approve/reject，风险主要来自旧 UI、脚本、外部 API 或人工调用 `/jobs/:id/approve|reject`。这些路径会出现 job 已经 queued/rejected，但 task 仍显示 awaiting_approval 的状态不一致。

### 修复 workflow

1. 在 `store.js` 新增一个 task 状态推导 helper，例如 `refreshTaskState(taskId)` 或扩展 `refreshTaskCounts(taskId)`。
2. 推导规则建议：
   - 如果任一子 job 为 `awaiting_approval`，task 仍为 `awaiting_approval`。
   - 如果任一子 job 为 `running`，task 为 `running`。
   - 如果任一子 job 为 `queued` 或 `paused`，task 分别为 `queued` 或 `paused`。
   - 如果全部子 job 为 `rejected`，task 为 `rejected`。
   - 如果全部子 job 均为 terminal (`done/failed/skipped/cancelled/rejected`)，按失败/拒绝占比推导 `done/failed/rejected`，并写 `completed_at`。
3. 计数字段若不想扩 schema，可先把 `rejected` 计入 `failed_items`，或新增 `rejected_items` 并迁移；二选一要写清楚 UI 语义。
4. `_transitionJobApproval()` 在更新 job 和 discovered_post 后调用新的推导 helper，而不只是 `refreshTaskCounts()`。
5. task 级 approve/reject 也共用同一 helper，避免两套状态机再次分叉。

### 验收用例

1. job approve:

```js
POST /api/broadcast/jobs/:id/approve
expect(store.getJob(id).status).toBe("queued")
expect(store.getDiscoveredByReplyJobId(id).status).toBe("queued")
expect(store.getTask(taskId).status).toBe("queued")
```

2. job reject:

```js
POST /api/broadcast/jobs/:id/reject
expect(store.getJob(id).status).toBe("rejected")
expect(store.getDiscoveredByReplyJobId(id).status).toBe("rejected")
expect(store.getTask(taskId).status).toBe("rejected")
// 或 failed_items/rejected_items 与产品语义一致
```

3. mixed task:

```js
// 一个 job queued，一个 job awaiting_approval
expect(task.status).toBe("awaiting_approval")
// 全部 approve 后
expect(task.status).toBe("queued")
```

## 已确认闭环项

- PF-01: schema migration 已拆 v1/v2，并有 startup self-heal 补 FR-10 columns。
- PF-02: `config.normalize()` 已 canonicalize platform keys，`getPlatform("twitter")` 与 `getPlatform("x")` 一致。
- PF-03: campaign 入口 canonicalize platform，config 只有 `x` 时 `twitter` alias 可用，task/job/campaign metadata 入库为 `x`。
- PF-04: discovery enqueue 前 canonicalize platform，`discovered_posts.platform` 与 job platform 均为 `x`。
- PF-05: job approve/reject 已同步 linked discovered_post；剩余问题集中在父 task 状态/计数推导。
