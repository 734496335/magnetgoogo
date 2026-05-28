# iOS Pre-flight Audit Report

> 生成时间：2026-05-29 00:05 (UTC+8)
> 审计范围：magnetgoogo-app/ 全量源码 + 配置 + 资产
> 目的：Phase 3 EAS 云构建前隐患排查

---

## A. Expo 配置静态校验

### A1. expo-doctor（14/18 passed, 4 failed）

```
$ npx expo-doctor

Running 18 checks on your project...
14/18 checks passed. 4 checks failed. Possible issues detected:

✖ Check for issues with Metro config
It looks like that you are using a custom metro.config.js that does not extend "expo/metro-config".
This can lead to unexpected and hard to debug issues.
Advice: Update your "metro.config.js" to extend "expo/metro-config".

✖ Check that required peer dependencies are installed
Missing peer dependency: expo-font (Required by: @expo/vector-icons)
Missing peer dependency: react-native-worklets (Required by: react-native-reanimated)
Advice: Install missing required peer dependencies with "npx expo install expo-font react-native-worklets"
Your app may crash outside of Expo Go without these dependencies.

✖ Check that no duplicate dependencies are installed
Found duplicates for expo-font:
  ├─ expo-font@55.0.6 (at: node_modules\expo-font)
  └─ expo-font@14.0.11 (at: node_modules\expo\node_modules\expo-font)
Advice: Resolve your dependency issues and deduplicate your dependencies.

✖ Check that packages match versions required by installed Expo SDK

❗ Major version mismatches
package            expected  found
babel-preset-expo  ~54.0.10  55.0.20

🔧 Patch version mismatches
package            expected  found
expo               ~54.0.34  54.0.33
expo-crypto        ~15.0.9   15.0.8
expo-file-system   ~19.0.22  19.0.21
expo-linking       ~8.0.12   8.0.11

5 packages out of date.
```

### A2. ios 配置合并验证

```
$ npx expo config --type public --json → ios 段：

{
  "supportsTablet": false,
  "bundleIdentifier": "com.magnetgoogo.app",
  "buildNumber": "1",
  "infoPlist": {
    "NSAppTransportSecurity": {
      "NSAllowsArbitraryLoads": true
    },
    "LSApplicationQueriesSchemes": ["magnet", "https", "http"]
  }
}
```

**结论**：Phase 1 追加的 `buildNumber` / `infoPlist` / `NSAllowsArbitraryLoads` / `LSApplicationQueriesSchemes` 全部被 Expo 正确合并。✅

### A3. expo install --check

```
$ npx expo install --check

The following packages should be updated for best compatibility:
  expo@54.0.33 → ~54.0.34
  expo-crypto@15.0.8 → ~15.0.9
  expo-file-system@19.0.21 → ~19.0.22
  expo-linking@8.0.11 → ~8.0.12
  babel-preset-expo@55.0.20 → ~54.0.10
```

**风险评估**：4 个 patch 级 + 1 个 major 级（babel-preset-expo 55 vs expected 54）。Patch 版本差异极小，EAS Build 用云端 node_modules 会按 package-lock.json 安装，**不会阻塞构建**。babel-preset-expo major 差异是已知 Expo SDK 54→55 过渡期现象，暂不影响 iOS 构建。

---

## B. 源码 iOS 兼容性审计

### B1. expo-intent-launcher 引用

| 文件 | 行号 | 上下文 | 状态 |
|---|---|---|---|
| ForceUpdateModal.tsx | :4 | import | import 本身不执行，安全 |
| ForceUpdateModal.tsx | :25 | `IntentLauncher.startActivityAsync(...)` | 在 `Platform.OS !== 'android'` 守卫之后（:18-21），✅ |
| OptionalUpdateModal.tsx | :4 | import | import 本身不执行，安全 |
| OptionalUpdateModal.tsx | :25 | `IntentLauncher.startActivityAsync(...)` | 在 `Platform.OS !== 'android'` 守卫之后（:18-21），✅ |

**结论**：所有 IntentLauncher 调用均在 Android 守卫下。✅

### B2. 硬编码 Android 路径

搜索 `/data/data/`、`/storage/emulated/`、`content://`、`file:///android_asset/`：**0 matches**。✅

### B3. PermissionsAndroid / BackHandler / ToastAndroid

搜索结果：**0 matches**。✅

### B4. Linking.openURL / Linking.canOpenURL scheme 检查

| 文件 | 行号 | 调用 | scheme |
|---|---|---|---|
| ForceUpdateModal.tsx | :20 | `Linking.openURL(result.downloadUrl)` | http/https（已在 LSApplicationQueriesSchemes） |
| ForceUpdateModal.tsx | :33 | `Linking.openURL(result.downloadUrl)` | 同上 |
| ForceUpdateModal.tsx | :41 | `Linking.openURL(url)` | mirrors，同上 |
| ForceUpdateModal.tsx | :82 | `Linking.openURL(url)` | 同上 |
| ForceUpdateModal.tsx | :90 | `Linking.openURL(url)` | 同上 |
| OptionalUpdateModal.tsx | :20 | `Linking.openURL(result.downloadUrl)` | 同上 |
| OptionalUpdateModal.tsx | :31 | `Linking.openURL(result.downloadUrl)` | 同上 |
| OptionalUpdateModal.tsx | :39 | `Linking.openURL(url)` | 同上 |
| OptionalUpdateModal.tsx | :75 | `Linking.openURL(url)` | 同上 |
| OptionalUpdateModal.tsx | :126 | `Linking.openURL(url)` | 同上 |

