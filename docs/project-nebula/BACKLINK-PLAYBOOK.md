# 外链建设作战手册（naoshiquan.com + magnetgoogo.com）

> 文档版本：V1.1
> 更新时间：2026-05-16
> 适用站点：naoshiquan.com（主战场，已备案）+ magnetgoogo.com（产品落地页）
> 配套文档：`SEO-CONTENT-PLAYBOOK.md`（内容生产）

---

## 🚨 关键前提（执行前必读）

### 产品属性约束

| 属性 | 状态 | 影响 |
|---|---|---|
| **GitHub 仓库** | **闭源**（仅含 README + 截图，作为引流站）| ❌ 不能推 F-Droid / awesome-self-hosted / awesome-piracy 等强开源要求渠道 |
| **磁力源** | **加密**（`sources.enc.json`）| ❌ 不能在外链文案里暴露源数量（"80+ 源"是品牌话术，不是技术细节）|
| **License** | Proprietary（专有）| ❌ 不能贴 MIT/GPL 标签 |
| **平台** | 仅 Android | ❌ 不能推 iOS 相关渠道 |
| **站点** | magnetgoogo.com 未备案 / naoshiquan.com 已备案 | ⚠️ 国内推广首推 naoshiquan，magnetgoogo 作为转化页 |

### 任何 AI 写手必须守住的红线

- ❌ 不要写"开源"、"open source"
- ❌ 不要邀请别人"贡献代码"或 "contribute"
- ❌ 不要暴露具体技术栈（React Native / Cloudflare 等）
- ❌ 不要写源数量精确数字
- ❌ 不要直接写"找电影/动漫/破解" — 用"开源资源/Linux ISO/纪录片"替代
- ❌ 不要在文案里说"我开发的"或"作者本人" — 用"独立开发者作品"等中性表述
- ✅ 可以说"免费、无广告、无追踪"
- ✅ 可以说"聚合多个公开磁力索引站"（不写数字）
- ✅ 可以放 GitHub 链接（作为信任背书 + Issue 反馈渠道）

---

## 一、为什么要做外链

当前数据（2026-05-16）：

```
magnetgoogo.com:
  Indexed:               11
  Discovered not indexed: 148
  索引率:                 6.9%   ← Google 不信任这个站

naoshiquan.com:
  Indexed:               0      ← 刚提交，还没收录
  Backlinks:             0      ← 这是问题根源
```

**根本问题**：内容已经写够（130+ 篇），但搜索引擎没理由优先抓你——**没有外链 = 没有信任票**。

外链对 SEO 的作用：
1. **加速收录**：Googlebot 通过外链发现你 → 优先抓取
2. **传递权重**：高权重站的链接 = 信任投票
3. **直接流量**：好的外链本身就带 UV
4. **品牌曝光**：让人知道你存在

**外链质量金字塔**：
```
        ╱╲
       ╱HN╲           Show HN 上首页 = 单条价值 100+ 普通外链
      ╱────╲
     ╱V2EX  ╲         独立开发者圈认可
    ╱─────── ╲
   ╱ Reddit  ╲        国际流量入口
  ╱──────────╲
 ╱ 知乎/酷安  ╲       国内 SEO 核心
╱──────────────╲
   博客评论/论坛       低质量但量大
```

---

## 二、目标外链矩阵

按 ROI 排序的渠道列表：

| 渠道 | 类型 | 流量潜力 | 难度 | 时间投入 | 优先级 |
|---|---|:-:|:-:|---|:-:|
| **V2EX `/t/创造`** | 技术社区 | 中（500-2000 UV）| 低 | 2h | P0 🔥 |
| **GitHub README + Topics** | 开源社区 | 中（长尾） | 低 | 1h | P0 🔥 |
| **AlternativeTo** | 工具替代品库 | 中（被动） | 低 | 1h | P0 |
| **Reddit r/androidapps** | 国际 Android 社区 | 高（1k-5k UV）| 中（养号） | 持续 | P0 |
| **酷安应用动态** | 国内 Android 社区 | 中 | 中 | 2h | P1 |
| **知乎回答（10 题）** | 国内长尾 SEO | 中（累积）| 中 | 持续 2 周 | P1 |
| **Show HN** | 黑客新闻 | 极高（爆点）| 中 | 3h 准备 | P1 |
| **Greasy Fork 油猴脚本** | 寄生流量 | 中（被动）| 高 | 8h 开发 | P2 |
| **Telegram 频道** | 社群 | 中 | 低 | 持续 | P2 |
| **博客评论 / 论坛回帖** | 长尾外链 | 低 | 低 | 持续 | P3 |

