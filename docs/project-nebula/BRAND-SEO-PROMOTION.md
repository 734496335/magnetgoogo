# 磁力古哥 品牌运营推广 & SEO 清单

文档版本：V2.0
更新时间：2026-05-12

> 本文档跟踪所有品牌曝光、搜索引擎优化、渠道推广的执行状态。
> 状态标记：✅ 已完成 | 🔄 进行中 | 🔲 待做

---

## 1. 搜索引擎收录

### 1.1 落地页技术 SEO（magnetgoogo.com）

| 项目 | 状态 | 说明 |
|------|------|------|
| `robots.txt` | ✅ | 允许全站爬取，指向 sitemap |
| `sitemap.xml` | ✅ | 154 URLs（6 核心页 + 148 品牌截流页），CF Pages `_headers` 修复 Content-Type |
| `<title>` 关键词优化 | ✅ | 磁力古哥 Magnet Googo — 聚合全网磁力搜索引擎 |
| `<meta description>` | ✅ | 含"磁力搜索/免费/无广告/Android"等核心词 |
| `<meta keywords>` | ✅ | 12 个中英文关键词 |
| `<link canonical>` | ✅ | `https://magnetgoogo.com/` |
| Open Graph 全套 | ✅ | og:title/description/image/url/locale，绝对路径 |
| Twitter Card | ✅ | summary_large_image |
| JSON-LD 结构化数据 | ✅ | SoftwareApplication schema，含价格/截图/功能列表 |
| `<meta robots>` | ✅ | index, follow |
| apple-touch-icon | ✅ | app-icon-lg.png |
| theme-color | ✅ | #4285F4 |
| 版权年份 | ✅ | 2024 → 2026 |
| hreflang 中英双语 | ✅ | zh / en / x-default 三标签已添加 |
| 多页面扩展 | ✅ | faq/privacy/terms/about/contact 5 个独立页 |
| 程序化 SEO 页面矩阵 | ✅ | 49 品牌 × 3 变体 = 147 截流着陆页 + 1 索引页，`/alt/` 目录 |
| PWA manifest | 🔲 | 让搜索引擎识别为 Web App |
| 百度适配 meta | ✅ | `codeva-le9FKQPkUa` 已添加 |

### 1.2 搜索引擎提交

| 平台 | 面向 | 状态 | 操作入口 |
|------|------|------|----------|
| **Google Search Console** | 国际 | ✅ | Cloudflare DNS 自动验证，sitemap 已提交 Success |
| **Bing Webmaster Tools** | 国际 | 🔄 | sitemap 已提交（旧 6 URLs），已重新提交 154 URLs + 手动 Request Indexing 多个页面 |
| **百度站长平台** | 国内 | ✅ | 文件验证通过，API token=p5bdB9NbHwP05Syl |
| **搜狗站长** | 国内 | ✅ | HTML 标签验证通过，已手动提交 20 URLs（2026-05-11） |
| **神马/夸克站长** | 国内移动 | ✅ | HTML 标签验证通过，sitemap 已提交（2026-05-11） |
| **360 站长** | 国内 | 🔄 | 站点已添加，待验证（需 ICP 备案才能完整使用） |
| **IndexNow** | Bing/Yandex | ✅ | key=a1b2c3d4e5f6g7h8，首次 ping 已发送(200) |
| **Yandex Webmaster** | 俄/东欧 | 🔲 | https://webmaster.yandex.com |
| **头条搜索站长** | 国内 | 🔲 | https://zhanzhang.toutiao.com |

---

## 2. GitHub 仓库 SEO

