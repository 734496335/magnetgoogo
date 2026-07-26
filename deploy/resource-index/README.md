# Resource Index 电影/电视剧多品牌稳定部署

系统采用“一套共享运行内核 + 每站独立适配器 + 品牌域名注册表”。共享内核负责锁、快照、断点恢复、请求预算、失败退避、去重、Feed和日志；各站点只负责自己的列表和详情解析。

正式来源：

- `sixv`：6V最新电影，默认50部；
- `dytt8899`：电影天堂最新电影，默认25部；
- `sixv-series`：6V最新电视剧，默认50条；
- `meijumi`：美剧迷最新剧集更新，默认50条。

统一输出 `media_latest_feed.json`，将电影和电视剧按更新时间混排。同一品牌的镜像不会重复计数；不同品牌的同一内容会合并资源并保留全部来源证据。

## 1. 品牌与镜像体系

品牌注册表：

```text
magnet\resource_index\config\movie_source_brands.json
```

域名角色包括：

- `primary`：正式主站；
- `official_mirror`：有发布页或内容指纹证据的同品牌镜像；
- `redirect_alias`：已验证跳转到正式主站的入口；
- `release_page`：品牌发布页，仅用于发现域名；
- `candidate`：候选站，默认不抓取；
- `discovery_portal`：导航页，不当作内容镜像。

“名字相似”不等于“同品牌镜像”。正式镜像必须有发布页、跳转关系、相同内容指纹或运行证据。当前已验证：

- SixV旧版镜像：`6v520.com / 6v520.net / 6v520.cc`；
- DYTT入口：`dy2018.com`跳转到`dytt8899.com`；
- `dytt8.org`是独立模板，不归入DYTT8899镜像池；
- `dianyingtiantang.me`是导航入口，不当作内容源。

查看品牌体系：

```bat
python -m magnet.resource_index.cli list-movie-brands
```

手工低频探测正式端点：

```bat
python -m magnet.resource_index.cli probe-movie-brands --brand sixv --brand dytt8899 --yes
```

探测候选域名必须显式增加：

```bat
python -m magnet.resource_index.cli probe-movie-brands --include-candidates --yes
```

探测只输出报告，不自动把候选升级为正式源。

## 2. 安全边界

低频策略只能降低触发反爬的概率，不能承诺永远不受限制。

- 单进程、单并发；
- SixV电影/剧集请求间隔至少10秒；
- DYTT至少15秒；
- 美剧迷至少12秒；
- 自动网络检查至少间隔12小时；
- 连续失败后退避24、48、72小时；
- 403、429、访问挑战或来源硬停止立即暂停；
- 每日请求预算按来源独立持久化；
- 快照不变时不重抓详情；
- 不处理验证码，不绕过WAF，不模拟登录；
- 不推导、等待或绕过页面未公开的下载资源；
- 只访问品牌注册表和来源适配器允许的公开路径。

自动化请求前预留最坏情况预算，正常完成后退还未使用额度；进程崩溃时保留预留额度，避免异常形成快速重试。

## 3. 安装与自检

环境要求：Windows 10/11或Windows Server、Python 3.10+、至少100 MB可用空间。

```bat
deploy\resource-index\setup.bat
```

按来源自检：

```bat
deploy\resource-index\doctor.bat -Source sixv
deploy\resource-index\doctor.bat -Source dytt8899
deploy\resource-index\doctor.bat -Source sixv-series
deploy\resource-index\doctor.bat -Source meijumi
```

默认数量：JavBus 100、SixV电影50、DYTT电影25、SixV电视剧50、美剧迷50。

## 4. 首次抓取与恢复

```bat
deploy\resource-index\run-latest.bat -Source sixv -Refresh
deploy\resource-index\run-latest.bat -Source dytt8899 -Refresh
deploy\resource-index\run-latest.bat -Source sixv-series -Refresh
deploy\resource-index\run-latest.bat -Source meijumi -Refresh
```

中断后执行同一命令但不要带`-Refresh`：

```bat
deploy\resource-index\run-latest.bat -Source meijumi
```

每次只处理少量批次：

```bat
deploy\resource-index\run-latest.bat -Source sixv-series -MaxBatches 2
```

