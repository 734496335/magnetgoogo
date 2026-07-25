import type { Lang } from './i18n';

export interface ResourceCopy {
  tabSearch: string;
  tabResources: string;
  tabSettings: string;
  title: string;
  subtitle: (count: number) => string;
  tapHint: string;
  loading: string;
  emptyTitle: string;
  emptyBody: string;
  retry: string;
  updatedAt: string;
  minutes: (value: number) => string;
  resourceCount: (value: number) => string;
  searchAction: string;
  sourceBundled: string;
  sourceRemote: string;
}

const EN: ResourceCopy = {
  tabSearch: 'Search',
  tabResources: 'Resources',
  tabSettings: 'Settings',
  title: 'Latest Resources',
  subtitle: (count) => `${count} items in source order`,
  tapHint: 'Tap any card to search its code',
  loading: 'Loading latest resources…',
  emptyTitle: 'No resources available',
  emptyBody: 'Refresh later or check the resource feed configuration.',
  retry: 'Retry',
  updatedAt: 'Updated',
  minutes: (value) => `${value} min`,
  resourceCount: (value) => `${value} links`,
  searchAction: 'Search',
  sourceBundled: 'Built-in snapshot',
  sourceRemote: 'Live feed',
};

const COPY: Record<Lang, ResourceCopy> = {
  zh: {
    tabSearch: '搜索',
    tabResources: '资源',
    tabSettings: '设置',
    title: '最新资源',
    subtitle: (count) => `按来源顺序展示最新 ${count} 条`,
    tapHint: '点击任意卡片，直接搜索对应番号',
    loading: '正在加载最新资源…',
    emptyTitle: '暂时没有可展示的资源',
    emptyBody: '请稍后刷新，或检查资源 Feed 配置。',
    retry: '重新加载',
    updatedAt: '更新于',
    minutes: (value) => `${value} 分钟`,
    resourceCount: (value) => `${value} 个磁力`,
    searchAction: '搜索',
    sourceBundled: '内置快照',
    sourceRemote: '在线数据',
  },
  en: EN,
  es: { ...EN, tabSearch: 'Buscar', tabResources: 'Recursos', tabSettings: 'Ajustes', title: 'Recursos recientes' },
  ru: { ...EN, tabSearch: 'Поиск', tabResources: 'Ресурсы', tabSettings: 'Настройки', title: 'Новые ресурсы' },
  pt: { ...EN, tabSearch: 'Buscar', tabResources: 'Recursos', tabSettings: 'Configurações', title: 'Recursos recentes' },
  ja: { ...EN, tabSearch: '検索', tabResources: 'リソース', tabSettings: '設定', title: '最新リソース', searchAction: '検索' },
  ko: { ...EN, tabSearch: '검색', tabResources: '리소스', tabSettings: '설정', title: '최신 리소스', searchAction: '검색' },
  fr: { ...EN, tabSearch: 'Recherche', tabResources: 'Ressources', tabSettings: 'Réglages', title: 'Ressources récentes' },
  de: { ...EN, tabSearch: 'Suche', tabResources: 'Ressourcen', tabSettings: 'Einstellungen', title: 'Neueste Ressourcen' },
  ar: { ...EN, tabSearch: 'بحث', tabResources: 'الموارد', tabSettings: 'الإعدادات', title: 'أحدث الموارد', searchAction: 'بحث' },
};

export function getResourceCopy(lang: Lang): ResourceCopy {
  return COPY[lang] ?? EN;
}
