# 流畅性 & 卡片加载 — 完整测试计划（极端条件）

> 目标版本：当前 App（magnetgoogo-app / 搜索结果页 `app/search.tsx`）
> 问题域：卡顿、列表高频跳动/闪烁、卡片加载抖动、排序 thrash、骨架屏闪烁
> 自动化脚本：`magnetgoogo-app/scripts/fluency-extreme-tests.mjs`
> 日期：2026-07-19

---

## 1. 问题机理（对照代码）

| 机制 | 位置 | 极端条件下风险 |
|------|------|----------------|
| 多源 `onItems` → `_notify` → **500ms debounce** 刷新 | `search.tsx` `debouncedSync` | 源多时仍约 2 次/秒全量 setState → 重排 |
| 每次 sync **全量 sort** dedup + 再 `toResultCardModel` | `syncFromSession` | 大结果集 CPU 尖峰 → 掉帧 |
| `sortedResults` 再 copy+sort | `useMemo` | 双重排序 |
| FlatList **无 `getItemLayout`**，标题最多 3 行变高 | FlatList props | 滚动中高度变化 → 跳动 |
| `removeClippedSubviews` + `LinearGradient` 卡片 | renderListItem | Android 裁剪重绘闪烁 |
| `AnimatedCard` 仅 index&lt;8 入场动画 | `AnimatedCard` | 列表重排导致前 8 项 remount 时再动画/错位 |
| 骨架 `ListEmptyComponent` ↔ 首条结果切换 | FlatList | 骨架→列表整页替换闪一下 |
| status 行 `doneCount/results.length` 高频变 | statusRow | 顶部高度微变 + 重排 |
| 切排序 / 收藏 / 复制 改 `extra` 依赖 | renderListItem deps | 全列表 re-render |
| 后台 handoff 整表 hydrate | AppState | 回前台瞬间大列表替换跳动 |
| 语言切换清空 card cache | `_cachedLang` | 全卡 model 重建 |

**高频跳动主因假设**：增量结果导致 **排序名次剧烈变化** + FlatList 按新 data 重绑 + 无稳定 layout。

---

## 2. 用例总表

### 2.1 列表跳动 / 排序 thrash

| ID | 场景 | 前置 | 步骤 | 期望 | 优先级 |
|----|------|------|------|------|--------|
| J1 | 多源 drip 到达 | ≥50 源，热门词 | 搜索后静置观察列表前 20 项 | 名次 5s 内不应「上下乱跳」；允许末尾追加 | P0 |
| J2 | 同源重复 hash 合并 | 多源同一 btih | 观察 sourceCount 角标 | 卡片 **id 不变**，位置尽量稳定 | P0 |
| J3 | 大结果集（500+） | mock / 热门词 | 滚动中途源继续返回 | 滚动位置不无故回顶；无明显闪白 | P0 |
| J4 | 排序切换 thrash | 已有 200+ 结果 | 综合↔相关↔大小↔日期连点 | 切换一次一稳，无连闪；箭头状态正确 | P0 |
| J5 | 相关度分割线 | 混合相关/不相关 | 切「相关度」 | divider 只出现一次，滚动不抖动 | P1 |
| J6 | 搜索中途改排序 | 搜索进行中 | 点大小排序 | 不崩溃；不永久锁骨架 | P1 |
| J7 | 快速连搜不同词 | 冷却 3s 限制 | 3s 后连搜 3 词 | 只显示最后一词结果；无串台 | P0 |
| J8 | 停止搜索 | 搜索中 | 点「停止」 | 立即停 spinner；列表冻结当前集 | P0 |

### 2.2 卡片加载 / 骨架 / 动画

