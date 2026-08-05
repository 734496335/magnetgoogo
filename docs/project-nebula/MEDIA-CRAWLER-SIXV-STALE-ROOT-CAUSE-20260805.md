# 影视爬虫停更与 SixV 新片缺失根因复盘（2026-08-05）

## 结论

`INCIDENT_ROOT_CAUSE=SYSTEMD_203_EXEC`

`SIXV_DISCOVERY=17_OF_17_PASS`

`SIXV_DETAIL_PARSE=17_OF_17_PASS`

`SIGNED_RELEASE_VERIFICATION=17_OF_17_PASS`

`FOUR_SOURCE_CATCH_UP=PASS`

`PRODUCTION_REVISION_9=PASS`

App 缺少用户列出的 SixV 新片，主因不是 SixV 改版、列表漏抓、详情解析失效或 App 缓存，而是 2026-08-01 部署后 Linux 运行脚本丢失可执行位。每日 Timer 在 8 月 2—5 日均准时触发，但 `magnet-media-daily.service` 在爬虫启动前即以 `203/EXEC` 失败，四源数据库和线上 revision 因此连续停留在 8 月 1 日。

## 事故时间线

- 2026-08-01：revision 8 发布成功；随后服务器源码同步到新版本目录。
- 2026-08-02 03:33：每日任务 `203/EXEC`。
- 2026-08-03 03:32：每日任务 `203/EXEC`。
- 2026-08-04 03:32：每日任务 `203/EXEC`。
- 2026-08-05 03:31：每日任务 `203/EXEC`。
- 2026-08-02 14:31：周审计任务同样 `203/EXEC`。
- 2026-08-05 08:44：修复 systemd 执行链后启动首次恢复运行。
- 2026-08-05 09:20：部署完整追赶、剧集集合语义与 pending 即时续跑修复，启动最终生产运行。
- 2026-08-05 09:54：revision 9 双端发布成功。

故障现场：

- `/opt/magnet-media/app/deploy/resource-index/linux/run-media-daily.sh` 为 `0644`；
- Git 索引中三个 Linux 脚本原为 `100644`；
- systemd 直接将脚本作为 `ExecStart`，因此内核拒绝执行；
- Timer 自身仍显示 enabled/active，且当时没有外部失败告警，形成“看起来定时器正常、实际任务每天秒失败”的假象。

## 用户提供的 17 条 SixV 内容核验

用户提供的 17 个内容编号：

`50140, 50142, 50141, 50143, 50072, 50078, 50077, 50074, 50075, 50070, 50071, 50137, 50136, 49936, 50135, 50134, 50132`

### 列表发现

使用阿里云生产网络与正式 SixV crawler 对最新 100 条执行只读探针：

- 列表请求：4；
- 解析候选：100；
- 17 条全部发现；
- 实际排名：1—17；
- 缺失：0。

### 详情与资源解析

逐条访问详情页：

- 详情解析成功：17/17；
- 封面：17/17；
- 含磁力：17/17；
- 磁力合计：20；
- 网盘资源会在正式 Feed 前被过滤，不影响磁力入库。

其中：

- 《不能错过的只有你2》2 条磁力；
- 《宗师叶问2》3 条磁力；
- 其余各1条磁力。

因此 SixV 当前页面结构、列表解析和磁力解析并未失效。

### 正式签名 release 验证

revision 9 的 Catalog、Detail、Resources 三层按 `movie_id`逐项核验：

- Catalog 命中：17/17；
- Detail 命中：17/17；
- Resources 命中：17/17；
- 资源均为 magnet：17/17；
- 缺失：0。

## 第二层可靠性问题

### 1. 单次处理上限不足以追赶停机积压

旧策略：

- SixV电影：5 × 2批 = 10条详情/次；
- DYTT、Meijumi、SixV电视剧：10 × 2批 = 20条详情/次。

停机4天后实际积压：

- SixV电影：30条新/变更；
- Meijumi：24条详情请求；
- SixV电视剧：41条详情请求；
- DYTT：3条详情请求，另有1个历史404。

旧上限即使服务恢复，也会让部分来源继续落后1—2天。

新策略：

- SixV电影：最多30条，日请求预算100；
- DYTT：最多50条，日请求预算300；
- Meijumi：最多50条，日请求预算120；
- SixV电视剧：最多50条，日请求预算120；
- 所有来源仍保持10—15秒最小请求间隔，且预留请求数不超过日预算。

### 2. pending 作业被12小时间隔错误阻挡

旧实现把“检查新快照”和“续跑未完成作业”使用同一个最小间隔。作业为 pending 时，立即重跑仍会返回 `minimum_interval`。

