# Project Nebula — Bug Lessons / 防再犯清单

> 目的：把已经发生过、影响用户体验或发布判断的缺陷沉淀成永久门禁。以后做 App、资源页、搜索、源测试、发布前审计时，必须先看本文件，不允许只修表象。
>
> **Analytics / 埋点专项索引：BL-018～BL-033、BL-038～BL-040、BL-042～BL-044、BL-050～BL-052。** 任何埋点采集、DAU、搜索生命周期、增长北极星、版本分布、D1/R2、历史回补、Admin 主读、容量或渠道归因改动，必须先逐条复核这一组 lessons；不能只看最近一条。SEO 发布还必须复核 BL-016、BL-017、BL-034、BL-049、BL-051。

## BL-001 — 搜索中的旧异步请求覆盖用户正在编辑的关键词

- **版本/时间**：0.2.7，2026-08-20
- **用户现象**：搜索正在执行时修改搜索框内容，输入会被旧搜索 session/snapshot 回写覆盖，用户无法正常改词重新搜索。
- **根因**：`query` 同时承担可编辑输入态和已提交搜索 session 的不可变 query；后台 snapshot/旧异步回调允许 `setQuery(oldQuery)`。
- **为什么会漏掉**：旧测试覆盖了 stale result 丢弃，但没有覆盖“请求结果不污染输入框草稿”的 UI 状态所有权。
- **永久规则**：输入草稿与已提交 query 必须解耦；旧 generation 绝不能写入新 generation 的输入/结果/loading/error/history。
- **发布门禁**：至少覆盖 A→编辑B、A→提交B、A错误晚于B成功、A完成不能关闭B loading、快速A/B/C/D、清空输入、历史词切换、unmount 后回调等竞态。

## BL-002 — Resource Tab 的成功 cooldown 阻止用户重新进入时检查新 revision

- **版本/时间**：0.2.7，2026-08-20
- **用户现象**：服务器已有新影视资源，用户离开资源页再点回来，仍显示旧内容；只有等待或手动刷新才更新。
- **根因**：`ResourceAutoSyncGate` 把“Tab focus”与“App foreground”共用 60 秒成功 cooldown；服务端若在 cooldown 内发布，新 focus 会直接跳过 `current.json` revalidate。
- **为什么会漏掉**：测试只验证了防重复请求，没有验证“重新进入页面就是明确的新鲜度检查边界”。
- **永久规则**：真正的 Resource Tab focus 必须强制轻量 pointer revalidate；foreground 可节流；in-flight 仍 single-flight。
- **发布门禁**：模拟成功同步后远端 revision 变化，在 cooldown 内重新 focus，必须发起 pointer 检查并在 revision 改变时更新 feed。

## BL-003 — 离线回退旧 cache 被误记为“本次网络刷新成功”

- **版本/时间**：0.2.7，2026-08-20
- **用户现象**：远端不可用时 App 正确显示旧缓存，但上层错误进入成功 cooldown，导致网络恢复后短时间内不重试。
- **根因**：`syncMediaFeed()` 返回 cache 的语义与“远端 current 已成功检查”混在一起；调用方只看是否有 feed，没有区分 `remoteChecked/changed`。
- **为什么会漏掉**：offline-first 的“有内容”被误当成网络层“成功”。
- **永久规则**：缓存可用性、远端检查成功、远端内容变化三种状态必须分别表达；只有真实完成远端 pointer 检查才允许启动成功 cooldown。
- **发布门禁**：网络全失败+本地 cache 存在时，UI 可展示 cache，但 refreshSucceeded 必须为 false；下一次 focus 应立即重试。

## BL-004 — K30S 网络代理前置条件未检查，造成新源大面积假阴性

- **版本/时间**：0.2.7 新源终验，2026-08-22
- **现象**：AniRena / BlueRoms / BTDig / Mikan / Snowfl / BangumiMoe / Shana 等前一天通过的源突然同时 0 结果，一度被误判为站点/API 大面积退化。
- **根因**：测试前没有确认 K30S 代理/出口条件；本轮源集合中有多站依赖代理网络，代理关闭后 exact handler 得到一致性 0 结果。
- **纠正证据**：代理恢复后首批 4/4、第二批 4/4 立即恢复；AniRena 3/3+3/3、BTDig 10/10+7/10、Mikan/Snowfl/Bangumi 30/30+30/30 等重新通过。
- **永久规则**：任何“批量源突然全 0”首先视为测试环境异常候选，不得直接修改 `health.status`；必须验证设备网络、代理出口、DNS、公共基准站，再做源级结论。
- **发布门禁**：K30S source test 开始前记录 `adb device`、公网基准可达性/代理前置检查；同批出现异常集群时先重测环境，再隔离单源。

## BL-005 — 更新下载策略测试把历史版本硬编码成 0.2.2

- **版本/时间**：0.2.7 发布门禁，2026-08-22
- **现象**：当前公开版已经 0.2.6，但 `update-download-policy-tests.mjs` 仍要求 0.2.2 链接，导致发布门禁假失败。
- **根因**：测试把发布数据复制成固定常量，而不是从当前正式 `config.json` 推导版本和下载地址。
- **为什么会漏掉**：早期发布测试只为单次版本编写，没有把“版本迭代”作为契约。
- **永久规则**：测试应校验结构和相互一致性，不应硬编码会随发版自然变化的版本号/URL；需要固定值时只固定真正不可变的域名、镜像顺序和安全策略。
- **发布门禁**：每次发版运行 update-download contract，并确认它从 `latest_version` 动态推导版本化 URL。

## BL-006 — 静态源排序过度依赖旧 benchmark，新用户无法充分利用近期真实表现

- **版本/时间**：0.2.7 发布前排序审查，2026-08-22
- **现象**：部分旧 GREEN 历史 `quality.score` 很高但近期用户侧成功率低/失败多；同时新验证池因 7 月 benchmark 无记录，在新安装用户上无法获得合理优先级。
- **根因**：运行时主排序主要是旧 K30S priors + 本机学习，`quality.score` 只在近乎同分时 tie-break；新用户没有本机学习，旧 prior 权重偏大。
- **永久规则**：排序必须同时使用：近期/静态质量、query-profile prior、本机成功/相关率学习、延迟；延迟是次级惩罚，不能让“快但低成功”压过“稍慢但高成功”；“慢且低成功/高失败”必须显著后置。
- **发布门禁**：纯函数测试必须覆盖 slow+reliable > fast+unreliable、同可靠性 fast > slow、slow+low-success 进入尾部、相关高产出 > 高量低相关；发布前用最新 V2 `source_sample` + K30S 复测校验前后排序。

## BL-007 — Resource Tab 自动更新期间无可见反馈，用户误以为仍是旧版内容

- **版本/时间**：0.2.7 正式候选真机验收，2026-08-22
- **用户现象**：进入资源页先秒开旧缓存；后台实际上会自动更新到最新 revision，但完整刷新可能持续数十秒，期间没有 toast、banner、spinner 或其他提示，用户只能看到旧内容，容易判断为“资源没更新”。
- **根因**：自动同步链 `focus -> autoSync() -> syncResourceFeed()` 没有独立 UI 状态；`refreshingKind` 只用于用户主动下拉刷新，因此后台 revalidate 从开始到结束对用户完全不可见。
- **为什么会漏掉**：此前门禁只验证“会不会自动刷新”和“缓存/远端状态是否正确”，没有验证慢网络条件下的用户可感知状态；技术成功被误当成完整 UX 成功。
- **永久规则**：offline-first 页面可以先展示缓存，但只要后台新鲜度检查可能超过瞬时延迟，就必须把 `checking / updated / failed` 三态显式反馈给用户；不得用旧内容静默等待几十秒。
- **发布门禁**：Resource Tab 自动同步开始必须持续显示“正在检查/更新”；只有 immutable release 真变化才显示“已更新”；远端检查失败要说明当前显示缓存；无变化时自动收起；提示不得与复制 toast 重叠。

## BL-008 — 异常 size 单位只修展示层会继续污染搜索排序

- **版本/时间**：0.2.7 最终真机终验，2026-08-22
- **用户现象**：Avatar 搜索结果出现 `4861400881.14 MB` 这类明显不可信的体积显示；数字本身约等于 4.5 GiB 的字节数，但上游错误附带了 `MB`。
- **根因**：结构化源可能把 raw bytes 与单位字段混用；同时 App 内曾存在多套独立 size parser（卡片展示、搜索累加器、去重排序），即使只把 UI 文案纠正，旧 parser 仍会把该条目当成数 PiB 资源参与排序。
- **为什么会漏掉**：此前 size 测试只覆盖正常 `GiB/MiB/bytes` 格式，没有覆盖“数值合理但单位不可信”的脏数据，也没有验证所有排序路径共用同一解析语义。
- **永久规则**：外部 size 永远视为不可信输入；异常量级必须在共享 parser 层防御性归一化，展示、累加器、去重、排序必须使用同一实现，不允许复制第二套单位换算。
- **发布门禁**：必须覆盖错误单位恢复、恢复后的显示、直接 `parseSizeBytes(raw)`、累加器排序和 dedup 排序；类似 `4861400881.14 MB` 不得显示为 PB 级，也不得因伪大体积被顶到正常 8GB 资源之前。

## BL-009 — `REPACK` 等宽泛关键词会把电影压制包误判成游戏

- **版本/时间**：0.2.7 最终真机终验，2026-08-22
- **用户现象**：`Inception 2010 REPACK 1080p BluRay...` 搜索结果被标成“游戏”，虽然标题和磁力内容本身正确。
- **根因**：`guessKind()` 把通用词 `REPACK` 直接作为游戏强特征；但影视重封装/重发包同样大量使用 REPACK。
- **为什么会漏掉**：分类测试覆盖了明确游戏、软件、电影关键词，却没有覆盖跨领域共享词的反例。
- **永久规则**：内容类型启发式必须优先使用高特异性组合，不得用跨领域常见词单独决定类型；`REPACK` 只有与 FitGirl/DODI/明确游戏平台等上下文共现时才可强化游戏判断。
- **发布门禁**：每个新增分类关键词至少增加一条正例和一条跨领域反例；电影 `year + quality + repack` 必须仍为电影，明确游戏 repack 必须仍为游戏。

## BL-010 — 最终 Release 构建不能依赖 Gradle 默认值或上一轮 shell 环境

- **版本/时间**：0.2.7 RC2/RC3 构建，2026-08-22
- **现象**：一次 Release 构建虽然成功，但未显式带 `arm64-only + R8 + shrinkResources` 的完整正式参数，APK 体积回到约 38.5MB；另一次新 shell 未继承正式签名环境，被 fail-closed 签名门禁拦截。
- **根因**：把“上一次构建环境/Gradle 默认属性”误当成稳定发布配置，没有把最终发行参数作为不可变单命令契约。
- **为什么会漏掉**：构建成功被误等同于“正式发行字节正确”，没有先比较 ABI、R8/shrink、签名、Hermes、bootstrap 与历史正式候选的完整指纹。
- **永久规则**：正式 APK 必须由固定发布命令显式传入 `reactNativeArchitectures=arm64-v8a`、`android.enableMinifyInReleaseBuilds=true`、`android.enableShrinkResourcesInReleaseBuilds=true` 并加载备案签名环境；任何参数缺失的成功构建都只能算诊断包。
- **发布门禁**：每次最终构建后逐项核对 package/version、ABI、备案证书 MD5/SHA256、Hermes magic、R8/shrink 日志、source bootstrap 计数、APK size/SHA256；任一不符即废弃该字节并重构建。

## BL-011 — 搜索结果日期值正确但格式混用，仍会被用户视为数据不可靠

- **版本/时间**：0.2.7 RC3 真机元数据审计，2026-08-22
- **用户现象**：同一搜索列表同时出现 `2024-09-24`、`4-21-2023`、`9-21-2020` 等日期格式；日期值本身可解析，但视觉上像不同源的日期规则不一致。
- **根因**：`cleanDateLabel()` 对 ISO 日期原样返回，对 `M-D-YYYY`/`M/D/YYYY` 也原样返回，只做“能否提取”而没有做统一展示归一化。
- **为什么会漏掉**：此前门禁关注日期字段是否误混 seeders/fileCount、是否是合法日期，没有把“格式一致性”视为用户可见数据质量的一部分。
- **永久规则**：所有可解析的数值日期在卡片层统一输出 `YYYY-MM-DD`；纯数字、纯时间、非法月/日继续拒绝，不允许为了统一格式把脏值强行显示。
- **发布门禁**：覆盖 `YYYY/M/D`、`M-D-YYYY`、`M/D/YYYY`、纯数字、纯时间和非法日期；同一列表最终只允许一种数值日期展示格式。

