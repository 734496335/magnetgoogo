#!/usr/bin/env node
/**
 * 通用"磁力"关键词 SEO 页面生成器
 * 围绕高搜索量的磁力相关长尾词生成着陆页
 * 输出到 magnetgoogo-site/guide/ 目录
 */

const fs = require('fs');
const path = require('path');

const SITE_DIR = path.join(__dirname, '..', 'magnetgoogo-site');
const OUT_DIR = path.join(SITE_DIR, 'guide');

// ─── 关键词数据库 ─────────────────────────────────────────────────
// 每个词条对应一个着陆页，围绕用户真实搜索意图设计
const KEYWORDS = [
  // ── 核心搜索意图：找工具 ──
  {
    slug: 'cili-sousuo',
    title: '磁力搜索引擎推荐',
    subtitle: '2026年最好用的磁力搜索工具合集',
    metaDesc: '2026年最新磁力搜索引擎推荐，免费、无广告、聚合全网资源。磁力古哥一次搜索全网磁力资源，秒级响应。',
    keywords: '磁力搜索,磁力搜索引擎,磁力搜索推荐,磁力搜索工具,磁力搜索App,最好的磁力搜索',
    sections: [
      { h2: '什么是磁力搜索引擎？', body: '磁力搜索引擎是一种专门搜索磁力链接（Magnet Link）的工具。磁力链接是基于 DHT 分布式哈希表网络的资源定位方式，无需传统服务器即可实现点对点的文件分享。通过磁力搜索引擎，你可以快速找到电影、音乐、软件、游戏、电子书等各类资源的磁力下载链接。' },
      { h2: '2026年磁力搜索引擎现状', body: '目前国内磁力搜索引擎面临严峻挑战：域名频繁更换、服务器不稳定、广告泛滥、资源库有限。用户经常发现昨天还能用的搜索站今天就打不开了，不得不反复寻找新地址。传统单站式磁力搜索已经无法满足用户需求。' },
      { h2: '磁力古哥：终极磁力搜索解决方案', body: '磁力古哥（Magnet Googo）是一款革命性的聚合磁力搜索 App，它的核心理念是：<strong>不依赖任何单一站点</strong>。当你搜索一个关键词时，磁力古哥会同时查询全网多个磁力资源站，将结果智能合并、去重、排序后呈现给你。即使某个站点挂了，其他站点照常提供结果。<strong>一次搜索，全网直达。</strong>' },
      { h2: '为什么选择磁力古哥？', list: ['<strong>聚合全网资源</strong> — 不依赖单一站点，覆盖面远超任何单个磁力站', '<strong>完全免费</strong> — 无广告、无需注册、无会员制', '<strong>秒级响应</strong> — 并发查询多个源，结果实时呈现', '<strong>智能排序</strong> — 按相关性和热度智能排序，最优结果置顶', '<strong>支持收藏和历史</strong> — 搜索记录和收藏本地保存', '<strong>持续更新</strong> — 源站挂了会自动替换新源，永远保持可用'] },
      { h2: '如何使用磁力古哥搜索？', body: '使用磁力古哥非常简单：下载安装 APK → 打开 App → 输入关键词 → 获取结果 → 复制磁力链接到你喜欢的下载工具（如迅雷、qBittorrent）。全程不到 30 秒。' },
    ]
  },
  {
    slug: 'cili-lianjie-zenme-yong',
    title: '磁力链接怎么用',
    subtitle: '磁力链接完全使用指南 — 从入门到精通',
    metaDesc: '磁力链接怎么用？完整教程：什么是磁力链接、如何搜索、如何下载。推荐最好用的磁力搜索工具和下载软件。',
    keywords: '磁力链接怎么用,磁力链接下载,磁力链接教程,magnet链接,磁力链接是什么,磁力链接搜索',
    sections: [
      { h2: '什么是磁力链接？', body: '磁力链接（Magnet Link）是一种以 <code>magnet:?</code> 开头的特殊链接格式。它不像普通下载链接指向某个服务器上的文件，而是通过一串哈希值（hash）在 P2P 网络中定位资源。磁力链接的优势在于不依赖中央服务器，只要网络中有人分享该资源就能下载。' },
      { h2: '磁力链接长什么样？', body: '一个典型的磁力链接格式如下：<br><code>magnet:?xt=urn:btih:XXXXXXXXXXXXXXXXXXXXXXXX&dn=文件名</code><br>其中 <code>xt=urn:btih:</code> 后面的一串字符是资源的唯一标识（哈希值），<code>dn=</code> 是文件名（可选）。' },
      { h2: '第一步：搜索磁力链接', body: '要使用磁力链接，首先需要找到你想要资源的磁力链接。推荐使用<strong>磁力古哥（Magnet Googo）</strong>，一款免费的聚合磁力搜索 App：<br>1. 下载安装磁力古哥<br>2. 输入你想搜索的内容（如电影名、软件名）<br>3. 从搜索结果中选择合适的资源<br>4. 复制磁力链接' },
      { h2: '第二步：使用下载工具下载', body: '拿到磁力链接后，你需要一个支持磁力下载的工具。常见的下载工具有：', list: ['<strong>迅雷</strong> — 国内最流行的下载工具，支持磁力链接', '<strong>qBittorrent</strong> — 开源免费，无广告，推荐！', '<strong>BitComet（比特彗星）</strong> — 老牌 BT 下载工具', '<strong>Motrix</strong> — 全能下载工具，界面美观', '<strong>WebTorrent</strong> — 浏览器内即可下载'] },
      { h2: '第三步：打开下载工具添加磁力链接', body: '在下载工具中选择"添加磁力链接"或"新建下载"，粘贴刚才复制的磁力链接即可开始下载。下载速度取决于该资源的做种人数（Seeders）——做种人越多，下载越快。' },
      { h2: '常见问题', body: '<strong>Q: 磁力链接下载速度慢怎么办？</strong><br>A: 选择做种人数（S/Seeders）多的资源，或尝试更换下载工具。<br><br><strong>Q: 磁力链接打不开？</strong><br>A: 确保你的下载工具已正确安装并设置为磁力链接的默认打开程序。<br><br><strong>Q: 如何找到更多的磁力链接？</strong><br>A: 使用磁力古哥搜索，它聚合全网资源，一次搜索全部直达。' },
    ]
  },
  {
    slug: 'cili-xiazai',
    title: '磁力下载教程',
    subtitle: '2026年最新磁力资源下载完全指南',
    metaDesc: '磁力下载完全指南：如何搜索磁力资源、选择下载工具、提高下载速度。推荐磁力古哥聚合搜索。',
    keywords: '磁力下载,磁力资源下载,磁力链接下载,BT下载,种子下载,磁力下载工具',
    sections: [
      { h2: '磁力下载是什么？', body: '磁力下载是通过磁力链接（Magnet Link）进行 P2P 文件传输的方式。与传统 HTTP 下载不同，磁力下载不依赖单一服务器，而是从多个用户那里同时获取文件片段，速度更快、资源更持久。' },
      { h2: '磁力下载三步走', body: '<strong>第一步：找资源</strong> — 使用磁力古哥搜索你需要的内容<br><strong>第二步：复制链接</strong> — 从搜索结果中复制磁力链接<br><strong>第三步：开始下载</strong> — 粘贴到下载工具中即可' },
      { h2: '推荐下载工具', list: ['<strong>qBittorrent</strong> — 完全免费开源，无广告，支持 Windows/Mac/Linux', '<strong>迅雷</strong> — 国内用户首选，加速效果好', '<strong>BitComet</strong> — 老牌稳定，支持长效种子', '<strong>Motrix</strong> — 全能型下载器，界面清爽', '<strong>Transmission</strong> — 轻量级，适合 NAS 和服务器'] },
      { h2: '如何搜索磁力资源？', body: '推荐使用<strong>磁力古哥（Magnet Googo）</strong>。磁力古哥是一款免费 Android App，聚合了全网磁力资源站。输入关键词后，它会同时查询多个站点，智能合并结果，让你一次搜到最全的资源。不用再一个一个站点找了！' },
      { h2: '提高磁力下载速度的技巧', list: ['选择<strong>做种人数多</strong>（S 值高）的资源', '添加更多 <strong>Tracker 服务器</strong>（网上搜"最新 tracker 列表"）', '确保路由器开启了 <strong>UPnP/端口转发</strong>', '避免同时下载过多任务', '优先选择文件<strong>体积更小</strong>的版本'] },
    ]
  },
  {
    slug: 'bt-sousuo',
    title: 'BT搜索引擎推荐',
    subtitle: '2026年最好用的BT种子搜索引擎',
    metaDesc: '2026年最新BT搜索引擎推荐。BT种子搜索、磁力搜索聚合工具。磁力古哥一次搜索全网BT资源。',
    keywords: 'BT搜索,BT搜索引擎,BT种子搜索,种子搜索,torrent搜索,BT下载搜索',
    sections: [
      { h2: '什么是 BT 搜索？', body: 'BT 搜索是指在互联网上搜索 BitTorrent 种子文件或磁力链接的行为。BT（BitTorrent）是一种点对点文件传输协议，通过种子文件或磁力链接，用户可以从其他用户处高速下载文件。BT 搜索引擎就是帮你快速找到这些种子和磁力链接的工具。' },
      { h2: '2026年 BT 搜索面临的困境', body: '传统 BT 搜索站（如海盗湾、磁力猫、BTSOW 等）面临严重问题：域名频繁被封、服务器经常宕机、广告满天飞、资源库不完整。用户需要不断更换站点，体验极差。' },
      { h2: '磁力古哥：新一代 BT 搜索解决方案', body: '磁力古哥彻底解决了传统 BT 搜索的痛点。它不是又一个 BT 搜索站，而是一个<strong>聚合搜索引擎</strong>——同时查询多个 BT/磁力站点，将结果合并呈现。一个站挂了？还有其他站顶上。<strong>永远能搜到你要的资源。</strong>' },
      { h2: '磁力古哥 vs 传统 BT 搜索站', table: { headers: ['对比项', '传统 BT 搜索站', '磁力古哥'], rows: [['资源覆盖', '单站资源有限', '聚合全网，覆盖最全'], ['稳定性', '域名常换，经常打不开', '多源聚合，永不失效'], ['广告', '弹窗广告满天飞', '零广告，纯净体验'], ['速度', '单站查询', '并发查询，秒级响应'], ['费用', '部分收费或限制', '完全免费'], ['平台', '仅网页', 'Android App，随时随地搜索']] } },
      { h2: '立即开始使用', body: '下载磁力古哥 App，告别不稳定的 BT 搜索站。一次搜索，全网直达。' },
    ]
  },
  {
    slug: 'cili-sousuo-app',
    title: '磁力搜索App推荐',
    subtitle: '2026年最好用的手机磁力搜索应用',
    metaDesc: '2026年最好用的磁力搜索App推荐。磁力古哥 — 免费、无广告、聚合全网磁力资源的Android搜索应用。',
    keywords: '磁力搜索App,磁力搜索应用,手机磁力搜索,Android磁力搜索,磁力搜索软件,磁力搜索工具',
    sections: [
      { h2: '为什么需要磁力搜索 App？', body: '传统的磁力搜索网站在手机上体验很差：界面不适配、弹窗广告多、加载速度慢。一个专门为手机优化的磁力搜索 App 能大幅提升搜索体验，让你随时随地搜索和管理磁力资源。' },
      { h2: '磁力古哥 — 最佳磁力搜索 App', body: '<strong>磁力古哥（Magnet Googo）</strong>是 2026 年最值得推荐的磁力搜索 App。它是一款完全免费、无广告的 Android 应用，核心功能是聚合全网磁力资源站进行联合搜索。' },
      { h2: '磁力古哥 App 功能亮点', list: ['<strong>全网聚合搜索</strong> — 一次搜索查询多个磁力站，结果最全', '<strong>智能排序</strong> — 按相关性、做种数自动排序', '<strong>秒级响应</strong> — 并发查询，结果实时返回', '<strong>完全免费</strong> — 无广告、无会员、无功能限制', '<strong>搜索历史</strong> — 本地保存搜索记录和收藏', '<strong>体积小巧</strong> — APK 仅约 30MB，不占空间', '<strong>持续更新</strong> — 资源站变动时自动适配'] },
      { h2: '如何下载磁力古哥？', body: '磁力古哥目前支持 Android 平台，可以通过以下方式免费下载：<br>1. 官方网站：<a href="https://magnetgoogo.com">magnetgoogo.com</a><br>2. GitHub Releases<br>3. 蓝奏云备用下载' },
    ]
  },
  {
    slug: 'cili-sousuo-wangzhan',
    title: '磁力搜索网站大全',
    subtitle: '2026年可用的磁力搜索网站汇总',
    metaDesc: '2026年最新可用的磁力搜索网站大全。磁力猫、BTSOW、种子吧等打不开？推荐使用磁力古哥聚合搜索。',
    keywords: '磁力搜索网站,磁力网站大全,磁力搜索网址,磁力站,磁力网站推荐,磁力搜索入口',
    sections: [
      { h2: '2026年磁力搜索网站现状', body: '国内磁力搜索网站数量众多，但绝大多数面临域名频繁更换、服务器不稳定、被防火墙屏蔽等问题。以下是一些知名的磁力搜索网站品牌（注：具体域名经常变动）。' },
      { h2: '国内磁力搜索站', list: ['<strong>磁力猫</strong> — 老牌磁力搜索引擎，域名频繁更换', '<strong>磁力宝</strong> — 拥有多个镜像站点', '<strong>磁力帝</strong> — 直接提供磁力链接', '<strong>BTSOW</strong> — 知名 BT 资源搜索', '<strong>种子吧</strong> — 种子和磁力资源搜索', '<strong>磁力天堂</strong> — 支持多种下载方式', '<strong>SOBT</strong> — 简洁稳定', '<strong>磁力狗</strong> — 资源聚合站'] },
      { h2: '国际磁力搜索站', list: ['<strong>The Pirate Bay</strong> — 全球最知名的种子站（国内无法直接访问）', '<strong>1337x</strong> — 资源丰富的国际种子站', '<strong>Nyaa</strong> — 动漫/ACG 资源专用', '<strong>RARBG</strong> — 高品质影视资源（已关站，镜像仍存）', '<strong>YTS</strong> — 专注高清电影种子', '<strong>Knaben</strong> — 种子搜索聚合引擎'] },
      { h2: '磁力搜索网站的共同问题', list: ['域名频繁更换，旧地址失效', '广告弹窗严重影响体验', '单站资源不完整', '国际站国内无法访问', '存在安全隐患（恶意软件、钓鱼）'] },
      { h2: '更好的选择：磁力古哥聚合搜索', body: '与其不断追逐各个磁力站的最新地址，不如用<strong>磁力古哥</strong>一劳永逸地解决问题。磁力古哥把上述所有磁力站整合到一个 App 里。一次搜索，全网资源全部直达。不用再收藏一堆不断过期的网址了。' },
    ]
  },
  {
    slug: 'zhongzi-sousuo',
    title: '种子搜索引擎推荐',
    subtitle: '2026年最好的种子搜索工具',
    metaDesc: '2026年种子搜索引擎推荐。BT种子搜索、磁力搜索工具对比。磁力古哥一次搜索全网种子资源。',
    keywords: '种子搜索,种子搜索引擎,BT种子搜索,种子搜索推荐,种子搜索器,种子搜索网站',
    sections: [
      { h2: '什么是种子搜索？', body: '种子搜索是指在互联网上搜索 BT 种子文件（.torrent）或磁力链接的行为。种子文件和磁力链接都是 BitTorrent 协议的资源定位方式，通过它们可以使用 BT 下载工具高速下载文件。' },
      { h2: '种子搜索 vs 磁力搜索', body: '早期 BT 下载需要下载 .torrent 种子文件，现在已经被磁力链接（Magnet Link）逐步取代。磁力链接更加便捷——只需一行链接文本，无需额外下载文件。现代"种子搜索"通常也包含磁力链接搜索。' },
      { h2: '磁力古哥：最佳种子/磁力搜索工具', body: '磁力古哥聚合了国内外主流种子站和磁力站，一次搜索覆盖全网。无论你搜的是种子还是磁力链接，都能快速找到。' },
      { h2: '使用场景', list: ['<strong>影视资源</strong> — 搜索电影、电视剧、纪录片', '<strong>音乐资源</strong> — 搜索无损音乐、音乐合集', '<strong>游戏资源</strong> — 搜索 PC 游戏、主机游戏', '<strong>软件资源</strong> — 搜索各类工具软件', '<strong>动漫资源</strong> — 搜索日本动画、漫画', '<strong>电子书</strong> — 搜索 PDF、EPUB 格式电子书'] },
    ]
  },
  {
    slug: 'cili-sousuo-2026',
    title: '2026年最新磁力搜索引擎',
    subtitle: '2026年还能用的磁力搜索工具推荐',
    metaDesc: '2026年最新还能用的磁力搜索引擎推荐。哪些磁力站还活着？磁力古哥聚合全网磁力资源，永不失效。',
    keywords: '2026磁力搜索,2026磁力搜索引擎,最新磁力搜索,2026年磁力搜索推荐,磁力搜索引擎2026',
    sections: [
      { h2: '2026年磁力搜索生态', body: '2026年，磁力搜索引擎的生态正在快速变化。大量曾经知名的磁力站已经关站或频繁更换域名，用户找到稳定可用的搜索工具越来越困难。' },
      { h2: '2026年磁力搜索面临的挑战', list: ['域名封锁加剧，旧地址大批失效', '防火墙对国际站封锁更严', '广告变本加厉，用户体验恶化', 'CDN/WAF 反爬增强（Cloudflare Turnstile 等）', '站点运营者跑路或被查'] },
      { h2: '2026年的解决方案：聚合搜索', body: '面对这些挑战，聚合搜索成为最佳解决方案。磁力古哥（Magnet Googo）正是为此而生——它不是某个具体的磁力站，而是一个搜索引擎的搜索引擎。即使某个站挂了，磁力古哥会自动切换到其他可用站点，<strong>永远保持可用</strong>。' },
      { h2: '磁力古哥 2026 版本功能', list: ['<strong>全网聚合搜索</strong> — 覆盖数十个磁力/种子站', '<strong>自动源更新</strong> — 源站变动时自动适配', '<strong>智能排序</strong> — 按相关性和热度排序', '<strong>零广告</strong> — 纯净搜索体验', '<strong>完全免费</strong> — 无需付费、无需注册'] },
    ]
  },
  {
    slug: 'cili-lianjie-sousuo',
    title: '磁力链接搜索工具',
    subtitle: '如何快速搜索磁力链接',
    metaDesc: '最好用的磁力链接搜索工具推荐。磁力古哥聚合全网磁力资源站，一次搜索获取所有磁力链接。',
    keywords: '磁力链接搜索,magnet搜索,磁力链接搜索工具,磁力链接搜索引擎,搜索磁力链接',
    sections: [
      { h2: '磁力链接搜索的本质', body: '磁力链接搜索就是在互联网上找到你需要的文件对应的磁力链接（magnet:?xt=urn:btih:...）。拿到磁力链接后，配合迅雷、qBittorrent 等下载工具就能下载文件。' },
      { h2: '传统搜索方式的问题', body: '传统方式是打开一个磁力搜索网站（如磁力猫、BTSOW），但这些站经常打不开、换域名、或者搜索结果不全。用户不得不同时收藏十几个站点轮流尝试。' },
      { h2: '更高效的方式：磁力古哥', body: '磁力古哥一次搜索就能查询全网多个磁力站，相当于帮你同时在十几个站点搜索，然后把结果合并去重后展示。效率提升 10 倍以上。' },
      { h2: '搜索技巧', list: ['使用<strong>精确关键词</strong>搜索（如电影名+年份）', '尝试<strong>英文原名</strong>搜索，结果通常更多', '关注结果中的<strong>做种数（S）</strong>，越高下载越快', '关注<strong>文件大小</strong>，判断是否为你需要的版本'] },
    ]
  },
  {
    slug: 'cili-ziyuan',
    title: '磁力资源搜索指南',
    subtitle: '如何高效搜索和下载磁力资源',
    metaDesc: '磁力资源搜索完全指南：电影、音乐、游戏、动漫等磁力资源如何搜索和下载。推荐磁力古哥聚合搜索。',
    keywords: '磁力资源,磁力资源搜索,磁力资源下载,磁力资源站,磁力资源网站,免费磁力资源',
    sections: [
      { h2: '什么是磁力资源？', body: '磁力资源是指通过磁力链接（Magnet Link）或 BT 种子可以下载的各类数字内容，包括电影、电视剧、音乐、游戏、软件、电子书、动漫等。这些资源分布在全球的 P2P 网络中，通过磁力搜索引擎可以找到它们。' },
      { h2: '热门磁力资源分类', list: ['<strong>影视</strong> — 最新院线电影、热播电视剧、经典老片、纪录片', '<strong>动漫/ACG</strong> — 日本动画新番、漫画、轻小说、Galgame', '<strong>音乐</strong> — 无损音乐、音乐合集、演唱会视频', '<strong>游戏</strong> — PC 大作、独立游戏、模拟器 ROM', '<strong>软件</strong> — 专业软件、操作系统镜像', '<strong>学习资料</strong> — 教程视频、电子书、文档'] },
      { h2: '如何搜索磁力资源', body: '推荐使用<strong>磁力古哥</strong>，聚合全网磁力资源站，一次搜索全部直达。下载 App 后输入关键词即可获取全网最全的磁力资源。' },
      { h2: '安全提示', list: ['优先选择<strong>做种人数多</strong>的资源（更可靠）', '下载后<strong>先用杀毒软件扫描</strong>', '注意文件格式是否正常（避免伪装的 .exe）', '使用正规下载工具（qBittorrent、迅雷等）'] },
    ]
  },
  {
    slug: 'magnet-search-engine',
    title: 'Best Magnet Search Engine 2026',
    subtitle: 'The Ultimate Magnet Link Search Tool',
    metaDesc: 'Best magnet search engine in 2026. Magnet Googo aggregates multiple torrent sites for one-stop magnet link search. Free, no ads.',
    keywords: 'magnet search engine,magnet search,magnet link search,torrent search engine,best magnet search,Magnet Googo',
    lang: 'en',
    sections: [
      { h2: 'What is a Magnet Search Engine?', body: 'A magnet search engine helps you find magnet links — special URIs that identify files using cryptographic hashes rather than server locations. These links work with BitTorrent clients to download files from a peer-to-peer network.' },
      { h2: 'The Problem with Traditional Torrent Sites', body: 'Popular torrent sites like The Pirate Bay, 1337x, and RARBG face constant domain seizures, server downtime, and geo-blocking. Users have to keep track of mirror sites and proxy lists just to perform a simple search.' },
      { h2: 'Magnet Googo: Search All Sites at Once', body: '<strong>Magnet Googo</strong> is a free Android app that aggregates multiple torrent and magnet sites into one unified search. When you search for a keyword, Magnet Googo queries dozens of sources simultaneously and merges the results. If one site goes down, others pick up the slack. <strong>Every magnet. One search.</strong>' },
      { h2: 'Key Features', list: ['<strong>Multi-source aggregation</strong> — Searches dozens of torrent sites at once', '<strong>Smart ranking</strong> — Results sorted by relevance and seeders', '<strong>Instant results</strong> — Concurrent queries for sub-second response', '<strong>Completely free</strong> — No ads, no registration, no premium tier', '<strong>Always available</strong> — Sources auto-update when sites change'] },
      { h2: 'How to Use', body: '1. Download Magnet Googo APK from <a href="https://magnetgoogo.com">magnetgoogo.com</a><br>2. Open the app and enter your search query<br>3. Browse results with file size, seeders, and date info<br>4. Copy the magnet link to your favorite torrent client (qBittorrent, Transmission, etc.)' },
    ]
  },
  {
    slug: 'torrent-search',
    title: 'Torrent Search Engine 2026',
    subtitle: 'Find Any Torrent with One Search',
    metaDesc: 'Best torrent search engine 2026. Magnet Googo aggregates torrents from multiple sites. Free, no ads, instant results.',
    keywords: 'torrent search,torrent search engine,best torrent search,torrent finder,torrent aggregator,search torrents',
    lang: 'en',
    sections: [
      { h2: 'Why You Need a Torrent Aggregator', body: 'No single torrent site has everything. Some specialize in movies, others in anime or software. An aggregator like Magnet Googo searches all of them at once, giving you the most comprehensive results possible.' },
      { h2: 'Magnet Googo vs Individual Torrent Sites', table: { headers: ['Feature', 'Individual Sites', 'Magnet Googo'], rows: [['Coverage', 'Limited to one site', 'Aggregates dozens of sites'], ['Availability', 'Often blocked or down', 'Always available'], ['Ads', 'Heavy ads and popups', 'Zero ads'], ['Speed', 'Single source', 'Concurrent multi-source'], ['Cost', 'Some require registration', 'Completely free']] } },
      { h2: 'Supported Source Categories', list: ['<strong>General torrents</strong> — The Pirate Bay, 1337x, Knaben, MagnetDL', '<strong>Movies</strong> — YTS, RARBG mirrors', '<strong>Anime</strong> — Nyaa, AnimeTosho, Mikanani, ACG.rip', '<strong>Chinese sources</strong> — 30+ Chinese magnet sites'] },
      { h2: 'Download Now', body: 'Get Magnet Googo for free at <a href="https://magnetgoogo.com">magnetgoogo.com</a>. Available for Android.' },
    ]
  },
  {
    slug: 'dianying-xiazai',
    title: '电影磁力下载',
    subtitle: '如何免费搜索和下载高清电影磁力资源',
    metaDesc: '免费电影磁力下载教程。如何搜索高清电影磁力链接？推荐磁力古哥聚合搜索，一次搜索全网电影资源。',
    keywords: '电影磁力下载,电影磁力搜索,电影种子下载,高清电影下载,电影BT下载,免费电影下载',
    sections: [
      { h2: '如何搜索电影磁力资源？', body: '想下载一部电影的磁力资源，最高效的方式是使用磁力搜索引擎。输入电影名称（建议加上年份），即可获取相关磁力链接。推荐使用<strong>磁力古哥</strong>，它聚合全网资源站，搜索结果最全面。' },
      { h2: '电影搜索技巧', list: ['使用<strong>电影英文原名+年份</strong>搜索（如 "Inception 2010"），结果更多', '关注文件大小判断画质：1-2GB 通常是 720p，4-8GB 通常是 1080p，20GB+ 通常是 4K', '优先选择<strong>做种人数高</strong>的资源，下载更快', '看文件名中的编码信息：x265/HEVC 比 x264 体积更小', '中文电影也可以尝试英文名搜索'] },
      { h2: '推荐搜索工具', body: '磁力古哥（Magnet Googo）聚合了国内外数十个磁力/种子站，包括 YTS（高清电影专用站）、1337x、海盗湾等，一次搜索覆盖全网。完全免费，无需注册。' },
      { h2: '下载流程', body: '1. 打开磁力古哥，搜索电影名<br>2. 选择合适画质和大小的资源<br>3. 复制磁力链接<br>4. 粘贴到迅雷/qBittorrent 开始下载<br>5. 等待下载完成，享受观影' },
    ]
  },
  {
    slug: 'dongman-cili-sousuo',
    title: '动漫磁力搜索',
    subtitle: '日本动画/ACG资源磁力搜索指南',
    metaDesc: '动漫磁力搜索完全指南。如何搜索日本动画、漫画、轻小说磁力资源？推荐磁力古哥聚合搜索。',
    keywords: '动漫磁力搜索,动漫种子下载,日本动画下载,动漫BT下载,新番下载,ACG资源搜索',
    sections: [
      { h2: '动漫磁力资源搜索', body: '对于动漫/ACG 爱好者，磁力下载是获取动画资源的重要途径。无论是当季新番、经典老番、漫画还是轻小说，都可以通过磁力搜索找到。' },
      { h2: '专业动漫资源站', list: ['<strong>Nyaa</strong> — 全球最大的日本动画种子站', '<strong>動漫花園</strong> — 中文动漫资源搜索引擎', '<strong>Mikanani（蜜柑计划）</strong> — 新番自动追踪和下载', '<strong>ACG.rip</strong> — ACG 资源分享站', '<strong>AnimeTosho</strong> — Nyaa 的镜像和备份站', '<strong>TokyoTosho</strong> — 日本资源搜索引擎'] },
      { h2: '磁力古哥：一站搜全部动漫资源', body: '磁力古哥整合了上述所有动漫资源站。你不需要分别访问 Nyaa、動漫花園、Mikanani 等网站——在磁力古哥中搜索一次，就能获取全部站点的结果。特别适合追番族！' },
      { h2: '搜索技巧', list: ['搜索<strong>日文原名</strong>结果最全', '新番可以搜索<strong>字幕组名称</strong>（如"喵萌奶茶屋"）', '加上<strong>分辨率</strong>关键词（如"1080p"）精确匹配', '使用<strong>集数编号</strong>（如"S01E05"）搜索特定集'] },
    ]
  },
  {
    slug: 'cili-sousuo-jiqiao',
    title: '磁力搜索技巧大全',
    subtitle: '提高磁力搜索效率的实用技巧',
    metaDesc: '磁力搜索技巧大全：如何提高搜索效率、找到高质量资源、避免假资源。磁力古哥搜索最佳实践。',
    keywords: '磁力搜索技巧,如何搜索磁力,磁力搜索方法,搜索磁力链接技巧,BT搜索技巧',
    sections: [
      { h2: '关键词优化技巧', list: ['<strong>使用英文原名</strong> — 国际资源更丰富，英文搜索结果通常比中文多', '<strong>加上年份</strong> — 搜索电影时加年份避免同名混淆（如"Dune 2024"）', '<strong>使用准确标题</strong> — 避免模糊搜索，越准确结果越精确', '<strong>尝试别名</strong> — 一部作品可能有多个名称，换个名称试试'] },
      { h2: '筛选高质量资源', list: ['<strong>看做种数（Seeders）</strong> — S 值越高下载越快，也更可靠', '<strong>看文件大小</strong> — 电影 1-2GB=720p, 4-8GB=1080p, 15GB+=4K', '<strong>看发布时间</strong> — 优先选择较新的资源', '<strong>看来源站点</strong> — 知名站点的资源更靠谱'] },
      { h2: '避免假资源和风险', list: ['<strong>不下载超小文件</strong> — 一部电影只有几 MB 肯定是假的', '<strong>不下载 .exe 文件</strong> — 视频/音乐不应该是 .exe 格式', '<strong>用杀毒软件扫描</strong> — 下载后先扫一遍', '<strong>注意文件名</strong> — 与搜索内容不符的要警惕'] },
      { h2: '使用磁力古哥提升效率', body: '磁力古哥的聚合搜索天然具备效率优势——同样一个关键词，它会从多个站点获取结果，你不需要手动去多个网站反复搜索。而且磁力古哥的智能排序会把最相关、做种最多的结果排在前面。' },
    ]
  },
  {
    slug: 'free-magnet-search',
    title: 'Free Magnet Search Tool',
    subtitle: 'Search Magnet Links for Free — No Ads, No Registration',
    metaDesc: 'Free magnet search tool with no ads and no registration. Magnet Googo searches dozens of torrent sites at once. Download for Android.',
    keywords: 'free magnet search,free torrent search,magnet search free,no ads magnet search,free magnet link search',
    lang: 'en',
    sections: [
      { h2: 'Free Magnet Search with Magnet Googo', body: 'Magnet Googo is a completely free magnet search application for Android. No ads, no registration required, no premium features locked behind a paywall. Every feature is available to every user from day one.' },
      { h2: 'Why Free Matters', body: 'Many torrent search tools either show intrusive ads, require registration, or lock features behind paid plans. Magnet Googo believes magnet search should be a utility — simple, fast, and free for everyone.' },
      { h2: 'What You Get for Free', list: ['<strong>Unlimited searches</strong> — No daily search limits', '<strong>Full result details</strong> — File size, seeders, leechers, date', '<strong>Search history</strong> — Save and revisit past searches', '<strong>Bookmarks</strong> — Save interesting results for later', '<strong>Multi-source search</strong> — Dozens of torrent sites aggregated', '<strong>Regular updates</strong> — New sources added continuously'] },
      { h2: 'Download', body: 'Get Magnet Googo for free at <a href="https://magnetgoogo.com">magnetgoogo.com</a>.' },
    ]
  },
];

