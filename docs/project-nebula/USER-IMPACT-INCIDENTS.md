# 用户影响 Bug / 事故教训永久台账

> **目的**：把所有已经真实影响用户、可能影响用户，或曾导致发布链错误的根因沉淀为永久约束。以后修 bug、审代码、发版前都要先扫本文，避免“同类错误换个地方再犯一次”。
>
> **维护规则**：每遇到一个会影响用户体验/可用性/数据/升级的 bug，修复后必须在本文追加一条；DEV-LOG 记录过程，本文只保留可复用教训和永久门禁。

---

## 0. 每条事故必须记录什么

模板：

```markdown
### INC-YYYYMMDD-NN — 标题
- 状态：OPEN / MITIGATED / CLOSED
- 用户症状：
- 用户影响：
- 根因：
- 为什么当时没被发现：
- 修复：
- 永久门禁：
- 禁止复发规则：
- 证据/相关文件：
```

### 分级

- **P0**：大面积不可用、数据破坏、无法升级/签名断链、安全泄露。
- **P1**：核心主流程明显错误，大量搜索/更新/资源功能受影响。
- **P2**：局部功能错误、边界数据问题、有明显用户体验影响。
- **P3**：测试/运维假失败，不直接影响用户，但会导致错误决策。

---

# A. 安装、签名、更新与发布

## INC-20260601-01 — Release keystore 被 `expo prebuild --clean` 删除

- 状态：**CLOSED / 历史重大事故**
- 级别：P0
- 用户症状：旧正式版用户无法覆盖安装新版本，只能卸载重装。
- 用户影响：升级链断裂；用户数据/设置可能因卸载丢失；备案/渠道签名信息需要更新。
- 根因：旧 keystore 被放在 `android/` 生成目录，且没有可靠备份；`prebuild --clean` 删除整个目录。
- 为什么没被发现：构建前没有“上一正式 signer 对比”硬门禁，也没有把 keystore 当不可再生生产资产。
- 修复：正式 keystore 固定到 Git 跟踪的 `releases/magnetgoogo-release-new.keystore`；构建通过相对路径引用；建立加密备份/恢复链。
- 永久门禁：每个正式 APK 必须 `verify_release_apk.py --previous <previous.apk>`，证书 SHA 必须完全一致。
- 禁止复发规则：**绝不把唯一 keystore 放在 `android/`；绝不因签名文件缺失重新生成签名。**
- 相关：`APP-SIGNING.md`、`RELEASE-CHECKLIST.md`。

## INC-202607xx-02 — 更新 config 早于 APK/渠道准备

- 状态：CLOSED（流程级教训）
- 级别：P1
- 用户症状：App 能看到新版本，但下载地址尚未准备好/仍是旧文件。
- 用户影响：点击更新失败或拿到错误版本。
- 根因：把“改 config”和“上传 APK”当作同一步，缺少发布顺序门禁。
- 修复：正式流程改为 **先 final APK → K30S → R2/Aliyun/GitHub/Lanzou 全准备 → 最后切 config**。
- 永久门禁：config `latest_version` 是用户可见开关，发布渠道不齐禁止修改。
- 禁止复发规则：不允许“先发布提示，之后再补 APK”。

## INC-202607xx-03 — 蓝奏云占位/旧链接随 config 上线

- 状态：CLOSED
- 级别：P1
- 用户症状：备用下载按钮打开旧版本、无效页或占位链接。
- 根因：蓝奏云是人工渠道，自动化 config/页面生成先于真实新链接产生。
- 修复：蓝奏云上传成为 config 切换前置 Gate；全仓扫描 placeholder/旧 ID。
- 永久门禁：真实 Lanzou URL 未人工打开验证前，不部署 config。
- 禁止复发规则：禁止 `REPLACE_WITH_NEW_LINK`、旧 lanzou ID、空镜像上线。

## INC-202607xx-04 — 官网多语言页面残留旧下载链接

