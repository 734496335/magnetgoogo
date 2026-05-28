#!/usr/bin/env node
/**
 * 程序化 SEO 页面生成器
 * 从 sources.json 品牌列表批量生成截流着陆页
 * 输出到 magnetgoogo-site/alt/ 目录
 */

const fs = require('fs');
const path = require('path');

// ─── 品牌数据库（手动整理，含搜索量高的中文别名/英文名） ─────────────
// slug 用于 URL，cnName 用于中文页面，enName 用于英文页面
// desc: 一句话介绍该品牌，增加页面差异化内容
const BRANDS = [
  // ── 国内知名磁力站 ──
  { slug: 'cilimao', cnName: '磁力猫', enName: 'CiliMao', aliases: ['磁力猫搜索','CiliMao','CLM','cilimao.me'], desc: '国内老牌磁力搜索引擎，以简洁界面著称，支持多种资源分类搜索', category: 'cn' },
  { slug: 'ciligou', cnName: '磁力狗', enName: 'CiliGou', aliases: ['磁力狗搜索','ciligou'], desc: '国内热门磁力资源聚合站，提供影视、音乐、软件等资源搜索', category: 'cn' },
  { slug: 'btsow', cnName: 'BTSOW', enName: 'BTSOW', aliases: ['BT搜','btsow.com','btsow.pics'], desc: '知名BT资源搜索引擎，支持磁力链接搜索和热门资源推荐', category: 'both' },
  { slug: 'zhongziba', cnName: '种子吧', enName: 'ZhongZiBa', aliases: ['种子吧搜索','zhongziba.cc','seed8.org'], desc: '专注种子和磁力资源搜索的国内平台，资源覆盖面广', category: 'cn' },
  { slug: 'cilibao', cnName: '磁力宝', enName: 'CiliBao', aliases: ['磁力宝搜索','CLB'], desc: '拥有大量镜像站点的磁力搜索平台，域名更换频繁', category: 'cn' },
  { slug: 'sobt', cnName: 'SOBT', enName: 'SOBT', aliases: ['SOBT搜索','sobt.top'], desc: '国内磁力搜索站，以稳定的搜索服务和简洁界面为特点', category: 'cn' },
  { slug: 'cilitiantang', cnName: '磁力天堂', enName: 'CiliTianTang', aliases: ['磁力天堂搜索','CLTT'], desc: '提供全面磁力资源搜索的国内站点，支持多种下载方式', category: 'cn' },
  { slug: 'cilidi', cnName: '磁力帝', enName: 'CiliDi', aliases: ['磁力帝搜索','52BT','cld'], desc: '国内磁力资源搜索引擎，直接提供磁力链接，响应速度快', category: 'cn' },
  { slug: 'cilimei', cnName: '磁力妹妹', enName: 'CiliMeiMei', aliases: ['磁力妹妹搜索','CLMM'], desc: '磁力资源搜索站，与磁力帝同源，提供大量直接磁力链接', category: 'cn' },
  { slug: 'cilimo', cnName: '磁力魔', enName: 'CiliMo', aliases: ['CiliMo','cilimo.com'], desc: '基于 DHT 网络的磁力搜索引擎，资源库庞大，支持 API 搜索', category: 'cn' },
  { slug: 'lulutang', cnName: '噜噜糖', enName: 'LuLuTang', aliases: ['噜噜糖搜索','lulutang.com'], desc: '新兴磁力搜索平台，界面友好，支持详情页查看', category: 'cn' },
  { slug: 'cilikoudai', cnName: '磁力口袋', enName: 'CiliKouDai', aliases: ['磁力口袋搜索','CLKD'], desc: '提供 JSON API 的磁力搜索引擎，搜索速度快，结果丰富', category: 'cn' },
  { slug: 'laowangcili', cnName: '老王磁力', enName: 'LaoWangCiLi', aliases: ['老王磁力搜索'], desc: '国内磁力资源搜索站，域名多次更换，需要定期查找最新地址', category: 'cn' },
  { slug: 'wuqiancili', cnName: '吴签磁力', enName: 'WuQianCiLi', aliases: ['吴签磁力搜索'], desc: '带有自定义验证码的磁力搜索站，需要通过验证才能使用', category: 'cn' },
  { slug: 'cilixiongmao', cnName: '磁力熊猫', enName: 'CiliXiongMao', aliases: ['磁力熊猫搜索'], desc: '国内磁力搜索平台，带验证码保护，多个镜像域名', category: 'cn' },
  { slug: 'cilingmeng', cnName: '磁力柠檬', enName: 'CiliNingMeng', aliases: ['磁力柠檬搜索'], desc: '磁力资源搜索站，采用 SPA 架构，需要浏览器渲染', category: 'cn' },
  { slug: 'cilihu', cnName: '磁力狐', enName: 'CiliHu', aliases: ['磁力狐搜索','阿狸搜','BTFOX'], desc: '磁力搜索聚合站，支持详情页跟进获取磁力链接', category: 'cn' },
  { slug: 'cilixing', cnName: '磁力星', enName: 'CiliXing', aliases: ['磁力星搜索'], desc: '磁力资源搜索引擎，提供基础的磁力链接搜索服务', category: 'cn' },
  { slug: 'cilixingqiu', cnName: '磁力星球', enName: 'CiliXingQiu', aliases: ['磁力星球搜索'], desc: '磁力搜索平台，域名更替频繁，稳定性一般', category: 'cn' },
  { slug: 'bt1207', cnName: 'BT1207', enName: 'BT1207', aliases: ['bt1207搜索'], desc: 'BT资源搜索站，采用 AJAX 架构，域名经常变动', category: 'cn' },
  { slug: 'cilisousou', cnName: '磁力搜搜', enName: '0Magnet', aliases: ['ØMagnet','0cili','0magnet','无极磁链'], desc: '多域名磁力搜索引擎，拥有多个镜像站点', category: 'cn' },
  { slug: 'cilihai', cnName: '磁力海', enName: 'CiliHai', aliases: ['磁力海搜索'], desc: '磁力资源搜索平台', category: 'cn' },
  { slug: 'cilishu', cnName: '磁力树', enName: 'CiliShu', aliases: ['磁力树搜索'], desc: '磁力资源搜索引擎', category: 'cn' },
  { slug: 'ciliwang', cnName: '磁力王', enName: 'CiliWang', aliases: ['磁力王搜索'], desc: '磁力资源搜索站点', category: 'cn' },
  { slug: 'cilihezi', cnName: '磁力盒子', enName: 'CiliHeZi', aliases: ['磁力盒子搜索'], desc: '磁力搜索工具站', category: 'cn' },
  { slug: 'ciliduo', cnName: '磁力多', enName: 'CiliDuo', aliases: ['磁力多搜索'], desc: '磁力搜索站，多个镜像域名', category: 'cn' },
  { slug: 'cilipa', cnName: '磁力爬', enName: 'CiliPa', aliases: ['磁力爬搜索','btsao'], desc: '磁力资源搜索引擎，域名不稳定', category: 'cn' },
  { slug: 'ciliguanjia', cnName: '磁力管家', enName: 'CiliGuanJia', aliases: ['磁力管家搜索'], desc: '磁力资源管理和搜索工具', category: 'cn' },
  { slug: 'u3c3', cnName: 'U3C3', enName: 'U3C3', aliases: ['u3c3搜索','u3c3.com'], desc: '磁力搜索引擎，支持多种资源类型', category: 'both' },
  { slug: 'kuaimasousuo', cnName: '快马搜索', enName: 'KuaiMa', aliases: ['快马搜索'], desc: '磁力资源快速搜索平台', category: 'cn' },
  { slug: 'btsousuo', cnName: 'BT搜索', enName: 'BTSearch', aliases: ['BT搜索引擎','BTSearch'], desc: 'BT和磁力资源综合搜索平台', category: 'cn' },
  { slug: 'cilisoushenqi', cnName: '磁力搜索神器', enName: 'CiliSearchTool', aliases: ['磁力搜索神器App'], desc: '磁力资源搜索工具', category: 'cn' },
  { slug: '91bt', cnName: '91BT', enName: '91BT', aliases: ['91bt搜索'], desc: 'BT资源搜索站', category: 'cn' },
  { slug: 'btdianyingtiantang', cnName: 'BT电影天堂', enName: 'BTMovieHeaven', aliases: ['BT电影天堂搜索'], desc: 'BT电影资源搜索和下载平台', category: 'cn' },
  
  // ── 国际知名站点 ──
  { slug: 'piratebay', cnName: '海盗湾', enName: 'The Pirate Bay', aliases: ['TPB','Pirate Bay','thepiratebay','海盗湾搜索'], desc: 'The Pirate Bay is the world\'s most well-known torrent site, famous for its resilience and massive content library spanning movies, music, software, and more', category: 'intl' },
  { slug: 'nyaa', cnName: 'Nyaa', enName: 'Nyaa', aliases: ['nyaa.si','Nyaa Torrents','nyaa搜索'], desc: 'Nyaa is the largest public torrent tracker for anime, manga, and East Asian media content, beloved by the anime community worldwide', category: 'intl' },
  { slug: '1337x', cnName: '1337x', enName: '1337x', aliases: ['1337x.to','1337x搜索'], desc: '1337x is a popular torrent directory providing verified torrents for movies, TV shows, music, games and software with a clean interface', category: 'intl' },
  { slug: 'torrentkitty', cnName: 'TorrentKitty', enName: 'TorrentKitty', aliases: ['TorrentKitty搜索','种子猫'], desc: 'TorrentKitty is a torrent search engine that converts magnet links and provides torrent file information', category: 'intl' },
  { slug: 'knaben', cnName: 'Knaben', enName: 'Knaben', aliases: ['knaben.org','Knaben Database'], desc: 'Knaben is a torrent meta-search engine that aggregates results from multiple sources, offering up to 100 results per page', category: 'intl' },
  { slug: 'magnetdl', cnName: 'MagnetDL', enName: 'MagnetDL', aliases: ['magnetdl.com'], desc: 'MagnetDL is a magnet link search engine providing direct magnet links for movies, TV shows, music, games, and software', category: 'intl' },
  { slug: 'yts', cnName: 'YTS', enName: 'YTS', aliases: ['yts.mx','YIFY','YTS Movies'], desc: 'YTS (YIFY Torrents) is famous for providing high-quality movie torrents in small file sizes, perfect for users with limited bandwidth', category: 'intl' },
  { slug: 'rutor', cnName: 'Rutor', enName: 'Rutor', aliases: ['rutor.info','rutor.is'], desc: 'Rutor is one of the largest Russian torrent trackers, offering a vast library of content popular in Russian-speaking countries', category: 'intl' },
  { slug: 'rarbg', cnName: 'RARBG', enName: 'RARBG', aliases: ['rarbg.to','rarbggo.to'], desc: 'RARBG was one of the most popular torrent sites known for high-quality releases. Clone sites continue to operate after the original shut down', category: 'intl' },
  { slug: 'bt4g', cnName: 'BT4G', enName: 'BT4G', aliases: ['bt4g.org','bt4gprx.com'], desc: 'BT4G is a BitTorrent search engine that provides magnet links sourced from DHT network', category: 'intl' },
  { slug: 'btdig', cnName: 'BTDigg', enName: 'BTDigg', aliases: ['btdig.com','btdigg'], desc: 'BTDigg is a DHT-based BitTorrent search engine that indexes torrents from the distributed hash table network', category: 'intl' },
  { slug: 'animetosho', cnName: 'AnimeTosho', enName: 'Anime Tosho', aliases: ['animetosho.org','动漫图书馆'], desc: 'Anime Tosho is a free, completely automated anime torrent mirror, providing anime torrents and NZB files', category: 'intl' },
  
  // ── ACG 专区 ──
  { slug: 'dongmanhuayuan', cnName: '動漫花園', enName: 'DMHY', aliases: ['动漫花园','dmhy.org','share.dmhy.org'], desc: '動漫花園是华语区最大的动漫BT资源分享平台，提供动画、漫画、音乐、游戏等ACG资源', category: 'cn' },
  { slug: 'mikanani', cnName: '蜜柑计划', enName: 'Mikanani', aliases: ['mikanani.me','蜜柑动漫'], desc: '蜜柑计划是新番动画自动追踪和BT下载平台，支持订阅新番自动推送', category: 'cn' },
  { slug: 'acgrip', cnName: 'ACG.rip', enName: 'ACG.rip', aliases: ['acg.rip'], desc: 'ACG.rip 是专注二次元资源的 BT 站点，提供动画、漫画、游戏、音声等资源', category: 'both' },
];

