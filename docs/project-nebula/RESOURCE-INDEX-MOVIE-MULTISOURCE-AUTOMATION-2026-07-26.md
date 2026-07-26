# Resource Index 电影多来源低频自动化闭环

日期：2026-07-26（UTC+8）

## 1. 架构裁决

电影资源抓取采用“一套共享运行内核 + 每个站点独立适配器”。不采用一个通用 CSS 解析器兼容所有网站。

共享内核负责：

- 数据库绑定的单实例锁；
- 最新列表冻结快照、逐 URL 状态与断点恢复；
- 请求间隔、每日预算、失败退避和自动化状态；
- 内容去重、SQLite 持久化、原子 Feed 和追加日志；
- 完成后零网络重放和跨电脑部署入口。

独立适配器负责：

- 列表入口、分页与最新顺序；
- 页面编码和详情 DOM；
- 元数据、封面及页面当前公开的资源协议；
- 来源域名与公开路径限制。

单站改版、限流或解析错误只暂停该来源，不污染其他来源数据库和 Feed。

## 2. 来源策略

### SixV

- 来源：`https://www.6v520.com/`
- 默认快照：最新电影 50 部；
- 最小请求间隔：10 秒；
- 自动检查最小间隔：12 小时；
- 每日硬预算：80 次；
- 公开路径：`/dy/`；
- 本次 HTTP 实测根目录 `robots.txt` 返回 404，因此采用显式域名/路径白名单和更保守频率。

### DYTT8899

- 来源：`https://www.dytt8899.com/index.html`
- 最新电影分类：`/html/gndy/dyzz/index.html`；
- 默认快照：25 部；
- 最小请求间隔：15 秒；
- 自动检查最小间隔：12 小时；
- 每日硬预算：50 次；
- 详情只允许同域 `/i/*.html`。

本次 HTTP 实测 `robots.txt` 明确禁止 `/d/` 与多个 `/e/` 后台路径；适配器不访问这些目录。列表解析严格限定 `table.tbspan a.ulink`，不会把侧栏经典推荐误判为最新电影。

低频策略只能降低触发限制的概率，不能承诺永远不会被站点限制。系统不使用代理轮换、随机账号、验证码处理、WAF 绕过或登录模拟。

## 3. 安全自动化契约

- 单进程、单并发；
- 完成快照至少 12 小时后才允许再次检查列表；
- 快照未变化时只消耗列表请求，不重新抓取详情；
- 上一任务未完成时沿用原快照，不重新获取列表；
- 每次自动调用最多 2 批，每批 5 条；
- 请求前事务性预留本次最坏请求额度；
- 正常结束退还未使用额度；
- 进程崩溃按全部预留额度计费，避免崩溃形成快速重试；
- 连续失败后的网络退避为 24、48、72 小时，成功后恢复 12 小时；
- 403、429、访问挑战和来源硬停止立即暂停；
- 多来源逐站隔离执行，一个来源失败不阻止其他来源；
- 候选写入快照前校验 HTTPS、注册 Origin、公开路径、连续 rank、唯一 URL 和 source key。

站点当前没有提供稳定的 ETag/Last-Modified，因此没有伪造 HTTP 条件请求。系统使用低频列表请求和规范化快照哈希判断是否发生变化。

## 4. DYTT资源边界

当前 DYTT 详情页公开提供的是 `jianpian://` 专属播放器链接。系统原样保存为：

```text
resource_type = player
provider = jianpian
```

如果静态 HTML 直接出现 magnet、thunder、ftp、ed2k 或公开网盘链接，也会保存。不会拆解播放器协议中的底层地址，不会等待或绕过页面说明的延迟磁力释放机制，`#downlist` 中的占位值不会作为资源写入。

普通 `magnet|cloud` 保存在原 `movie_resources`；`download|player` 保存在新增 `movie_external_resources`，Feed 层统一输出。

## 5. DYTT正式真实数据

正式文件：

```text
D:\lpproduct\magnet\data\resource_index\dytt8899_latest_25.db
D:\lpproduct\magnet\data\resource_index\dytt8899_latest_25_urls.json
D:\lpproduct\magnet\data\resource_index\dytt8899_latest_25_feed.json
D:\lpproduct\magnet\data\resource_index\dytt8899_latest_25.log
```

最终审计：

