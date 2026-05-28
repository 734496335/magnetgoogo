# crawler_v3 Phase 3 实施手册：人机验证 + Cookie 持久化

> **核心思路转向**：放弃「全自动绕过 anti-bot」幻想，采用 legado（开源阅读 app）已稳定运行多年的方案 — **让用户点一次盾牌，cf_clearance cookie 复用 30 天**。
>
> **回滚锚点**：tag `crawler-v3-phase2-5-complete`。
> **Token 预算**：无限。MiMo 主导实施。
> **预估工作量**：4-6h。
> **预期产出**：+5-8 GREEN 品牌（破解 Turnstile/CF 类活体验证站）。

---

## 0. 背景：legado 已经走通这条路

源码位置：`d:\lpproduct\magnet\legado-master\app\src\main\java\io\legado\app\`

### 关键参考文件（**读这些，别从零设计**）

| 文件 | 作用 |
|---|---|
| `ui/browser/WebViewActivity.kt:269-310` | CustomWebViewClient.onPageFinished：CF 检测 + cookie 持久化 |
| `ui/browser/WebViewActivity.kt:300-308` | `evaluateJavascript("!!window._cf_chl_opt")` CF 探针 |
| `help/http/CookieStore.kt` | Cookie 持久化 KV 存储 |
| `help/http/CookieManager.kt` | applyToWebView：把存的 cookie 注入到 WebView |
| `help/source/SourceVerificationHelp.kt` | 触发 / 收集验证结果的协调器 |

### legado 的核心循环

```
1. HTTP 请求被站点拒绝（403 / CF challenge HTML）
2. 抛 NeedSourceVerificationException(url)
3. UI 弹出 WebViewActivity，加载该 URL
4. 用户看到 CF 盾牌，点击 → CF 自己跑完 → cookie 注入 WebView
5. onPageFinished 检测 _cf_chl_opt 已变 false → 把所有 cookie 存 CookieStore
6. 后续 HTTP 请求带这些 cookie → 直接 200 OK
7. cookie TTL 由站点决定（CF 通常 30 天）
```

**这套机制经过 legado 数百万用户、无数 anti-bot 站点验证过。我们只需要把它移植到 v3 + RN 客户端 + 服务端 CLI**。

---

## 1. 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                        CookieStore                           │
│   ~/.cache/magnet/cookies/<origin>.json  (TTL=30d default)   │
└──────────────────────────────────────────────────────────────┘
                ▲                        ▲
                │ read                   │ write
                │                        │
        ┌───────┴────────┐      ┌───────┴────────────────────┐
        │  Tier 0 HTTP   │      │  CLI verify-interactive    │
        │  curl_cffi     │      │  (服务端运维手动过 CF)     │
        │  附带 cookie   │      └────────────────────────────┘
        └────────────────┘                ▲
                                          │ write
                                  ┌───────┴────────────────────┐
                                  │  RN VerifyWebView          │
                                  │  (移动端用户手动过 CF)     │
                                  └────────────────────────────┘
                ▲ escalate (no cookie or expired)
                │
        ┌───────┴────────┐
        │  Tier 1 Cloak  │
        │  (尝试自动过)   │
        └────────────────┘
```

### 三个写入端 / 一个读取端

- **写入端**：CLI 服务端、RN VerifyWebView、（可选）Tier 1 CloakBrowser 自动通过后也写入
- **读取端**：所有 HTTP 请求（Tier 0 / Tier 1 / web 端 fetcher）

---

## 2. Task K — CookieStore Python 实现

### 2.1 文件 `magnet/crawler_v3/cookie_store.py`

API：

```python
class CookieStore:
    """Per-origin cookie persistence with TTL.

    Storage: ~/.cache/magnet/cookies/<origin_safe>.json
    Format: {"cookies": [{"name", "value", "domain", "path", "expires"}], "stored_at": iso_ts}
    """
    def __init__(self, root: Path | None = None, default_ttl_days: int = 30): ...

    def get(self, origin: str) -> list[dict]:
        """Return non-expired cookies for origin (empty list if none/expired)."""

    def put(self, origin: str, cookies: list[dict]) -> None:
        """Replace all cookies for origin. Expired ones are still pruned at get-time."""

    def merge(self, origin: str, cookies: list[dict]) -> None:
        """Add to existing without dropping unrelated cookies."""

    def delete(self, origin: str) -> None: ...

    def list_origins(self) -> list[str]: ...

    def to_header(self, origin: str) -> str:
        """Return Cookie header string for HTTP requests."""

    def to_curl_cffi_format(self, origin: str) -> dict:
        """Return dict suitable for curl_cffi.requests.Session.cookies.update()."""
```

### 2.2 设计约束