- 状态：CLOSED
- 级别：P1/P2
- 用户症状：不同语言页面下载到不同版本。
- 根因：静态多语言 HTML 分散，人工逐文件修改遗漏。
- 修复：统一生成脚本/镜像同步脚本，发布前全仓 grep 旧版本/R2/GitHub/Lanzou。
- 永久门禁：禁止手改 10+ 个页面；旧链接 audit 必须 0（历史文章白名单除外）。

## INC-20260730-05 — 旧客户端没有 `REQUEST_INSTALL_PACKAGES`

- 状态：CLOSED / 兼容迁移已知事实
- 级别：P1
- 用户症状：旧版点击“立即更新”无法直接从 MagGoogo 拉起 APK 安装，需要浏览器/文件管理器完成一次迁移。
- 根因：权限必须存在于**发起安装的旧 APK manifest**，新版本加权限不能追溯赋予旧 caller。
- 修复：从 0.2.3 起声明 `android.permission.REQUEST_INSTALL_PACKAGES`；后续版本走 App 内下载 + `content://` installer。
- 永久门禁：跨“首次引入安装权限”的版本升级必须做真实旧版→新版 E2E，不可只测最新包。

## INC-202608xx-06 — Optional update 下载中可被 Android Back 隐藏

- 状态：CLOSED（v0.2.6）
- 级别：P2
- 用户症状：用户按返回键后更新弹窗消失，但 APK 仍在下载；稍后系统安装器突然出现。
- 根因：下载时隐藏了“稍后”按钮，但 `Modal.onRequestClose` 仍直接调用 dismiss。
- 修复：下载中 `onRequestClose` 不允许 dismiss。
- 永久门禁：`D2B` adversarial test。
- 禁止复发规则：**所有不可中断后台操作都要同时检查可见按钮和系统 Back/手势关闭入口。**

## INC-202608xx-07 — update config 校验过弱

- 状态：CLOSED（v0.2.6）
- 级别：P1/P2
- 用户症状：错误 config 可能导致版本比较异常、错误 URL、错误强制更新判断。
- 根因：只检查字符串非空；非法 semver 可能被当 `0`，URL/numeric/timestamp 未严格验证。
- 修复：严格 semver、HTTP(S) URL、有限正数/整数、时间戳 schema 校验；authority body 校验后才接受。
- 永久门禁：`D2` adversarial + config validation tests。

## INC-20260816-08 — 同版本旧候选被误当“最终正式包已测”

- 状态：CLOSED（流程纠正）
- 级别：P3，但可导致 P1 发布错误
- 用户症状：若错误发布，最终代码变化可能从未在真机跑过。
- 根因：只看 versionName/code，相同 `0.2.6/code10` 的多个构建没有用 SHA 区分。
- 修复：final APK SHA 固定后，K30S installed `base.apk` 必须 exact SHA match。
- 永久门禁：Release Gate 明确 `local final SHA == installed SHA == archive/channel SHA`。

---

# B. 搜索与结果正确性

## INC-20260816-09 — 历史搜索/相同关键词恢复旧 completed session

- 状态：**CLOSED（v0.2.6 用户反馈）**
- 级别：P1
- 用户症状：从历史搜索词再次搜索，结果不是最新；手打同样关键词却得到不同的实时结果。
- 根因：`SearchScreen` 用 module-level session，并只根据 `query` 判断是否恢复；再次点击相同历史词命中了旧 completed session，跳过 `doSearch()`。
- 为什么没被发现：之前只覆盖“不同关键词”与普通 manual submit，没有“同 query 新搜索 intent 必须 fresh”的身份模型。
- 修复：引入 search run identity；Home 手输、历史点击、详情继续搜索、deep link 都生成/升级为新 run；仅 `same query + same run` 才可恢复。
- 永久门禁：`R3B`；K30S Debug 双 report id/startedAt；Formal same-query framebuffer freshness。
- 禁止复发规则：**业务 session identity 不能只用用户输入内容；一次用户意图必须有独立 run identity。**

## INC-202608xx-10 — 异步旧搜索结果可写回新搜索