| ID | 场景 | 步骤 | 期望 | 优先级 |
|----|------|------|------|--------|
| C1 | 首屏骨架 | 新搜索无缓存 | 先 4 张骨架 shimmer，首条结果后切列表 | P0 |
| C2 | 骨架消失闪白 | 慢网 | 骨架→首卡切换无整屏白闪 &gt;1 帧可感知 | P0 |
| C3 | 入场动画上限 | 结果&gt;8 | 仅前 8 张有 fade/slide；后面静态出现 | P1 |
| C4 | 重排后动画 | drip 导致前 8 换人 | 不应反复「飞入」；已出现卡保持稳定 | P0 |
| C5 | 长标题 3 行 | 超长 title | 高度变高后邻卡不错位跳动 | P0 |
| C6 | 无 magnet 卡 | 脏数据 | 不显示操作钮；列表不错位 | P1 |
| C7 | 标签行 0/多 tag | 多种 title | tags 有无切换时高度变化平滑 | P1 |
| C8 | 收藏切换 | 点 bookmark | 仅该卡图标变，整表不闪 | P0 |
| C9 | 复制反馈 | 连点复制 | 2s 内「已复制」；无列表抖动 | P1 |
| C10 | 主题/深浅色 | 设置切换后回搜索 | 卡背景一致，无半新半旧 | P1 |

### 2.3 滚动流畅 / 掉帧

| ID | 场景 | 步骤 | 期望 | 优先级 |
|----|------|------|------|--------|
| S1 | 快速 fling 长列表 | 300+ 结果 | 无明显卡顿条；不白块长时间 | P0 |
| S2 | 滚动中源更新 | 搜索未完成时 fling | 不强制回顶；跳动 &lt; 2 行/次刷新 | P0 |
| S3 | 滚动中打开 magnet | 点「打开」 | 不卡死主线程 | P1 |
| S4 | 滚动中点收藏 | 快速点多张 | 反馈及时；列表不炸 | P1 |
| S5 | removeClippedSubviews | Android 快速上下扫 | 卡不「空白洞」久留 | P0 |
| S6 | 低端机/热机 | 连续搜 10 次 | 不 ANR；内存不线性暴涨崩溃 | P0 |

### 2.4 生命周期 / 极端交互

| ID | 场景 | 步骤 | 期望 | 优先级 |
|----|------|------|------|--------|
| L1 | 搜中途返回首页再进 | 同 q | 恢复 session，不重搜（除非新 q） | P0 |
| L2 | 后台 handoff | 搜中压 Home | 回前台结果可 hydrate；无双列表闪 | P0 |
| L3 | 后台未完成回前台 | 轮询 1.5s | progress 更新不导致列表抽风 | P1 |
| L4 | 验证码 WebView | 触发 verify | 弹层期间列表不继续狂刷导致卡死 | P1 |
| L5 | 无源 | sources=0 | 空态引导，无骨架死循环 | P0 |
| L6 | 全源失败 | mock 全 fail | 空结果文案；无永久 searching | P0 |
| L7 | 极慢首包 | 首结果 10s+ | 骨架持续；超时后有结束态 | P1 |
| L8 | 超长 query / 特殊字符 | emoji、空格、标点 | 不崩；冷却与 maxLength 生效 | P1 |
| L9 | 语言中途切换 | 搜中切语言 | 文案刷新；卡不全灭重建闪屏 | P2 |
| L10 | 通知点进来 | 后台完成通知 | 进搜索页数据一致 | P1 |

### 2.5 数据层极端（可自动化）

| ID | 场景 | 断言 | 优先级 |
|----|------|------|--------|
| D1 | 1000 条 drip，debounce 500ms | UI 刷新次数 ≪ 事件次数 | P0 |
| D2 | 同 hash 多源 | id 稳定 = btih | P0 |
| D3 | 排序名次抖动度量 | top20 位置 churn 率有上限 | P0 |
| D4 | model cache hit | dirty 才重建 | P1 |
| D5 | 无 hash 条目 | 不污染 dedup map；可展示 | P1 |
| D6 | 双排序一致性 | sync 内排序与 comprehensive 规则不矛盾 | P1 |

---

## 3. 设备手工操作路径（K30S / 真机）