## BL-012 — 只按字面 exact relevance 排序，会让语义无关内容压过真正目标内容

- **版本/时间**：0.2.7 RC3 真机元数据/相关性审计，2026-08-22
- **用户现象**：搜索 `One Piece` 时 AI 图集/成人同人占据前排；搜索 `The Office` 时标题里只是包含“in the office”的成人视频压过真正剧集。它们字面完整命中查询，因此旧算法都给 100 分。
- **根因**：搜索页默认相关性排序只比较 `relevance` 数值；100 分同分时完全沿用到达顺序，没有区分“明确电影/剧集/动漫/软件语义类型”和“仅由扩展名推断的视频/其他”。
- **为什么会漏掉**：此前测试验证了高相关 > 低相关，但没有覆盖“多个结果都 exact=100、语义可信度不同”的真实冲突。
- **永久规则**：字面 relevance 始终是第一排序键；只有 relevance 完全相同才允许类型可信度作为 tie-break。明确语义类型优先于通用格式类型，通用格式优先于 `other`，不得用类型分把低相关结果抬过高相关结果。
- **发布门禁**：至少覆盖《The Office》剧集 vs “in the office”普通视频、One Piece 动漫 vs 泛内容；同时断言 relevance 差异存在时仍严格以 relevance 为先。

## BL-013 — 搜索相关性同分不能按内容类别做价值排序

- **版本/时间**：0.2.7 RC4 真机终验，2026-08-25
- **用户现象**：为修复 `One Piece` / `The Office` 的语义误排，曾加入“明确动漫/剧集等类型 > 通用视频/other”的同分 tie-break；这会间接把成人/泛视频内容后置，不符合 Full 版作为中立搜索工具、以用户查询本身为主的产品目标。
- **根因**：把“内容类型识别可信度”错误地混入“用户相关性价值判断”；类型标签可以用于展示，但不能替用户决定某类内容更值得排前。
- **为什么会漏掉**：此前只从典型影视查询的首屏体验评估排序，没有用成人/通用视频作为反例验证排序的类别中立性。
- **永久规则**：Full 版默认排序不得因 adult/anime/movie/software/video/other 等内容类别本身加分或扣分。relevance 同分时只能使用类别中立信号，如查询词在标题中的位置、完整度/紧凑度、源可靠性与本机学习；Compliance build 的过滤是独立构建策略，不能泄漏到 Full 版排序。
- **发布门禁**：必须包含“查询作为标题主体 > 句中偶然出现”的正例，同时包含成人标题以查询词开头的反例，证明其不会因为类别被降权；Full Release 必须确认 `COMPLIANCE_MODE=false` 且不存在 kind-based result filter/rank。

## BL-014 — 内容分类正则必须防止校验码误撞并覆盖季范围/发布组变体

- **版本/时间**：0.2.7 RC4 真机终验，2026-08-25
- **用户现象**：`[SubsPlease] One Piece - 1076 (1080p)[1DC31210].mkv` 被误标为电影；`The Office [S01-09] ...` 整季包也被误标为电影。
- **根因**：JAV 编号正则缺少字母数字边界，CRC/校验码中的 `DC31210` 可被截断命中；动漫发布组列表漏掉 SubsPlease；TV 规则只覆盖 `S01E01`/`Season N`，漏掉 `S01-09` 范围写法。
- **为什么会漏掉**：分类单测只覆盖标准命名，没有把 release-group + CRC、整季范围、混合语言标题当成对抗输入。
- **永久规则**：编号类正则必须有完整 token 边界，禁止从更长 hash/CRC/文件校验串中截取命中；高可信发布组和常见季范围语法要作为独立强特征；分类规则新增时必须配至少一个“相似但不应命中”的反例。
- **发布门禁**：SubsPlease+CRC 必须为 anime，`[S01-09]` 必须为 tv，标准 `ABP-123` 仍保持既有分类；同时保留 REPACK 跨领域反例。

## BL-015 — 单季缩写 `S05` 也属于高置信 TV 语法，不能只覆盖 `S01E01` / Season N

- **版本/时间**：0.2.7 RC5 真机终验，2026-08-25
- **用户现象**：`Breaking Bad S01` / `S02` / `S03` / `S04` / `S05` 在搜索结果卡片中显示为“其他”，虽然明显是电视剧单季包。
- **根因**：TV 分类只覆盖 `S01E01`、`S01-S09`、`Season N` 等写法，漏掉了独立的、带前导零的单季 token `S01…S09`。
- **为什么会漏掉**：此前对抗样本集中在单集与整季范围，没有覆盖“标题主体 + 单季缩写”的真实发布命名。
- **永久规则**：高置信 season token 必须覆盖独立 `S0N` 形式；扩展规则时要同时提供硬件/型号反例，避免把 `Galaxy S24` 等产品名当电视剧。
- **发布门禁**：`Breaking Bad S05` 必须为 tv；`Samsung Galaxy S24 Ultra` 必须不是 tv；原有 `S01E01`、`S01-S09`、`Season N` 规则继续通过。

## BL-016 — IndexNow 必须按主机独立验证，批量推送只能以 canonical sitemap 为权威

- **版本/时间**：SEO Growth Phase 2 生产收口，2026-08-26
- **用户/运营现象**：`naoshiquan.com` 的 key 文件公网 `200` 且内容精确匹配，但复用 `magnetgoogo.com` 已在使用的 IndexNow key 时，单 URL 与 175 URL 批量提交均返回 `403 UserForbiddedToAccessSite`；同时旧 `all` 模式通过遍历全部 HTML 构造 URL，存在把历史/noindex/非 canonical 页面重新提交给搜索引擎的风险。
- **根因**：①两个不同主机共享同一 IndexNow key，搜索端对该 key 的主机验证/缓存未接受第二主机；②推送脚本把“磁盘上存在的 HTML”错误当成“允许索引的 URL”，绕开了 sitemap/canonical 单一权威。
- **为什么会漏掉**：此前只验证 key 文件可公开访问和一次历史推送成功，没有做“每个主机独立单 URL 验证”；也没有给 `all` 模式增加 sitemap 等价性门禁。
- **永久规则**：每个主机使用独立 IndexNow key；发布后先验证 `{host}/{key}.txt = 200 + exact body`，再提交单 URL，只有得到 `200/202` 才允许批量提交。批量 URL 集合必须直接读取该主机 canonical `sitemap.xml`，禁止递归扫描 HTML 文件系统生成。
- **发布门禁**：IndexNow 前必须断言 sitemap URL 数量=unique 数量；单 URL 提交 `200/202`；正式批量提交 `200/202`。任何 `403/422` 均视为发布收口未完成，必须定位后重试，不能仅打印“完成”。

## BL-017 — 搜索引擎提交脚本必须用退出码表达 HTTP 失败，不能只打印错误

- **版本/时间**：SEO Growth Phase2 独立终审，2026-08-26
- **用户/发布风险**：本次 Magnet 214 URL 与 naoshiquan 175 URL 的 IndexNow 实际响应均为 `200`，所以当前发布结果有效；但独立审计发现两个 `indexnow-push.js` 在未来遇到 `403/422/5xx` 时主要只打印 `✗`，未可靠设置非零退出码，批处理/CI 可能把搜索引擎提交失败误判为命令成功。
- **根因**：脚本最初以人工控制台观察为主，成功/失败语义停留在日志文本，没有把 HTTP 接受状态提升为进程级发布门禁。
- **为什么会漏掉**：BL-016 已规定“任何 403/422 均视为发布收口未完成”，但上一轮只验证了真实 200/202 与 key/sitemap 权威，没有继续对脚本自身做 fail-closed 退出码对抗检查。
- **永久规则**：所有 IndexNow/站长提交工具必须把 `200/202` 之外的 HTTP 状态、网络异常、批次部分失败聚合成非零退出码；不能在任何失败后仍打印成功语义“完成”。测试应使用 mock/本地 stub 验证 `200/202 -> exit 0`、`403/422/5xx/network error -> exit != 0`，避免为了测试重复向真实搜索引擎提交。
- **当前裁决**：`CLOSED`（2026-08-30）。`indexnow-push.js` 已改为 fail-closed，并新增本地 HTTP 对抗测试：`200/202 -> exit 0`，`403/422/500 -> exit != 0`；最终生产 sitemap 214 个 URL 在 canonical 收敛后重新真实提交，IndexNow 返回 HTTP 200。

## BL-018 — 同类刷新并发应 single-flight join，不能把“已有刷新”暴露成 HTTP 409

- **版本/时间**：运营后台 Analytics，2026-08-29
- **用户现象**：在“数据分析”点击“拉取最新”时直接提示 `刷新失败: HTTP 409`。尤其后台刚启动约10秒、或恰逢20分钟自动刷新周期时更容易出现。
- **根因**：`refreshAnalyticsCache()` 用布尔 `cacheFetchingNow` 做互斥；自动刷新占锁期间，手动刷新带 `throwOnError:true` 会把“已有相同刷新正在进行”转换成 `409 Analytics refresh already in progress`。这是同一资源的可合并请求，却被错误建模成业务冲突。
- **为什么会漏掉**：之前 fail-closed 门禁重点验证上游401/500/坏JSON不能伪成功，但没有覆盖“后台自动刷新与用户手动刷新重叠”的正常并发；浏览器门禁也只验证单次按钮点击，没有主动构造重复调用/跨请求重叠。
- **永久规则**：读取/刷新同一 Analytics 快照必须使用 Promise single-flight：同一时刻最多1个上游 fetch，后来的自动/手动/多Tab请求 join 同一个 Promise。非严格后台调用失败可保留 last-known-good；任何 `throwOnError:true` 的用户刷新即使是 join，也必须收到真实上游错误，不能拿旧缓存伪报成功。
- **发布门禁**：函数级测试必须验证两并发调用只产生1次上游 fetch；真实 HTTP 同时 POST 两次 `/api/events/refresh` 必须两个都200且第二个 `_refreshJoined=true`；浏览器重复调用强制刷新只允许1个 POST；上游失败时 joined strict caller 必须得到原始503/502而非200或409。

## BL-019 — 本地Admin启动器不能继承通用 `PORT`，否则会“重启失败但旧页面仍可用”

- **版本/时间**：运营后台启动收口，2026-08-29
- **用户/运维现象**：代码已修复并尝试重启后，3800仍返回旧响应契约；进一步前台启动发现当前DevSpace环境带`PORT=17676`，`start-admin.bat`继承后让Admin去抢DevSpace端口并被单实例门禁拒绝。结果是新进程没有起来，浏览器继续连接旧3800实例，造成“代码修了但现象还在”的错觉。
- **根因**：桌面启动器把通用环境变量`PORT`当成自己的配置来源；而该变量常被DevSpace、其它Node服务、IDE任务复用，语义并不属于Admin。
- **为什么会漏掉**：此前单实例测试只验证`server.js`自身的EADDRINUSE行为，没有覆盖真实`start-admin.bat`在污染环境变量下的启动契约。
- **永久规则**：本地桌面启动器只接受专用`ADMIN_PORT`，默认3800，并在启动Node前显式`set PORT=%ADMIN_PORT%`；通用`PORT`只允许直接运行`node server.js`的测试/临时进程使用。
- **发布门禁**：control-plane测试静态断言`start-admin.bat`包含`ADMIN_PORT=3800`默认值和`PORT=%ADMIN_PORT%`映射；真实收尾若发现响应契约不像当前代码，必须核对3800 PID/父进程并确认确实由当前项目启动器产生，不能仅凭HTTP 200判断重启成功。
- **2026-08-30 再犯补充**：本轮出现“HTML 模板已是最新、但3800 Node进程仍是旧后端”的混合版本：页面已有 DSSU/`?` 文案，接口却仍把8/27～8/29标verified且无 northStar。真实浏览器对**后端新字段/新状态**的断言才抓到。以后重启门禁必须至少检查一个只可能来自新后端的契约字段/状态，不能用最新HTML token证明整个Admin已更新。

## BL-020 — 原始R2对象库不能直接承担日活查询；任何不完整读取都不得推进同步watermark

