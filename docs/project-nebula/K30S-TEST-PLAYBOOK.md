# K30S 真机测试权威手册

> **用途**：以后凡是“装到 K30S 测一下”“做主流程测试”“验证源/搜索/更新/资源页”的任务，先按本文决定是 Debug 证据还是 Release 证据，再执行对应矩阵。
>
> **设备**：Redmi K30S，serial `a1ea223a`。
>
> **核心原则**：Debug 用来做深度可观测和搜索质量审计；Release 用来证明正式二进制、签名、升级、生命周期和用户可见主流程。两种证据不能互相冒充。

---

## 1. 测试分层

| 层级 | 包名 | 主要目的 | 可用能力 | 不能证明 |
|---|---|---|---|---|
| Debug standalone | `com.magnetgoogo.app.debug` | 搜索源、结果质量、私有缓存、搜索报告、故障诊断 | `run-as`、Debug report、源 override | 正式签名/正式包行为完全一致 |
| Formal Release | `com.magnetgoogo.app` | 最终 APK 身份、正式签名、升级、生命周期、用户主流程 | WindowManager、Activity、framebuffer、logcat、installed SHA | 私有 cache 内容（Release 不可 `run-as`） |
| 旧版→新版 App 内升级 | 正式包 | 用户真实更新体验 | 远程 config、APK 下载、MIUI installer、数据保留 | 不能由单纯 `adb install -r` 代替 |

---

## 2. 每次真机测试的统一前置

```bat
adb devices
adb -s a1ea223a shell input keyevent 224
adb -s a1ea223a shell wm dismiss-keyguard
adb -s a1ea223a shell svc power stayon true
```

测试前可关闭已知抢前台的专用测试包：

```bat
adb -s a1ea223a shell am force-stop uni.UNIB56C11F
```

不要卸载/清数据该包，只在 MagGoogo 测试窗口临时 force-stop。

### 建议先清 logcat

```bat
adb -s a1ea223a logcat -c
```

这样 Fatal/ANR 证据不会混入旧日志。

---

## 3. Debug：主流程与搜索质量测试

### 3.1 构建/安装

推荐 standalone Debug：

```bat
cd magnetgoogo-app
npm run android:k30s
```

或手工：

```bat
cd magnetgoogo-app/android
gradlew.bat assembleDebug -PstandaloneDebug=true -PreactNativeArchitectures=arm64-v8a
adb -s a1ea223a install -r app/build/outputs/apk/debug/app-debug.apk
```

### 3.2 Debug 包身份

```bat
adb -s a1ea223a shell dumpsys package com.magnetgoogo.app.debug
```

必须确认 versionName/versionCode 与本轮候选一致。

---

## 4. Debug：标准搜索 UX 套件

现有权威入口：

```bat
python scripts/test_k30s_search.py --compact --output scripts/k30s-search-quality.json
```

默认四类：

```text
EN movie   Inception
ZH movie   流浪地球
ZH anime   海贼王
EN series  Breaking Bad
```

脚本会：

1. 检查设备和 Debug 包；
2. 唤醒/解锁；
3. 阻止其它测试 App 抢前台；
4. 每个 query 前 force-stop；
5. 用 deep link 启动搜索；
6. pin MagGoogo task；
7. 从 Debug 私有 `last-search-report.json` 读取完整搜索报告；
8. 汇总 loaded hosts / pools / errors / relevance；
9. 运行结果质量审计；
10. 强制 `hash placeholder title = 0`；
11. 有 hard finding 时返回非 0。

### 4.1 重点验收字段

每个 query 至少检查：

```text
completed = true
quality hard finding = 0
hash placeholder title = 0
high-relevance 结果合理
loadedHostCount / loadedPoolCount 与当前源包规模相符
没有异常 skipped 全池
```

结果数量本身不是固定常量；公网源实时变化会导致 188/190 之类差异，不能把“数量不完全相等”当回归。

---

## 5. Debug：广覆盖搜索验证

### 5.1 8 类 benchmark

```bat
python scripts/test_k30s_search.py --benchmark --compact --max-wait 180 --output scripts/k30s-benchmark.json
```

覆盖：

- EN/ZH movie
- EN/ZH anime
- EN series
- Software
- code-like title

Benchmark 模式会尽量耗尽加载到 App runtime 的 hosts，用于初始源排名和大范围源质量评估。

### 5.2 24 类 validation

```bat
python scripts/test_k30s_search.py --validation --compact --output scripts/k30s-validation.json
```

覆盖中英日韩、电影、剧集、动漫、游戏、软件、番号样式、多词 query。

`--validation` 默认 cold-start source-learning 模式，适合验证新规则/排序改动不会只对几个热门 bait 过拟合。

### 5.3 分批执行

```bat
python scripts/test_k30s_search.py --benchmark --only "EN movie" --only "Software" --append --output scripts/k30s-benchmark.json
```

长任务因连接层中断时，先检查：

- 设备上搜索是否仍在跑；
- 输出 JSON 是否已产生；
- Python/ADB 进程是否仍活着。

不要看到 DevSpace 502 就直接重复启动整批测试。

---

