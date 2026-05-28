#!/usr/bin/env node
/**
 * 多语言 SEO 关键词指南页生成器
 * 为每种语言生成本地化的磁力/种子搜索关键词着陆页
 * 输出到 magnetgoogo-site/{lang}/guide/ 目录
 */

const fs = require('fs');
const path = require('path');

const SITE_DIR = path.join(__dirname, '..', 'magnetgoogo-site');
const downloadUrl = 'https://api.naoshiquan.com/download/v0.1.8/MagGoogo-v0.1.8.apk';

// ─── 各语言关键词数据库 ──────────────────────────────────────────────

const LANG_KEYWORDS = {
  ja: {
    name: '日本語', htmlLang: 'ja', dir: 'ltr',
    indexTitle: 'マグネット検索ガイド — Magnet Googo',
    indexDesc: 'マグネット＆トレント検索に関する完全ガイド。無料ダウンロード方法、おすすめアプリ、使い方を解説。',
    ctaBtn: '無料ダウンロード',
    backToHome: 'ホームに戻る',
    guideIndex: 'ガイド一覧',
    whyTitle: 'なぜ Magnet Googo？',
    whyItems: ['数十のサイトを同時検索','広告ゼロ・完全無料','自動ソース更新','スマートランキング'],
    keywords: [
      {
        slug: 'magnet-kensaku', title: 'マグネット検索エンジンおすすめ【2026年最新】',
        metaDesc: '2026年最新のマグネット検索エンジンを比較。無料で使えるおすすめマグネット検索ツールを紹介。Magnet Googoなら複数サイトを一括検索。',
        metaKeywords: 'マグネット検索,マグネット検索エンジン,magnet検索,マグネットリンク検索,無料マグネット検索',
        h1: '2026年 おすすめマグネット検索エンジン',
        sections: [
          { h2: 'マグネット検索とは？', body: 'マグネットリンクは、P2Pネットワーク上のファイルを特定するためのURIスキームです。従来のトレントファイルと異なり、トラッカーサーバーを必要とせず、ファイルのハッシュ値だけでダウンロードを開始できます。' },
          { h2: 'おすすめマグネット検索エンジン', body: 'Magnet Googoは複数のマグネット検索サイトを同時に検索する無料Androidアプリです。', list: ['複数サイトを一括検索','結果を自動統合・重複排除','広告なし・登録不要','常に最新のソースに自動更新'] },
          { h2: 'マグネットリンクの使い方', body: 'マグネットリンクを使うには、BitTorrentクライアント（qBittorrent、Transmissionなど）が必要です。リンクをコピーしてクライアントに貼り付けるだけでダウンロードが始まります。' },
        ]
      },
      {
        slug: 'torrent-kensaku', title: 'トレント検索サイトおすすめ【無料・安全】',
        metaDesc: '安全で無料のトレント検索サイトを紹介。ウイルスなし、広告なしのトレント検索方法を解説。',
        metaKeywords: 'トレント検索,トレントサイト,torrent検索,無料トレント,トレントダウンロード',
        h1: '安全なトレント検索サイトおすすめ',
        sections: [
          { h2: 'トレント検索の基礎知識', body: 'トレント（BitTorrent）は、大容量ファイルを効率的に共有するためのP2Pプロトコルです。映画、音楽、ソフトウェアなど、様々なファイルをダウンロードできます。' },
          { h2: '安全にトレントを検索する方法', body: 'Magnet Googoを使えば、複数のトレントサイトを安全に一括検索できます。', list: ['怪しい広告サイトにアクセスする必要なし','結果の自動フィルタリング','ウイルスリスクの低減','VPN推奨'] },
        ]
      },
      {
        slug: 'anime-torrent', title: 'アニメ トレント検索 — 無料で安全にダウンロード',
        metaDesc: 'アニメのトレント・マグネットリンクを安全に検索する方法。最新アニメから名作まで、無料で検索。',
        metaKeywords: 'アニメ トレント,アニメ マグネット,anime torrent,アニメ ダウンロード,アニメ 無料',
        h1: 'アニメ トレント検索ガイド',
        sections: [
          { h2: 'アニメトレントの検索方法', body: 'Magnet Googoはアニメ専門のトレントサイトを含む複数のソースを同時検索します。日本語タイトルでも英語タイトルでも検索可能です。' },
          { h2: 'おすすめの検索テクニック', body: 'アニメを効率的に見つけるためのコツ：', list: ['作品名+解像度で検索（例：進撃の巨人 1080p）','字幕グループ名で検索','シーズン番号を含める','英語タイトルでも試す'] },
        ]
      },
      {
        slug: 'eiga-download', title: '映画ダウンロード — マグネットリンクで無料検索',
        metaDesc: '映画のマグネットリンクを検索する方法。洋画・邦画・最新映画のトレントを安全に検索。',
        metaKeywords: '映画 ダウンロード,映画 マグネット,映画 トレント,movie download,映画 無料',
        h1: '映画マグネットリンク検索ガイド',
        sections: [
          { h2: '映画のマグネットリンクを検索', body: 'Magnet Googoで映画タイトルを入力するだけで、複数のトレントサイトから結果を一括取得できます。' },
          { h2: '高画質な映画を見つけるコツ', body: '映画の品質を判断するポイント：', list: ['1080pまたは4K表記を確認','ファイルサイズが大きいほど高画質','シーダー数が多いほどダウンロード速度が速い','リリースグループの評判を確認'] },
        ]
      },
    ]
  },
  ko: {
    name: '한국어', htmlLang: 'ko', dir: 'ltr',
    indexTitle: '마그넷 검색 가이드 — Magnet Googo',
    indexDesc: '마그넷 & 토렌트 검색에 관한 완전 가이드. 무료 다운로드 방법, 추천 앱, 사용법 안내.',
    ctaBtn: '무료 다운로드',
    backToHome: '홈으로',
    guideIndex: '가이드 목록',
    whyTitle: '왜 Magnet Googo?',
    whyItems: ['수십 개 사이트 동시 검색','광고 제로·완전 무료','자동 소스 업데이트','스마트 랭킹'],
    keywords: [
      {
        slug: 'magnet-geomsakgi', title: '마그넷 검색엔진 추천【2026년 최신】',
        metaDesc: '2026년 최신 마그넷 검색엔진 비교. 무료 마그넷 검색 도구 추천. Magnet Googo로 여러 사이트를 한번에 검색.',
        metaKeywords: '마그넷 검색,마그넷 검색엔진,magnet 검색,마그넷 링크 검색,무료 마그넷 검색,토렌트 검색',
        h1: '2026년 추천 마그넷 검색엔진',
        sections: [
          { h2: '마그넷 검색이란?', body: '마그넷 링크는 P2P 네트워크에서 파일을 식별하기 위한 URI 방식입니다. 트래커 서버 없이 파일 해시값만으로 다운로드를 시작할 수 있습니다.' },
          { h2: '추천 마그넷 검색엔진', body: 'Magnet Googo는 여러 마그넷 검색 사이트를 동시에 검색하는 무료 Android 앱입니다.', list: ['여러 사이트 한번에 검색','결과 자동 통합·중복 제거','광고 없음·가입 불필요','최신 소스 자동 업데이트'] },
        ]
      },
      {
        slug: 'torrent-geomsakgi', title: '토렌트 검색 사이트 추천【무료·안전】',
        metaDesc: '안전하고 무료인 토렌트 검색 사이트를 소개. 바이러스 없이, 광고 없이 토렌트를 검색하는 방법.',
        metaKeywords: '토렌트 검색,토렌트 사이트,torrent 검색,무료 토렌트,토렌트 다운로드,토렌트 추천',
        h1: '안전한 토렌트 검색 사이트 추천',
        sections: [
          { h2: '토렌트 검색 기초', body: '토렌트(BitTorrent)는 대용량 파일을 효율적으로 공유하기 위한 P2P 프로토콜입니다.' },
          { h2: '안전하게 토렌트를 검색하는 방법', body: 'Magnet Googo를 사용하면 여러 토렌트 사이트를 안전하게 한번에 검색할 수 있습니다.', list: ['수상한 광고 사이트 방문 불필요','결과 자동 필터링','바이러스 위험 감소','VPN 권장'] },
        ]
      },
      {
        slug: 'yeonghwa-download', title: '영화 다운로드 — 마그넷 링크로 무료 검색',
        metaDesc: '영화 마그넷 링크를 검색하는 방법. 최신 영화부터 클래식까지 토렌트를 안전하게 검색.',
        metaKeywords: '영화 다운로드,영화 마그넷,영화 토렌트,movie download,영화 무료',
        h1: '영화 마그넷 링크 검색 가이드',
        sections: [
          { h2: '영화 마그넷 링크 검색', body: 'Magnet Googo에서 영화 제목을 입력하면 여러 토렌트 사이트에서 결과를 한번에 가져옵니다.' },
          { h2: '고화질 영화 찾는 팁', body: '영화 품질을 판단하는 포인트:', list: ['1080p 또는 4K 표기 확인','파일 크기가 클수록 고화질','시더 수가 많을수록 다운로드 속도 빠름'] },
        ]
      },
      {
        slug: 'anime-torrent-ko', title: '애니메이션 토렌트 검색 — 무료 다운로드',
        metaDesc: '애니메이션 토렌트·마그넷 링크를 안전하게 검색하는 방법. 최신 애니부터 명작까지.',
        metaKeywords: '애니 토렌트,애니메이션 마그넷,anime torrent,애니 다운로드',
        h1: '애니메이션 토렌트 검색 가이드',
        sections: [
          { h2: '애니 토렌트 검색 방법', body: 'Magnet Googo는 애니메이션 전문 토렌트 사이트를 포함한 여러 소스를 동시에 검색합니다.' },
          { h2: '효율적인 검색 팁', body: '애니를 효율적으로 찾는 방법:', list: ['작품명+해상도로 검색','자막 그룹명으로 검색','시즌 번호 포함','영어 제목도 시도'] },
        ]
      },
    ]
  },
  es: {
    name: 'Español', htmlLang: 'es', dir: 'ltr',
    indexTitle: 'Guía de Búsqueda de Magnets — Magnet Googo',
    indexDesc: 'Guía completa sobre búsqueda de magnets y torrents. Métodos de descarga gratuita, apps recomendadas y tutoriales.',
    ctaBtn: 'Descarga Gratis',
    backToHome: 'Volver al inicio',
    guideIndex: 'Índice de guías',
    whyTitle: '¿Por qué Magnet Googo?',
    whyItems: ['Busca en docenas de sitios a la vez','Cero anuncios · Totalmente gratis','Actualización automática de fuentes','Ranking inteligente'],
    keywords: [
      {
        slug: 'buscar-magnets', title: 'Buscador de Magnets Gratis【2026】— Los Mejores',
        metaDesc: 'Los mejores buscadores de magnets y torrents de 2026. Busca magnets gratis con Magnet Googo, el agregador definitivo.',
        metaKeywords: 'buscar magnets,buscador de magnets,buscar torrents,descargar magnets gratis,magnet search,buscador torrent',
        h1: 'Los Mejores Buscadores de Magnets 2026',
        sections: [
          { h2: '¿Qué es un enlace magnet?', body: 'Un enlace magnet es un URI que identifica archivos en redes P2P sin necesidad de un archivo .torrent. Solo necesitas el hash del archivo para iniciar la descarga.' },
          { h2: 'El mejor buscador de magnets', body: 'Magnet Googo es una app Android gratuita que busca en múltiples sitios de magnets simultáneamente.', list: ['Búsqueda en múltiples sitios a la vez','Resultados unificados y sin duplicados','Sin anuncios ni registro','Fuentes siempre actualizadas'] },
        ]
      },
      {
        slug: 'descargar-torrents', title: 'Cómo Descargar Torrents Gratis y Seguro【Guía 2026】',
        metaDesc: 'Guía completa para descargar torrents de forma segura y gratuita. Las mejores herramientas y consejos.',
        metaKeywords: 'descargar torrents,torrents gratis,descargar peliculas torrent,bajar torrents,torrent seguro',
        h1: 'Guía para Descargar Torrents de Forma Segura',
        sections: [
          { h2: 'Descarga de torrents paso a paso', body: 'Descargar torrents es sencillo si sigues los pasos correctos y usas las herramientas adecuadas.' },
          { h2: 'Consejos de seguridad', body: 'Para descargar torrents de forma segura:', list: ['Usa Magnet Googo para buscar de forma segura','Instala un cliente BitTorrent confiable (qBittorrent)','Considera usar una VPN','Verifica el número de seeders antes de descargar'] },
        ]
      },
      {
        slug: 'peliculas-torrent', title: 'Descargar Películas por Torrent — Búsqueda Gratuita',
        metaDesc: 'Busca y descarga películas por torrent de forma gratuita. Estrenos, clásicos y series en español.',
        metaKeywords: 'peliculas torrent,descargar peliculas,peliculas magnet,movies torrent,peliculas gratis',
        h1: 'Descargar Películas por Torrent',
        sections: [
          { h2: 'Buscar películas por torrent', body: 'Con Magnet Googo, busca el título de cualquier película y obtén resultados de múltiples sitios al instante.' },
          { h2: 'Encontrar películas en alta calidad', body: 'Consejos para encontrar la mejor calidad:', list: ['Busca con "1080p" o "4K" junto al título','Archivos más grandes = mejor calidad','Más seeders = descarga más rápida','Busca en español o inglés para más resultados'] },
        ]
      },
      {
        slug: 'series-torrent', title: 'Descargar Series por Torrent — Guía Completa',
        metaDesc: 'Cómo buscar y descargar series por torrent. Series en español, anime y más.',
        metaKeywords: 'series torrent,descargar series,series magnet,anime torrent español',
        h1: 'Guía para Descargar Series por Torrent',
        sections: [
          { h2: 'Series por torrent', body: 'Magnet Googo te permite buscar series de TV, anime y documentales en múltiples sitios a la vez.' },
          { h2: 'Tips para buscar series', body: 'Cómo encontrar series eficientemente:', list: ['Incluye el nombre de la temporada (S01E01)','Busca en el idioma original para más resultados','Filtra por tamaño para calidad deseada'] },
        ]
      },
    ]
  },
  fr: {
    name: 'Français', htmlLang: 'fr', dir: 'ltr',
    indexTitle: 'Guide de Recherche Magnet — Magnet Googo',
    indexDesc: 'Guide complet sur la recherche de magnets et torrents. Téléchargement gratuit, apps recommandées, tutoriels.',
    ctaBtn: 'Téléchargement Gratuit',
    backToHome: 'Retour à l\'accueil',
    guideIndex: 'Index des guides',
    whyTitle: 'Pourquoi Magnet Googo ?',
    whyItems: ['Recherche sur des dizaines de sites','Zéro publicité · Gratuit','Mise à jour automatique des sources','Classement intelligent'],
    keywords: [
      {
        slug: 'recherche-magnet', title: 'Moteur de Recherche Magnet Gratuit【2026】',
        metaDesc: 'Les meilleurs moteurs de recherche magnet et torrent de 2026. Recherchez gratuitement avec Magnet Googo.',
        metaKeywords: 'recherche magnet,moteur de recherche torrent,télécharger magnet,recherche torrent gratuit,magnet search',
        h1: 'Meilleurs Moteurs de Recherche Magnet 2026',
        sections: [
          { h2: 'Qu\'est-ce qu\'un lien magnet ?', body: 'Un lien magnet est un URI qui identifie des fichiers sur les réseaux P2P sans avoir besoin d\'un fichier .torrent.' },
          { h2: 'Le meilleur outil de recherche', body: 'Magnet Googo est une app Android gratuite qui recherche simultanément sur plusieurs sites magnet.', list: ['Recherche multi-sites simultanée','Résultats unifiés sans doublons','Sans publicité ni inscription','Sources toujours à jour'] },
        ]
      },
      {
        slug: 'telecharger-torrent', title: 'Comment Télécharger des Torrents — Guide Sécurisé',
        metaDesc: 'Guide complet pour télécharger des torrents en toute sécurité. Outils recommandés et conseils pratiques.',
        metaKeywords: 'télécharger torrent,torrent gratuit,télécharger films torrent,torrent sécurisé,client torrent',
        h1: 'Guide pour Télécharger des Torrents en Sécurité',
        sections: [
          { h2: 'Téléchargement de torrents', body: 'Télécharger des torrents est simple si vous suivez les bonnes pratiques et utilisez les bons outils.' },
          { h2: 'Conseils de sécurité', body: 'Pour télécharger en toute sécurité :', list: ['Utilisez Magnet Googo pour rechercher en sécurité','Installez un client BitTorrent fiable','Envisagez l\'utilisation d\'un VPN','Vérifiez le nombre de seeders'] },
        ]
      },
      {
        slug: 'films-torrent', title: 'Télécharger des Films par Torrent — Recherche Gratuite',
        metaDesc: 'Recherchez et téléchargez des films par torrent gratuitement. Dernières sorties, classiques et séries.',
        metaKeywords: 'films torrent,télécharger films,films magnet,movies torrent,films gratuit',
        h1: 'Télécharger des Films par Torrent',
        sections: [
          { h2: 'Rechercher des films', body: 'Avec Magnet Googo, recherchez n\'importe quel titre de film et obtenez des résultats de plusieurs sites instantanément.' },
          { h2: 'Trouver des films en haute qualité', body: 'Conseils pour la meilleure qualité :', list: ['Recherchez avec "1080p" ou "4K"','Fichiers plus gros = meilleure qualité','Plus de seeders = téléchargement plus rapide'] },
        ]
      },
    ]
  },
  de: {
    name: 'Deutsch', htmlLang: 'de', dir: 'ltr',
    indexTitle: 'Magnet-Suchratgeber — Magnet Googo',
    indexDesc: 'Kompletter Ratgeber zur Magnet- und Torrent-Suche. Kostenlose Download-Methoden, empfohlene Apps und Anleitungen.',
    ctaBtn: 'Kostenlos Herunterladen',
    backToHome: 'Zurück zur Startseite',
    guideIndex: 'Ratgeber-Übersicht',
    whyTitle: 'Warum Magnet Googo?',
    whyItems: ['Dutzende Seiten gleichzeitig durchsuchen','Keine Werbung · Komplett kostenlos','Automatische Quellen-Updates','Intelligentes Ranking'],
    keywords: [
      {
        slug: 'magnet-suchmaschine', title: 'Beste Magnet-Suchmaschine 2026 — Kostenlos',
        metaDesc: 'Die besten Magnet- und Torrent-Suchmaschinen 2026 im Vergleich. Kostenlos suchen mit Magnet Googo.',
        metaKeywords: 'Magnet Suchmaschine,Torrent Suchmaschine,Magnet suchen,Torrent suchen,kostenlos Torrent',
        h1: 'Beste Magnet-Suchmaschinen 2026',
        sections: [
          { h2: 'Was ist ein Magnet-Link?', body: 'Ein Magnet-Link ist ein URI-Schema, das Dateien in P2P-Netzwerken identifiziert, ohne eine .torrent-Datei zu benötigen.' },
          { h2: 'Die beste Magnet-Suchmaschine', body: 'Magnet Googo ist eine kostenlose Android-App, die gleichzeitig mehrere Magnet-Seiten durchsucht.', list: ['Gleichzeitige Suche auf mehreren Seiten','Vereinigte Ergebnisse ohne Duplikate','Ohne Werbung oder Registrierung','Immer aktuelle Quellen'] },
        ]
      },
      {
        slug: 'torrent-herunterladen', title: 'Torrents Sicher Herunterladen — Anleitung 2026',
        metaDesc: 'Anleitung zum sicheren Herunterladen von Torrents. Empfohlene Tools und Sicherheitstipps.',
        metaKeywords: 'Torrent herunterladen,Torrent Download,sicher Torrent,kostenlos Torrent,BitTorrent Anleitung',
        h1: 'Torrents Sicher Herunterladen — Anleitung',
        sections: [
          { h2: 'Torrents herunterladen', body: 'Das Herunterladen von Torrents ist einfach, wenn Sie die richtigen Werkzeuge verwenden.' },
          { h2: 'Sicherheitstipps', body: 'Für sicheres Herunterladen:', list: ['Verwenden Sie Magnet Googo für sichere Suche','Installieren Sie einen vertrauenswürdigen BitTorrent-Client','Nutzen Sie ein VPN','Prüfen Sie die Seeder-Anzahl'] },
        ]
      },
      {
        slug: 'filme-torrent', title: 'Filme per Torrent Herunterladen — Kostenlose Suche',
        metaDesc: 'Filme per Torrent suchen und herunterladen. Neuerscheinungen, Klassiker und Serien.',
        metaKeywords: 'Filme Torrent,Filme herunterladen,Filme Magnet,Movie Download,Filme kostenlos',
        h1: 'Filme per Torrent Herunterladen',
        sections: [
          { h2: 'Filme per Torrent suchen', body: 'Mit Magnet Googo geben Sie einfach den Filmtitel ein und erhalten Ergebnisse von mehreren Seiten.' },
          { h2: 'Filme in hoher Qualität finden', body: 'Tipps für die beste Qualität:', list: ['Suchen Sie mit "1080p" oder "4K"','Größere Dateien = bessere Qualität','Mehr Seeder = schnellerer Download'] },
        ]
      },
    ]
  },
  ru: {
    name: 'Русский', htmlLang: 'ru', dir: 'ltr',
    indexTitle: 'Руководство по поиску магнетов — Magnet Googo',
    indexDesc: 'Полное руководство по поиску магнет-ссылок и торрентов. Бесплатные методы загрузки, рекомендуемые приложения.',
    ctaBtn: 'Скачать бесплатно',
    backToHome: 'На главную',
    guideIndex: 'Список руководств',
    whyTitle: 'Почему Magnet Googo?',
    whyItems: ['Поиск по десяткам сайтов одновременно','Без рекламы · Бесплатно','Автообновление источников','Умный рейтинг'],
    keywords: [
      {
        slug: 'poisk-magnet', title: 'Лучшие поисковики магнет-ссылок 2026 — Бесплатно',
        metaDesc: 'Лучшие поисковики магнет-ссылок и торрентов 2026 года. Бесплатный поиск с Magnet Googo.',
        metaKeywords: 'поиск магнет,поиск торрент,магнет ссылка поиск,бесплатный торрент поиск,торрент поисковик',
        h1: 'Лучшие поисковики магнет-ссылок 2026',
        sections: [
          { h2: 'Что такое магнет-ссылка?', body: 'Магнет-ссылка — это URI-схема для идентификации файлов в P2P-сетях без необходимости в .torrent файле.' },
          { h2: 'Лучший поисковик магнетов', body: 'Magnet Googo — бесплатное Android-приложение для одновременного поиска по нескольким магнет-сайтам.', list: ['Поиск по нескольким сайтам одновременно','Объединённые результаты без дубликатов','Без рекламы и регистрации','Источники всегда актуальны'] },
        ]
      },
      {
        slug: 'skachat-torrent', title: 'Как безопасно скачать торрент — Руководство 2026',
        metaDesc: 'Руководство по безопасному скачиванию торрентов. Рекомендуемые инструменты и советы.',
        metaKeywords: 'скачать торрент,торрент бесплатно,скачать фильмы торрент,безопасный торрент,торрент клиент',
        h1: 'Как безопасно скачать торрент',
        sections: [
          { h2: 'Загрузка торрентов', body: 'Скачивание торрентов просто, если использовать правильные инструменты.' },
          { h2: 'Советы по безопасности', body: 'Для безопасного скачивания:', list: ['Используйте Magnet Googo для безопасного поиска','Установите надёжный BitTorrent-клиент','Используйте VPN','Проверяйте количество сидеров'] },
        ]
      },
      {
        slug: 'filmy-torrent', title: 'Скачать фильмы через торрент — Бесплатный поиск',
        metaDesc: 'Ищите и скачивайте фильмы через торрент бесплатно. Новинки, классика, сериалы.',
        metaKeywords: 'фильмы торрент,скачать фильмы,фильмы магнет,кино торрент,фильмы бесплатно',
        h1: 'Скачать фильмы через торрент',
        sections: [
          { h2: 'Поиск фильмов', body: 'В Magnet Googo введите название фильма и получите результаты с нескольких сайтов мгновенно.' },
          { h2: 'Найти фильмы в высоком качестве', body: 'Советы для лучшего качества:', list: ['Ищите с "1080p" или "4K"','Больше размер файла = лучше качество','Больше сидеров = быстрее загрузка'] },
        ]
      },
    ]
  },
  pt: {
    name: 'Português', htmlLang: 'pt', dir: 'ltr',
    indexTitle: 'Guia de Busca Magnet — Magnet Googo',
    indexDesc: 'Guia completo sobre busca de magnets e torrents. Download grátis, apps recomendados e tutoriais.',
    ctaBtn: 'Download Grátis',
    backToHome: 'Voltar ao início',
    guideIndex: 'Índice de guias',
    whyTitle: 'Por que Magnet Googo?',
    whyItems: ['Busca em dezenas de sites','Zero anúncios · Grátis','Atualização automática de fontes','Ranking inteligente'],
    keywords: [
      {
        slug: 'busca-magnet', title: 'Buscador de Magnet Grátis【2026】— Os Melhores',
        metaDesc: 'Os melhores buscadores de magnet e torrent de 2026. Busque grátis com Magnet Googo.',
        metaKeywords: 'busca magnet,buscador de magnet,buscar torrent,download magnet grátis,magnet search',
        h1: 'Melhores Buscadores de Magnet 2026',
        sections: [
          { h2: 'O que é um link magnet?', body: 'Um link magnet é um URI que identifica arquivos em redes P2P sem precisar de um arquivo .torrent.' },
          { h2: 'O melhor buscador de magnets', body: 'Magnet Googo é um app Android gratuito que busca em múltiplos sites de magnet simultaneamente.', list: ['Busca em múltiplos sites ao mesmo tempo','Resultados unificados sem duplicatas','Sem anúncios ou registro','Fontes sempre atualizadas'] },
        ]
      },
      {
        slug: 'baixar-torrent', title: 'Como Baixar Torrents com Segurança — Guia 2026',
        metaDesc: 'Guia completo para baixar torrents com segurança. Ferramentas recomendadas e dicas.',
        metaKeywords: 'baixar torrent,torrent grátis,baixar filmes torrent,torrent seguro,cliente torrent',
        h1: 'Como Baixar Torrents com Segurança',
        sections: [
          { h2: 'Baixando torrents', body: 'Baixar torrents é simples se você seguir as práticas corretas.' },
          { h2: 'Dicas de segurança', body: 'Para baixar com segurança:', list: ['Use Magnet Googo para buscar com segurança','Instale um cliente BitTorrent confiável','Considere usar uma VPN','Verifique o número de seeders'] },
        ]
      },
      {
        slug: 'filmes-torrent', title: 'Baixar Filmes por Torrent — Busca Gratuita',
        metaDesc: 'Busque e baixe filmes por torrent gratuitamente. Lançamentos, clássicos e séries.',
        metaKeywords: 'filmes torrent,baixar filmes,filmes magnet,movie download,filmes grátis',
        h1: 'Baixar Filmes por Torrent',
        sections: [
          { h2: 'Buscar filmes por torrent', body: 'Com Magnet Googo, digite o título de qualquer filme e obtenha resultados de múltiplos sites.' },
          { h2: 'Encontrar filmes em alta qualidade', body: 'Dicas para a melhor qualidade:', list: ['Busque com "1080p" ou "4K"','Arquivos maiores = melhor qualidade','Mais seeders = download mais rápido'] },
        ]
      },
    ]
  },
  ar: {
    name: 'العربية', htmlLang: 'ar', dir: 'rtl',
    indexTitle: 'دليل بحث المغناطيس — Magnet Googo',
    indexDesc: 'دليل شامل حول بحث المغناطيس والتورنت. طرق التحميل المجانية والتطبيقات الموصى بها.',
    ctaBtn: 'تحميل مجاني',
    backToHome: 'العودة للرئيسية',
    guideIndex: 'فهرس الأدلة',
    whyTitle: 'لماذا Magnet Googo؟',
    whyItems: ['بحث في عشرات المواقع','بدون إعلانات · مجاني','تحديث تلقائي للمصادر','ترتيب ذكي'],
    keywords: [
      {
        slug: 'bahth-magnet', title: 'أفضل محرك بحث مغناطيس 2026 — مجاني',
        metaDesc: 'أفضل محركات بحث المغناطيس والتورنت لعام 2026. ابحث مجاناً باستخدام Magnet Googo.',
        metaKeywords: 'بحث مغناطيس,محرك بحث تورنت,بحث تورنت,تحميل مغناطيس مجاني,magnet search',
        h1: 'أفضل محركات بحث المغناطيس 2026',
        sections: [
          { h2: 'ما هو رابط المغناطيس؟', body: 'رابط المغناطيس هو URI يحدد الملفات على شبكات P2P بدون الحاجة إلى ملف .torrent.' },
          { h2: 'أفضل أداة بحث', body: 'Magnet Googo تطبيق Android مجاني يبحث في عدة مواقع مغناطيس في وقت واحد.', list: ['بحث في عدة مواقع في وقت واحد','نتائج موحدة بدون تكرار','بدون إعلانات أو تسجيل','مصادر محدثة دائماً'] },
        ]
      },
      {
        slug: 'tahmil-torrent', title: 'كيفية تحميل التورنت بأمان — دليل 2026',
        metaDesc: 'دليل شامل لتحميل التورنت بأمان. الأدوات الموصى بها ونصائح الأمان.',
        metaKeywords: 'تحميل تورنت,تورنت مجاني,تحميل أفلام تورنت,تورنت آمن',
        h1: 'كيفية تحميل التورنت بأمان',
        sections: [
          { h2: 'تحميل التورنت', body: 'تحميل التورنت سهل إذا استخدمت الأدوات الصحيحة.' },
          { h2: 'نصائح الأمان', body: 'للتحميل بأمان:', list: ['استخدم Magnet Googo للبحث بأمان','ثبّت عميل BitTorrent موثوق','استخدم VPN','تحقق من عدد المشاركين'] },
        ]
      },
      {
        slug: 'aflam-torrent', title: 'تحميل أفلام تورنت — بحث مجاني',
        metaDesc: 'ابحث وحمّل الأفلام عبر التورنت مجاناً. أحدث الأفلام والكلاسيكيات.',
        metaKeywords: 'أفلام تورنت,تحميل أفلام,أفلام مغناطيس,تحميل أفلام مجاني',
        h1: 'تحميل أفلام عبر التورنت',
        sections: [
          { h2: 'البحث عن الأفلام', body: 'في Magnet Googo، أدخل اسم أي فيلم واحصل على نتائج من عدة مواقع فوراً.' },
          { h2: 'إيجاد أفلام بجودة عالية', body: 'نصائح للحصول على أفضل جودة:', list: ['ابحث مع "1080p" أو "4K"','ملفات أكبر = جودة أفضل','مشاركون أكثر = تحميل أسرع'] },
        ]
      },
    ]
  },
};