- **版本/时间**：Analytics历史DAU故障，2026-08-29
- **用户现象**：运营后台每日活跃反复出现`100+ → 4/7/15 → 100+`，且点击“拉取最新”后历史低谷长期不恢复。
- **根因**：旧架构把`1 batch = 1 R2 object`的原始事实库存储模型直接当运营查询模型；Gateway在单Worker请求里对大日分区逐object读取并受subrequest/CPU限制，Admin又把不完整结果视为完整并推进`lastFetchedAt`，之后只回拉最近1~2天，形成永久假低谷。
- **为什么会漏掉**：原测试只覆盖小规模/当前日与HTTP成功，没有制造1000+/5000+ object日，也没有把“完整性证明”作为缓存提交条件；因此HTTP 200被错误等价为“数据完整”。
- **永久规则**：R2只作为不可变raw事实库/灾备；运营DAU必须来自可索引聚合层。任何历史同步只有在remote inventory与本地`count + fingerprint`验证一致后才能提交正式cache/watermark；未验证日期必须显示`数据不完整`，不能绘成0。
- **发布门禁**：必须保留>1200 object分区恢复对抗测试；真实生产大分区必须使用cursor inventory/data page；正式cache切换必须断言`_inventoryVerified=true`和完整日期数。

## BL-021 — 辅助去重/索引组件故障不能阻断原始Telemetry耐久写入

- **版本/时间**：Analytics ingestion生产故障，2026-08-29
- **用户/数据风险**：生产Worker tail出现`KV put() limit exceeded for the day`；旧方案为每个event写KV dedupe，配额耗尽时可能让整批埋点500，更旧顺序还可能出现“dedupe成功但R2失败”导致重试永久丢事件。
- **根因**：把辅助KV dedupe当成采集成功路径的一部分，且其写放大远高于业务需要；辅助系统的低配额反向成为原始事实库的可用性单点。
- **永久规则**：Analytics采集成功边界必须是R2 durable write；KV/D1/其它索引全部是可重建辅助层。辅助索引失败不得把已成功的R2写变成App可见5xx。跨batch幂等由event_id在下游索引/聚合层处理。
- **发布门禁**：源码契约必须断言`R2 put`发生在D1 shadow之前，D1通过`waitUntil`异步执行且错误被隔离；Analytics热路径禁止per-event KV write。生产故障对抗必须验证D1不可用时R2成功仍返回成功、R2失败时绝不能由D1伪成功。

## BL-022 — D1 migration 不能依赖多语句 Trigger body；本地 SQLite PASS 不等于 Wrangler remote 可执行

- **版本/时间**：Analytics D1 迁移，2026-08-30
- **现象**：`wrangler d1 migrations apply --remote` 对首版 migration 报 `incomplete input`；远端已部分创建表，但 migration 未记入 `d1_migrations`，trigger 也未建立。
- **根因**：本地 `sqlite3.executescript()` 能完整解析 `CREATE TRIGGER ... BEGIN ...; ... END`，Wrangler/D1 migration 的 statement splitting 对该结构产生了截断。
- **为什么会漏掉**：旧门禁只验证本地 SQLite 语义，没有验证 remote migration parser，也没有检查失败后的“部分 schema”状态。
- **永久规则**：D1 核心 rollup migration 保持 trigger-free；显式幂等写入/聚合优先。remote apply 后必须同时检查 `d1_migrations`、表/索引清单与 `PRAGMA quick_check`。
- **发布门禁**：migration 必须可本地重复执行；生产 remote apply 必须 `✅`，且 `quick_check=ok` 后才允许 Worker 切入新 binding。

## BL-023 — `installation_time > 0` 不是合法 epoch-ms 校验，uptime-like 值会污染到 1970 年

- **版本/时间**：Analytics V2 / D1 backfill review，2026-08-30
- **现象**：真实缓存中出现 `installation_time=2580891395`；旧逻辑会把它当 Unix 毫秒时间并计入 1970 年物理安装。
- **根因**：只校验“正数且不晚于 first_open”，没有 epoch 下界；设备运行时长/其它毫秒值也满足该条件。
- **永久规则**：物理安装时间统一要求 `>= 2000-01-01 UTC` 且 `<= first_open.ts + 5min`；Admin、Gateway shadow、历史 backfill 三处必须同口径。
- **发布门禁**：永久保留真实 uptime-like 反例，必须从 physical install 中排除；正常 epoch-ms 样本继续计数。

## BL-024 — Legacy `daily.devices` 不能冒充跨版本真实 DAU；经营主口径必须有明确 read-model authority

- **版本/时间**：Analytics DAU 主读迁移，2026-08-30
- **用户/运营风险**：R2 回补后旧顶层图曾得到 8/20=98、8/21=105，容易被误认为“真实 DAU 已修复”；独立对账后发现正确跨版本 DAU 分别为 216、224。
- **根因**：旧 `daily.devices` 是 Legacy 兼容图口径，而 Analytics V2 `executive.daily.activeDevices` 使用 `legacy_did/device_id/did` 跨版本桥接；两个口径含义不同。
- **永久规则**：经营总览/每日 DAU 的唯一主口径是 D1 `ops_daily.active_devices`，并必须独立等价于 verified R2 的 `executive.daily.activeDevices`；Legacy 图只能留在 Legacy 子页。
- **发布门禁**：Admin 页面必须显示 `DAU source = D1 exact operational index / raw audit = R2`；D1 与独立 R2 聚合逐日对账；partial/unknown 日不得进入已验证折线。

## BL-025 — 物理安装身份是全局 `install_id`，不能用 `(install_day, install_id)` 作为唯一性边界

- **版本/时间**：Analytics D1 独立终审，2026-08-30
- **潜在风险**：同一 install_id 若跨批次携带不同但合法的 `installation_time` 日期，复合主键 `(install_day,install_key)` 会允许同一物理安装被计到多个日期。
- **为什么此前没触发**：当前 verified R2 的 609 个真实 install_id 中 `multi-day=0`，所以现网数据尚未污染；5000 DAU happy-path 也未制造跨日冲突。
- **永久规则**：`install_id` 全局唯一，冲突时保留最早合法 `installation_time` 并移动计数日；D1 通过 `idx_ops_install_days_install_key UNIQUE` 封死跨日重复。
- **发布门禁**：0002 migration 后必须验证 `COUNT(*) = COUNT(DISTINCT install_key)`；对抗测试必须制造“先晚后早”的同 install_id，最终只在最早日计 1 次。

## BL-026 — Windows 下不要把整条 Wrangler 命令作为 `cmd /c` 单字符串；大规模 backfill 必须支持 chunk 原子重试

- **版本/时间**：Analytics D1 backfill 运维，2026-08-30
- **现象**：Windows Node 24 下单字符串 `cmd /s /c` 会把 `--file` 路径变成双引号字面量；修正后长序列子进程又偶发 `UV_HANDLE_CLOSING` / `3221226505`。
- **根因**：Windows cmd 参数转义与 Node/npx 子进程稳定性叠加；旧脚本把一次子进程失败视为整个 16-chunk backfill 永久失败。
- **永久规则**：Windows 必须向 `cmd /d /c` 传分离参数 `npx, ...args`，不得拼接用户/路径字符串；每个 SQL chunk 必须事务原子、全流程幂等，并对进程级瞬时失败做有上限重试。
- **发布门禁**：不仅 dry-run，必须至少一次真实 `--apply` 16/16 完成；最后一个 chunk 才允许写 `backfill_complete`，随后必须远端 `quick_check=ok`。

## BL-027 — `backfill_complete` 只证明历史快照，不能证明后续 D1 shadow 持续完整

- **版本/时间**：Analytics D1 运营主读二次审查，2026-08-30
- **用户/运营风险**：R2 已成功耐久写入后，D1 shadow 在 `ctx.waitUntil` 内若因配额/瞬时故障失败，App 返回 200 是正确的；但若后台仅检查历史 `backfill_complete=true`，就可能继续把缺少部分实时事件的 D1 标成 verified，再次形成“服务正常但运营数据静默偏低”。
- **根因**：把“一次历史 backfill 完成”错误等价为“此后增量索引始终完整”，缺少从 R2 事实层到 D1 read model 的持续完整性状态。
- **为什么会漏掉**：此前故障门禁只验证“D1 失败不能影响 R2/App 成功边界”，没有同时验证“辅助层失败必须撤销运营数据可信标记”。
- **永久规则**：D1 仍是可重建 shadow，但任何 shadow 写失败在有界重试后必须把 unresolved marker 耐久写入 R2；`ops_daily` 每次读取都要结合该 marker 与最新 verified backfill 时间判断 `operational_verified`。存在未修复 marker 或完整性检查失败时，Admin 必须把 D1 全部降级为 partial/观测值，不得继续显示 verified。
- **发布门禁**：必须永久保留 `D1 fail + R2 success => App 200 + R2 failure marker`、`unresolved marker => operational_verified=false`、`verified rebuild newer than marker => 可恢复`、marker 写入自身有界重试等故障对抗。

## BL-028 — App 版本分布不能按 batch 数统计，必须按活跃设备的最新观测版本去重

- **版本/时间**：运营后台版本分布，2026-08-30
- **用户/运营风险**：高频使用设备会产生更多 batch；若按 batch 的 `app_v` 统计，重度用户会被重复放大，版本渗透率会直接误导升级策略。
- **根因**：旧 Legacy “版本分布”复用了原始 batch 聚合，没有为“一个设备在窗口内属于哪个版本”建立独立身份 read model。
- **永久规则**：经营总览版本分布使用 D1 `ops_device_latest`，按跨版本匿名 `device_key` 全局一设备一行；最近31个 UTC+8 运营日内，每台设备只按最后一次**服务端接收**的 `app_v/version_code` 计1次。Legacy batch 版本图只能留在 Legacy 兼容区，不能作为运营主口径。
- **发布门禁**：版本升级必须“移动”设备而不是增加总设备；同设备重复 batch 不增加版本人数；乱序较旧 batch 不得把版本回退；查询必须命中 `last_seen_day` 索引且不扫描 R2 raw objects；UI 明确标注“活跃设备”而非“批次”。

## BL-029 — 5000 DAU 容量门禁必须验证 D1 写放大和乱序状态，不只是最终 DAU 数字

- **版本/时间**：Analytics 5000+ DAU 二次容量审查，2026-08-30
- **潜在风险**：`5000 devices -> DAU=5000` 即使正确，若每个设备一天产生几十批、每批都无条件 UPDATE D1，同样可能把辅助索引写配额/吞吐打满；一旦 shadow 故障又缺少完整性门禁，就会重演静默低估。
- **根因**：首版容量测试主要验证基数幂等，没有把“真实 raw batch 数 × 每批数据库写入”作为容量维度；latest-version 更新也曾在测试中暴露同日乱序旧 batch 回退版本的边界。
- **永久规则**：同一 device-day 的无状态变化 batch 必须是真正 SQL no-op；`ops_daily` 只在首次设备/flag 状态转换时更新，`ops_device_days` 只在状态变化时写，`ops_device_latest` 只在新运营日或同日更晚且元数据变化时写。容量判断必须同时覆盖 cardinality、write amplification、故障降级和重建能力。
- **发布门禁**：固定保留 `5000 devices × 25 batches = 125,000 raw batches/day` 对抗；其中后续120,000个同日无状态变化 device 更新的 SQLite `total_changes` 必须为0；同设备100次 replay DAU不增；较旧同日版本事件不能回退 latest version；31日查询复杂度不得随 R2 object 数增长。

## BL-030 — Verified repair checkpoint 是灾备/回补证据，成功 promotion 后不能整目录删除

- **版本/时间**：Analytics 最终收口复审，2026-08-30
- **潜在风险**：`refreshAnalyticsCache()` 成功完成 R2 inventory 验证并正式 promotion 后，旧代码直接 `rm -rf repair-partitions`。这样虽然正式 `batches.json` 已可用，但刚刚取得的 verified 分区证据被销毁；后续 D1 rebuild、当前日 catch-up、审计复核若需要精确分区，只能重新扫描远端 R2，增加恢复成本和窗口漂移风险。
- **为什么会漏掉**：早期 checkpoint 被当成“临时下载缓存”，没有把它视为“count + fingerprint 验证后的灾备证据”；测试只断言正式 cache 成功，没有断言成功 promotion 后 checkpoint 仍存在。
- **永久规则**：verified repair checkpoint 属于当前 31-day inventory window 的恢复证据，promotion 后必须保留；只允许清理窗口外 checkpoint。旧 checkpoint 即使远端分区已变化也不能误用，加载时继续用 `count + fingerprint` 与当前 inventory 严格匹配，失配则忽略而非覆盖。
- **发布门禁**：1205-object partition recovery 测试必须断言目标日 checkpoint 在成功 refresh 后仍存在，并同时断言窗口外 stale checkpoint 被清理；D1 backfill/catch-up 只能消费 verified cache 或经过严格验证的 retained checkpoint。

