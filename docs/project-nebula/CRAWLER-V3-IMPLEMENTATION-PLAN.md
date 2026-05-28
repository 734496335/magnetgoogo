# crawler_v3 实施手册（指挥 AI Agent 落地）

> **本文档目标读者**：MiMo v2.5 Pro / 任何接手 v3 后续工作的 AI 编码 Agent。
> **本文档不是设计稿**——架构已落地（commit `7c4b03b`、`700d046`），代码骨架可跑。本文档给出**剩余三个任务（A/B/C）的可执行规格**，每个任务有：输入文件、改动范围、验收命令、放弃条件。
> **回滚锚点**：tag `pre-crawler-v3` (commit `48357f9`)；`git reset --hard pre-crawler-v3` 回到 v2 时代。

---

## 0. 心智模型（Agent 必读）

### 4-Tier 架构总图

```
orchestrator.search(source, query)
  ↓ detector.classify(source) 决定顺序
  ├── Tier 0 HTTP        curl_cffi + Chrome TLS 指纹（90% 普通源）
  ├── Tier 1 Cloak       CloakBrowser headless + humanize（CF JS / Turnstile / 通用 SPA）
  ├── Tier 2 Handler     hello_js_reverse_skill 产出的纯 Python 算法（共享平台 anti-bot）
  └── Tier 3 Stub        VerifyWebView（移动端兜底，Python 端 stub）
```

### 不变量（Agent 不许破坏）

1. **Tier 接口** `tiers/base.py::Tier` —— 所有 Tier 实现 `search(source, query, *, limit) -> list[SearchResult]`，失败用 `TierError(reason, retryable=, hint=)` 抛出，**不许抛通用异常**
2. **`SearchResult` dataclass** —— 字段不许加，要加先改 `tiers/base.py` 并更新所有 Tier
3. **Smart List Detector** `crawler_v2/smart_list.py` 已胜出，**不许重写**，crawler_v3 只 import 不复制
4. **sources.json schema 0.1**：`rulesets[0].rules[*]` 是规则数组；`search.request_template` 是 URL 模板；`search.parse_metadata.selectors` 是选择器；`tier_override: {tier, platform}` 强制路由
5. **handler 必须纯 Python**——Tier 2 handler 不许调浏览器；如果离不开浏览器，那就是 Tier 1 的事

### 当前 status

| 模块 | 状态 |
|---|---|
| 4-Tier 骨架 | ✅ 就绪可跑 |
| Tier 0 curl_cffi | ✅ 实测 fitgirl 1.8s 通 |
| Tier 1 CloakBrowser 0.3.31 | ✅ 实测启动 + Turnstile 自动通过普通 CF 站 |
| Tier 2 thatcdn handler | ⏸ 占位，**待 Task A 实现** |
| web `route.ts` Tier 1 迁移 | ⏸ **待 Task B** |
| health_check 接 v3 | ⏸ **待 Task C** |
| 回归测试 | ⏸ **待 Task D**（D 跟着 A/B/C 同步加） |

---

## 1. Agent 启动后的阅读顺序（≤ 10 分钟）

1. `magnet/AGENTS.md` —— 项目行为规范
2. 本文档（CRAWLER-V3-IMPLEMENTATION-PLAN.md）
3. `magnet/crawler_v3/README.md` —— 架构总览
4. `magnet/crawler_v3/tiers/base.py` —— 看 `Tier` 接口、`SearchResult`、`TierError`
5. `magnet/crawler_v3/orchestrator.py` —— 看调度链
6. 跑 smoke：`python -m magnet.crawler_v3 classify --status yellow` 应该输出 36 行 Tier plan，4 个 thatcdn 排首位 `tier2_handler`
7. 跑 Tier 0：`python -m magnet.crawler_v3 search "Inception" --origin uindex.org --limit 5` 应该 ≤ 3s 返回 5 个 magnet