## 6. 重复搜索 / 历史搜索 freshness 专项

这是 v0.2.6 必须保留的回归门禁。

### 6.1 Debug 强证据

对同一 query 连续发起两个**不同 run intent**，例如 `Inception`。

验收：

- `report id` 不同；
- `startedAt` 不同；
- 第二轮真正重新跑 source；
- 第二轮结果可以和第一轮数量不同；
- 两轮 hard=0；
- 不允许第二轮直接恢复第一轮 completed session。

永久自动门禁在：

```text
magnetgoogo-app/scripts/app-adversarial-tests.mjs
R3B: history and repeated same-query launches always create a fresh live search run
```

### 6.2 Formal Release 证据

Release 不写 Debug report，因此用：

1. 第一次 `magnetgoogo:///search?q=Inception`；
2. 等页面稳定；
3. 再给同一个 Activity 发完全相同 no-run URI；
4. 对比 framebuffer；
5. 第二轮应明显重新进入加载/结果重建状态；
6. 再等待其独立稳定。

v0.2.6 当前正式包实测：

```text
second-run frame MAE = 12.3088
changed pixels >4 = 31.23%
second-run stable-window MAE = 0.0017
```

说明同词 intent 不是静态复用旧完成页。

---

## 7. Debug：App 主流程 smoke

现有脚本：

```bat
python scripts/test_k30s_app_flows.py --package com.magnetgoogo.app.debug --output scripts/k30s-app-flows.json
```

当前脚本会检查：

- package identity
- cold start
- source encrypted disk cache
- resources route
- media cache/revision
- movie detail route/detail cache
- favorites
- settings
- HOME hot resume
- force-stop cold resume
- Fatal/ANR

### 7.1 重要限制

这个脚本的私有 cache 断言依赖：

```text
run-as <package>
```

因此它**只适合作为 Debug 完整 smoke**。

对 `com.magnetgoogo.app` Release 调用时会得到：

```text
run-as: package not debuggable
```

不得把它误报为：

```text
source cache missing
media cache missing
```

---

## 8. Formal Release：安装前门禁

正式包必须先在 PC 上通过：

```bat
cd magnetgoogo-app
npx tsc --noEmit
node scripts/app-adversarial-tests.mjs
npm run test:resource-feed
npm run test:media-network
npm run test:media-security
npm run test:media-cache
npm run test:update-download
npm run test:release-build
npm run test:analytics-v2
npm run test:resource-auto-sync
node scripts/fluency-extreme-tests.mjs
```

最终 APK 再用：

```bat
python scripts/verify_release_apk.py <apk> --previous <previous-apk> ...
```

正式包没有通过这些 deterministic gates 前，不进入 K30S 最终验收。

---

## 9. Formal Release：字节级安装验收

详见 `K30S-INSTALL-PLAYBOOK.md`。

最低要求：

```text
[ ] adb install -r = Success
[ ] installed base.apk SHA = 本地 final APK SHA
[ ] package=com.magnetgoogo.app
[ ] version/code 正确
[ ] firstInstallTime 保持不变
```

不要使用“之前同版本的某个正式 APK 已装过”替代当前最终 SHA 的真机验收。

---

## 10. Formal Release：不依赖 `run-as` 的主流程测试

### 10.1 冷启动

```bat
adb -s a1ea223a shell am force-stop com.magnetgoogo.app
adb -s a1ea223a shell am start -W -n com.magnetgoogo.app/com.magnetgoogo.app.MainActivity
```

必须：

- `Status: ok`
- `Activity` 正确
- WindowManager 前台是 `com.magnetgoogo.app`
- 启动耗时没有明显劣化

### 10.2 WindowManager 前台确认

```bat
adb -s a1ea223a shell dumpsys window
```

查：

```text
mCurrentFocus
mFocusedApp
```

### 10.3 framebuffer 取证

K30S UIAutomator 不稳定时，用：

```bat
python scripts/inspect_k30s_screen.py
```

或项目内存截图脚本。

可比较：

- 页面进入前/后像素差异；
- 页面加载中/稳定后的 MAE；
- 全白/全黑/非空白结构；
- 同 query 第二轮是否重新变化。

不要把视觉哈希完全一致作为“业务结果必须一致”的要求；动态图片、时钟、动画可改变像素。

---

## 11. Formal Release：路由矩阵

使用显式 component，避免 MIUI resolver：

```bat
adb -s a1ea223a shell am start -W -a android.intent.action.VIEW -d "magnetgoogo:///resources" com.magnetgoogo.app/com.magnetgoogo.app.MainActivity
```

同理验证：

```text
magnetgoogo:///search?q=Inception
magnetgoogo:///resources
magnetgoogo:///movie/<movieId>?kind=movie
magnetgoogo:///favorites
magnetgoogo:///settings
```

注意 URI 含 `&` 时必须完整 quote，见 `K30S-INSTALL-PLAYBOOK.md`。

验收每个 route：

- Activity 仍为 MagGoogo；
- 页面发生合理结构变化；
- 最终稳定；
- 不出现白屏/崩溃；
- logcat 无 Fatal/ANR。

---

## 12. 生命周期测试