- 状态：CLOSED
- 级别：P1
- 用户症状：切换 query 后可能混入上一轮晚到结果/状态。
- 根因：异步任务没有统一 owner/run fencing。
- 修复：新搜索 invalidate stale async start；background owner/token fence；abort/handoff identity。
- 永久门禁：`R1`、`B5`、`B9` 等 adversarial。
- 禁止复发规则：任何异步搜索结果提交前必须证明自己仍属于当前 owner/run。

## INC-202608xx-11 — 页面全局 magnet 被错误绑定到无关标题

- 状态：CLOSED（v0.2.6）
- 级别：P1
- 用户症状：结果标题看似正常，但点进去 magnet 其实属于页面另一条资源；或出现 `(brute) magnet...` 之类无意义标题。
- 根因：brute fallback 扫描整个 HTML 的 magnet，再人工合成标题，破坏“title/magnet 同条 evidence”约束。
- 修复：page-global brute 只接受 magnet 自身 `dn` 能提供可信非 hash title 的情况；正常结果必须 entry/detail 内绑定。
- 永久门禁：Tier output validation + hash placeholder gate。
- 禁止复发规则：**绝不把页面级两个独立字段凭位置猜成一条资源。**

## INC-202608xx-12 — 非法 BTIH 被当合法 magnet

- 状态：CLOSED（v0.2.6）
- 级别：P1/P2
- 用户症状：点击结果后磁力无法使用，或 hash/title 异常。
- 根因：不同 Tier/handler 各自写 regex；某些路径接受了 32 位 hex 等非标准 BTIH。
- 修复：统一 BTIH gate：仅 `40 hex` 或 `32 base32`。
- 永久门禁：`test_tier_output_validation.py`、handler tests。

## INC-202608xx-13 — malformed magnet 阻止 detail recovery

- 状态：CLOSED
- 级别：P2
- 用户症状：列表明明有可用详情页，App/爬虫却返回 0 结果。
- 根因：代码只判断 magnet 字段“非空”，即使内容非法也认为已有 magnet，于是跳过 detail follow。
- 修复：先验证 BTIH；非法等同缺失，再进入 detail recovery。
- 永久门禁：Tier0/Tier1 detail recovery test。

## INC-20260613-14 — Python handler PASS，但 App 走 generic → 用户 0 结果

- 状态：CLOSED / 永久架构教训
- 级别：P1
- 用户症状：后台/爬虫显示源健康，用户 App 搜索该源却一直 0。
- 根因：crawler_v3 按 `tier_override.platform` 走 specialized handler；App 按 `search.handler`，规则没同步路由信息。
- 修复：补 App handler/规则 `search.handler`，以后 handler 双端对齐。
- 永久门禁：源适配必须完成“Python 单源 + App/K30S 实搜”。
- 禁止复发规则：**供给侧 PASS 不能替代消费侧 PASS。**

## INC-202606xx-15 — Base32 hash 被错误截断/解析

- 状态：CLOSED
- 级别：P1
- 用户症状：dmhy/animetosho/tokyotosho 等结果 hash 变成错误长度，磁力不可用。
- 根因：hash parser 假设 hex/regex 分支不完整。
- 修复：标准 Base32→40hex authority；最终统一 BTIH validation。
- 永久门禁：Base32/hex canonicalization tests。

## INC-202608xx-16 — 结果体积/日期/Unicode 在不同 handler 出口不一致

- 状态：CLOSED
- 级别：P2
- 用户症状：显示荒谬超大体积、乱码/非法 Unicode、日期排序异常；同 hash 的大小随源响应顺序变化。
- 根因：specialized handlers 绕过 shared canonical metadata authority；冲突使用 first/max 或 arrival order。
- 修复：所有 exit path 最终 canonicalize；非法 surrogate 删除；>=1PiB 等不可能值 fail-closed；同 hash 尺寸冲突按 source consensus，多源未决冲突隐藏而不猜。
- 永久门禁：M3/M3D/M4B/M5B 等 adversarial + result-quality audit。

---

# C. 源、网络与反爬

## INC-20260509-17 — source envelope/server expiry 导致全用户锁死风险

