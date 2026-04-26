# Project Nebula — AI Agent 行为规范

> **每次开始工作前，先读本文件，再读 `docs/project-nebula/DEV-LOG.md` 最新条目。**
> Python 引擎侧的详细规范见 `magnet/AGENTS.md`。
> Web 客户端的规范见 `web/AGENTS.md`。

## 核心规则

1. **DEV-LOG 必须更新**：每次编码会话结束前，按模板格式在 `docs/project-nebula/DEV-LOG.md` 顶部插入新版本记录。模板见 `magnet/AGENTS.md` 第1节。
2. **sources.json 契约**：`health.status` 仅 `green|yellow|gray`，`health.status_detail` 仅 `ok|healed|waf|404|expired|unreachable|parsing_failed`。永远不删除源。
3. **代码规范**：见 `docs/project-nebula/CODE-STANDARDS.md`。
4. **质量门禁**：修改后运行 `python magnet/validate_enum.py` 验证枚举合规。

## 项目结构

```
magnet/           # Python 爬虫引擎（供给侧）
web/              # Next.js Web 客户端（消费端）
docs/project-nebula/  # 架构/规范/开发日志
sources.json      # 核心数据契约
```

## 网络环境

中国大陆环境，海外 BT 站大多被 GFW 阻断。国内磁力站多为导航聚合站。浏览器渲染通过 Selenium。