## BL-031 — `search_completed` 是全量源流程终态，不是搜索成功/满意终态

- **版本/时间**：增长北极星重构，2026-08-30
- **运营风险**：旧后台把 `submitted → completed` 配对率当搜索健康指标，容易把用户“前几个源已找到结果并 copy/open，随后离开或重搜”的正常成功行为误判成失败，进而诱导错误产品优化：让用户等待全部源跑完。
- **生产证据**：D1 历史审计约 19,948 个 Satisfied Search（search_id 关联 Magnet Action）中，约 7,438 个没有 `search_completed`，即约37%的满意搜索在全量源完成前就已产生核心价值；当前生产快照同样约 19,917 satisfied / 7,399 satisfied-without-completion。
- **根因**：技术生命周期事件与用户价值终态混为一谈。`search_completed` 的语义是全量源任务终态，而不是“用户第一次拿到可用结果”或“用户满意”。
- **永久规则**：增长/产品主指标使用 DSSU、Satisfied Search、Magnet Action、TTFR/首可用结果；`search_completed` 只能作为全量源流程完整度和埋点生命周期诊断。不得以提高 completed 率为目标迫使用户等待剩余源。
- **发布门禁**：D1/Admin 必须保留 `satisfied_without_completion`；后台固定显示“全量源跑完率（非成功率）”；数据质量不得因低 completed 配对率直接报警为产品失败；对抗测试必须覆盖 action-before-completed 和永不 completed 但已 satisfied 的 search_id。

## BL-032 — R2 storage-verified 不等于端到端 ingestion-complete

- **版本/时间**：8/25后历史完整性复审，2026-08-30
- **运营风险**：R2 inventory/count/fingerprint 全部吻合，只能证明“已经进入 R2 的对象读全了”。旧采集入口若在 R2 durable write 之前因 KV quota、429/5xx 或客户端未成功上传而丢事件，服务器无法从 R2 反推出从未到达的用户。
- **具体影响**：2026-08-26～2026-08-29 均处在旧采集链/切换窗口，不能作为可靠增长趋势日期；8/26有明确 ingestion KV 事故，8/27～8/29虽可 storage-verify，但不能证明 end-to-end ingestion complete。
- **永久规则**：历史运营日只有同时能证明采集成功边界和读模型完整性时才能标 `verified`。storage repair 可以恢复少读，不能把“从未进入事实库”的事件补回来；无法证明时必须 `partial`，数值只作为下限观测。
- **发布门禁**：真实3800浏览器固定断言8/26～8/29为 partial；任何北极星/SEO前后窗口只消费 verified 日期；partial/unknown 永远不得混入增长同比、环比和模型训练基线。

## BL-033 — 指标无法理解本身就是运营正确性 Bug，必须在数据旁解释口径

- **版本/时间**：运营后台可解释性收口，2026-08-30
- **用户现象**：DAU、DSSU、New DSSU、D7 Returning、TTFR、全量源跑完率、安装/首次观测等指标并列后，即使计算正确，运营人员也很难仅凭名称判断分子/分母、窗口和完整性边界。
- **根因**：只把“数字正确”当作数据产品完成，忽略指标被正确理解才是运营决策链的最后一环；尤其 `completed`、`first_open`、物理安装等技术词极易被自然语言误解。
- **永久规则**：所有非显然 Analytics/SEO/增长指标必须就地提供可点击 `?` 说明；说明要简洁，但至少明确统计对象/窗口/关键分母或“不是X”的边界。新增指标必须同步登记定义，不能只加卡片。
- **发布门禁**：Admin 当前统一自动装饰 Analytics 指标，真实3800已渲染105个可点击说明入口；静态测试检查 aria-label/弹窗调用，真实 Chromium 必须点击 DAU 说明并验证内容，同时要求 pageErrors=0、consoleErrors=0。

## BL-034 — Cloudflare Pages 会把 `.html` 永久重定向到无扩展名；增长核心 canonical 必须指向最终URL

- **版本/时间**：SEO生产收口，2026-08-30
- **用户/SEO风险**：本地页面曾自 canonical 为 `/guide/x.html`，sitemap 也提交 `.html`，但生产 Pages 实际返回 `308 /guide/x`。这会制造 sitemap/canonical 与最终可访问URL不一致，浪费抓取信号并增加搜索引擎自行选择 canonical 的不确定性。
- **发现证据**：生产实测 `cili-sousuo.html`、`cili-lianjie-sousuo.html`、`free-magnet-search.html` 均 308 到无扩展名；Cloudflare Pages 官方文档也明确 HTML 扩展名会归一化到无扩展名路径。
- **永久规则**：所有增长核心页的 canonical、og:url、sitemap loc 必须直接使用 Pages 最终无扩展名URL。历史长尾允许风险受控分批迁移，但任何新增长核心页不得新增 `.html` canonical。
- **为什么原门禁仍会漏问题**：此前 audit 只保证 canonical/sitemap 是最终 URL，却没有检查 indexable 页面里的站内 `<a href>` / hreflang 是否仍指向 `.html`。因此 canonical 可以全绿，但爬虫仍从 72 个页面经过 382 次无意义 308，继续浪费 crawl hop；`alt/index.html` 单页一度就有 147 个旧后缀链接。
- **永久规则升级**：最终 URL 治理必须覆盖 canonical、og:url、sitemap、hreflang、站内 `<a href>` 和生成器源头。静态物理文件可以继续叫 `.html`，但任何 indexable 页面输出给用户/爬虫的 same-site 页面链接必须直接使用最终无扩展名 URL。生成器不得重新写回 `.html` 内链。
- **发布门禁**：`seo-growth-audit.js` 对 mustTrack URL 出现 `.html` 直接失败；`seo-audit.js` 还必须扫描全部 indexable 页面并要求 same-site `.html` href=0；本地 `urlToFile()` 支持将无扩展名 canonical 映射回物理 `.html`。生产部署后必须全量验证 sitemap 214/214 final URL=200、214/214 canonical exact、live same-site `.html` href=0，并对 125 个非目录 final URL 的 legacy `.html` 逐一验证 308 + Location 精确回 final URL，不能只做抽样。

## BL-035 — 百度普通收录 API 要按动态配额和最终 canonical 推送，token 只能进本地 `.env`

- **版本/时间**：国内 SEO 主动提交收口，2026-08-30
- **运营/安全风险**：百度普通收录 API 的站点额度不是固定常量，真实剩余额度由成功响应 `remain` 返回；重复提交旧 URL 会浪费额度并可能触发额度下调。另一方面，token 若硬编码进源码/脚本/日志会形成站长权限泄漏。Cloudflare Pages 又会把 `.html` 规范化到无扩展名，若把跳转前 URL 推给百度会再次浪费抓取信号。
- **永久规则**：`BAIDU_PUSH_TOKEN` 只允许存放 Git 忽略的根 `.env`，推送脚本运行时加载，不打印明文。API 推送优先当天新建/实质更新的高价值中文页，并且 URL 必须来自 canonical sitemap、去重且直接是最终可访问 URL；禁止为了“用完额度”重复推全站旧链接。
- **失败语义**：HTTP 非 200、`over quota`、`not_valid`、`not_same_site`、部分成功均必须非零退出码；成功后记录 `success/remain`，但不得记录 token。单次请求仍遵守百度最多 2000 URL 的接口限制。
- **发布门禁**：本地 mock 固定验证 `success -> exit 0`、`over quota / partial invalid -> exit != 0`；生产推送前先验证目标 URL HTTP 200 且在 sitemap。若执行安全层阻止携带站长凭证发起外部 POST，应保留 token 配置与可复现命令，不得绕过安全层或伪报百度已接收。
- **2026-08-30 生产证据**：token 仅存根 `.env`；第一批4个高价值最终 canonical 实际返回 `success=4 / remain=6`，第二批6个最终 canonical 实际返回 `success=6 / remain=0`。当天10个额度全部用于新建/实质更新中文强意图页，没有为“用完额度”重复提交旧URL。

## BL-036 — IndexNow 成功不等于 Google Search Console 已提交，搜索引擎提交渠道必须分别记账

- **版本/时间**：SEO 多搜索引擎提交复核，2026-08-30
- **运营风险**：IndexNow HTTP 200 可以证明 Bing/IndexNow 生态已收到通知，但不能据此声称 Google Search Console 已显式提交 sitemap。若把不同搜索引擎渠道混为一条“已推送”，会让SEO发布状态失真。
- **永久规则**：百度、Bing/IndexNow、Google Search Console 三条渠道独立记录。Bing 以 IndexNow 200/202 为成功证据；百度以 API `success/remain` 为成功证据；Google 普通页面只走 canonical sitemap + robots + Search Console sitemap，不得滥用仅适用于 JobPosting/直播 BroadcastEvent 的 Indexing API。
- **Google 自动化边界**：Search Console API 需要已授权 OAuth/服务账号且该身份对对应 Search Console property 有权限。项目/系统没有授权凭证时，允许完成公网 sitemap/robots 和Google可发现性门禁，但不得伪报“Search Console显式提交成功”。
- **发布门禁**：最终SEO报告必须分别写 `Baidu / Bing(IndexNow) / Google(Search Console)` 状态；若 Google 无授权，明确标记为“sitemap/robots已上线，Search Console显式提交待授权”，同时禁止使用已废弃 sitemap ping 接口冒充提交。

## BL-037 — Public SEO data 有 freshness 声明不等于真的新鲜；过期状态数据必须自动降级

- **版本/时间**：增长对抗终审，2026-09-01
- **现象**：`magnetgoogo-site/data/status-public.json` 声明 `freshness_hours=6`，但本轮检查时 `generated_at` 仍停在 `2026-08-26T01:03:25Z`；`/status/` 和 `/sites/*` 仍会消费该静态文件。
- **增长/品牌风险**：第一手Status/Sites原本用于建立“近期验证、可引用数据”权威；如果自动projector停摆而页面继续展示旧快照，就会把数据资产变成可信度负债，后续Report/PR还可能放大错误。
- **根因**：projector脚本有单次freshness输入门，但缺少“输出文件持续SLA”的调度/监测闭环；`write` fail-closed只能防本次写坏，不能发现任务已经数天没跑。
- **为什么会漏掉**：SEO发布门禁主要检查HTTP/canonical/indexability/download CTA，没有断言公开数据文件的`generated_at + freshness_hours`仍在SLA内。
- **永久规则**：所有public intelligence输出必须同时有 producer freshness、consumer stale展示、watchdog告警三层；超SLA时禁止使用`recent/current/verified`类措辞并冻结依赖该事实的entity/report/PR扩张。
- **发布门禁**：SEO生产审计新增public-data freshness检查；Status projector必须由独立调度稳定执行并保存last-known-good/失败状态；不能把旧数据当0或当前事实。

## BL-038 — Growth事件已经写入不等于增长归因读面可用；不可用必须显式stale而不是0

- **版本/时间**：增长对抗终审，2026-09-01
- **现象**：Admin `/api/growth?days=14` 本轮返回 `available=false / error=fetch failed / total=0`；Gateway已有`seo_download_click`写入逻辑，但运营端无法稳定获得page/placement/country归因。
- **增长风险**：如果把`total=0`自然理解成“没有SEO下载”，会直接误导CRO、SEO实验和渠道资源配置；如果只相信事件写入代码，又会错误认为归因闭环已经完成。
- **根因**：采集事实层、受保护Gateway读取、Admin代理和可用性/freshness没有作为一个完整数据产品验收。
- **永久规则**：增长数据必须区分`zero / unavailable / stale / partial / verified`；任何网络/鉴权/上游故障不得降级成真实0。增长读模型需要last-known-good、freshness和自动恢复测试。
- **发布门禁**：对`/api/growth`增加真实代理/故障/恢复门禁；CRO和Opportunity Engine在growth read不可用时必须暂停结论，不允许继续自动改页面。

## BL-039 — D7 exact-day Returning 不能单独代表工具类新用户留存；增长质量需要7日窗口复用

- **版本/时间**：增长留存视角复核，2026-09-01
- **现象**：2026-08-18～08-25健康New DSSU cohort中，第7天当天再次Magnet Action合计约5.5%，但首次后的1～7天内至少再次满意使用一次合计约38%，单cohort约25%～62%。
- **运营风险**：只看D7 exact会把episodic utility正常的非每日使用误判成“留存崩溃”，导致错误否决高质量SEO渠道；只看New DSSU又会忽略真正的一次性流量。
- **根因**：固定日留存指标与工具类非日常使用节奏不匹配。
- **永久规则**：D7 exact-day Returning保留为严格辅助指标；SEO/获客质量主阀增加`New DSSU 7-day satisfied reuse`，定义为首日已满意的新设备在第1～7天任一天再次发生Magnet Action。
- **发布门禁**：增长实验必须同时报告New Device、New DSSU、7-day satisfied reuse和D7 exact；不得用任一单指标替代完整质量判断。

