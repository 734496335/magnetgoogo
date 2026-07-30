# v0.2.3 影视缓存原子提交与国内更新候选验收

## 结论

`0.2.3 / versionCode 7` 候选已完成构建与 K30S 正式包验收，但尚未公开发布。

本版本包含的核心影视缓存特性不是泛指“有本地缓存”，而是关闭正式 `0.2.2` 在 revision 6 落盘时的原子提交缺陷：

- 线上 revision：`6`
- 电影：`498`
- 电视剧：`469`
- 资源：`3,720`
- Pointer SHA-256：`5efaf37f00447bafa3ea17d977d7b3a35a20a46a32c803b5ea1c7f4443bf7197`

修复后的正式候选可稳定保存电影和电视剧频道目录，断网并强杀进程后仍能恢复 revision 6 中不属于 APK 内置 Feed 的内容。

## 发现并关闭的第二层缓存缺陷

原冻结提交 `77a48f710f10dd48b10e33c53211e3556c70e4cf` 已修复 Expo File 对象移动后的引用失效问题，但正式包复验发现仍未完全闭环。

真实反例：

```text
MEDIA_CACHE_COMMIT_FAILED
FileAlreadyExistsException
/data/user/0/com.magnetgoogo.app/files/media-release-cache-v2/.index.json.backup
```

根因不是单次文件删除失败，而是电影和电视剧并行同步时，两个 `saveMediaFeeds()` 事务都会修改共享 `index.json`，并同时使用固定 `.index.json.backup`，形成原子提交竞态。

最终修复：

- 保持电影、电视剧目录和对象的网络下载并行；
- 将完整的 `Feed + 共享 index` 落盘事务串行化；
- 前一个事务失败不会永久阻塞后续事务；
- 保留原有临时文件、备份、校验与恢复逻辑。

新增队列回归测试同时提交 movie、series、失败任务及失败后的下一任务，验证最大活动提交数严格为 `1`，且队列能从失败中继续。

## K30S 正式候选验收

设备：Redmi K30S，型号 `M2007J3SC`，国内 Wi-Fi。

### 保留数据升级

先安装正式 `0.2.2 / code 6`，再覆盖安装候选 `0.2.3 / code 7`：

- 安装返回：`Success`
- `firstInstallTime` 保持 `2026-07-28 21:17:01`
- 用户数据保留：PASS

### 电影长期缓存

在线同步后，资源页出现 `超级少女`。该标题不属于 APK 内置的 50 部电影，而属于 revision 6 远程目录。

随后执行：

```text
关闭 Wi-Fi 和移动数据
强杀 App 进程
重新启动资源页
```

离线仍显示 `超级少女`，证明远程电影 Feed 已真正落盘，而不是只停留在内存。

### 电视剧长期缓存

在线打开国产剧频道后，页面出现 `聪明镇`。该标题不属于 APK 内置的 100 条电视剧，而属于 revision 6 远程目录。

断网并强杀进程后重新进入国产剧，仍显示 `聪明镇`，证明远程电视剧 Feed 也已持久化。

### 缓存异常扫描

最终候选在电影和电视剧先后同步、旧 `.index.json.backup` 异常现场恢复、断网重启过程中均未出现：

- `MEDIA_CACHE_COMMIT_FAILED`
- `FileAlreadyExistsException`
- `.index.json.backup` 冲突
- `.movie.json.backup` 冲突
- `.series.json.backup` 冲突
- Fatal Exception
- ANR

## App 内更新失败的真实边界

### 当前 0.2.2 用户

已发布的 0.2.2 没有声明：

```text
android.permission.REQUEST_INSTALL_PACKAGES
```

因此 0.2.2 即使在 App 内成功下载 APK，也可能无法稳定进入系统安装确认页，然后退回浏览器。目标 APK 无法反向给旧调用方补权限。

所以：

> `0.2.2 → 0.2.3` 仍需要一次浏览器下载安装作为迁移兜底。

### 0.2.3 以后

0.2.3 候选已包含：

- `REQUEST_INSTALL_PACKAGES`
- R2 国内直连主下载
- 蓝奏云优先、GitHub 最后
- 多个直连候选依次回退
- APK 最小体积校验
- APK ZIP 文件头校验
- 下载与安装失败的结构化日志

更新实现与此前在 K30S 上完成 `R2 下载 → MIUI 扫描 → 安装确认 → 覆盖升级` 的权限修复候选逐文件一致。

因此安装 0.2.3 后，后续 `0.2.3 → 0.2.4` 才具备稳定使用 App 内进度条下载并拉起安装器的基础。

生产下载接口仍未提供真正的客户端断点续传闭环；弱网中断后可能重新下载，不能表述为“绝不会失败”。

## APK 权威信息

- 文件：`releases/magnetgoogo-v0.2.3.apk`
- 大小：`38,486,986` 字节
- SHA-256：`bbbe9b5900d69262c903ef8153c0954466956d416934ad7504caf159d6ad960d`
- 包名：`com.magnetgoogo.app`
- 版本：`0.2.3`
- versionCode：`7`
- ABI：仅 `arm64-v8a`
- 安装权限：已包含 `REQUEST_INSTALL_PACKAGES`
- 签名证书 SHA-256：`475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d`
- 签名证书 MD5：`df1e684bf483ceffe49062d285b17c06`

## 自动门禁

- revision 6 双端协议与字节一致：PASS
- 媒体缓存策略：PASS，含共享 index 串行提交
- 媒体安全：PASS
- Resource Feed：PASS
- 国内更新下载策略：PASS
- Release 构建契约：PASS
- TypeScript：PASS
- App 对抗测试：`52/52 PASS`
- 流畅性测试：`17/17 PASS`
- signed clean prebuild + Gradle Release：PASS

## 发布边界

本轮仅生成并验证正式候选，没有执行：

- GitHub Release v0.2.3 发布
- R2/阿里云 APK 替换
- 远程更新配置切换到 0.2.3
- 官网下载入口更新

公开发布前需使用同一 APK 字节完成全端点上传和回下载 SHA 复核。