1. 安装当前 debug/release 包，冷启动。
2. **J1/C1/C2**：搜「流浪地球」/「Inception」，录屏 30s，逐帧看前 20 卡是否跳动。
3. **S1/S2**：结果 &gt;100 时快速 fling，同时看 status 进度是否仍在涨。
4. **J4/J6**：搜索中途连切四个排序。
5. **L1/L2**：搜中返回 / 压 Home 15s 再回。
6. **C8/C9**：滚动中收藏+复制。
7. **L5/L6**：断网或清空源后搜。
8. 导出 logcat：`ReactNativeJS` / `Choreographer` skipped frames。

**通过标准（建议）**

- 搜索进行中 top10 卡 **每 2s 名次变化 ≤ 3 次**（允许合并升级）。
- 滚动 60fps 主观可接受；Choreographer skip 不持续 &gt;10 帧尖峰。
- 无整表白闪；无自动滚回顶部。
- 无崩溃 / ANR。

---

## 4. 自动化

见 `magnetgoogo-app/scripts/fluency-extreme-tests.mjs`：

- 模拟 multi-source drip + debounce
- 度量：notify 次数、sync 次数、topK churn、id 稳定性、排序耗时
- exit code 非 0 = 有失败断言

运行：

```bash
cd magnetgoogo-app
node scripts/fluency-extreme-tests.mjs
```

---

## 5. 已知高风险代码点（供修 bug 对照）

1. `syncFromSession` 每次 newResults 都对 **整个** `_dedupMap` sort + map models。
2. `setResults` + `setSearching` + `setDoneCount` 同 tick 多次触发 render。
3. FlatList 缺 `extraData` 显式控制时，依赖 data 引用变化 → 过度更新。
4. `AnimatedCard` 用 **列表 index** 而非稳定 id 做动画资格。
5. 变高卡片无 `getItemLayout` / 无估计高度。

---

## 6. 输出物

| 文件 | 说明 |
|------|------|
| 本计划 | 用例与标准 |
| `scripts/fluency-extreme-tests.mjs` | 可重复极端逻辑测试 |
| `scripts/fluency-extreme-report.json` | 最近一次跑分 |

---

## 7. 本轮执行结果（2026-07-19 / 续 K30S 2026-07-24）

### 7.1 自动化逻辑层

```
node magnetgoogo-app/scripts/fluency-extreme-tests.mjs
→ 13/13 PASS
```

| 指标 | 结果 | 解读 |
|------|------|------|
| D1 debounce | notify 30 → sync ≤2 | 合批有效，仍约 2Hz 刷新上限 |
| D3 top20 churn | rate **0.141** | 中等 drip 下名次有抖动，未爆表 |
| S2 随机 seeders 重排 | risk **LOW**（固定 20 id） | 极端全表 seed 乱序时需真机确认 |
| PERF 500 卡全量 rebuild | avg **&lt;200ms**（逻辑层） | CPU 可接受；UI 线程另计 |
| J2/C4 id 稳定 | PASS | keyExtractor 不会因 merge 乱 remount |

### 7.2 设备层（K30S，App v0.1.14）

| 操作 | 结果 |
|------|------|
| monkey 120 事件 | 完成，无进程崩溃记录 |
| logcat Choreographer | 有少量 skipped frames 信号（噪声环境） |
| 深度链 `magnetgoogo://search?q=` | 需真机录屏做 J1/C2 主观验收 |

### 7.3 代码审阅结论（高风险 → 建议修）

即使逻辑测试 PASS，**真机「高频跳动」仍可能来自**：

1. **搜索进行中每 500ms `setResults` + 全量 re-sort** → FlatList data 引用变 → 可视区重绑
2. **无 `getItemLayout`** + 标题 1–3 行变高 → 滚动锚定漂移
3. **`AnimatedCard` 按 index** 决定是否动画 → 重排时 index&lt;8 的新卡可能再入场
4. **status 文案每 tick 变** → 顶部布局微抖
5. **骨架 ↔ 列表** 整组件切换闪一下

**建议修复方向 → 已在 7.4 落地**

### 7.4 代码修复已落地

