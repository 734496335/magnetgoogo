# Crawler 架构评判与重构方案

> 起草于 2026-05-22 v0.3.4 之后，以纠正「次抛脚本越积越多」的开发模式。
> 本文是架构师视角，不是教程。先看「问题」节，再看「目标架构」，最后看「整合路径」。

## 1. 现状（事实陈述）

### 1.1 已有模块

```
magnet/
├── crawler/           # v1: requests + Selenium 网络层
│   ├── extractor.py   # 列表页 selectors → magnet 抽取
│   └── healer.py      # 失败诊断 + selector 修复链
├── crawler_v2/        # v2: 仅替换网络层
│   ├── extractor.py   # MagnetExtractorV2(MagnetExtractor) — Scrapling Fetcher
│   ├── healer.py      # HealerV2(Healer) — Scrapling + StealthyFetcher
│   └── smart_list.py  # DOM path-shape 聚类（自研列表行检测）
├── ai_parser/
│   └── ai_parser.py   # LocalHeuristic + Volces/OpenAI/DeepSeek/Gemini 链
├── discovery/
│   ├── search_engine.py  # 搜索引擎 dorking（Bing/Google）— 750 行老代码
│   └── link_sniffer.py   # 友情链接递归
├── verify_and_heal.py    # 批量主入口（用 v1 healer，**未升级到 v2**）
└── health_check.py       # 单独的 requests-only 健康巡检（**与 verify_and_heal 重复**）
```

### 1.2 实际能力（HealerV2 的兜底链）

```
search url
  ↓
[Step 1] Scrapling Fetcher (Chrome TLS 指纹)
  ↓ 失败
[Step 2] requests fallback
  ↓ 失败 / WAF / 长页面无 magnet
[Step 3] StealthyFetcher (Playwright + anti-fingerprint)
  ↓ 仍无 magnet
[Step 4] LocalHeuristicParser → 自动生成 selectors
  ↓ heuristic 失败
[Step 5] StealthyFetcher 二跑 + heuristic 二解析
  ↓ 仍失败
return parsing_failed
```

### 1.3 v0.3.x 我新加的 6 个「次抛工具」

| 文件 | 实际是什么能力 | 应该归属哪里 |
|------|---------------|-------------|
| `magnet/_ai_bootstrap_common.py` | LLM provider chain + Stealthy fetch + selectors 验证 | → `crawler_v2/ai/` 模块库 |
| `magnet/_ai_bootstrap_crawl4ai.py` | LLM-driven selector 生成（Crawl4AI） | → `crawler_v2/ai/selector_synth.py` |
| `magnet/_ai_bootstrap_scrapegraph.py` | LLM-driven selector 生成（ScrapeGraphAI） | 实测兼容差，**淘汰** |
| `magnet/_ai_bootstrap_batch.py` | suspect_dead 源批量复核 | → `magnet/scripts/ai_reverify.py`（运维脚本） |
| `magnet/_brand_domain_finder.py` | 搜索引擎查品牌新主域名 | → `discovery/brand_rediscovery.py` |
| `magnet/_brand_search_probe.py` | 探测新站 search URL pattern | → `discovery/search_form_probe.py` |

---

## 2. 架构问题（4 个）

### 问题 A：能力散布，没有「策略表」

`HealerV2.heal_and_retry` 对所有源用同一条链。但实际站点分四类：

| 类别 | 特征 | 应该走的路径 |
|------|------|-------------|
| **列表页型** | TPB/knaben/nyaa：搜索结果页直接含 magnet | Fetcher / Stealthy → selectors |
| **详情页型** | yts/cilitiantang/cilishenqi：列表页只有 detail 链接，magnet 在 `/movie/<slug>` | 多需要二跳 follow |
| **SPA / API 型** | bt1207、磁力柠檬：JS 渲染，请求 XHR 后再渲染 | StealthyFetcher 强制等 network_idle |
| **导航站 / 镜像聚合** | btmayi/cilihezi/btlm.cc：本身不是搜索源，是发现源 | 不进 healer，进 discovery |

**当前 healer 把这 4 类混在一起跑**——所以 yts.rs 标 yellow，cilitiantang 也 yellow，但实际是两种不同问题。

**修复方向**：sources.json 加 `capabilities.parse_strategy` 字段（`list_page` / `detail_follow` / `spa_xhr` / `nav_aggregator`），healer 按声明分发。

### 问题 B：discovery 与 crawler 之间没有反馈循环

- v1 `crawler/healer.py` 有 `discover_new_domain(site_name)` **stub** — 只打日志不真做。
- v0.3.4 我做的 `_brand_domain_finder.py` 实现了真正的搜索引擎查询，但**孤立**：跑 → 输出 JSON → 等人工 review → 写 sources.json。
- health_check 发现 `clb*` 家族集体 404，**不会自动触发** brand rediscovery。

