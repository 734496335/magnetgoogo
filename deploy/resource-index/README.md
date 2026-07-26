# Resource Index 多站点稳定部署

Resource Index 采用“一套运行内核 + 每站独立适配器”的结构。统一内核负责锁、快照、请求预算、恢复、去重、Feed、日志和低频调度；SixV 与 DYTT8899 分别维护自己的编码、分页和详情解析逻辑。

当前来源：

- `javbus`：历史成人内容来源；
- `sixv`：6V 最新电影，默认 50 部；
- `dytt8899`：电影天堂最新电影，默认 25 部。

电影来源使用独立 SQLite 和 Feed。单站改版、限流或解析失败不会污染其他站点。

## 1. 安全边界

脚本只能降低触发反爬的概率，不能承诺永远不会被限制。当前策略：

- 单进程、单并发；
- SixV 每次 HTTP 尝试至少间隔 10 秒；
- DYTT8899 每次 HTTP 尝试至少间隔 15 秒；
- 自动检查间隔至少 12 小时；
- SixV 每日最多预留 80 次请求，DYTT8899 每日最多预留 50 次；
- 快照未变化时不重新抓取详情；
- 403、429、访问挑战或站点硬停止立即暂停；
- 连续失败后自动退避为至少 24、48、72 小时，成功后恢复 12 小时检查；
- 不处理验证码，不绕过 WAF，不模拟登录；
- 不绕过 DYTT 延迟释放的隐藏磁力资源，只保存页面当前公开的链接；
- DYTT 仅访问公开电影分类和 `/i/` 详情路径。

自动调度在请求前预留最坏情况预算。即使进程崩溃或外部通道返回 502，预留额度也不会自动释放并形成高频重试。

## 2. 环境与安装

要求 Windows 10/11 或 Windows Server、Python 3.10+、可访问目标站点、至少 100 MB 可用空间。最小直接依赖：

- `beautifulsoup4==4.15.0`
- `curl_cffi==0.15.0`
- `Pillow`（SixV封面压缩和App离线导出）

首次安装：

```bat
deploy\resource-index\setup.bat
```

按来源自检：

```bat
deploy\resource-index\doctor.bat -Source sixv
deploy\resource-index\doctor.bat -Source dytt8899
```

未传 `-Count` 时自动使用来源默认值：JavBus 100、SixV 50、DYTT8899 25。

## 3. 首次初始化

SixV 最新 50 部：

```bat
deploy\resource-index\run-latest.bat -Source sixv -Refresh
```

DYTT8899 最新 25 部：

```bat
deploy\resource-index\run-latest.bat -Source dytt8899 -Refresh
```

需要控制单次运行长度：

```bat
deploy\resource-index\run-latest.bat -Source dytt8899 -MaxBatches 2
```

退出码 `2` 表示任务尚未完成。再次执行同一命令即可续跑；恢复时不要带 `-Refresh`。

SixV 完整抓取成功后，现有 `run-latest.bat` 流程还会同步缺失封面到 SQLite，并导出：

```text
sixv_app_bundle\feed.json
sixv_app_bundle\covers\*.jpg
```

已入库封面再次运行时保持零封面网络请求。

## 4. 安全自动化

同时管理 SixV 与 DYTT8899：

```bat
deploy\resource-index\run-movies-safe.bat
```

只管理一个来源：

```bat
deploy\resource-index\run-movies-safe.bat -Sources dytt8899
```

控制器会根据持久化状态自动选择：

1. 12 小时内运行过：直接跳过，零网络；
2. 上次任务未完成：沿用原快照，只补缺失详情；
3. 当前任务已完成：低频获取最新列表；
4. 列表未变化：停止，不重抓详情；
5. 列表有变化：每次最多处理 2 批，每批 5 条；
6. 达到每日预算：停止到次日；
7. 站点异常或解析失败：按 24/48/72 小时逐级退避。

查看自动化策略、每日剩余额度和任务覆盖：

```bat
deploy\resource-index\movie-sources-status.bat
```

### Windows 任务计划程序

一键安装当前用户的安全抓取任务：

```bat
deploy\resource-index\install-movie-schedule.bat
```

默认每 6 小时触发 `run-movies-safe.bat`，内部 12 小时门禁会让多余触发零网络退出，并设置“已有实例时不启动新实例”。安装脚本不会绕过每日请求预算。

只调度 DYTT8899：

```bat
deploy\resource-index\install-movie-schedule.bat -Sources dytt8899
```

删除任务：

```bat
deploy\resource-index\install-movie-schedule.bat -Remove
```

也可以手工建立任务，但应使用项目所在账户运行，不设置分钟级无限重试，并选择“不启动新的实例”。

## 5. 输出文件

默认目录：

```text
data\resource_index
```

SixV：

```text
sixv_latest_50.db
sixv_latest_50_urls.json
sixv_latest_50_feed.json
sixv_latest_50.log
sixv_app_bundle\feed.json
sixv_app_bundle\covers\*.jpg
```

DYTT8899：

```text
dytt8899_latest_25.db
dytt8899_latest_25_urls.json
dytt8899_latest_25_feed.json
dytt8899_latest_25.log
```

- `.db`：电影详情、公开资源、任务、封面资产和自动化预算状态；
- `_urls.json`：冻结列表顺序；
- `_feed.json`：供 App 展示；
- `.log`：追加运行日志。

## 6. DYTT资源说明

DYTT 当前详情页公开提供 `jianpian://` 专属播放器链接，Feed 中保存为：

```text
resource_type = player
provider = jianpian
```

如果静态 HTML 直接出现 magnet、thunder、ftp、ed2k 或公开网盘链接，解析器会保存。不会拆解播放器协议中的底层地址，也不会等待或绕过页面说明的延迟磁力释放机制。

## 7. 状态与恢复

查看单站持久化任务：

```bat
deploy\resource-index\status.bat -Source sixv
deploy\resource-index\status.bat -Source dytt8899
```

电脑重启、网络失败或 `Ctrl+C` 后，重新执行对应 `run-latest` 命令，不带 `-Refresh`。运行器会用数据库实际覆盖核对快照，只处理缺失 URL。

解析器升级后，只重抓当前快照中缺类型或简介的电影：

```bat
deploy\resource-index\run-latest.bat -Source sixv -ReparseIncomplete
deploy\resource-index\run-latest.bat -Source dytt8899 -ReparseIncomplete
```

## 8. 单实例与迁移

每个 SQLite 数据库绑定一个 `.lock` 文件。同一数据库只允许一个写进程。同机死亡 PID 的陈旧锁会自动恢复；跨电脑复制数据时必须先停止原电脑写入，再复制整个 `data\resource_index` 目录。

不支持多台电脑同时写同一个网络共享 SQLite。不要同时使用普通 `crawl` 与 `crawl-latest` 写同一数据库。

## 9. 退出码

```text
0   成功、自动跳过或安全检查完成
1   配置、环境、锁或不可恢复错误
2   手动 crawl-latest 尚未完成，可继续恢复
130 用户中断，状态已保存
```

## 10. App 接入

SixV App离线构建继续读取 `sixv_app_bundle`。DYTT列表读取 `dytt8899_latest_25_feed.json`。SixV 与 DYTT Feed 使用同一 `movie-feed/1` 字段结构，但保持来源独立。App可以在展示层按更新时间合并，也可以按来源分区；不要在抓取层把不同站点解析逻辑合并成一个通用CSS选择器。

运维时保留日志和 `_urls.json`，停止写入后再备份数据目录。每次升级代码先运行 `doctor.bat` 和 `movie-sources-status.bat`。
