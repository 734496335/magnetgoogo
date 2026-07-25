/**
 * Lightweight i18n — 10 languages.
 * No heavy libraries; just a typed dictionary + React context.
 */

export type Lang = 'zh' | 'en' | 'es' | 'ru' | 'pt' | 'ja' | 'ko' | 'fr' | 'de' | 'ar';

export const LANG_LABELS: Record<Lang, string> = {
  zh: '中文',
  en: 'English',
  es: 'Español',
  ru: 'Русский',
  pt: 'Português',
  ja: '日本語',
  ko: '한국어',
  fr: 'Français',
  de: 'Deutsch',
  ar: 'العربية',
};

export const ALL_LANGS: Lang[] = ['zh', 'en', 'es', 'ru', 'pt', 'ja', 'ko', 'fr', 'de', 'ar'];

const zh = {
  // ── Home ──
  sloganPrefix: '搜全网磁力，上',
  sloganBrand: '磁力古哥',
  searchPlaceholder: '电影、动漫、游戏、找片...',
  searchButton: '搜索磁力',
  emptyQueryToast: '请输入搜索内容',

  // ── Search results ──
  searchingStatus: (done: number, total: number, results: number) =>
    `搜索 ${done}/${total} 个源，找到 ${results} 条结果`,
  searchDoneStatus: (done: number, total: number, results: number) =>
    `已搜索 ${done}/${total} 个源，找到 ${results} 条结果`,
  sortComprehensive: '综合',
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
  syncSuccess: (_count: number) => `已同步精选磁力源`,
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
  feedbackBtn: '吐槽',

  // ── History ──
  historyTitle: '搜索历史',
  historyClear: '清空',

  // ── Favorites ──
  favoritesTitle: '收藏夹',
  favoriteAdded: '已收藏',
  favoriteRemoved: '已取消收藏',
  noFavorites: '暂无收藏',

  // ── Watchlist ──
  watchlistTitle: '关键词订阅',
  watchSubscribe: '订阅',
  watchSubscribed: '已订阅',
  watchUnsubscribe: '取消订阅',
  noWatchlist: '暂无订阅',
  watchlistHint: '在搜索结果页点击「订阅」，有新结果时会在此提示',
  watchTapToSeeUpdate: '有新结果，点击查看',
  watchLastCount: (n: number) => `上次 ${n} 条结果`,
  watchSubscribedToast: '已订阅此关键词',
  watchUpdateToast: '订阅关键词有新结果',
  homeWatchlist: '我的订阅',
  cancel: '取消',

  // ── Legal ──
  privacyTitle: '隐私政策',
  termsTitle: '用户协议',

  // ── Empty results ──
  noResultsHint: '没有找到相关结果',
  noResultsSuggestion: '试试其他关键词，或检查拼写',

  // ── Compliance mode ──
  complianceBannerLine1: '此版本为合规版，解锁更多搜索源，请到官网了解',
  complianceBannerLink: '前往官网',
  complianceSearchPlaceholder: '搜索开源软件、学术资料...',

  // ── Misc ──
  fileCount: (n: number) => `文件数 ${n}`,
};

