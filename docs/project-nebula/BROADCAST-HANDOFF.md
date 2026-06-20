# Broadcast Engine 交接文档（供 Gemini 接手）

> **阅读本文件即可接手传播引擎的后续开发工作。**
> 无需阅读其他文档——必要上下文已内嵌于此。

---

## 1. 项目背景（60 秒速览）

**MagGoogo（磁力古哥）**是磁力链聚合搜索应用（React Native App + Next.js Web + Python 爬虫引擎）。  
当前任务：实现「核弹级传播引擎」——一套受控的社媒自动发帖/评论系统，
挂载在本地 admin 后台（`admin-server/server.js`，Express on port 3800），
通过 Dashboard UI 操控，真实发帖走 **OpenCLI**（复用已登录 Chrome 会话，不需要 API 密钥，零运行时 LLM 成本）。

目标平台：**知乎、X、小红书、B站、Reddit**（OpenCLI 有内置适配器）。

---

## 2. 已完成模块（勿重复开发）

### M1 — 地基（`admin-server/broadcast/` 模块）

全部文件已落盘并通过测试（11 项单元测试 + HTTP 冒烟），可直接使用。

| 文件 | 职责 |
|------|------|
| `broadcast-config.json`（仓库根） | 控制契约（全局开关/kill_switch/各平台限频） |
| `admin-server/broadcast/config.js` | load/save/normalize，缺字段自动补默认值 |
| `admin-server/broadcast/store.js` | SQLite WAL，三表：templates / jobs / logs；含限频辅助函数 |
| `admin-server/broadcast/rateLimiter.js` | `canAct(platform,account)` 硬约束，5 级拒绝理由 |
| `admin-server/broadcast/index.js` | Express Router，10 个路由（status/kill/config/templates/jobs/check） |

挂载方式（已写入 server.js）：
```js
app.use('/api/broadcast', require('./broadcast'));
```

`better-sqlite3@^11.7.0` 已写入 `admin-server/package.json` 并已 `npm install`。

### M4 — 仪表盘 UI（`admin_templates/dashboard.html`）

已添加「传播投放」标签页（Alpine.js），包含：
- 全局控制（kill switch 按钮 + 队列 pills）
- 平台配置（表格内联编辑 + 保存 + 限频检查）
- 内容模板（创建 / 审批 / 下架）
- 投放任务（按状态过滤，M2 执行后填充）

---

## 3. 待开发模块

### M2 — OpenCLI 执行引擎（最高优先级，但有前置依赖）

**前置（需用户就绪才能联调）：**
- 用户机器安装 OpenCLI（`npm install -g opencli` 或参考 https://github.com/opencli/opencli）
- 各平台浏览器已登录账号（OpenCLI 复用 Chrome user profile）

**M2 要实现的内容：**

新建 `admin-server/broadcast/executor.js`，职责：
1. **job 轮询调度器**：`setInterval`（间隔可配，默认 60s），查 `status='queued'` 且 `scheduled_at <= now` 的 jobs（若 `global.approval_required=true` 则只处理 `status='approved'` 的）。
2. **执行前再校验**：调 `rateLimiter.canAct(platform, account)`，不通过则 skip（写 logs reason）。
3. **OpenCLI 调用**：用 Node.js `child_process.spawnSync` 或 `execSync` 调用 `opencli post --platform <name> --content "<body>" --title "<title>"`（具体 CLI 参数以 OpenCLI 文档为准）。
4. **结果写回**：成功 → job.status='done'，addLog({status:'done',...})；失败 → job.status='failed'，addLog({status:'failed', detail:stderr})。
5. **急停**：每轮开始前检查 `kill_switch`，true 则整轮 skip。

Router 新增路由：
- `POST /jobs` → 创建 job（body: `{platform, account?, template_id, payload_json?, scheduled_at?}`），若 `approval_required` 则状态设 `awaiting_approval`，否则 `queued`。
- `POST /jobs/:id/approve` → status 改 `queued`（审批通过才入队）。
- `GET  /logs` → 可选 `?job_id=&platform=` 过滤。

### M3 — LLM 内容改写 + Campaign 调度器（不依赖 OpenCLI）

新建 `admin-server/broadcast/contentGen.js`：
- 复用已有 LLM key（环境变量 `OPENAI_API_KEY` 或 `ARK_API_KEY`/Volces），走 openai-compatible `/v1/chat/completions`。
- `generateVariant(templateBody, platform, keyword) -> string`：将模板正文改写为平台风格（知乎学术/小红书活泼/X 简短），植入关键词（如「磁力古哥」「免费磁力搜索」）。
- 生成的内容作为 `payload_json.body` 存入 job。

新建 `admin-server/broadcast/campaign.js`：
- `launchCampaign(cfg)` 接受 campaign 配置（platform, templateId, count, keywordList, startAt），批量生成 jobs 并写入 store。
- 对应 Router 路由：`POST /campaigns`（触发 launchCampaign）、`GET /campaigns`（读 bcConfig.campaigns）。
- Dashboard 的「传播投放 → 投放任务」卡片自动展示这些 jobs。

---

