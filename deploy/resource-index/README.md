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

## 9. 本地签名发布包（M1）

电影和电视剧 Feed、封面同步完成后，执行：

```bat
deploy\resource-index\build-media-release.bat -PointerRevision 1
```

首次运行会在 Git 忽略的 `data\resource_index\.secrets` 中创建本地 Ed25519 密钥；后续运行会先校验密钥对，并在公钥缺失或与私钥不匹配时由私钥安全补建。私钥不得上传到对象存储、GitHub 或服务器，必须单独离线备份；未来 App 只内置对应公钥。然后生成：

```text
data\resource_index\media_releases\staging\releases\<release_id>\v1\releases\<release_id>\manifest.json
data\resource_index\media_releases\staging\releases\<release_id>\v1\objects\catalog\*.json
data\resource_index\media_releases\staging\releases\<release_id>\v1\objects\detail\*.json
data\resource_index\media_releases\staging\releases\<release_id>\v1\objects\resources\*.json
data\resource_index\media_releases\staging\releases\<release_id>\v1\covers\*
data\resource_index\media_releases\staging\pointers\<pointer_revision>-<release_id>.json
```

不可变 release 与可变指针候选严格分离：相同内容复用同一 release；提高 `pointer_revision` 时只新增签名指针，不改写 Manifest 或对象。此命令只建立和验证本地 staging，不上传 R2、阿里云、GitHub、Pages 或 Worker。构建过程中会阻断：

- 电影或电视剧数量低于门槛；
- `media_id`、info-hash 或资源 URL 重复；
- 显式跨季资源；
- 类型或国家字段包含 HTML 残片；
- 封面缺失或哈希不一致；
- 单个对象异常过大；
- 相比上一版异常缩减或未知季集资源增加。

与上一版比较：

```bat
deploy\resource-index\build-media-release.bat ^
  -PointerRevision 2 ^
  -PreviousManifest "data\resource_index\media_releases\staging\releases\上一版本\v1\releases\上一版本\manifest.json"
```

只有明确的业务变更才能使用 `-AllowRegression "原因"`。原因会写入签名指针的 `release_gate`，不能静默绕过，也不会改变不可变数据 release。

验证已有 staging：

```bat
deploy\resource-index\build-media-release.bat -VerifyOnly ^
  -ReleaseDir "完整不可变发布目录" ^
  -CurrentPath "对应的签名指针 JSON"
```

重复输入会复用同一 `release_id` 和同一指针候选，不会覆盖不同内容；同一个 `pointer_revision` 也不能重新指向另一配置。签名、Manifest 哈希或任一对象被篡改时，验证会失败。

## 10. R2 隔离测试发布（M2）

M2 只允许发布到独立测试 Bucket 和以 `m2-test` 开头的前缀，代码中没有生产 `v1/current.json` 的上传或晋级能力。推荐为测试 Bucket 创建最小权限的 R2 S3 凭证，并只通过当前终端的环境变量提供：

```powershell
$env:R2_ACCOUNT_ID = "<R2_ACCOUNT_ID>"
$env:R2_ACCESS_KEY_ID = "<M2_TEST_ACCESS_KEY_ID>"
$env:R2_SECRET_ACCESS_KEY = "<M2_TEST_SECRET_ACCESS_KEY>"
```

也可以使用 `R2_ENDPOINT_URL` 直接指定 S3 兼容端点。凭证禁止写入 bat、PowerShell 参数、源码、发布收据或 Git。

更推荐使用 Cloudflare 临时凭证 API。父凭证只放在当前终端环境变量中，程序会在内存中生成最长 1 小时、仅允许当前测试 Bucket 和 `m2-test/...` 前缀的子凭证，不写入磁盘：

```powershell
$env:R2_ACCOUNT_ID = "<R2_ACCOUNT_ID>"
$env:CLOUDFLARE_API_TOKEN = "<PARENT_API_TOKEN>"
$env:R2_PARENT_ACCESS_KEY_ID = "<PARENT_R2_ACCESS_KEY_ID>"
```