- 快照、数据库和 Feed 均为 25 部；
- 25/25 URL 覆盖，0 失败，0 运行中；
- 25 部均有标题、封面与简介；
- 24 部有详情类型；《杀手正在召唤》源站详情和列表均未给出可靠类型，保守留空；
- 48 条公开 `jianpian://` 播放资源；
- 当前静态页面没有直接磁力或网盘链接，因此未伪造下载资源；
- 首部为《后室》，第 25 部为《卫兵的呐喊》。

正式抓取经历一次 DevSpace 502 崩溃窗口。数据库已原子保存其中 1 部，恢复后按实际 URL 覆盖跳过该记录并补完剩余项，没有重复详情抓取。由于进程在批次统计落库前中断，job 的 `detail_http_requests` 显示 24，而实际完成了 25 个详情请求。安全自动化不依赖该事后计数执法，而是请求前按最坏额度预留，因此不会因该统计窗口继续高频重试。

## 6. 自动化真实验证

对已完成的 DYTT 快照执行安全检查：

- 只发 1 次列表请求；
- 快照哈希未变化；
- 详情请求为 0；
- 预留 12 次、实际使用 1 次、退款 11 次；
- 当日剩余额度 49/50；
- 紧接着再次调用被 12 小时门禁跳过，网络请求为 0。

崩溃永久反例：

- 测试来源预留 2 次请求后抛出通道异常；
- 当日保留全部 2 次额度，剩余 8/10；
- 连续失败计数变为 1；
- 失败后 13 小时仍因 `failure_backoff` 禁止联网；
- 25 小时后才允许下一次尝试。

完成后手动 `run-latest` 零重放验证：

- DYTT：run 数保持 6，48 条播放器资源保持不变，`invocation_http_requests=0`；
- SixV：run 数保持 28、详情请求统计保持 109、50 张封面保持不变；
- SixV 封面同步为 50 已存在、0 下载、0 HTTP，并成功导出 50 项 App Bundle。

## 7. Schema与历史兼容

- schema 0005 保留主项目既有 `movie_cover_assets`；
- schema 0006 新增 `movie_external_resources` 与 `movie_source_state`；
- 历史 SixV 50 部、134 条磁力/网盘资源和 50 张封面无损保留；
- 0005→0006 历史库升级有永久测试。

DYTT正式库曾由本批次未提交草稿占用本地 0005。处理前使用 SQLite backup API 创建一致性备份，随后补建正式 0005 封面表、校正校验值并由正常迁移器应用 0006。校正后仍为 25 部和 48 条播放器资源，没有重新请求详情页。

## 8. 部署入口

首次初始化：

```bat
deploy\resource-index\setup.bat -Source dytt8899
deploy\resource-index\run-latest.bat -Source dytt8899 -Refresh
```

安全自动化与状态：

```bat
deploy\resource-index\run-movies-safe.bat
deploy\resource-index\movie-sources-status.bat
```

一键安装当前用户 Windows 任务计划，默认每 6 小时触发：

```bat
deploy\resource-index\install-movie-schedule.bat
```

内部 12 小时门禁会让多余触发零网络退出，任务设置为已有实例时不启动新实例。删除任务：

```bat
deploy\resource-index\install-movie-schedule.bat -Remove
```

本轮只提供安装脚本，没有擅自注册操作系统任务。

## 9. 验证

- DYTT与自动化专项：12 passed；
- Resource Index：134 passed；
- 全部 magnet 非集成测试：197 passed，2 deselected；
- compileall：PASS；
- `validate_enum.py`：241/241 ALL VALID；
- PowerShell：7/7 语法解析通过；
- ScheduledTasks 对象验证：`IgnoreNew`、`PT6H`；
- Python 3.13.13 全新最小环境安装与 schema 0006 doctor：PASS；
- 从项目目录外调用状态与安全脚本：PASS；
- SixV/DYTT 不传 Count 时分别正确使用 50/25，完成任务均为 0 请求。

## 10. 当前边界

- SQLite 仍是单机单写，不支持多机同时写共享数据库；
- 不是 Windows Service，使用任务计划程序；
- 页面没有公开磁力时不会推导、等待或绕过隐藏资源；
- 站点改版可能暂停该来源，但不会高频重试或影响其他来源；
- App 目前仍使用 SixV 离线 Bundle；DYTT Feed 已准备好，展示层是否分区或按更新时间合并属于后续产品批次。
