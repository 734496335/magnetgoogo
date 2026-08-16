# K30S 安装与覆盖升级权威操作手册

> **用途**：以后所有 Redmi K30S 真机安装、覆盖升级、安装失败诊断先读本文。
>
> **设备**：Redmi K30S，ADB serial `a1ea223a`。
>
> **当前权威原则**：优先使用 Android 标准 `adb install -r`；需要验证真实用户 App 内更新体验时，走 MagGoogo 自己的 `content:// + ACTION_VIEW` 安装链。不要把 shell 直接拉 MIUI Installer 当作标准安装方案。

---

## 1. 安装路径总览

| 路径 | 用途 | 是否保留数据 | 是否需要手机确认 | 权威级别 |
|---|---|---:|---:|---|
| `adb install -r APK` | 开发/发版前把同签名新 APK 覆盖到 K30S | 是 | MIUI 可能要求确认 | **首选** |
| Gradle `installDebug` | Debug 构建后直接安装 | Debug 包数据保留 | MIUI 可能要求确认 | Debug 首选之一 |
| App 内更新：下载 → `content://` → `ACTION_VIEW` | 验证真实用户从旧版升级新版本 | 是 | **必须由用户确认** | **用户路径权威** |
| 系统文件管理器手动点 APK | ADB 安装策略异常时的人机备用 | 是/取决于签名 | 必须 | 备用 |
| shell 直接 `am start ... InstallStart` | 仅诊断 MIUI 安装器 | 不一定能进入安装 | 不可靠 | **禁止作为标准方案** |

---

## 2. 安装前必须确认

### 2.1 设备在线

```bat
adb devices
```

必须看到：

```text
a1ea223a    device
```

若是 `unauthorized`，在手机上重新允许 USB 调试。

### 2.2 确认目标 APK 身份

正式包先跑：

```bat
python scripts/verify_release_apk.py ^
  magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk ^
  --previous releases/magnetgoogo-v0.2.5.apk ^
  --expect-version 0.2.6 ^
  --expect-code 10 ^
  --expect-package com.magnetgoogo.app ^
  --max-bytes 52428800
```

必须同时满足：

- package = `com.magnetgoogo.app`
- versionName / versionCode 正确
- ABI 只有 `arm64-v8a`
- signer 与上一正式版一致
- APK < 50 MiB
- 记录 SHA-256，后续真机必须验证 installed APK 是同一 SHA

### 2.3 记录安装前状态

```bat
adb -s a1ea223a shell dumpsys package com.magnetgoogo.app
```

重点记录：

- `versionName`
- `versionCode`
- `firstInstallTime`
- `lastUpdateTime`

覆盖升级成功后，`firstInstallTime` 应保持不变。

---

## 3. 正式包标准覆盖安装

### 3.1 标准命令

在项目根目录：

```bat
adb -s a1ea223a install -r "magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk"
```

成功的权威输出：

```text
Performing Streamed Install
Success
```

这是当前 K30S 已重复验证过的成熟路径。

### 3.2 如果手机出现安装确认

用户手动完成 MIUI 提示即可。不要用自动点击绕过系统安装确认。

常见系统页面包括：

- USB 安装确认
- ICP/安全审核提示
- “继续安装/继续更新”

### 3.3 `INSTALL_FAILED_USER_RESTRICTED`

典型输出：

```text
INSTALL_FAILED_USER_RESTRICTED: Install canceled by user
```

含义通常不是签名坏，而是 MIUI USB 安装被系统/用户确认阻断。

处理顺序：

1. 保持手机亮屏、解锁；
2. 重新执行同一条 `adb install -r`；
3. 手机端出现提示时用户手动确认；
4. 不要因为一次 `USER_RESTRICTED` 就重建 APK 或更换签名。

项目规则：同一失败不要无脑重试多次；先确认是 MIUI 安装确认问题还是 APK 身份问题。

---

## 4. 安装后做“字节级”确认

只看版本号不够。同一个 `0.2.6/code10` 可能存在多个候选 APK。

### 4.1 取得设备已安装 APK 路径

```bat
adb -s a1ea223a shell pm path com.magnetgoogo.app
```

示例：