const en: typeof zh = {
  // ── Home ──
  sloganPrefix: 'Search every magnet. ',
  sloganBrand: 'All in one.',
  searchPlaceholder: 'Search movies, anime, games...',
  searchButton: 'Search Magnets',
  emptyQueryToast: 'Please enter a search query',

  // ── Search results ──
  searchingStatus: (done, total, results) =>
    `Searching ${done}/${total} indexers... ${results} found`,
  searchDoneStatus: (done, total, results) =>
    `Searched ${done}/${total} indexers. ${results} found`,
  sortComprehensive: 'Best Match',
  sortRelevance: 'Relevance',
  sortSize: 'Size',
  sortDate: 'Date',
  copyMagnet: 'Copy Magnet',
  copied: 'Copied to clipboard',
  openMagnet: 'Open Link',
  copyFailed: 'Copy failed',
  cannotOpen: 'Unable to open link',
  cannotOpenMsg: 'No compatible torrent client found on this device',
  noSourcesHint: 'Please sync search indexers in Settings first',
  goToSettings: 'Go to Settings',

  // ── Settings ──
  settings: 'Settings',
  sectionSources: 'Search Indexers',
  syncSources: 'Sync latest indexers',
  syncSuccess: (_count) => `Indexers synced successfully`,
  notSynced: 'Not synced',
  lastSync: 'Last synced',
  sectionLanguage: 'Language',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'About',
  version: 'Version',

  // ── Kind labels (Tier 1: content types) ──
  kindMovie: 'Movies',
  kindTvUs: 'US/EU TV Shows',
  kindTvJp: 'Anime/Japanese Drama',
  kindTvKr: 'Korean Drama',
  kindTvCn: 'Chinese Drama',
  kindTv: 'TV Series',
  kindAnime: 'Anime',
  kindVariety: 'Variety Shows',
  kindDocumentary: 'Documentary',
  kindMusic: 'Music',
  kindGame: 'Games',
  kindEbook: 'eBooks',
  kindManga: 'Manga',
  // ── Kind labels (Tier 2: format types) ──
  kindVideo: 'Video',
  kindAudio: 'Audio',
  kindArchive: 'Archive',
  kindImage: 'Images',
  kindDocument: 'Documents',
  kindSoftware: 'Software',
  kindOther: 'Others',

  sectionTheme: 'Theme',

  // ── Search UX ──
  lowRelevanceHint: 'Low relevance results',
  feedbackBtn: 'Feedback',

  // ── History ──
  historyTitle: 'Search History',
  historyClear: 'Clear All',

  // ── Favorites ──
  favoritesTitle: 'Favorites',
  favoriteAdded: 'Added to favorites',
  favoriteRemoved: 'Removed from favorites',
  noFavorites: 'No favorites yet',

  watchlistTitle: 'Keyword Subscription',
  watchSubscribe: 'Subscribe',
  watchSubscribed: 'Subscribed',
  watchUnsubscribe: 'Unsubscribe',
  noWatchlist: 'No subscriptions yet',
  watchlistHint: 'Subscribe to search terms to get notified of new results',
  watchTapToSeeUpdate: 'New results found. Tap to view.',
  watchLastCount: (n: number) => `Last search: ${n} ${n === 1 ? 'result' : 'results'}`,
  watchSubscribedToast: 'Subscribed to keyword',
  watchUpdateToast: 'New results available for subscribed keyword',
  homeWatchlist: 'My Subscriptions',
  cancel: 'Cancel',

  // ── Legal ──
  privacyTitle: 'Privacy Policy',
  termsTitle: 'Terms of Service',

  // ── Empty results ──
  noResultsHint: 'No results found',
  noResultsSuggestion: 'Try alternative keywords or check spelling',

  // ── Compliance mode ──
  complianceBannerLine1: 'You are using the Compliant Edition. To unlock indexers, visit our website.',
  complianceBannerLink: 'Go to Website',
  complianceSearchPlaceholder: 'Search open-source software, academic papers...',

  // ── Misc ──
  fileCount: (n) => `${n} ${n === 1 ? 'file' : 'files'}`,
};

const es: typeof zh = {
  sloganPrefix: 'Todos los magnets. ',
  sloganBrand: 'Una búsqueda.',
  searchPlaceholder: 'Películas, anime, torrents...',
  searchButton: 'Buscar magnets',
  emptyQueryToast: 'Escribe algo para buscar',

  searchingStatus: (done, total, results) =>
    `Buscando ${done}/${total} fuentes, ${results} resultados`,
  searchDoneStatus: (done, total, results) =>
    `Consultadas ${done}/${total} fuentes, ${results} resultados`,
  sortComprehensive: 'Inteligente',
  sortRelevance: 'Relevancia',
  sortSize: 'Tamaño',
  sortDate: 'Fecha',
  copyMagnet: 'Copiar magnet',
  copied: 'Copiado',
  openMagnet: 'Abrir',
  copyFailed: 'Error al copiar',
  cannotOpen: 'No se puede abrir',
  cannotOpenMsg: 'No se encontró una app para enlaces magnet',
  noSourcesHint: 'Primero descarga las fuentes en Ajustes',
  goToSettings: 'Ir a Ajustes',

  settings: 'Ajustes',
  sectionSources: 'Fuentes',
  syncSources: 'Descargar fuentes',
  syncSuccess: (_count) => `Fuentes seleccionadas sincronizadas`,
  notSynced: 'Sin sincronizar',
  lastSync: 'Última sincronización',
  sectionLanguage: 'Idioma',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'Acerca de',
  version: 'Versión',

  kindMovie: 'Película',
  kindTvUs: 'Series EE.UU.',
  kindTvJp: 'Doramas JP',
  kindTvKr: 'Doramas KR',
  kindTvCn: 'Series CN',
  kindTv: 'Series',
  kindAnime: 'Anime',
  kindVariety: 'Variedades',
  kindDocumentary: 'Documental',
  kindMusic: 'Música',
  kindGame: 'Juego',
  kindEbook: 'eBook',
  kindManga: 'Manga',
  kindVideo: 'Vídeo',
  kindAudio: 'Audio',
  kindArchive: 'Archivo',
  kindImage: 'Imagen',
  kindDocument: 'Documento',
  kindSoftware: 'Software',
  kindOther: 'Otro',

  sectionTheme: 'Tema',

  lowRelevanceHint: 'Los siguientes resultados pueden ser menos relevantes',
  feedbackBtn: '¡Reclama!',

  historyTitle: 'Historial',
  historyClear: 'Borrar',

  favoritesTitle: 'Favoritos',
  favoriteAdded: 'Añadido a favoritos',
  favoriteRemoved: 'Eliminado de favoritos',
  noFavorites: 'Sin favoritos',

  watchlistTitle: 'Lista de seguimiento',
  watchSubscribe: 'Seguir',
  watchSubscribed: 'Siguiendo',
  watchUnsubscribe: 'Dejar de seguir',
  noWatchlist: 'Sin palabras clave',
  watchlistHint: 'Toca Seguir en resultados; avisamos si cambian',
  watchTapToSeeUpdate: 'Nuevos resultados — toca para ver',
  watchLastCount: (n: number) => `Última búsqueda: ${n} resultados`,
  watchSubscribedToast: 'Palabra añadida a la lista',
  watchUpdateToast: 'Hay nuevos resultados',
  homeWatchlist: 'Mi lista',
  cancel: 'Cancelar',

  privacyTitle: 'Política de privacidad',
  termsTitle: 'Términos de servicio',

  noResultsHint: 'Sin resultados',
  noResultsSuggestion: 'Prueba otras palabras clave',

  complianceBannerLine1: 'Versión compatible. Desbloquea más fuentes en nuestro sitio web.',
  complianceBannerLink: 'Visitar sitio',
  complianceSearchPlaceholder: 'Software libre, artículos académicos...',

  fileCount: (n) => `${n} archivos`,
};

