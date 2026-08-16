# v0.2.6 全链路公开发布与生产更新控制面验收

日期：2026-08-16（UTC+8）
源码候选提交：`e4b935cce76b5177cef6731151bf7d25c3e29f14`
正式版本：`v0.2.6 / versionCode 10`
结论：`PUBLIC_RELEASE=PASS / PUBLIC_APK_SHA_CONVERGENCE=PASS / PUBLIC_CONFIG_CONVERGENCE=PASS / PRODUCTION_UPDATE_E2E=TOOL_SAFETY_BLOCKED_NOT_EXECUTED`

## 一、最终正式制品

```text
文件：D:\lpproduct\m023\releases\magnetgoogo-v0.2.6.apk
包名：com.magnetgoogo.app
版本：0.2.6
versionCode：10
大小：33,614,822 bytes
SHA-256：1ca02b0d81524ea912afc4bf5fe4f2532cedf288d21c50c1adf78832ec8fff71
ABI：arm64-v8a only
证书SHA-256：475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d
```

`verify_release_apk.py` 再次 PASS，证书与正式 v0.2.5 完全一致。该 APK 在公开发布前已经以 exact bytes 安装到 K30S，设备 `base.apk` SHA 与本地正式包完全一致，并完成保留数据覆盖、重复搜索 freshness、资源/详情/收藏、HOT/COLD 生命周期及 Fatal/ANR=0 验收。

## 二、更新说明

用户可见更新内容固定为三条：

```text
修复影视资源相关问题。
优化搜索体验。
修复若干问题并提升稳定性。
```

App 更新公告第三行附带蓝奏云密码：

```text
修复若干问题并提升稳定性；蓝奏云密码：8888。
```

`min_version` 保持 `0.1.10`，因此本次是可选更新，不提高旧用户强制升级门槛。

## 三、公开 APK 渠道

### R2 primary

```text
https://api.naoshiquan.com/download/v0.2.6/magnetgoogo-v0.2.6.apk
```

- HTTP 200
- Content-Type：`application/vnd.android.package-archive`
- Content-Length：`33,614,822`
- 完整回下载 SHA-256：与 final APK 完全一致

### GitHub Release

```text
https://github.com/734496335/magnetgoogo/releases/tag/v0.2.6
https://github.com/734496335/magnetgoogo/releases/download/v0.2.6/magnetgoogo-v0.2.6.apk
```

- Release：非 draft / 非 prerelease
- tag 指向源码候选提交 `e4b935cce76b5177cef6731151bf7d25c3e29f14`
- asset size：`33,614,822`
- GitHub asset digest：`sha256:1ca02b0d81524ea912afc4bf5fe4f2532cedf288d21c50c1adf78832ec8fff71`
- 独立完整回下载 SHA 一致
- `/releases/latest` 已指向 `v0.2.6`

### 阿里云

```text
https://cn.magnetgoogo.com/download/magnetgoogo.apk
https://cn.magnetgoogo.com/download/magnetgoogo-v0.2.6.apk
```

服务器 stable/versioned 均为 `33,614,822` bytes 和 final SHA。Windows 当前开发机访问 `cn.magnetgoogo.com` 仍存在已知 TLS EOF/Schannel 握手问题，因此没有把本机 TLS 失败误报成服务器发布失败；改用 Linux/服务器公共域名路径独立回下载，两条 URL 均 HTTP 200 且 SHA 完全一致。

旧 stable APK 已保留回滚副本：

```text
/var/www/apk/magnetgoogo.apk.pre-v026-20260816T1930
```

### 蓝奏云

```text
https://wwbdy.lanzn.com/irfev42qyyne
密码：8888
```

落地页 HTTP 200。蓝奏云文件本体受网页密码/脚本保护，本轮不伪造自动 exact-SHA 结论；用户已经确认上传的是本次正式包。

## 四、config 与更新控制面

`mg-data/config.json` 发布内容：

```text
latest_version=0.2.6
min_version=0.1.10
primary=https://api.naoshiquan.com/download/v0.2.6/magnetgoogo-v0.2.6.apk
mirror1=https://wwbdy.lanzn.com/irfev42qyyne
mirror2=https://github.com/734496335/magnetgoogo/releases/download/v0.2.6/magnetgoogo-v0.2.6.apk
updated_at=2026-08-16T19:31:57+08:00
```

`mg-data` 提交：

```text
5b71595 chore: publish v0.2.6 app config
```

最终以下六个配置端点业务内容收敛到同一份 v0.2.6 config：

1. GitHub Raw `mg-data/main/config.json`
2. `https://magnetgoogo.com/config.json`
3. `https://api.naoshiquan.com/config.json`
4. `https://cn.magnetgoogo.com/config.json`
5. `https://maggoogo-gateway.734496335lp.workers.dev/config.json`
6. jsDelivr `mg-data@main/config.json`

六端点最终 config SHA-256：

```text
9f6b68b2ab9ddf84b0d6d7681653fa025b34a4c4a3c07929474ae72c54d36518
```

jsDelivr 初次检查仍返回旧 0.2.5，这是历史 stale CDN 风险的真实复现；主动 purge `mg-data@main/config.json` 后重新验证，已收敛到 0.2.6。当前 v0.2.6 客户端本身使用 validated authority-first 顺序，不允许 stale-fast CDN 抢赢 mutable config。

