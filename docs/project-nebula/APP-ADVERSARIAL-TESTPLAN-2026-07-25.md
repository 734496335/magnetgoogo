# App 对抗性缺陷审查与回归测试（2026-07-25）

## 1. 目标与范围

本轮不重复既有列表流畅度测试，而是从功能正确性、异常数据、并发状态机、生命周期、真机交互和构建兼容六个方向寻找可复现缺陷。

覆盖范围：

- 首页、搜索页、收藏和历史记录；
- 数据源启动同步、远程配置、语言和主题；
- 搜索连续换词、停止、排序、前后台切换；
- Android `SearchKeepAlive` 原生服务；
- Expo/TypeScript/Gradle 构建链。

不覆盖：

- Expo Go 不包含自定义 `SearchKeepAlive`，因此原生后台保活/Headless 搜索仅完成代码审查、自动化契约和 Kotlin 编译，未完成当前代码的 K30S 运行时验收；
- MIUI 的 `uiautomator dump` 因系统缺少 `/data/system/theme_config/theme_compatibility.xml` 仍不可用。

## 2. 发现并修复的缺陷

| 编号 | 缺陷 | 影响 | 修复 |
|---|---|---|---|
| B01 | 启动时缓存源写入导致初始化 Effect 再执行，远程同步两次 | 重复网络、重复写盘、启动负担 | `SourceContext` 使用稳定回调、单飞 Promise 和 sourceCount ref |
| B02 | 连续换词时旧 `doSearch` 可在异步等待后重新取得控制权 | 旧结果回灌、页面状态被旧搜索覆盖 | 增加 search generation；所有异步边界和回调验证当前会话 |
| B03 | 旧搜索结束会无条件停止原生前台服务 | 可能停止新搜索的保活通知和 WakeLock | JS/Kotlin 全链路传 token；Service 忽略旧 token 的 stop |
| B04 | 搜索历史/收藏的 JSON 结构异常可进入缓存 | `.filter/.some` 等运行时崩溃 | 新增存储清洗器、去重、字段归一和数组副本返回 |
| B05 | `Office2021`、`Ubuntu2204`、`Photoshop2024` 被判为电影 | 卡片分类、图标和标签错误 | 软件规则前置于宽泛电影编号规则 |
| B06 | DTS 正则把 `\b` 写入字符组，无法识别普通 DTS | 标签缺失 | 改为 `\bDTS(?:\b|-)` |
| B07 | 累加器不识别 GiB/MiB，综合排序与卡片大小排序不一致 | 1 GiB 可能排在 900 MB 后面 | 统一二进制/十进制大小解析，并注入累加器 |
| B08 | 远程配置竞速接受第一个 HTTP 200，即使结构错误 | 错误更新判断、异常下载字段 | Promise.any 分支在胜出前执行结构校验 |
| B09 | 中文同步失败 Toast 检测字符串为乱码 | 错误提示显示成普通样式 | 检测“失败”及英文 fail/error |
| B10 | 首页循环渐变动画卸载时未停止 | 重复进出页面后的动画资源泄漏 | 保存 animation 实例并在 cleanup 中 stop |
| B11 | 历史、统计或埋点异常可阻塞/中断搜索启动 | 用户点击搜索后无结果或页面挂在搜索中 | 历史和统计并行容错；埋点降级；搜索主流程捕获异常并结束状态 |
| B12 | 路由、输入框、历史和引擎可能使用不同空白/长度形式 | 重复历史、搜索词显示与实际请求不一致 | 统一 `normalizeSearchTerm`，按 Unicode code point 限制 100 字符 |

## 3. 自动化用例

新增：`magnetgoogo-app/scripts/app-adversarial-tests.mjs`

| 类别 | 用例 | 断言 |
|---|---|---|
| 搜索输入 | Q1–Q2 | 清理空白；Unicode 100 code point 截断，不切断代理对 |
| 本地存储 | S1–S2、D1 | 错误 JSON 形状、坏行、重复项不会进入缓存或触发崩溃 |
| 远程配置 | C1–C2、D2 | 版本比较稳定；HTTP 200 垃圾配置不能赢得竞速 |
| 多语言 | I1 | 10 种语言键完整，动态翻译函数均可调用 |
| 资源建模 | M1–M5 | 软件分类、DTS、GiB/bytes、综合排序、BTIH 稳定 ID |
| 启动同步 | P1–P2 | 初始化 Effect 稳定、同步单飞、中文错误样式正确 |
| 搜索状态机 | R1–R4 | 旧搜索失效、埋点不阻塞、搜索词一致、原生 stop token 化 |
| 生命周期 | U1 | 首页循环动画卸载时停止 |