```text
package:/data/app/.../com.magnetgoogo.app-.../base.apk
```

### 4.2 对 installed `base.apk` 算 SHA

先拿路径：

```bat
adb -s a1ea223a shell pm path com.magnetgoogo.app
```

把输出中 `package:` 后的完整 `/data/app/.../base.apk` 作为下一条命令参数：

```bat
adb -s a1ea223a exec-out cat /data/app/.../base.apk > installed-base.apk
certutil -hashfile installed-base.apk SHA256
```

验证后删除本地临时 `installed-base.apk`。也可以用现有 Python/ADB harness 流式计算，不要求固定一种 host shell 写法。

**验收要求：设备 SHA 必须与本地最终 APK SHA 完全一致。**

### 4.3 再检查安装时间

```bat
adb -s a1ea223a shell dumpsys package com.magnetgoogo.app
```

- `firstInstallTime` 不变 → 保留数据覆盖升级
- `lastUpdateTime` 更新 → 新 APK 已替换

### 4.4 v0.2.6 当前已验证样本

当前最终正式包：

```text
package: com.magnetgoogo.app
version: 0.2.6
versionCode: 10
SHA-256: 1ca02b0d81524ea912afc4bf5fe4f2532cedf288d21c50c1adf78832ec8fff71
ABI: arm64-v8a only
```

K30S installed `base.apk` 已验证与此 SHA 完全一致。

---

## 5. Debug 安装路径

Debug 与正式包是两个不同 applicationId：

```text
Debug:   com.magnetgoogo.app.debug
Release: com.magnetgoogo.app
```

因此可以同时安装，不要误把 Debug 覆盖结果当正式包验收。

### 5.1 standalone Debug

`package.json` 已有：

```bat
cd magnetgoogo-app
npm run android:k30s
```

其核心行为是：

```text
expo prebuild --no-install
→ assembleDebug -PstandaloneDebug=true -PreactNativeArchitectures=arm64-v8a
→ adb install -r app-debug.apk
```

### 5.2 手工 Debug 构建安装

```bat
cd magnetgoogo-app/android
gradlew.bat assembleDebug -PstandaloneDebug=true -PreactNativeArchitectures=arm64-v8a
adb -s a1ea223a install -r app/build/outputs/apk/debug/app-debug.apk
```

### 5.3 Metro Debug 与 standalone Debug 不要混淆

历史上 Debug 曾依赖 Metro：

```bat
npx expo start --port 8081
adb -s a1ea223a reverse tcp:8081 tcp:8081
```

当前做发布候选真机测试，优先 standalone Debug，因为它不依赖持续运行 Metro，更接近 Release 生命周期。

---

## 6. App 内真实更新安装路径

这是用户最终实际会经历的路径，和 `adb install -r` 的用途不同。

### 6.1 客户端代码链

`configChecker.ts`：

```text
远程 config
→ latest_version / min_version 比较
→ OptionalUpdateModal / ForceUpdateModal
```

`updateDownload.ts`：

```text
按候选顺序下载 APK
→ 文件 >= 5 MiB
→ ZIP/APK 文件头检查
→ 错误候选删除
```

`OptionalUpdateModal.tsx` / `ForceUpdateModal.tsx`：

```text
FileSystem.getContentUriAsync(fileUri)
→ content:// URI
→ IntentLauncher.startActivityAsync(android.intent.action.VIEW)
→ type=application/vnd.android.package-archive
→ FLAG_GRANT_READ_URI_PERMISSION
→ MIUI Package Installer
```

### 6.2 为什么一定要 `content://`

MIUI 会判断安装请求的 caller。

已实测：shell 直接发：

```text
callingPackage=com.android.shell
```

MIUI 会报：

```text
Requesting uid 2000 needs to declare permission android.permission.REQUEST_INSTALL_PACKAGES
```

即使给 shell 临时 AppOps `allow` 也不能弥补 manifest 没声明权限。

**因此不要把 shell 的 `ACTION_VIEW file://...` 当作 App 内更新等价测试。**

### 6.3 正确的 App 内更新 E2E

历史已验证的本地隔离 E2E：