// ─── 页面变体模板 ─────────────────────────────────────────────────────
// 每个品牌生成以下变体页面
const VARIANTS = [
  { suffix: 'alternative', titleZh: '{brand}替代方案', titleEn: '{brand} Alternative', descZh: '{brand}打不开？最佳替代方案推荐', descEn: 'Best {brand} alternative in 2026' },
  { suffix: 'down', titleZh: '{brand}打不开了', titleEn: '{brand} Not Working', descZh: '{brand}无法访问？原因分析和解决方案', descEn: '{brand} down? Here\'s what to do' },
  { suffix: 'latest', titleZh: '{brand}最新地址2026', titleEn: '{brand} Latest 2026', descZh: '{brand}最新网址和可用镜像', descEn: '{brand} latest working site 2026' },
];

// ─── 输出目录 ────────────────────────────────────────────────────────
const OUT_DIR = path.join(__dirname, '..', 'magnetgoogo-site', 'alt');
const SITE_DIR = path.join(__dirname, '..', 'magnetgoogo-site');

// ─── HTML 生成 ────────────────────────────────────────────────────────

function generatePage(brand, variant) {
  const { slug, cnName, enName, aliases, desc, category } = brand;
  const { suffix, titleZh, titleEn, descZh, descEn } = variant;

  const isIntl = category === 'intl';
  const displayName = isIntl ? enName : cnName;
  const pageTitle = titleZh.replace(/{brand}/g, displayName);
  const pageDesc = descZh.replace(/{brand}/g, displayName);
  const pageTitleEn = titleEn.replace(/{brand}/g, enName);
  const pageDescEn = descEn.replace(/{brand}/g, enName);
  const fullTitle = `${pageTitle}【2026最新】— 磁力古哥`;
  const metaDesc = `${pageDesc}。磁力古哥(Magnet Googo)聚合全网磁力资源，一次搜索全部直达，免费无广告。`;

  const aliasText = aliases.length > 0 ? aliases.join('、') : displayName;

  // 根据变体生成不同的主体内容
  let mainContent = '';
  if (suffix === 'alternative') {
    mainContent = generateAlternativeContent(brand, displayName);
  } else if (suffix === 'down') {
    mainContent = generateDownContent(brand, displayName);
  } else if (suffix === 'latest') {
    mainContent = generateLatestContent(brand, displayName);
  }

  // 英文内容区块（国际站 + both 类别）
  let enSection = '';
  if (category === 'intl' || category === 'both') {
    enSection = generateEnglishSection(brand, variant);
  }

  const filename = `${slug}-${suffix}.html`;

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${fullTitle}</title>
    <meta name="description" content="${metaDesc}">
    <meta name="keywords" content="${displayName},${displayName}打不开,${displayName}替代,${displayName}最新地址,${displayName}2026,磁力搜索,磁力古哥,Magnet Googo,${aliasText}">
    <link rel="canonical" href="https://magnetgoogo.com/alt/${filename}">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="${fullTitle}">
    <meta property="og:description" content="${metaDesc}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="https://magnetgoogo.com/alt/${filename}">
    <meta property="og:image" content="https://magnetgoogo.com/images/app-icon-lg.png">
    <meta property="og:site_name" content="磁力古哥 Magnet Googo">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="${fullTitle}">
    <meta name="twitter:description" content="${metaDesc}">
    <link rel="icon" type="image/png" href="../images/app-icon.png">
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Article",
      "headline": "${pageTitle}",
      "description": "${metaDesc}",
      "author": {"@type": "Organization", "name": "磁力古哥 Magnet Googo"},
      "publisher": {"@type": "Organization", "name": "磁力古哥 Magnet Googo", "logo": {"@type": "ImageObject", "url": "https://magnetgoogo.com/images/app-icon-lg.png"}},
      "datePublished": "2026-05-11",
      "dateModified": "${new Date().toISOString().slice(0, 10)}"
    }
    </script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config={theme:{extend:{colors:{brand:'#4285F4'}}}}</script>
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; }
      .grad-btn { background: linear-gradient(135deg, #4285F4, #34A853); transition: transform .2s, box-shadow .2s; }
      .grad-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(66,133,244,.35); }
      /* Typography spacing for article content */
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
    <a href="https://api.naoshiquan.com/download/v0.1.8/MagGoogo-v0.1.8.apk" class="grad-btn text-white text-sm font-medium px-4 py-2 rounded-full inline-flex items-center gap-1.5">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
      免费下载
    </a>
  </div>
</nav>

<!-- BREADCRUMB -->
<div class="max-w-4xl mx-auto px-6 py-3 text-sm text-gray-400">
  <a href="../" class="hover:text-brand">首页</a> &gt; <a href="./" class="hover:text-brand">磁力站替代</a> &gt; <span class="text-gray-600">${pageTitle}</span>
</div>

<!-- MAIN -->
<main class="max-w-4xl mx-auto px-6 pb-16">

  <!-- HERO -->
  <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 md:p-12 mb-8">
    <h1 class="text-2xl md:text-3xl font-bold mb-4 text-gray-900">${pageTitle}</h1>
    <p class="text-lg text-gray-500 mb-6">${pageDesc}</p>
    <div class="flex flex-col sm:flex-row gap-3">
      <a href="https://api.naoshiquan.com/download/v0.1.8/MagGoogo-v0.1.8.apk" class="grad-btn text-white font-semibold px-8 py-3 rounded-full text-center inline-flex items-center justify-center gap-2">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
        免费下载磁力古哥
      </a>
      <a href="https://wwbdy.lanzoue.com/iFHEh3oomsjg" target="_blank" class="border border-gray-200 text-gray-600 font-medium px-8 py-3 rounded-full text-center hover:border-brand hover:text-brand transition-colors">
        备用下载（蓝奏云）
      </a>
    </div>
  </div>

  <!-- ARTICLE CONTENT -->
  <article class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 md:p-12 mb-8 prose prose-gray max-w-none">
    ${mainContent}
    ${enSection}
  </article>

  <!-- CTA -->
  <div class="bg-gradient-to-r from-blue-500 to-green-500 rounded-2xl p-8 md:p-12 text-center text-white">
    <h2 class="text-2xl font-bold mb-3">告别找地址的烦恼</h2>
    <p class="text-blue-100 mb-6">下载磁力古哥，聚合全网磁力资源，一次搜索全部直达</p>
    <a href="https://api.naoshiquan.com/download/v0.1.8/MagGoogo-v0.1.8.apk" class="bg-white text-brand font-semibold px-8 py-3 rounded-full inline-flex items-center gap-2 hover:shadow-lg transition-shadow">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
      立即下载（免费）
    </a>
    <p class="text-sm text-blue-100 mt-3">Android · 无需注册 · 无广告</p>
  </div>

  <!-- RELATED -->
  <div class="mt-8 bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
    <h3 class="font-bold text-lg mb-4">相关推荐</h3>
    <div class="grid grid-cols-2 md:grid-cols-3 gap-3" id="related-links"></div>
  </div>

</main>

<!-- FOOTER -->
<footer class="border-t border-gray-100 bg-white py-8">
  <div class="max-w-4xl mx-auto px-6 text-center text-sm text-gray-400">
    <p class="mb-2">&copy; 2026 <a href="../" class="text-brand hover:underline">磁力古哥 Magnet Googo</a>。版权所有。</p>
    <p>免责声明：磁力古哥是一款搜索工具，不存储任何资源内容。搜索结果来自公开互联网，使用者应遵守当地法律法规。</p>
    <div class="mt-3 flex justify-center gap-4">
      <a href="../privacy.html" class="hover:text-gray-600">隐私政策</a>
      <a href="../terms.html" class="hover:text-gray-600">用户协议</a>
      <a href="../faq.html" class="hover:text-gray-600">常见问题</a>
    </div>
  </div>
</footer>

</body>
</html>`;

  return { filename, html };
}

// ─── 内容生成函数 ──────────────────────────────────────────────────────

function generateAlternativeContent(brand, displayName) {
  return `
    <h2 class="text-xl font-bold mt-0">${displayName}是什么？</h2>
    <p>${displayName}是一个磁力链接搜索引擎。${brand.desc}。</p>
    <p>然而，像${displayName}这样的磁力搜索站经常面临域名更换、服务器不稳定、被防火墙屏蔽等问题。很多用户经常遇到<strong>${displayName}打不开</strong>、<strong>${displayName}无法访问</strong>的情况，不得不反复寻找最新地址。</p>

    <h2 class="text-xl font-bold">为什么需要${displayName}的替代方案？</h2>
    <ul>
      <li><strong>域名频繁更换</strong> — ${displayName}的域名经常变动，旧地址失效后需要重新寻找</li>
      <li><strong>服务不稳定</strong> — 服务器宕机、维护等原因导致经常无法访问</li>
      <li><strong>网络屏蔽</strong> — 部分地区可能无法直接访问</li>
      <li><strong>广告干扰</strong> — 许多磁力站充斥弹窗广告，影响使用体验</li>
      <li><strong>资源有限</strong> — 单个站点的资源库总是有限的</li>
    </ul>

    <h2 class="text-xl font-bold">终极解决方案：磁力古哥（Magnet Googo）</h2>
    <p>与其不断寻找${displayName}的最新地址，不如使用<strong>磁力古哥</strong>——一款聚合全网磁力资源的免费搜索App。</p>
    <p>磁力古哥的工作原理是将多个磁力资源站整合到一起。即使某个站点挂了，其他站点仍然可以提供结果。<strong>一次搜索，全网直达。</strong></p>
    
    <h3 class="text-lg font-bold">磁力古哥 vs 单独使用${displayName}</h3>
    <table class="w-full border-collapse border border-gray-200 my-4">
      <thead><tr class="bg-gray-50">
        <th class="border border-gray-200 px-4 py-2 text-left">对比项</th>
        <th class="border border-gray-200 px-4 py-2 text-left">${displayName}</th>
        <th class="border border-gray-200 px-4 py-2 text-left">磁力古哥</th>
      </tr></thead>
      <tbody>
        <tr><td class="border border-gray-200 px-4 py-2">资源覆盖</td><td class="border border-gray-200 px-4 py-2">单站资源</td><td class="border border-gray-200 px-4 py-2 text-green-600 font-medium">聚合全网资源</td></tr>
        <tr><td class="border border-gray-200 px-4 py-2">稳定性</td><td class="border border-gray-200 px-4 py-2">域名经常更换</td><td class="border border-gray-200 px-4 py-2 text-green-600 font-medium">多源冗余，永远可用</td></tr>
        <tr><td class="border border-gray-200 px-4 py-2">广告</td><td class="border border-gray-200 px-4 py-2">有弹窗广告</td><td class="border border-gray-200 px-4 py-2 text-green-600 font-medium">零广告</td></tr>
        <tr><td class="border border-gray-200 px-4 py-2">需要找地址</td><td class="border border-gray-200 px-4 py-2">每次都要找</td><td class="border border-gray-200 px-4 py-2 text-green-600 font-medium">下载一次，永久使用</td></tr>
        <tr><td class="border border-gray-200 px-4 py-2">价格</td><td class="border border-gray-200 px-4 py-2">免费</td><td class="border border-gray-200 px-4 py-2 text-green-600 font-medium">免费</td></tr>
      </tbody>
    </table>

    <h2 class="text-xl font-bold">如何使用磁力古哥？</h2>
    <ol>
      <li><strong>下载安装</strong> — 点击本页下载按钮，下载 APK 安装包</li>
      <li><strong>打开搜索</strong> — 在搜索框输入你想找的资源名称</li>
      <li><strong>获取结果</strong> — 磁力古哥自动从全网搜索，秒级返回结果</li>
      <li><strong>复制链接</strong> — 点击结果即可复制磁力链接，粘贴到下载工具中使用</li>
    </ol>

    <h2 class="text-xl font-bold">常见问题</h2>
    <h3 class="text-base font-bold">${displayName}还能用吗？</h3>
    <p>${displayName}的可用性取决于其当前域名状态。由于磁力站域名经常更换，建议使用磁力古哥作为稳定的替代方案。</p>
    <h3 class="text-base font-bold">磁力古哥安全吗？</h3>
    <p>磁力古哥是纯搜索工具，不存储任何资源内容，不收集个人信息，完全免费无广告。</p>
    <h3 class="text-base font-bold">支持哪些平台？</h3>
    <p>目前支持 Android 7.0 及以上版本。iOS 版本正在开发中。</p>
  `;
}

function generateDownContent(brand, displayName) {
  return `
    <h2 class="text-xl font-bold mt-0">${displayName}打不开了怎么办？</h2>
    <p>如果你发现<strong>${displayName}无法访问</strong>，不用慌。这是磁力搜索站的常见问题。以下是${displayName}打不开的常见原因和解决方案。</p>

    <h2 class="text-xl font-bold">${displayName}打不开的常见原因</h2>
    <ol>
      <li><strong>域名更换</strong> — ${displayName}可能已经更换了新域名。${brand.desc}。磁力站经常需要更换域名以维持运营。</li>
      <li><strong>服务器维护</strong> — 临时的服务器维护或故障可能导致短暂无法访问。</li>
      <li><strong>网络屏蔽</strong> — 部分网络环境可能屏蔽了${displayName}的域名。</li>
      <li><strong>DNS 污染</strong> — 域名解析被污染，导致无法正确连接到服务器。</li>
      <li><strong>永久关站</strong> — 极端情况下，站点可能已经永久关闭。</li>
    </ol>

    <h2 class="text-xl font-bold">临时解决方案</h2>
    <ul>
      <li><strong>尝试镜像站</strong> — 搜索"${displayName}镜像"或"${displayName}最新地址"</li>
      <li><strong>更换 DNS</strong> — 尝试使用 8.8.8.8 或 114.114.114.114</li>
      <li><strong>等待恢复</strong> — 如果是临时维护，通常几小时后会恢复</li>
    </ul>

    <h2 class="text-xl font-bold">一劳永逸的解决方案：磁力古哥</h2>
    <p>每次找地址太麻烦了。<strong>磁力古哥</strong>是一款聚合全网磁力资源的免费 Android App，它把包括${displayName}在内的众多磁力站整合到一起。</p>
    <p><strong>一个站挂了，还有其他站顶上。一次搜索，全网直达。再也不用找地址了。</strong></p>
    
    <div class="bg-blue-50 border border-blue-100 rounded-xl p-6 my-6">
      <h3 class="text-lg font-bold text-blue-900 mb-2">为什么磁力古哥是最好的选择？</h3>
      <ul class="text-blue-800 space-y-1">
        <li>✅ 聚合全网磁力资源，不依赖单一站点</li>
        <li>✅ 免费、无广告、无需注册</li>
        <li>✅ 秒级搜索响应</li>
        <li>✅ 支持收藏、历史记录</li>
        <li>✅ 一次下载，永久使用，告别找地址</li>
      </ul>
    </div>

    <h2 class="text-xl font-bold">常见问题</h2>
    <h3 class="text-base font-bold">${displayName}是不是彻底关了？</h3>
    <p>磁力站的运营状态随时可能变化。即使${displayName}关闭，磁力古哥仍能通过其他来源为你提供搜索结果。</p>
    <h3 class="text-base font-bold">磁力古哥包含${displayName}的资源吗？</h3>
    <p>磁力古哥聚合全网磁力资源站的搜索结果，覆盖面远超任何单一站点。</p>
  `;
}

function generateLatestContent(brand, displayName) {
  return `
    <h2 class="text-xl font-bold mt-0">${displayName}最新地址（2026年更新）</h2>
    <p>很多用户在搜索<strong>"${displayName}最新地址"</strong>、<strong>"${displayName}2026"</strong>、<strong>"${displayName}新网址"</strong>。这是因为磁力搜索站的域名经常更换。${brand.desc}。</p>

    <h2 class="text-xl font-bold">为什么${displayName}要不断换地址？</h2>
    <p>磁力搜索站更换域名主要有以下原因：</p>
    <ul>
      <li><strong>域名被封</strong> — 被 DNS 污染或域名注册商停止解析</li>
      <li><strong>服务器被封</strong> — IP 地址被屏蔽</li>
      <li><strong>版权投诉</strong> — 收到 DMCA 等版权通知</li>
      <li><strong>域名过期</strong> — 旧域名到期未续费</li>
    </ul>
    <p>这意味着你每隔一段时间就要重新寻找${displayName}的可用地址。<strong>这很烦人。</strong></p>

    <h2 class="text-xl font-bold">不再需要找地址的方案</h2>
    <p>与其每次都找${displayName}的最新地址，不如换一种思路：使用<strong>磁力古哥</strong>。</p>
    <p>磁力古哥是一款 Android App，它聚合了全网磁力资源站。<strong>一次搜索覆盖所有站点</strong>，即使某个站点域名变了或者挂了，也不影响你的搜索结果。</p>
    
    <div class="bg-green-50 border border-green-100 rounded-xl p-6 my-6">
      <h3 class="text-lg font-bold text-green-900 mb-2">磁力古哥的优势</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-green-800">
        <div>🔍 <strong>全网搜索</strong> — 一次搜索覆盖所有磁力站</div>
        <div>🛡️ <strong>永远可用</strong> — 多源冗余，不怕单站失效</div>
        <div>🚫 <strong>零广告</strong> — 纯净搜索体验</div>
        <div>⚡ <strong>秒级响应</strong> — 极速返回搜索结果</div>
        <div>📱 <strong>Android App</strong> — 手机直接使用</div>
        <div>💰 <strong>完全免费</strong> — 无需注册或付费</div>
      </div>
    </div>

    <h2 class="text-xl font-bold">如何获取磁力古哥？</h2>
    <ol>
      <li>点击本页的<strong>"免费下载"</strong>按钮下载 APK</li>
      <li>安装后打开 App</li>
      <li>搜索任何你想找的资源</li>
      <li>从此告别找地址的烦恼</li>
    </ol>

    <h2 class="text-xl font-bold">常见问题</h2>
    <h3 class="text-base font-bold">磁力古哥是${displayName}的官方 App 吗？</h3>
    <p>不是。磁力古哥是独立的磁力搜索聚合工具，不隶属于任何磁力站。它聚合全网资源，为用户提供一站式搜索体验。</p>
    <h3 class="text-base font-bold">磁力古哥需要翻墙吗？</h3>
    <p>磁力古哥的大部分搜索源可在国内直接使用，无需翻墙。部分国际源可能需要网络代理。</p>
  `;
}

function generateEnglishSection(brand, variant) {
  const { enName, desc } = brand;
  const { suffix } = variant;

  let content = '';
  if (suffix === 'alternative') {
    content = `
    <h2 class="text-xl font-bold">Looking for a ${enName} Alternative?</h2>
    <p>${desc}.</p>
    <p>If you're looking for a reliable alternative to ${enName}, <strong>Magnet Googo</strong> is a free Android app that aggregates magnet links from across the entire web. Instead of relying on a single torrent site that may go down at any time, Magnet Googo searches multiple sources simultaneously.</p>
    <ul>
      <li><strong>All-in-one search</strong> — Search across dozens of magnet sources at once</li>
      <li><strong>Always available</strong> — If one source is down, others still provide results</li>
      <li><strong>Free &amp; ad-free</strong> — No ads, no registration, no tracking</li>
      <li><strong>Fast results</strong> — Results appear in seconds</li>
    </ul>
    <p>Download Magnet Googo for free at <a href="https://magnetgoogo.com" class="text-brand hover:underline">magnetgoogo.com</a></p>`;
  } else if (suffix === 'down') {
    content = `
    <h2 class="text-xl font-bold">${enName} Not Working? Here's What To Do</h2>
    <p>${desc}.</p>
    <p>If ${enName} is down or not accessible, it could be due to domain changes, server issues, or network restrictions. Instead of constantly searching for the latest ${enName} URL, try <strong>Magnet Googo</strong> — a free Android app that aggregates magnet search results from multiple sources.</p>
    <p>With Magnet Googo, you'll never need to hunt for working torrent site URLs again. One search covers everything. Download free at <a href="https://magnetgoogo.com" class="text-brand hover:underline">magnetgoogo.com</a></p>`;
  } else if (suffix === 'latest') {
    content = `
    <h2 class="text-xl font-bold">${enName} Latest Working Site (2026)</h2>
    <p>${desc}.</p>
    <p>Tired of searching for the latest ${enName} URL every few weeks? <strong>Magnet Googo</strong> eliminates this problem entirely. It's a free Android app that aggregates magnet search results from dozens of sources — including ${enName} when it's available, plus many alternatives.</p>
    <p>Stop chasing URLs. Download Magnet Googo once and search forever. Free at <a href="https://magnetgoogo.com" class="text-brand hover:underline">magnetgoogo.com</a></p>`;
  }

  return `
    <hr class="my-8 border-gray-200">
    <div class="text-gray-600">
      ${content}
    </div>`;
}