**修复方向**：
1. `discovery/brand_rediscovery.py` 暴露函数 `find_replacement_domains(brand_id) → [candidate]`
2. health_check 在多个源同 brand_family 同时塌方时，**自动调用** brand rediscovery
3. 输出候选写入 `sources.json` 的 `_pending_rediscovery` 字段（由人工或定时任务确认后才入正式 rules）

### 问题 C：sources.json 缺「能力声明」字段

每条 rule 当前只有 selectors + status。缺：

```jsonc
{
  "site": {...},
  "capabilities": {
    "supports_search": true,           // 已有
    "supports_detail": true,           // 已有
    "parse_strategy": "list_page",     // 新增：list_page | detail_follow | spa_xhr | nav_aggregator
    "fetch_strategy": ["fetcher", "stealthy"],  // 新增：哪些 fetcher 能用，按优先级
    "brand_family": "clb"              // 新增：用于域名重发现联动
  },
  "search": {...},
  "health": {...}
}
```

**新字段全部可选**——旧规则不写 `capabilities.parse_strategy` 就走默认（list_page）。这样不破坏契约。

### 问题 D：LLM-driven selector 生成 + 实时搜索路径混淆

我做 AI bootstrap 时一度想把它接进 healer 链。**这是错的**——LLM 推理 30s + ¥0.02/调用，**不能放在每次搜索的关键路径上**。

**正确做法**：分两条路径
- **实时路径** (HealerV2)：保持纯算法（Fetcher → Stealthy → LocalHeuristic）。响应时间 < 5s。
- **离线增强路径** (新增 `crawler_v2/ai/`)：批处理时跑，把 AI 生成的 selectors 写入 sources.json 的**草稿字段** `_ai_proposal.selectors`。等人工或自动脚本验证后才升级到正式 `parse_metadata.selectors`。

这样**生产搜索永远不调 LLM**，AI 只是离线运维工具。

---

## 3. 目标架构（最小化重构）

```
                  ┌──────────────────────────────────┐
                  │  Real-time search path (in app)  │
                  │  HealerV2 (Fetcher → Stealthy →  │
                  │  LocalHeuristic) — NO LLM        │
                  └────────────────┬─────────────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │ sources.json (rules + caps)  │
                    │ + _pending_rediscovery       │
                    │ + _ai_proposal               │
                    └──────────────┬───────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
   ┌────────┴────────┐  ┌──────────┴──────────┐  ┌────────┴────────┐
   │ verify_and_heal │  │ brand_rediscovery   │  │ ai_selector     │
   │ (batch健康巡检) │  │ (domain rediscovery │  │ _bootstrap      │
   │                 │  │  via DDG/Bing)      │  │ (LLM 生成草稿)  │
   └────────┬────────┘  └──────────┬──────────┘  └────────┬────────┘
            │                      │                      │
            │   trigger when family collapse              │
            │ ◀────────────────────┘                      │
            │                                             │
            │ trigger when suspect_dead_search            │
            └─────────────────────────────────────────────┘
```

### 3.1 新模块布局

```
magnet/
├── crawler_v2/
│   ├── extractor.py         (保持)
│   ├── healer.py            (保持，不接 LLM)
│   ├── smart_list.py        (保持)
│   ├── ai/                  (新建)
│   │   ├── __init__.py
│   │   ├── llm_provider.py     # ← _ai_bootstrap_common 的 resolve_llm_choice + LLMChoice
│   │   ├── selector_synth.py   # ← _ai_bootstrap_crawl4ai 的 run_crawl4ai_extraction
│   │   └── reverify.py         # ← _ai_bootstrap_batch 的批量 driver
│   └── strategy.py          (新建：parse_strategy 路由)
├── discovery/
│   ├── search_engine.py     (保持)
│   ├── link_sniffer.py      (保持)
│   ├── brand_rediscovery.py (新建：← _brand_domain_finder)
│   └── search_form_probe.py (新建：← _brand_search_probe)
├── scripts/                 (运维入口，不是次抛工具)
│   ├── verify_and_heal.py
│   ├── health_check.py      (从根迁入)
│   └── ai_reverify.py       (批量 AI 复核 suspect_dead，调用 crawler_v2.ai.reverify)
└── (删除所有 _xxx.py 临时脚本)
```

### 3.2 sources.json 契约扩展（向后兼容）

```jsonc
{
  "id": "knaben.org",
  "site": {"name": "knaben.org", "origin": "https://knaben.org"},
  "capabilities": {
    "supports_search": true,
    "supports_detail": true,
    "parse_strategy": "list_page",        // 新：默认 list_page
    "fetch_strategy": ["stealthy"],       // 新：默认 ["fetcher","requests","stealthy"]
    "brand_family": null                  // 新：knaben 是独立站，没家族
  },
  "search": {
    "request_template": "/search/?q={query}",
    "parse_metadata": {
      "selectors": {                      // 真正生效的 selectors
        "list_item": "tr[data-id]:has(td a[href^='magnet:'])",
        ...
      }
    }
  },
  "health": {
    "status": "yellow",                   // 枚举不变
    "status_detail": "parsing_failed",
    "suspect_signals": ["dead_search"]    // 新：可选辅助信号
  },
  "_ai_proposal": {                       // 新：AI 生成的草稿，需人工 review
    "generated_at": "2026-05-22T10:00Z",
    "selectors": {...},
    "confidence": 0.6,
    "validation": {"magnets_found": 30, "list_items": 50}
  },
  "_pending_rediscovery": [               // 新：domain finder 输出的候选
    {"host": "cilibao.top", "title": "...", "score": 0.8}
  ]
}
```