1. 旧版 App 安装在 K30S；
2. 本地启动 `scripts/local_update_e2e_server.py`；
3. `adb reverse tcp:8765 tcp:8765`；
4. 测试变体仅把 config 地址指向 `127.0.0.1:8765`，更新下载/安装代码不改；
5. App 显示更新；
6. 点击“立即更新”；
7. App 下载目标 APK；
8. App 自己发 `content:// + ACTION_VIEW`；
9. MIUI 显示“安装来源：MagGoogo”；
10. 用户点击继续更新；
11. 验证版本、`firstInstallTime`、数据保留和 Fatal/ANR。

公开发布后还必须再做一次**真实公网更新 E2E**，不能只依赖本地服务器测试。

---

## 7. 系统文件管理器备用路径

目标 APK 可推到：

```bat
adb -s a1ea223a push app-release.apk /sdcard/Download/MagGoogo.apk
```

然后用户在系统文件管理器中点击 APK。

这条路径适合：

- ADB `install -r` 被 MIUI policy 暂时阻断；
- 需要人工确认“文件管理器来源安装”。

它不是 App 内更新链的替代测试，因为 installer source 不再是 MagGoogo。

### Git Bash 路径坑

Git Bash 会把 `/sdcard/...` 自动转换为类似：

```text
C:/Program Files/Git/sdcard/...
```

必要时：

```bash
MSYS_NO_PATHCONV=1 adb -s a1ea223a push app-release.apk /sdcard/Download/MagGoogo.apk
```

此坑只影响 host shell 参数转换，不是手机故障。

---

## 8. Deep Link / shell 特殊字符坑

搜索测试经常带：

```text
&benchmark=1
&cold=1
&run=...
```

如果直接把 URI 交给远端 shell，`&` 会被当命令分隔符。

项目现有 `scripts/test_k30s_search.py` 已使用：

```python
quoted_uri = shlex.quote(uri)
```

后续脚本必须保持“整个 URI 一次性 quote”，不要手写半截转义。

---

## 9. MIUI / K30S 已知环境问题

### 9.1 `uiautomator dump` 不稳定

已多次出现：

```text
ERROR: could not get idle state
```

或者返回桌面层级而实际 App 在前台。

因此：

- 不要把 UIAutomator 一次失败判为 App 崩溃；
- 使用 WindowManager、Activity 状态、framebuffer、App 自己的 Debug 报告、logcat 交叉取证；
- 不要为了“证明点击过”盲点固定坐标。

### 9.2 前台被其它测试 App 抢走

专用 K30S 上历史 DCloud 包：

```text
uni.UNIB56C11F
```

会偶发抢前台。`scripts/test_k30s_search.py` 会在测试期 force-stop 它，并对 MagGoogo task pin。

### 9.3 Release 不能 `run-as`

正式包是 `android:debuggable=false`：

```text
run-as: package not debuggable: com.magnetgoogo.app
```

这是正确安全行为。

**任何正式包测试脚本若依赖 `run-as` 读私有 cache，都属于 harness 设计错误，不是 App 缓存丢失。**

---

## 10. 安装后的最小验收清单

每次安装至少完成：

```text
[ ] adb install -r 返回 Success
[ ] package/versionCode/versionName 正确
[ ] installed base.apk SHA = 本地最终 SHA
[ ] firstInstallTime 保持不变（升级场景）
[ ] 冷启动成功
[ ] HOT 恢复成功
[ ] force-stop 后 COLD 恢复成功
[ ] 搜索主流程成功
[ ] 资源页成功
[ ] 详情页成功
[ ] Fatal/ANR = 0
```

完整测试见 `K30S-TEST-PLAYBOOK.md`。

---

## 11. 相关文档

- `K30S-TEST-PLAYBOOK.md` — K30S 测试矩阵
- `RELEASE-CHECKLIST.md` — App 构建、归档、发布、更新全链路
- `APP-SIGNING.md` — 签名证书权威信息
- `TEST-RESULT-20260804-v0.2.3到v0.2.5-App内更新全链路.md` — App 内安装器 E2E 历史证据
- `TEST-RESULT-20260805-v0.2.5全链路公开发布与0.2.3公网升级验收.md` — 公网升级历史证据
- `USER-IMPACT-INCIDENTS.md` — 相关事故与永久教训
