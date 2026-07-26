# Resource Index 电影/电视剧多品牌稳定部署

系统采用“共享运行内核 + 每站独立适配器 + 品牌域名注册表 + 分类型严格聚合”。共享内核负责锁、冻结快照、断点恢复、请求预算、失败退避、字段持久化、跨来源去重、Feed和日志；每个站点只维护自身公开列表和详情解析逻辑。

## 1. 正式来源与目标

| source_id | 内容 | 正式抓取池 | 最小请求间隔 |
|---|---|---:|---:|
| `sixv` | 最新电影 | 100 | 10秒 |
| `dytt8899` | 最新电影补充 | 50 | 15秒 |
| `sixv-series` | 最新电视剧 | 50 | 10秒 |
| `meijumi` | 最新剧集补充 | 100 | 12秒 |

自动化始终更新兼容的部分聚合Feed，并仅在严格配额满足时更新正式目录：

```text
data\resource_index\media_latest_feed.json          部分兼容Feed
data\resource_index\movies_latest_100_feed.json    正式电影100
data\resource_index\series_latest_100_feed.json    正式电视剧100
data\resource_index\media_latest_200_feed.json     正式合并200
```

抓取池大于最终数量，是为了在跨品牌去重后仍保证电影100条、电视剧100条。若任一类型不足100条，手工严格聚合命令返回错误，不生成伪完整结果。

## 2. 一键本地运行

在Windows电脑上执行：

```bat
deploy\resource-index\run-media-offline.bat
```

首次运行会自动创建Python虚拟环境并安装锁定依赖，随后顺序执行：

```text
四个来源抓取或断点恢复
→ 严格跨品牌聚合
→ 标签与资源季集归一化
→ 跨季/未知季资源隔离
→ 电影100＋电视剧100质量门禁
→ 本地封面下载与内容哈希校验
→ App离线Bundle生成
→ 无网络离线审计
```

运行链只使用本地Python规则、SQLite状态机和PowerShell，不调用LLM，也不需要人工逐条判断。主动刷新最新列表时使用：

```bat
deploy\resource-index\run-media-offline.bat -Refresh
```

数据库选择不是按文件名判断。脚本会只读比较候选库的完整任务状态、成功rank覆盖、内容数和SQLite健康状态，优先复用证据最完整的数据库；任何候选库仍被活跃进程持锁时立即停止，避免并发重复抓取。

正式离线产物：

```text
data\resource_index\movie_app_bundle\feed.json
data\resource_index\movie_app_bundle\covers\
data\resource_index\series_app_bundle\feed.json
data\resource_index\series_app_bundle\covers\
data\resource_index\media_quality_report.json
data\resource_index\media_resource_quarantine.json
```

## 3. 品牌与镜像体系

品牌注册表：

```text
magnet\resource_index\config\movie_source_brands.json
```

域名角色：

- `primary`：正式主站；
- `official_mirror`：有发布页、跳转关系或内容指纹证据的同品牌镜像；
- `redirect_alias`：已验证跳转到正式主站的入口；
- `release_page`：品牌发布页，仅用于发现域名；
- `candidate`：候选站，默认不抓取；
- `discovery_portal`：导航页，不当作内容镜像。

当前正式镜像关系：

- SixV旧版：`6v520.com / 6v520.net / 6v520.cc`；
- `dy2018.com`是`dytt8899.com`的跳转别名；
- `dytt8.org`为独立模板，不归入DYTT8899镜像池；
- `dianyingtiantang.me`是导航入口，不作为内容镜像。

查看和低频探测：

```bat
python -m magnet.resource_index.cli list-movie-brands
python -m magnet.resource_index.cli probe-movie-brands --brand sixv --brand dytt8899 --yes
```

候选域名不会因一次可访问就自动升级为正式来源。

## 4. 安全边界

- 每个来源单进程、单并发；
- 自动网络检查至少间隔12小时；
- 连续失败后退避24、48、72小时；
- HTTP 403、429和访问挑战立即硬停；
- 本地物理请求预算耗尽使用独立错误码，不误判成站点限流；
- 每批5条默认预留12次物理请求，允许有限网络重试；
- 快照不变时不重抓详情；
- 完成任务重复运行保持0 HTTP；
- 不处理验证码，不绕过WAF，不模拟登录；
- 不推导、等待或绕过页面未公开的下载资源；
- 只访问品牌注册表和适配器明确允许的公开路径。

异常通道返回502时，先检查锁、PID、数据库rank和日志，不盲目重放命令。

## 5. 安装与自检

```bat
deploy\resource-index\setup.bat
```

```bat
deploy\resource-index\doctor.bat -Source sixv
deploy\resource-index\doctor.bat -Source dytt8899
deploy\resource-index\doctor.bat -Source sixv-series
deploy\resource-index\doctor.bat -Source meijumi
```

默认数量：SixV电影100、DYTT电影50、SixV电视剧50、美剧迷100。

## 6. 首次抓取与恢复

```bat
deploy\resource-index\run-latest.bat -Source sixv -Refresh
deploy\resource-index\run-latest.bat -Source dytt8899 -Refresh
deploy\resource-index\run-latest.bat -Source sixv-series -Refresh
deploy\resource-index\run-latest.bat -Source meijumi -Refresh
```