const ru: typeof zh = {
  sloganPrefix: 'Все магнеты. ',
  sloganBrand: 'Один поиск.',
  searchPlaceholder: 'Фильмы, аниме, торренты...',
  searchButton: 'Искать магнеты',
  emptyQueryToast: 'Введите поисковый запрос',

  searchingStatus: (done, total, results) =>
    `Поиск ${done}/${total} источников, найдено ${results}`,
  searchDoneStatus: (done, total, results) =>
    `Проверено ${done}/${total} источников, найдено ${results}`,
  sortComprehensive: 'Умная',
  sortRelevance: 'Релевантность',
  sortSize: 'Размер',
  sortDate: 'Дата',
  copyMagnet: 'Копировать магнет',
  copied: 'Скопировано',
  openMagnet: 'Открыть',
  copyFailed: 'Ошибка копирования',
  cannotOpen: 'Не удалось открыть',
  cannotOpenMsg: 'Не найдено приложение для магнет-ссылок',
  noSourcesHint: 'Сначала загрузите источники в настройках',
  goToSettings: 'Настройки',

  settings: 'Настройки',
  sectionSources: 'Источники',
  syncSources: 'Загрузить источники',
  syncSuccess: (_count) => `Подобранные источники синхронизированы`,
  notSynced: 'Не синхронизировано',
  lastSync: 'Последняя синхронизация',
  sectionLanguage: 'Язык',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'О приложении',
  version: 'Версия',

  kindMovie: 'Фильм',
  kindTvUs: 'Сериалы США',
  kindTvJp: 'Дорамы JP',
  kindTvKr: 'Дорамы KR',
  kindTvCn: 'Сериалы CN',
  kindTv: 'Сериалы',
  kindAnime: 'Аниме',
  kindVariety: 'Шоу',
  kindDocumentary: 'Документальное',
  kindMusic: 'Музыка',
  kindGame: 'Игра',
  kindEbook: 'Книга',
  kindManga: 'Манга',
  kindVideo: 'Видео',
  kindAudio: 'Аудио',
  kindArchive: 'Архив',
  kindImage: 'Изображение',
  kindDocument: 'Документ',
  kindSoftware: 'Программа',
  kindOther: 'Прочее',

  sectionTheme: 'Тема',

  lowRelevanceHint: 'Результаты ниже могут быть менее релевантны',
  feedbackBtn: 'Пожаловаться',

  historyTitle: 'История поиска',
  historyClear: 'Очистить',

  favoritesTitle: 'Избранное',
  favoriteAdded: 'Добавлено в избранное',
  favoriteRemoved: 'Удалено из избранного',
  noFavorites: 'Нет избранного',

  watchlistTitle: 'Подписки',
  watchSubscribe: 'Подписаться',
  watchSubscribed: 'Подписан',
  watchUnsubscribe: 'Отписаться',
  noWatchlist: 'Нет подписок',
  watchlistHint: 'Нажмите «Подписаться» на странице результатов',
  watchTapToSeeUpdate: 'Новые результаты — нажмите',
  watchLastCount: (n: number) => `Последний поиск: ${n}`,
  watchSubscribedToast: 'Ключевое слово добавлено',
  watchUpdateToast: 'Есть новые результаты',
  homeWatchlist: 'Мои подписки',
  cancel: 'Отмена',

  privacyTitle: 'Политика конфиденциальности',
  termsTitle: 'Условия использования',

  noResultsHint: 'Ничего не найдено',
  noResultsSuggestion: 'Попробуйте другие ключевые слова',

  complianceBannerLine1: 'Совместимая версия. Разблокируйте больше источников на нашем сайте.',
  complianceBannerLink: 'На сайт',
  complianceSearchPlaceholder: 'Открытое ПО, научные статьи...',

  fileCount: (n) => `${n} файлов`,
};