## 4. mimo-v2.5-pro 调度方式

### API 信息
```
Key:   tp-c7zzz9eaf2a47yrz66fa6ye1v5yajcakd979sc7leok8xz3a  (从 env MIMO_KEY 读)
URL:   https://token-plan-cn.xiaomimimo.com/anthropic       (从 env MIMO_URL 读)
Model: mimo-v2.5-pro
```

### 调度器脚本
`tmp_mimo/dispatch.py`（已存在，流式 SSE，自动重试 3 次）：
```
python tmp_mimo/dispatch.py <prompt_file> <out_file> [max_tokens] [system_file]

# 典型用法（在仓库根运行）：
set MIMO_KEY=tp-c7zzz9eaf2a47yrz66fa6ye1v5yajcakd979sc7leok8xz3a
set MIMO_URL=https://token-plan-cn.xiaomimimo.com/anthropic
python tmp_mimo/dispatch.py tmp_mimo/m2_prompt.txt tmp_mimo/m2_out.md 20000 tmp_mimo/system.txt
```
注：`tmp_mimo/` 目录已 gitignore，安全存放 prompt/output。

### 系统提示（system.txt）
`tmp_mimo/system.txt` 已写好（含 HARD RULES + 环境事实 + 输出格式）。  
**关键输出格式**（你必须告知 mimo，它已被 system.txt 设定，不要变更）：
```
### FILE: <path-relative-to-repo-root>
```<lang>
<full file content>
```
### NOTES  ← 仅此处写说明，≤10 行
```

### 解析 mimo 输出的规则
1. 按 `### FILE: <path>` 切分，每段的 ` ```lang ... ``` ` 内是完整文件内容。
2. **Review 前不落盘**：检查逻辑正确性、错误处理、无硬编码密钥、无不必要依赖。
3. 落盘后运行测试再提交。
4. mimo 不知道 server.js 现有内容——需要改 server.js 时，先 grep 查找插入点，由你（Gemini）自己做 StrReplace，不要让 mimo 输出整个 server.js。

---

## 5. 关键文件地图

```
d:\lpproduct\magnet\
├── broadcast-config.json          ← 控制契约（全局+平台限频）
├── sources.json                   ← 磁力源数据（勿改）
├── admin-server/
│   ├── server.js                  ← Express 主文件（port 3800）
│   ├── package.json               ← 含 express/cors/better-sqlite3
│   ├── broadcast/
│   │   ├── index.js               ← Router（已完成）
│   │   ├── config.js              ← config load/save（已完成）
│   │   ├── store.js               ← SQLite CRUD（已完成）
│   │   ├── rateLimiter.js         ← canAct()（已完成）
│   │   ├── executor.js            ← ← ← M2 需新建
│   │   └── contentGen.js          ← ← ← M3 需新建
│   └── broadcast.db               ← 运行时生成（已 gitignore）
├── admin_templates/
│   └── dashboard.html             ← 单文件 Alpine.js + Tailwind 仪表盘（已含传播投放标签）
├── tmp_mimo/
│   ├── dispatch.py                ← mimo API 调度器（流式）
│   ├── system.txt                 ← mimo 系统提示
│   ├── m1_prompt.txt / m1_out.md  ← M1 的 prompt 和 mimo 输出（参考）
│   └── m4_prompt.txt / m4_out.md  ← M4 的 prompt 和 mimo 输出（参考）
└── docs/project-nebula/
    ├── DEV-LOG.md                 ← 开发日志（每次会话结束后插入新条目）
    ├── _progress.txt              ← 当前进度（≤30行，每次会话更新）
    └── BROADCAST-HANDOFF.md       ← 本文件
```

---

## 6. 工作规范（AGENTS.md 摘要）

1. **每次会话结束前**：在 `DEV-LOG.md` 顶部插入新条目（日期/版本/范围/成果/验证）。
2. **每次会话结束前**：更新 `_progress.txt`（≤30行，3 条摘要）。
3. **代码规范**：CommonJS only；无叙述性注释；错误处理要具体（不要裸 catch）；无硬编码密钥。
4. **质量门禁**：有新逻辑时先写测试脚本验证，再汇报。
5. **mimo 额度几乎无限**：充分利用，可多轮迭代；每次 max_tokens 可设 20000。

---

## 7. 快速上手 checklist

接手后建议依次执行：

```bash
# 1. 确认后端路由工作
cd admin-server && npm install
node server.js  # 应看到 http://localhost:3800

# 2. 验证 broadcast API
curl http://localhost:3800/api/broadcast/status

# 3. 确认 mimo 调度器（在仓库根）
set MIMO_KEY=<key>
set MIMO_URL=https://token-plan-cn.xiaomimimo.com/anthropic
python tmp_mimo/dispatch.py tmp_mimo/test_prompt.txt tmp_mimo/test_out.md 500 tmp_mimo/system.txt

# 4. 开始 M2（若用户 OpenCLI 已就绪）或 M3（不依赖 OpenCLI）
```

---

*本文档由 Claude Sonnet 4.6 生成于 2026-06-03，交接给 Gemini 继续工作。*
