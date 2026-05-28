# crawler_v3 — 4-Tier 统一爬虫架构

> 设计目标：把分散在 `crawler/`、`crawler_v2/`、`cloak_yellow_verify.py`、web `route.ts` 的 5 套反检测/渲染方案统一为 4 层 Tier，每层职责单一、可独立测试、可在源之间复用。
> 备份点：tag `pre-crawler-v3` (commit `48357f9`)

## 架构总览

```
┌────────────────────────────────────────────────────────────┐
│ orchestrator.search(source, query)                         │
│   ↓                                                         │
│ detector.classify(source) → 选择 Tier                       │
│   ↓                                                         │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Tier 0  curl_cffi 纯 HTTP + TLS 指纹                │    │
│ │   适用：90% 普通源（HTML 列表 / 简单 JSON API）     │    │
│ ├─────────────────────────────────────────────────────┤    │
│ │ Tier 1  CloakBrowser 反指纹浏览器                    │    │
│ │   适用：CF JS / Turnstile / 通用 SPA / 反指纹检测   │    │
│ ├─────────────────────────────────────────────────────┤    │
│ │ Tier 2  逆向 Handler（hello_js_reverse_skill 产出） │    │
│ │   适用：共享平台自定义 captcha (thatcdn / 自研签名) │    │
│ │   形态：纯 Python 函数，输入 query → 输出请求参数   │    │
│ │   速度：等同 Tier 0（无浏览器）                     │    │
│ ├─────────────────────────────────────────────────────┤    │
│ │ Tier 3  用户协助 VerifyWebView（仅 RN 客户端）      │    │
│ │   Python 引擎不实现，仅做接口预留                    │    │
│ └─────────────────────────────────────────────────────┘    │
│   ↓                                                         │
│ parser.smart_list (共用 crawler_v2/smart_list.py)           │
│   ↓                                                         │
│ 标准 SearchResult[]                                         │
└────────────────────────────────────────────────────────────┘
```

## 跟旧版的关系

| 旧版组件 | v3 归宿 |
|---|---|
| `crawler/` v1 | 退役（保留作为对比基准） |
| `crawler_v2/healer.py` | 拆分：StealthyFetcher 被 Tier 1 替代；selector 自愈逻辑迁入 v3 detector |
| `crawler_v2/smart_list.py` | **保留**，v3 通过 `parser/` 直接复用 |
| `crawler_v2/ai/` LLM selector | 保留作为 detector 兜底，但不再是主路径 |
| `cloak_yellow_verify.py` | 能力上移为 Tier 1 常驻能力 |
| web `route.ts` execFile + verify-extension | P1 阶段用 Tier 1 替换（待 web 端迁移） |

## 目录结构

```
crawler_v3/
├── README.md             # 本文件
├── __init__.py
├── orchestrator.py       # 主入口：search(source, query) → results
├── detector.py           # 反爬指纹识别 + Tier 路由决策
├── config.py             # 默认配置、Tier 覆盖表
├── cli.py                # python -m magnet.crawler_v3 ...
├── tiers/
│   ├── base.py           # Tier ABC
│   ├── tier0_http.py     # curl_cffi
│   ├── tier1_cloak.py    # CloakBrowser
│   ├── tier2_handler.py  # 逆向 handler registry
│   └── tier3_stub.py     # 占位
├── handlers/             # 逆向产出的纯 Python token 算法
│   ├── README.md         # 添加新 handler 的工作流（js-reverse skill）
│   └── _example.py
└── parser/
    └── __init__.py       # re-export smart_list
```

## 使用

```bash
# 单源搜索
python -m magnet.crawler_v3 search "Inception" --origin clb21.top

# 批量验证 yellow 源（替代 cloak_yellow_verify.py）
python -m magnet.crawler_v3 verify-yellow "蜘蛛侠"

# 探针：识别一个新源该走哪个 Tier
python -m magnet.crawler_v3 classify https://newsite.com
```

## Roadmap

详见 `docs/project-nebula/TECH-CHALLENGES.md` CHALLENGE-002 的 Tier 路由方案，以及本目录后续 commit 历史。

| 阶段 | 任务 | 状态 |
|---|---|---|
| P0 | CloakBrowser 升级 + thatcdn 复测 | pending |
| P1 | Tier 0/1 落地 + 5 yellow 源对比 | scaffold |
| P2 | js-reverse-skill 接入，thatcdn handler | pending |
| P3 | web `route.ts` Tier 1 迁移 | pending |
| P4 | health_check 改用 v3 orchestrator | pending |