**status_detail 枚举不变**（继续 7 值），新字段全部嵌套在已有结构里或 `_` 前缀。

### 3.3 strategy 路由器（healer 入口前置）

```python
# crawler_v2/strategy.py
def route(rule):
    """Decide which healer pipeline runs based on capabilities.parse_strategy."""
    cap = (rule.get('capabilities') or {})
    s = cap.get('parse_strategy', 'list_page')
    if s == 'list_page':
        return 'pipeline_list'         # 当前 healer 链
    if s == 'detail_follow':
        return 'pipeline_detail_follow'  # 列表 → 跟 detail_link → magnet
    if s == 'spa_xhr':
        return 'pipeline_spa'          # StealthyFetcher network_idle 强制
    if s == 'nav_aggregator':
        return 'skip_or_discovery'     # 不跑 healer，进 discovery
    return 'pipeline_list'
```

---

## 4. 整合路径（v0.3.5 起，分 6 步走）

| 步 | 范围 | 工作量 | 是否可独立交付 |
|----|------|--------|----------------|
| 1 | **写本文件 + 把 `magnet/_xxx.py` 标 dev-only** | 10 min | ✓（文档先行） |
| 2 | **创建 `crawler_v2/ai/` 模块**：搬 `_ai_bootstrap_common` → `llm_provider.py`，搬 `_ai_bootstrap_crawl4ai` 核心函数 → `selector_synth.py`。CLI 入口移到 `scripts/ai_reverify.py` | 30 min | ✓（旧 _ai_bootstrap_*.py 可立刻删） |
| 3 | **创建 `discovery/brand_rediscovery.py`**：把 `_brand_domain_finder` 改为函数 `find_brand_domains(brand_id, dead_hosts) → [candidate]`。CLI 入口移到 `scripts/brand_rediscover.py` | 20 min | ✓（旧 `_brand_*.py` 可立刻删） |
| 4 | **新增 `capabilities.parse_strategy` 字段**：默认全 `list_page`，对已知详情页型源（yts.rs / cilitiantang.club / cilishenqi.me / yhdm33.com）改为 `detail_follow` | 10 min | ✓（向后兼容） |
| 5 | **创建 `crawler_v2/strategy.py` 路由 + `pipeline_detail_follow`** | 60 min | ✓（救活 ~5% 详情页型源） |
| 6 | **`verify_and_heal` 联动**：检测到 ≥3 个同 `brand_family` 一起 gray 时，自动调 brand_rediscovery，候选写入 `_pending_rediscovery` | 30 min | ✓（自动化闭环） |

总工作量约 **2.5-3 小时**，可以分 2-3 个 session 推进。

---

## 5. 验收标准（每步必须满足）

1. `python validate_enum.py` → ALL VALID（不动 status_detail 枚举）
2. 旧的 `verify_and_heal.py` / `health_check.py` 调用接口不变（被外部 admin-server 用）
3. 删除的 `_xxx.py` 工具其能力必须有等价模块化替代
4. DEV-LOG 每步更新一条 vX.Y.Z 记录
5. `sources.json` 大小不显著膨胀（新字段全部 lazy 写入，只对要用的源加）

---

## 6. 不做什么（保守边界）

- **不重写 v1 `crawler/`**：v1 是 v2 的 parent，被 healer/extractor 继承。重写 v1 会引入回归。
- **不动 `ai_parser/ai_parser.py`**：1500+ 行老代码，是 healer 的 LocalHeuristic 来源。
- **不在生产路径加 LLM**：AI 永远是「离线增强」，不是实时调用。
- **不删除 sources.json 中任何源**：契约约束，永远只改 health。
- **不删根目录历史 `_xxx.py`**：那是别人留的，跟我无关，scope 之外。我只负责清理我加的 v0.3.x 那 6 个。

---

## 附：实际优先级（告诉接续 AI 怎么继续）

如果你接续这个工作，按以下顺序：

1. **必须先读** `magnet/AGENTS.md` + `docs/project-nebula/DEV-LOG.md` 最新 1-2 条 + 本文件
2. **第一件事**：执行步骤 2（搬 `_ai_bootstrap_*` → `crawler_v2/ai/`），删除旧脚本
3. **第二件事**：执行步骤 3（搬 `_brand_*` → `discovery/`），删除旧脚本
4. **每完成一步**：跑 `python validate_enum.py` + 写 DEV-LOG
5. **不许新加 `magnet/_xxx.py` 类型的次抛脚本**——任何能力先想「这是什么模块的什么函数」