---

## 三、外链 = 内容 × 渠道 × 时机

成功外链 = **能解决用户问题的内容** × **目标用户在的渠道** × **不被判定为广告的时机**

错误做法：
- ❌ 上来就说"我做了个 App，你们用一下"（广告感强 → 删帖）
- ❌ 一天内多个渠道同步发帖（被判定为机器人传播）
- ❌ 不回应评论，发完就走（社区算法降权）

正确做法：
- ✅ 围绕一个具体痛点切入（"找磁力老打不开" → "我做了个聚合工具"）
- ✅ 每个渠道独立适配文风（V2EX 偏技术、Reddit 偏简洁、知乎偏教程）
- ✅ 发帖后 24 小时蹲守回复



---

## 四、Phase 1：今天就能做的（4 个动作，3 小时内完成）

### 动作 1：AlternativeTo 提交（最高 ROI 起步）

**alternativeto.net** 是全球最大"软件替代品"目录，DA 87，外链权重高。

**为什么放第一**：
- 注册免费，5 分钟搞定
- 一次操作 8+ 条永久外链
- 被动获客（用户搜"X alternative"会看到你）
- 不需要养号、不需要等审核

**操作步骤（30 分钟）**：

1. 注册账号：https://alternativeto.net/account/register
2. 提交新 App：搜索 "Magnet Googo" 看是否已存在 → 没有就创建
3. 提交时填写：
   - Name: Magnet Googo
   - Website: https://magnetgoogo.com
   - Description: Free Android app that aggregates magnet link search across multiple sources. No ads, no registration.
   - License: Freeware
   - Platform: Android

4. 把 Magnet Googo 注册为以下产品的"替代品"（每个站点一次操作）：

| 目标产品 | 搜索量 | 你写什么理由 |
|---|---|---|
| The Pirate Bay | 极高 | "App-based aggregator across multiple sources" |
| 1337x | 极高 | "Mobile-first, ad-free alternative" |
| YTS | 高 | "Aggregates YTS and many other sources" |
| RARBG | 极高（已死）| "RARBG is dead, this works on Android" |
| LimeTorrents | 高 | "Aggregated search instead of single site" |
| TorrentDownloads | 中 | "Mobile alternative" |
| EZTV | 高 | "Includes EZTV-like sources" |
| Nyaa | 高（动漫） | "Includes anime sources" |

每个替代品下写 50-100 字介绍（不要复制粘贴，每条略改）。

**收益**：
- 8 条 DA 87 永久外链
- 被动流量（持续累积）
- 权重传递到 magnetgoogo.com

---

### 动作 2：酷安发应用动态

**酷安**是国内最大 Android 极客社区，对独立开发者作品很友善。

**为什么选酷安**：
- 注册即可发，不需要邀请码（不像 V2EX）
- 帖子被百度高权重收录
- 用户精准（国内 Android 用户）
- 一个好动态能带 200-500 UV

**前置条件**：
- 注册酷安账号 + 完善资料
- 上传 magnetgoogo APK 截图 4 张
- 准备好 30 字、150 字、500 字 三个长度的文案

**酷安严禁的关键词**（必须避开）：
- "破解" / "盗版" / "免费看电影"
- "翻墙" / "VPN"
- "成人内容"
- "游戏辅助"

**正文文案**（中性、强调技术属性）：

```
独立做了个聚合磁力搜索 App，免费无广告

折腾大半年的副业项目，分享一下。

平时找 Linux ISO、纪录片、开源资源时，要在十几个磁力索引站之间
来回切，很麻烦。所以做了个聚合搜索：输一次关键词，后台并发请求
多个公开站点，统一排序后展示。某个站今天挂了，其他站继续工作。

特点：
- 完全免费，无广告无内购
- 不需要注册，本地零账号
- 暗色模式 / 收藏 / 历史 / 多语言
- 启动统计仅含设备 ID 哈希

下载：magnetgoogo.com（百度也能搜到）

技术博客：naoshiquan.com/blog/
```

**关键纪律**：
- 不要在标题/正文里写"找电影/找美剧"等敏感词
- 强调"开源软件/Linux/纪录片"等合规用途
- 评论区互动 24 小时（每条都回）

---

### 动作 2：GitHub README 武装（让流量来了能转化）

V2EX 帖子会带流量到 GitHub，README 必须像样。