跑完 6+7 之后再开始 Task A，否则环境本身就有问题。

---

## 2. Task A — thatcdn JS 逆向（**最高价值**）

### A.0 目标

实现 `magnet/crawler_v3/handlers/thatcdn.py::thatcdn_search`，使下面四个 yellow 源能在 Tier 0 速度下返回 ≥10 个含 magnet 的 SearchResult：

- `https://xiongmaogb.top` 磁力熊猫
- `https://lemonun.top` 磁力柠檬
- `https://wuqianso.org` 吴签磁力
- `https://laowangzo.top` 老王磁力

四站共用 `prod.b5.thatcdn.com` CDN + Bootstrap 3.3.7 模板 + 自研 anti-bot。**1 次逆向 = 4 个源解锁 + 未来同平台新源零成本接入**。

### A.1 工具栈

```bash
# 1. 安装 js-reverse-mcp（Camoufox + chrome-devtools-mcp 重构，自带反检测）
git clone https://github.com/zhizhuodemao/js-reverse-mcp
cd js-reverse-mcp && npm install

# 2. 安装 hello_js_reverse_skill（Phase 0-5 工作流定义）
git clone https://github.com/WhiteNightShadow/hello_js_reverse_skill
# 把 SKILL.md 复制/链接到 Cascade 或 Cursor 的 skills 目录
```

### A.2 Phase 0–5 执行步骤

按 `hello_js_reverse_skill/SKILL.md` 的工作流，目标是恢复 `xiongmaogb.top` 的搜索请求所需 token / cookie 算法。

| Phase | 任务 | 关键 MCP 工具 | 预期产出 |
|---|---|---|---|
| **0** | 用 Camoufox 进入 `https://xiongmaogb.top/`，确认能渲染 | `browser_navigate` | 截图 + `title` 已渲染（已确认） |
| **1** | 在搜索框输入 "spider" 提交，**抓 Network 全程** | `browser_network_log` | 真实搜索请求的 URL、headers、cookies、payload |
| **2** | 找到 form 提交时执行的脚本（`/style/one.js` 或类似） | `browser_evaluate('document.scripts')` + `js_search` | 加密入口函数名 |
| **3** | 在加密函数下断点，捕获输入 → 输出映射 | `js_breakpoint` + 多次提交不同 query | 输入 query "spider"/"abc"/"长字符串" → 输出对应的 token/cookie |
| **4** | 翻译成纯 Python（`hashlib`/`hmac`/`base64` 实现 90% 情况够；遇 JSVM 用 `pyjsparser` + 模拟） | 本地 IDE | `_thatcdn_token(query, ts) -> str` 单测通过 |
| **5** | 在 `magnet/crawler_v3/handlers/thatcdn.py` 替换 `thatcdn_search` 实现 | `edit` | handler 集成完毕 |

**Phase 1 探针提示**：v3 的 `_debug_probe.py` 已经验证 GET `/search?keyword=spider` 直接返回首页表单 3.5KB——说明 token 不在 query string 里，多半在 cookie 或 POST body。所以 Phase 1 重点抓**form submit 时的 set-cookie 和 referrer header**。

### A.3 实现规格（替换 `thatcdn_search` stub）

```python
# magnet/crawler_v3/handlers/thatcdn.py 完成后的形态（示意，不是最终代码）

from curl_cffi import requests as cc_requests
from ..tiers.base import SearchResult, TierError
from ..tiers.tier2_handler import register_handler
from ..parser import extract_results_from_html

@register_handler("thatcdn")
def thatcdn_search(source: dict, query: str) -> list[SearchResult]:
    origin = source["site"]["origin"].rstrip("/")
    # 1. 拿到入站 cookie（首页访问可能 set 一个 challenge cookie）
    session = cc_requests.Session(impersonate="chrome124")
    session.get(origin + "/", timeout=10)

    # 2. 算 token（替换为 Phase 4 还原出的算法）
    token = _thatcdn_token(query)

    # 3. 发搜索请求（具体 method/path/body 由 Phase 1 决定）
    r = session.get(
        origin + "/search",
        params={"keyword": query, "_t": token},
        headers={"Referer": origin + "/"},
        timeout=15,
    )
    if r.status_code != 200:
        raise TierError(f"HTTP {r.status_code}", retryable=False)

    # 4. 用现成 selectors 解析（已在模块里存了 THATCDN_SELECTORS）
    results = extract_results_from_html(r.text, source=source, base_url=r.url)
    if not results:
        raise TierError("zero results — algorithm may have changed", retryable=False)
    return results
```

