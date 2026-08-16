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

## 当前发布状态

```text
FORMAL_APK=PASS
K30S_EXACT_SHA=PASS
ARCHIVE=PASS
PUBLIC_RELEASE=NOT_STARTED
```

该 APK 已准备供人工上传蓝奏云。

公网 R2/GitHub/Aliyun/config/官网发布必须按 `docs/project-nebula/RELEASE-CHECKLIST.md` 执行，不能因蓝奏云文件已上传就提前切 `latest_version`。