临时凭证模式在发布命令后增加：

```text
-TemporaryCredentials -CredentialTtlSeconds 900
```

在配置任何凭证前，先执行完全离线的发布计划检查：

```bat
deploy\resource-index\publish-media-r2-staging.bat ^
  -ReleaseDir "data\resource_index\media_releases\staging\releases\<release_id>" ^
  -CurrentPath "data\resource_index\media_releases\staging\pointers\<pointer_revision>-<release_id>.json" ^
  -Bucket "magnetgoogo-media-m2-test" ^
  -Prefix "m2-test\手工批次名" ^
  -DryRun
```

`-DryRun` 不需要 `--yes` 或任何 Cloudflare/R2 凭证，不创建收据、不访问网络；它会先完成 Release、Manifest、签名和 614 个对象的本地深度校验，再输出总文件数、总字节数、对象分类及首尾远程键。真实 M1 Release 当前计划为 614 个不可变对象 + Manifest + 签名指针候选，共 616 个文件、11,072,715 字节，且 `remote_requests=0`、`current_promoted=false`。

执行隔离上传：

```bat
deploy\resource-index\publish-media-r2-staging.bat ^
  -ReleaseDir "data\resource_index\media_releases\staging\releases\<release_id>" ^
  -CurrentPath "data\resource_index\media_releases\staging\pointers\<pointer_revision>-<release_id>.json" ^
  -Bucket "magnetgoogo-media-m2-test" ^
  -Prefix "m2-test\手工批次名"
```

发布顺序固定为：

```text
全部内容寻址对象
→ 逐对象远程大小、SHA-256 元数据和实际下载内容校验
→ Manifest
→ staging/pointers 下的签名指针候选
```

不会上传：

```text
v1/current.json
```

关键行为：

- 远端不存在时使用 `If-None-Match: *` 原子创建，避免并发覆盖；
- 远端存在且大小、SHA-256 和实际内容一致时直接复用；
- 相同路径出现不同内容时阻断，不覆盖；
- 429、超时和 5xx 按指数退避重试，每次重试重新打开本地文件；
- 任一对象失败时不上传 Manifest；Manifest 失败时不上传指针候选；
- 中断后重新执行会复用已经验证的对象，只补传缺失对象；
- 每次尝试保留独立的成功或失败收据，不覆盖历史证据；
- 同一目标的并发发布由本地锁阻断，异常退出留下的陈旧锁可自动恢复。

发布收据默认位于：

```text
data\resource_index\media_publish_receipts\
```

仅验证对象和 Manifest、暂不上传签名指针候选：

```bat
deploy\resource-index\publish-media-r2-staging.bat ... -NoPointerCandidate
```

`-ShallowVerify` 只校验远端大小和 SHA-256 元数据，不重新下载对象。正式验证默认必须使用深度校验，不建议日常关闭。

如果当前机器只有 Wrangler OAuth 登录、没有 R2 S3 或父凭证，可以使用一次性 Worker Bridge。它会生成随机内存令牌、部署仅绑定测试 Bucket 的临时 Worker、创建版本化 Secret、执行两轮完整发布，并在 `finally` 中删除 Worker：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File deploy\resource-index\publish-media-r2-oauth-bridge.ps1 `
  -ReleaseDir "data\resource_index\media_releases_m1_final\staging\releases\20260726T000000Z-b8c702d5" `
  -CurrentPath "data\resource_index\media_releases_m1_final\staging\pointers\00000000000000000004-20260726T000000Z-b8c702d5.json" `
  -Prefix "m2-test/release-20260726T000000Z-b8c702d5-r4-published"
```

Worker Bridge 仍使用同一个 `PublisherBackend` 状态机：Worker 只提供带鉴权的条件写、自定义 SHA-256 元数据和回读；生产 `current.json` 仍被本地与 Worker 双重禁止。Cloudflare workers.dev 新版本在不同边缘节点传播可能有短暂 401/403/平台 404，客户端只对这些未带协议标记的响应做最长 60 秒的有界等待；带 `x-media-bridge: 1` 的对象 404 才表示真实不存在。

