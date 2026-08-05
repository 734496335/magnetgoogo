#!/usr/bin/env node
/**
 * 多语言 SEO 落地页生成器
 * 为 App 支持的 10 种语言各生成一个本地化首页
 * 输出到 magnetgoogo-site/{lang}/ 目录
 * 
 * 语言: zh(已有主站) / en / es / ru / pt / ja / ko / fr / de / ar
 */

const fs = require('fs');
const path = require('path');

const SITE_DIR = path.join(__dirname, '..', 'magnetgoogo-site');
function loadJson(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
  return JSON.parse(raw);
}

const siteConfig = loadJson(path.join(SITE_DIR, 'site-config.json'));
const downloadUrl = siteConfig.download_url;
const backupDownloads = Array.isArray(siteConfig.backup_downloads) && siteConfig.backup_downloads.length > 0
  ? siteConfig.backup_downloads
  : [{ url: siteConfig.backup_url || `${siteConfig.lanzou_base}/${siteConfig.lanzou_id}`, label: siteConfig.backup_label || 'Backup' }];

// ─── 语言数据 ──────────────────────────────────────────────────────
const LANGS = [
  {
    code: 'en',
    htmlLang: 'en',
    dir: 'ltr',
    name: 'English',
    title: 'Magnet Googo — Free Aggregated Magnet & Torrent Search Engine',
    metaDesc: 'Magnet Googo is a free Android app that aggregates multiple magnet and torrent sites into one search. Movies, anime, music, games — one search, all results. No ads, no registration.',
    keywords: 'magnet search,torrent search,magnet link,free torrent search engine,magnet googo,torrent aggregator,BT search,magnet download,free magnet search app',
    h1: 'Every Magnet. One Search.',
    subtitle: 'Magnet Googo aggregates multiple magnet & torrent sites into one free search app.',
    ctaDownload: 'Free Download (APK)',
    ctaBackup: 'Backup Download',
    features: [
      { icon: '🔍', title: 'Aggregated Search', desc: 'Search dozens of magnet and torrent sites simultaneously. One query, all results.' },
      { icon: '⚡', title: 'Instant Results', desc: 'Concurrent multi-source queries deliver results in seconds.' },
      { icon: '🚫', title: 'Zero Ads', desc: 'Completely free. No ads, no registration, no premium tier.' },
      { icon: '🔄', title: 'Always Available', desc: 'Sources auto-update. If one site goes down, others keep working.' },
      { icon: '📊', title: 'Smart Ranking', desc: 'Results ranked by relevance, seeders, and file quality.' },
      { icon: '📱', title: 'Mobile First', desc: 'Built natively for Android. Fast, lightweight, beautiful.' },
    ],
    howTitle: 'How It Works',
    howSteps: [
      { n: '1', title: 'Download', desc: 'Get the free APK from this page.' },
      { n: '2', title: 'Search', desc: 'Enter any keyword — movies, anime, music, games.' },
      { n: '3', title: 'Download', desc: 'Copy the magnet link to your favorite torrent client.' },
    ],
    faqTitle: 'FAQ',
    faqs: [
      { q: 'Is Magnet Googo free?', a: 'Yes, completely free with no ads or in-app purchases.' },
      { q: 'Which platforms are supported?', a: 'Currently Android. iOS support is planned.' },
      { q: 'How does it work?', a: 'Magnet Googo searches multiple torrent and magnet sites simultaneously, merges and deduplicates results, then presents them in a unified interface.' },
      { q: 'Is it safe?', a: 'Magnet Googo only searches for magnet links. It does not host or distribute any content. Always use a reputable torrent client for downloads.' },
    ],
    footer: '© 2026 Magnet Googo. Every Magnet. One Search.',
    langLabel: 'Language',
  },
  {
    code: 'ja',
    htmlLang: 'ja',
    dir: 'ltr',
    name: '日本語',
    title: 'Magnet Googo — 無料マグネット＆トレント統合検索エンジン',
    metaDesc: 'Magnet Googoは複数のマグネット・トレントサイトを一括検索する無料Androidアプリです。映画、アニメ、音楽、ゲーム — 一回の検索で全結果。広告なし、登録不要。',
    keywords: 'マグネット検索,トレント検索,マグネットリンク,無料トレント検索,magnet googo,BT検索,マグネットダウンロード,アニメトレント',
    h1: 'すべてのマグネット。ワンサーチ。',
    subtitle: 'Magnet Googoは複数のマグネット＆トレントサイトを統合する無料検索アプリです。',
    ctaDownload: '無料ダウンロード（APK）',
    ctaBackup: 'バックアップダウンロード',
    features: [
      { icon: '🔍', title: '統合検索', desc: '数十のマグネット・トレントサイトを同時に検索。一回のクエリで全結果。' },
      { icon: '⚡', title: '即座に結果', desc: '並行マルチソースクエリで数秒で結果を表示。' },
      { icon: '🚫', title: '広告ゼロ', desc: '完全無料。広告なし、登録不要、有料プランなし。' },
      { icon: '🔄', title: '常に利用可能', desc: 'ソースは自動更新。一つのサイトがダウンしても他が機能。' },
      { icon: '📊', title: 'スマートランキング', desc: '関連性、シーダー数、ファイル品質で結果をランキング。' },
      { icon: '📱', title: 'モバイルファースト', desc: 'Android向けネイティブ開発。高速、軽量、美しいUI。' },
    ],
    howTitle: '使い方',
    howSteps: [
      { n: '1', title: 'ダウンロード', desc: 'このページから無料APKを取得。' },
      { n: '2', title: '検索', desc: 'キーワードを入力 — 映画、アニメ、音楽、ゲーム。' },
      { n: '3', title: 'ダウンロード', desc: 'マグネットリンクをお気に入りのトレントクライアントにコピー。' },
    ],
    faqTitle: 'よくある質問',
    faqs: [
      { q: 'Magnet Googoは無料ですか？', a: 'はい、完全無料で広告やアプリ内課金はありません。' },
      { q: '対応プラットフォームは？', a: '現在Android対応。iOS対応は計画中です。' },
      { q: 'どのように動作しますか？', a: '複数のトレント・マグネットサイトを同時検索し、結果を統合・重複排除して表示します。' },
    ],
    footer: '© 2026 Magnet Googo. すべてのマグネット。ワンサーチ。',
    langLabel: '言語',
  },
  {
    code: 'ko',
    htmlLang: 'ko',
    dir: 'ltr',
    name: '한국어',
    title: 'Magnet Googo — 무료 마그넷 & 토렌트 통합 검색 엔진',
    metaDesc: 'Magnet Googo는 여러 마그넷·토렌트 사이트를 한 번에 검색하는 무료 Android 앱입니다. 영화, 애니, 음악, 게임 — 한 번 검색으로 모든 결과. 광고 없음, 가입 불필요.',
    keywords: '마그넷 검색,토렌트 검색,마그넷 링크,무료 토렌트 검색,magnet googo,BT 검색,마그넷 다운로드,토렌트 앱',
    h1: '모든 마그넷. 한 번에 검색.',
    subtitle: 'Magnet Googo는 여러 마그넷 & 토렌트 사이트를 통합하는 무료 검색 앱입니다.',
    ctaDownload: '무료 다운로드 (APK)',
    ctaBackup: '백업 다운로드',
    features: [
      { icon: '🔍', title: '통합 검색', desc: '수십 개의 마그넷·토렌트 사이트를 동시에 검색. 한 번의 쿼리로 모든 결과.' },
      { icon: '⚡', title: '즉각 결과', desc: '병렬 멀티소스 쿼리로 몇 초 만에 결과 표시.' },
      { icon: '🚫', title: '광고 제로', desc: '완전 무료. 광고 없음, 가입 불필요, 유료 플랜 없음.' },
      { icon: '🔄', title: '항상 사용 가능', desc: '소스 자동 업데이트. 한 사이트가 다운되어도 다른 사이트가 작동.' },
      { icon: '📊', title: '스마트 랭킹', desc: '관련성, 시더 수, 파일 품질로 결과 순위 지정.' },
      { icon: '📱', title: '모바일 퍼스트', desc: 'Android 네이티브 개발. 빠르고, 가볍고, 아름다운 UI.' },
    ],
    howTitle: '사용 방법',
    howSteps: [
      { n: '1', title: '다운로드', desc: '이 페이지에서 무료 APK를 받으세요.' },
      { n: '2', title: '검색', desc: '키워드를 입력하세요 — 영화, 애니, 음악, 게임.' },
      { n: '3', title: '다운로드', desc: '마그넷 링크를 즐겨 사용하는 토렌트 클라이언트에 복사.' },
    ],
    faqTitle: '자주 묻는 질문',
    faqs: [
      { q: 'Magnet Googo는 무료인가요?', a: '네, 완전 무료이며 광고나 인앱 결제가 없습니다.' },
      { q: '지원 플랫폼은?', a: '현재 Android 지원. iOS 지원 예정.' },
      { q: '어떻게 작동하나요?', a: '여러 토렌트·마그넷 사이트를 동시에 검색하여 결과를 통합·중복 제거하여 표시합니다.' },
    ],
    footer: '© 2026 Magnet Googo. 모든 마그넷. 한 번에 검색.',
    langLabel: '언어',
  },
  {
    code: 'es',
    htmlLang: 'es',
    dir: 'ltr',
    name: 'Español',
    title: 'Magnet Googo — Motor de Búsqueda de Magnets y Torrents Gratuito',
    metaDesc: 'Magnet Googo es una app Android gratuita que agrega múltiples sitios de magnet y torrent en una sola búsqueda. Películas, anime, música, juegos — una búsqueda, todos los resultados. Sin anuncios.',
    keywords: 'búsqueda magnet,búsqueda torrent,enlace magnet,buscador de torrents gratis,magnet googo,descarga torrent,BT búsqueda',
    h1: 'Todos los magnets. Una búsqueda.',
    subtitle: 'Magnet Googo agrega múltiples sitios de magnet y torrent en una app de búsqueda gratuita.',
    ctaDownload: 'Descarga Gratis (APK)',
    ctaBackup: 'Descarga Alternativa',
    features: [
      { icon: '🔍', title: 'Búsqueda Agregada', desc: 'Busca en docenas de sitios de magnet y torrent simultáneamente.' },
      { icon: '⚡', title: 'Resultados Instantáneos', desc: 'Consultas paralelas de múltiples fuentes entregan resultados en segundos.' },
      { icon: '🚫', title: 'Sin Anuncios', desc: 'Completamente gratis. Sin anuncios, sin registro, sin planes premium.' },
      { icon: '🔄', title: 'Siempre Disponible', desc: 'Las fuentes se actualizan automáticamente. Si un sitio cae, otros siguen funcionando.' },
      { icon: '📊', title: 'Ranking Inteligente', desc: 'Resultados ordenados por relevancia, seeders y calidad del archivo.' },
      { icon: '📱', title: 'Mobile First', desc: 'Desarrollado nativamente para Android. Rápido, ligero, hermoso.' },
    ],
    howTitle: 'Cómo Funciona',
    howSteps: [
      { n: '1', title: 'Descargar', desc: 'Obtén el APK gratuito desde esta página.' },
      { n: '2', title: 'Buscar', desc: 'Ingresa cualquier palabra clave — películas, anime, música, juegos.' },
      { n: '3', title: 'Descargar', desc: 'Copia el enlace magnet a tu cliente de torrent favorito.' },
    ],
    faqTitle: 'Preguntas Frecuentes',
    faqs: [
      { q: '¿Es gratis Magnet Googo?', a: 'Sí, completamente gratis sin anuncios ni compras dentro de la app.' },
      { q: '¿Qué plataformas soporta?', a: 'Actualmente Android. Soporte para iOS está planificado.' },
      { q: '¿Cómo funciona?', a: 'Busca simultáneamente en múltiples sitios de torrent y magnet, fusiona y deduplica los resultados.' },
    ],
    footer: '© 2026 Magnet Googo. Todos los magnets. Una búsqueda.',
    langLabel: 'Idioma',
  },
  {
    code: 'fr',
    htmlLang: 'fr',
    dir: 'ltr',
    name: 'Français',
    title: 'Magnet Googo — Moteur de Recherche Magnet & Torrent Gratuit',
    metaDesc: 'Magnet Googo est une application Android gratuite qui agrège plusieurs sites magnet et torrent en une seule recherche. Films, anime, musique, jeux — une recherche, tous les résultats. Sans publicité.',
    keywords: 'recherche magnet,recherche torrent,lien magnet,moteur de recherche torrent gratuit,magnet googo,téléchargement torrent',
    h1: 'Tous les magnets. Une recherche.',
    subtitle: 'Magnet Googo agrège plusieurs sites magnet & torrent dans une application de recherche gratuite.',
    ctaDownload: 'Téléchargement Gratuit (APK)',
    ctaBackup: 'Téléchargement Alternatif',
    features: [
      { icon: '🔍', title: 'Recherche Agrégée', desc: 'Recherchez simultanément dans des dizaines de sites magnet et torrent.' },
      { icon: '⚡', title: 'Résultats Instantanés', desc: 'Les requêtes multi-sources parallèles fournissent des résultats en quelques secondes.' },
      { icon: '🚫', title: 'Zéro Publicité', desc: 'Entièrement gratuit. Pas de publicité, pas d\'inscription, pas de plan premium.' },
      { icon: '🔄', title: 'Toujours Disponible', desc: 'Les sources se mettent à jour automatiquement. Si un site tombe, les autres continuent.' },
      { icon: '📊', title: 'Classement Intelligent', desc: 'Résultats classés par pertinence, seeders et qualité du fichier.' },
      { icon: '📱', title: 'Mobile First', desc: 'Développé nativement pour Android. Rapide, léger, élégant.' },
    ],
    howTitle: 'Comment Ça Marche',
    howSteps: [
      { n: '1', title: 'Télécharger', desc: 'Obtenez l\'APK gratuit depuis cette page.' },
      { n: '2', title: 'Rechercher', desc: 'Entrez un mot-clé — films, anime, musique, jeux.' },
      { n: '3', title: 'Télécharger', desc: 'Copiez le lien magnet dans votre client torrent préféré.' },
    ],
    faqTitle: 'Questions Fréquentes',
    faqs: [
      { q: 'Magnet Googo est-il gratuit ?', a: 'Oui, entièrement gratuit sans publicité ni achats intégrés.' },
      { q: 'Quelles plateformes sont supportées ?', a: 'Actuellement Android. Le support iOS est prévu.' },
    ],
    footer: '© 2026 Magnet Googo. Tous les magnets. Une recherche.',
    langLabel: 'Langue',
  },
  {
    code: 'de',
    htmlLang: 'de',
    dir: 'ltr',
    name: 'Deutsch',
    title: 'Magnet Googo — Kostenlose Magnet- & Torrent-Suchmaschine',
    metaDesc: 'Magnet Googo ist eine kostenlose Android-App, die mehrere Magnet- und Torrent-Seiten in einer Suche vereint. Filme, Anime, Musik, Spiele — eine Suche, alle Ergebnisse. Keine Werbung.',
    keywords: 'Magnet-Suche,Torrent-Suche,Magnet-Link,kostenlose Torrent-Suchmaschine,Magnet Googo,BT-Suche,Torrent-Download',
    h1: 'Alle Magnets. Eine Suche.',
    subtitle: 'Magnet Googo vereint mehrere Magnet- & Torrent-Seiten in einer kostenlosen Such-App.',
    ctaDownload: 'Kostenlos Herunterladen (APK)',
    ctaBackup: 'Alternativer Download',
    features: [
      { icon: '🔍', title: 'Aggregierte Suche', desc: 'Durchsuchen Sie gleichzeitig Dutzende von Magnet- und Torrent-Seiten.' },
      { icon: '⚡', title: 'Sofortige Ergebnisse', desc: 'Parallele Multi-Source-Abfragen liefern Ergebnisse in Sekunden.' },
      { icon: '🚫', title: 'Keine Werbung', desc: 'Komplett kostenlos. Keine Werbung, keine Registrierung, kein Premium.' },
      { icon: '🔄', title: 'Immer Verfügbar', desc: 'Quellen werden automatisch aktualisiert. Fällt eine Seite aus, arbeiten andere weiter.' },
      { icon: '📊', title: 'Intelligentes Ranking', desc: 'Ergebnisse sortiert nach Relevanz, Seedern und Dateiqualität.' },
      { icon: '📱', title: 'Mobile First', desc: 'Nativ für Android entwickelt. Schnell, leicht, schön.' },
    ],
    howTitle: 'So Funktioniert\'s',
    howSteps: [
      { n: '1', title: 'Herunterladen', desc: 'Laden Sie die kostenlose APK von dieser Seite.' },
      { n: '2', title: 'Suchen', desc: 'Geben Sie ein Stichwort ein — Filme, Anime, Musik, Spiele.' },
      { n: '3', title: 'Herunterladen', desc: 'Kopieren Sie den Magnet-Link in Ihren Torrent-Client.' },
    ],
    faqTitle: 'Häufige Fragen',
    faqs: [
      { q: 'Ist Magnet Googo kostenlos?', a: 'Ja, komplett kostenlos ohne Werbung oder In-App-Käufe.' },
      { q: 'Welche Plattformen werden unterstützt?', a: 'Derzeit Android. iOS-Unterstützung ist geplant.' },
    ],
    footer: '© 2026 Magnet Googo. Alle Magnets. Eine Suche.',
    langLabel: 'Sprache',
  },
  {
    code: 'ru',
    htmlLang: 'ru',
    dir: 'ltr',
    name: 'Русский',
    title: 'Magnet Googo — Бесплатный агрегатор магнет-ссылок и торрентов',
    metaDesc: 'Magnet Googo — бесплатное Android-приложение для поиска магнет-ссылок по нескольким торрент-сайтам одновременно. Фильмы, аниме, музыка, игры — один поиск, все результаты. Без рекламы.',
    keywords: 'поиск магнет,поиск торрент,магнет ссылка,бесплатный торрент поиск,magnet googo,BT поиск,скачать торрент',
    h1: 'Все магнеты. Один поиск.',
    subtitle: 'Magnet Googo объединяет несколько магнет- и торрент-сайтов в одно бесплатное поисковое приложение.',
    ctaDownload: 'Скачать Бесплатно (APK)',
    ctaBackup: 'Альтернативная загрузка',
    features: [
      { icon: '🔍', title: 'Агрегированный Поиск', desc: 'Поиск по десяткам магнет- и торрент-сайтов одновременно.' },
      { icon: '⚡', title: 'Мгновенные Результаты', desc: 'Параллельные запросы к нескольким источникам выдают результаты за секунды.' },
      { icon: '🚫', title: 'Без Рекламы', desc: 'Полностью бесплатно. Без рекламы, без регистрации, без премиума.' },
      { icon: '🔄', title: 'Всегда Доступен', desc: 'Источники обновляются автоматически. Если один сайт упал, другие работают.' },
      { icon: '📊', title: 'Умный Рейтинг', desc: 'Результаты отсортированы по релевантности, сидерам и качеству файла.' },
      { icon: '📱', title: 'Mobile First', desc: 'Нативная разработка для Android. Быстро, легко, красиво.' },
    ],
    howTitle: 'Как Это Работает',
    howSteps: [
      { n: '1', title: 'Скачать', desc: 'Загрузите бесплатный APK с этой страницы.' },
      { n: '2', title: 'Искать', desc: 'Введите ключевое слово — фильмы, аниме, музыка, игры.' },
      { n: '3', title: 'Скачать', desc: 'Скопируйте магнет-ссылку в ваш торрент-клиент.' },
    ],
    faqTitle: 'Часто задаваемые вопросы',
    faqs: [
      { q: 'Magnet Googo бесплатный?', a: 'Да, полностью бесплатный без рекламы и встроенных покупок.' },
      { q: 'Какие платформы поддерживаются?', a: 'В настоящее время Android. Поддержка iOS планируется.' },
    ],
    footer: '© 2026 Magnet Googo. Все магнеты. Один поиск.',
    langLabel: 'Язык',
  },
  {
    code: 'pt',
    htmlLang: 'pt',
    dir: 'ltr',
    name: 'Português',
    title: 'Magnet Googo — Motor de Busca de Magnets e Torrents Gratuito',
    metaDesc: 'Magnet Googo é um aplicativo Android gratuito que agrega vários sites de magnet e torrent em uma única busca. Filmes, anime, música, jogos — uma busca, todos os resultados. Sem anúncios.',
    keywords: 'busca magnet,busca torrent,link magnet,buscador de torrents grátis,magnet googo,download torrent,BT busca',
    h1: 'Todos os magnets. Uma busca.',
    subtitle: 'Magnet Googo agrega vários sites de magnet & torrent em um aplicativo de busca gratuito.',
    ctaDownload: 'Download Grátis (APK)',
    ctaBackup: 'Download Alternativo',
    features: [
      { icon: '🔍', title: 'Busca Agregada', desc: 'Pesquise em dezenas de sites de magnet e torrent simultaneamente.' },
      { icon: '⚡', title: 'Resultados Instantâneos', desc: 'Consultas paralelas de múltiplas fontes entregam resultados em segundos.' },
      { icon: '🚫', title: 'Zero Anúncios', desc: 'Completamente grátis. Sem anúncios, sem registro, sem plano premium.' },
      { icon: '🔄', title: 'Sempre Disponível', desc: 'Fontes se atualizam automaticamente. Se um site cai, outros continuam.' },
      { icon: '📊', title: 'Ranking Inteligente', desc: 'Resultados classificados por relevância, seeders e qualidade do arquivo.' },
      { icon: '📱', title: 'Mobile First', desc: 'Desenvolvido nativamente para Android. Rápido, leve, bonito.' },
    ],
    howTitle: 'Como Funciona',
    howSteps: [
      { n: '1', title: 'Baixar', desc: 'Obtenha o APK gratuito desta página.' },
      { n: '2', title: 'Buscar', desc: 'Digite qualquer palavra-chave — filmes, anime, música, jogos.' },
      { n: '3', title: 'Baixar', desc: 'Copie o link magnet para seu cliente de torrent favorito.' },
    ],
    faqTitle: 'Perguntas Frequentes',
    faqs: [
      { q: 'O Magnet Googo é grátis?', a: 'Sim, completamente grátis sem anúncios ou compras no app.' },
      { q: 'Quais plataformas são suportadas?', a: 'Atualmente Android. Suporte iOS está planejado.' },
    ],
    footer: '© 2026 Magnet Googo. Todos os magnets. Uma busca.',
    langLabel: 'Idioma',
  },
  {
    code: 'ar',
    htmlLang: 'ar',
    dir: 'rtl',
    name: 'العربية',
    title: 'Magnet Googo — محرك بحث مغناطيس وتورنت مجاني',
    metaDesc: 'Magnet Googo هو تطبيق Android مجاني يجمع عدة مواقع مغناطيس وتورنت في بحث واحد. أفلام، أنمي، موسيقى، ألعاب — بحث واحد، كل النتائج. بدون إعلانات.',
    keywords: 'بحث مغناطيس,بحث تورنت,رابط مغناطيس,محرك بحث تورنت مجاني,magnet googo,تحميل تورنت',
    h1: 'جميع المغناطيسات. بحث واحد.',
    subtitle: 'Magnet Googo يجمع عدة مواقع مغناطيس وتورنت في تطبيق بحث مجاني واحد.',
    ctaDownload: 'تحميل مجاني (APK)',
    ctaBackup: 'تحميل بديل',
    features: [
      { icon: '🔍', title: 'بحث مجمّع', desc: 'ابحث في عشرات مواقع المغناطيس والتورنت في وقت واحد.' },
      { icon: '⚡', title: 'نتائج فورية', desc: 'استعلامات متوازية من مصادر متعددة تقدم النتائج في ثوانٍ.' },
      { icon: '🚫', title: 'بدون إعلانات', desc: 'مجاني بالكامل. بدون إعلانات، بدون تسجيل، بدون خطط مدفوعة.' },
      { icon: '🔄', title: 'متاح دائماً', desc: 'المصادر تتحدث تلقائياً. إذا توقف موقع، تعمل المواقع الأخرى.' },
      { icon: '📊', title: 'ترتيب ذكي', desc: 'النتائج مرتبة حسب الصلة وعدد المشاركين وجودة الملف.' },
      { icon: '📱', title: 'للجوال أولاً', desc: 'مطوّر أصلياً لنظام Android. سريع، خفيف، جميل.' },
    ],
    howTitle: 'كيف يعمل',
    howSteps: [
      { n: '1', title: 'تحميل', desc: 'احصل على APK المجاني من هذه الصفحة.' },
      { n: '2', title: 'بحث', desc: 'أدخل أي كلمة — أفلام، أنمي، موسيقى، ألعاب.' },
      { n: '3', title: 'تحميل', desc: 'انسخ رابط المغناطيس إلى عميل التورنت المفضل لديك.' },
    ],
    faqTitle: 'الأسئلة الشائعة',
    faqs: [
      { q: 'هل Magnet Googo مجاني؟', a: 'نعم، مجاني بالكامل بدون إعلانات أو مشتريات داخل التطبيق.' },
      { q: 'ما المنصات المدعومة؟', a: 'حالياً Android. دعم iOS مخطط له.' },
    ],
    footer: '© 2026 Magnet Googo. جميع المغناطيسات. بحث واحد.',
    langLabel: 'اللغة',
  },
];