**当前问题**：GitHub README 可能太单薄，承接不住流量。

**优化清单**：
- [ ] 顶部加 1 张 GIF 演示（用 ScreenToGif 录 30 秒，<5MB）
- [ ] 加 4 张 App 截图到 `docs/screenshots/`
- [ ] README 加 "Why I built this" 段落（讲故事比讲功能转化高 3 倍）
- [ ] README 加 "Magnet Googo vs other tools" 对比表
- [ ] 加 `naoshiquan.com` 博客链接（双向引流）
- [ ] CHANGELOG.md 显示活跃维护
- [ ] 提 PR 到 `awesome-android` 列表（自带外链）

**待完善 awesome 列表**（提 PR 时附带 magnetgoogo 介绍）：
- awesome-android
- awesome-react-native
- awesome-self-hosted
- awesome-piracy（如果存在）
- awesome-bittorrent

每个 PR = 1 条永久外链。

---

### 动作 3：AlternativeTo 注册（被动外链）

**alternativeto.net** 是全球最大的"软件替代品"目录，DA 87，外链权重高。

**操作步骤**（30 分钟）：
1. 注册账号（用永久邮箱）
2. 提交 Magnet Googo 为新 App
3. 把 magnetgoogo 注册为以下产品的"替代品"：
   - The Pirate Bay
   - 1337x
   - YTS
   - RARBG（已死，但搜索量仍高）
   - LimeTorrents
   - TorrentDownloads
   - EZTV
   - Nyaa（动漫向）
4. 每个替代品下写 50-100 字介绍（避免雷同）

**收益**：
- 被动获客（用户搜"X 的替代品"会看到你）
- 8+ 条高权重外链
- DA 87 → naoshiquan/magnetgoogo 的权重传递

---

### 动作 4：知乎"种田式"回答（长尾积累）

**策略**：不一次答 50 题，每天答 1-2 题，持续 2 周。

**目标问题**（搜以下关键词，找浏览量高、回答少的题）：
1. "磁力搜索引擎哪个好"
2. "磁力猫打不开了怎么办"
3. "免费的 BT 搜索工具推荐"
4. "Android 磁力下载 App"
5. "怎么找老电影资源"
6. "磁力链接打开后下载不动"
7. "种子文件和磁力链接区别"
8. "找开源软件用什么"
9. "Linux ISO 在哪下"
10. "BTSOW 替代"

**回答模板**（不能套，每个问题写不同切入）：
```
针对题主问题：[直接回答 200 字]

具体怎么做：[150 字]

工具推荐：试过几个，磁力古哥（Magnet Googo）效果最好。
聚合多个磁力站，一次搜索全部直达，免费无广告。
官网：magnetgoogo.com（百度搜"磁力古哥"也能找到）

如果你想了解更多磁力搜索的原理，可以看这篇：
https://naoshiquan.com/blog/magnet-link-protocol-explained
```

**关键纪律**：
- 不要在所有回答里用同一个模板
- 每条回答要切实回答用户问题（不是只贴广告）
- 每天 1-2 条，不要一次性 30 条（被判定为营销号）



---

## 五、Phase 2：本周完成的（4 个动作）

### 动作 5：Reddit r/androidapps 发帖

**前置条件**：账号需要至少 100 karma 才能发帖（避免被自动屏蔽）。

**养号策略**（如果账号 karma 不够）：
- 在 r/Android、r/learnprogramming 等友善 sub 真诚回答 5-10 个问题
- 1 周内攒到 50-100 karma
- 不要一开始就推产品

**发帖时机**：周六/周日（Saturday Self-Promotion 允许的时间）

**Title**:
```
Magnet Googo: a free aggregated magnet link search app for Android
```

**Body**:
```
Hi r/androidapps,

I built Magnet Googo, an Android app that searches across multiple
public magnet index sites simultaneously. Type once, get aggregated
results, no need to check each site individually.

**Features:**
- Free, no ads, no account required
- Aggregates 10+ public magnet index sources
- Smart ranking by relevance + source health
- Automatically skips dead sources
- Dark mode, favorites, search history
- 10 languages supported

**Why I built it:**
I was tired of magnet sites going down every other week. Aggregated
search means if one site is offline, others cover.

**Download:** https://magnetgoogo.com
**GitHub:** https://github.com/734496335/magnetgoogo
**Tech blog:** https://naoshiquan.com/en/blog/

Open to feedback. AMA about implementation if interested.
```