const pt: typeof zh = {
  sloganPrefix: 'Todos os magnets. ',
  sloganBrand: 'Uma busca.',
  searchPlaceholder: 'Filmes, anime, torrents...',
  searchButton: 'Buscar magnets',
  emptyQueryToast: 'Digite algo para buscar',

  searchingStatus: (done, total, results) =>
    `Buscando ${done}/${total} fontes, ${results} resultados`,
  searchDoneStatus: (done, total, results) =>
    `Pesquisadas ${done}/${total} fontes, ${results} resultados`,
  sortComprehensive: 'Inteligente',
  sortRelevance: 'Relevância',
  sortSize: 'Tamanho',
  sortDate: 'Data',
  copyMagnet: 'Copiar magnet',
  copied: 'Copiado',
  openMagnet: 'Abrir',
  copyFailed: 'Falha ao copiar',
  cannotOpen: 'Não foi possível abrir',
  cannotOpenMsg: 'Nenhum app encontrado para links magnet',
  noSourcesHint: 'Primeiro baixe as fontes em Configurações',
  goToSettings: 'Configurações',

  settings: 'Configurações',
  sectionSources: 'Fontes',
  syncSources: 'Baixar fontes',
  syncSuccess: (_count) => `Fontes selecionadas sincronizadas`,
  notSynced: 'Não sincronizado',
  lastSync: 'Última sincronização',
  sectionLanguage: 'Idioma',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'Sobre',
  version: 'Versão',

  kindMovie: 'Filme',
  kindTvUs: 'Séries EUA',
  kindTvJp: 'Doramas JP',
  kindTvKr: 'Doramas KR',
  kindTvCn: 'Séries CN',
  kindTv: 'Séries',
  kindAnime: 'Anime',
  kindVariety: 'Variedades',
  kindDocumentary: 'Documentário',
  kindMusic: 'Música',
  kindGame: 'Jogo',
  kindEbook: 'eBook',
  kindManga: 'Mangá',
  kindVideo: 'Vídeo',
  kindAudio: 'Áudio',
  kindArchive: 'Arquivo',
  kindImage: 'Imagem',
  kindDocument: 'Documento',
  kindSoftware: 'Software',
  kindOther: 'Outro',

  sectionTheme: 'Tema',

  lowRelevanceHint: 'Os resultados abaixo podem ser menos relevantes',
  feedbackBtn: 'Reclame!',

  historyTitle: 'Histórico',
  historyClear: 'Limpar',

  favoritesTitle: 'Favoritos',
  favoriteAdded: 'Adicionado aos favoritos',
  favoriteRemoved: 'Removido dos favoritos',
  noFavorites: 'Sem favoritos',

  watchlistTitle: 'Lista de observação',
  watchSubscribe: 'Observar',
  watchSubscribed: 'Observando',
  watchUnsubscribe: 'Remover',
  noWatchlist: 'Nenhuma palavra-chave',
  watchlistHint: 'Toque Observar nos resultados',
  watchTapToSeeUpdate: 'Novos resultados — toque',
  watchLastCount: (n: number) => `Última busca: ${n} resultados`,
  watchSubscribedToast: 'Palavra adicionada',
  watchUpdateToast: 'Novos resultados disponíveis',
  homeWatchlist: 'Minha lista',
  cancel: 'Cancelar',

  privacyTitle: 'Política de Privacidade',
  termsTitle: 'Termos de Serviço',

  noResultsHint: 'Nenhum resultado encontrado',
  noResultsSuggestion: 'Tente outras palavras-chave',

  complianceBannerLine1: 'Versão compatível. Desbloqueie mais fontes no nosso site.',
  complianceBannerLink: 'Visitar site',
  complianceSearchPlaceholder: 'Software livre, artigos acadêmicos...',

  fileCount: (n) => `${n} arquivos`,
};

