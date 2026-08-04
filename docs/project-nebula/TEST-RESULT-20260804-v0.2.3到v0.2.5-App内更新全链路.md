# v0.2.3 → v0.2.5 App内更新全链路测试

日期：2026-08-04（UTC+8）
设备：Redmi K30S，HyperOS/MIUI 14，序列号 `a1ea223a`
结论：`IN_APP_UPDATE_E2E=PASS / DATA_RETENTION=PASS / FATAL=0 / ANR=0`

## 一、测试目标

验证安装了0.2.3的用户是否可以在App内完成以下升级链路：

```text
启动0.2.3
→ 获取0.2.5更新配置
→ 展示更新弹窗
→ App内下载APK
→ 校验APK基本完整性
→ 自动拉起MIUI系统安装器
→ 用户确认更新
→ 覆盖安装0.2.5
→ 保留原App数据
```

该能力不是静默安装。Android和MIUI仍要求用户在系统安装页确认。

## 二、正式制品兼容性前置证据

正式0.2.3：

```text
文件：releases/magnetgoogo-v0.2.3.apk
package：com.magnetgoogo.app
versionName：0.2.3
versionCode：7
SHA-256：bbbe9b5900d69262c903ef8153c0954466956d416934ad7504caf159d6ad960d
证书SHA-256：475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d
```

正式0.2.5：

```text
文件：magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk
package：com.magnetgoogo.app
versionName：0.2.5
versionCode：9
SHA-256：2d89e372d24ee951d49ad69f17631b7b66b323e7a78d1eb23b31213a2b463b93
证书SHA-256：475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d
```

两个正式APK证书完全一致，且0.2.5的versionCode高于0.2.3，满足Android覆盖升级条件。此前K30S正式包 `adb install -r` 保留数据升级也已PASS。

## 三、E2E测试边界

不能修改线上公开更新配置，也不能把测试APK上传到公开发布渠道。因此本轮采用本地隔离E2E：

- 0.2.3源码绑定最终发布提交 `01555edc217fcf8db63c9af1f20c099a786337c0`；
- 仅将配置地址替换为 `http://127.0.0.1:8765/config.json`；
- 仅为该本地地址开启cleartext测试许可；
- `OptionalUpdateModal`、`ForceUpdateModal`、`updateDownload.ts`、`updateDownloadPolicy.ts`均与正式0.2.3源码完全一致；
- 使用ADB reverse把手机的127.0.0.1:8765映射到电脑本地测试服务器；
- 使用同一Debug证书的0.2.3/code7和0.2.5/code9测试包完成系统覆盖升级。

测试变体源码差异只有：

```text
magnetgoogo-app/app.json                  允许本地HTTP
magnetgoogo-app/src/core/configChecker.ts 配置地址改为127.0.0.1
```

下载、校验、文件URI转换、Intent和安装逻辑未修改。

## 四、测试APK核验

0.2.3 Debug测试包：

```text
package：com.magnetgoogo.app.debug
versionName：0.2.3
versionCode：7
大小：68,461,198 bytes
SHA-256：d74f26b77f498f9324d5a86d8bdc94fb0175a7b3504b9d3a76eb25d6fa55fbd3
证书SHA-256：fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c
```

0.2.5 Debug目标包：

```text
package：com.magnetgoogo.app.debug
versionName：0.2.5
versionCode：9
大小：71,104,307 bytes
SHA-256：5a26d8615143cacae792c2931369c14764dd9792208900aba5cde88752b368aa
证书SHA-256：fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c
```

两包的Debug证书、包名一致，目标versionCode更高。

## 五、升级前数据标记

0.2.3安装完成后执行搜索：

```text
UpdateRetentionProbe20260804
```

升级前直接读取Debug包AsyncStorage数据库：

```text
mg_search_history[{"query":"UpdateRetentionProbe20260804",...}]
```

证明保留标记已经写入 `databases/RKStorage`，不是只存在于页面内存。

升级前包状态：

```text
versionName=0.2.3
versionCode=7
firstInstallTime=2026-08-04 22:19:57
lastUpdateTime=2026-08-04 22:19:57
```

## 六、App内检测与下载

0.2.3启动后，本地服务器收到：

```text
GET /config.json HTTP/1.1 → 200
```