## BL-040 — Exact D1 指标不等于低成本查询；免费层 row-read 配额必须成为架构门禁

- **版本/时间**：增长执行与D1成本复核，2026-09-01
- **现象**：Cloudflare从2026-09-01开始对Free D1达到每日row-read额度后直接拒绝后续查询；本项目当天真实命中`code=7500 / daily row read limit exceeded`，随后`/api/growth`与直接Wrangler查询均不可用直到00:00 UTC重置。
- **运营风险**：指标逻辑可以100% exact，但如果每20分钟通过相关子查询反复扫描历史device-day/search状态，仍可能把免费层5M rows-read打满；一旦把平台拒绝误当成0，DAU/增长判断会再次失真。
- **根因**：此前容量门禁证明了5000 devices / 125k raw batches的逻辑正确性，却没有把D1计费层“实际扫描多少row/day”纳入容量定义；north-star first-seen/reuse查询又使用了逐设备相关历史子查询，放大了读成本，手工Wrangler审计也会共同消耗账户级额度。
- **永久规则**：exact authority与serving cost必须分离审计。运营read model必须优先紧凑聚合、索引、bounded window与snapshot cache；禁止在高频接口中出现per-device correlated history scan。D1额度/平台错误必须返回stale/LKG/unavailable，不得返回真实0。
- **已落门禁**：`ops_daily` exact快照增加30分钟edge cache且缓存命中仍独立检查R2 shadow failure marker；first-observed/D7/reuse改为`firsts + windowed + join`；容量测试固定禁止相关`NOT EXISTS/EXISTS canonical`回归。Growth Daily安排在本地10:15运行，晚于UTC 00:00（UTC+8 08:00）每日额度重置。
- **后续预算门**：恢复后必须持续观察真实D1 rows-read；正常运营日应显著低于免费层上限并保留安全余量，不能把升级付费计划作为掩盖低效查询的第一修复。

## BL-041 — 自动化脚本存在不等于自动发布成立；调度必须匹配真实部署拓扑

- **版本/时间**：Public Status自动化闭环，2026-09-01
- **现象**：`magnetgoogo-site` Cloudflare Pages项目是Direct Upload（Git Provider=No），而站点目录又被根仓`.gitignore`排除；仅增加GitHub workflow/提交快照并不能证明每4小时生产站会自动更新，且当前GitHub Actions未确认具备Cloudflare deploy secrets。
- **增长风险**：如果把“workflow文件已写”误报成“freshness自动化已上线”，Status仍可能再次数天过期，重演BL-037。
- **根因**：自动化设计最初围绕Git push，而实际生产发布authority是本机Wrangler Direct Upload，调度与发布拓扑不一致。
- **永久规则**：任何自动化必须验证`trigger → process → deploy → public readback`四段真实闭环；存在脚本/cron/workflow不算完成。Direct Upload站点在没有云端deploy credential前必须使用已认证的实际发布执行域或显式标BLOCKED。
- **已落门禁**：Windows Task Scheduler已注册`MagnetGoogo-PublicStatus-4h`，真实手动触发后`LastTaskResult=0`；任务执行`probe → freshness/SEO gates → Wrangler Pages deploy → production watchdog`，运行结果写`growth-ops/runtime/public-status-last-run.json`。Growth日报独立注册`MagnetGoogo-GrowthDaily`每天10:15执行。

## BL-042 — Verified backfill 完成后不能继续被旧 edge snapshot 判成 unresolved

- **版本/时间**：Growth P0→P6 生产闭环，2026-09-02
- **现象**：31日 R2 inventory repair 已生成 `sourceCachedAt=2026-09-02T02:14:07.544Z / 103432 batches` 的 verified 快照，D1 backfill 也已写入更晚的 `backfill_complete`，但 `/api/events?mode=ops_daily` 仍返回 `operational_verified=false / unresolved_shadow_failure`。等待旧 snapshot TTL 才会自然恢复，导致 Growth KPI 和 Admin 在真实修复后仍被错误阻断最多30分钟。
- **根因**：`ops_daily` edge snapshot 把旧 `backfill` metadata 与 rows 一起缓存；cache hit 虽会重新读取 R2 failure marker，却仍用缓存中的旧 `backfill.sourceCachedAt` 判断 marker 是否已被修复，因此看不到 D1 中刚写入的更晚 verified backfill。
- **为什么会漏掉**：既有 failure contract 覆盖“marker 新于/旧于 backfill”与 fail-closed，但没有构造“cache 中旧 backfill + D1 已有更新 backfill”的恢复时序；因此只证明了判定函数正确，没有证明 cache recovery 正确。
- **永久规则**：健康 cache hit 继续零额外 D1 读取以保护 row-read 预算；只有 cached integrity 为 `unresolved_shadow_failure` 时，允许读取**一行**最新 `backfill_complete`。若最新 backfill 为31日 inventory-verified、时间晚于 cached backfill 且已经覆盖 failure marker，则必须绕过旧 snapshot 并从 D1 重算/覆盖 cache；严禁仅把旧 rows 重新贴成 verified。
- **发布门禁**：failure contract 必须固定断言“stale cached snapshot + newer repaired backfill => `snapshot_cache.hit=false`、重新计算 rows、`operational_verified=true / repaired_by_backfill`”；生产 backfill 完成后立即读取真实 Gateway，不能只等 TTL。2026-09-02 已部署 Gateway `638d9bbe-3a55-4d42-84f5-f65d43fab416`，生产验证 `operational_verified=true / shadow_healthy=true / integrity_status=repaired_by_backfill`。

## BL-043 — Full backfill 也会消耗 D1 row-write 配额；修复动作不能反过来打死实时 shadow

- **版本/时间**：Growth P0→P6 生产收口，2026-09-02
- **现象**：31日 R2 verified repair 与 Analytics D1 full backfill 成功后，生产一度恢复 `operational_verified=true`；约十几分钟后新的 R2 marker 再次把运营读面降级。新 marker 不是 cache bug，而是 `D1 free tier daily row write limit`：本轮18个全量 backfill chunks 与当天实时 shadow 共用同一个账户级日写额度，修复本身耗尽配额，随后新的 R2 durable batch 无法写入 D1 shadow。
- **为什么 BL-040 没挡住**：BL-040 主要针对 row-read 扫描成本和高频读缓存；容量测试证明 steady-state 重复 batch 可做到 write-noop，却没有把**运维 full backfill 本身的 rows_written**计入同一天预算，也没有规定修复后的剩余写额度门槛。
- **永久规则**：Free D1 下，31日 full backfill 只允许作为灾难恢复工具，不能作为日常 shadow repair。已有 verified 31日基线后，shadow 缺口必须按 R2 receive-day 做 append/upsert 型增量重放；增量 repair 禁止删除 compact state，必须先有对应 receive-day 的 exact `count+fingerprint` checkpoint。若 full rebuild 预计会逼近/超过 Free 日写额度，应转付费容量或采用显式多日维护方案，不能在生产日硬跑后再把实时 shadow 留死。
- **配额语义**：R2 marker 将 D1 `daily row write/read limit` 分类为明确 failure class；同一 UTC quota day 内检测到配额耗尽时自动恢复必须立即 `BLOCKED_PLATFORM_QUOTA`，不得重试写放大。Cloudflare Free 配额在 00:00 UTC 重置后，先刷新31日 verified R2 cache，再只重放 marker receive-day 到当前日（最多3日）。
- **已落门禁**：新增 `repair-analytics-ops-day.mjs`，真实 2026-09-02 dry-run 为 `275 batches / 8 SQL / 1 chunk`，相对旧 verified base 仅新增22 batches；内存 SQLite 契约验证 baseline→repair、跨batch search lifecycle、重复重放幂等、无DELETE。新增 `analytics-shadow-recover.mjs`，08:05 本地 `MagnetGoogo-AnalyticsShadowRecovery` 任务 + 10:15 GrowthDaily preflight；当前配额日实测任务 `LastTaskResult=2` 且 GrowthDaily 在 KPI 前停止，不发布不可信增长结论。
- **生产恢复边界**：2026-09-02 当前 D1 Free 写额度已由本轮 full backfill 消耗完，现态必须保持 fail-closed；不能通过删 marker/伪 verified 绕过。下一次平台自然重置为 2026-09-03 00:00 UTC（UTC+8 为 08:00），已注册任务 08:05 执行上述增量恢复链。

## BL-044 — 5000 DAU 逻辑容量通过不等于 D1 Free 计费容量通过

- **版本/时间**：Analytics D1 write-budget 复核，2026-09-02
- **现象/风险**：已有容量测试能证明 `5000 devices × 25 batches = 125000 raw batches/day` 在 exact identity 上不会把 DAU 重复放大，但这不能证明 Free D1 能承受真实用户搜索强度。真实 2026-09-01 receive-day 为 5265 batches / 210 devices，却产生 5001 个 batch-local search upsert group、1597 个 unique search_id；D1 secondary index 维护本身也按 rows-written 计费。若只看“重复 batch 是 no-op”，会错误宣称 5000 DAU 已通过 Free 容量门。
- **实测预算**：新增 `analytics-ops-write-budget-audit.mjs` 对 verified R2 cache 做保守物理写预算。优化后 2026-09-01 估算约 `15913 rows/day`（Free 100k 的15.9%）；按同强度70%工程预算线性外推，conservative safe≈923 DAU，Paid review trigger≈742 DAU；5000 DAU≈37.9万 rows/day，明确不是 Free-safe。该数字是规划估算，Cloudflare Row Metrics 仍是账单authority。
- **根因**：旧容量门只把“状态正确性/重复写 no-op”与 raw batch 数绑定，没有把每个 search lifecycle 的表写、secondary indexes、legacy diagnostic counters、growth meta 和运维 backfill 纳入同一 rows-written 预算。
- **永久规则**：以后容量必须同时给出 `correctness capacity` 与 `billable capacity`。Free 层固定使用低于硬上限的70k rows-written/day工程预算；Growth KPI 每日输出 `d1_write_capacity`、safe DAU 和 Paid-review trigger。达到 review trigger 时提前评审扩容，不能等100k硬限报错；也禁止为了死守Free而牺牲exact/fail-closed语义。
- **已落优化**：live shadow 不再写非权威 `ops_daily` counters；稳定 canonical alias、重复 search lifecycle、重复 backfill compact state 均用 SQL `WHERE` 变成真正 no-op；每条 Growth event 删除未消费的 `growth_read_model_last_write_ts` 写；full apply 默认拒绝，显式允许后仍需通过70k预算门。真实103432-batch full-state本地回放验证：首次51247 logical compact changes，完全相同第二次回放 compact changes=`0`（仅backfill metadata 1行）。
- **5000 DAU 裁决**：当前模型不以 Free 为5000 DAU目标。按现有强度5000 DAU约1130万 rows-written/30d，低于当前 Workers Paid 包含的5000万/月；因此优先在约700～900 DAU区间提前切换Paid，而不是引入更复杂、风险更高的去实时化搜索聚合架构。任何付费切换必须由用户明确批准，不能自动购买。

## BL-045 — freshness 源因 minimum_interval 主动跳过时，不能被当成抓取失败

- **版本/时间**：影视多源 quorum 生产收口，2026-09-02
- **现象**：Bitba/MJF 已在阿里云真实完成 50/50，新数据库 `job_status=success` 且有 461/48 条有效 magnet；正式 media-daily 紧接着启动时，安全爬虫因 `minimum_interval` 正确返回 `status=skipped / reason=minimum_interval / publish_ready=false`。旧 media-daily 把所有 `publish_ready=false` 都视为 freshness incomplete，于是把这两个刚验证过的健康源转成 fallback；recovery 又因 daily budget 被拒绝，最终 freshness group 被错误计算为仅 sixv-series 1/4，revision32 被正确但不必要地 withheld。
- **根因**：`publish_ready` 混合了“这次调用是否生成可发布新结果”和“现有 durable success 是否仍处在允许复用的最小检查间隔”两种语义；media-daily 没有识别 `minimum_interval` 是安全策略主动去重，不是源失败。
- **为什么已有门禁没挡住**：既有测试覆盖 `pending/partial/fallback`、no-magnet、旧库不能替本轮空 feed 兜底，但没有覆盖“刚完成真实成功抓取后，第二次调度被 minimum_interval 主动跳过”的连续时序。
- **永久规则**：freshness authority 允许一种严格的 `recent_success_within_minimum_interval` 证据：仅当 `status=skipped + reason=minimum_interval + durable job_status=success + covered_count>=target_count` 时，才能免于 fallback；同时 group 仍必须从该 source 当前 feed 验证至少一条有效 magnet。`daily_budget`、`failure_backoff`、under-covered、partial/pending、无 feed、无 magnet 均不得复用该豁免。
- **发布门禁**：必须固定测试 `minimum_interval complete success => not degraded`；`daily_budget/under-covered/partial => degraded`；端到端 media-daily candidate 必须证明多个 recent-success 源不触发 recovery、freshness quorum 正常通过并输出 `freshness_evidence=recent_success_within_minimum_interval`。生产发布前还要在克隆生产状态上复现该时序。

