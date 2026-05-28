---
name: dev-log-protocol
description: 任何编码会话结束前、任何 commit 前必须加载本 skill 并按模板写 DEV-LOG。
---

# DEV-LOG 写入协议

文件位置：`docs/project-nebula/DEV-LOG.md`
写入位置：**文件最顶部**（紧贴 frontmatter 后），新条目压在最新条目上方，永不在文件中部插入。

## 模板

```
日期/时间：YYYY-MM-DD HH:MM（UTC+8）
本次版本：<git tag 风格短语，如 crawler-v3-phase2-complete>
本次范围：**<一句话总结>**
涉及模块：<逗号分隔的相对路径>

### 关键改动
1. **<改动名>**（<文件路径>，<行数>）
   - <要点 1>
   - <要点 2>

### 验证结果
| # | 验收项 | 结果 |
|---|---|---|
| x.1 | <命令或检查项> | ✅/❌ <说明> |

### 关键发现 / 教训
- <一句话>
```

## 硬规则
- 不写 DEV-LOG 不许结束会话。
- 涉及 sources.json 改动必须在 DEV-LOG 中记录 green/yellow/gray 计数 delta。
- 发现新瓶颈 → 同步追加到 `docs/project-nebula/TECH-CHALLENGES.md`，DEV-LOG 中加链接。
- 字段「本次版本」与 git tag 必须一致（如打了 tag）。
