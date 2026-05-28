# MagGoogo iOS 开发作战计划（Windows-only，无 Mac 路线）

> **Audience**: mimo v2.5 pro（执行 Agent）
> **Author**: Cascade（架构 / 决策）
> **Status**: ACTIVE — 2026-05-28 起算
> **更新规则**: 每完成一个 Phase 在 §进度日志 追加一行；遇到本文未覆盖的决策点必须先回报 Cascade，不要自作主张。

---

## 0. 总目标 & 约束

**目标**: 把 `magnetgoogo-app/`（Expo SDK 54 + RN 0.81.5）打包成可在用户那台老 iPhone 上运行的 iOS App，开发期允许 7 天重签。

**硬约束**:
- 开发机只有 Windows，**不依赖 Mac**
- Apple 账号只用**免费 Apple ID**（不付 $99/年）
- 上架 App Store 不在本计划内（留到最后借 Mac）

**最终成果交付物**:
1. 装在 iPhone 上、可正常搜索/打开磁力的 MagGoogo iOS App
2. 一套可复现的 Windows 出包 + AltStore 安装流程
3. 后续可平滑切到 TrollStore（永久免签）或 Mac 上架 App Store

---

## 1. 路线总览

```
┌────────────── Windows ──────────────┐         ┌── Cloud ──┐         ┌─ iPhone ─┐
│ Cursor + mimo                        │         │           │         │          │
│ ├─ npm install / 代码改动             │         │ EAS Build │         │ AltStore │
│ ├─ npm start (Metro JS bundler)  ────┼─Wi-Fi──→│ macOS     │──.ipa──→│ Dev      │
│ └─ eas-cli (触发云构建)         ─────┼────────→│ worker    │         │ Client   │
└──────────────────────────────────────┘         └───────────┘         └──────────┘
                                                                            ↑
                                                                        AltServer
                                                                        (Win 后台)
```

**关键工具职责**:
- **EAS Build**：免费每月 30 次 iOS 云构建，产出 .ipa；Windows 只需 `eas-cli`
- **AltStore + AltServer**：用免费 Apple ID 在 iPhone 安装/每 7 天自动重签 .ipa
- **Expo Dev Client**：自定义 Expo Go，含项目原生模块；装 1 次后 JS 改动靠 Metro 热更，不用重出 ipa

---

## 2. Phase 0 — Windows 工具链安装

mimo 依次执行，每步执行后 `echo` 验证版本号。任何 step 失败立即停下回报。

### 0.1 检查 Node.js

```powershell
node --version  # 期望 >= 18.18
npm --version   # 期望 >= 9
```

如版本不符或缺失：到 https://nodejs.org/ 下 LTS（20.x），安装后重开终端验证。

### 0.2 全局安装 EAS CLI

```powershell
npm install -g eas-cli
eas --version  # 期望 >= 15.0
```

### 0.3 安装 iTunes（AltServer 强依赖）

**必须**装 Apple 官网的 iTunes（不能装 Microsoft Store 版本）：
- 下载: https://www.apple.com/itunes/download/win64
- 安装时勾选 Apple Mobile Device Support
- 装完用 USB 线连一次 iPhone，弹出"信任此电脑"在 iPhone 上点信任

### 0.4 安装 AltServer for Windows

- 下载: https://altstore.io/ → "Download for Windows"
- 解压 `AltInstaller.zip` 到 `C:\AltServer\`
- 双击 `Setup.exe` 安装，AltServer 图标会出现在系统托盘
- **不要在此步登录 Apple ID**，留到 Phase 4

### 0.5 验证清单

```powershell
node --version
npm --version
eas --version
# AltServer: 检查任务栏托盘图标是否常驻
# iTunes: powershell 执行 (Get-ItemProperty "HKLM:\SOFTWARE\Apple Inc.\iTunes").Version
```

✅ 全部通过 → 进入 Phase 1。

---

## 3. Phase 1 — 项目 iOS 代码适配

### 1.1 进入项目并装依赖

```powershell
# 工作目录:
# d:\lpproduct\magnet\magnetgoogo-app
npm install
```

如已装过，跳过。

### 1.2 给 expo-intent-launcher 加 iOS 守卫

**问题**: `IntentLauncher.startActivityAsync` 是 Android-only API，iOS 上调用会抛 `UnavailabilityError` 直接崩。

**改动文件**:
- `src/components/ForceUpdateModal.tsx`
- `src/components/OptionalUpdateModal.tsx`

**改法（两个文件相同模式）**: 把 `installApk` 函数体最外层包一层 `Platform.OS === 'android'` 守卫，iOS 分支改为调用 `Linking.openURL(downloadUrl)` 让 Safari 接管下载（开发期足够，后续生产可换 ad-hoc 分发或 TestFlight）。

伪代码示例：

```ts
import { Platform, Linking } from 'react-native';