修复后：

- pending 作业可立即续跑；
- success 后的新快照检查仍等待12小时；
- paused/失败作业仍保留退避；
- 每日请求预算继续生效。

### 3. SixV详情年份缺失

《灵魂伴侣》《麦迪的秘密》详情元数据没有年代字段，但列表标题明确以2026开头。旧解析器返回 `year=null`。

修复后，在详情年代缺失时只接受列表标题开头的4位合法年份作为兜底，两条均正确得到2026。

### 4. 剧集集合资源上下文丢失

`《莫得闲》全集`属于SixV电视剧栏目，条目级状态为“全集”，但磁力显示名仅为“1080p.HD国语中字无水印.mkv”。旧聚合没有把条目级“全集”传给资源，导致 `unknown_series_resources` 从0变1，正式回归门阻止发布。

没有使用强制发布。修复后资源为：

`全集 · 1080p.HD国语中字无水印.mkv`

且：

- `episode_label=全集`；
- `title_source=item_context`；
- `unknown_series_resources=0`；
- `cross_season_resources=0`。

## 代码修复

提交：

- `c05f508 fix(media): restore daily crawl and absorb sixv bursts`
- `7571f9a fix(media): expand source outage catch-up budgets`
- `e2066c5 fix(media): preserve series collection resource context`
- `c6b75c2 fix(media): resume pending source jobs immediately`

关键修复：

1. daily/audit systemd 服务通过 `/usr/bin/bash`运行脚本，不再依赖脚本执行位；
2. 三个 Linux `.sh`在Git中改为 `100755`；
3. 永久测试检查 systemd 必须通过bash执行；
4. 四源单次追赶上限按请求预算扩大；
5. SixV年份增加列表标题安全兜底；
6. 剧集资源继承可信条目级季集/全集上下文；
7. pending 作业立即续跑，成功和失败间隔语义分离。

## Revision 9生产结果

- pointer revision：9；
- release ID：`20260805T000000Z-8f0b833e`；
- pointer SHA：`8bcb332aeb16d7992a1fa078c54f9d3eec80ca7c25fb0021803ab3f75d7675d8`；
- Manifest SHA：`8b4929cf906e99e005f923ee4444d7ec09bf1aa81646353899476e600f3fd3bd`；
- 电影：247；
- 电视剧：249；
- 影视合计：496；
- 磁力：3892；
- cloud：0；
- 封面：441个唯一对象，所有影视封面完整；
- release对象：1454；
- unknown series resources：0；
- cross-season resources：0；
- 数据回归：0。

相对revision 8：

- 电影：217 → 247，+30；
- 电视剧：227 → 249，+22；
- 影视：444 → 496，+52；
- 磁力：3597 → 3892，+295。

发布收据：

- 阿里云：上传474，复用981；
- R2：上传472，复用983；
- R2与阿里云 current SHA一致；
- R2与阿里云 Manifest SHA一致。

## 四源最终状态

- SixV电影：100/100，pending 0，failed 0；
- Meijumi：100/100，pending 0，failed 0；
- SixV电视剧：100/100，pending 0，failed 0；
- DYTT：249/250，pending 0；唯一未覆盖项为站点返回404的`/i/120024.html`，已结构化记录为 `NOT_FOUND`，不阻塞发布。

## App更新边界

`syncMediaFeed()`会以 `forceRefresh=true`重新获取两个端点的`current.json`。72小时本地缓存只是离线兜底，不会阻止联网用户发现revision 9。用户重新进入或刷新资源页后应获取新Catalog。

## 验证

- SixV实时列表：17/17；
- SixV实时详情：17/17；
- 最终磁力Feed：17/17；
- 签名Catalog/Detail/Resources：17/17；
- 定向测试：64 passed；
- 全量非实时：432 passed，1 skipped，1 deselected；
- 枚举：241 / ALL VALID；
- compileall：PASS；
- Shell语法：PASS；
- diff check：PASS；
- 服务器镜像：`sha256:e2bf34fcfee10eaa8dc8ebab911d6f0273740731488bf7d45946aafde399683a`；
- systemd最终运行：exit 0 / Result=success。

唯一未纳入全量PASS的是无关实时搜索源`xiongmaogb`当时返回4条而测试阈值为5条，属于外部站点波动，不涉及影视流水线。

## 剩余风险

- 当前仍缺少外部主动告警；systemd/journal能记录失败，但没有在连续失败时主动通知运营人员。
- DYTT有一个长期404条目，应继续由快照替换自然淘汰，不应反复强抓。
- 四源仍存在品牌/主站相关性，后续需增加真正独立的电影与电视剧来源。