退出码：

```text
0   成功
1   配置、锁、数据库或不可恢复错误
2   pending/partial，可继续恢复
130 用户中断，状态已保存
```

恢复时执行同一命令，不带`-Refresh`：

```bat
deploy\resource-index\run-latest.bat -Source meijumi
```

限制单次批次数：

```bat
deploy\resource-index\run-latest.bat -Source sixv -MaxBatches 2
```

## 7. 安全自动化

管理四个正式来源并生成三份聚合Feed：

```bat
deploy\resource-index\run-movies-safe.bat
```

默认来源目标是独立的：

```text
sixv=100
dytt8899=50
sixv-series=50
meijumi=100
```

控制器会：

1. 12小时内检查过则0网络跳过；
2. 未完成任务沿用原冻结快照，只补缺失详情；
3. 完成任务低频检查列表；
4. 快照不变则不抓详情；
5. 快照变化时每次最多2批、每批5条；
6. 达到每日预算后停止；
7. 一个来源失败不阻断其他来源；
8. 每轮结束先更新部分兼容Feed；只有严格满足100+100时才逐文件原子替换正式三份目录，否则保留上一份完整目录。

查看状态：

```bat
deploy\resource-index\movie-sources-status.bat
```

安装Windows任务计划：

```bat
deploy\resource-index\install-movie-schedule.bat
```

默认每6小时触发，内部12小时门禁使多余触发0网络退出，计划任务设置为已有实例时`IgnoreNew`。

## 8. 正式来源输出

```text
data\resource_index\sixv_latest_100_urls.json
data\resource_index\sixv_latest_100_feed.json

data\resource_index\dytt8899_latest_50_urls.json
data\resource_index\dytt8899_latest_50_feed.json

data\resource_index\sixv-series_latest_50_urls.json
data\resource_index\sixv-series_latest_50_feed.json

data\resource_index\meijumi_latest_100_urls.json
data\resource_index\meijumi_latest_100_feed.json
```

数据库可通过`--db`复用原文件扩容；文件名中的旧数量不影响任务身份，因为任务以`source_id + target_count + snapshot_hash`隔离。迁移前建议使用SQLite backup API备份正式库。

## 9. 手工严格聚合

```bat
python -m magnet.resource_index.cli aggregate-media-feeds ^
  --feed data\resource_index\sixv_latest_100_feed.json ^
  --feed data\resource_index\dytt8899_latest_50_feed.json ^
  --feed data\resource_index\sixv-series_latest_50_feed.json ^
  --feed data\resource_index\meijumi_latest_100_feed.json ^
  --output data\resource_index\media_latest_200_feed.json ^
  --movie-output data\resource_index\movies_latest_100_feed.json ^
  --series-output data\resource_index\series_latest_100_feed.json ^
  --movie-limit 100 ^
  --series-limit 100 ^
  --strict-kind-limits
```

聚合规则：

- 电影按规范标题和年份识别；
- 剧集按规范剧名和当前季识别；
- IMDb仅作为辅助别名，不作为唯一主键；
- 缺季数记录只有在所有别名都指向唯一明确季时才合并；
- 冲突候选保持独立，防止未知季桥接不同季；
- 磁力按`info_hash`去重，网盘/协议按类型、提供方和URL去重；
- 同一来源同一内容只保留一份来源证据；
- 保留跨品牌`source_variants`和全部互补资源。

## 10. 数据质量与评分回写契约

最终导出会统一清理类型和国家字段，解析资源级季集身份，并将与明确季不一致或无法证明季号的资源写入隔离清单。正式Feed的质量门禁要求：脏标签、跨季正式资源、丢失集数标题和空资源条目均为0。

App Bundle只保留客户端支持的`magnet/cloud`资源；完整审计Feed仍保留其他公开资源证据。若前100候选中存在App不支持的资源类型，Bundle构建器会从更大的合格候选池顺序补位，仍严格输出100条。

schema 0008预留以下评分字段：

```text
rotten_tomatoes_rating
rotten_tomatoes_rating_text
rotten_tomatoes_url
bangumi_rating
bangumi_rating_text
bangumi_subject_id
bangumi_url
```

当前字段全部为空，由独立评分工具后续回写。爬虫详情更新采用非空覆盖规则，评分工具已经写入的值不会被下一轮空值抓取清除。烂番茄按0—100百分制，Bangumi按0—10分制。

## 11. 迁移保护

生产迁移必须满足：

- 版本号从0001连续到当前版本；
- 不允许两个SQL文件使用同一版本号；
- 已执行迁移checksum不可静默变化；
- 已知早期0007 IMDb开发变体只在精确checksum且结构指纹完整时归档，再执行正式0007品牌迁移；
- 任何部分结构、伪造checksum或索引不一致仍立即失败。

## 12. 当前边界

- App预构建已使用电影100和电视剧100两份完整离线Bundle，正常运行不依赖资源站封面域名；
- EZTV、YTS、蜜柑、动漫花园等仍在候选池，未完成正式适配与门禁前不自动抓取；
- 页面未公开的资源不会推导或绕过；
- SQLite为单机单写，不支持多机同时写共享数据库。