const ja: typeof zh = {
  sloganPrefix: 'すべてのマグネット。',
  sloganBrand: 'ワンサーチ。',
  searchPlaceholder: '映画、アニメ、トレント...',
  searchButton: 'マグネット検索',
  emptyQueryToast: '検索キーワードを入力してください',

  searchingStatus: (done, total, results) =>
    `検索中 ${done}/${total} ソース、${results}件の結果`,
  searchDoneStatus: (done, total, results) =>
    `検索完了 ${done}/${total} ソース、${results}件の結果`,
  sortComprehensive: '総合',
  sortRelevance: '関連性',
  sortSize: 'サイズ',
  sortDate: '日付',
  copyMagnet: 'マグネットをコピー',
  copied: 'コピーしました',
  openMagnet: '開く',
  copyFailed: 'コピー失敗',
  cannotOpen: '開けません',
  cannotOpenMsg: 'マグネットリンクに対応するアプリが見つかりません',
  noSourcesHint: '設定でソースデータを取得してください',
  goToSettings: '設定へ',

  settings: '設定',
  sectionSources: 'ソース',
  syncSources: '最新ソースを取得',
  syncSuccess: (_count) => `厳選ソースを同期しました`,
  notSynced: '未同期',
  lastSync: '前回の同期',
  sectionLanguage: '言語',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'このアプリについて',
  version: 'バージョン',

  kindMovie: '映画',
  kindTvUs: '海外ドラマ',
  kindTvJp: '日本ドラマ',
  kindTvKr: '韓国ドラマ',
  kindTvCn: '中国ドラマ',
  kindTv: 'ドラマ',
  kindAnime: 'アニメ',
  kindVariety: 'バラエティ',
  kindDocumentary: 'ドキュメンタリー',
  kindMusic: '音楽',
  kindGame: 'ゲーム',
  kindEbook: '電子書籍',
  kindManga: 'マンガ',
  kindVideo: '動画',
  kindAudio: 'オーディオ',
  kindArchive: '圧縮ファイル',
  kindImage: '画像',
  kindDocument: 'ドキュメント',
  kindSoftware: 'ソフトウェア',
  kindOther: 'その他',

  sectionTheme: 'テーマ',

  lowRelevanceHint: '以下の結果は関連性が低い可能性があります',
  feedbackBtn: '愚痴る',

  historyTitle: '検索履歴',
  historyClear: 'クリア',

  favoritesTitle: 'お気に入り',
  favoriteAdded: 'お気に入りに追加',
  favoriteRemoved: 'お気に入りから削除',
  noFavorites: 'お気に入りはありません',

  watchlistTitle: 'キーワード購読',
  watchSubscribe: '購読',
  watchSubscribed: '購読中',
  watchUnsubscribe: '購読解除',
  noWatchlist: '購読なし',
  watchlistHint: '検索結果で「購読」をタップ',
  watchTapToSeeUpdate: '新しい結果があります',
  watchLastCount: (n: number) => `前回 ${n} 件`,
  watchSubscribedToast: 'キーワードを購読しました',
  watchUpdateToast: '新しい結果があります',
  homeWatchlist: '購読一覧',
  cancel: 'キャンセル',

  privacyTitle: 'プライバシーポリシー',
  termsTitle: '利用規約',

  noResultsHint: '結果が見つかりません',
  noResultsSuggestion: '他のキーワードをお試しください',

  complianceBannerLine1: 'コンプライアンス版です。公式サイトでより多くのソースを解放。',
  complianceBannerLink: '公式サイトへ',
  complianceSearchPlaceholder: 'オープンソース、学術資料...',

  fileCount: (n) => `${n}ファイル`,
};

