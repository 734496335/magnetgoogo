# MagGoogo v0.2.6 Formal APK Manifest

日期：2026-08-16（UTC+8）

## 正式制品

```text
文件：releases/magnetgoogo-v0.2.6.apk
包名：com.magnetgoogo.app
版本：0.2.6
versionCode：10
大小：33,614,822 bytes
SHA-256：1ca02b0d81524ea912afc4bf5fe4f2532cedf288d21c50c1adf78832ec8fff71
ABI：arm64-v8a only
证书SHA-256：475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d
```

证书与正式 v0.2.5 完全一致。

## K30S 最终字节验收

- `adb install -r`：PASS (`Performing Streamed Install / Success`)
- K30S installed `base.apk` SHA-256：与本文件完全一致
- `firstInstallTime` 保持 `2026-07-28 21:17:01`，确认保留数据覆盖升级
- main cold / HOT resume / force-stop COLD recovery：PASS
- 相同 `Inception` 新搜索 intent freshness：PASS
- resources / detail / favorites：PASS
- Fatal / ANR：0

## 代码/协议门禁

- TypeScript：PASS
- App adversarial：63/63 PASS
- resource feed：PASS
- media network/security/cache：PASS
- update download：PASS
- release build contract：PASS
- analytics-v2：PASS
- resource auto-sync：PASS
- crawler_v3 deterministic：PASS
- source enum / delivery contract：PASS

## 更新内容

1. 修复影视资源相关问题。
2. 优化搜索体验。
3. 修复若干问题并提升稳定性。

## 正式下载渠道

```text
R2：https://api.naoshiquan.com/download/v0.2.6/magnetgoogo-v0.2.6.apk
GitHub：https://github.com/734496335/magnetgoogo/releases/tag/v0.2.6
Aliyun stable：https://cn.magnetgoogo.com/download/magnetgoogo.apk
Aliyun versioned：https://cn.magnetgoogo.com/download/magnetgoogo-v0.2.6.apk
Lanzou：https://wwbdy.lanzn.com/irfev42qyyne
Lanzou password：8888
```

R2、GitHub Release asset、Aliyun stable、Aliyun versioned 均已独立验证为 `33,614,822 bytes` 且 SHA-256 与本地正式包完全一致。蓝奏云落地页 HTTP 200；由于网页密码/脚本保护，本次不伪造蓝奏云文件本体 exact-SHA 结论。

## 更新控制面

- `latest_version=0.2.6`
- `min_version=0.1.10`，保持可选更新，不提高强制升级门槛
- `mg-data` config commit：`5b71595`
- 六个 config 端点最终业务内容及字节 SHA 已收敛；公共 config SHA-256 为 `9f6b68b2ab9ddf84b0d6d7681653fa025b34a4c4a3c07929474ae72c54d36518`
- Cloudflare Pages deployment：`https://d40a482e.magnetgoogo-site.pages.dev`
- 官网 911 个 HTML 经下载镜像同步审计，旧 v0.2.5 R2/GitHub/蓝奏云下载 URL 与 placeholder 均为 0
- Aliyun 整站已在备份 `/var/www/magnetgoogo-site.pre-v026-20260816T1937` 后同步上线

## 最终发布状态

```text
FORMAL_APK=PASS
K30S_EXACT_SHA_PREPUBLICATION=PASS
ARCHIVE=PASS
PUBLIC_RELEASE=PASS
PUBLIC_CONFIG_CONVERGENCE=PASS
PUBLIC_APK_SHA_CONVERGENCE=PASS
PRODUCTION_UPDATE_CONTROL_PLANE=PASS
PRODUCTION_UPDATE_E2E=TOOL_SAFETY_BLOCKED_NOT_EXECUTED
```

生产 E2E 的唯一未闭环项：发布后原计划将 K30S 保留数据降级到同签名正式 v0.2.5，再从公网 config/R2 走 App 内下载 → MIUI 确认 → 保留数据升级到 v0.2.6。当前设备执行安全层在 `adb install -r -d` 执行前阻断，并随后阻断可执行的 `am start`；未使用任何替代 ADB/pm/Gradle 安装路径绕过。该状态是工具权限阻断，不是已观察到的产品失败，也不能记作 E2E PASS。

补充控制面实证：Gateway `/api/check` 对 `0.2.5` 返回 `update_available=true / force_update=false / latest=0.2.6`，并下发当前 R2/Lanzou/GitHub 链；对 `0.2.6` 返回 `update_available=false / force_update=false`。