// ─── HTML 渲染 ────────────────────────────────────────────────────

function renderSection(section) {
  let html = `<h2 class="text-xl font-bold text-gray-900 mt-8 mb-3">${section.h2}</h2>\n`;
  html += `<p class="text-gray-600 mb-4 leading-relaxed">${section.body}</p>\n`;
  if (section.list) {
    html += '<ul class="list-disc list-inside text-gray-600 space-y-1 mb-4">\n';
    section.list.forEach(li => { html += `  <li>${li}</li>\n`; });
    html += '</ul>\n';
  }
  return html;
}

function generateGuidePage(langData, kw) {
  const today = new Date().toISOString().slice(0, 10);
  const dirAttr = langData.dir === 'rtl' ? ' dir="rtl"' : '';
  const canonical = `https://magnetgoogo.com/${langData.htmlLang}/guide/${kw.slug}.html`;

  return `<!DOCTYPE html>
<html lang="${langData.htmlLang}"${dirAttr}>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${kw.title} — Magnet Googo</title>
    <meta name="description" content="${kw.metaDesc}">
    <meta name="keywords" content="${kw.metaKeywords}">
    <link rel="canonical" href="${canonical}">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="${kw.title}">
    <meta property="og:description" content="${kw.metaDesc}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="${canonical}">
    <meta property="og:image" content="https://magnetgoogo.com/images/app-icon-lg.png">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="${kw.title}">
    <meta name="twitter:description" content="${kw.metaDesc}">
    <link rel="icon" type="image/png" href="../../images/app-icon.png">
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Article","headline":"${kw.title}","description":"${kw.metaDesc}","author":{"@type":"Organization","name":"Magnet Googo"},"publisher":{"@type":"Organization","name":"Magnet Googo","logo":{"@type":"ImageObject","url":"https://magnetgoogo.com/images/app-icon-lg.png"}},"datePublished":"${today}","mainEntityOfPage":"${canonical}"}
    </script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config={theme:{extend:{colors:{brand:'#4285F4',brandGreen:'#34A853'}}}}</script>
    <style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}article h2{margin-top:1.5em}article p{line-height:1.8;margin-bottom:0.8em}article ul{margin-bottom:1em}.grad-btn{background:linear-gradient(135deg,#4285F4,#34A853)}.grad-btn:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(66,133,244,.35);transition:all .2s}</style>
</head>
<body class="bg-gray-50 text-gray-800 antialiased">
<nav class="bg-white border-b border-gray-100 sticky top-0 z-50">
  <div class="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
    <a href="../../" class="flex items-center gap-2"><img src="../../images/app-icon-sm.png" class="w-8 h-8" alt="Magnet Googo"><span class="font-bold">Magnet Googo</span></a>
    <a href="${downloadUrl}" class="grad-btn text-white text-sm font-medium px-4 py-2 rounded-full">${langData.ctaBtn}</a>
  </div>
</nav>
<div class="max-w-4xl mx-auto px-6 py-3 text-sm text-gray-400">
  <a href="../../" class="hover:text-brand">Magnet Googo</a> &gt; <a href="./" class="hover:text-brand">${langData.guideIndex}</a> &gt; <span class="text-gray-600">${kw.title}</span>
</div>
<main class="max-w-4xl mx-auto px-6 pb-16">
  <article class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 md:p-12">
    <h1 class="text-2xl md:text-3xl font-extrabold text-gray-900 mb-6">${kw.h1}</h1>
${kw.sections.map(renderSection).join('')}
  </article>
  <section class="mt-10 bg-gradient-to-r from-blue-50 to-green-50 rounded-2xl p-8 text-center">
    <h2 class="text-xl font-bold mb-3">${langData.whyTitle}</h2>
    <ul class="text-gray-600 space-y-1 mb-6 inline-block text-left">
${langData.whyItems.map(i => `      <li>✅ ${i}</li>`).join('\n')}
    </ul>
    <div><a href="${downloadUrl}" class="grad-btn text-white font-bold px-8 py-3 rounded-full inline-block">${langData.ctaBtn}</a></div>
  </section>
</main>
<footer class="border-t border-gray-100 py-6 text-center text-sm text-gray-400">© 2026 Magnet Googo</footer>
</body>
</html>`;
}