### 12.1 HOT resume

```bat
adb -s a1ea223a shell input keyevent 3
adb -s a1ea223a shell am start -W -n com.magnetgoogo.app/com.magnetgoogo.app.MainActivity
```

应出现：

```text
LaunchState: HOT
```

### 12.2 force-stop COLD recovery

```bat
adb -s a1ea223a shell am force-stop com.magnetgoogo.app
adb -s a1ea223a shell am start -W -n com.magnetgoogo.app/com.magnetgoogo.app.MainActivity
```

应出现：

```text
LaunchState: COLD
Status: ok
```

然后：

```bat
adb -s a1ea223a shell pidof com.magnetgoogo.app
```

确认进程仍存活。

---

## 13. Crash / ANR 验收

### 13.1 当前测试窗口 logcat

测试前 `logcat -c`，测试后：

```bat
adb -s a1ea223a logcat -d
```

重点搜索：

```text
FATAL EXCEPTION
AndroidRuntime
ANR in com.magnetgoogo.app
ReactNativeJS
```

### 13.2 exit-info

```bat
adb -s a1ea223a shell dumpsys activity exit-info com.magnetgoogo.app
```

区分：

- `USER REQUESTED`：测试自己 force-stop，正常；
- WebView isolated process `ISOLATED NOT NEEDED`：正常清理；
- CRASH / ANR / native crash：失败。

不要把测试自己 `am force-stop` 造成的 exit-info 当 App crash。

---

## 14. 源更新在 K30S 的验证

源发布后，不只测公网端点，还要让 App 实际消费。

### Debug 推荐流程

1. 确认远程 `sources.enc.json` exact SHA；
2. 清理 Debug 自己的数据，或使用新的/到期 source pack；
3. 启动 App；
4. `test_k30s_search.py` 查看 `inventory.sourcePackOrigin`、loaded hosts/pools；
5. 跑 `Inception` + 中文 query；
6. result quality hard=0；
7. hash placeholder=0。

### 不推荐的做法

- 只看到服务器 `HTTP 200` 就宣告 App 源更新成功；
- 只看源数量，不执行真实搜索；
- 为了强制远程同步随便清正式包用户数据。

完整源发布见 `SOURCE-RELEASE-PLAYBOOK.md`。

---

## 15. 真实 App 更新 E2E

### 发布前本地隔离 E2E

使用：

```bat
python scripts/local_update_e2e_server.py --apk <target.apk> --latest-version <NEW>
adb -s a1ea223a reverse tcp:8765 tcp:8765
```

测试变体只允许修改本地 config endpoint / cleartext localhost，下载与 installer 业务代码必须和正式源码一致。

### 发布后的公网 E2E

必须：

1. 安装一个真实旧正式版；
2. 保留数据；
3. App 从**公开 config**检测到新版本；
4. 点击立即更新；
5. 从公开 primary 下载 APK；
6. APK 完整性检查通过；
7. 自动拉起 MIUI installer；
8. 用户确认；
9. 升级后 package/version/code 正确；
10. `firstInstallTime` 不变；
11. 重要持久化数据仍在；
12. 资源/搜索主流程正常；
13. Fatal/ANR=0。

只有本地 E2E 通过不能替代生产链 E2E。

---

## 16. K30S 的已知假失败

### `uiautomator dump`

可能：

```text
ERROR: could not get idle state
```

处理：切换 WindowManager + framebuffer，不要反复无脑 dump。

### `run-as formal`

```text
run-as: package not debuggable
```

这是 Release 正常安全特性。

### DevSpace 502

可能只是连接层断开，设备上的测试仍继续。

处理：

1. 检查进程；
2. 检查输出 JSON；
3. 检查设备 Activity；
4. 确认未在跑后才重启测试。

### 搜索结果数量波动

实时站点会波动。主要判定：

- 搜索是否 fresh；
- 完成状态；
- relevance；
- hard findings；
- title/magnet 合法；
- pool/source 覆盖。

---

## 17. 发布候选最终 K30S Gate

```text
Debug 深度测试
[ ] 4 类 UX query PASS
[ ] 广覆盖 validation/benchmark 按变更风险执行
[ ] hard finding = 0
[ ] hash placeholder = 0
[ ] source/media 主流程 PASS
[ ] lifecycle PASS

Formal 最终字节
[ ] verify_release_apk PASS
[ ] adb install -r Success
[ ] installed SHA exact match
[ ] retained-data upgrade
[ ] cold/hot/cold-recovery PASS
[ ] repeated-query freshness PASS
[ ] resources PASS
[ ] detail PASS
[ ] favorites/settings 主路由无崩溃
[ ] Fatal/ANR = 0

发布链
[ ] 旧版→新版 App 内更新本地 E2E
[ ] 发布后生产 E2E
```

---

## 18. 相关文档

- `K30S-INSTALL-PLAYBOOK.md`
- `RELEASE-CHECKLIST.md`
- `SOURCE-RELEASE-PLAYBOOK.md`
- `SOURCE-CRAWL-AND-TEST-PLAYBOOK.md`
- `USER-IMPACT-INCIDENTS.md`