## BL-046 — 外部资源 href 不能假设 `urlparse().hostname` 永不抛异常

- **版本/时间**：Meijumi production recovery，2026-09-03
- **现象**：meijumi 长期停在 `99/100`，唯一 unresolved 页面 `27336.html` 实际 HTTP 200、页面结构正常且含大量 magnet。生产 parser 却稳定抛 `ValueError: 'V2' does not appear to be an IPv4 or IPv6 address`，因此被误认为站点验证码/反爬导致的单源 degraded。
- **根因**：详情页同时存在 `ed2k://|file|[V2]Godless...`。旧 `_resources()` 对所有非-magnet href 都调用 `_cloud_provider()`，后者无条件执行 `urlparse(url).hostname`；Python 3.11 会把 URI 中 `[V2]` 解释为 bracketed host 并进行 IP 校验，直接抛 `ValueError`。
- **为什么会漏掉**：旧 fixture 只覆盖 magnet 与正常 `https://pan.*` 云盘 URL，没有覆盖 ED2K、畸形 URI、方括号文件名等现实资源链接；同时异常发生在 provider 探测层，导致整条详情失败而不是单条无效资源被丢弃。
- **永久规则**：第三方 href 一律视为不可信输入。资源 provider 识别必须先安全解析；捕获 URL parser 异常，并只允许显式支持的 `http/https + valid hostname` 进入云盘 provider 判断。ED2K、FTP、javascript、相对文本或 malformed URI 不得因 provider 探测异常拖垮整条详情。
- **发布门禁**：必须固定回归“合法 magnet + `ed2k://|file|[V2]...` 同页”场景：parser 不抛异常、非法/不支持资源被忽略、合法 magnet 保留。修复后生产单源 recovery 必须证明 unresolved 从1→0、covered 99→100、`publish_ready=true`，再以 media audit 验证 freshness group 恢复。
- **生产结果**：修复提交 `605f5c9` 后，受控 recovery 仅1个详情请求即恢复 meijumi 100/100；部署后 audit series freshness=4/4，meijumi 已退出 degraded_sources。

## BL-047 — 搜索结果字段不能由各 handler 自行解释；同一 BTIH 的镜像多数也不等于独立真值

- **版本/时间**：App 0.2.8 搜索字段治理，2026-09-05
- **现象**：用户长期看到搜索列表里的大小单位与迅雷打开同一 magnet 后差一个甚至多个数量级，例如 SSBC `size=7969178` 被旧 App 当约8MB，K30S 迅雷同 hash 实际约7.5GB；另有详情页把第一个文件2GB误当整个 torrent 总大小，以及单个源报8276GB而独立源/迅雷只有约2.3MB。标题、日期、fileCount、seed/leech 也存在各 handler 各写一套解析规则导致的串位与复发风险。
- **根因**：历史实现把字段语义分散在 HTML/JSON handler、detail-follow、卡片 formatter、去重排序、后台缓存和 Python crawler 中；同一字段存在多套 parser。更隐蔽的是同一后端索引被多个镜像复制后，旧合并逻辑按 source/host 数量投票，会把“一份错误元数据复制成十个镜像”伪装成多数共识。
- **为什么旧门禁没挡住**：BL-008 只要求共享 size parser，但没有覆盖 source-specific 单位世代、详情总量/单文件语义、同 BTIH 跨源证据相关性、后台缓存重新注入旧字段，也没有真实 K30S 全源矩阵和迅雷 BT metadata 交叉真值。单元测试可以全绿，真实列表仍可能错。
- **永久规则**：所有 source 输出进入 App/Python 后必须再经过统一最终字段 contract；title/magnet/size/date/fileCount/seeders/leechers 任何一个可选字段无法证明语义时宁可留空，不得猜。裸数字 size 默认不解释；详情总大小与文件列表单项大小必须分离；日期必须验证真实日历；fileCount 是一等字段；counter 必须保留 `1.2k/2万` 原始语义直到统一 parser。
- **同-hash证据规则**：同一 pool 的多个镜像只能算一个 size evidence group；已证实共享旧索引的数据家族必须进一步合并为一个组。同组内部 >25% 冲突则整组作废；只有真正独立 evidence groups 才能形成多数。无法裁决的 exact-torrent size 必须留空，不允许“第一个非空值”或“镜像多数”胜出。
- **发布门禁**：0.2.8 起固定执行 `audit:k30s-fields`，至少覆盖影视/软件ISO/动漫多语言/中文编码/游戏大文件五类查询；必须满足 `completedSources=totalSources` 且 `finalIssueCount=0`。第三方原始冲突可作为 `UPSTREAM_WARNING` 保留，但只有最终用户字段0错误才允许发布。当前五组共810 source-runs / 2500 raw results / 987 final unique，final issues=0。
- **真实真值**：`9b14e6bd...` 旧显示约8MB、迅雷7.5GB，0.2.8约7.6GB；`8efc1d36...` 上游2GB/6.69GB但迅雷21.4GB/4 files，0.2.8保留fileCount=4并把size留空；`b73c932d...` 一个源8276.22GB、两个独立pool 2.38MB，0.2.8最终2.4MB，迅雷2.3MB。

## BL-048 — 搜索输入框只能由用户或明确外部导航写；不要让搜索页反写路由再治理自己的回声

- **版本/时间**：App 0.2.8 搜索生命周期收口，2026-09-06
- **用户现象**：搜索 A 过程中用户已经把输入改成 B，旧 A 的异步结果、后台 snapshot 或搜索页自身路由同步有机会再次把输入/搜索 owner 拉回 A；为了防这种竞态，旧修复一度引入 `committedQueryRef / dirtyDraft / routeOwner / knownOwners / ABA classifier` 等多层状态，正确但明显过度复杂。
- **根因**：`query` 同时被当作“用户正在编辑的草稿”“已提交搜索词”“路由参数”和“后台恢复值”。更关键的是 SearchScreen 内部搜索后又 `router.setParams(q=...)`，于是页面会收到自己制造的异步 route echo，只能再增加 owner token 去区分真外部导航和自回声。
- **为什么已有 BL-001 仍会走向复杂化**：BL-001 已要求 draft 与 committed query 解耦，但没有明确禁止“后台/异步任务写输入框”以及“SearchScreen 内部反写 q”。因此修复方向仍可能围绕识别更多状态来源，而不是直接减少写入来源。
- **永久规则**：搜索交互只允许三条规则：①输入框 draft 只由用户输入，或进入 SearchScreen 时的一次明确外部导航设置；②用户提交时创建新的不可变 search generation，并在任何 await 前立即使旧 generation 失效；③所有旧 generation 的 result/progress/background snapshot 只能被丢弃，绝不能修改 draft。SearchScreen 内部再次搜索（包括点击结果文件名）直接 `doSearch(term)`，**禁止**为了同步显示而 `router.setParams(q=...)`。
- **source-not-ready 规则**：源尚未加载时只保存**一个最后提交的 pending query**；后提交覆盖前提交。源就绪后只启动该最后 query，不重放旧 route。
- **发布门禁**：`test:search-lifecycle` 必须固定验证：不同 query 不受同词 cooldown 阻塞、提交前旧 generation 已失效、所有 result/progress callback 有 generation fence、background snapshot 不含 `setQuery(snapshot.query)`、SearchScreen 不含 `router.setParams`/route-owner 状态、pending 只保留一个最后查询、首页/历史/影视“搜索更多”/影视资源文件名/收藏/结果文件名均进入同一搜索路径。K30S 至少复测 A→B、长时间 dirty draft 后提交、前后台 snapshot 回传期间编辑并提交新词。
- **K30S 真机证据**：0.2.8 Debug 上 `Inception→Interstellar` 明确 commit B；`Interstellar` 搜索运行期间把 draft 改成 `ubuntu` 后等待10秒再提交，最终仍 commit `ubuntu`；前后台恢复后 `delta` snapshot 连续回传期间把 draft 改成 `epsilon`，多次 snapshot 均未改输入，最终 commit `epsilon / previous delta`，且 epsilon commit 后未再出现 delta snapshot apply；crash scan 无 FATAL/AndroidRuntime/ReactNativeJS Error。

## BL-049 — SEO 文案与下载入口不得硬编码 App 版本号

- **版本/时间**：App 0.2.8 发布收口，2026-09-06
- **现象**：历史 SEO 首页、状态页、工具页和站点页曾把 `v0.2.7/v0.2.8` 写进“免费下载”按钮或 `Android 7.0+ · vX.Y.Z` 文案；部分旧文章下载 href 还绑定具体 APK 版本。这样每次 App 发版都需要全站批量改文案，既多余，也容易留下旧版本入口。
- **永久规则**：所有 SEO 用户可见文本一律不显示 App 版本号，只写“免费下载 / 最新版 / Free Download”等长期有效文案；SEO 下载按钮使用动态最新版入口（`/go/download`、官网 latest 或等价动态入口），不得新增具体版本 APK URL。具体 `latest_version / min_version / primary APK` 只由发布配置维护。
- **生成器规则**：SEO 生成器不得读取 `latest_version` 只是为了拼页面文字；重新生成页面后也必须保持用户可见版本号为 0。
- **发布门禁**：上线 SEO 站前扫描 HTML/JS 可见文本，`v0.x.x` 命中必须为 0；历史报告、正式 release notes、机器发布 `config.json` 不属于 SEO 用户可见文本，可保留版本信息。

## BL-050 — Analytics Recovery 必须能超时退出；计划任务 IgnoreNew 不能代替跨入口进程锁

- **版本/时间**：SEO/Growth 数据可信度恢复，2026-09-06
- **现象**：`MagnetGoogo-AnalyticsShadowRecovery` 的 08:05、GrowthDaily 10:15 preflight 与 14:26 手工恢复同时残留，三组进程都卡在 `cmd/npx/wrangler d1 execute` 子进程；任务表看似 Running，但生产仍 `operational_verified=false`。
- **根因**：恢复脚本通过多层 `npx wrangler@...` 启动远端 D1 命令且没有硬超时；Task Scheduler 的 `MultipleInstances IgnoreNew` 只能限制同一个计划任务实例，挡不住 GrowthDaily preflight 或手工入口并发进入同一恢复链。
- **永久规则**：Analytics recovery 必须同时具备：①跨入口进程锁；②stale lock 可恢复；③直接调用项目已安装 Wrangler CLI，避免多层 npx 子树；④每个远端 D1 repair chunk 有硬超时；⑤最终以生产 `operational_verified=true + shadow_healthy=true` 回读为成功边界。不得因为任务仍在 Running 就认为恢复正在健康推进。
- **恢复证据**：清理仅 Analytics recovery 的三组僵死子树后，远端 `SELECT 1` 立即成功；使用 verified 31-day R2 snapshot 对 2026-09-04～09-06 做 bounded incremental replay 后，生产恢复为 `repaired_by_backfill`，legacy drift=`0/0`，Growth Opportunity 从 `GATED` 回到 `READY / blockers=[]`。

## BL-051 — SEO 渠道归因只能记录有限来源类别，不能保存完整 Referer、搜索词或访客标识