// ─── 索引页生成 ────────────────────────────────────────────────────────

function generateIndexPage(allPages) {
  const rows = allPages.map(p => 
    `<li class="py-2 border-b border-gray-50"><a href="${p.filename}" class="text-brand hover:underline">${p.title}</a></li>`
  ).join('\n      ');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>磁力站替代方案大全 — 磁力古哥 Magnet Googo</title>
    <meta name="description" content="全网磁力搜索站替代方案汇总。磁力猫、BTSOW、种子吧、海盗湾等打不开？磁力古哥聚合全网磁力资源，一次搜索全部直达。">
    <meta name="keywords" content="磁力站替代,磁力搜索替代方案,磁力猫替代,BTSOW替代,磁力古哥,Magnet Googo">
    <link rel="canonical" href="https://magnetgoogo.com/alt/">
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
  <h1 class="text-3xl font-bold mb-2">磁力站替代方案大全</h1>
  <p class="text-gray-500 mb-8">全网磁力搜索站打不开？磁力古哥聚合全网资源，一次搜索全部直达。</p>
  <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
    <ul class="space-y-0">
      ${rows}
    </ul>
  </div>
  <div class="mt-8 text-center">
    <a href="https://api.naoshiquan.com/download/v0.1.8/MagGoogo-v0.1.8.apk" class="bg-brand text-white font-semibold px-8 py-3 rounded-full inline-block">免费下载磁力古哥</a>
  </div>
</main>
<footer class="border-t border-gray-100 py-6 text-center text-sm text-gray-400">
  <p>&copy; 2026 <a href="../" class="text-brand">磁力古哥</a>。免责声明：磁力古哥是搜索工具，不存储任何资源内容。</p>
</footer>
</body>
</html>`;
}

// ─── sitemap 更新 ─────────────────────────────────────────────────────

function generateSitemapEntries(allPages) {
  return allPages.map(p => 
    `  <url><loc>https://magnetgoogo.com/alt/${p.filename}</loc><lastmod>${new Date().toISOString().slice(0,10)}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>`
  ).join('\n');
}