// ─── HTML 生成 ─────────────────────────────────────────────────────

function renderSection(section) {
  let html = `\n    <h2 class="text-xl font-bold">${section.h2}</h2>\n`;
  if (section.body) {
    html += `    <p>${section.body}</p>\n`;
  }
  if (section.list) {
    html += `    <ul>\n`;
    for (const item of section.list) {
      html += `      <li>${item}</li>\n`;
    }
    html += `    </ul>\n`;
  }
  if (section.table) {
    html += `    <div class="overflow-x-auto">\n    <table class="w-full text-left border-collapse">\n      <thead><tr>\n`;
    for (const h of section.table.headers) {
      html += `        <th class="bg-gray-50 border border-gray-200 px-4 py-2 font-semibold">${h}</th>\n`;
    }
    html += `      </tr></thead>\n      <tbody>\n`;
    for (const row of section.table.rows) {
      html += `      <tr>\n`;
      for (const cell of row) {
        html += `        <td class="border border-gray-200 px-4 py-2">${cell}</td>\n`;
      }
      html += `      </tr>\n`;
    }
    html += `      </tbody>\n    </table>\n    </div>\n`;
  }
  return html;
}

function generateGuidePage(kw) {
  const lang = kw.lang || 'zh-CN';
  const isEn = lang === 'en';
  const today = new Date().toISOString().slice(0, 10);
  const downloadUrl = 'https://api.naoshiquan.com/download/v0.1.8/MagGoogo-v0.1.8.apk';
  const lanzouUrl = 'https://wwbdy.lanzoue.com/iFHEh3oomsjg';
  
  const ctaTitle = isEn ? 'Free Download Magnet Googo' : '免费下载磁力古哥';
  const ctaBackup = isEn ? 'Backup Download (LanzouCloud)' : '备用下载（蓝奏云）';
  const navDownload = isEn ? 'Free Download' : '免费下载';
  const breadHome = isEn ? 'Home' : '首页';
  const breadGuide = isEn ? 'Guides' : '使用指南';
  const footerSlogan = isEn ? 'Every Magnet. One Search.' : '搜全网磁力，上磁力古哥';
  const whyTitle = isEn ? 'Why Magnet Googo?' : '为什么磁力古哥是最好的选择？';
  const whyItems = isEn
    ? ['Aggregate magnet resources across the web', 'Free, no ads, no registration', 'Instant search response', 'Search history & bookmarks', 'Continuously updated sources']
    : ['聚合全网磁力资源，不依赖单一站点', '免费、无广告、无需注册', '秒级搜索响应', '支持收藏、历史记录', '持续更新，源站变动自动适配'];

  const sectionsHtml = kw.sections.map(s => renderSection(s)).join('\n');

  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${kw.title}【2026最新】— 磁力古哥 Magnet Googo</title>
    <meta name="description" content="${kw.metaDesc}">
    <meta name="keywords" content="${kw.keywords},磁力古哥,Magnet Googo">
    <link rel="canonical" href="https://magnetgoogo.com/guide/${kw.slug}.html">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="${kw.title}【2026最新】— 磁力古哥">
    <meta property="og:description" content="${kw.metaDesc}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="https://magnetgoogo.com/guide/${kw.slug}.html">
    <meta property="og:image" content="https://magnetgoogo.com/images/app-icon-lg.png">
    <meta property="og:site_name" content="磁力古哥 Magnet Googo">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="${kw.title}【2026最新】— 磁力古哥">
    <meta name="twitter:description" content="${kw.metaDesc}">
    <link rel="icon" type="image/png" href="../images/app-icon.png">
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Article",
      "headline": "${kw.title}",
      "description": "${kw.metaDesc}",
      "author": {"@type": "Organization", "name": "磁力古哥 Magnet Googo"},
      "publisher": {"@type": "Organization", "name": "磁力古哥 Magnet Googo", "logo": {"@type": "ImageObject", "url": "https://magnetgoogo.com/images/app-icon-lg.png"}},
      "datePublished": "${today}",
      "dateModified": "${today}"
    }
    </script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config={theme:{extend:{colors:{brand:'#4285F4'}}}}</script>
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; }
      .grad-btn { background: linear-gradient(135deg, #4285F4, #34A853); transition: transform .2s, box-shadow .2s; }
      .grad-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(66,133,244,.35); }
      article h2 { margin-top: 2rem; margin-bottom: 0.75rem; }
      article h3 { margin-top: 1.5rem; margin-bottom: 0.5rem; }
      article p { margin-bottom: 1rem; line-height: 1.8; }
      article ul, article ol { margin-top: 0.5rem; margin-bottom: 1.25rem; padding-left: 1.5rem; }
      article li { margin-bottom: 0.5rem; line-height: 1.7; }
      article table { margin-top: 1rem; margin-bottom: 1.5rem; }
      article td, article th { padding: 0.5rem 1rem; }
    </style>
</head>
<body class="bg-gray-50 text-gray-800 antialiased">

<!-- NAV -->
<nav class="bg-white border-b border-gray-100 sticky top-0 z-50">
  <div class="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
    <a href="../" class="flex items-center gap-2">
      <img src="../images/app-icon-sm.png" alt="磁力古哥" class="w-8 h-8">
      <span class="font-bold text-gray-800">磁力古哥</span>
    </a>
    <a href="${downloadUrl}" class="grad-btn text-white text-sm font-medium px-4 py-2 rounded-full inline-flex items-center gap-1.5">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
      ${navDownload}
    </a>
  </div>
</nav>

<!-- BREADCRUMB -->
<div class="max-w-4xl mx-auto px-6 py-3 text-sm text-gray-400">
  <a href="../" class="hover:text-brand">${breadHome}</a> &gt; <a href="./" class="hover:text-brand">${breadGuide}</a> &gt; <span class="text-gray-600">${kw.title}</span>
</div>

<!-- MAIN -->
<main class="max-w-4xl mx-auto px-6 pb-16">

  <!-- HERO -->
  <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 md:p-12 mb-8">
    <h1 class="text-2xl md:text-3xl font-bold mb-4 text-gray-900">${kw.title}</h1>
    <p class="text-lg text-gray-500 mb-6">${kw.subtitle}</p>
    <div class="flex flex-col sm:flex-row gap-3">
      <a href="${downloadUrl}" class="grad-btn text-white font-semibold px-8 py-3 rounded-full text-center inline-flex items-center justify-center gap-2">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
        ${ctaTitle}
      </a>
      <a href="${lanzouUrl}" target="_blank" class="border border-gray-200 text-gray-600 font-medium px-8 py-3 rounded-full text-center hover:border-brand hover:text-brand transition-colors">
        ${ctaBackup}
      </a>
    </div>
  </div>

  <!-- ARTICLE CONTENT -->
  <article class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 md:p-12 mb-8 prose prose-gray max-w-none">
${sectionsHtml}
  </article>

  <!-- WHY MAGNET GOOGO -->
  <div class="bg-blue-50 rounded-2xl p-8 mb-8">
    <h2 class="text-xl font-bold text-brand mb-4">${whyTitle}</h2>
    <ul class="space-y-2">
${whyItems.map(item => `      <li class="flex items-start gap-2"><span class="text-green-500 mt-0.5">✅</span><span>${item}</span></li>`).join('\n')}
    </ul>
  </div>

  <!-- BOTTOM CTA -->
  <div class="bg-gradient-to-r from-blue-600 to-green-500 rounded-2xl p-8 md:p-12 text-center text-white">
    <h2 class="text-2xl font-bold mb-3">${footerSlogan}</h2>
    <p class="mb-6 opacity-90">${isEn ? 'Free download, no ads, no registration.' : '免费下载，无广告，无需注册。'}</p>
    <div class="flex flex-col sm:flex-row gap-3 justify-center">
      <a href="${downloadUrl}" class="bg-white text-blue-600 font-bold px-8 py-3 rounded-full hover:shadow-lg transition-shadow">
        ${ctaTitle}
      </a>
      <a href="${lanzouUrl}" target="_blank" class="border-2 border-white text-white font-medium px-8 py-3 rounded-full hover:bg-white hover:text-blue-600 transition-colors">
        ${ctaBackup}
      </a>
    </div>
  </div>

</main>

<footer class="border-t border-gray-100 py-8 mt-8">
  <div class="max-w-4xl mx-auto px-6 text-center text-sm text-gray-400">
    <p>&copy; 2026 磁力古哥 Magnet Googo. ${footerSlogan}</p>
    <p class="mt-2">
      <a href="../" class="hover:text-brand">${breadHome}</a> · 
      <a href="./" class="hover:text-brand">${breadGuide}</a> · 
      <a href="../alt/" class="hover:text-brand">${isEn ? 'Alternatives' : '磁力站替代方案'}</a> · 
      <a href="../faq.html" class="hover:text-brand">FAQ</a>
    </p>
  </div>
</footer>

</body>
</html>`;
}

// ─── Index Page ─────────────────────────────────────────────────────

function generateGuideIndex(keywords) {
  const items = keywords.map(kw => 
    `      <li class="py-2 border-b border-gray-50"><a href="${kw.slug}.html" class="text-brand hover:underline">${kw.title}</a><span class="text-gray-400 text-sm ml-2">— ${kw.subtitle}</span></li>`
  ).join('\n');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>磁力搜索使用指南 — 磁力古哥 Magnet Googo</title>
    <meta name="description" content="磁力搜索完全指南：磁力链接怎么用、磁力搜索引擎推荐、BT种子搜索、磁力下载教程。磁力古哥聚合全网磁力资源。">
    <meta name="keywords" content="磁力搜索指南,磁力链接教程,磁力下载,BT搜索,种子搜索,磁力古哥">
    <link rel="canonical" href="https://magnetgoogo.com/guide/">
    <meta name="robots" content="index, follow">
    <link rel="icon" type="image/png" href="../images/app-icon.png">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config={theme:{extend:{colors:{brand:'#4285F4'}}}}</script>
    <style>body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; }</style>
</head>
<body class="bg-gray-50 text-gray-800 antialiased">
<nav class="bg-white border-b border-gray-100 sticky top-0 z-50">
  <div class="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
    <a href="../" class="flex items-center gap-2"><img src="../images/app-icon-sm.png" alt="磁力古哥" class="w-8 h-8"><span class="font-bold">磁力古哥</span></a>
    <a href="https://api.naoshiquan.com/download/v0.1.8/MagGoogo-v0.1.8.apk" class="bg-brand text-white text-sm font-medium px-4 py-2 rounded-full">免费下载</a>
  </div>
</nav>
<main class="max-w-4xl mx-auto px-6 py-10">
  <h1 class="text-3xl font-bold mb-2">磁力搜索使用指南</h1>
  <p class="text-gray-500 mb-8">磁力链接怎么用？如何搜索和下载磁力资源？这里有你需要的全部答案。</p>
  <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
    <ul class="space-y-0">
${items}
    </ul>
  </div>
  <div class="mt-8 text-center">
    <a href="../alt/" class="text-brand hover:underline">查看磁力站替代方案 →</a>
  </div>
</main>
<footer class="border-t border-gray-100 py-8 mt-8">
  <div class="max-w-4xl mx-auto px-6 text-center text-sm text-gray-400">
    <p>&copy; 2026 磁力古哥 Magnet Googo. 搜全网磁力，上磁力古哥。</p>
  </div>
</footer>
</body>
</html>`;
}