// All language codes for hreflang tags
const ALL_LANG_CODES = ['zh', ...LANGS.map(l => l.code)];
const LANG_SELECTOR = [{ code: 'zh', name: '中文', path: '../' }, ...LANGS.map(l => ({ code: l.code, name: l.name, path: `../${l.code}/` }))];

// ─── HTML Generator ─────────────────────────────────────────────────

function generateLandingPage(lang) {
  const today = new Date().toISOString().slice(0, 10);
  const dirAttr = lang.dir === 'rtl' ? ' dir="rtl"' : '';

  const hreflangTags = ALL_LANG_CODES.map(code => {
    const href = code === 'zh' ? 'https://magnetgoogo.com/' : `https://magnetgoogo.com/${code}/`;
    return `    <link rel="alternate" hreflang="${code}" href="${href}">`;
  }).join('\n');

  const langSelectorHtml = LANG_SELECTOR.map(l =>
    l.code === lang.code
      ? `<span class="text-brand font-semibold">${l.name}</span>`
      : `<a href="${l.path}" class="text-gray-400 hover:text-brand">${l.name}</a>`
  ).join(' · ');

  return `<!DOCTYPE html>
<html lang="${lang.htmlLang}"${dirAttr}>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${lang.title}</title>
    <meta name="description" content="${lang.metaDesc}">
    <meta name="keywords" content="${lang.keywords}">
    <link rel="canonical" href="https://magnetgoogo.com/${lang.code}/">
${hreflangTags}
    <link rel="alternate" hreflang="x-default" href="https://magnetgoogo.com/">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="${lang.title}">
    <meta property="og:description" content="${lang.metaDesc}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://magnetgoogo.com/${lang.code}/">
    <meta property="og:image" content="https://magnetgoogo.com/images/app-icon-lg.png">
    <meta property="og:site_name" content="Magnet Googo">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="${lang.title}">
    <meta name="twitter:description" content="${lang.metaDesc}">
    <link rel="icon" type="image/png" href="../images/app-icon.png">
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      "name": "Magnet Googo",
      "operatingSystem": "Android",
      "applicationCategory": "UtilitiesApplication",
      "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
      "description": "${lang.metaDesc}",
      "url": "https://magnetgoogo.com/${lang.code}/"
    }
    </script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config={theme:{extend:{colors:{brand:'#4285F4',brandGreen:'#34A853'}}}}</script>
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", "PingFang SC", sans-serif; }
      .grad-btn { background: linear-gradient(135deg, #4285F4, #34A853); }
      .grad-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(66,133,244,.35); transition: all .2s; }
    </style>
</head>
<body class="bg-gray-50 text-gray-800 antialiased">

<!-- NAV -->
<nav class="bg-white border-b border-gray-100 sticky top-0 z-50">
  <div class="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
    <a href="../" class="flex items-center gap-2">
      <img src="../images/app-icon-sm.png" alt="Magnet Googo" class="w-8 h-8">
      <span class="font-bold text-gray-800">Magnet Googo</span>
    </a>
    <a href="${downloadUrl}" class="grad-btn text-white text-sm font-medium px-4 py-2 rounded-full inline-flex items-center gap-1.5">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
      ${lang.ctaDownload}
    </a>
  </div>
</nav>

<!-- HERO -->
<section class="bg-gradient-to-br from-blue-50 via-white to-green-50 py-16 md:py-24">
  <div class="max-w-5xl mx-auto px-6 text-center">
    <h1 class="text-3xl md:text-5xl font-extrabold text-gray-900 mb-4 leading-tight">${lang.h1}</h1>
    <p class="text-lg md:text-xl text-gray-500 mb-8 max-w-2xl mx-auto">${lang.subtitle}</p>
    <div class="flex flex-col sm:flex-row gap-3 justify-center">
      <a href="${downloadUrl}" class="grad-btn text-white font-bold px-8 py-4 rounded-full text-lg inline-flex items-center justify-center gap-2 shadow-lg">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
        ${lang.ctaDownload}
      </a>
${backupDownloads.map((item) => `      <a href="${item.url}" target="_blank" rel="noopener" class="border-2 border-gray-200 text-gray-600 font-medium px-6 py-4 rounded-full text-base hover:border-brand hover:text-brand transition-colors">
        ${item.label === '蓝奏云' ? `LanzouCloud · PIN ${item.password || '8888'}` : item.label}
      </a>`).join('\n')}
    </div>
    <p class="mt-4 text-sm text-gray-400">Android 7.0+ · APK 36.7MB · v0.2.5</p>
  </div>
</section>

<!-- FEATURES -->
<section class="py-16 bg-white">
  <div class="max-w-5xl mx-auto px-6">
    <div class="grid md:grid-cols-3 gap-8">
${lang.features.map(f => `      <div class="text-center p-6">
        <div class="text-4xl mb-4">${f.icon}</div>
        <h3 class="font-bold text-lg mb-2">${f.title}</h3>
        <p class="text-gray-500">${f.desc}</p>
      </div>`).join('\n')}
    </div>
  </div>
</section>

<!-- HOW IT WORKS -->
<section class="py-16 bg-gray-50">
  <div class="max-w-5xl mx-auto px-6">
    <h2 class="text-2xl md:text-3xl font-bold text-center mb-12">${lang.howTitle}</h2>
    <div class="grid md:grid-cols-3 gap-8">
${lang.howSteps.map(s => `      <div class="bg-white rounded-2xl p-8 text-center shadow-sm border border-gray-100">
        <div class="w-12 h-12 bg-brand text-white rounded-full flex items-center justify-center text-xl font-bold mx-auto mb-4">${s.n}</div>
        <h3 class="font-bold text-lg mb-2">${s.title}</h3>
        <p class="text-gray-500">${s.desc}</p>
      </div>`).join('\n')}
    </div>
  </div>
</section>

<!-- FAQ -->
<section class="py-16 bg-white">
  <div class="max-w-3xl mx-auto px-6">
    <h2 class="text-2xl font-bold text-center mb-8">${lang.faqTitle}</h2>
${lang.faqs.map(f => `    <div class="border-b border-gray-100 py-4">
      <h3 class="font-semibold text-gray-900 mb-1">${f.q}</h3>
      <p class="text-gray-500">${f.a}</p>
    </div>`).join('\n')}
  </div>
</section>

<!-- BOTTOM CTA -->
<section class="py-16 bg-gradient-to-r from-blue-600 to-green-500 text-white text-center">
  <div class="max-w-3xl mx-auto px-6">
    <h2 class="text-2xl md:text-3xl font-bold mb-4">${lang.h1}</h2>
    <p class="mb-8 opacity-90">${lang.subtitle}</p>
    <a href="${downloadUrl}" class="bg-white text-blue-600 font-bold px-10 py-4 rounded-full text-lg inline-block hover:shadow-xl transition-shadow">
      ${lang.ctaDownload}
    </a>
  </div>
</section>

<!-- FOOTER -->
<footer class="border-t border-gray-100 py-8 bg-white">
  <div class="max-w-5xl mx-auto px-6 text-center text-sm text-gray-400">
    <p class="mb-3">${lang.langLabel}: ${langSelectorHtml}</p>
    <p>${lang.footer}</p>
  </div>
</footer>

</body>
</html>`;
}