- 状态：CLOSED
- 级别：P0/P1
- 用户症状：源包到期且续期不及时后，搜索源整体不可用。
- 根因：72h freshness 是正确安全门禁，但早期缺少足够提前的自动 renewal 与端点传播闭环。
- 修复：`mg-data` 每 8h 检查；剩余 <=32h 自动刷新为新 72h envelope；payload hash 不变；authority convergence；Aliyun hourly sync；App 前台/6h 周期刷新。
- 永久门禁：renewal state-machine 5/5 + required authority convergence + K30S consumption。
- 禁止复发规则：**安全过期机制必须自带提前续期和失败预算，不能只定义 expires_at。**

## INC-20260815-18 — 快但旧的 source mirror 抢赢新 authority

- 状态：CLOSED
- 级别：P1
- 用户症状：App 启动后继续使用旧 source pack，线上明明已发布新规则。
- 根因：mutable source 用 first-response/Promise.any race；速度比 freshness/trust 优先。
- 修复：authority/fallback 分层，**每个 endpoint 必须 fetch→decrypt→freshness→green 校验后才接受**；全部 authority 失败才进 mirrors。
- 永久门禁：P1C / stale-fast-mirror dynamic tests。
- 禁止复发规则：mutable control plane 永远 `trust + validation > fastest response`。

## INC-20260815-19 — Gateway control plane authority 全失败时 fail-open

- 状态：CLOSED
- 级别：P1
- 用户症状：上游 config 都不可用时，Gateway 可能用 `0.0.0` 等默认值继续响应，弱化版本/源门禁。
- 根因：为了“高可用”使用危险默认值，把不可确认状态当合法状态。
- 修复：config/source authority 总失败返回 502 fail-closed；Raw-first validated loader。
- 永久门禁：Gateway contract tests：Raw valid、Raw garbage→fallback、total outage→502。
- 禁止复发规则：**安全/版本 control plane 不能用宽松默认值兜底。**

## INC-202608xx-20 — 0-green 可解密 pack 覆盖健康源

- 状态：CLOSED
- 级别：P1
- 用户症状：同步“成功”但搜索突然没有源。
- 根因：旧 acceptance 只验证 crypto/freshness，没有验证业务上至少存在一个 usable green。
- 修复：remote/disk/bootstrap/debug source pack 都 `requireUsableGreenSources`。
- 永久门禁：source lifecycle adversarial。

## INC-202608xx-21 — 长时间不退出 App，内存源过期仍继续使用

- 状态：CLOSED
- 级别：P1
- 用户症状：进程活几天后可能仍用已经过期的内存规则，或者 renewal 失败后状态不一致。
- 根因：只在启动时判断 disk/envelope，内存 active set 没独立 expiry identity。
- 修复：active expiry tracking；前台 30m due refresh；active 每 6h周期；过期 + sync failed 清空 fail-closed。
- 永久门禁：P1D。

## INC-202608xx-22 — Python CookieStore 把 `expires=-1` session cookie 当过期

- 状态：CLOSED
- 级别：P1/P2
- 用户症状：需要验证/cookie 的源反复过挑战、搜索退化/失败。
- 根因：Playwright/Cloak 用 `-1`/非正数表示 session cookie；代码按 Unix 时间戳比较，立即 prune。
- 修复：非正 expiry 作为 session cookie 保留；只有正且过去的 timestamp 过期。
- 永久门禁：cookie store tests / Tier cookie integration。

## INC-202608xx-23 — App `Set-Cookie` 用逗号简单 split

- 状态：CLOSED
- 级别：P1/P2
- 用户症状：验证 cookie 缺失，部分 WAF/会话源间歇失败。
- 根因：`Expires=Wed, ...` 自带逗号；naive split 破坏 cookie。
- 修复：只在“逗号后看起来是新 cookie pair”时切分；fetch/XHR/manual 共用 parser。
- 永久门禁：N1。

## INC-202608xx-24 — WAF browser timeout 比人工验证窗口短

