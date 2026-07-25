# Resource Index 跨电脑稳定部署

本目录用于在 Windows 电脑上部署 JavBus 与 6V 最新列表抓取。运行器保持单并发、每次 HTTP 尝试至少间隔 10 秒，并把快照、批次进度、失败次数和最终 Feed 持久化。

## 1. 环境要求

- Windows 10/11 或 Windows Server
- Python 3.10 或更高版本，安装时勾选 Python Launcher 或 PATH
- 可以访问目标站点的网络环境
- 至少 100 MB 可用磁盘空间
- 项目目录需要可写

不需要安装完整开发依赖。部署脚本只安装：

- `beautifulsoup4==4.15.0`
- `curl_cffi==0.15.0`

## 2. 首次安装

在项目根目录双击或执行：

```bat
deploy\resource-index\setup.bat
```

部署 6V 电影来源时也可以直接执行：

```bat
deploy\resource-index\setup.bat -Source sixv -Count 50
```

脚本会：

1. 创建独立环境 `.venv-resource-index`；
2. 安装最小运行依赖；
3. 创建 `data\resource_index`；
4. 初始化 SQLite schema；
5. 运行离线部署自检。

重新检查环境：

```bat
deploy\resource-index\doctor.bat
```

6V 环境检查：

```bat
deploy\resource-index\doctor.bat -Source sixv -Count 50
```

所有检查均为 `ok: true` 后再开始真实抓取。

## 3. 抓取最新列表

JavBus 最新 100 条：

```bat
deploy\resource-index\run-latest.bat -Source javbus -Count 100 -Refresh
```

6V 最新电影 50 部：

```bat
deploy\resource-index\run-latest.bat -Source sixv -Count 50 -Refresh
```

输出目录默认为：

```text
data\resource_index
```

JavBus 主要文件：

```text
javbus_latest_100.db
javbus_latest_100_urls.json
javbus_latest_100_feed.json
javbus_latest_100.log
```

6V 主要文件：

```text
sixv_latest_50.db
sixv_latest_50_urls.json
sixv_latest_50_feed.json
sixv_latest_50.log
sixv_app_bundle\feed.json
sixv_app_bundle\covers\*.jpg
```

6V 完整抓取成功后，`run-latest.bat` 会自动继续：

1. 下载缺失封面并压缩写入 `sixv_latest_50.db`；
2. 已入库封面再次运行时保持零网络请求；
3. 从 SQLite 导出 `sixv_app_bundle`，供 App 离线打包。

- `.db`：完整内容、人物、标签、磁力、网盘资源、电影封面二进制和作业状态；
- `_urls.json`：本轮最新 100 条的冻结顺序；
- `_feed.json`：供 App 直接展示的排序 Feed；
- `.log`：追加写入的运行日志。

## 4. 中断和恢复

正常关闭窗口、网络失败、电脑重启或手动按 `Ctrl+C` 后，重新执行同一命令即可恢复：

```bat
deploy\resource-index\run-latest.bat -Source javbus -Count 100
```

6V 恢复命令：

```bat
deploy\resource-index\run-latest.bat -Source sixv -Count 50
```

恢复时不会重新抓取已经存在的详情 URL。运行器会：

1. 读取原快照；
2. 恢复上一次未完成的批次；
3. 用数据库来源观测核对实际已入库项；
4. 只抓取缺失 URL；
5. 完成后重新原子生成 Feed。

不要在恢复时使用 `-Refresh`。`-Refresh` 表示放弃继续旧快照，重新获取当前最新列表。

## 5. 控制单次运行长度

需要让任务每次只跑少量批次时：

```bat
deploy\resource-index\run-latest.bat -MaxBatches 2
```

退出码 `2` 表示作业仍未完成，不代表数据损坏。再次运行同一命令继续即可。

默认每批 5 条：

```bat
deploy\resource-index\run-latest.bat -BatchSize 5
```

不建议随意提高批量。较小批次更容易在断电、网络切换或系统重启后精确恢复。

查看当前持久化进度：

```bat
deploy\resource-index\status.bat -Source javbus -Count 100
```

查看 6V 任务：

```bat
deploy\resource-index\status.bat -Source sixv -Count 50
```

状态会显示已覆盖数量、失败数量、请求次数和未完成 URL，不会发起网络请求。

## 6. 获取下一轮数据与修复旧解析结果

重新获取新的 JavBus 100 条或 6V 50 部时，使用对应来源并加 `-Refresh`：

```bat
deploy\resource-index\run-latest.bat -Source sixv -Count 50 -Refresh
```

SQLite 会继续保留历史内容，Feed 只展示新快照对应的来源记录。

6V 解析器升级后，只修复当前快照中缺少类型或简介的记录：

```bat
deploy\resource-index\run-latest.bat -Source sixv -Count 50 -ReparseIncomplete
```

该参数不会刷新列表快照，也不会重抓字段已经完整的电影。

## 7. 单实例保护

同一个 SQLite 数据库只能同时运行一个 `crawl-latest`。第二个进程会检测与数据库绑定的 `.lock` 文件并拒绝启动，避免重复抓取和并发写入。

如果同一电脑异常断电留下锁文件，下一次启动会检查原进程是否仍存在；确认原进程已不存在后自动恢复陈旧锁。

如果把数据目录复制到另一台电脑时意外带上 `.lock` 文件，运行器无法跨电脑验证原进程。必须先确认原电脑已经停止写入，再手动删除对应 `.lock` 文件。共享网络目录不支持多台电脑同时写入同一个 SQLite 数据库。

不要手动同时运行普通 `crawl` 和 `crawl-latest` 写入同一个数据库。

## 8. 退出码

```text
0   快照覆盖完整，Feed 已生成
1   配置、环境或锁冲突
2   作业未完成，可再次运行恢复
130 用户中断，状态已安全保存
```

## 9. App 接入

App 的“资源”模块只使用 6V 影视数据，不再接入 JavBus 成人 Feed。

构建时读取：

```text
data\resource_index\sixv_app_bundle\feed.json
data\resource_index\sixv_app_bundle\covers\*.jpg
```

`feed.json` 保留来源列表排名，并包含 `recommended`、`highlight_labels`、类型、清晰度、字幕、豆瓣/IMDb、导演演员和磁力/网盘资源字段。封面由 SQLite 导出为本地图片，随 APK 打包，手机无需访问 6V 图片域名。

## 10. 运维建议

- 每次升级代码后先执行 `doctor.bat`；
- 停止抓取任务后，再对整个 `data\resource_index` 目录做一致性备份；
- 日志持续追加，不要依赖终端窗口作为唯一运行证据；
- 不要删除未完成作业的 `_urls.json`，否则无法按原快照精确恢复；
- 迁移项目目录时，至少复制整个 `data\resource_index` 目录；
- Windows 任务计划程序应设置为“不启动新的实例”，不要并行运行同一任务。