**无 `Linking.canOpenURL('magnet:...')` 调用**。所有 openURL 均为 http/https URL，已在 LSApplicationQueriesSchemes 声明。✅

### B5. WebView — onShouldStartLoadWithRequest

```
src/components/VerifyWebView.tsx:528
  onShouldStartLoadWithRequest={() => true}
```

当前始终返回 `true`，**未拦截 magnet: 协议**。但 VerifyWebView 仅用于加载 HTTP/HTTPS 网页（验证 Cloudflare challenge），不涉及 magnet: scheme，**不阻塞 iOS 构建**。

**注意**：如果未来需要在 WebView 中拦截 magnet: 链接，需在 `onShouldStartLoadWithRequest` 中加 `url.startsWith('magnet:')` 判断并用 `Linking.openURL` 跳转。当前无此需求。

---

## C. Asset 审计

| 文件 | 尺寸 | 色深 | Alpha | iOS 要求 | 状态 |
|---|---|---|---|---|---|
| assets/icon.png | 1024×1024 | 8-bit RGB | 无 | 1024×1024 无 alpha | ✅ |
| assets/splash-icon.png | 1254×1254 | 8-bit RGB | 无 | 无特殊要求 | ✅ |
| assets/adaptive-icon.png | 1024×1024 | 8-bit RGB | 无 | Android-only，iOS 不用 | ✅ |
| assets/favicon.png | 1254×1254 | 8-bit RGB | 无 | Web-only | ✅ |

---

## D. 依赖 iOS 支持核查

所有 29 个 dependencies 的 `package.json` 均未声明 `expo.platforms` 排除 iOS。

已知风险：
- **expo-intent-launcher**：Android-only API，已在代码中加 Platform.OS 守卫。✅
- 其余包均为跨平台（react-native / expo 生态标准包）。

**结论**：无 iOS 排除性依赖。✅

---

## E. tsc 5 个基线 error 清单

```
1. src/components/ForceUpdateModal.tsx(16,41): error TS2694
   Namespace 'expo-file-system/build/index' has no exported member 'DownloadResumable'.

2. src/components/ForceUpdateModal.tsx(49,32): error TS2339
   Property 'cacheDirectory' does not exist on type 'typeof expo-file-system'.

3. src/components/OptionalUpdateModal.tsx(47,32): error TS2339
   Property 'cacheDirectory' does not exist on type 'typeof expo-file-system'.

4. src/core/LangContext.tsx(50,24): error TS2345
   Argument of type 'string | null' is not assignable to parameter of type 'SetStateAction<Lang>'.

5. src/core/VerifyManager.ts(83,41): error TS2576
   Property 'BLACKLIST_TTL_MS' does not exist on type '_VerifyManager'.
     Did you mean to access the static member '_VerifyManager.BLACKLIST_TTL_MS' instead?
```

**全部为历史 error，Phase 1/2 未引入新 error。** EAS Build 使用 `tsc` 仅做类型检查（不阻塞 `npx expo export`），这些 error 不影响云构建。

---

## F. 风险评级与 Phase 3 启动建议

### 评级：🟡 黄灯 — 可开 EAS Build，但建议先修 2 个文件

**阻塞项**：无。

**建议修再开（非阻塞但 expo-doctor 报了）**：

| # | 问题 | 影响 | 修复方式 | 紧急度 |
|---|---|---|---|---|
| 1 | 缺 expo-font peer dep | @expo/vector-icons 在非 Expo Go 环境可能崩 | `npx expo install expo-font` | 中 |
| 2 | 缺 react-native-worklets peer dep | react-native-reanimated 在非 Expo Go 环境可能崩 | `npx expo install react-native-worklets` | 中 |
| 3 | babel-preset-expo 55 vs expected 54 | 可能有构建期 warning | `npx expo install babel-preset-expo@~54.0.10` | 低 |

**结论**：EAS Build 可以启动。#1 和 #2 是 peer dep 警告，expo-doctor 明确说 "Your app may crash outside of Expo Go"，建议 Phase 3 前用 `npx expo install` 修掉（3 条命令，1 分钟）。#3 是 babel 版本差异，影响极小。

---

## 低优先级建议

1. **installApk 的 `.catch(() => {})` 应改为 toast 提示** — 当前 10 处 Linking.openURL 的 catch 都静默吞错，用户点了没反应也不知道为什么。建议改为 `Alert.alert('无法打开链接', url)` 或 Toast。
2. **VerifyWebView 的 `onShouldStartLoadWithRequest={() => true}` 可加 magnet: 拦截** — 当前不阻塞，但如果后续搜索结果页用 WebView 渲染，需要处理 magnet: scheme 跳转。
3. **metro.config.js 不 extend expo/metro-config** — expo-doctor 报了，长期可能导致 bundler 行为不一致。建议后续排期修复。
4. **expo-font 版本冲突** — `node_modules/expo-font@55.0.6` vs `node_modules/expo/node_modules/expo-font@14.0.11`，应 deduplicate。
