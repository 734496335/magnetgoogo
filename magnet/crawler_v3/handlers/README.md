# crawler_v3/handlers — 逆向产出 Tier 2 处理器

每个 `.py` 文件 = 一个共享平台的反爬算法 Python 还原。一次逆向，N 个站点解锁。

## 工作流（hello_js_reverse_skill）

参考 `WhiteNightShadow/hello_js_reverse_skill` 的 Phase 0–5：

| Phase | 任务 | 工具 |
|---|---|---|
| 0 | 进入页面（绕初步检测） | `js-reverse-mcp` (Camoufox) |
| 1 | 抓搜索请求（Network） | mcp browser_network_log |
| 2 | 找 JS 入口（定位 token 字段在哪个 script 算的） | mcp js_search / mcp js_breakpoint |
| 3 | hook 验证（在加密函数入口下断点，捕获输入输出） | mcp js_eval |
| 4 | 还原算法（把 JS 翻译成 Python） | LLM + 单测 |
| 5 | 写入 `handlers/{platform_id}.py` | 本目录 |

## 已知目标（优先级排序）

| Platform ID | 影响源 | 状态 | 备注 |
|---|---|---|---|
| `thatcdn` | laowangzo / wuqianso / xiongmaogb / lemonun (4 yellow) + 未来同平台 | TODO | `/recaptcha/v4/challenge` 自定义 captcha |
| `clb_spa` | 16 CLB mirrors | TODO | SPA captcha cookie 算法 |
| `btsearch_love` | 1 源 | TODO | Next.js SPA token |

## Handler 规范

```python
from magnet.crawler_v3.tiers.tier2_handler import register_handler
from magnet.crawler_v3.tiers.base import SearchResult

@register_handler("thatcdn")
def thatcdn_search(source: dict, query: str) -> list[SearchResult]:
    """逆向算出 captcha token → 直接调搜索 API → 解析返回。"""
    # 1. 算 token (纯 Python，对应 JS 算法)
    token = _compute_thatcdn_token(query)
    # 2. 发请求 (curl_cffi)
    ...
    # 3. 解析 → SearchResult[]
    return [...]
```

约定：
- handler **不得**调用浏览器（那是 Tier 1 的职责）
- handler **必须**纯函数（无全局状态、可单测）
- handler **必须**配单测：`tests/handlers/test_{platform_id}.py`

## 失效检测

handler 在站点更新算法后会失效。orchestrator 的 fallback 链会自动降级到 Tier 1（CloakBrowser），所以失效不会让源彻底挂掉，只会让它变慢。failover 触发后，会在日志里打 `[orchestrator] {site} ✗ tier2_handler reason=...`，定期巡检日志即可发现需要重新逆向的 handler。
