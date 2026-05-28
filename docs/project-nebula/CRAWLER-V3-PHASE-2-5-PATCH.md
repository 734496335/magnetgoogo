# crawler_v3 Phase 2.5 修补工单 — Task E 复审 + tier1 误判 bug

> **背景**：Phase 2 完成后（tag `crawler-v3-phase2-complete`），人工抽查发现 Task E 的 WAF-HARDER 判定**很可能错了**。CloakBrowser 实际通过了 CF，0 results 的真因是 `sources.json` 里的 `search.request_template` 配置错。如果假设成立，能再拿回 2-4 个 GREEN 品牌。
>
> 同时 `tier1_cloak.CHALLENGE_MARKERS` 包含 `"请稍候"` 字符串，会把站点正常加载页误判为 CF 挑战，导致白白等满 40s。
>
> **Token 预算**：无限。
> **回滚锚点**：`git reset --hard crawler-v3-phase2-complete`。
> **工作量预估**：1.5h。
> **预期产出**：+0 ~ +3 GREEN 品牌 + 1 个 tier1 bug 修复。

---

## 0. 必读：人工已经验证的关键事实

针对 E.03 cilixingqiu.net (https://www.cilixingqiu.net) 跑过独立 CloakBrowser 验证脚本，原始数据：

| 时刻 | title | html_len | 解读 |
|---|---|---|---|
| t=3s | `请稍候...` | 31510 | CF 挑战页 |
| **t=6s** | **`磁力星球 - 懂你的磁力链接搜索引擎`** | **6345** | **CF 已通过 → 站点首页** |
| t=15s | 同上 | 7765 | 静止 |

**结论**：CloakBrowser 0.3.31 humanize 模式**确实通过了 CF**。0 magnets 的真因是 `search.request_template = "/?q={query}"` 不是该站点的真实 search URL。请求 `?q=Inception` 返回的是首页（6.3KB），不是搜索结果页。

跟 Phase 1 修的 `clttone.top`（`?word=` → `?kw=`）属于同一类问题。

---

## 1. 任务范围（精确）

### Task P1：5 个 WAF-HARDER 源的 search_template 复审

| ID | brand | origin | 当前 request_template |
|---|---|---|---|
| E.01 | seedhub | https://www.seedhub.cc | `/categories/1/movies/`（明显错，无 `{query}`）|
| E.03 | 磁力星球 | https://www.cilixingqiu.net | `/?q={query}` |
| E.04 | 天堂磁力 | https://www.tiantangcili.net | `/?q={query}` |
| E.05 | 磁力夜 | https://www.ciliri.shop | `/?q={query}` |
| E.07 | magnetcatcat | https://magnetcatcat.com | `/search?q={query}` |

**对每一个源**逐个执行 `§2 单源工作流`。

### Task P2：tier1_cloak 误判 bug 修复

`magnet/crawler_v3/tiers/tier1_cloak.py:39-46` 的 `CHALLENGE_MARKERS` 含 `"请稍候"` / `"正在进行安全验证"`。这两个中文短语会出现在站点正常加载文案里，不是 CF 独占。

**修复策略**（最小改动）：
- 把 `"请稍候"` 和 `"正在进行安全验证"` 限定为只在 `<title>` 标签或 `head` 内出现才算挑战
- 或者改为更精确的 CF 标记：`"请稍候，正在跳转到目标网址"`、`Cloudflare`、`cf-mitigated`、`__cf_chl_`

**禁止**直接删除 `"请稍候"` 标记（原意是兜底中文 CF 站点），要做精确化。

---

## 2. 单源工作流（Task P1 每个源都按此流程）

### Step 1：起 CloakBrowser 看真实首页 HTML

写个临时探针脚本（只做诊断，跑完删除）：

```python
# tmp_probe_homepage.py
from cloakbrowser import launch
import time
from pathlib import Path

ORIGIN = "https://<host>"  # 替换为目标
b = launch(headless=True, humanize=True)
try:
    p = b.new_page()
    p.goto(ORIGIN + "/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(8)  # 留够 CF 通过时间
    html = p.content()
    Path(f"tmp_homepage_{ORIGIN.split('//')[1].split('/')[0]}.html").write_text(html, encoding="utf-8")
    print(f"title={p.title()!r} len={len(html)}")
finally:
    b.close()
```

跑完检查 HTML 长度：
- **html_len < 5000**：站点本身可能是 SPA 空壳 → 标 `SPA-shell-confirmed`，**不再花时间**
- **html_len > 8000**：有真实内容 → 进 Step 2

### Step 2：找真实搜索表单

读 HTML 找 `<form>` 和 search-related `<input>`，命令：

```powershell
python -c @"
from pathlib import Path
import re
html = Path('tmp_homepage_<HOST>.html').read_text(encoding='utf-8')
print('=== forms ===')
for f in re.findall(r'<form[^>]*>', html, re.I)[:5]:
    print(' ', f)
print('=== search inputs ===')
for i in re.findall(r'<input[^>]*>', html, re.I):
    if any(k in i.lower() for k in ['search','name=\"q\"','name=\"kw\"','keyword','query','word']):
        print(' ', i)
print('=== search-like links ===')
for h in set(re.findall(r'href=[\"\\\']([^\"\\']*(?:search|/s/|\\?q=|\\?kw=|\\?keyword=|\\?word=)[^\"\\']*)[\"\\\']', html))[:10]:
    print(' ', h)
"@
```

寻找：
1. `<form action="...">` 的 action URL
2. `<input name="?">` 的真实 input name（可能是 `q` / `kw` / `word` / `s` / `keyword`）
3. 页面里现有的搜索类 anchor

### Step 3：手动验证候选 URL

构造候选 search URL，再跑 CloakBrowser 看返回页：

```python
# 改 ORIGIN + 候选 search_path 后再跑一次 tmp_probe_homepage.py
# e.g. ORIGIN + "/search?keyword=Inception"  或  ORIGIN + "/?kw=Inception"
```

判定：
- 返回 HTML 含 ≥3 个 `magnet:?xt=urn:btih:` → **找到真实 search URL**
- 仅含 search box 重复内容 → 还是错的，再换 query name 试

### Step 4：更新 sources.json + 复测

找到真实 URL 后，编辑 `sources.json` 那一条：
- 改 `search.request_template`
- 如果该站要求 `requires_browser`，确认已设
- 跑两次不同 query 验证：

```powershell
python -m magnet.crawler_v3 search "蜘蛛侠" --origin <host> --limit 5
python -m magnet.crawler_v3 search "Inception" --origin <host> --limit 5
```

### Step 5：终态分类与 commit

按 §3 终态规则单源单 commit。

### Step 6：清理探针

每完成一个源**立即删 tmp_probe_homepage.py 和 tmp_homepage_*.html**，不要污染仓库。

---

## 3. Task P1 终态规则

| 终态 | 触发条件 | sources.json 操作 |
|---|---|---|
| **GREEN-promoted-fixed** | 修对 search URL 后，2 次 query 都 ≥3 magnets | 改 `request_template`，更新 `health.status=green/status_detail=ok` |
| **YELLOW-fixed** | 1 次过 1 次不过 / <3 magnets | 改 `request_template`，留 yellow 但记笔记 |
| **SPA-shell-confirmed** | Step 1 html_len <5000 | 不动 sources.json，progress.md 记原因，commit "no-op" |
| **TRULY-WAF** | 找到了真 search URL，但 CloakBrowser 跑出来还是 0 magnets，且 HTML 含 `Just a moment` 或 `cf-browser-verification` | 留 yellow + 加 `notes: "needs_tier2_handler_or_2captcha"` |
| **DEAD-confirmed** | 域名失效 / 持续 5xx | 沿用 MiMo 的 DEAD 判定（不需重测）|

---

## 4. Task P2 实施细节

### 4.1 修改 `magnet/crawler_v3/tiers/tier1_cloak.py`

把 `CHALLENGE_MARKERS` 重新分类：

```python
# 强信号：只要 head 任意位置出现就肯定是 CF 挑战
CF_STRONG_MARKERS = (
    "challenge-platform",
    "cf-browser-verification",
    "Just a moment",
    "Checking your browser",
    "__cf_chl_",
    "cf-mitigated",
)

# 弱信号：仅在 <title> 标签内出现才算挑战（避免误判站点正常 loading 文案）
CF_WEAK_TITLE_MARKERS = (
    "请稍候",
    "正在进行安全验证",
)
```

`_poll_for_results` 内部的判定：

```python
challenge_present = (
    any(m in head for m in CF_STRONG_MARKERS)
    or self._title_has_weak_marker(page)
)
```

`_title_has_weak_marker` 实现：

```python
def _title_has_weak_marker(self, page) -> bool:
    try:
        title = page.title() or ""
    except Exception:
        return False
    return any(m in title for m in CF_WEAK_TITLE_MARKERS)
```

### 4.2 加测试 `magnet/tests/crawler_v3/test_tier1_markers.py`

至少 4 个用例：

```python
def test_cf_strong_marker_in_body_is_challenge():
    # head 含 'Just a moment' → True
def test_weak_marker_only_in_body_not_challenge():
    # body 含 '请稍候' 但 title 不含 → False（站点正常加载文案）
def test_weak_marker_in_title_is_challenge():
    # title='请稍候...' → True
def test_clean_page_not_challenge():
    # 啥都没有 → False
```

### 4.3 验证 + commit

```powershell
python -m pytest magnet/tests/crawler_v3 -m 'not integration' -q
# 期望：52/52 passed (48 + 4 new)
```

单 commit：

```
fix(crawler_v3-tier1): precise CF challenge detection (avoid false positives)

CHALLENGE_MARKERS contained '请稍候' / '正在进行安全验证' which are also
common Chinese loading text on regular sites. This caused tier1_cloak to
poll the full 40s on cilixingqiu.net etc. even after CF passed.

Changes:
 - Split markers into CF_STRONG_MARKERS (must appear in head) and
   CF_WEAK_TITLE_MARKERS (must appear in <title> only).
 - Added 4 unit tests covering the false-positive cases.

Discovered during Phase 2.5 patch on E.03 verification.
```

---

## 5. 单源单 commit 规约（这次必须严守）

**违反规约的 commit 会被人工拒收**。每个源（含 SPA-shell-confirmed 这种 no-op）都必须独立 commit：

```
fix(crawler_v3-phase2.5): E.<NN> <brand>(<host>) -> <终态>

Hypothesis: search.request_template was wrong (returned homepage, not results).
Investigation: <1-2 line description of what you found in HTML>
Action:
  - Old request_template: <X>
  - New request_template: <Y>
  - Re-verified: 2x queries (蜘蛛侠 / Inception), n=<count>
Final state: <GREEN-promoted-fixed | YELLOW-fixed | SPA-shell-confirmed | TRULY-WAF>
```

**禁止**用 `batch` 类 commit 把多个源塞一起。

---

## 6. 进度跟踪

更新 `docs/project-nebula/_phase2_progress.md`：

在 Task E 表格下面追加 §Task P1 复审 段落：

```markdown
## §Task P1 复审（2026-XX-XX）

| ID | 原终态 | 新终态 | 真实 search_template | n_magnets |
|---|---|---|---|---|
| E.01 | WAF-HARDER | _pending_ | | |
| E.03 | WAF-HARDER | _pending_ | | |
| E.04 | WAF-HARDER | _pending_ | | |
| E.05 | WAF-HARDER | _pending_ | | |
| E.07 | WAF-HARDER | _pending_ | | |
```

---

## 7. Definition of Done

```bash
# [DoD.1] 测试不破
python -m pytest magnet/tests/crawler_v3 -m 'not integration' -q
# 期望：52/52 passed (48 原 + 4 新)

# [DoD.2] tier1 修复在生效
python -c "from magnet.crawler_v3.tiers.tier1_cloak import CF_STRONG_MARKERS, CF_WEAK_TITLE_MARKERS; print('strong:', CF_STRONG_MARKERS); print('weak_title:', CF_WEAK_TITLE_MARKERS)"
# 期望：能 import 到这两个常量

# [DoD.3] _phase2_progress.md §Task P1 表 5 行非 _pending_

# [DoD.4] 至少 5 个 fix(crawler_v3-phase2.5) commits
git log --oneline | findstr "phase2.5" | Measure-Object -Line
# 期望：>=6 (5 sources + 1 tier1 fix)

# [DoD.5] 临时探针脚本全清干净
git status --short | findstr "tmp_"
# 期望：空输出

# [DoD.6] validate_enum 通过
python validate_enum.py | findstr "ALL VALID"
```

全过 → 在本文档末尾加 `Phase 2.5 implemented by <agent-name> on <date>`，并报告净增 GREEN 品牌数。

---

## 8. Decision Tree

```
Step 1 html_len < 5000?
  └─ Yes → 标 SPA-shell-confirmed，commit no-op，下一个源

Step 2 找不到任何 form/search input/search anchor?
  └─ Yes → 标 SPA-shell-confirmed（站点确实没传统搜索）
  └─ No  → 进 Step 3

Step 3 试了 3 个候选 search URL 都 0 magnets?
  └─ HTML 含 cf 挑战标记 → 标 TRULY-WAF
  └─ HTML 是真实站点页但没结果 → 站点搜索功能死了，标 SKIP-search-broken

Step 4 找到 URL 但只过 1 次 query?
  └─ 标 YELLOW-fixed（保留改动，不升 GREEN）

Step 5 站点搜索结果是 detail 链接而非 magnet?
  └─ 配置 search.detail.selectors.magnet（参考 thatcdn.py 的 _fetch_detail_magnets 模式）
```

---

## 9. 不许动

- `magnet/crawler_v3/handlers/thatcdn.py`（已稳定）
- `magnet/crawler_v3/orchestrator.py` / `detector.py` / `tiers/base.py`
- 已 GREEN 的源（51 个）
- Task F 已经 DEAD 的源（不要再去复活）

---

**起点**：从 **E.03 (cilixingqiu.net)** 开始 — 已知 CloakBrowser 通过 CF（人工已验证），最有可能修出 GREEN。