| 项目 | 状态 | 说明 |
|------|------|------|
| About 描述（中英文关键词） | ✅ | 磁力古哥 + Free aggregated magnet & torrent search |
| Website 链接 | ✅ | magnetgoogo.com |
| Topics 标签（12 个） | ✅ | android, search-engine, torrent, bittorrent, aggregator, apk, magnet-link, android-app, magnet, torrent-search, free-app, magnet-search |
| Social Preview 图 | ✅ | 1280×640 已上传 |
| README.md SEO 增强 | ✅ | What-is 段、对比表、下载量 badge、关键词 alt |
| README_CN.md SEO 增强 | ✅ | 同上中文版 |
| Release Notes 关键词 | 🔲 | 每次发版写完整描述含关键词 |
| GitHub Pages | 🔲 | 可考虑启用作为备用入口 |

---

## 3. 应用分发平台

| 平台 | 面向 | 状态 | 优先级 | 说明 |
|------|------|------|--------|------|
| **GitHub Releases** | 国际 | ✅ | P0 | 已有 v0.1.8 |
| **蓝奏云** | 国内 | ✅ | P0 | 备用下载渠道 |
| **酷安** | 国内 | 🔲 | P0 | 国内最大 Android 社区，发帖+上传 APK |
| **AlternativeTo** | 国际 | 🔲 | P1 | 注册为磁力搜索替代品 |
| **APKPure** | 国际 | ✅ | P1 | v0.1.8 已提交，审核中（2026-05-04） |
| **APKMirror** | 国际 | ✅ | P2 | v0.1.8 已提交，审核中（2026-05-04） |
| **F-Droid / IzzyOnDroid** | 国际 | 🔲 | P2 | 需开源才可提交 |
| **Uptodown** | 国际 | ✅ | P2 | v0.1.8 已提交，审核中（2026-05-04） |

---

## 4. 社区推广 & 外链

### 4.1 国内

| 平台 | 状态 | 优先级 | 策略 |
|------|------|--------|------|
| **V2EX** | 🔲 | P0 | /t/创造 或 /t/Android 节点发帖，标题含"磁力搜索聚合" |
| **吾爱破解** | 🔲 | P0 | [原创工具] 板块发帖，附截图+下载链接 |
| **酷安** | 🔲 | P0 | 应用动态 + 应用集推荐 |
| **知乎** | 🔲 | P1 | 回答"磁力搜索推荐"/"BT搜索工具"相关问题 |
| **少数派** | 🔲 | P1 | 写详细测评文章 |
| **贴吧** | 🔲 | P2 | 磁力吧、BT吧、Android吧发帖 |
| **B 站** | 🔲 | P2 | 录制 App 演示视频 |

### 4.2 国际

| 平台 | 状态 | 优先级 | 策略 |
|------|------|--------|------|
| **Reddit** | 🔲 | P0 | r/androidapps, r/Android, r/torrents, r/Piracy |
| **Telegram** | 🔲 | P0 | 创建 @MagnetGoogo 频道，发布更新+讨论 |
| **Product Hunt** | 🔲 | P1 | 注册产品页，争取 upvote |
| **Hacker News** | 🔲 | P1 | Show HN 帖 |
| **Twitter/X** | 🔲 | P2 | 创建官方账号 |
| **GitHub Awesome 列表** | 🔲 | P2 | 提 PR 到 awesome-android, awesome-torrent 等 |

---

## 5. 部署信息

| 项目 | 值 |
|------|------|
| 落地页托管 | Cloudflare Pages（direct upload） |
| 项目名 | `magnetgoogo-site` |
| 绑定域名 | `magnetgoogo.com`, `naoshiquan.com`, `magnetgoogo-site.pages.dev` |
| 部署命令 | `npx wrangler pages deploy . --project-name=magnetgoogo-site --branch=main` |
| 部署目录 | `D:\lpproduct\magnet\magnetgoogo-site` |
| GitHub 仓库 | `734496335/magnetgoogo` |
| Google Search Console | ✅ 已验证（Cloudflare DNS） |

---

## 6. 效果追踪

