import type { Lang } from './i18n';

export interface ResourceCopy {
  tabSearch: string;
  tabResources: string;
  tabSettings: string;
  title: string;
  recommendedTitle: string;
  latestTitle: string;
  loading: string;
  emptyTitle: string;
  emptyBody: string;
  retry: string;
  minutes: (value: number) => string;
  rating: (value: number) => string;
  resourceCount: (value: number) => string;
  viewResources: (value: number) => string;
  recommendation: string;
  detailSynopsis: string;
  detailInfo: string;
  detailCast: string;
  detailResources: string;
  detailDirector: string;
  detailActors: string;
  detailCountry: string;
  detailLanguage: string;
  detailRelease: string;
  searchMore: string;
  openResource: string;
  cloudResourceHint: string;
  extractionCode: string;
  extractionCodeCopied: string;
  magnetCopied: string;
  movieNotFound: string;
  back: string;
  openFailed: string;
  providerMagnet: string;
  providerXunlei: string;
  providerQuark: string;
  providerBaidu: string;
}

const EN: ResourceCopy = {
  tabSearch: 'Search',
  tabResources: 'Movies',
  tabSettings: 'Settings',
  title: 'Movies',
  recommendedTitle: 'Recommended',
  latestTitle: 'Recently added',
  loading: 'Loading movies…',
  emptyTitle: 'No movies available',
  emptyBody: 'The movie snapshot is unavailable. Rebuild the App bundle and try again.',
  retry: 'Retry',
  minutes: (value) => `${value} min`,
  rating: (value) => `${value.toFixed(1)}`,
  resourceCount: (value) => `${value} links`,
  viewResources: (value) => `View resources (${value})`,
  recommendation: 'Pick',
  detailSynopsis: 'Story',
  detailInfo: 'Details',
  detailCast: 'Cast & crew',
  detailResources: 'Resources',
  detailDirector: 'Director',
  detailActors: 'Cast',
  detailCountry: 'Country',
  detailLanguage: 'Language',
  detailRelease: 'Release',
  searchMore: 'Search for more',
  openResource: 'Open',
  cloudResourceHint: 'Cloud storage link',
  extractionCode: 'Access code',
  extractionCodeCopied: 'Access code copied',
  magnetCopied: 'Magnet link copied',
  movieNotFound: 'Movie not found',
  back: 'Back',
  openFailed: 'Unable to open this link',
  providerMagnet: 'Magnet',
  providerXunlei: 'Xunlei',
  providerQuark: 'Quark',
  providerBaidu: 'Baidu Netdisk',
};

const ZH: ResourceCopy = {
  tabSearch: '搜索',
  tabResources: '资源',
  tabSettings: '设置',
  title: '影视',
  recommendedTitle: '值得一看',
  latestTitle: '最近更新',
  loading: '正在加载影视…',
  emptyTitle: '暂无影视内容',
  emptyBody: '本地影视数据未准备完成，请重新构建 App 后再试。',
  retry: '重新加载',
  minutes: (value) => `${value} 分钟`,
  rating: (value) => `${value.toFixed(1)}`,
  resourceCount: (value) => `${value} 个资源`,
  viewResources: (value) => `查看资源（${value}）`,
  recommendation: '推荐',
  detailSynopsis: '剧情简介',
  detailInfo: '影片信息',
  detailCast: '主创阵容',
  detailResources: '资源',
  detailDirector: '导演',
  detailActors: '主演',
  detailCountry: '国家地区',
  detailLanguage: '语言',
  detailRelease: '上映',
  searchMore: '搜索更多资源',
  openResource: '打开',
  cloudResourceHint: '点击打开云盘资源',
  extractionCode: '提取码',
  extractionCodeCopied: '提取码已复制',
  magnetCopied: '磁力链接已复制',
  movieNotFound: '影片不存在',
  back: '返回',
  openFailed: '无法打开该链接',
  providerMagnet: '磁力',
  providerXunlei: '迅雷',
  providerQuark: '夸克',
  providerBaidu: '百度网盘',
};

const COPY: Record<Lang, ResourceCopy> = {
  zh: ZH,
  en: EN,
  es: { ...EN, tabSearch: 'Buscar', tabResources: 'Películas', tabSettings: 'Ajustes' },
  ru: { ...EN, tabSearch: 'Поиск', tabResources: 'Фильмы', tabSettings: 'Настройки' },
  pt: { ...EN, tabSearch: 'Buscar', tabResources: 'Filmes', tabSettings: 'Configurações' },
  ja: { ...EN, tabSearch: '検索', tabResources: '映画', tabSettings: '設定' },
  ko: { ...EN, tabSearch: '검색', tabResources: '영화', tabSettings: '설정' },
  fr: { ...EN, tabSearch: 'Recherche', tabResources: 'Films', tabSettings: 'Réglages' },
  de: { ...EN, tabSearch: 'Suche', tabResources: 'Filme', tabSettings: 'Einstellungen' },
  ar: { ...EN, tabSearch: 'بحث', tabResources: 'أفلام', tabSettings: 'الإعدادات' },
};

export function getResourceCopy(lang: Lang): ResourceCopy {
  return COPY[lang] ?? EN;
}