const ko: typeof zh = {
  sloganPrefix: '모든 마그넷. ',
  sloganBrand: '한 번에 검색.',
  searchPlaceholder: '영화, 애니, 토렌트...',
  searchButton: '마그넷 검색',
  emptyQueryToast: '검색어를 입력하세요',

  searchingStatus: (done, total, results) =>
    `검색 중 ${done}/${total} 소스, ${results}개 결과`,
  searchDoneStatus: (done, total, results) =>
    `검색 완료 ${done}/${total} 소스, ${results}개 결과`,
  sortComprehensive: '종합',
  sortRelevance: '관련성',
  sortSize: '크기',
  sortDate: '날짜',
  copyMagnet: '마그넷 복사',
  copied: '복사됨',
  openMagnet: '열기',
  copyFailed: '복사 실패',
  cannotOpen: '열 수 없음',
  cannotOpenMsg: '마그넷 링크를 처리할 앱을 찾을 수 없습니다',
  noSourcesHint: '설정에서 소스 데이터를 먼저 받아주세요',
  goToSettings: '설정으로',

  settings: '설정',
  sectionSources: '소스',
  syncSources: '최신 소스 받기',
  syncSuccess: (_count) => `엄선된 소스 동기화됨`,
  notSynced: '동기화 안 됨',
  lastSync: '마지막 동기화',
  sectionLanguage: '언어',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: '정보',
  version: '버전',

  kindMovie: '영화',
  kindTvUs: '미드',
  kindTvJp: '일드',
  kindTvKr: '한드',
  kindTvCn: '중드',
  kindTv: '드라마',
  kindAnime: '애니메이션',
  kindVariety: '예능',
  kindDocumentary: '다큐멘터리',
  kindMusic: '음악',
  kindGame: '게임',
  kindEbook: '전자책',
  kindManga: '만화',
  kindVideo: '영상',
  kindAudio: '오디오',
  kindArchive: '압축파일',
  kindImage: '이미지',
  kindDocument: '문서',
  kindSoftware: '소프트웨어',
  kindOther: '기타',

  sectionTheme: '테마',

  lowRelevanceHint: '아래 결과는 관련성이 낮을 수 있습니다',
  feedbackBtn: '한마디',

  historyTitle: '검색 기록',
  historyClear: '지우기',

  favoritesTitle: '즐겨찾기',
  favoriteAdded: '즐겨찾기에 추가됨',
  favoriteRemoved: '즐겨찾기에서 삭제됨',
  noFavorites: '즐겨찾기 없음',

  watchlistTitle: '키워드 구독',
  watchSubscribe: '구독',
  watchSubscribed: '구독 중',
  watchUnsubscribe: '구독 취소',
  noWatchlist: '구독 없음',
  watchlistHint: '검색 결과에서 구독을 탭하세요',
  watchTapToSeeUpdate: '새 결과 — 탭하여 보기',
  watchLastCount: (n: number) => `이전 ${n}개 결과`,
  watchSubscribedToast: '키워드가 구독되었습니다',
  watchUpdateToast: '새 결과가 있습니다',
  homeWatchlist: '내 구독',
  cancel: '취소',

  privacyTitle: '개인정보처리방침',
  termsTitle: '이용약관',

  noResultsHint: '결과를 찾을 수 없습니다',
  noResultsSuggestion: '다른 키워드로 검색해 보세요',

  complianceBannerLine1: '규정 준수 버전입니다. 공식 사이트에서 더 많은 소스를 해제하세요.',
  complianceBannerLink: '공식 사이트',
  complianceSearchPlaceholder: '오픈소스, 학술 자료...',

  fileCount: (n) => `${n}개 파일`,
};

const fr: typeof zh = {
  sloganPrefix: 'Tous les magnets. ',
  sloganBrand: 'Une recherche.',
  searchPlaceholder: 'Films, anime, torrents...',
  searchButton: 'Rechercher',
  emptyQueryToast: 'Saisissez un terme de recherche',

  searchingStatus: (done, total, results) =>
    `Recherche ${done}/${total} sources, ${results} résultats`,
  searchDoneStatus: (done, total, results) =>
    `Consultées ${done}/${total} sources, ${results} résultats`,
  sortComprehensive: 'Intelligent',
  sortRelevance: 'Pertinence',
  sortSize: 'Taille',
  sortDate: 'Date',
  copyMagnet: 'Copier le magnet',
  copied: 'Copié',
  openMagnet: 'Ouvrir',
  copyFailed: 'Échec de la copie',
  cannotOpen: 'Impossible d\'ouvrir',
  cannotOpenMsg: 'Aucune application trouvée pour les liens magnet',
  noSourcesHint: 'Téléchargez d\'abord les sources dans les paramètres',
  goToSettings: 'Paramètres',

  settings: 'Paramètres',
  sectionSources: 'Sources',
  syncSources: 'Télécharger les sources',
  syncSuccess: (_count) => `Sources sélectionnées synchronisées`,
  notSynced: 'Non synchronisé',
  lastSync: 'Dernière synchronisation',
  sectionLanguage: 'Langue',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'À propos',
  version: 'Version',

  kindMovie: 'Film',
  kindTvUs: 'Séries US',
  kindTvJp: 'Dramas JP',
  kindTvKr: 'Dramas KR',
  kindTvCn: 'Séries CN',
  kindTv: 'Séries',
  kindAnime: 'Anime',
  kindVariety: 'Divertissement',
  kindDocumentary: 'Documentaire',
  kindMusic: 'Musique',
  kindGame: 'Jeu',
  kindEbook: 'eBook',
  kindManga: 'Manga',
  kindVideo: 'Vidéo',
  kindAudio: 'Audio',
  kindArchive: 'Archive',
  kindImage: 'Image',
  kindDocument: 'Document',
  kindSoftware: 'Logiciel',
  kindOther: 'Autre',

  sectionTheme: 'Thème',

  lowRelevanceHint: 'Les résultats ci-dessous peuvent être moins pertinents',
  feedbackBtn: 'Râlez!',

  historyTitle: 'Historique',
  historyClear: 'Effacer',

  favoritesTitle: 'Favoris',
  favoriteAdded: 'Ajouté aux favoris',
  favoriteRemoved: 'Retiré des favoris',
  noFavorites: 'Aucun favori',

  watchlistTitle: 'Abonnements',
  watchSubscribe: 'Suivre',
  watchSubscribed: 'Suivi',
  watchUnsubscribe: 'Ne plus suivre',
  noWatchlist: 'Aucun mot-clé',
  watchlistHint: 'Appuyez sur Suivre dans les résultats',
  watchTapToSeeUpdate: 'Nouveaux résultats',
  watchLastCount: (n: number) => `Dernière recherche : ${n}`,
  watchSubscribedToast: 'Mot-clé ajouté',
  watchUpdateToast: 'Nouveaux résultats',
  homeWatchlist: 'Mes abonnements',
  cancel: 'Annuler',

  privacyTitle: 'Politique de confidentialité',
  termsTitle: 'Conditions d\'utilisation',

  noResultsHint: 'Aucun résultat trouvé',
  noResultsSuggestion: 'Essayez d\'autres mots-clés',

  complianceBannerLine1: 'Version conforme. Débloquez plus de sources sur notre site.',
  complianceBannerLink: 'Visiter le site',
  complianceSearchPlaceholder: 'Logiciels libres, articles académiques...',

  fileCount: (n) => `${n} fichiers`,
};