### A.4 验收命令

```bash
# 单源：每个 thatcdn 源独立验证
python -m magnet.crawler_v3 search "蜘蛛侠" --origin xiongmaogb.top --limit 5
python -m magnet.crawler_v3 search "蜘蛛侠" --origin lemonun.top --limit 5
python -m magnet.crawler_v3 search "蜘蛛侠" --origin wuqianso.org --limit 5
python -m magnet.crawler_v3 search "蜘蛛侠" --origin laowangzo.top --limit 5

# 批量：4 个 yellow 源全过
python -m magnet.crawler_v3 verify-yellow "蜘蛛侠"
# 期望输出：✓ PASS xiongmaogb.top n=≥5 ... 4/4 verified
```

**通过标准**：4/4 源每个返回 ≥5 个含 magnet 的 SearchResult，`?ref=eeenav` 跳转链系列也连带打通。

### A.5 失败/放弃条件（硬规则）

| 信号 | 行动 |
|---|---|
| Phase 1 抓到的关键脚本是 JSVM（webpack-encrypt-loader / `eval(_0x...)` 重度 obfuscation） | 用 `wakaru` / `de4js` 工具反混淆；**仍卡住 24h** → 走 A.6 fallback |
| Phase 4 算法翻译完但单测对不上 | 多采几个样本（不同长度、含中文 query 等）重 hook |
| 累计耗时超过 **3 个工作日** | **停止**，进入 A.6 |

### A.6 Fallback 路径（Task A 失败时）

不写 thatcdn handler，改让 Tier 1 (CloakBrowser) **手动填表 + 等结果**：

```python
# 在 tier1_cloak.py 里加一个 "interactive_form" 模式（仅当 source.search.requires_form_fill=true）
# 1. page.goto(origin)
# 2. page.fill('input[name=keyword]', query)
# 3. page.locator('button[type=submit]').click(modifiers=['humanize'])
# 4. page.wait_for_url(re.compile(r'/search'))
# 5. extract from page.content()
```

代价：每次搜索 30s+ 浏览器启动。但**至少能用**。

### A.7 不许做

- 不要为了快用通用 captcha 破解服务（2captcha 等）——thatcdn 不是标准 captcha
- 不要把 cloakbrowser 的 humanize 机制直接搬进 handler（handler 必须纯 Python，见不变量 #5）
- 不要去改 `tiers/tier2_handler.py` 的注册机制——只在 handlers/ 下加文件

---

## 3. Task B — web `route.ts` Tier 1 迁移

### B.0 目标

把 `web/src/app/api/search/route.ts` 的 Tier 2（execFile + verify-extension MV3 cookie bridge）替换为 CloakBrowser，**删除 `verify-extension/` 整个目录**。同时把 Tier 1（Playwright + CDP）也升级到 cloakbrowser-node，复用同一个二进制。

### B.1 现状（不要丢）

- `web/src/core/browser-engine.ts:107` `browserFetch()` —— Tier 1，Playwright headless + CDP
- `web/src/core/browser-engine.ts:276` `interactiveVerify()` —— Tier 2，`execFile(chromiumPath) + verify-extension/`
- `web/src/app/api/search/route.ts:5` 同时 import 这两者
- `web/src/app/api/verify-browser/route.ts:13` 也 import `interactiveVerify`
- `web/verify-extension/` 3 文件 7.8KB（manifest.json + background.js + content.js）
- 7 个自定义 handler `fetchJavBus / fetch6v520 / fetchMeijumi / fetchYhg / fetchZhongzidi / fetchRarbggo / fetchRrjav`（**全保留**，不动业务逻辑）