// ─── MAIN ────────────────────────────────────────────────────────────

function main() {
  // Ensure output directory
  if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
  }

  const allPages = [];
  let count = 0;

  for (const brand of BRANDS) {
    for (const variant of VARIANTS) {
      const { filename, html } = generatePage(brand, variant);
      const displayName = brand.category === 'intl' ? brand.enName : brand.cnName;
      const title = variant.titleZh.replace(/{brand}/g, displayName);
      
      fs.writeFileSync(path.join(OUT_DIR, filename), html, 'utf-8');
      allPages.push({ filename, title, brand: displayName });
      count++;
    }
  }

  // Generate index page
  const indexHtml = generateIndexPage(allPages);
  fs.writeFileSync(path.join(OUT_DIR, 'index.html'), indexHtml, 'utf-8');
  count++;

  // Update main sitemap
  const sitemapPath = path.join(SITE_DIR, 'sitemap.xml');
  const sitemapEntries = generateSitemapEntries(allPages);
  const indexEntry = `  <url><loc>https://magnetgoogo.com/alt/</loc><lastmod>${new Date().toISOString().slice(0,10)}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>`;
  
  if (fs.existsSync(sitemapPath)) {
    let sitemap = fs.readFileSync(sitemapPath, 'utf-8');
    // Remove old alt entries if any
    sitemap = sitemap.replace(/\n.*magnetgoogo\.com\/alt\/.*\n?/g, '\n');
    // Insert before </urlset>
    sitemap = sitemap.replace('</urlset>', `${indexEntry}\n${sitemapEntries}\n</urlset>`);
    fs.writeFileSync(sitemapPath, sitemap, 'utf-8');
    console.log('✅ Updated sitemap.xml');
  }

  console.log(`\n🚀 Generated ${count} pages in ${OUT_DIR}`);
  console.log(`   - ${BRANDS.length} brands × ${VARIANTS.length} variants = ${BRANDS.length * VARIANTS.length} landing pages`);
  console.log(`   - 1 index page`);
  console.log(`\nBrand breakdown:`);
  const cnCount = BRANDS.filter(b => b.category === 'cn').length;
  const intlCount = BRANDS.filter(b => b.category === 'intl').length;
  const bothCount = BRANDS.filter(b => b.category === 'both').length;
  console.log(`   - Chinese: ${cnCount}, International: ${intlCount}, Both: ${bothCount}`);
  console.log(`   - Pages with English content: ${(intlCount + bothCount) * VARIANTS.length}`);
}

main();