function generateGuideIndex(langData) {
  const dirAttr = langData.dir === 'rtl' ? ' dir="rtl"' : '';
  const cards = langData.keywords.map(kw => `
    <a href="${kw.slug}.html" class="block bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition-shadow">
      <h2 class="font-bold text-gray-900 mb-2">${kw.title}</h2>
      <p class="text-sm text-gray-500">${kw.metaDesc}</p>
    </a>`).join('\n');

  return `<!DOCTYPE html>
<html lang="${langData.htmlLang}"${dirAttr}>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${langData.indexTitle}</title>
    <meta name="description" content="${langData.indexDesc}">
    <link rel="canonical" href="https://magnetgoogo.com/${langData.htmlLang}/guide/">
    <meta name="robots" content="index, follow">
    <link rel="icon" type="image/png" href="../../images/app-icon.png">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config={theme:{extend:{colors:{brand:'#4285F4'}}}}</script>
    <style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}.grad-btn{background:linear-gradient(135deg,#4285F4,#34A853)}</style>
</head>
<body class="bg-gray-50 text-gray-800 antialiased">
<nav class="bg-white border-b border-gray-100 sticky top-0 z-50">
  <div class="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
    <a href="../../" class="flex items-center gap-2"><img src="../../images/app-icon-sm.png" class="w-8 h-8" alt="Magnet Googo"><span class="font-bold">Magnet Googo</span></a>
    <a href="${downloadUrl}" class="grad-btn text-white text-sm font-medium px-4 py-2 rounded-full">${langData.ctaBtn}</a>
  </div>
</nav>
<main class="max-w-4xl mx-auto px-6 py-10">
  <h1 class="text-2xl font-extrabold mb-8">${langData.indexTitle}</h1>
  <div class="grid gap-4">
${cards}
  </div>
</main>
<footer class="border-t border-gray-100 py-6 text-center text-sm text-gray-400">© 2026 Magnet Googo</footer>
</body>
</html>`;
}