退出码2表示任务未完成，可继续恢复，不代表数据损坏。

解析器升级后，只重抓当前快照中字段不完整的记录：

```bat
deploy\resource-index\run-latest.bat -Source meijumi -ReparseIncomplete
```

电影会检查类型/简介；电视剧还会检查季数/集数。已经完整的记录不会重抓。

## 5. 安全自动化

同时管理四个正式来源：

```bat
deploy\resource-index\run-movies-safe.bat
```

只检查指定来源：

```bat
deploy\resource-index\run-movies-safe.bat -Sources sixv-series,meijumi
```

每轮结束后自动生成：

```text
data\resource_index\media_latest_feed.json
```

控制器会：

1. 12小时内运行过则零网络跳过；
2. 未完成任务沿用原快照，只补缺失详情；
3. 完成任务低频检查列表；
4. 快照未变化则不抓详情；
5. 快照变化时每次最多2批、每批5条；
6. 达到每日预算后停止到次日；
7. 来源异常按24/48/72小时退避；
8. 一个来源失败不会阻断其他来源和已有聚合Feed。

查看状态：

```bat
deploy\resource-index\movie-sources-status.bat
```

## 6. Windows任务计划

安装当前用户任务，默认每6小时触发：

```bat
deploy\resource-index\install-movie-schedule.bat
```

内部12小时门禁会让多余触发零网络退出，任务配置为已有实例时`IgnoreNew`，不会并行启动。

删除任务：

```bat
deploy\resource-index\install-movie-schedule.bat -Remove
```

安装脚本不会绕过来源每日预算，也不会自动探测候选站。

## 7. 正式输出

```text
data\resource_index\sixv_latest_50.db
data\resource_index\sixv_latest_50_feed.json

data\resource_index\dytt8899_latest_25.db
data\resource_index\dytt8899_latest_25_feed.json

data\resource_index\sixv-series_latest_50.db
data\resource_index\sixv-series_latest_50_feed.json

data\resource_index\meijumi_latest_50.db
data\resource_index\meijumi_latest_50_feed.json

data\resource_index\media_latest_feed.json
```

每个来源还有`_urls.json`冻结快照和追加式`.log`。

统一Feed字段包括：

- `content_kind`：`movie`或`series`；
- 标题、年份、封面、简介、类型、导演演员；
- `series_title / season_number / episode_number / update_status`；
- `resources`：磁力、公开网盘、公开播放器或下载协议；
- `source_variants`：各来源详情URL、品牌、端点和更新时间；
- `source_count / brand_count`：补充来源数量；
- `media_identity`：跨来源去重身份。

## 8. 聚合与去重

手工重建统一Feed：

```bat
python -m magnet.resource_index.cli aggregate-media-feeds ^
  --feed data\resource_index\sixv_latest_50_feed.json ^
  --feed data\resource_index\dytt8899_latest_25_feed.json ^
  --feed data\resource_index\sixv-series_latest_50_feed.json ^
  --feed data\resource_index\meijumi_latest_50_feed.json ^
  --output data\resource_index\media_latest_feed.json
```

电影按规范标题+年份去重，IMDb作为辅助证据；剧集按规范剧名+当前季去重。只有一边缺季数时，必须同名且只有一个兼容季候选才允许合并，避免不同季误合并。

## 9. 单实例与迁移

每个SQLite数据库绑定一个`.lock`文件，只允许一个写进程。同机死亡PID的陈旧锁会自动恢复；跨电脑迁移前必须先停止原电脑写入，再复制完整`data\resource_index`目录。

不支持多机同时写共享SQLite，也不要让普通`crawl`和`crawl-latest`同时写同一数据库。

## 10. 当前边界

- App当前仍使用SixV离线电影Bundle；统一电影/电视剧Feed已准备好，App展示接入属于独立产品批次；
- 候选站如EZTV、YTS、蜜柑、动漫花园等仅进入品牌候选池，未经过正式适配器和运行门禁前不会自动抓取；
- 页面没有公开资源时不会推导或绕过隐藏资源；
- 站点改版可能暂停该来源，但不会高频重试或影响其他来源。