const installApk = useCallback(async (fileUri: string) => {
  if (Platform.OS !== 'android') {
    // iOS: 走 Safari 下载 ipa 路径，下载链接由 configChecker 提供 ios_download_url
    if (downloadUrl) await Linking.openURL(downloadUrl);
    return;
  }
  // ... 原有 Android 安装逻辑
}, [/* deps */]);
```

**注意**:
- 不要删除 Android 分支
- `import * as IntentLauncher from 'expo-intent-launcher'` 这行保留，import 本身不会在 iOS 抛错
- 真实的 iOS 下载 URL 字段先用占位 `null`，等到 v0.2 再处理远程更新

### 1.3 验证 `app.json` 的 iOS 段

当前已有：
```json
"ios": {
  "supportsTablet": false,
  "bundleIdentifier": "com.magnetgoogo.app"
}
```

**追加** 以下字段（mimo 用 read+edit 修改）：

```json
"ios": {
  "supportsTablet": false,
  "bundleIdentifier": "com.magnetgoogo.app",
  "buildNumber": "1",
  "infoPlist": {
    "NSAppTransportSecurity": {
      "NSAllowsArbitraryLoads": true
    },
    "LSApplicationQueriesSchemes": [
      "magnet",
      "https",
      "http"
    ]
  }
}
```

**理由**:
- `NSAllowsArbitraryLoads`: 大量磁力站是 HTTP 明文，iOS ATS 默认拦截，必须开
- `LSApplicationQueriesSchemes`: `Linking.canOpenURL('magnet:...')` 在 iOS 14+ 必须显式声明 scheme 才返回 true
- `buildNumber`: iOS 必填，每次提交递增

### 1.4 准备 iOS 图标

iOS 要求 1024×1024 PNG，无圆角无 alpha 通道。

```powershell
# 检查 assets/icon.png 尺寸
# 若不是 1024x1024 让 mimo 用 sharp 或 ImageMagick 生成；当前文件路径:
# magnetgoogo-app/assets/icon.png
```

如尺寸正确无 alpha 即可。如有 alpha 通道：
```powershell
npx --yes sharp-cli -i assets/icon.png -o assets/icon.png --flatten --background "#fffdfb"
```

（mimo 如不会用 sharp，可暂跳过此步，EAS 构建报错时再修。）

### 1.5 验证 Phase 1

```powershell
npx tsc --noEmit
```

期望 0 error（如已有的历史 error 数量未增加即可，记录基线）。

---

## 4. Phase 2 — `eas.json` 补 iOS profile

当前 `eas.json` 只有 Android。改为：

```json
{
  "cli": {
    "version": ">= 15.0.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "ios": {
        "simulator": false,
        "resourceClass": "m-medium"
      }
    },
    "preview": {
      "distribution": "internal",
      "android": { "buildType": "apk" },
      "ios": {
        "simulator": false,
        "resourceClass": "m-medium"
      }
    },
    "production": {
      "android": { "buildType": "apk" },
      "ios": {
        "resourceClass": "m-medium"
      }
    }
  }
}
```

**说明**:
- `development` 是 Dev Client（含 Metro 调试），日常迭代用这个
- `preview` 是给 AltStore 安装的 standalone .ipa（无 Metro 依赖）
- `simulator: false` = 真机包（不是 simulator x86_64）
- `resourceClass: m-medium` = EAS 标准 macOS worker（免费层够用）

---

## 5. Phase 3 — 首次 EAS 云构建（Dev Client）

### 3.1 登录 EAS

```powershell
eas login
```

输入 Expo 账号（项目 `app.json` 已有 `projectId=9f312496-11bc-4e6b-8a92-9b281670c0df`，登录的账号必须是该 projectId 的所有者；如忘账号让用户提供）。

```powershell
eas whoami
```

### 3.2 触发 Dev Client 构建

```powershell
eas build --profile development --platform ios
```

**交互过程**:
1. 提示 "Generate a new Apple Distribution Certificate?" → **Y**
2. 提示输入 Apple ID → 用户的免费 Apple ID（无双因素的 app-specific password 或新建一个）
3. 提示选 Team → 选 `(Personal Team)`（免费账号唯一选项）
4. 提示 Provisioning Profile → 自动生成
5. 提示 Push Notifications → No（暂不需要）

**等待**: ~12–18 分钟（macOS worker 排队 + Pods + xcodebuild）

**产出**: 构建成功后终端打印 `.ipa` 下载 URL（也会在 https://expo.dev/accounts/.../projects/magnetgoogo-app/builds 看到）

### 3.3 把 .ipa 下载到 Windows

```powershell
# 直接浏览器下载，或:
curl -L -o magnetgoogo-dev-client.ipa "<上一步打印的 URL>"
```

存到 `magnetgoogo-app/build-ios/` 目录（mimo 自行创建该目录）。

---

## 6. Phase 4 — AltStore 装 Dev Client 到 iPhone

**前提**: iPhone 和 Windows PC 接同一个 Wi-Fi，USB 线连一次（首次配对）。

### 4.1 把 AltStore 装到 iPhone

1. 打开 AltServer 托盘图标 → "Install AltStore" → 选你的 iPhone
2. 弹窗输入 Apple ID + 密码（建议用专门的子 Apple ID，不要主账号；如开了两步验证用 [App Specific Password](https://appleid.apple.com/account/manage)）
3. 等约 1–2 分钟，AltStore 出现在 iPhone 主屏
4. 在 iPhone：设置 → 通用 → VPN 与设备管理 → 信任你的 Apple ID 开发者证书

### 4.2 把 .ipa 推送到 AltStore

**方法 A（USB 推荐）**: 用 USB 把 iPhone 连 PC，AltServer 托盘 → "Install IPA" → 选 .ipa 文件 → 选设备

**方法 B（Wi-Fi）**: AirDrop / 邮箱发到 iPhone，在 Files App 长按 .ipa → 共享 → AltStore

### 4.3 启用后台自动重签

在 iPhone AltStore App → 设置 → 启用 "Refresh in Background"。配合 Windows AltServer 7×24 在线，能在过期前自动重签。

**重签前提**: PC 开机 + AltServer 运行 + iPhone 与 PC 同 Wi-Fi。如做不到（PC 经常关机）就需要 7 天手动重打开 AltStore 一次。

---

## 7. Phase 5 — 日常 JS 迭代

```powershell
# Windows 上一次性长跑
npm start
```

- iPhone 上启动 Dev Client（不是 AltStore，是装好的 MagGoogo 图标），首次会让你扫码或选择 Metro server
- 选 PC 同网段的 IP（如 `192.168.x.x:8081`）连接
- 此后改 `.ts/.tsx` 文件保存，Dev Client 自动 fast refresh

**何时需要重新跑 EAS Build**:
- 改了 `package.json` 加新 npm 包且包含原生代码
- 改了 `app.json` 的 iOS 配置（infoPlist / plugins）
- 改了 `eas.json`

**只改 JS/TS 不需要重新构建**。

---

## 8. Phase 6 — 产出 Preview .ipa（给最终用户/重装时用）

```powershell
eas build --profile preview --platform ios
```

产出**不依赖 Metro 的 standalone ipa**。同样走 AltStore 装到 iPhone。这个版本就是"开发完成态"的可交付物。

---

## 9. Phase 7（后续）— 长期分发选项

开发完成后再决定，本计划不展开：

- **TrollStore 路线**（iPhone 在 iOS 14.0–17.0 间）: AltStore 装 TrollHelper → 提权 → 装 TrollStore → 装本 .ipa 永久免签
- **Mac + 付费账号 + App Store**: 借 Mac，`xcrun altool --upload-app -f magnetgoogo.ipa` → App Store Connect → 审核

---

## 10. 错误兜底

| 现象 | 排查方向 |
|---|---|
| `eas build` 卡 "Waiting in queue" 超 20 分钟 | 免费层排队，正常；切勿 ctrl-c |
| EAS 提示 "Invalid Apple credentials" | App-Specific Password 用错；到 appleid.apple.com 重新生成 |
| AltStore 安装报 "Could not find Apple Mobile Device Support" | iTunes 没装或装的是 Microsoft Store 版本，按 0.3 重装 |
| iPhone 上点开 App 闪退 | 看 PC 上 Metro 终端日志；或 iPhone 设置 → 隐私 → 分析 → 分析数据 找 crash log |
| 网络请求全部失败 | `NSAllowsArbitraryLoads` 没开，回 Phase 1.3 检查 app.json |
| `Linking.openURL('magnet:...')` 返 false | iOS 没有装支持 magnet 的客户端 App，这是预期行为，需要手动复制磁力到迅雷等 |
| Metro "No bundle url present" | iPhone 和 PC 不在同一 Wi-Fi，或防火墙挡 8081 端口 |

---

## 11. 进度日志（mimo 每完成一个 Phase 追加一行）

| 时间 | Phase | 结果 | 耗时 | 备注 |
|---|---|---|---|---|
| 2026-05-28 22:40 | Plan 起草 | OK | — | 由 Cascade 起草 |
| 2026-05-28 23:20 | Phase 0 | OK | ~15min | node v24.15.0 / npm 11.12.1 / eas 18.8.1 / AMDS 19.4.0.10 / AltServer 运行中 |
| 2026-05-28 23:30 | Phase 1 | OK | ~10min | installApk iOS 守卫 x2 / app.json ios infoPlist / icon 1024x1024 RGB OK / tsc 5 err (基线) |
| 2026-05-28 23:50 | Phase 2 | OK | ~5min | eas.json +development/preview/production ios profiles |
| | Phase 3 | | | |
| | Phase 4 | | | |
| | Phase 5 | | | |
| | Phase 6 | | | |
