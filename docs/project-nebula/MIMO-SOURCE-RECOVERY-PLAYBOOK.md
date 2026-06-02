# MiMo 磁力源批量恢复 & 爬虫工具链优化指南 (v2.5 Unlimited Token 版)

> **前言**：
> 针对当前后端请求高达 **84.2% 的全局失败率** 与 30 DAU 瓶颈，单靠拉新是“给筛子续水”。
> 必须发动 MiMo 强大的无限 Token 算力，**通过系统化的多级探测、新域名搜索、人机验证与 Cookie 穿透技术，逐个攻克/重构黄色与灰色源**。
> 每攻克一个源，都必须沉淀为 `crawler_v3` 的底层工具优化（如解析器改进、通配 Handler、WAF 探针校准），实现「打下一座城，升级一次兵器」。

---

## 一、 最有价值的事情：目标源优先级

并非所有 100+ 灰/黄源都值得恢复。MiMo 必须集中兵力攻克以下 **Top 10 高价值核心品牌**：

| 优先级 | 品牌 | 现状 | 诊断 | 为什么高价值？（对增长/留存的杠杆） |
|---|---|---|---|---|
| **1** | **磁力猫** (`clm`/`magnetcatcat`) | yellow/gray | CF Turnstile WAF | 国内用户心智 Top 1。一旦用 CookieStore/VerifyWebView 突破，将大幅提升搜索成功率。 |
| **2** | **老王磁力** (`laowang`) | yellow/gray | CF WAF / 域名过期 | 曾经的高流、高频词。需要寻找新域名并用人机验证恢复。 |
| **3** | **种子吧** (`seed8`/`zzb`) | yellow | `parsing_failed` | query 需要 Base64 编码，且详情页有 layout 变化。修复 parser 后能稳定产出中文经典资源。 |
| **4** | **SOBT / BT1207** | gray | `expired` | `thatcdn` 经典家族。一旦找到最新域名，可套用 `thatcdn` 处理器直接秒开。 |
| **5** | **BTSOW** | gray/yellow | `unreachable` | 国际站标杆，资源量巨大。通过更新最新多套备用镜像，直接提升冷门资源搜索。 |
| **6** | **无极磁链** (`0cili`) | yellow/gray | `parsing_failed` | Parser Bug：`list_item` 与 `detail_link` 使用了相同的 CSS 选择器导致提取不出。 |
| **7** | **电影天堂 / 6v电影** | gray | `expired`/`unreachable` | 泛搜索的核心。用户搜电影的首选，目前 100% 失败。极需寻找有效域名。 |
| **8** | **磁力星球** (`cilixingqiu`) | yellow/gray | CF 403 / SPA Shell | 包含 eeenav 及独立形态。若为 eeenav 需跳过，独立形态需过验证。 |
| **9** | **磁力多 / 磁力夜** | yellow | CF WAF / `parsing_failed` | 界面和 selectors 需要适配更新。 |
| **10** | **91BT** | yellow | `parsing_failed` / 屏蔽广告跳转 | 国内小众但活跃的成人/福利源，是提升 WAU/D7 留存的强力钩子。 |

---

## 二、 MiMo 五级恢复工作流 (SOP)

对于列入计划的黄色/灰色源，MiMo 必须**严格按以下五级步骤**由浅入深进行攻坚：

```
┌────────────────────────────────────────────────────────┐
│             第 1 步：域名旋转 (Domain Rotation)         │ ─── (若域名已死/404/502)
│             寻找品牌最新发布页或导航站提取外链            │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│             第 2 步：Tier 0 HTTP 快速探测              │ ─── (通过 referer/自定义 headers 恢复)
│             使用 curl_cffi 进行 Chrome TLS 模拟直接抓   │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│             第 3 步：Tier 1 Cloak 自动穿透             │ ─── (检测 CF JS 挑战并静默等待通过)
│             启动 headless CloakBrowser 提取数据         │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│             第 4 步：Tier 2 逆向 / 通用 Handler 编写   │ ─── (针对 common AJAX 验证码等)
│             识别 cookie 生成逻辑，或逆向加密参数         │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│             第 5 步：Tier 3 人机协助过盾 (CookieStore) │ ─── (终极兜底方案)
│             使用 verify-interactive / RN VerifyWebView │
└────────────────────────────────────────────────────────┘
```

### 详细步骤说明：