### B.2 步骤

**B.2.1 安装依赖**
```bash
cd web
npm install cloakbrowser playwright-core
```

**B.2.2 改写 `core/browser-engine.ts`**

替换 `browserFetch` 内部实现：
- 旧：`import { chromium } from 'playwright'; const browser = await chromium.launch(...)`
- 新：`import { launch } from 'cloakbrowser'; const browser = await launch({ headless: true, humanize: true })`

替换 `interactiveVerify` 内部实现：
- 旧：`execFile(chromiumPath, args)` + `verify-extension`
- 新：跟 `browserFetch` 一样用 `cloakbrowser.launch()`，但 `headless: false`、`humanize: true`，让 CloakBrowser 自己过 Turnstile（不再需要扩展）
- 返回值保持 `VerifyResult { success, html?, cookies? }` 不变（保签名兼容）

**B.2.3 删除扩展**
```bash
rm -rf web/verify-extension/
```
确认 `route.ts` 和 `browser-engine.ts` 都没有 `verify-extension` 字符串引用后再删。

**B.2.4 不要碰**
- `route.ts` 调用方代码 (`fetchResult = ... browserFetch(...)`、`vr = await interactiveVerify(...)`) **完全不动**——只换底层实现
- `app/api/verify-browser/route.ts` 不动
- 7 个自定义 handler 不动
- `cookieStore` / `getStoredCookies` 不动

**B.2.5 处理无头/有头模式**
- `browserFetch` 默认 headless（性能）
- `interactiveVerify` 默认 headed（CloakBrowser humanize 在有头模式效果最好）
- 但 RN 客户端 / 服务端环境跑不了有头——加一个 `process.env.CLOAK_FORCE_HEADLESS=1` 环境变量统一切到 headless

### B.3 验收命令

```bash
# 1. 类型检查 + 构建
cd web && npm run build
# 期望：build succeeded

# 2. 启动 dev server
cd web && npm run dev
# 期望：localhost:3000 启动无错

# 3. 调一个会触发 Tier 1 的源（比如 cilixingqiu.net）
curl -s 'http://localhost:3000/api/search?q=test&sources=cilixingqiu.net' | jq '.results | length'
# 期望：>0

# 4. 调一个会触发 Tier 2 的源（曾被 Turnstile 拦的）
curl -s 'http://localhost:3000/api/search?q=test&sources=clttone.top' | jq '.results | length'
# 期望：>0（如果 P0 也修了 clttone selectors 的话）

# 5. 确认目录已删
test ! -d web/verify-extension && echo "OK: verify-extension deleted"
```

### B.4 不许做

- 不要重写 7 个 custom handler 的业务逻辑
- 不要改 `cookieStore` 的语义
- 不要改 `cf-gateway` 任何东西（边缘函数与浏览器无关）
- 不要把 cloakbrowser 集成到 RN 客户端 — 桌面 Chromium 二进制移动端跑不动

### B.5 部署侧风险

CloakBrowser 自动下载 ~535MB Chromium 二进制到 `~/.cloakbrowser/`。**Vercel/Cloudflare Pages 跑不动**。
- 检查 web 端当前部署在哪：
  - 如果是 Cloudflare Pages → **不能迁移**，Task B 改为只迁移本地 dev server，生产保持现状（在 docs 里加一行说明）
  - 如果是阿里云 ECS / 自建服务器 → 可以迁移，注意 2C2G 内存
- **Agent 起手必先确认**：`cat web/wrangler.toml`（如有则是 CF）+ `find . -name 'vercel.json'` + 看 `package.json` deploy script

