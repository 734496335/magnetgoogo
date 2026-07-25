# Resource Index 6V 最新电影 50 部实现与真实运行证据

日期：2026-07-25

基线提交：`1f526d4d45f2455eaab1d011dfb5d5c64938a08b`

开发分支：`feat/resource-index-sixv-latest50`

## 1. 目标

将 `https://www.6v520.com/` 作为第二个真实 latest 来源，冻结并持久化最新电影 50 部，同时保留页面红色推荐语义，并复用已有跨电脑部署、单实例锁、中断恢复、原子 Feed 和完成后零网络重放能力。

本轮不把普通电影写入既有成人内容表。普通电影使用独立 schema，避免 `adult=1` 约束和业务语义污染。

## 2. 来源结构

- 最新电影分类第一页：`/dy/`，25 条。
- 第二页：`/dy/index_2.html`，25 条。
- 两页按返回顺序组成最新 50 部冻结快照。
- 红色推荐由标题节点中的 `font color="#FF0000"` 或等价红色样式识别。
- 红色语义保存为：
  - `recommended=true`
  - `highlight_labels=["推荐"]`
- 详情页一次请求可获得标题、年份、地区、类型、语言、上映日期、导演演员、豆瓣/IMDb、简介、封面 URL、磁力和网盘资源。

## 3. 数据契约

schema 从 `0003` 升级到 `0004`，新增：

- `movie_items`
- `movie_resources`

电影记录与原成人内容表完全隔离。

电影 Feed 主要字段：

- `rank`
- `movie_id`
- `listing_title`
- `title`
- `original_title`
- `year`
- `update_date`
- `release_date`
- `duration_minutes`
- `countries`
- `genres`
- `languages`
- `directors`
- `actors`
- `imdb_id`
- `douban_rating`
- `cover_source_url`
- `synopsis`
- `recommended`
- `highlight_labels`
- `quality_tags`
- `resources`

资源支持：

- magnet
- 迅雷云盘
- 夸克云盘
- 百度网盘

## 4. 解析兼容

真实页面存在三类详情模板：

1. 元数据分别位于直接子级 `div`；
2. 元数据分别位于直接子级 `p`；
3. 全部元数据位于单个 `p`，字段依靠 `br`、链接和 `◎` 标记分隔。

已兼容：

- GB2312/GBK 页面按 GB18030 解码；
- `中文名 -> 标题`；
- `主演 -> 演员`；
- 中英文冒号；
- 多字段紧凑段落；
- 演员、编剧和简介续行；
- 源站畸形文本残片 `片">`；
- 详情页缺少类别时，从列表标题 `《片名》` 前的固定类型词回退；
- 红色标题推荐；
- 4K、1080p、HD、BD、双语、字幕和无水印标签。

## 5. 数据非退化

电影 upsert 不再用空数组覆盖历史非空结构化字段。

以下字段只有新值非空时才覆盖：

- countries
- genres
- languages
- directors
- actors
- quality_tags

解析器升级后新增：

```text
--reparse-incomplete
```

该参数只重新抓取当前 6V 快照中缺少类型或简介的电影，不刷新列表快照，也不重抓字段已经完整的电影。

## 6. 运行恢复问题与修复

真实运行发现 Windows 陈旧 PID 探测可能由 `os.kill(pid, 0)` 抛出 `SystemError`，而不是普通 `OSError`。

已修复：

- Windows `SystemError` 视为 PID 不存在；
- 同机死亡进程留下的锁可自动恢复；
- 真实仍存活 PID 继续拒绝第二实例。

6V Runner 同时覆盖：

- Ctrl+C 中断后未访问项回退为 `pending/attempts=0`；
- 当前失败项保留一次尝试；
- 限流或访问挑战后立即暂停本次运行，不继续下一批；
- 恢复仅处理失败项和后续未访问项；
- 完成后普通重复运行零 ingest run、零 HTTP。

## 7. 真实 50 部结果

正式输出目录：

```text
D:\lpproduct\magnet\data\resource_index
```

生成文件：

```text
sixv_latest_50.db
sixv_latest_50_urls.json
sixv_latest_50_feed.json
sixv_latest_50.log
```

最终指标：