App正确显示：

```text
发现新版本
v0.2.5
0.2.3 → 0.2.5 本地App内更新全链路测试
立即更新
稍后再说
```

点击“立即更新”后，本地服务器收到：

```text
GET /magnetgoogo-v0.2.5.apk HTTP/1.1 → 200
```

APK大小约71.1MB。下载完成后App没有跳转浏览器，而是自动进入：

```text
com.miui.packageinstaller/com.miui.packageInstaller.NewInstallerPrepareActivity
```

证明以下链路PASS：

- App内直接下载；
- 下载完成回调；
- APK最小体积和ZIP文件头校验；
- FileSystem content URI转换；
- `android.intent.action.VIEW`安装Intent；
- 自动拉起MIUI安装器。

## 七、MIUI安装确认

MIUI先展示ICP备案提示，选择“继续安装”后，正式安装确认页显示：

```text
MagGoogo
版本：0.2.3 → 0.2.5
安装来源：MagGoogo
继续更新
取消更新
```

该页面明确证明：

- 系统识别为更新现有App，而不是安装第二个App；
- 目标版本是0.2.5；
- 安装来源是MagGoogo自身；
- App内下载的APK证书与已安装包一致。

点击“继续更新”后，MIUI显示“完成”。

## 八、升级后结果

升级后包状态：

```text
versionName=0.2.5
versionCode=9
firstInstallTime=2026-08-04 22:19:57
lastUpdateTime=2026-08-04 22:28:23
```

`firstInstallTime`完全不变，证明是覆盖升级而非卸载重装。

升级后再次直接读取AsyncStorage：

```text
mg_search_history[{"query":"UpdateRetentionProbe20260804",...}]
```

升级前的唯一搜索历史仍存在，数据保留PASS。

0.2.5强杀后冷启动：

```text
MainActivity正常获得前台焦点
Fatal Exception：0
ANR：0
```

## 九、MIUI实际用户体验

0.2.3可以自动完成：

```text
检测更新
→ App内下载APK
→ 自动打开系统安装器
```

但不能、也不应该绕过Android系统静默安装。用户仍需：

1. 点击App更新弹窗中的“立即更新”；
2. 首次使用时，可能允许“MagGoogo安装应用”；
3. MIUI可能显示ICP备案/安全审核提示；
4. 点击“继续更新”。

完成一次来源授权后，后续流程通常会更短。

## 十、自动失败回退保障

本轮真机重点验证成功升级主链。失败分支继续由永久自动测试覆盖：

- 主下载失败后按候选顺序重试；
- HTML错误页、小于5MB文件、非ZIP APK被拒绝；
- 失败候选在尝试下一个地址前被删除；
- 全部直连失败后展示蓝奏云/GitHub等浏览器兜底；
- 安装Intent失败时退回浏览器下载页。

对应门禁：

```text
npm run test:update-download
```

## 十一、清理与环境恢复

测试结束后：

- 删除ADB reverse 8765；
- 关闭本地更新服务器；
- 删除手机Download和`/data/local/tmp`测试APK；
- 三项系统动画恢复为1；
- `com.android.shell REQUEST_INSTALL_PACKAGES`恢复为default；
- 正式包 `com.magnetgoogo.app` 始终保持0.2.5/code9，正式数据未被测试变体触碰；
- 未修改、未部署任何线上更新配置；
- 未上传GitHub、R2、阿里云或蓝奏云。

## 十二、最终裁决

```text
CONFIG_DETECTION=PASS
UPDATE_MODAL=PASS
IN_APP_APK_DOWNLOAD=PASS
APK_BASIC_INTEGRITY_GUARD=PASS
SYSTEM_INSTALLER_LAUNCH=PASS
VERSION_0.2.3_TO_0.2.5_CONFIRMATION=PASS
USER_CONFIRMED_INSTALL=PASS
DATA_RETENTION=PASS
COLD_START_AFTER_UPDATE=PASS
FATAL=0
ANR=0
PUBLIC_CONFIG_UNCHANGED=YES
```

结论：

> 0.2.3具备完整的App内升级0.2.5能力。它会自动下载并自动拉起MIUI安装器，但最终安装必须由用户在系统界面确认，不属于静默安装。