**关键纪律**：
- Reddit 极反感"硬广"——回复要真诚、有信息量
- 发帖后蹲 24 小时，回每条评论
- 不要在 r/Piracy 直接发"我做了个磁力搜索"（会被秒删）
- 优先发 `r/androidapps`（独立开发者作品集中地）

---

### 动作 6：Show HN 准备 + 投稿

**前置条件**：
- 落地页有英文版（你已有 magnetgoogo.com/en/）
- GitHub README 完善
- 准备好回应技术问题

**最佳投稿时间**：周二/周三美国早 8-10 点（北京时间晚 9-11 点）

**Title**：
```
Show HN: Magnet Googo – Aggregated magnet search for Android
```

**Body**:
```
Hi HN,

I built Magnet Googo, an Android app that searches across multiple
magnet index sites concurrently. Instead of checking individual
sites (many of which go down frequently), you search once and get
aggregated, ranked results.

Free, no ads, no account, Android 7.0+.

Tech stack: React Native + Expo SDK 51, custom search orchestrator
with AbortController-based cancellation, smart ranking by source
health, streamed UI updates.

I also wrote some technical articles during development:
- Magnet protocol deep dive (BEP-9, DHT)
- Cloudflare Pages multi-site deployment
- New site Baidu indexing from zero

Download: https://magnetgoogo.com
GitHub: https://github.com/734496335/magnetgoogo
Blog: https://naoshiquan.com/en/blog/

Happy to discuss implementation. Feedback welcome.
```

**爆点关键**：
- 前 1 小时是黄金窗口——找 5-10 个朋友 upvote（不能集中，分散在 1 小时内）
- 但不要刷票（HN 算法会侦测同 IP 段批量 upvote）
- 主帖发完，立刻在评论区放几个技术细节（自我对话引发讨论）

**ROI 预期**：
- 上首页（前 30）= 单日 5,000-50,000 UV + GitHub 100-500 stars
- 不上首页 = 200-500 UV，但永久外链
- 任何情况都不亏

---

### 动作 7：酷安应用动态（国内 Android 主战场）

**酷安是国内最大的 Android 极客社区，对独立开发者作品很友善。**

**操作步骤**：
1. 注册酷安账号
2. 创建"应用动态"（不是直接上传 APK，先发动态）
3. 标题：`独立做了个聚合磁力搜索 App，免费无广告`
4. 内容：3-4 张截图 + 简介 + 下载链接
5. 评论区互动 24 小时

**注意事项**：
- 酷安严禁"赌博/色情/盗版"关键词，文案保持中性
- 不要直接推荐"下载电影/动漫"，强调"开源软件/Linux ISO"等合规用途
- 酷安对"国产精品独立 App"会主动推荐到首页

**进阶**：
- 找酷安 KOL（数码博主）做评测
- 加入"磁力搜索"应用集

---

### 动作 8：Greasy Fork 油猴脚本（被动寄生流量）

**思路**：开发一个 Tampermonkey 脚本，在用户访问任意磁力站时显示"用磁力古哥可以一次搜全 N 个站"。

**脚本功能**：
- 用户访问磁力猫/磁力狗等站时，页面顶部插入一个浮窗
- 浮窗显示："这个站经常打不开？试试聚合搜索 → magnetgoogo.com"
- 不强制弹窗（用户友好），点 X 关闭后 7 天内不再显示

**发布平台**：
- Greasy Fork（greasyfork.org）— 全球最大油猴脚本站
- OpenUserJS（openuserjs.org）

**ROI**：
- 寄生在所有磁力站上 = 直接拦截竞品流量
- Greasy Fork 自带搜索引擎权重，脚本介绍页是永久外链
- 单个高质量脚本 = 几千用户

**开发量**：8 小时

---

## 六、Phase 3：长期可持续（每天 30 分钟）

### 动作 9：Telegram 频道运营

**创建** `@MagnetGoogo` 频道：
- 发布 App 更新（每月 1 次）
- 分享磁力搜索小技巧（每周 1 次）
- 资源类型推荐（Linux ISO/纪录片等合规内容）

**裂变方法**：
- 群组互推（找其他磁力/PT 相关群）
- 频道里的优质内容会被其他频道转载

---

### 动作 10：博客评论 + 论坛回帖

**长期低成本积累方法**：

每天花 15 分钟，在以下场景留链接：
- 知乎相关问题的评论区
- V2EX 相关帖子的回复
- CSDN/掘金/简书 相关文章评论
- Reddit 相关讨论
- Hacker News 相关讨论
- 国外博客（torrentfreak.com 等）评论