#### 1. 域名旋转 (Domain Rotation)
*   **适用对象**：status_detail 为 `expired` 或 `unreachable` 且探测持续失败的源。
*   **动作**：
    1.  去已知该品牌的**官方发布页**（如吴签 `wuqiandizhi.net`、熊猫 `xiongmaobt.org`、柠檬 `lemonso.net`）抓取最新旋转域名。
    2.  若无发布页，解析主流 **导航站**（如 `btmayi.cc`、`btlm.cc`、`cilishenqi.cc`）的跳转详情页，使用 base64/JS 跳转解密机制，还原该品牌最新域名。
    3.  替换 `sources.json` 中的 `site.origin`。

#### 2. Tier 0 HTTP 快速探测
*   **动作**：
    1.  配置合理的 User-Agent 与请求头。
    2.  **核心发现**：部分源（如磁力狐/阿狸搜 `cache.foxs.top`）返回 104/空，是因为缺 `Referer`。MiMo 必须尝试在 `sources.json` 规则中增加 `"search.referer"` 或特定的自定义 Headers。
    3.  配置特定的 query 编码（如 GB2312、Base64 等），测试是否可以通过 Tier 0 HTTP 直接 200 OK 拿到。

#### 3. Tier 1 Cloak 自动穿透
*   **动作**：
    1.  若 Tier 0 返回 403 或 CF/Turnstile 阻断，调用 `tier1_cloak`。
    2.  由 CloakBrowser 自动通过 Cloudflare 盾牌。
    3.  若通过，**立即捕获 `cf_clearance` 及关联 Cookie 并写回 CookieStore**，让后续请求可以直接通过 Tier 0 免渲染请求。

#### 4. Tier 2 逆向 / 编写 Handler
*   **动作**：
    1.  若网站使用了自定义的 SPA+Captcha（例如吴签/熊猫/柠檬家族的 `/recaptcha/v4/challenge`），传统的 CDP 会被识别。
    2.  编写 Tier 2 处理器，逆向其验证码验证流程，直接发送带 session 的 API 获取结果（参见 `magnet/crawler_v3/handlers/thatcdn.py`）。

#### 5. Tier 3 人机协助 (CookieStore 兜底)
*   **动作**：
    1.  若前 4 步全数失败（WAF-HARDER，如 `magnetcatcat.com`），升级至 Tier 3。
    2.  在服务端运行：`python -m magnet.crawler_v3 verify-interactive --origin <domain>`。
    3.  操作员在 headed 窗口中手动点过 CF/Turnstile，按下回车。
    4.  Cookie 捕获存入 `~/.cache/magnet/cookies/`。
    5.  利用 Cookie 结合 Tier 0 HTTP 再次搜索，验证是否通过。

---

## 三、 突破成功后的「爬虫工具链优化循环」

每当 MiMo 成功恢复一个源时，**绝不允许只改 `sources.json` 就收工**。必须触发以下优化审计：

### 1. 优化解析器 (crawler_v3.parser)
*   **问题**：由于网站改版，原有 CSS Selectors 无法匹配（导致 `parsing_failed` / `0 results`）。
*   **优化动作**：
    *   检查 `sources.json` 中的 selectors（`list_item`, `title`, `magnet`, `size`, `date`, `detail_link`）。
    *   如果目标站是无 selectors 的野站，调用或改进 `parser` 中的 **`smart list detector`**（通用智能列表提取器），让它不依赖显式 selector 也能抽取出磁力结果。
    *   更新 `sources.json` 并单 commit 提交。

### 2. 优化 HTTP 客户端与查询编码
*   **问题**：某些老旧源使用特定的 URL 编码（如 GB2312 编码的 query，或 `{query_b64}`）。
*   **优化动作**：
    *   如果需要特殊的 query 编码，在 `crawler_v3/tiers/tier0_http.py` 中确认对 `query_b64`, `query_hex`, `query_gb2312` 的支持。
    *   对 `sources.json` 对应规则进行参数对齐。

### 3. 提取通用 Handler / 扩展 Tier 2
*   **问题**：发现多个不同域名的源，其底层其实使用的是同一套后台模板（例如 `thatcdn` 或 `eeenav`、或 Bootstrap 自定义 Captcha 模板）。
*   **优化动作**：
    *   将具体的绕过逻辑，抽象成通用的 `Tier 2 Handler`。
    *   在 `sources.json` 中配置 `"tier_override": "thatcdn"`，让该品牌的其他新域名或镜像源可以瞬间复用该套代码，实现“一劳永逸”。

