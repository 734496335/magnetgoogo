# MagGoogo v0.2.1 Media RC1 发布候选记录

日期：2026-07-28
状态：**RC_READY_WITH_DEVICE_INSTALL_GATE**

> 本记录只形成可发布候选，不上传 APK/AAB、不更新远程版本配置、不创建 tag、不推送 Git、不执行灰度或正式发布。

## 1. 候选绑定

- 媒体生产提交：`dfbdc9c feat(media): harden production app release candidate`
- Release 日志清理提交：`aab126c fix(media): strip debug evidence from release bundle`
- 构建 worktree：`D:\lpproduct\mrc`
- 构建基线：detached `aab126c`
- 构建时 Git 状态：clean
- App 包名：`com.magnetgoogo.app`
- versionName：`0.2.1`
- versionCode：`5`
- 上一公开同签名版本：`0.1.14 / versionCode 4`
- ABI：`arm64-v8a`
- minSdk：24
- targetSdk：36

## 2. 正式制品

### APK

- 文件：`releases/magnetgoogo-v0.2.1-media-rc1.apk`
- 字节数：38,386,726
- 大小：36.61 MiB
- SHA-256：`ad2b95e6c4365c581e54b0660f8849e5d968ce1c95f07cb5ac65e22a2dde4232`
- APK Signature Scheme：v2

### AAB

- 文件：`releases/magnetgoogo-v0.2.1-media-rc1.aab`
- 字节数：29,224,907
- 大小：27.87 MiB
- SHA-256：`dc834b91bde4dc5c39c3421d2e7439188c828266b9143a7dcf1fa56c58a0b73a`
- JAR 签名验证：PASS

### 签名证书

- SHA-256：`475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d`
- SHA-1：`4b7b0b68ecab6c4c04d2939e861ec373596fb874`
- MD5：`df1e684bf483ceffe49062d285b17c06`
- 与公开 `v0.1.14` 证书一致：PASS

## 3. 媒体生产链路

- current revision：4
- pointer SHA-256：`4f7b57d20296645f50a3329791c8ea09513ef0a5ccacc9ab485bfe33cb632739`
- release ID：`20260726T000000Z-b8c702d5`
- Manifest SHA-256：`8891347a02646fe6d98279205b0614a6945238e5cb57d67188c722febd91f838`
- 生产公开集合：614 个不可变对象 + Manifest = 615 个文件
- R2：`https://media.magnetgoogo.com`
- 阿里云镜像：`https://cn.magnetgoogo.com/media`
- 双端点 current/Manifest/对象实时协议测试：PASS

## 4. App 安全闭环

已实现并验证：

- Ed25519 current/Manifest 验签；
- Manifest、Catalog、Detail、Resources、Cover 大小及 SHA-256 校验；
- 同 revision 不同 pointer SHA-256 全部拒绝；
- 新 revision 低于设备已接受 revision 时拒绝回滚；
- 同 revision 的 pointer、release ID、Manifest SHA 任一漂移时拒绝；
- 单端点存活且 revision 更高时可接受；
- 网络请求使用真正的 Promise 硬超时，不依赖 React Native AbortController 是否及时结算；
- AES-256-CBC + HMAC-SHA256 缓存；
- SecureStore 保存随机缓存密钥；
- 主缓存与备份缓存原子切换；
- 主缓存损坏时从 backup 恢复并重建主缓存；
- 主备同时损坏时清除无效缓存并回退 APK bundled Feed；
- 72 小时缓存有效期；
- 列表仅下载 Catalog，详情和资源按点击加载；
- 正式包移除 Debug 成功证据日志，但保留错误日志。

## 5. K30S 实机证据

设备：Redmi K30S，ADB `a1ea223a`

Debug 包已实证：

- 在线电影：100 条、351 个资源；
- 在线剧集：100 条、1331 个资源；
- 点击详情后按需获得 6 个资源；
- 断网重启从 AES 缓存恢复电影 100 条；
- 断网时详情从缓存恢复 6 个资源；
- 主缓存手工破坏后从 backup 恢复 100 条；
- 主备同时破坏后回退 bundled 电影 50 条，不白屏；
- R2-only 实机链路：PASS。