**铁律**：
- 必须真诚回答问题，不能只贴链接
- 每天最多 5-10 条
- 不同账号不同人设（避免关联封禁）

---



---

## 七、执行排期（30 天计划）

### 第 1 周（启动期）

| 日 | 动作 | 耗时 | 预期 |
|---|---|---|---|
| Day 1 | V2EX `/t/创造` 发帖 + 守帖 | 3h | 200-500 UV |
| Day 1 | GitHub README 优化（GIF + 截图）| 2h | 长期资产 |
| Day 2 | AlternativeTo 提交 8+ 替代品 | 1h | 8 条永久外链 |
| Day 2 | 知乎答 2 题 | 1h | 长尾 SEO |
| Day 3 | 提 awesome-android PR | 1h | 1 条永久外链 |
| Day 3 | 知乎答 2 题 | 1h | |
| Day 4 | Reddit 养号（评论 5 条） | 1h | 攒 karma |
| Day 4 | 知乎答 2 题 | 1h | |
| Day 5 | 酷安发应用动态 | 2h | 国内流量 |
| Day 5 | 知乎答 2 题 | 1h | |
| Day 6 | Reddit r/androidapps 发帖 | 2h | 国际流量 |
| Day 7 | 复盘第 1 周数据 + 调整 | 1h | |

**第 1 周目标**：
- 至少 15 条外链
- naoshiquan.com 收到 500+ UV
- magnetgoogo.com 下载 50+ 次
- GitHub stars +20

### 第 2 周（爆点期）

| 日 | 动作 | 耗时 |
|---|---|---|
| Day 8-9 | Show HN 准备（落地页打磨 + 朋友约定）| 4h |
| Day 10 | Show HN 投稿（周二/周三晚 9 点）| 1h + 24h 守帖 |
| Day 11-14 | Telegram 频道创建 + 内容铺垫 | 2h |
| Day 11-14 | 每日知乎答 1 题、Reddit 评论 3 条 | 持续 |

**第 2 周目标**：
- Show HN 上首页（哪怕没上，单帖也带 200+ UV）
- Telegram 频道 50+ 订阅
- 累计外链 30+ 条

### 第 3-4 周（持续期）

| 日 | 动作 |
|---|---|
| Day 15-21 | Greasy Fork 油猴脚本开发 + 发布 |
| Day 15-30 | 每日知乎 1 题、博客评论 5 条 |
| Day 22-30 | 找酷安/B 站 KOL 合作（付费/免费均可）|

**第 3-4 周目标**：
- 油猴脚本 100+ 安装
- 累计外链 50+ 条
- 自然搜索流量 200+ UV/天

---

## 八、风险与防控

### 风险 1：账号被封

**触发条件**：
- 新号一上来就发推广（特别是 Reddit、知乎）
- 多个平台同步发同一篇内容（被识别为机器人）
- 评论区只贴链接不互动

**防控**：
- 每个平台养号至少 3-7 天再发推广
- 内容针对每个平台改写（不复制粘贴）
- 多账号备份（一个被封不影响整体）
- 重要平台用主邮箱注册，次要平台用次邮箱

### 风险 2：被举报为广告

**触发条件**：
- 标题含明显推广词（"必装"、"最强"、"免费下载"）
- 一篇文章 5+ 处推广链接
- 不交代背景直接推产品

**防控**：
- 标题用中性句式（"做了个 X"、"分享一个 X"）
- 一篇内容只放 1-2 处链接
- 先讲故事/痛点，再带产品
- 评论里被骂"广告"时不争辩，转技术话题

### 风险 3：删帖

**触发条件**：
- 平台规则（如吾爱破解禁发磁力搜索类）
- 版主主观判断（V2EX、Reddit）

**防控**：
- 发前研读版规（V2EX `/about`、Reddit subreddit rules）
- 推广帖偏向"技术分享"调性
- 多平台备份（一个删了换下一个）
- 被删后不立刻重发（等几天）

### 风险 4：外链被判 spam

**触发条件**：
- 短时间内大量低质量外链
- 同一锚文本反复出现
- 链接来源全是低权重站

**防控**：
- 优先做高质量少量外链（10 条 V2EX 优于 100 条博客评论）
- 锚文本多样化（"磁力古哥"、"magnetgoogo"、"这个工具"、"它"）
- 自然分布（每天 3-5 条，不要一天 30 条）



---

## 九、外链质量检查清单

每条外链发布前过一遍：