// ─── MAIN ────────────────────────────────────────────────────────────

function main() {
  let count = 0;

  for (const lang of LANGS) {
    const outDir = path.join(SITE_DIR, lang.code);
    if (!fs.existsSync(outDir)) {
      fs.mkdirSync(outDir, { recursive: true });
    }
    const html = generateLandingPage(lang);
    fs.writeFileSync(path.join(outDir, 'index.html'), html, 'utf-8');
    count++;
  }

  // Update sitemap
  const sitemapPath = path.join(SITE_DIR, 'sitemap.xml');
  const today = new Date().toISOString().slice(0, 10);
  const entries = LANGS.map(l =>
    `  <url><loc>https://magnetgoogo.com/${l.code}/</loc><lastmod>${today}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>`
  ).join('\n');

  if (fs.existsSync(sitemapPath)) {
    let sitemap = fs.readFileSync(sitemapPath, 'utf-8');
    // Remove old i18n entries
    for (const l of LANGS) {
      sitemap = sitemap.replace(new RegExp(`\\n.*magnetgoogo\\.com\\/${l.code}\\/.*\\n?`, 'g'), '\n');
    }
    sitemap = sitemap.replace('</urlset>', `${entries}\n</urlset>`);
    fs.writeFileSync(sitemapPath, sitemap, 'utf-8');
    console.log('✅ Updated sitemap.xml with i18n pages');
  }

  // Also add hreflang to main index.html if not already present
  const mainIndex = path.join(SITE_DIR, 'index.html');
  if (fs.existsSync(mainIndex)) {
    let html = fs.readFileSync(mainIndex, 'utf-8');
    if (!html.includes('hreflang="es"')) {
      const hreflangTags = LANGS.map(l =>
        `    <link rel="alternate" hreflang="${l.code}" href="https://magnetgoogo.com/${l.code}/">`
      ).join('\n');
      // Insert after existing hreflang tags
      if (html.includes('hreflang="x-default"')) {
        html = html.replace(
          /(<link rel="alternate" hreflang="x-default"[^>]*>)/,
          `$1\n${hreflangTags}`
        );
        fs.writeFileSync(mainIndex, html, 'utf-8');
        console.log('✅ Added hreflang tags to main index.html');
      }
    }
  }

  console.log(`\n🚀 Generated ${count} i18n landing pages`);
  console.log(`   Languages: ${LANGS.map(l => l.code).join(', ')}`);
}

main();