- **版本/时间**：SEO acquisition attribution，2026-09-06
- **现象**：网站已有 qualified landing view 与可信下载点击，但 745+ 个合格访问只能看到国家/locale，无法区分 Google、百度、直接访问和外链，导致“SEO 带来多少新增”只能靠方向推断。
- **永久规则**：浏览器只允许从 `document.referrer` hostname（以及明确 allowlist 的安全来源标记）本地映射到有限枚举。除传统搜索引擎 `google/baidu/bing/sogou/360/shenma/yahoo/yandex/duckduckgo/brave/ecosia` 外，可为已批准增长渠道增加有限类别（当前含 `chatgpt/perplexity/copilot/gemini/claude/naoshiquan/github/reddit/zhihu/v2ex/coolapk/52pojie/bilibili/telegram/producthunt/x/youtube`），并保留 `direct/internal/referral/unknown`；服务端必须同步白名单校验。只存类别，不上传/保存完整 Referer URL、query、搜索词、cookie、IP、localStorage ID 或其他持久访客标识。
- **实现约束**：复用现有 `landing_view.placement=qualified_view:<source>` 聚合维度，不为渠道归因增加用户级表或 Web→App join；`direct` 必须保持 direct，禁止用 locale/country 猜搜索引擎。旧历史事件保留 `qualified_view`，不得伪造回填来源。
- **发布门禁**：Gateway contract 必须断言 acquisition sanitizer、有限枚举和 privacy definition；前端 tracker 必须无 cookie/storage，生产 `/api/growth` 必须显式暴露 `landing_views.acquisition_sources`。渠道归因只能从上线后的真实新流量开始统计。

## BL-052 — 渠道 tracker 全覆盖不等于渠道结构立即可决策；必须切掉低覆盖历史样本

- **版本/时间**：SEO acquisition attribution 全站收敛，2026-09-07
- **现象**：渠道归因首次上线时仅 25/214 个 indexable URL（11.7%）接入 tracker，随后即使把静态覆盖补到 214/214，`acquisition_sources.bySource` 仍混有低覆盖期的历史流量。如果只看“当前覆盖=100%”就立即分析 Google/百度/Direct/Referral 占比，会把页面选择偏差包装成渠道结论。
- **根因**：原 Growth API 只有跨日累计 `bySource`，缺少 source×day 维度；报告 gate 只检查当前 HTML 覆盖率，没有区分“什么时候开始全覆盖”和“决策样本是否全部来自全覆盖后的完整运营日”。
- **永久规则**：所有 indexable sitemap URL 必须接入同一隐私安全 tracker；Growth API 必须暴露 `acquisition_sources.bySourceDay`；渠道决策只允许使用全覆盖部署后的**完整运营日**，并逐日校验 source 分类总数等于该日 qualified landing views。部署当天因包含部署前流量不得进入决策窗口。
- **当前门禁**：全覆盖部署时间 `2026-09-07T00:24:38+08:00`；第一个干净完整运营日固定为 `2026-09-08`（UTC+8）。至少积累 3 个完整日且合计 ≥200 qualified views 后，`channel_mix_decision_ready` 才能为 true；此前历史 `bySource` 仅 diagnostic，不得用于全站渠道占比结论。
- **发布门禁**：`seo-growth-audit.js` 要求 `attribution_tracked_all=214/214`；公网 sitemap crawl 同样要求 214/214 页面实际包含 tracker；Gateway contract 必须断言 `bySourceDay/byPlacementDay`；任何页面缺 tracker 或任一决策日 sourceTotal != landingTotal 都 fail-closed。

## BL-053 — 影视 redundancy 告警只能看 freshness group 冗余，不得把 supplemental degraded 当成 quorum 缺口

- **版本/时间**：影视生产监控复审，2026-09-07
- **现象**：生产日更 revision37 已成功发布，series freshness 实际为 `4/4`，`required_degraded_sources=[]`、`failed_freshness_groups=[]`，但 `media-source-redundancy` P2 仍连续失败 8 次并保持 open；唯一 degraded 是非 quorum supplemental `dytt8899=249/250`。
- **根因**：`media-alert.sh` 旧规则只要全局 `degraded_sources` 非空就打开 P2，把不参与 freshness quorum 的 supplemental 源也解释成“冗余不足”。
- **永久规则**：P2 redundancy 只能来自 freshness group 本身的冗余缺口：`fresh_count < member_count` 且 `fresh_count >= min_fresh`。若 group 已全员 fresh（如4/4），即使外围 supplemental 源 degraded，也必须判 redundancy success；若低于 `min_fresh` 则升级为既有 P1 freshness failure，不重复用 P2 表达同一故障。
- **发布门禁**：告警测试必须断言 success helper 分支依赖 group `fresh_count/member_count/min_fresh`，禁止重新以裸 `DEGRADED_SOURCES` 作为 P2 条件。生产 smoke 必须使用真实 latest-publish status 验证“4/4 + supplemental degraded => P1/P2 success”，且不修改 `sources.json health.status`。
- **生产证据**：2026-09-07 daily 03:33→04:31 exit0，revision36→37，396 movies / 498 series / 6280 magnets；meijumi/sixv-series/bitba-series/mjf-series 4/4 fresh。修复提交 `d9b35c2` 后隔离 state + disabled transport 的真实 status smoke 返回 `media-source-freshness success`、`media-source-redundancy success`。真实告警状态不被测试篡改，将由下一次正常 success hook 自然收敛。

## BL-054 — GEO/AI 引荐不能混入 generic referral；AI 来源归因必须前瞻、隐私安全且禁止历史猜测

- **版本/时间**：GEO measurable discovery，2026-09-11
- **现象**：全站 acquisition tracker 已能区分 Google/百度等搜索引擎，但 ChatGPT、Perplexity、Copilot、Gemini、Claude 等 AI 问答/AI 搜索访问仍会落入 `referral`（Referer 丢失时甚至是 `direct`），导致 GEO 即使开始生效也无法从运营数据中单独观察。
- **根因**：BL-051 的有限来源枚举在 GEO 成为增长主战线之前设计，分类器只覆盖传统搜索引擎；同时没有利用 ChatGPT Search 官方外链的 `utm_source=chatgpt.com` 这一可验证来源标记。
- **永久规则**：AI 来源也只能映射为有限类别 `chatgpt/perplexity/copilot/gemini/claude`；浏览器可检查已知 Referer hostname，以及明确 allowlist 的 `utm_source` 值后立即折叠为类别。**严禁**上传或保存完整 URL、query string、UTM 原值、搜索提示词、cookie/storage ID 或访客标识。服务端继续二次白名单。
- **历史边界**：AI 分类只从部署后的新事件开始。历史 `referral/direct` 不得根据页面、国家、时间或猜测重新分类；GEO 基线第一个完整运营日为 2026-09-12（UTC+8）。
- **发布门禁**：`geo-audit.js` 必须真实执行分类器，覆盖 ChatGPT Referer、ChatGPT `utm_source=chatgpt.com`、Perplexity/Copilot/Gemini/Claude、普通 Google/referral/direct，并断言发送体仅含 `page/locale/source`；Gateway contract 必须包含同一 AI 来源枚举。

## BL-055 — Broadcast 增长发现必须要求“资源实体 + 明确用户需求 + 新鲜度”，不能把搜索查询命中当成帖子意图

- **版本/时间**：Growth referral outreach hardening，2026-09-11
- **现象**：真实 discovery 用查询“磁力猫 打不开”搜索 X 时，曾命中一条仅讨论“推特发不了图片、相机打不开”的帖子，并生成 awaiting_approval Job #395；帖子正文没有任何磁力/BT/torrent/目标品牌语义，只因为泛化“打不开”命中旧 USER_NEED/POSITIVE 规则。
- **根因**：旧分类器把 discovery query 当作高召回入口，但正文判定仍允许“打不开/not working/替代”等泛故障词本身提升到资源意图；没有硬要求**目标帖子正文自身**包含磁力/种子/torrent/magnet/BT/BTSOW/磁力猫等资源实体。搜索引擎返回的相关性不能代替帖子自身语义证据。
- **永久规则**：外联候选必须同时满足：①帖子正文命中资源实体；②明确求推荐/求替代/资源服务不可用；③非自荐/发布/教程展示；④生产配置要求可验证发布日期且不超过14天；⑤ Tier-1 自动候选=0；⑥每轮最多1条；⑦`approval_required=true`，自动流程只能进入审批队列，绝不自动发布。
- **错误候选处置**：Job #395 与 discovered post #313 均已标记 rejected，关联任务136收敛 failed；从未外发。
- **发布门禁**：`test-broadcast-growth-intent.js` 必须固定包含“推特相机打不开”与泛 App 故障反例；`test-growth-discovery-policy.js` 必须验证 approval-only fail-closed 配置；二者必须并入 `npm run test:admin`。真实 discovery smoke 应允许 0 候选，禁止为了产量降低门槛。

## BL-056 — GSC 外部授权失败时必须区分“最后可信快照”与“当前采集状态”，不能把旧 OK 冒充新鲜数据

- **版本/时间**：Growth evidence reliability，2026-09-11
- **现象**：Search Console OAuth refresh token 已 expired/revoked，Daily 已正确识别为 `BLOCKED_EXTERNAL_AUTH`；但 `latest-opportunity-report.json` 仍只读取 2026-09-08 留下的 `latest.json(status=OK)`，把 L1 Search Console 显示为当前 `OK`，容易让旧排名/CTR 证据看起来仍在持续更新。
- **根因**：`latest.json` 同时承担“最后一份成功数据”和“当前采集健康状态”两个语义。为了保留最后可信历史快照，授权失败时没有覆盖它；报告层又缺少独立 ingest status，因此无法区分 last-good 与 fresh。
- **永久规则**：Search Console 成功数据与 ingest health 必须拆开：`latest.json` 只保存最后成功 final snapshot，`ingest-status.json` 保存最近一次采集的 `OK/BLOCKED_EXTERNAL_AUTH`。若较新的 ingest status 为授权阻塞但 last-good 仍存在，报告必须显示 `STALE_LAST_GOOD` + warning，可继续用于历史实验基线，但不得描述为当前数据；不得把缺失采集解释成 0 流量。
- **发布门禁**：`test-gsc-last-good-contract.mjs` 必须验证独立 status、`STALE_LAST_GOOD` 和 non-destructive warning 语义，并并入 `npm run test:admin`。生产 GrowthDaily health 必须同时记录 `search_console=BLOCKED_EXTERNAL_AUTH` 与 `search_console_evidence_status=STALE_LAST_GOOD`。

## BL-057 — GEO/SEO 内容不得伪造第一手实测、动态源数量或把 GitHub 项目页等同应用源码；发布页不得泄漏 frontmatter

- **版本/时间**：NSQ GEO entity fact cleanup，2026-09-12。
- **现象**：既有 NSQ 页面出现 `80+/100+` 固定来源数、把 Magnet Googo 描述成 open-source/source-auditable、`94/100 queries`、两周/数月使用、具体设备/网络/秒数/崩溃等无法证明的第一手叙事；其中一页甚至声称在当前日期之后的 `2026-10-15` 完成测试。另有多语言页面把 YAML/frontmatter 连同 `canonical_url` 原样渲染进正文。
- **根因**：旧内容流水线为了“像真人测评”允许模型补体验细节，brief 标题直接要求“实测/Tested”，finalizer 又要求 YAML front matter；当模型把整篇 Markdown 包进代码围栏时，publisher 只识别首字符为 `---` 的 front matter，导致作者元数据被当正文发布。
- **为什么漏掉**：既有 SEO 门禁主要验证 canonical/indexability/tracker 和少数高意图页，没有对 sitemap 全量页面做 Magnet Googo 实体事实审计，也没有禁止“第一人称真实性”被模型用虚构细节实现。
- **永久规则**：① Magnet Googo 来源集合视为动态事实，除非 brief 提供有日期、可归属的权威证据，否则禁止固定 `80+/100+/百余` 数字；② GitHub 项目/Release 页只能证明发布与项目活动，不能据此宣称应用源码开放或可审计；③ 禁止模型编造个人使用历史、设备、网络、查询次数、命中率、响应时间、崩溃、成功下载、社区反馈或未来日期测试；④ 动态质量结论优先引用官方 status/methodology/release evidence；⑤ 发布页禁止出现 raw YAML/frontmatter 或 `canonical_url:`。
- **发布门禁**：`naoshiquan-site/scripts/growth-seo-audit.js` 必须遍历 sitemap 全量页面，对固定源数量、错误开源、伪第一手/量化测试、未来日期测试、标题层 `Tested/实测/测评/评测` 和 raw frontmatter fail-closed；`publish_to_naoshiquan.py` 必须解包 LLM 外层 Markdown fence，未解析 front matter 进入 HTML 时直接失败；content-engine writer/revisor/finalizer/briefs 同步禁止伪测试。不得为了“让 audit 过”篡改无关真实内容或削弱规则。
- **生产证据**：2026-09-12 NSQ sitemap=175，扩展事实门 175/175 PASS；生产部署 `69b8e474-2fa1-4e09-a959-7be3613b79f0` 后抽查 16 个高风险中/英/俄/日页面全部 HTTP200 且旧伪证据/frontmatter 信号为0；IndexNow 仅按 sitemap 刷新 175 个既有 canonical，HTTP200。

