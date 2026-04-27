/**
 * Lightweight i18n — Chinese + English only.
 * No heavy libraries; just a typed dictionary + React context.
 */

export type Lang = 'zh' | 'en';

const zh = {
  // ── Home ──
  slogan: '磁力古哥  最新 | 最全 | 最快',
  searchPlaceholder: '电影、动漫、游戏、找片...',
  searchButton: '搜索磁力',
  emptyQueryToast: '请输入搜索内容',

  // ── Search results ──
  searchingStatus: (sources: number, results: number) =>
    `正在搜索 ${sources} 个源，找到 ${results} 条结果`,
  searchDoneStatus: (sources: number, results: number) =>
    `搜索了 ${sources} 个源，找到 ${results} 条结果`,
  sortRelevance: '相关性',
  sortSize: '大小',
  sortDate: '时间',
  copyMagnet: '复制磁力',
  copied: '已复制',
  openMagnet: '立即打开',
  copyFailed: '复制失败',
  cannotOpen: '无法打开',
  cannotOpenMsg: '未找到支持磁力链接的应用',
  noSourcesHint: '请先在设置中拉取源数据',
  goToSettings: '前往设置',

  // ── Settings ──
  settings: '设置',
  sectionSources: '数据源',
  syncSources: '拉取最新源',
  syncSuccess: (count: number) => `成功获取 ${count} 个源`,
  notSynced: '尚未同步',
  lastSync: '上次同步',
  sectionLanguage: '语言/Language',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: '关于',
  version: '版本',

  // ── Kind labels (Tier 1: content types) ──
  kindMovie: '电影',
  kindTvUs: '美剧',
  kindTvJp: '日剧',
  kindTvKr: '韩剧',
  kindTvCn: '国产剧',
  kindTv: '剧集',
  kindAnime: '动漫',
  kindVariety: '综艺',
  kindDocumentary: '纪录片',
  kindMusic: '音乐',
  kindGame: '游戏',
  kindEbook: '电子书',
  kindManga: '漫画',
  // ── Kind labels (Tier 2: format types) ──
  kindVideo: '视频',
  kindAudio: '音频',
  kindArchive: '压缩包',
  kindImage: '图片',
  kindDocument: '文档',
  kindSoftware: '程序',
  kindOther: '其他',

  sectionTheme: '主题',

  // ── Search UX ──
  lowRelevanceHint: '以下是相关度较低的结果',
  feedbackBtn: '反馈',

  // ── History ──
  historyTitle: '搜索历史',
  historyClear: '清空',

  // ── Favorites ──
  favoritesTitle: '收藏夹',
  favoriteAdded: '已收藏',
  favoriteRemoved: '已取消收藏',
  noFavorites: '暂无收藏',

  // ── Privacy ──
  privacyTitle: '隐私协议与免责声明',

  // ── Misc ──
  fileCount: (n: number) => `文件数 ${n}`,
};

const en: typeof zh = {
  // ── Home ──
  slogan: 'MagnetGoogo — Latest | Fullest | Fastest',
  searchPlaceholder: 'Movies, anime, games, torrents...',
  searchButton: 'Search Magnets',
  emptyQueryToast: 'Please enter a search term',

  // ── Search results ──
  searchingStatus: (sources, results) =>
    `Searching ${sources} sources, found ${results} results`,
  searchDoneStatus: (sources, results) =>
    `Searched ${sources} sources, found ${results} results`,
  sortRelevance: 'Relevance',
  sortSize: 'Size',
  sortDate: 'Date',
  copyMagnet: 'Copy Magnet',
  copied: 'Copied',
  openMagnet: 'Open',
  copyFailed: 'Copy failed',
  cannotOpen: 'Cannot open',
  cannotOpenMsg: 'No app found to handle magnet links',
  noSourcesHint: 'Pull source data in Settings first',
  goToSettings: 'Go to Settings',

  // ── Settings ──
  settings: 'Settings',
  sectionSources: 'Sources',
  syncSources: 'Pull latest sources',
  syncSuccess: (count) => `Fetched ${count} sources`,
  notSynced: 'Not synced',
  lastSync: 'Last sync',
  sectionLanguage: 'Language',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'About',
  version: 'Version',

  // ── Kind labels (Tier 1: content types) ──
  kindMovie: 'Movie',
  kindTvUs: 'US TV',
  kindTvJp: 'JP Drama',
  kindTvKr: 'KR Drama',
  kindTvCn: 'CN Drama',
  kindTv: 'TV Series',
  kindAnime: 'Anime',
  kindVariety: 'Variety',
  kindDocumentary: 'Documentary',
  kindMusic: 'Music',
  kindGame: 'Game',
  kindEbook: 'eBook',
  kindManga: 'Manga',
  // ── Kind labels (Tier 2: format types) ──
  kindVideo: 'Video',
  kindAudio: 'Audio',
  kindArchive: 'Archive',
  kindImage: 'Image',
  kindDocument: 'Document',
  kindSoftware: 'Software',
  kindOther: 'Other',

  sectionTheme: 'Theme',

  // ── Search UX ──
  lowRelevanceHint: 'Results below may be less relevant',
  feedbackBtn: 'Feedback',

  // ── History ──
  historyTitle: 'Search History',
  historyClear: 'Clear',

  // ── Favorites ──
  favoritesTitle: 'Favorites',
  favoriteAdded: 'Added to favorites',
  favoriteRemoved: 'Removed from favorites',
  noFavorites: 'No favorites yet',

  // ── Privacy ──
  privacyTitle: 'Privacy Policy & Disclaimer',

  // ── Misc ──
  fileCount: (n) => `${n} files`,
};

const translations: Record<Lang, typeof zh> = { zh, en };

export type Translations = typeof zh;

export function getTranslations(lang: Lang): Translations {
  return translations[lang];
}
