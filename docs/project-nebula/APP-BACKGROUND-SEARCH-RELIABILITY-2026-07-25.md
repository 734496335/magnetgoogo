# App 后台搜索可靠性修复与 K30S 真机验收记录（2026-07-25）

## 1. 最终结论

用户反馈成立。旧实现虽然多数情况下启动了 Headless JS，但结果恢复、快速切后台、跨进程身份和前台服务并发清理均存在缺陷，用户体验等同于“切到后台后没有自动搜索”。

本轮已在 Redmi K30S 安装当前 debug APK，并完成当前源码与自定义原生模块的真机闭环。后台 handoff、提前返回持续恢复、自然完成、服务清理、同关键词进程重启、A→B 搜索替换均通过。当前后台搜索主链路判定为 **PASS**。

## 2. 旧版根因实证

旧正式包中，切后台后可观察到 `SearchKeepAlive.handoff`、`SearchHeadlessService.getTaskConfig` 和 Headless JS 搜索；一次完整搜索约需 70 秒以上，但前台页面恢复后只轮询 20 秒。因此后台稍后完成时，页面已停止读取结果，表现为“后台没有搜索”。

此外还存在快速切后台竞态：搜索会话异步创建前 App 已进入后台时，原实现会错过唯一一次 `background` 事件，导致完全不 handoff。

## 3. 修复过程中发现的全部后台缺陷

1. 前台恢复仅观察 20 秒，与真实后台耗时不匹配。
2. 后台只写最终结果，不持续桥接部分结果和进度。
3. 搜索后快速按 Home 可能错过 AppState handoff。
4. 旧后台任务可覆盖新搜索的共享结果存储。
5. Headless 未继承前台已获得的结果。
6. Headless 与 KeepAlive 清理不完整，异常相互牵连。
7. KeepAlive 使用 `START_STICKY`，存在无任务复活风险。
8. `android/` 被忽略，原生后台模块无法由版本库重建。
9. JS 进程重启后 token 从 1 重新计数；同关键词可误认旧快照为当前搜索，注入旧进度并提前停止新服务。
10. A→B 快速替换时，A 的延迟 stop 与 B 的 `startForegroundService` 交叉，可触发 `ForegroundServiceDidNotStartInTimeException` 并导致主进程崩溃。

## 4. 最终设计

### 4.1 持久进度与双通道恢复

后台持续保存 query、token、searchId、开始时间、源进度、部分结果、终态和错误。写入按时间和源步长节流并串行化。

同一 JS 运行时使用订阅实时推送；页面或进程恢复后每 1.5 秒读取持久快照，观察窗口与 Headless 30 分钟任务时限一致，不再固定 20 秒。

### 4.2 快速切后台补偿

除监听 `AppState → background` 外，搜索会话创建后再次读取 `AppState.currentState`。若此时已不在前台，立即 handoff，覆盖“先进入后台、后创建会话”的竞态。

### 4.3 严格后台所有权

后台状态由 `{query, token}` 严格标识：

- token 必须为非零且完全一致；
- 不再仅凭路由关键词恢复快照；
- 新 claim 清除旧终态结果；
- 新搜索撤销旧 owner；
- 旧任务失去所有权后中止，不能写入或停止新任务。

Token 改为时间、随机数和进程 nonce 组合生成的 31 位正整数，避免进程重启后从 1 重用。

### 4.4 前台服务并发安全

原生模块同步记录最新 KeepAlive token，重复或过期 stop 在进入 Service 前直接拒绝。Service 在 `onCreate` 立即调用 `startForeground()`，确保满足 Android 前台服务时限；stop 使用 `stopSelfResult(startId)`，旧 stop 不能拉下更新的 start。

Headless 和 KeepAlive 均按 token 清理；旧 Headless stop 会被当前 token 拒绝。KeepAlive 使用 `START_NOT_STICKY`，完成后无幽灵服务或常驻通知。

### 4.5 可重建原生模块

已新增受 Git 管理的 Expo config plugin 与 Kotlin 模板：