- **不依赖外部 KV**：纯 JSON 文件，跨 Python 重启可读
- **路径安全**：`origin_safe` 用 `re.sub(r'[^\w.-]', '_', origin)` 防注入
- **过期清理**：只在 `get()` 时惰性清理，避免后台线程
- **空 cookie 也算 hit**：站点没设 cookie 但通过验证也是有效状态，用 `meta.verified_at` 标记

### 2.3 单测 `magnet/tests/crawler_v3/test_cookie_store.py`

至少 6 个用例：
1. put → get 同 origin 拿回
2. 不同 origin 隔离
3. 过期 cookie 自动 prune
4. delete 删干净
5. to_header 输出格式
6. 跨进程持久化（写一次，新建另一个 store 读出来）

---

## 3. Task L — Tier 0 / Tier 1 集成 CookieStore

### 3.1 改 `magnet/crawler_v3/tiers/tier0_http.py`

在 `fetch_html()` 顶部读 CookieStore：

```python
from magnet.crawler_v3.cookie_store import CookieStore

_COOKIE_STORE = CookieStore()  # module-level singleton

def fetch_html(url, ...):
    origin = _origin_from(url)
    cookies = _COOKIE_STORE.get(origin)
    # pass to curl_cffi via session.cookies.update or direct headers
    ...
```

### 3.2 改 `magnet/crawler_v3/tiers/tier1_cloak.py`

CloakBrowser 跑完后**抓 cookie 写回**（即便 headless 自动通过的情况，也要存）：

```python
def search(...):
    page = browser.new_page()
    # ... existing logic ...
    if results:
        # success — harvest cookies
        cookies = page.context.cookies(url)
        _COOKIE_STORE.put(origin, cookies)
    return results
```

→ 这样 Tier 1 一旦自动通过过一次，下次 Tier 0 就能直接用 cookie 跳过整个 CloakBrowser 启动开销。

### 3.3 测试要补

- mock CookieStore，验证 Tier 0 调用 `to_curl_cffi_format`
- 验证 Tier 1 成功后会 put cookie

---

## 4. Task M — CLI `verify-interactive` 命令

### 4.1 用法

```bash
python -m magnet.crawler_v3 verify-interactive --origin cilixingqiu.net
# → 启动 headed CloakBrowser，操作员看到 CF 盾牌
# → 操作员点一下，等页面加载完
# → 操作员按 Enter（命令行 input）→ harvest cookies → 写 CookieStore
# → 关闭浏览器
```

### 4.2 实现要点

`magnet/crawler_v3/cli.py` 新增 `cmd_verify_interactive(args)`：

```python
def cmd_verify_interactive(args):
    from cloakbrowser import launch
    origin = _normalize_origin(args.origin)
    b = launch(headless=False, humanize=True)  # ← 关键：headed
    p = b.new_page()
    p.goto(origin, wait_until="domcontentloaded")
    print(f"\n=== 请在浏览器窗口手动通过验证 ===")
    print(f"通过后，回到此终端按 Enter 继续...")
    input()
    cookies = p.context.cookies()
    cookie_store.put(origin, cookies)
    print(f"已存 {len(cookies)} 个 cookie 到 {cookie_store.path_for(origin)}")
    b.close()

    # 立即用 Tier 0 跑一次验证
    print(f"\n=== 立即跑 Tier 0 复测 ===")
    result = orchestrator.search({...origin source rule...}, "Inception")
    print(f"got {len(result)} magnets")
```

### 4.3 不做的部分

- 不做无人值守自动重新过验证（cookie 过期自然降级到 yellow，由 RN 端用户重过）
- 不做 cookie sharing 跨主机（单机本地存就好）

---

## 5. Task N — RN VerifyWebView 接 v3

> **范围警告**：碰 RN 客户端代码。先确认 `magnetgoogo-app/src/components/VerifyWebView.tsx` 的现状，再决定动多少。

### 5.1 现状摸底

`magnetgoogo-app/src/components/VerifyWebView.tsx` 已存在但孤立。需要：
1. 读它了解现有 API
2. 找到 RN 端 HTTP fetch 入口（搜 `searchEngine.ts` / `httpClient.ts`）
3. 看 sources.json schema 怎么标记「需要人机验证」

### 5.2 集成方案（**先确认现状再细化**）

```
RN 端 fetch(url) → 收到 403/挑战页 →
  显示 VerifyWebView with url →
  WebView 检测 _cf_chl_opt 变 false →
  抓 cookie 通过 RN-Native bridge 存 AsyncStorage →
  关闭 VerifyWebView →
  原 fetch 重试（带新 cookie）→ 200 OK
```

参考 legado 的 `WebViewActivity.kt:288-310` onPageFinished 实现。

### 5.3 任务拆分到 N.1 - N.5