Gateway `/api/check` 生产验证：

```text
X-App-Version: 0.2.5
=> update_available=true
=> force_update=false
=> latest_version=0.2.6
=> min_version=0.1.10
=> 下发新 R2/Lanzou/GitHub 链及三条公告

X-App-Version: 0.2.6
=> update_available=false
=> force_update=false
```

## 五、官网与 Cloudflare Pages

主站本地目录：

```text
D:\lpproduct\magnet\magnetgoogo-site
```

发布前发现 911 个 HTML 中有 192 个页面仍包含旧版本下载链。`scripts/sync-download-mirrors.js` 本轮补齐 primary R2 同步能力，不再只同步 GitHub/Lanzou；执行后：

```text
htmlFiles=911
changedFiles=192
missingFiles=0
最终 --check changedFiles=0
```

同时更新首页 JSON-LD `softwareVersion=0.2.6` 和 9 个语言首页的 `APK 32.1MB · v0.2.6` 展示。

全站扫描：

```text
旧 v0.2.5 R2 URL = 0
旧 v0.2.5 GitHub asset URL = 0
旧蓝奏云 ID = 0
REPLACE_WITH_NEW_LINK = 0
```

Cloudflare Pages：

```text
https://d40a482e.magnetgoogo-site.pages.dev
```

本次 deploy 上传总计 961 个静态文件，其中 199 个新上传、762 个已存在。`magnetgoogo.com` 首页、英文页和 SEO 页面抽查均只显示 v0.2.6、新 R2、新蓝奏云，未发现旧下载链。

## 六、阿里云整站发布

发布前建立整站回滚：

```text
/var/www/magnetgoogo-site.pre-v026-20260816T1937
```

完整站点先上传到：

```text
/home/admin/magnetgoogo-site-v026
```

SCP 命令在 DevSpace 连接层返回 HTTP 502；未盲目重传。后续检查证明：

```text
本地非隐藏文件：957
远端 staging 文件：957
本地总 bytes：16,470,449
远端总 bytes：16,470,449
远端 config latest=0.2.6
远端 index softwareVersion=0.2.6
```

因此确认是“传输已经完成、connector 最终响应失败”，随后只提升已验证 staging tree 到 `/var/www/magnetgoogo-site`。

阿里云站点最终针对真正用户下载链的精确扫描：

```text
旧 R2 下载 URL = 0
旧 GitHub asset URL = 0
旧蓝奏云 ID = 0
placeholder = 0
```

公共中文首页、英文首页、SEO 页面抽查全部为 v0.2.6 新链。

## 七、发布前完整门禁

App：

```text
TypeScript PASS
App adversarial 63/63 PASS
resource feed PASS
live media network PASS
media security PASS
media cache PASS
update download PASS
release-build contract PASS
analytics-v2 PASS
resource-auto-sync PASS
fluency 17/17 PASS
```

实时影视：

```text
revision=17
release=20260815T000000Z-b6b1a79a
movies=287
series=318
resources=4481
media.magnetgoogo.com 与 Gateway pointer SHA 一致
```

Source：

```text
crawler_v3：71 passed, 2 deselected
source delivery hard finding=0
rules=357 / ALL VALID
```

## 八、生产旧版本→0.2.6 K30S E2E 边界

发布完成后计划严格复现真实用户升级：

1. 当前 K30S 正式包为 0.2.6/code10；
2. 保留数据降级到同签名正式 0.2.5；
3. 0.2.5 从已发布的公网 config 发现 0.2.6；
4. App 内从 R2 下载 APK；
5. App 自己拉起 MIUI installer；
6. 用户确认后保留数据升级；
7. 验证 firstInstallTime、搜索/资源与 Fatal/ANR。

只读设备预检成功：

```text
device=a1ea223a online
package=com.magnetgoogo.app
version=0.2.6/code10
firstInstallTime=2026-07-28 21:17:01
lastUpdateTime=2026-08-16 15:39:37
```

但 `adb install -r -d releases/magnetgoogo-v0.2.5.apk` 被当前设备执行安全层在**设备执行前**拦截，随后 App 启动类 ADB action 也被安全层拦截。没有使用 `pm install`、Gradle install、卸载重装或任何替代路径绕过。

因此本轮只能真实记录：

```text
PRODUCTION_UPDATE_CONTROL_PLANE=PASS
PREPUBLICATION_EXACT_FINAL_K30S=PASS
PRODUCTION_UPDATE_E2E=TOOL_SAFETY_BLOCKED_NOT_EXECUTED
```

这不是已观察到的产品失败，但也绝不能写成生产 E2E PASS。对应失败证据已保存在 `_failures/20260816-1947-k30s-production-update-e2e-safety-block.log`。

## 九、最终结论

v0.2.6 已完成正式公开发布：最终 APK 身份、备案签名、R2、GitHub、阿里云、蓝奏云落地页、官网、Cloudflare Pages、mg-data、六端点 config 和更新控制面均已闭环；未发现新的 P0/P1。

唯一未获得的新证据是**发布后**旧正式版→0.2.6 的 K30S MIUI 生产更新操作，因为设备动作被工具安全层阻断。此前 final v0.2.6 exact bytes 的 K30S 真机验收仍保持 PASS。