未能自动完成：

- K30S 首次安装正式包；
- 从公开 `v0.1.14` 覆盖升级到 RC；
- 正式包在线/离线重复验收。

阻断原因不是 APK、签名或代码：MIUI 对 shell/ADB 发起的新正式包安装立即返回 `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`；标准系统安装器也因调用方 shell UID 缺少 `android.permission.REQUEST_INSTALL_PACKAGES` 立即退出。设备当前没有安装 `com.magnetgoogo.app`，只有 Debug 包，因此无法在不人工调整手机“USB 安装/未知来源安装”权限的前提下完成覆盖升级。

人工开启该设备安装权限后，必须补跑：

1. 安装公开 `v0.1.14`；
2. 写入搜索历史/收藏哨兵；
3. `adb install -r` RC APK；
4. 确认 versionCode 4 → 5、UID/firstInstallTime不变；
5. 确认历史、收藏、源缓存不丢失；
6. 清数据冷启动验证 bundled → 网络 100/100；
7. 断网验证 AES 缓存恢复；
8. 恢复网络。

## 6. 测试门禁

- `python -m pytest magnet/tests/resource_index -q`：201 passed
- Python compile：PASS
- Media security：PASS
- Media live protocol：PASS
- Release build contract：PASS
- Resource Feed：PASS
- App adversarial：47/47 PASS
- Fluency：17/17 PASS
- TypeScript：PASS
- `assembleRelease bundleRelease`：BUILD SUCCESSFUL
- APK 包名/版本/ABI：PASS
- APK 签名与备案证书：PASS
- AAB 签名：PASS
- Release bundle 敏感扫描：PASS

Release bundle 不包含：

- 媒体私钥；
- `.env`；
- keystore；
- 签名环境变量名；
- R2 上传 Token；
- Debug 包名；
- `MediaReleaseEvidence`；
- 发布收据。

只包含验证所需的 Ed25519 公钥。

## 7. 依赖审计

`npm audit --omit=dev` 报告 22 项（含 2 critical、6 high）。依赖链审查表明其集中在 Expo/React Native 的 Node 构建、CLI、Metro、DevTools、归档/YAML/WebSocket工具链；最终 Hermes bundle逐项扫描不包含：

- `shell-quote`
- `node-tar`
- `undici`
- `postcss`
- `fast-uri`
- `brace-expansion`
- `@babel/core`

结论：记录为 Expo/React Native SDK 工具链升级债务，不作为当前移动运行时媒体功能 blocker；不得执行 `npm audit fix --force` 直接跨越到 Expo 57。

## 8. 回滚方案

### App 回滚

保留：

- `releases/magnetgoogo-v0.1.14.apk`
- `releases/magnetgoogo-v0.2.1-media-rc1.apk`
- 两者签名证书一致。

在新版本尚未发布前，无需执行任何 App 回滚。

### 媒体数据回滚

客户端强制 revision 单调，不能把 current 从高 revision直接降回低 revision。

若未来 revision 5 指向有问题的 Release B，应签发 revision 6，并让 revision 6重新指向当前稳定 Release A；不能把 current直接改回 revision 4。

## 9. 发布前剩余门禁

1. 在 K30S人工允许正式 APK安装后，完成正式包首次安装和覆盖升级验收；
2. 合并其他仍在开发的特性；
3. 从最终合并提交重新构建新的正式候选，不能直接把本 Media RC当作包含其他特性的最终版本；
4. 重新计算 APK/AAB SHA-256并复验签名；
5. 再决定上传、更新版本配置和灰度。

## 10. 明确未执行

- 未上传 APK/AAB；
- 未修改 `latest_version`、`min_version`或下载地址；
- 未发布正式 App；
- 未灰度；
- 未创建 Git tag；
- 未 Git push；
- 未改变生产媒体 current revision 4；
- 未留下临时 Worker、Tunnel、8443服务或临时Nginx入口。