- N.1 摸底现有 VerifyWebView + searchEngine 调用链（可能 0 改动就能用）
- N.2 实现 AsyncStorage cookie 持久化（参考 legado CookieStore 接口）
- N.3 onPageFinished 探针（_cf_chl_opt 检测）
- N.4 修改 httpClient.ts 自动带 cookie + 失败时弹 VerifyWebView
- N.5 端到端测：cilixingqiu.net 真机过一次，验证 cookie 复用

⚠️ 这块不熟悉就**先 N.1 写调研报告，等用户决定再做 N.2-N.5**。不要瞎改 RN 代码。

---

## 6. Task O — 复测 WAF-HARDER 源

CookieStore + verify-interactive 跑通后，对 Phase 2.5 标 WAF-HARDER 的源逐个跑一遍 verify-interactive：

| 源 | 上次终态 | 期望 |
|---|---|---|
| E.07 magnetcatcat.com | WAF-HARDER-confirmed | Turnstile 手动过 → cookie 存 → Tier 0 应能拿数据 |
| E.03 cilixingqiu.net | YELLOW-fixed | hex URL + cookie → 升 GREEN |
| E.04 tiantangcili.net | YELLOW-fixed | key param + cookie → 升 GREEN |
| E.05 ciliri.shop | SKIP (403) | 看 403 是不是 CF 早期态，过 CF 后能不能拿到结果 |
| 其他 status_detail=waf 源 | yellow | 同上 |

每源单 commit，按 Phase 2.5 同样规约。

预期产出：**+3-5 GREEN 品牌**。

---

## 7. Definition of Done

```bash
# [DoD.1] 测试通过
python -m pytest magnet/tests/crawler_v3 -m 'not integration' -q
# 期望：≥58 passed (52 + 6 cookie_store + N tier integration)

# [DoD.2] CookieStore 单独可用
python -c "from magnet.crawler_v3.cookie_store import CookieStore; s=CookieStore(); s.put('test.com',[{'name':'x','value':'y','domain':'test.com','path':'/','expires':99999999999}]); print(s.get('test.com'))"

# [DoD.3] verify-interactive 命令存在
python -m magnet.crawler_v3 verify-interactive --help
# 期望：non-zero help output

# [DoD.4] cookies 实际持久化（运维至少跑过一个真站）
ls ~/.cache/magnet/cookies/
# 期望：≥1 个 .json 文件

# [DoD.5] Task O 至少 1 个源升 GREEN
git log --oneline | findstr "phase3" | findstr "GREEN"
# 期望：≥1

# [DoD.6] DEV-LOG 顶部记录本次成果
```

全过 → tag `crawler-v3-phase3-complete`。

---

## 8. Decision Tree

```
RN 端怎么改不确定？
  └─ 先做 Task N.1 摸底报告，等用户决定 → 不要瞎动 RN 代码

CloakBrowser headless 自动过了，要不要也存 cookie？
  └─ 要存（Task L 提到）。下次直接 Tier 0 跳过 CloakBrowser 启动开销。

cookie 过期了怎么办？
  └─ Tier 0 拿到 403 → 抛 TierError(retryable=True) → orchestrator 降级 Tier 1 →
     Tier 1 也过不了（headless 对 Turnstile 通常 0%）→ 抛 TierError(hint="needs_user_verify") →
     RN 端弹 VerifyWebView 让用户重过

服务端跑批 health_check 用什么 cookie？
  └─ 服务端用 verify-interactive 命令一次性手动过，cookie 存 ~/.cache/，
     之后 30 天自动用。过期再过一次。

是否实现 cookie 自动续期？
  └─ 不实现。CF 自身机制处理（每次 200 响应都会 refresh cookie，curl_cffi 自动跟随 Set-Cookie 即可）。
```

---

## 9. 不许动

- `magnet/crawler_v3/orchestrator.py`（架构稳定，Phase 3 不需要改）
- `magnet/crawler_v3/handlers/thatcdn.py`（已工作，别动）
- `magnet/cloak_yellow_verify.py`（deprecated，2026-07-01 删）
- 已 GREEN 的源（55 个）— Task L 集成 cookie 后跑回归确认它们没坏即可
- `cf-gateway/`（不属于 v3 范围）

---

## 10. 起手第一件事

**读这 3 个文件**（都在工作区里）：
1. `d:\lpproduct\magnet\legado-master\app\src\main\java\io\legado\app\help\http\CookieStore.kt`
2. `d:\lpproduct\magnet\legado-master\app\src\main\java\io\legado\app\help\http\CookieManager.kt`
3. `d:\lpproduct\magnet\legado-master\app\src\main\java\io\legado\app\ui\browser\WebViewActivity.kt`

抄思路，**不抄代码结构**（Kotlin → Python，存储路径和 API 风格按 Python 习惯走）。

---

**完成签名**：`Phase 3 implemented by <agent-name> on <date>`，并报告净增 GREEN 品牌数 + cookie 复用观测数据（avg cookie lifetime 实测）。