2026-07-27 已将完整 Release 发布到私有 Bucket `magnetgoogo-media-m2-test` 的前缀：

```text
m2-test/release-20260726T000000Z-b8c702d5-r4-published/
```

远端对象与本地签名计划逐键完全一致：614 个不可变对象 + Manifest + 签名指针候选，共 616 个文件、11,072,715 字节。恢复轮仅补传 Manifest 和指针 2 个文件、复用 614 个；第二轮 `uploaded_count=0`、`reused_count=616`。成功收据：

```text
r2-worker-bridge-af9febdd6c-20260726T000000Z-b8c702d5-r4-6428518140dd.json
r2-worker-bridge-af9febdd6c-20260726T000000Z-b8c702d5-r4-a5084e559622.json
```

独立管理面复验确认远端恰好 616 个键，无缺失、无多余、无 `v1/current.json`；六类代表对象回读 SHA-256 全部匹配。临时 Worker 已删除，发布锁已释放，Bucket 的 r2.dev 访问仍关闭且未绑定自定义域名。本阶段只完成 M2 私有数据面发布，尚未切换 App 生产端点。

## 11. 生产双数据面与控制指针

生产数据先发布到两个独立静态数据面，且不包含 staging 指针：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File deploy\resource-index\publish-media-r2-production-data.ps1 `
  -ReleaseDir "完整 Release 目录" `
  -CurrentPath "签名指针候选"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File deploy\resource-index\publish-media-aliyun-data.ps1 `
  -ReleaseDir "完整 Release 目录" `
  -CurrentPath "签名指针候选"
```

生产公开数据集合固定为 614 个不可变对象 + Manifest，共 615 个文件。R2 使用 `magnetgoogo-media` Bucket 和 `media.magnetgoogo.com`；阿里云使用 `/var/www/magnetgoogo-site/media` 和 `https://cn.magnetgoogo.com/media`。两端均逐文件校验大小和 SHA-256，重复发布只能复用相同内容，冲突内容会阻断。

只有两个数据面的 Manifest 均与签名指针一致时，才执行最后的控制面晋级：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File deploy\resource-index\promote-media-current.ps1 `
  -CurrentPath "签名指针候选" `
  -ReleaseDir "完整 Release 目录"
```

晋级器会验证 Ed25519 签名、Manifest 哈希、revision 单调性和同 revision 内容一致性，然后发布同一字节的 `/v1/current.json`，再从两个端点回读验签。2026-07-27 已上线 revision 4：

```text
https://media.magnetgoogo.com/v1/current.json
https://cn.magnetgoogo.com/media/v1/current.json
```

## 12. App 接入与离线回退

App 的资源模块仍保留随 APK 打包的电影/剧集 Feed作为最后兜底；进入资源页后在后台读取两个生产 `current.json`，选择签名有效且 revision 最高的候选，验证 Manifest签名和每个对象的大小、SHA-256。列表只拉频道对象；详情和资源在点击时按需下载。

磁盘缓存使用随机设备密钥、AES-256-CBC 加密和 HMAC-SHA256 完整性校验，最长保留 72 小时。加载顺序为：

```text
内存 → AES 磁盘缓存 → APK bundled Feed
```

K30S 实测：电影和剧集网络 Feed各 100 条；电影资源 351、剧集资源 1331；在线点击详情按需获取 6 个资源；关闭 Wi-Fi和移动数据后重启，仍从磁盘缓存恢复 100 条和同一详情的 6 个资源。

## 13. 运维建议

- 每次升级代码后先执行 `doctor.bat`；
- 停止抓取任务后，再对整个 `data\resource_index` 目录做一致性备份；
- 日志持续追加，不要依赖终端窗口作为唯一运行证据；
- 不要删除未完成作业的 `_urls.json`，否则无法按原快照精确恢复；
- 迁移项目目录时，至少复制整个 `data\resource_index` 目录；
- Windows 任务计划程序应设置为“不启动新的实例”，不要并行运行同一任务。