## BL-058 — 渠道转化归因必须前瞻且只使用有限 source 类别，严禁把历史点击反推到来源

- **版本/时间**：500 DAU growth scale measurement，2026-09-16
- **现象**：已有 acquisition source 与 download click 两套聚合，但缺少 source×page×day 同窗数据；若直接按历史时间或页面相关性拼接，会把无法证明属于同一访问链路的点击错误归因给 NSQ/百度/社区渠道。
- **根因**：原增长模型分别优化“来源结构”和“下载点击”，没有设计前瞻的同事件 source 维度；跨表历史 join 看似能算转化率，实际上没有用户级连接证据。
- **永久规则**：新增 `growth_attribution_daily_dims`，仅保存有限 source 类别、page、day、locale、placement、country 与聚合计数；绝不保存 raw referrer/UTM/query/user/device/visitor ID。下载 source 只允许由浏览器有限分类经 Magnet 一方传递，或对 `nsq:*` 直接 CTA 使用明确的 `naoshiquan` 类别；历史点击严禁补猜来源。
- **裁决门**：首个完整干净日为 2026-09-17；至少 3 个完整日且 >=20 个 source-attributed download clicks 后，`conversion_attribution` 才允许方向性裁决。NSQ 文章没有文章浏览分母时只看 `nsq:*` 下载点击与 NSQ referral 量，不制造虚假 conversion_pct。
- **发布门禁**：Gateway growth contract 必须验证新 D1 表、API `attribution_funnel/bySourcePageDay`、first-party source trust、rebuild 幂等；GEO audit 必须验证 CTA 只携带有限 source 且不复制 raw query。

## BL-059 — Broadcast 配置了浏览器 profile 不等于 discovery 真正使用了它；单平台导航失败也不能拖垮整个审批扫描

- **版本/时间**：Second acquisition engine discovery，2026-09-16
- **现象**：`broadcast-config.json` 已为平台配置 `account_profile=k2dn57uc`，但 `searchPlatform()` 调 OpenCLI 时未传 `--profile`，知乎出现 `Navigation rejected`；旧 PowerShell wrapper 又会把可恢复的 native stderr 直接写成整轮 ERROR。
- **根因**：配置层和执行层之间缺少 profile contract；同时 wrapper 把“某个 query/platform 失败”与“整个 approval-only discovery 失败”混成一个错误语义。
- **永久规则**：浏览器型平台 search 必须显式传已配置 `--profile`；每个平台/查询继续 fail-closed，不生成候选即可，其他平台必须继续。Node 进程 exit=0 时，wrapper 不得因可恢复 stderr 把整轮判 ERROR；健康文件用 `PARTIAL + recoverable_platform_errors` 表达降级。无适配器的平台保持 manual，不得假装已自动化。
- **当前能力边界**：知乎/Reddit 可进入自动发现+人工审批；V2EX OpenCLI 无 search 命令，需未来安全的 latest→关键词→topic 适配；酷安/52破解当前无支持的搜索适配器，保持 manual discovery。
- **发布门禁**：`test-growth-discovery-policy.js` 必须断言 account_profile 被转发、approval-only 安全门不变、platform error 可降级且不 auto-post。真实 smoke 允许 0 候选；2026-09-16 实跑 81 searched / 0 new / 0 enqueued / auto_post=false / status=OK。

## BL-060 — 单个 shadow failure 不能抹掉历史已验证日；3日自动恢复上限必须有显式深度修复出口

- **版本/时间**：Analytics verification / Growth operations review，2026-09-29。
- **现象**：2026-09-23 23:56Z 发生一次 `d1_daily_row_read_quota` shadow failure 后，`operational_verified=false` 一直未闭合。Admin 当前逻辑只要全局 `shadowHealthy=false`，就把返回窗口内**所有**日级 rows 标成 `partial`，因此用户看到很多历史 DAU 都像“核验失败”；实际上 2026-09-23 之前已有正式 verified LKG。与此同时自动恢复从 failure receive-day 到 current UTC day 最多允许3日；首次几天没有闭合后，09-29 已固定报 `recovery window exceeds 3 receive days; require explicit deep repair`，每日计划任务继续重复 exit1，但没有自动进入可执行的深度修复流程。
- **根因**：① 完整性模型只有一个当前全局 `shadowHealthy`，没有保留 `verified_through` / per-day verification provenance，导致“当前 shadow 有缺口”和“历史完整日是否曾正式核验”两个语义被混在一起；② `maxDays=3` 是正确的写放大安全阀，却只有拒绝路径，没有对应 `NEEDS_DEEP_REPAIR` 状态、分段预算和人工修复入口，所以超过3日后会形成稳定死锁。
- **为什么已有 BL-040～044 仍没挡住**：已有门禁正确要求配额失败 fail-closed、最多3日增量 repair、不得删除 marker/伪 verified，也验证了短窗口恢复；但没有覆盖“连续多日计划任务都未闭合，窗口自然增长到第4日以后”的长期时序，也没有验证 UI 应继续保留故障前的 last-known-good verified days。
- **永久规则**：① current shadow health 与历史 daily verification 必须分离。故障发生后，只能把**受故障覆盖且尚未重新证明完整**的日期降级；已被 prior verified snapshot/backfill 证明的历史日必须保留 `verified_lkg` 或等价状态，不能因后续 marker 被全局改成 partial。② 自动恢复超过安全窗口时必须输出明确 `NEEDS_DEEP_REPAIR` + failure day/current day/span，而不是普通 ERROR；计划任务应停止重复做必然失败的同一动作。③ 深度修复必须先刷新 verified R2 inventory/checkpoint，按 receive-day 分段估算 D1 read/write budget，再逐段 replay；不得扩大普通自动任务的3日安全阀，不得删 failure marker 或直接把 observational 标成 verified。
- **发布门禁**：增加长期时序测试：`verified historical days + newer unresolved marker => historical verified_lkg preserved, affected days partial`；以及 `failure span >3 days => NEEDS_DEEP_REPAIR, no D1 apply`。深度修复后必须真实回读 Gateway，证明 `operational_verified=true / shadow_healthy=true`，并核对 repaired days 的 R2 count+fingerprint 后才允许新 `_growth_kpi.json` 覆盖 LKG。
- **2026-09-29 生产证据**：唯一 unresolved marker=`2026-09-23T23:56:57.731Z` / class=`d1_daily_row_read_quota`；`AnalyticsShadowRecovery` 与 `GrowthDaily` 最近均 result=1；当前 D1 exact state 仍持续产生 09-26/27/28 DAU=`289/306/308`，legacy diagnostic 最大 active-device drift 仅5，但这些日直到 deep repair 完成前只能记 observational。

## BL-061 — 备用下载直链若绕过归因会系统性低估首页 CVR；测量修复不得改变用户下载去向

- **版本/时间**：Homepage CRO measurement precondition，2026-09-29。
- **现象**：首页主 CTA 统一经过 `/go/download`，但 GitHub / 蓝奏云两个 `data-backup-download` 直接跳外站，没有进入 `seo_download_click` / source×page×placement 归因。因此现有 homepage CVR 只能视为 primary tracked download 下限；若直接用这个 baseline 启动新的首页 CRO，会重复“分母/分子口径不完整却宣称 uplift”的旧问题。
- **根因**：备用镜像最初只承担可用性兜底，没有纳入后续增长测量契约；tracker 只给 `api.naoshiquan.com/go/download` 链接追加 finite acquisition source，不处理外站 mirror click。
- **永久规则**：所有用户可见下载出口都必须进入同一有限维度归因，但不能为了追踪改变原下载目标。外站备用链接采用 sideband tracking：点击仍按原 href 打开，同时向 `/go/download` 发 `redirect=manual` 的 keepalive GET，只记录 `page/locale/source/placement=backup_<mirror>`，禁止跟随主 APK 302、禁止复制 raw referrer/query/UTM。
- **实验门禁**：新的首页 CRO 在备用下载 tracking 生产上线后至少积累3个完整运营日，才能冻结 matched homepage baseline；处理变量一次只允许一条 evergreen trust microcopy，不动 title/meta/H1/Hero位置。7日主要成功门为 source-stratified matched homepage CVR 相对 +15%，Baidu/Google/Direct 单独不得出现实质性恶化。
- **测试门禁**：`magnetgoogo-site/scripts/geo-audit.js` 必须验证 GitHub/蓝奏 sideband 请求都命中 `/go/download`、`source` 仍为有限类别、placement 分别为 `backup_github` / `backup_lanzou`、`redirect='manual'` 且 `keepalive=true`；原外站 href 不得被改写。

## BL-062 — 健康 no-op 不得用强制 `process.exit()` 造成“业务 PASS / 进程 FAIL”假失败

- **版本/时间**：Analytics deep repair production closeout，2026-09-29。
- **现象**：deep repair 完成后再次只读运行工具，Gateway 已返回 `PASS_NOOP / operational_verified=true`，但 Node 24 on Windows 在紧接着 `process.exit(0)` 时触发 libuv async-handle assertion，最终 shell exit code 非0。业务状态实际健康，却会让计划任务或人工验收误判为失败。
- **根因**：异步 `fetch()`/Undici 连接句柄仍处于关闭生命周期时调用强制 `process.exit()`，跳过了 Node 的自然事件循环收尾；Windows/Node24 下放大为 libuv assertion。
- **永久规则**：完成网络 I/O 的维护脚本，健康/no-op 分支必须自然结束或设置 `process.exitCode`，不得在成功路径直接 `process.exit(0)` 强退。业务 PASS 与进程 exit0 必须同时成立才算自动化门禁通过。
- **修复/验证**：`repair-analytics-shadow-deep.mjs` 已将健康分支改为自然结束；再次运行输出 `PASS_NOOP / operational_verified=true` 且进程 exit0，无 assertion、无第二次 D1 写入。

## BL-063 — 结构性首页发布必须 cache-bust 与 HTML 同步变化的 CSS/JS，不能只验“公网文件已更新”

- **版本/时间**：Homepage visual deploy regression，2026-09-29。
- **现象**：本地视觉审查完全正常，Pages 部署后用户看到首页“全乱”。线上 `index.html` / `style.css` / `growth-attribution.js` 与本地 SHA-256 完全一致，Tailwind runtime 也加载成功；但生产 `style.css` / tracker JS 仍带 `Cache-Control: public, max-age=14400`。老浏览器可能拿到新 HTML 结构，同时继续复用4小时内的旧 CSS，形成结构/样式版本错配。
- **根因**：发布验收只检查了新请求得到的 HTML/CSS 是否200、内容是否正确，没有覆盖“已有访问用户持有旧静态资源缓存”的真实升级路径；首页视觉刷新又同时改变 HTML class 结构和自定义 CSS，属于强耦合发布。
- **永久规则**：① 任何 HTML 与 CSS/JS 同时发生结构耦合变化的发布，HTML 引用必须带内容指纹或等价版本化 URL，例如 `style.css?v=<content-hash>`；② 发布验收必须包含 warm-cache/old-cache 场景，不能只用无缓存 curl/headless 新会话；③ 首页生产截图必须和冻结的本地基线做同 viewport 像素/布局一致性对比；④ 版本 query 不得让 SEO/Growth tracker 审计误判，审计器必须允许同一路径的版本 query；⑤ 主下载/备用下载仍需独立回归，不能因视觉修复省略。
- **本次修复证据**：生产 HTML 已改为 `style.css?v=3c68ec22` 与 `/js/growth-attribution.js?v=c8addc6b`；SEO Growth 审计已兼容版本 query并恢复24/24 core PASS。相同 Chrome/390×844 同时截 localhost 与公网后平均像素差仅0.16（RMS1.73）；1440桌面公网与冻结基线平均像素差0.19，证明线上已恢复为本地认可视觉。

## 使用规则

1. 修复一个影响用户/发布判断的新 Bug 后，必须新增或更新本文件条目，而不是只写 `DEV-LOG.md`。
2. 同类 Bug 再次发生时，要补“为什么已有门禁仍没挡住”，并升级测试，不允许只改代码。
3. source health 自动化仍不得自行修改 `health.status`；状态升降级必须有人工/用户明确授权和有效测试环境证据。
4. 发布前至少复核与本次改动相关的全部 BL 条目，并在 `DEV-LOG.md` 记录对应门禁结果。
