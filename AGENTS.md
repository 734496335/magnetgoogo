# Project Nebula — AI Agent 行为规范

> **每次开始工作前，先读本文件，再读 `docs/project-nebula/DEV-LOG.md` 最新条目，再扫一眼 `docs/project-nebula/TECH-CHALLENGES.md` 当前 open/researching 难点。**
> Python 引擎侧的详细规范见 `magnet/AGENTS.md`。
> Web 客户端的规范见 `web/AGENTS.md`。
> **所有 App/K30S/发版/源/Crawler 操作先从 `docs/project-nebula/DOC-INDEX.md` 进入当前权威 Playbook，禁止从历史 DEV-LOG 自行拼接流程。**

## 核心规则

1. **DEV-LOG 必须更新**：每次编码会话结束前，按模板格式在 `docs/project-nebula/DEV-LOG.md` 顶部插入新版本记录。模板见 `magnet/AGENTS.md` 第1节。
2. **sources.json 契约**：`health.status` 仅 `green|yellow|gray`，`health.status_detail` 仅 `ok|healed|waf|404|expired|unreachable|parsing_failed`。永远不删除源。
3. **代码规范**：见 `docs/project-nebula/CODE-STANDARDS.md`。
4. **质量门禁**：修改后运行 `python magnet/validate_enum.py` 验证枚举合规。
5. **技术难题追踪**：发现新瓶颈或调研到新方案 → 写入 `docs/project-nebula/TECH-CHALLENGES.md`；难题解决后改 status 但不删除条目。每月初做一次 GitHub/HN/arXiv 巡检（流程见该文末尾 SOP）。

## AI 行为准则（源自 Karpathy 观察）

1. **先想再写**：遇到模糊需求时，先列出假设和备选方案，不默默选一个冲。不确定就问，不要隐藏困惑。
2. **最小实现**：只写解决问题所需的最少代码。不加没被要求的功能、抽象层或"灵活性"。200 行能缩到 50 行就缩。
3. **目标驱动**：复杂任务先声明成功标准（如"搜索返回 ≥10 条结果且含 magnet 链接"），再迭代执行直到满足。

## 项目结构

```
magnet/           # Python 爬虫引擎（供给侧）
web/              # Next.js Web 客户端（消费端）
docs/project-nebula/  # 架构/规范/开发日志
sources.json      # 核心数据契约
```

## 网络环境

中国大陆环境，海外 BT 站大多被 GFW 阻断。国内磁力站多为导航聚合站。浏览器渲染通过 Selenium。

---

## 工作协议（Plan-Act-Verify）

任何**非平凡任务**（涉及 ≥2 个文件、或新建文件、或改 sources.json/契约）开工前必须先输出以下 4 段，再开始动手：

```
TASK: <一句话>
ASSUMPTIONS: <≤5 条；不确定的标 ?>
SUCCESS CRITERIA: <可机器验证的命令 + 期望输出关键行>
PLAN: <编号步骤；不超过 8 步>
```

执行完毕后追加：

```
VERIFICATION
跑了 <command>，输出关键行：<key line>
跑了 <command>，结果：✅/❌
```

失败时**不静默重试 >2 次**：超 2 次必须停下汇报，列已尝试方案与剩余备选。

## 长期记忆约定

1. **`docs/project-nebula/_progress.txt`** — 当前进行中 Phase + 阻塞点。每次会话开头先读，会话结束前更新（≤30 行）。
2. **`docs/project-nebula/_failures/`** — 任何 build/test/构建失败的 stdout 落盘到 `YYYYMMDD-HHMM-<topic>.log`。下次遇类似问题先 grep 此目录再开问。