- 状态：CLOSED
- 级别：P1/P2
- 用户症状：用户还在过验证，后台 search executor 已超时把该源判失败。
- 根因：browser task ~10s，interactive verification 最长 ~45s。
- 修复：browser timeout 提升到能覆盖验证窗口（当前 50s），源完成后清 timeout timer。
- 永久门禁：SQ4B。

## INC-202608xx-25 — VerifyWebView challenge 状态跨请求泄漏

- 状态：CLOSED
- 级别：P2
- 用户症状：上一请求的 challenge 状态可能影响下一请求，产生假通过/错误 dismiss。
- 根因：`isCloudflareChallenge` 和延迟 timer 没按 request identity 重置/取消。
- 修复：每个 request reset；timer cancel + request-id guard。
- 永久门禁：V1。

---

# D. 资源/媒体

## INC-202608xx-26 — media current 只信第一个可达 endpoint

- 状态：CLOSED（v0.2.6）
- 级别：P1
- 用户症状：endpoint A 旧、B 新时，App 可能误判“当前没有更新”，继续展示旧影视资源。
- 根因：`remotePointerState()` 第一个成功响应就 return。
- 修复：所有有效 media endpoints `Promise.allSettled` 收集，再按 revision/一致性分类。
- 永久门禁：media security old-first/new-second case。

## INC-202608xx-27 — media detail single-flight 跨 release 复用旧 Promise

- 状态：CLOSED
- 级别：P2
- 用户症状：新媒体 release 同一个 movie_id 可能短暂显示上一 release 的详情。
- 根因：single-flight map 只用 `movie_id` 作为 key。
- 修复：key 加 content kind + movie id + remote release id + detail hash/path。
- 永久门禁：`detail_singleflight_release_scoped`。

## INC-20260803-28 — same revision 旧 Feed cache 隐藏新客户端评分映射

- 状态：CLOSED（v0.2.5）
- 级别：P1/P2
- 用户症状：线上 Catalog 已有 Rotten Tomatoes，但升级客户端后资源页仍只显示旧两项评分。
- 根因：pointer revision 未变化，客户端直接返回旧消费 cache，没重新执行新版 mapping。
- 修复：feed/detail consumer cache schema 版本化；发现旧 consumer version 时复用 raw Catalog 但重新映射。
- 永久门禁：缓存 identity 必须包含**业务消费 schema**，不能只靠远端 revision。
- 禁止复发规则：客户端解释逻辑升级时，即使 server data revision 不变，也要考虑 cache migration。

---

# E. 本地持久化与生命周期

## INC-202608xx-29 — history/favorites 快速并发写丢更新

- 状态：CLOSED（v0.2.6）
- 级别：P2
- 用户症状：快速收藏/取消、搜索历史更新时偶发丢条目/恢复旧值。
- 根因：cache-hit 返回内部数组引用；多个 async mutation 并发；启动首读与首写竞争，旧 AsyncStorage read 可覆盖新 cache。
- 修复：返回数组 copy；module serial mutation queue；初次 load single-flight。
- 永久门禁：D1B。

---

# F. 测试与运维误判（不直接影响用户，但会导致错误发布结论）

## INC-20260816-30 — Formal smoke 用 `run-as` 产生 `source cache missing` 假失败

- 状态：CLOSED / harness limitation 已记录
- 级别：P3
- 现象：`test_k30s_app_flows.py --package com.magnetgoogo.app` 报 source cache missing。
- 根因：正式 Release 是 non-debuggable，Android 正确拒绝 `run-as`；脚本把“无法读私有目录”误当“文件不存在”。
- 修复：Formal 验收改用 WindowManager/framebuffer/logcat/installed SHA；私有 cache 断言只用于 Debug。
- 永久门禁：K30S 文档明确 Debug/Formal 证据边界。

## INC-20260816-31 — Git Bash 把 `/sdcard/...` 改写成 Windows 路径