| 修复 | 行为 |
|------|------|
| 搜索中冻结综合排序 | `_orderKeys` 首次出现顺序；合并只更新字段不重排 |
| 搜索结束 / 点停止 | session 统一执行一次 comprehensive 全量排序，渲染层不再二次排序 |
| 滚动中推迟 setResults | `isScrollingRef` + 松手后再刷列表，停止和自然完成均遵守延迟 |
| dirty 卡片更新 | 保持稳定 id/key，但生成新的 `ResultCardModel` 对象，确保 PureComponent 单元格刷新 |
| 派生字段一致性 | 标题升级后重新计算分类、主题、标签、相关度、体积、日期等字段 |
| 来源计数 | `sourceCount` 只统计唯一来源，同源重复行不触发刷新 |
| 无 hash 结果 | 使用稳定 fallback id 去重，避免 FlatList 重复 key |
| 共享累加器 | `searchResultAccumulator.ts` 同时供生产页面与自动化测试调用，消除测试实现漂移 |
| debounce | 搜索中 700ms / 结束后 400ms |
| AnimatedCard | 按 **stable id** 只入场一次，不用 index |
| statusRow | `minHeight: 36` 防挤列表 |

### 7.5 自动化回归（最终修复后）

```
node scripts/fluency-extreme-tests.mjs → 17/17 PASS
D3 top20 churn while searching: 0.000
D4b dirty card fresh object + derived fields: PASS
D2b unique source count + duplicate row ignored: PASS
PROD production/shared-accumulator contracts: PASS
```

补充门禁：

- `npx tsc --noEmit` → PASS
- `npx expo export --platform android` → 1397 modules bundled，HBC 生成成功
- `./gradlew assembleDebug -PreactNativeArchitectures=arm64-v8a` → BUILD SUCCESSFUL

### 7.6 K30S 实机状态（M2007J3SC）

MIUI 仍阻止直接覆盖安装最新 debug APK：

```
INSTALL_FAILED_USER_RESTRICTED: Install canceled by user
```

但设备已安装 Expo Go 54.0.8，与项目 Expo SDK 54 匹配。本轮改用以下方式加载当前工作区源码，而不是复用旧正式包：

```
adb reverse tcp:8081 tcp:8081
exp://127.0.0.1:8081/--/search?q=ubuntu
```

Expo Go 日志确认当前 Metro bundle 启动、125 个源加载并执行真实搜索。连续请求日志停止后，再执行最终列表 fling，结果如下：

| 场景 | 帧数 | Jank | P95 | P99 | 崩溃/ANR |
|---|---:|---:|---:|---:|---|
| 搜索中持续上下 fling | 2053 | 0.83% | 15ms | 34ms | 无 |
| 请求静默后的最终列表 fling | 355 | 0.56% | 18ms | 34ms | 无 |

结论：S1 前台搜索与滚动性能已基于当前源码通过；骨架到列表转换已实际运行且未出现 JS/native 崩溃。Expo Go 不包含项目自定义 `SearchKeepAlive` 原生模块，因此 L2 原生后台保活/Headless handoff 仍需在可安装的 development APK 上单独验证。

### 7.7 2026-07-25 对抗性回归补充

新增 `scripts/app-adversarial-tests.mjs`，覆盖连续换词竞态、存储损坏、源重复同步、远程配置结构、分类/标签、二进制大小、语言完整性和原生 keepalive token 契约，结果 21/21 PASS；原流畅度套件继续 17/17 PASS。

K30S 当前源码补测：

- 冷启动仅一次缓存加载和一次远程保存，重复源同步已关闭；
- `Inception` 搜索中切换为 `Ubuntu2204 LTS`，旧任务在 12 源快速阶段后结束，无旧结果回灌；
- 停止、连续排序和上下 fling：681 帧、现代 jank 0.59%、P95 14ms、P99 27ms，无 FATAL/ANR/React 错误。

完整用例与剩余风险见 `APP-ADVERSARIAL-TESTPLAN-2026-07-25.md`。