结果：

```text
node scripts/app-adversarial-tests.mjs
21/21 PASS
```

既有回归：

```text
node scripts/fluency-extreme-tests.mjs
17/17 PASS

d3 top20 churn = 0
```

类型门禁：

```text
npx tsc --noEmit
PASS
```

## 4. K30S 真机用例与结果

运行方式：Expo Go 54.0.8 + Expo SDK 54 + Metro + `adb reverse tcp:8081 tcp:8081`。

### 4.1 冷启动重复同步

预期：读取一次缓存，只发起一轮远程同步并保存一次。

结果：

- `Loaded 125 sources from disk cache`：1 次；
- `Saved 125 sources to disk cache`：1 次；
- 修复前同一启动周期曾出现两次保存，修复后未复现。

结论：PASS。

### 4.2 连续换词竞态

步骤：启动 `Inception`，约 3.4 秒后切换为 `Ubuntu2204 LTS`。

结果：

- 旧 `Inception` 仅完成首个快速阶段 12 个源后终止，没有继续执行完整 125 个源；
- 未发现旧结果覆盖新查询、React TypeError、FATAL 或 ANR。

结论：PASS。

### 4.3 停止、排序和快速滚动

步骤：搜索中触发停止，连续切换大小、时间、相关性和综合排序，并多次上下 fling。

结果：

| 指标 | 数值 |
|---|---:|
| Total frames | 681 |
| Modern janky frames | 4（0.59%） |
| P50 | 7ms |
| P90 | 13ms |
| P95 | 14ms |
| P99 | 27ms |
| Missed vsync | 1 |
| Frame deadline missed | 4 |

无 AndroidRuntime/ReactNative 错误、FATAL 或 ANR。ADB 注入会放大 High input latency 与 legacy jank，不作为本轮现代帧截止门禁。

结论：PASS。

## 5. 构建门禁

```text
npx expo export --platform android --output-dir .test-tmp/app-adversarial-export --clear
PASS：1400 modules，Android HBC 4.72 MB

./gradlew testDebugUnitTest assembleDebug -PreactNativeArchitectures=arm64-v8a
BUILD SUCCESSFUL：495 tasks，24s
```

App 自身当前没有 JVM 单元测试源（`app:testDebugUnitTest NO-SOURCE`），但 Kotlin 编译、依赖模块单测和 APK 组装均通过。

## 6. 尚未关闭的风险

1. `expo-doctor` 为 17/18：顶层 `babel-preset-expo` 为 55.0.20，而 Expo SDK 54 期望 `~54.0.10`；另有 5 个 Expo 补丁版本落后。当前导出和 Gradle 构建通过，但这是明确的依赖漂移风险，应独立升级并做完整回归，不能与本轮功能修复混在一起。
2. `SearchKeepAlive` token 修复已通过静态契约和 Kotlin/Gradle 编译，但 Expo Go 无此自定义模块；仍需可安装 development APK 在 K30S 上验证通知、WakeLock、后台 handoff、旧 token stop 和进程恢复。
3. MIUI 系统问题阻塞 `uiautomator`，目前真机点击采用已知坐标与日志/帧指标交叉验证，尚不能形成稳定的语义控件自动化。
4. 搜索源属于外部动态网络，单个源超时、403 和验证码仍会发生；本轮验证的是 App 不崩溃、状态可结束，而不是保证所有源可用。

## 7. 裁决

- 本轮发现并关闭 12 类可复现缺陷；
- 新增对抗用例 21/21，通过原流畅度回归 17/17；
- K30S 前台核心路径和构建链通过；
- 当前可继续功能开发，但在发布前必须关闭 Expo 依赖漂移，并使用 development APK 补齐原生后台保活运行时验收。