// ─── Sitemap ─────────────────────────────────────────────────────

function generateSitemapEntries(keywords) {
  const today = new Date().toISOString().slice(0, 10);
  return keywords.map(kw =>
    `  <url><loc>https://magnetgoogo.com/guide/${kw.slug}.html</loc><lastmod>${today}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>`
  ).join('\n');
}

// ─── MAIN ────────────────────────────────────────────────────────

function main() {
  if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
  }

  let count = 0;

  for (const kw of KEYWORDS) {
    const html = generateGuidePage(kw);
    fs.writeFileSync(path.join(OUT_DIR, `${kw.slug}.html`), html, 'utf-8');
    count++;
  }

  // Generate index page
  const indexHtml = generateGuideIndex(KEYWORDS);
  fs.writeFileSync(path.join(OUT_DIR, 'index.html'), indexHtml, 'utf-8');
  count++;

  // Update sitemap
  const sitemapPath = path.join(SITE_DIR, 'sitemap.xml');
  const sitemapEntries = generateSitemapEntries(KEYWORDS);
  const today = new Date().toISOString().slice(0, 10);
  const indexEntry = `  <url><loc>https://magnetgoogo.com/guide/</loc><lastmod>${today}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>`;

  if (fs.existsSync(sitemapPath)) {
    let sitemap = fs.readFileSync(sitemapPath, 'utf-8');
    // Remove old guide entries if any
    sitemap = sitemap.replace(/\n.*magnetgoogo\.com\/guide\/.*\n?/g, '\n');
    // Insert before </urlset>
    sitemap = sitemap.replace('</urlset>', `${indexEntry}\n${sitemapEntries}\n</urlset>`);
    fs.writeFileSync(sitemapPath, sitemap, 'utf-8');
    console.log('✅ Updated sitemap.xml with guide pages');
  }

  const cnCount = KEYWORDS.filter(k => !k.lang || k.lang !== 'en').length;
  const enCount = KEYWORDS.filter(k => k.lang === 'en').length;

  console.log(`\n🚀 Generated ${count} guide pages in ${OUT_DIR}`);
  console.log(`   - ${KEYWORDS.length} keyword pages + 1 index page`);
  console.log(`   - Chinese: ${cnCount}, English: ${enCount}`);
}

main();
