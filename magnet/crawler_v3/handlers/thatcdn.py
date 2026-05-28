"""thatcdn 平台共享 handler — TODO: 用 hello_js_reverse_skill 完成逆向后填充

平台特征（2026-05-28 探针发现）：
- 资产 CDN：`prod.b5.thatcdn.com` (CSS + 图标)
- 模板：Bootstrap 3.3.7 + 自研 anti-bot
- 行为：直接 GET `/search?keyword={q}` 返回**首页搜索表单**而非结果，
  说明服务端通过某种校验（可能是 cookie / referer / JS-set 头）
  决定是否返回真实结果

当前命中源：
- xiongmaogb.top (磁力熊猫)
- lemonun.top (磁力柠檬)
- wuqianso.org (吴签磁力)
- laowangzo.top (老王磁力)
- soxiongmao.top / lemonzc.top / bt1207yx.top / wuqianyx.top (?ref=eeenav 跳转链)
- bitdao.me

逆向工作流（hello_js_reverse_skill）：
  Phase 0 → 用 js-reverse-mcp / Camoufox 打开 https://xiongmaogb.top/
  Phase 1 → DevTools Network 抓提交搜索后的真实请求
  Phase 2 → 找到挂载在 form 上的 onsubmit / cookie 逻辑 (one.js? captcha endpoint?)
  Phase 3 → hook 加密函数，捕获生成的 token / cookie
  Phase 4 → 翻译成纯 Python，验证可独立调通
  Phase 5 → 替换 search() 实现

成功标准：handler 输入 query="蜘蛛侠" → 返回 ≥10 个含 magnet 的 SearchResult
"""
from __future__ import annotations

from ..tiers.base import SearchResult, TierError
from ..tiers.tier2_handler import register_handler


PLATFORM_ID = "thatcdn"


# Recovered selectors (from探针 HTML inspection 2026-05-28)
# These are valid once we have the correct HTML — pending Phase 2 reverse work.
THATCDN_SELECTORS = {
    "list_item": "div.search-item, ul.list-group li",
    "title": "h4 a, a.item-title",
    "magnet": "a[href^='magnet:']",
    "size": "span.size, .item-size",
}


@register_handler(PLATFORM_ID)
def thatcdn_search(source: dict, query: str) -> list[SearchResult]:
    """TODO: replace with reverse-engineered token + request flow.

    Expected once implemented:
        1. compute submission token via _thatcdn_token(query, ts=...)
        2. curl_cffi.get(/search, params={keyword: query, _t: token}, cookies={...})
        3. parse response with THATCDN_SELECTORS or smart_list
        4. return SearchResult[]
    """
    raise TierError(
        f"thatcdn handler not yet reverse-engineered. "
        f"See magnet/crawler_v3/handlers/thatcdn.py for workflow.",
        retryable=False,
        hint="run_js_reverse_skill_phase_0_to_5",
    )


def _thatcdn_token(query: str, *, ts: int) -> str:
    """Placeholder for the recovered algorithm. Replace after Phase 4."""
    raise NotImplementedError("Phase 4 not done — see module docstring")