---

## 4. Task C — 退役老路径

### C.0 目标

让 `magnet/health_check.py` 用 v3 orchestrator，让 `cloak_yellow_verify.py` 永久退役。

### C.1 步骤

**C.1.1** 在 `magnet/health_check.py` 里把 yellow 源 verify 段落（搜索 `cloak_yellow_verify` 或类似）替换为：
```python
from magnet.crawler_v3 import search as v3_search
results = v3_search(rule, query="蜘蛛侠", limit=5)
ok = bool(results) and any(r.magnet for r in results)
```

**C.1.2** 在 `magnet/cloak_yellow_verify.py` 顶部加 deprecation banner：
```python
import warnings
warnings.warn(
    "cloak_yellow_verify.py is deprecated since 2026-05-28. "
    "Use 'python -m magnet.crawler_v3 verify-yellow' instead. "
    "Will be removed 2026-07-01.",
    DeprecationWarning, stacklevel=2,
)
```

**C.1.3** 在 `.github/workflows/health-check.yml`（如有引用 cloak_yellow_verify）改为 `python -m magnet.crawler_v3 verify-yellow ...`

### C.2 验收

```bash
python magnet/health_check.py --dry-run 2>&1 | grep -E "v3|orchestrator|tier"
# 期望：日志里能看到 v3 orchestrator 调用

python magnet/cloak_yellow_verify.py "test" 2>&1 | grep -i deprecat
# 期望：DeprecationWarning 输出
```

### C.3 不许做

- **不要删 cloak_yellow_verify.py**，留 1 个月 grace 期
- 不要动 GitHub Actions 的 cron 频率
- 不要改 mg-data 加密推送逻辑

---

## 5. Task D — 回归测试（**跟着 A/B/C 同步加，不单独排期**）

### D.0 目录

新建 `magnet/tests/crawler_v3/`：
```
magnet/tests/crawler_v3/
├── __init__.py
├── conftest.py            # fixture: 加载 sources.json、构造 fake source dict
├── test_orchestrator.py   # TierError fallback 链 + classify
├── test_tier0_http.py     # mock curl_cffi 200/403/timeout 三种响应
├── test_tier1_cloak.py    # 跳过 (需要真浏览器，标 @pytest.mark.integration)
└── handlers/
    └── test_thatcdn.py    # Task A 完成后必加：算法单测 + 集成测试
```

### D.1 关键测试（A/B/C 必带）

**`test_orchestrator.py`**
- 给一个 fake source 强制 raise TierError(retryable=True) on Tier 0，断言会降级到 Tier 1
- 给 `tier_override: tier2_handler` 但没注册 platform 的 source，断言 Tier 2 declines (`supports() == False`) → 降级到 Tier 0

**`test_thatcdn.py`**（Task A 完成后）
- 单测 `_thatcdn_token("spider")` 返回固定值（与 Phase 3 hook 抓到的真实值一致）
- 集成测试用 `@pytest.mark.integration` 标记，跑真实站点（CI 不跑，本地 verify 时跑）

### D.2 CI

`.github/workflows/test-crawler-v3.yml`：
```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - run: pip install -r magnet/requirements.txt
      - run: pip install pytest pytest-mock curl_cffi
      - run: pytest magnet/tests/crawler_v3 -m 'not integration' -v
```

---

## 6. Conventions（Agent 必守）

1. **每个 task 单独 commit**，commit message 带 `feat(crawler_v3-A): ...` / `feat(crawler_v3-B): ...` / `feat(crawler_v3-C): ...` 前缀
2. **每个 task 完成后立即更新 `docs/project-nebula/DEV-LOG.md`**（顶部插入新版本块），格式参考最近的 `crawler-v3-scaffold` 条目
3. **质量门禁**（每个 commit 之前跑）：
   ```bash
   python validate_enum.py    # sources.json 枚举合规
   pytest magnet/tests/crawler_v3 -m 'not integration'  # 单测
   python -m magnet.crawler_v3 classify --status yellow  # smoke
   ```