### 4. 优化 Cloak 检测探针 (tier1_cloak.py)
*   **问题**：遇到某些加载缓慢的源，CloakBrowser 可能会在 CF 挑战还没跑完前就超时退出，或者因为 False Positive 的 CF 强/弱探针标志提前误判。
*   **优化动作**：
    *   校准 `magnet/crawler_v3/tiers/tier1_cloak.py` 中的 `CF_STRONG_MARKERS` 与 `CF_WEAK_MARKERS`。
    *   优化 `_poll_for_results` 轮询逻辑，确保既不漏判、也不误判，并且在检测到挑战已过、页面完成渲染后，第一时间捕获 Cookie 持久化。

---

## 四、 给 MiMo 的具体任务包与单 commit 规范

为保证仓库干净，避免 MiMo “成批破坏性提交”，强制执行 **单源/单特性・单 Commit 规范**。

### 任务阶段 1：底座就位 — Phase 3 人机底座（Task K, L, M）
*   **任务 K**：实现 `CookieStore` 及其单测（`magnet/crawler_v3/cookie_store.py`）。
*   **任务 L**：将 CookieStore 读写接入 `tier0_http.py` 读、`tier1_cloak.py` 写。
*   **任务 M**：实现 `verify-interactive` 命令行。
*   *Commit 规则*：每个 Task 独立 commit。

### 任务阶段 2：逐源攻克 — High-Value 攻坚（Task O）
MiMo 必须排好队列，**一次只做一个源**。

#### A. 修复 0cili / 无极磁链 (`F.37` / `0cili.nl`)
*   **诊断**：`status_detail=parsing_failed`，真因是 `list_item` 选择器和 `detail_link` 都误配成了相同的 a 标签导致提取报错。
*   **MiMo 的动作**：
    1.  运行 `python -m magnet.crawler_v3 search -s 0cili.nl -q "test"`。
    2.  修正 `sources.json` 中的 selectors（特别是 `list_item` 指向 `div.item` 或 `tr`，而 `title`/`detail_link` 指向内部的 a 标签）。
    3.  验证通过，提交 commit：`fix(crawler_v3): restore 0cili.nl by correcting CSS selectors`

#### B. 拯救 种子吧 / zzb (`seed8.biz` / `zzb01.top`)
*   **诊断**：`status_detail=parsing_failed`，该平台 query 必须以 `base64` 编码传送，且 selector 略有更新。
*   **MiMo 的动作**：
    1.  在 `sources.json` 中确认 `request_template` 为 `/search?wd={query_b64}`。
    2.  运行 `search` 验证。若有 WAF 拦截，应用 `verify-interactive` 拿到 Cookie。
    3.  修复 selectors，提升为 GREEN。
    4.  提交 commit：`fix(crawler_v3): restore seed8.biz brand using base64 query and human verification`

#### C. 寻找并拯救 老王磁力 (`laowangzo.top` / `ilaowang06.xyz`)
*   **诊断**：域名经常失效（`unreachable`），原站有 CF 强保护。
*   **MiMo 的动作**：
    1.  在最新导航网/老王发布页（如 `laowangso.com` 等）获取最新旋转域名。
    2.  更新 `sources.json`。
    3.  用 `verify-interactive` 命令让操作员点过 CF，写入 cookie。
    4.  做一次 Tier 0 快速搜索，验证拿到结果。
    5.  提交 commit：`fix(crawler_v3): rotate laowang domain to active and pass cf via tier3`

#### D. 寻找并拯救 电影天堂 / 6v电影 (`6vdy.org` 镜像等)
*   **诊断**：100% 失败。
*   **MiMo 的动作**：
    1.  通过导航站提取真实、未死、在国内可达的电影天堂/6v镜像。
    2.  编写/微调专属详情页 parser。
    3.  提交 commit：`fix(crawler_v3): replace dead 6vdy with active working mirror`

---

## 五、 成功标准与过程监控

MiMo 每轮运行完毕，必须输出如下格式的审计汇报：

```
[MiMo 恢复报告]
攻克品牌: <BrandName> (新 origin: <origin>)
突破方式: Tier X (<method>)
Net 影响: sources.json 中 <BrandName> 成功由 <gray/yellow> -> GREEN! 
工具优化: <例如: 优化了 parser 中的 xxx, 或者在 tier0 中增加了 search.referer 支持>
回归单测: python -m pytest magnet/tests/crawler_v3 -q  ==> ✅ PASS
```