const de: typeof zh = {
  sloganPrefix: 'Alle Magnets. ',
  sloganBrand: 'Eine Suche.',
  searchPlaceholder: 'Filme, Anime, Torrents...',
  searchButton: 'Magnets suchen',
  emptyQueryToast: 'Bitte Suchbegriff eingeben',

  searchingStatus: (done, total, results) =>
    `Suche ${done}/${total} Quellen, ${results} Ergebnisse`,
  searchDoneStatus: (done, total, results) =>
    `Durchsucht ${done}/${total} Quellen, ${results} Ergebnisse`,
  sortComprehensive: 'Smart',
  sortRelevance: 'Relevanz',
  sortSize: 'Größe',
  sortDate: 'Datum',
  copyMagnet: 'Magnet kopieren',
  copied: 'Kopiert',
  openMagnet: 'Öffnen',
  copyFailed: 'Kopieren fehlgeschlagen',
  cannotOpen: 'Kann nicht geöffnet werden',
  cannotOpenMsg: 'Keine App für Magnet-Links gefunden',
  noSourcesHint: 'Bitte zuerst Quellen in den Einstellungen laden',
  goToSettings: 'Einstellungen',

  settings: 'Einstellungen',
  sectionSources: 'Quellen',
  syncSources: 'Quellen laden',
  syncSuccess: (_count) => `Ausgewählte Quellen synchronisiert`,
  notSynced: 'Nicht synchronisiert',
  lastSync: 'Letzte Synchronisierung',
  sectionLanguage: 'Sprache',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'Über',
  version: 'Version',

  kindMovie: 'Film',
  kindTvUs: 'US-Serien',
  kindTvJp: 'JP-Dramen',
  kindTvKr: 'KR-Dramen',
  kindTvCn: 'CN-Serien',
  kindTv: 'Serien',
  kindAnime: 'Anime',
  kindVariety: 'Unterhaltung',
  kindDocumentary: 'Dokumentation',
  kindMusic: 'Musik',
  kindGame: 'Spiel',
  kindEbook: 'eBook',
  kindManga: 'Manga',
  kindVideo: 'Video',
  kindAudio: 'Audio',
  kindArchive: 'Archiv',
  kindImage: 'Bild',
  kindDocument: 'Dokument',
  kindSoftware: 'Software',
  kindOther: 'Sonstiges',

  sectionTheme: 'Design',

  lowRelevanceHint: 'Die folgenden Ergebnisse sind möglicherweise weniger relevant',
  feedbackBtn: 'Ärgern!',

  historyTitle: 'Suchverlauf',
  historyClear: 'Löschen',

  favoritesTitle: 'Favoriten',
  favoriteAdded: 'Zu Favoriten hinzugefügt',
  favoriteRemoved: 'Aus Favoriten entfernt',
  noFavorites: 'Keine Favoriten',

  watchlistTitle: 'Beobachtungsliste',
  watchSubscribe: 'Beobachten',
  watchSubscribed: 'Beobachtet',
  watchUnsubscribe: 'Entfernen',
  noWatchlist: 'Keine Stichwörter',
  watchlistHint: 'In den Ergebnissen auf Beobachten tippen',
  watchTapToSeeUpdate: 'Neue Ergebnisse',
  watchLastCount: (n: number) => `Letzte Suche: ${n} Treffer`,
  watchSubscribedToast: 'Stichwort hinzugefügt',
  watchUpdateToast: 'Neue Ergebnisse verfügbar',
  homeWatchlist: 'Meine Liste',
  cancel: 'Abbrechen',

  privacyTitle: 'Datenschutzrichtlinie',
  termsTitle: 'Nutzungsbedingungen',

  noResultsHint: 'Keine Ergebnisse gefunden',
  noResultsSuggestion: 'Versuchen Sie andere Suchbegriffe',

  complianceBannerLine1: 'Konforme Version. Mehr Quellen auf unserer Website freischalten.',
  complianceBannerLink: 'Zur Website',
  complianceSearchPlaceholder: 'Open-Source-Software, akademische Artikel...',

  fileCount: (n) => `${n} Dateien`,
};