// ─── MAIN ────────────────────────────────────────────────────────

function main() {
  const today = new Date().toISOString().slice(0, 10);
  let totalPages = 0;
  const sitemapEntries = [];

  for (const [langCode, langData] of Object.entries(LANG_KEYWORDS)) {
    const outDir = path.join(SITE_DIR, langCode, 'guide');
    if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

    // Generate keyword pages
    for (const kw of langData.keywords) {
      fs.writeFileSync(path.join(outDir, `${kw.slug}.html`), generateGuidePage(langData, kw), 'utf-8');
      sitemapEntries.push(`  <url><loc>https://magnetgoogo.com/${langCode}/guide/${kw.slug}.html</loc><lastmod>${today}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>`);
      totalPages++;
    }

    // Generate index
    fs.writeFileSync(path.join(outDir, 'index.html'), generateGuideIndex(langData), 'utf-8');
    sitemapEntries.push(`  <url><loc>https://magnetgoogo.com/${langCode}/guide/</loc><lastmod>${today}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>`);
    totalPages++;
  }

  // Update sitemap
  const sitemapPath = path.join(SITE_DIR, 'sitemap.xml');
  if (fs.existsSync(sitemapPath)) {
    let sitemap = fs.readFileSync(sitemapPath, 'utf-8');
    // Remove old i18n guide entries
    sitemap = sitemap.replace(/\n.*magnetgoogo\.com\/(ja|ko|es|fr|de|ru|pt|ar)\/guide\/.*\n?/g, '\n');
    // Clean up multiple blank lines
    sitemap = sitemap.replace(/\n{3,}/g, '\n');
    sitemap = sitemap.replace('</urlset>', sitemapEntries.join('\n') + '\n</urlset>');
    fs.writeFileSync(sitemapPath, sitemap, 'utf-8');
    console.log('✅ Updated sitemap.xml with i18n guide pages');
  }

  const langStats = Object.entries(LANG_KEYWORDS).map(([code, data]) => `${code}:${data.keywords.length}`).join(', ');
  console.log(`\n🚀 Generated ${totalPages} i18n guide pages (${Object.keys(LANG_KEYWORDS).length} languages)`);
  console.log(`   ${langStats}`);
}

main();
