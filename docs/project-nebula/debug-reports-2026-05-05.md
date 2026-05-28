# 搜索调试报告分析 — 2026-05-05

## 报告概览

| # | 场景 | 查询词 | 耗时 | 有结果源 | 空源 | 错误 | 磁力数 |
|---|------|--------|------|---------|------|------|--------|
| 1 | 有码番号 | `sdde88` | 73s | 16/92 | 76 | 0 | 134 |
| 2 | 中文电影(?) | (编码乱码) | 74s | 22/92 | 70 | 0 | 315 |
| 3 | 英文剧集 | `s04e02 alone together` | 74s | 25/92 | 67 | 0 | 202 |

> 注：第4条报告（无码番号）被 JSON 截断，数据不完整。

---

## 一、关键问题

### P0: items[] 全部为空 — 逐条详情未采集
所有报告的 `items: []` 都是空数组。说明最新的 itemLogs 采集代码还未在这些搜索中生效（可能需要 kill app 重启才能加载最新 Metro 包）。

### P0: 中文查询词 JSON 编码乱码
报告2的 query 显示为 `"  ñ    ð  "`，中文字符完全丢失。AsyncStorage/JSON.stringify 的编码链路有 bug。

### P1: TPB 镜像冗余严重 — 19个镜像返回完全相同数据
| 镜像 | 结果数 | hash 样本 |
|------|--------|-----------|
| thepiratebay.xyz | 6-20 | 2A32FF14A708, D019EC670130... |
| piratebay.party | 同上 | **完全相同** |
| thepiratebay.zone | 同上 | **完全相同** |
| pirateproxy.live | 同上 | **完全相同** |
| thepiratebay.rocks | 同上 | **完全相同** |
| pirateproxylive.org | 同上 | **完全相同** |
| thepiratebay.bond | 同上 | **完全相同** |
| ...等 12+ 个 | 同上 | **完全相同** |

**影响：** 浪费大量并发请求 + 搜索时间，且所有结果去重后只贡献 6 条唯一磁力。应该按品牌（brand）只取最快的 1-2 个镜像。

### P1: GFW 超时源 — 10 个源固定 10s 超时
以下源在中国大陆全部超时，浪费 10s×10 = 100s 并发资源：

| 源 | 耗时 | 原因 |
|----|------|------|
| BTDigg (btdig.com) | 10.0s | GFW |
| BitSearch (bitsearch.to) | 10.0s | GFW |
| 動漫花園 (share.dmhy.org) | 10.0s | GFW |
| 動漫花園 mirror | 10.0s | GFW |
| Mikanani | 10.0s | GFW |
| sukebei.nyaa.si | 10.0s | GFW |
| nyaa.si | 10.0-10.8s | GFW |
| tokyotosho ×2 | 10.0s | GFW |
| u3c3.com | 10.0-10.9s | GFW |
| piratebay.live | 10.0s | GFW |

### P1: JavBus 超时 63 秒
JavBus 在所有 3 次搜索中都耗时 **63 秒** 且返回 0 结果。custom handler 严重异常。

### P2: 0ms 跳过源 — requires_browser 在移动端无法执行
| 源 | durationMs | 原因 |
|----|-----------|------|
| BT4G | 0 | requires_browser + waf |
| 0cili.com | 0-1 | requires_browser |
| cld140.buzz | 0 | 原因不明（非browser） |
| 529072.xyz | 0-1 | 原因不明 |
| BTSearch | 0 | requires_browser |

---

## 二、场景分析

### 场景 1: `sdde88` — 有码番号

**有效数据源（16 个返回结果）：**

| 源 | 结果数 | 耗时 | 相关性 | 备注 |
|----|--------|------|--------|------|
| 种子吧 ×7 | 8条×7 | 3-6s | ⚠️中等 | 标题含 "happygjs88@SDDE-278/344/326"，是用户名含88 + SDDE系列 |
| 阿狸搜 | 7 | 2.7s | ✅高 | sdde-564, sdde-581, sdde-582 — 真正SDDE番号 |
| cilisousuo ×3 | 7×3 | 4-7s | ⚠️中等 | SDDE-326 等 |
| 0magnet.co | 8 | 5.1s | ⚠️中等 | 混合 |
| BTSOW | 15 | 0.4s | ⚠️低 | 含 LAF-88, SDDE-690 |
| TPB.baby | 20 | 3.1s | ❌无关 | "Little House on Prairie" — 完全无关 |
| clb12.xyz | 6 | 8s | ❌低 | 混杂 |
| 磁力狗 | 1 | 3.7s | ✅精确 | sdde-550 |

**问题：**
- 没有任何源返回 **SDDE-088** 精确结果（这个番号可能确实不存在或极稀有）
- TPB.baby 返回完全无关内容 → 搜索引擎逻辑有误
- **JavBus 完全失败**（理应是番号最佳源，63s 超时返回 0）
- CiliMo 返回 0（它 DHT 数据库应该有 SDDE 系列）

### 场景 3: `s04e02 alone together` — 英文剧集

**最佳结果来源：**

| 源 | 结果数 | 耗时 | 相关性 |
|----|--------|------|--------|
| TPB 系列 ×13 | 6×13 | 0.3-3s | ✅精确 "9-1-1 S04E02 Alone Together" |
| animetime.cc | 20 | 2.8s | ⚠️混杂（含其他 S04E02 剧集） |
| CiliMo | 20 | 1.4s | ⚠️泛泛（"Alone Together"泛匹配） |
| UIndex | 4 | 1.6s | ✅精确 |
| Knaben | 1 | 4.6s | ✅精确 |
| 磁力狗 | 2 | 2.5s | ✅精确 |

**特点：** 英文搜索效果最好，TPB 生态主导。但 13 个 TPB 镜像返回相同 6 条结果，严重冗余。

---

## 三、优化建议（按优先级）

### 立即可做

1. **品牌去重**：同品牌只取最快响应的 2 个镜像
   - TPB 19→2, 种子吧 7→2, cilisousuo 3→1
   - 预期减少 ~30 个并发请求，加速整体搜索

2. **GFW 黑名单**：对中国大陆用户自动禁用 10 个已知 GFW 封锁源
   - 可用 health_check 的 fail_streak 自动降级

3. **修复 JavBus handler**：63s 超时说明 AJAX 提取或 age-verify 流程卡死

4. **修复中文编码**：debug report JSON export 丢失中文字符

### 中期优化

5. **requires_browser 源标记**：移动端跳过这些源并在 UI 显示"仅桌面可用"
6. **搜索超时降低**：当前 10s 过长，对 GFW 源可降至 5s
7. **修复 items[] 采集**：确保 kill 重启 app 后 itemLogs 生效

---

## 四、源效能排名

### 性价比最高的源（快 + 有结果）
| 源 | 平均耗时 | 特点 |
|----|---------|------|
| BTSOW (so2.btsow.top) | 0.4-0.9s | 最快，中文+日文 |
| pirateproxylive.org | 0.3-0.6s | TPB 最快镜像 |
| CiliMo | 1.4s | DHT 大库，中英文 |
| UIndex | 1.6s | 精确，国际 |
| 阿狸搜 | 1.5-2.7s | 中文磁力，番号好 |
| animetime.cc | 2.5-2.8s | ACG 广覆盖 |

### 需要修复的源
| 源 | 问题 |
|----|------|
| JavBus | 63s 超时，0 结果 |
| TPB.baby | 返回无关结果（sdde88查出 Prairie） |
| cld140.buzz | 0ms 直接跳过 |