```text
magnetgoogo-app/plugins/with-search-background.js
magnetgoogo-app/plugins/search-background/*.kt.template
```

插件负责生成 4 个 Kotlin 文件、注册原生 Package、写入 Service 和权限。当前模板与本机构建使用的原生源码逐文件一致，`npx expo config --type prebuild` 可加载插件。破坏性的 `expo prebuild --clean` 尚未在当前脏工作区执行，仍应在独立工作树复验。

## 5. 自动化回归

后台专项已扩展为 B1–B10：

- B1：部分快照、终态和严格 token 匹配；
- B2：前后台结果稳定合并与 BTIH 去重；
- B3：30 分钟观察窗口和部分结果通道；
- B4：searchId 贯通及 token-aware 清理；
- B5：新 owner 隔离旧任务；
- B6：原生桥接由 Expo plugin 与模板纳管；
- B7：搜索会话创建后立即后台仍 handoff；
- B8：无 sticky 服务和清理异常隔离；
- B9：进程重启不重用旧后台身份；
- B10：前台服务 start/stop 竞态不崩溃。

结果：`31/31 PASS`。

## 6. K30S 当前 debug APK 真机证据

安装：

```text
adb install -r -t android/app/build/outputs/apk/debug/app-debug.apk
Performing Streamed Install
Success
```

包名：`com.magnetgoogo.app.debug`，版本 `0.1.14`，versionCode `4`。当前 JS 通过 Metro dev-client 加载，自定义 `SearchKeepAlive` 原生模块生效。

### 6.1 极速切后台

检测到搜索 KeepAlive start 后约 0.26 秒发送 Home：

```text
SearchKeepAlive start
SearchKeepAlive handoff
SearchHeadlessService onStartCommand/getTaskConfig
BackgroundSearch source start
```

结果：Headless 自动接管，PASS。

### 6.2 提前返回前台

Ubuntu2204 后台搜索尚未完成时返回 App，无需再次切换前后台：

```text
done 34/121, results 22
→ done 86/121, results 43
→ done 121/121, results 60, terminal=true
```

结果与进度持续自动恢复，PASS。

### 6.3 同关键词跨进程重启

保留旧 Ubuntu2204 快照，强制结束进程后重新搜索同一关键词。新 token 为 `1855691244`，未重用旧 token 1；旧 `107/121、57 条` 快照未注入，新服务未被提前停止。PASS。

### 6.4 A→B 搜索替换

初次反例真实触发：

```text
ForegroundServiceDidNotStartInTimeException
FATAL EXCEPTION: main
```

修复并重新安装后原样重放：

- A/Inception token：`1616387422`；
- B/Ubuntu2204 token：`552699424`；
- A 的延迟 stop 被原生模块和 Headless 服务拒绝；
- B 继续到 `121/121、58 条、terminal=true`；
- 无 FATAL、无进程崩溃。

PASS。

### 6.5 完成清理

搜索完成后：

- `SearchKeepAliveService` 不存在；
- `SearchHeadlessService` 不存在；
- 无活动中的 `search-running` 通知；
- 无幽灵服务。

PASS。

## 7. 最终验证

```text
npx tsc --noEmit
PASS

node scripts/app-adversarial-tests.mjs
31/31 PASS

node scripts/fluency-extreme-tests.mjs
17/17 PASS

./gradlew testDebugUnitTest assembleDebug -PreactNativeArchitectures=arm64-v8a
BUILD SUCCESSFUL，495 tasks
```

当前 debug APK：

```text
magnetgoogo-app/android/app/build/outputs/apk/debug/app-debug.apk
```

## 8. 剩余边界

后台搜索主链路已通过当前 K30S 真机验收。仍未覆盖的扩展场景：

- 锁屏后长时间运行；
- MIUI 深度省电、内存清理或系统主动杀进程；
- 独立工作树执行 `expo prebuild --clean` 后的重建验证；
- MIUI UIAutomator 故障导致的语义 UI 自动化；
- Expo SDK 54 依赖补丁漂移。

这些属于后续耐久性和工程维护门禁，不否定本轮前后台搜索主链路 PASS。
