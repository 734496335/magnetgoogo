# 磁力古哥 品牌运营推广 & SEO 清单

文档版本：V1.0
更新时间：2026-05-03

> 本文档跟踪所有品牌曝光、搜索引擎优化、渠道推广的执行状态。
> 状态标记：✅ 已完成 | 🔄 进行中 | 🔲 待做

---

## 1. 搜索引擎收录

### 1.1 落地页技术 SEO（magnetgoogo.com）

| 项目 | 状态 | 说明 |
|------|------|------|
| `robots.txt` | ✅ | 允许全站爬取，指向 sitemap |
| `sitemap.xml` | ✅ | 含首页 URL，CF Pages `_headers` 修复 Content-Type |
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
| 多页面扩展 | ✅ | faq/privacy/terms/about/contact 5 个独立页，sitemap 6 URLs |
| PWA manifest | 🔲 | 让搜索引擎识别为 Web App |
| 百度适配 meta | ✅ | `codeva-le9FKQPkUa` 已添加 |

### 1.2 搜索引擎提交

| 平台 | 面向 | 状态 | 操作入口 |
|------|------|------|----------|
| **Google Search Console** | 国际 | ✅ | Cloudflare DNS 自动验证，sitemap 已提交 Success |
| **Bing Webmaster Tools** | 国际 | ✅ | 从 GSC 导入，sitemap Success，6 URLs discovered |
| **百度站长平台** | 国内 | ✅ | 文件验证通过，API token=p5bdB9NbHwP05Syl |
| **Yandex Webmaster** | 俄/东欧 | 🔲 | https://webmaster.yandex.com |
| **IndexNow** | Bing/Yandex | ✅ | key=a1b2c3d4e5f6g7h8，首次 ping 已发送(200) |
| **搜狗站长** | 国内 | 🔲 | https://zhanzhang.sogou.com |
| **360 站长** | 国内 | 🔲 | https://zhanzhang.so.com |
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
| Google 索引页数 | GSC | 1 | 5+ |
| Google 搜索展示 | GSC | 0 | 100+/周 |
| GitHub Stars | GitHub | 0 | 50+ |
| GitHub 流量 | Insights → Traffic | 0 | 10+ unique/天 |
| 落地页 UV | CF Analytics | - | 50+/天 |
| APK 下载量 | GitHub Releases | - | 100+ |
