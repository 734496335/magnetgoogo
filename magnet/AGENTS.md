# Project Nebula — AI Agent 行为规范

> 本文件是 AI 编码助手（Claude/Opencode/Cursor 等）的强制行为约束。
> 每次 AI 开始工作时，必须先读取本文件，然后读取 `docs/project-nebula/DEV-LOG.md` 的最新条目，了解项目当前状态。

## 0. 强制启动流程

```
1. 读本文件 (AGENTS.md)
2. 读 docs/project-nebula/DEV-LOG.md （只读最新1-2条即可）
3. 读 docs/project-nebula/CODE-STANDARDS.md
4. 开始工作
```

## 1. 文档联动（最重要）

**每次编码会话结束前，必须更新 `docs/project-nebula/DEV-LOG.md`。**

在文件顶部（第1行之前）插入新条目，严格遵循以下模板：

```markdown
---
日期/时间：YYYY-MM-DD HH:MM（本地时区）
本次版本：vX.Y.Z（递增）
本次范围：一句话描述
涉及模块：模块A / 模块B
关键改动摘要（可检索）：
  - 改动1
  - 改动2
  - ...
实测数据：
  - 数据1
  - ...
关键发现：
  - 发现1
  - ...
修改文件清单（新增/修改/删除）：
  - `+ path/to/new_file.py` (说明)
  - `~ path/to/modified_file.py` (说明)
  - ...
关键契约变更：
  - 描述 sources.json 或接口的变更
风险与未决事项：
  - 风险1
  - ...
验证方式：
  - 如何验证本次改动
复核要点/审查路径：
  - 首先检查：path/to/file.py（要点：xxx）
  - 然后检查：...
待办清单（按优先级）：
  - [ ] 待办1
  - [ ] 待办2
---
```

### DEV-LOG 版本号规则
- **PATCH (v0.2.x)**：bug 修复、小改进、健康标记更新
- **MINOR (v0.x.0)**：新功能、新源添加、extractor 增强
- **MAJOR (vx.0.0)**：架构变更、契约不兼容变更

## 2. sources.json 契约约束

修改 `sources.json` 时必须遵守 `docs/project-nebula/CODE-STANDARDS.md` 3.2-3.3 节：

- `health.status` 仅允许：`green | yellow | gray`
- `health.status_detail` 仅允许：`ok | healed | waf | 404 | expired | unreachable | parsing_failed`
- `quality.score` 范围：0-100
- **永远不要删除源**，只更新 health 标记（失效源留给域名重发现工具处理）
- 修改后必须更新 `meta.total_rules` 计数

## 3. Python 代码规范

### 3.1 目录结构
```
magnet/
├── ai_parser/        # LLM + 本地启发式解析
├── crawler/          # extractor.py, healer.py
├── discovery/        # 搜索引擎聚合发现
├── validation/       # 源验证
├── utils/            # sources_manager.py
├── verify_and_heal.py    # 批量验证+自愈
└── discover_sources.py   # 新源发现
```

### 3.2 代码风格
- 不添加注释（除非用户要求）
- 使用 `from urllib.parse import urlparse` 等标准库
- 异常处理必须具体（禁止裸 `except:`）
- `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 处理 Windows 控制台编码

### 3.3 日志输出规范（重要）
所有长时间运行的 Python 脚本（验证/发现/测试等），必须同时将输出写入 `magnet/run.log` 文件，以便在 IDE 中实时查看进度。

每个脚本开头必须包含：
```python
import logging, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('run.log', encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)
```

然后用 `log.info('...')` 代替 `print('...')` 进行所有输出。这样用户可以在 IDE 中打开 `magnet/run.log` 实时查看运行进度。

### 3.3 新增依赖
- 安装后必须记录到 `magnet/requirements.txt`
- 优先使用项目已有的库（requests, beautifulsoup4, lxml, selenium）

## 4. 网络环境认知

本项目在中国大陆网络环境下开发，以下事实影响所有决策：
- 大部分海外 BT 站被 GFW 阻断（DNS 污染 / 连接重置）
- 国内磁力站大多是导航聚合站（非搜索引擎）
- 需要浏览器渲染的站点使用 Selenium（已安装）或 undetected-chromedriver
- `ai_parser.py` 的 `get_browser_dom()` 是浏览器 fallback 的标准入口

## 5. 质量门禁

编码完成后必须执行：
1. `python magnet/validate_enum.py` — 验证 sources.json 的 status_detail 枚举合规
2. 如果修改了 extractor.py / healer.py — 运行对应的测试脚本验证
3. 更新 DEV-LOG.md

## 6. 禁止事项

- 禁止删除 sources.json 中的任何源（只标记）
- 禁止在代码中硬编码 API key / 密码
- 禁止提交 .env 文件
- 禁止创建临时文件后不清理（测试脚本在 DEV-LOG 中标记为待清理）
- 禁止修改 CODE-STANDARDS.md 中定义的枚举值（如需新增，先更新 CODE-STANDARDS）