const ar: typeof zh = {
  sloganPrefix: 'جميع المغناطيسات. ',
  sloganBrand: 'بحث واحد.',
  searchPlaceholder: 'أفلام، أنمي، تورنت...',
  searchButton: 'بحث مغناطيس',
  emptyQueryToast: 'يرجى إدخال كلمة بحث',

  searchingStatus: (done, total, results) =>
    `جارٍ البحث ${done}/${total} مصادر، ${results} نتيجة`,
  searchDoneStatus: (done, total, results) =>
    `تم البحث ${done}/${total} مصادر، ${results} نتيجة`,
  sortComprehensive: 'ذكي',
  sortRelevance: 'الصلة',
  sortSize: 'الحجم',
  sortDate: 'التاريخ',
  copyMagnet: 'نسخ المغناطيس',
  copied: 'تم النسخ',
  openMagnet: 'فتح',
  copyFailed: 'فشل النسخ',
  cannotOpen: 'تعذّر الفتح',
  cannotOpenMsg: 'لم يُعثر على تطبيق يدعم روابط المغناطيس',
  noSourcesHint: 'يرجى تحميل المصادر من الإعدادات أولاً',
  goToSettings: 'الإعدادات',

  settings: 'الإعدادات',
  sectionSources: 'المصادر',
  syncSources: 'تحميل المصادر',
  syncSuccess: (_count) => `تم مزامنة المصادر المختارة`,
  notSynced: 'غير متزامن',
  lastSync: 'آخر مزامنة',
  sectionLanguage: 'اللغة',
  langZh: '中文',
  langEn: 'English',
  sectionAbout: 'حول التطبيق',
  version: 'الإصدار',

  kindMovie: 'فيلم',
  kindTvUs: 'مسلسلات أمريكية',
  kindTvJp: 'دراما يابانية',
  kindTvKr: 'دراما كورية',
  kindTvCn: 'مسلسلات صينية',
  kindTv: 'مسلسلات',
  kindAnime: 'أنمي',
  kindVariety: 'برامج ترفيهية',
  kindDocumentary: 'وثائقي',
  kindMusic: 'موسيقى',
  kindGame: 'ألعاب',
  kindEbook: 'كتاب إلكتروني',
  kindManga: 'مانغا',
  kindVideo: 'فيديو',
  kindAudio: 'صوتي',
  kindArchive: 'أرشيف',
  kindImage: 'صورة',
  kindDocument: 'مستند',
  kindSoftware: 'برنامج',
  kindOther: 'أخرى',

  sectionTheme: 'المظهر',

  lowRelevanceHint: 'النتائج أدناه قد تكون أقل صلة',
  feedbackBtn: 'اشتكي!',

  historyTitle: 'سجل البحث',
  historyClear: 'مسح',

  favoritesTitle: 'المفضلة',
  favoriteAdded: 'أُضيف إلى المفضلة',
  favoriteRemoved: 'أُزيل من المفضلة',
  noFavorites: 'لا توجد مفضلات',

  watchlistTitle: 'قائمة المتابعة',
  watchSubscribe: 'متابعة',
  watchSubscribed: 'متابَع',
  watchUnsubscribe: 'إلغاء المتابعة',
  noWatchlist: 'لا كلمات مفتاحية',
  watchlistHint: 'اضغط متابعة في صفحة النتائج',
  watchTapToSeeUpdate: 'نتائج جديدة',
  watchLastCount: (n: number) => `آخر بحث: ${n} نتيجة`,
  watchSubscribedToast: 'تمت إضافة الكلمة',
  watchUpdateToast: 'نتائج جديدة متاحة',
  homeWatchlist: 'متابعاتي',
  cancel: 'إلغاء',

  privacyTitle: 'سياسة الخصوصية',
  termsTitle: 'شروط الخدمة',

  noResultsHint: 'لم يتم العثور على نتائج',
  noResultsSuggestion: 'جرّب كلمات مفتاحية أخرى',

  complianceBannerLine1: 'نسخة متوافقة. افتح المزيد من المصادر على موقعنا الرسمي.',
  complianceBannerLink: 'زيارة الموقع',
  complianceSearchPlaceholder: 'برامج مفتوحة المصدر، أبحاث أكاديمية...',

  fileCount: (n) => `${n} ملفات`,
};

const translations: Record<Lang, typeof zh> = { zh, en, es, ru, pt, ja, ko, fr, de, ar };

export type Translations = typeof zh;

export function getTranslations(lang: Lang): Translations {
  return translations[lang];
}