```text
冻结来源记录：50
Feed 记录：50
排名连续：1..50
红色推荐：9
电影记录：50
资源总数：134
磁力：71
网盘资源：63
  百度：21
  夸克：21
  迅雷：21
缺失标题：0
缺失封面 URL：0
无资源电影：0
缺失类型：0
缺失简介：0
标题正文污染：0
畸形类型标签：0
推荐标签不一致：0
重复详情 URL：0
重复资源 URL：0
运行中任务：0
失败任务项：0
```

第一部：`寒战1994`

第 50 部：`停下那辆火车!`

文件大小：

```text
sixv_latest_50.db          544768 bytes
sixv_latest_50_urls.json    22537 bytes
sixv_latest_50_feed.json   166259 bytes
sixv_latest_50.log           8851 bytes
```

## 8. 502 断线恢复证据

DevSpace 长命令两次返回 502，但后台进程仍继续执行。

本轮没有根据 502 盲目重放，而是先检查：

- lock 文件；
- 锁所属 PID；
- latest job 状态；
- item 状态；
- running ingest run。

真实结果证明：

- 中断前已原子入库的电影被恢复逻辑识别；
- 后续运行跳过这些 URL；
- 最终 50/50 成功；
- 锁正常释放；
- 无永久 running run。

最终任务记录：

```text
snapshot_http_requests=2
detail_http_requests=109
status=success
covered_count=50
pending_count=0
running_count=0
failed_count=0
```

`detail_http_requests` 是已正常终结批次的持久化计数；被外部强制终止的进程中，已完成原子 upsert 但尚未来得及持久化 request budget 的请求不会被该字段完整反映。

## 9. 零重放证据

完成后再次执行普通恢复命令：

```text
BEFORE ingest_runs=28, sum(http_requests)=109, job_detail_requests=109
AFTER  ingest_runs=28, sum(http_requests)=109, job_detail_requests=109
```

证明完成快照的普通重复运行不会创建新 run，也不会访问网站。

显式 `--reparse-incomplete` 属于人工要求的修复操作，不属于普通零重放路径。

## 10. Windows 部署

部署脚本新增来源参数：

```text
-Source javbus
-Source sixv
```

6V 首次安装和检查：

```bat
deploy\resource-index\setup.bat -Source sixv -Count 50
deploy\resource-index\doctor.bat -Source sixv -Count 50
```

新快照：

```bat
deploy\resource-index\run-latest.bat -Source sixv -Count 50 -Refresh
```

恢复：

```bat
deploy\resource-index\run-latest.bat -Source sixv -Count 50
```

查看状态：

```bat
deploy\resource-index\status.bat -Source sixv -Count 50
```

修复不完整旧解析：

```bat
deploy\resource-index\run-latest.bat -Source sixv -Count 50 -ReparseIncomplete
```

使用全新 Python 3.13.13 虚拟环境，只安装冻结最小依赖后，setup/doctor/schema 0004 PASS。从项目目录外调用 doctor/status 也 PASS。

## 11. 自动化门禁

```text
6V 专项：13 passed
resource_index：119 passed
all magnet non-integration：182 passed, 2 deselected
validate_enum：241/241 ALL VALID
compileall：PASS
git diff --check：PASS
PowerShell parse：4/4 PASS
sixv doctor：PASS
sixv latest-status：success, 50/50
```

专项反例覆盖：

- GB2312/GB18030；
- 红色推荐；
- 三种详情 DOM 模板；
- 同义标签；
- 紧凑多字段段落；
- 畸形标签清洗；
- 列表类型回退；
- 磁力和网盘提取码；
- schema 0004；
- upsert 幂等和非退化；
- reparse incomplete；
- Ctrl+C；
- 限流暂停；
- 中断恢复；
- 完成后零网络重放；
- Windows 无效 PID `SystemError`。

## 12. 边界

- 当前封面以远程 URL 保存，没有把图片二进制写入 SQLite。
- 当前仍为单机 SQLite writer，不支持多台电脑并发写同一数据库。
- 当前不是 Windows Service，可使用任务计划程序但必须设置“不启动新实例”。
- 电影 Feed/API/App 页面接入不在本提交范围。
- 正式推广前仍建议对最终提交执行独立 clean-worktree 对抗复验。
