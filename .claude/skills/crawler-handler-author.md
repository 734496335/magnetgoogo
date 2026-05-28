---
name: crawler-handler-author
description: 新增或修改 magnet/crawler_v3/handlers/ 下的源 handler 时加载。包含 Tier 选型决策树与代码骨架。
---

# Crawler v3 Handler 编写规范

## Tier 选型决策树（按顺序判断，命中即止）

1. 站点用 thatcdn / 自定义 reCaptcha v4 challenge → **专用 handler**（参考 `handlers/thatcdn.py`）
2. 普通 HTML SSR、可能有 Cloudflare JS challenge → **Tier 0（curl_cffi）** 即可
3. SPA 必须执行 JS 才出结果 → **Tier 1（CloakBrowser headless）**
4. Turnstile / hCaptcha 活体验证 → **Tier 2（CloakBrowser headed + 人机协同）**

## Tier 0 必备元素
- `curl_cffi.requests.Session(impersonate="chrome120")`
- 完整 Referer 链（首页 → 搜索结果 → detail），缺失会被 WAF 拒
- 默认超时 10s，重试 3 次（backoff 2s/4s）
- 检测 anti-bot：HTTP 403/503、body 含 `cloudflare` / `turnstile` / `challenge` 关键字 → 抛 `TierError(reason='waf')`

## Tier 1 必备元素
- `CloakBrowser.launch(humanize=True)`
- 通过环境变量 `CLOAK_FORCE_HEADLESS=1` 切 headless（CI 用）
- `page.wait_for_selector(...)` 而非 `sleep()`

## Handler 骨架

```python
from crawler_v3.tiers import Tier0Http, TierError
from crawler_v3.types import SearchResult

def search(query: str, source: dict) -> list[SearchResult]:
    tier0 = Tier0Http(referer_chain=[source["origin"]])
    html = tier0.get(source["search"]["url_template"].format(query=query))
    # 解析 list_item / title / magnet / size / date / seeders
    return [...]
```

## 配套测试（必写）

在 `magnet/tests/crawler_v3/handlers/test_<name>.py` 写 ≥3 个 case：

- selector 提取正确
- WAF/超时降级行为正确
- 标记 `@pytest.mark.integration` 的真实网络 case

## DoD
- `pytest -m 'not integration' magnet/tests/crawler_v3/handlers/test_<name>.py` 全绿
- `python magnet/crawler_v3/cli.py search "Inception" --origin <domain>` 返回 ≥1 magnet
- `python magnet/validate_enum.py` 通过