- 状态：CLOSED / 环境教训
- 级别：P3
- 现象：ADB push 的 remote path 变成 `C:/Program Files/Git/sdcard/...`。
- 根因：MSYS path conversion。
- 修复：必要时 `MSYS_NO_PATHCONV=1` 或用不做路径转换的 host shell。
- 永久门禁：遇到 `/sdcard` 路径异常先查 shell conversion，不怪 Android storage。

## INC-20260816-32 — deep link 中 `&run=` 被远端 shell 当命令分隔符

- 状态：CLOSED
- 级别：P3
- 现象：URI 后半截被当 shell command，App 未按预期路由，甚至落到 MIUI resolver。
- 根因：`adb shell` 还会进入设备 shell，URI 未整体 quote。
- 修复：`scripts/test_k30s_search.py` 用 `shlex.quote(uri)`。
- 永久门禁：任何含 `&` 的 deep link 必须整体 quote。

## INC-202608xx-33 — DevSpace 502 被误当测试/构建失败

- 状态：CLOSED / 持续注意
- 级别：P3
- 现象：长 Gradle/search 命令连接层返回 502，但设备/Java/Python 仍在运行并最终产生成功产物。
- 根因：connector transport 断开 ≠ child process exit。
- 修复：先只读检查 process/artifact/log，再决定是否重跑；保存 connector failure evidence。
- 永久门禁：**502 后禁止盲目重启同一长任务。**

## INC-202608xx-34 — UIAutomator “桌面层/idle failure” 被误当 App 状态

- 状态：MITIGATED（设备特性仍存在）
- 级别：P3
- 现象：`uiautomator dump` 返回 `could not get idle state`，或层级显示桌面而 WindowManager/截图证明 MagGoogo 前台。
- 根因：K30S MIUI Accessibility/UIAutomator 不稳定。
- 修复：正式验收用 WindowManager + framebuffer + logcat + Debug report 交叉证据。
- 永久门禁：不能为了自动化完整度伪造“实际点过某按钮”的证明。

---

# G. 当前待持续关注的潜在用户影响债务

## DEBT-01 — Gateway APK GitHub fallback 仍需始终验证

`cf-gateway/src/index.js` 当前下载主链是：

```text
R2 RELEASES object
→ missing 时 GitHub fallback
```

正式发布必须确保 R2 object 一定存在并 exact-SHA 验证，不能依赖 fallback 才“补救”主下载。

后续若修改 Gateway fallback repo/tag 逻辑，必须增加 download contract test + 实际 404/R2-missing case。

## DEBT-02 — 旧 health-check CI 与当前人工状态治理冲突

历史 `.github/workflows/health-check.yml` 仍包含 `--update` 自动写 status 的逻辑；当前 AI-RULES 明确禁止自动 status 变更。

在彻底清理该 workflow 前：

- 不把它视为 status authority；
- 不允许它自动升降级生产源；
- 任何状态变化以人工确认 + `validate_enum` 为准。

---

# H. 发版前事故回归速查

每次 App Release：

```text
[ ] signer 与 previous 完全一致
[ ] final SHA 已装 K30S
[ ] config 最后切
[ ] R2/GitHub/Aliyun/Lanzou 都准备完
[ ] 无旧链接/placeholder
[ ] App 内真实更新链已测
[ ] Android Back/权限/installer 兼容
[ ] repeat same-query fresh
[ ] history/favorites persistence
[ ] media current 多端点一致
[ ] cache schema migration 风险已考虑
[ ] source authority 不走 stale fastest race
[ ] source envelope renewal 健康
[ ] 0-green/expired pack fail-closed
[ ] crawler/App handler 一致
[ ] hash/title/size/date/unicode quality gates
[ ] Fatal/ANR=0
```

---

# I. 新事故如何进入永久门禁

一个用户影响 bug 不算“真正关闭”，除非同时完成：

```text
1. reproduce / root cause
2. code fix
3. focused regression
4. broad affected-flow test
5. permanent automated test（能自动化时）
6. K30S / production evidence（相关时）
7. 本文追加事故条目
8. DEV-LOG 记录本轮实现细节
```

如果无法自动化，必须在对应 Playbook 里增加明确人工 gate。