| 指标 | 工具 | 当前值 | 目标 |
|------|------|--------|------|
| Google 索引页数 | GSC | 1 | 154+ |
| Google 搜索展示 | GSC | 0 | 1000+/周 |
| Bing 索引页数 | Bing Webmaster | 0 | 50+ |
| 百度收录 | 百度站长 | - | 50+ |
| 搜狗收录 | 搜狗站长 | 0 | 30+ |
| 神马收录 | 神马站长 | 0 | 30+ |
| GitHub Stars | GitHub | 0 | 50+ |
| GitHub 流量 | Insights → Traffic | 0 | 10+ unique/天 |
| 落地页 UV | CF Analytics | - | 50+/天 |
| APK 下载量 | GitHub Releases | - | 500+ |

---

## 7. 核弹级增长计划

### 7.1 现状诊断

产品已经 90 分（120 green 源、完整 App、分析管线），推广还是 0 分——零流量、零下载、零社区存在。

### 7.2 三维饱和打击框架

#### 维度一：截流（寄生式增长）

| 策略 | 状态 | 说明 |
|------|------|------|
| 程序化 SEO 页面矩阵 | ✅ | 49 品牌 × 3 变体 = 148 着陆页已部署（"磁力猫打不开" → 推荐磁力古哥） |
| 通用磁力关键词 SEO | 🔄 | "磁力搜索"、"磁力链接怎么用" 等长尾词着陆页 |
| 竞品宕机实时截流 | 🔲 | health_check 检测品牌宕机 → 30 分钟内知乎/贴吧/V2EX 发截流帖 |
| 知乎屠榜 | 🔲 | 50-100 个相关问题全部回答，长尾 SEO 霸屏 |
| 论坛饱和轰炸 | 🔲 | 吾爱破解 + 酷安 + V2EX + 贴吧 + Reddit + Telegram |

#### 维度二：造势（内容核弹）

| 策略 | 状态 | 说明 |
|------|------|------|
| SEO 博客内容矩阵 | 🔲 | "2026 最好磁力搜索"、"磁力猫 vs 磁力古哥" 等 10+ 篇 |
| 视频矩阵 | 🔲 | B 站演示 + 抖音短视频 + YouTube 英文版 |
| GitHub 造势 | 🔲 | Star 互刷 + Awesome 列表 PR + Trending 冲榜 |

#### 维度三：裂变（让用户替你推广）

| 策略 | 状态 | 说明 |
|------|------|------|
| 分享得解锁 | 🔲 | 分享 App 解锁无限搜索 |
| 搜索结果水印分享图 | 🔲 | 自带品牌 + 下载二维码 |
| 社群裂变 | 🔲 | QQ 群 / Telegram 群滚雪球 |

### 7.3 核武器级策略

| 策略 | 状态 | 说明 |
|------|------|------|
| 过期域名抢注 | 🔲 | 竞品过期域名 301 到 magnetgoogo.com |
| 油猴脚本 | 🔲 | 在任意磁力站显示磁力古哥结果（寄生获客） |
| Web 版搜索 | 🔲 | 在网站直接提供搜索 → 百万级 SEO 长尾页 |

### 7.4 执行排期

| 阶段 | 时间 | 任务 | 预期 |
|------|------|------|------|
| Phase 1 | 1-3 天 | 吾爱破解 + V2EX + 酷安 + 知乎 Top10 + Reddit | 首周 500+ 下载 |
| Phase 2 | 4-10 天 | 程序化 SEO 部署 + 知乎 30+ 回答 + B站视频 + Product Hunt | 累计 1000+ 下载 |
| Phase 3 | 11-30 天 | 裂变机制开发 + 油猴脚本 + 博客矩阵 + 宕机监控 | 稳定增长 |

### 7.5  30 天目标

| 指标 | 目标 |
|------|------|
| APK 下载量 | 500+ |
| DAU | 50+ |
| GitHub Stars | 50+ |
| 日均 UV | 100+ |

> **核心：不是等用户来找你，而是去用户在的每一个角落拦截他们。今天就开始。**