4. **代码风格**：见 `docs/project-nebula/CODE-STANDARDS.md`；类型注解必带（v3 已用 `from __future__ import annotations`，保持）
5. **不许引入新依赖**除非：
   - 在本计划里点名提到（cloakbrowser、curl_cffi、cloakbrowser-node、playwright-core 是允许的）
   - 或者你能证明现有依赖不能完成任务，且把理由写进 commit message
6. **遇到 sources.json 模糊处**：先看 `magnet/AGENTS.md` 第 2 条契约，再看 schema_version 0.1 的现有规则，**最后的最后**再问用户

## 7. Don't-touch list（修改即视为破坏）

- `magnet/crawler/`（v1）、`magnet/crawler_v2/`（v2） —— 对比基准，禁动
- `magnet/cloak_yellow_verify.py` —— 仅加 deprecation 注释（Task C），不许删
- `magnetgoogo-app/src/components/VerifyWebView.tsx` 和 `VerifyManager.ts` —— RN 端 Tier 3，不动
- `magnetgoogo-app/src/core/searchEngine.ts` —— 客户端搜索流，不动
- `cf-gateway/` —— 边缘函数，跟浏览器无关
- `web/verify-extension/` —— **Task B 才能删**，其它 Task 不许碰
- `sources.json` 的 `health.status` 枚举 / `status_detail` 枚举 —— 见 `validate_enum.py`，不许加新值

## 8. Definition of Done（全 Task 完成的最终验收）

跑下列脚本全部通过：

```bash
# 8.1 Smoke
python -m magnet.crawler_v3 classify --status yellow | findstr /R "tier" >nul && echo OK

# 8.2 Tier 0 真测（普通源）
python -m magnet.crawler_v3 search "Inception" --origin uindex.org --limit 5

# 8.3 Tier 2 真测（thatcdn 4 源全过）— Task A 完成后
python -m magnet.crawler_v3 verify-yellow "蜘蛛侠"
# 期望：4/4 thatcdn 源 PASS

# 8.4 Web 端 Tier 1 迁移 — Task B 完成后
cd web && npm run build && (test ! -d verify-extension)

# 8.5 health_check 走 v3 — Task C 完成后
python magnet/health_check.py --dry-run | findstr /I "v3 orchestrator"

# 8.6 单测
pytest magnet/tests/crawler_v3 -m 'not integration' -v

# 8.7 枚举校验
python validate_enum.py | findstr /C:"ALL VALID"
```

全部 OK 后：
- `git tag crawler-v3-stable`
- 更新 `magnet/AGENTS.md` 的 "项目结构" 段落，说明 crawler_v3 已成主路径
- DEV-LOG 写一条 `crawler-v3-complete` 版本号

---

## 附：Agent 决策树（遇到模糊情况）

```
任务模糊？
  ├─ 是单纯实现细节？→ 按 AGENTS.md 第 1 条 "先想再写"，列出 2 个备选方案，挑最小实现
  ├─ 涉及 sources.json schema？→ 看 schema_version 0.1 现有规则，绝不删字段
  ├─ 涉及反爬策略？→ 上抗指纹（Tier 1）和上逆向（Tier 2）按本文件 0 节心智模型选
  └─ 真不确定？→ 在 commit message 标 RFC + 写假设，**继续推进**，等用户 review

代码量超过 200 行单文件？
  └─ 拆模块；单 commit ≤ 300 行 diff（review 友好度）

引入新概念/抽象？
  └─ 默认拒绝。要加先在 PR 描述里写 "为什么现有 4-Tier 不够"
```

---

**最后**：Agent 完成所有 Task 后，把本文档的 §0 status 表更新为 ✅，并在文末加 "Implemented by `<agent-name>` on `<date>`"。