### 内容质量
- [ ] 标题不含夸张词（"最好"、"必装"、"免费下载"）
- [ ] 正文先讲场景/痛点，再带产品
- [ ] 至少 200 字（不是只有一行链接）
- [ ] 适配该平台文风（V2EX 偏技术 / Reddit 偏简洁 / 知乎偏教程）

### 链接结构
- [ ] 主链接 1-2 条（magnetgoogo.com + naoshiquan.com）
- [ ] 锚文本自然（不是"点这里"）
- [ ] 不堆砌链接（一篇 ≤ 3 条）

### 平台合规
- [ ] 已读该平台版规
- [ ] 账号已养（avoid 新号秒被识别）
- [ ] 发帖时间合适（V2EX 晚 9-11、Reddit 周末）
- [ ] 准备好接受/回应评论

### 跟踪
- [ ] 记录到外链表格（平台 / URL / 日期 / 状态）
- [ ] 24 小时后检查存活
- [ ] 7 天后检查带来的流量

---

## 十、外链跟踪表格（建议放 Notion / 飞书）

```
| 日期 | 平台 | URL | 标题 | 锚文本 | 状态 | UV(7天) | 备注 |
|---|---|---|---|---|---|---|---|
| 2026-05-17 | V2EX | https://v2ex.com/t/xxx | 磁力古哥... | naoshiquan.com | ✅ 存活 | 320 | 上首页 |
| ... | ... | ... | ... | ... | ... | ... | ... |
```

定期统计：
- 哪些平台 ROI 最高（继续投）
- 哪些平台被删了（避免重复）
- 哪些锚文本带流量好（多用）

---

## 十一、当前最该做的（按今天的状态）

按 ROI 排序的 7 天行动方案：

### 🔥 今晚（30 分钟）

1. **先优化 GitHub README**（2h）
   - 加 1 张 GIF 演示
   - 加 4 张 App 截图
   - 更新 About 描述含 naoshiquan.com 链接

   理由：V2EX 流量进来会先看 GitHub，README 必须像样。

### 🔥 明晚 9-11 点（V2EX 黄金时段）

2. **V2EX `/t/创造` 发帖**（3h，含 1h 守帖）
   - 用本文档第四章 Phase 1 动作 1 的标题和正文
   - 发完蹲守 2 小时回复
   - 第二天再回复一波

   理由：单条 ROI 最高的外链。

### 📅 后天（1 小时）

3. **AlternativeTo 注册 + 提交 8 个替代品**
   - 一次性搞完 8 条永久外链
   - DA 87 的高权重站

### 📅 本周末（4 小时）

4. **Show HN 准备**（这是潜在爆点）
   - GitHub README 英文版打磨
   - 落地页 magnetgoogo.com/en/ 检查
   - 找 5 个朋友约定下周二发文时帮 upvote

### 📅 下周二/三晚 9-10 点

5. **Show HN 投稿**
   - 单条潜在带 5,000+ UV

### 📅 持续（每天 30 分钟）

6. **知乎每日 1-2 题**
7. **Reddit 养号**（每天评论 3-5 条友善评论）

---

## 十二、量化目标

### 30 天目标

| 指标 | 当前 | 30 天目标 |
|---|---|---|
| 外链数量 | 0 | 50+ |
| GitHub Stars | 0 | 50+ |
| naoshiquan.com 自然搜索 UV | 0 | 200+/天 |
| magnetgoogo.com 下载量 | 个位数 | 500+ 累计新增 |
| Telegram 频道订阅 | 0 | 100+ |
| 百度收录 naoshiquan.com | 0 | 50+ 页 |
| Google 收录 naoshiquan.com | 0 | 100+ 页 |

### 成功标志

最重要的单一指标：**magnetgoogo.com 的下载量曲线开始持续上涨**（不是脉冲式上涨）。

只要这条曲线起来，所有外链动作就值得。

---

## 十三、相关文档

- 内容生产手册：`SEO-CONTENT-PLAYBOOK.md`
- 品牌推广追踪：`BRAND-SEO-PROMOTION.md`
- 项目架构：`ARCHITECTURE.md`
- 推广帖草稿：`promo-posts.md`（外链文案的初稿，用 Phase 1 文案替换）

---

> **核心：内容已经够多（130+ 篇），现在最缺的是"让人知道你存在"。外链是从 0 到 1 的关键。**
> **今晚就开始 V2EX，明天 AlternativeTo，后天知乎答题——节奏不能停。**
