import type { Lang } from './i18n';

export interface UpdateCopy {
  optionalTitle: string;
  optionalDescription: string;
  forceTitle: string;
  forceDescription: string;
  updateNow: string;
  updateLater: string;
  backupDownload: string;
  backupLink: (index: number) => string;
  downloading: string;
  downloadComplete: string;
  downloadFailed: string;
  downloadFailedMessage: string;
  openDownload: string;
}

const COPY: Record<Lang, UpdateCopy> = {
  zh: {
    optionalTitle: '发现新版本',
    optionalDescription: '新版本已发布，建议更新以获得更好的体验。',
    forceTitle: '需要更新',
    forceDescription: '当前版本过旧，无法继续使用。\n请更新到最新版本。',
    updateNow: '立即更新',
    updateLater: '稍后再说',
    backupDownload: '备用下载：',
    backupLink: (index) => `备用链接 ${index}`,
    downloading: '正在下载…',
    downloadComplete: '下载完成，正在安装…',
    downloadFailed: '下载失败',
    downloadFailedMessage: '请使用浏览器下载安装',
    openDownload: '前往下载',
  },
  en: {
    optionalTitle: 'Update Available',
    optionalDescription: 'A new version is ready with the latest improvements.',
    forceTitle: 'Update Required',
    forceDescription: 'This version is no longer supported.\nPlease update to continue.',
    updateNow: 'Update Now',
    updateLater: 'Later',
    backupDownload: 'Backup download:',
    backupLink: (index) => `Mirror ${index}`,
    downloading: 'Downloading…',
    downloadComplete: 'Download complete. Installing…',
    downloadFailed: 'Download failed',
    downloadFailedMessage: 'Please download and install it in your browser.',
    openDownload: 'Open download',
  },
  es: {
    optionalTitle: 'Actualización disponible',
    optionalDescription: 'Hay una nueva versión con las últimas mejoras.',
    forceTitle: 'Actualización necesaria',
    forceDescription: 'Esta versión ya no es compatible.\nActualiza para continuar.',
    updateNow: 'Actualizar ahora',
    updateLater: 'Más tarde',
    backupDownload: 'Descarga alternativa:',
    backupLink: (index) => `Enlace ${index}`,
    downloading: 'Descargando…',
    downloadComplete: 'Descarga completa. Instalando…',
    downloadFailed: 'Error de descarga',
    downloadFailedMessage: 'Descarga e instala la app desde el navegador.',
    openDownload: 'Abrir descarga',
  },
  ru: {
    optionalTitle: 'Доступно обновление',
    optionalDescription: 'Вышла новая версия с последними улучшениями.',
    forceTitle: 'Требуется обновление',
    forceDescription: 'Эта версия больше не поддерживается.\nОбновите приложение.',
    updateNow: 'Обновить',
    updateLater: 'Позже',
    backupDownload: 'Запасная ссылка:',
    backupLink: (index) => `Ссылка ${index}`,
    downloading: 'Загрузка…',
    downloadComplete: 'Загружено. Установка…',
    downloadFailed: 'Ошибка загрузки',
    downloadFailedMessage: 'Скачайте и установите приложение через браузер.',
    openDownload: 'Открыть загрузку',
  },
  pt: {
    optionalTitle: 'Atualização disponível',
    optionalDescription: 'Uma nova versão está disponível com melhorias.',
    forceTitle: 'Atualização necessária',
    forceDescription: 'Esta versão não é mais compatível.\nAtualize para continuar.',
    updateNow: 'Atualizar agora',
    updateLater: 'Mais tarde',
    backupDownload: 'Download alternativo:',
    backupLink: (index) => `Link ${index}`,
    downloading: 'Baixando…',
    downloadComplete: 'Download concluído. Instalando…',
    downloadFailed: 'Falha no download',
    downloadFailedMessage: 'Baixe e instale pelo navegador.',
    openDownload: 'Abrir download',
  },
  ja: {
    optionalTitle: 'アップデートがあります',
    optionalDescription: '最新の改善を含む新バージョンが公開されました。',
    forceTitle: 'アップデートが必要です',
    forceDescription: 'このバージョンはサポート対象外です。\n更新して続行してください。',
    updateNow: '今すぐ更新',
    updateLater: 'あとで',
    backupDownload: '予備ダウンロード：',
    backupLink: (index) => `リンク ${index}`,
    downloading: 'ダウンロード中…',
    downloadComplete: '完了しました。インストール中…',
    downloadFailed: 'ダウンロード失敗',
    downloadFailedMessage: 'ブラウザからダウンロードしてインストールしてください。',
    openDownload: 'ダウンロードを開く',
  },
  ko: {
    optionalTitle: '업데이트가 있습니다',
    optionalDescription: '최신 개선 사항이 포함된 새 버전이 출시되었습니다.',
    forceTitle: '업데이트가 필요합니다',
    forceDescription: '이 버전은 더 이상 지원되지 않습니다.\n업데이트 후 계속하세요.',
    updateNow: '지금 업데이트',
    updateLater: '나중에',
    backupDownload: '보조 다운로드:',
    backupLink: (index) => `링크 ${index}`,
    downloading: '다운로드 중…',
    downloadComplete: '다운로드 완료. 설치 중…',
    downloadFailed: '다운로드 실패',
    downloadFailedMessage: '브라우저에서 다운로드하여 설치해 주세요.',
    openDownload: '다운로드 열기',
  },
  fr: {
    optionalTitle: 'Mise à jour disponible',
    optionalDescription: 'Une nouvelle version avec les dernières améliorations est disponible.',
    forceTitle: 'Mise à jour requise',
    forceDescription: 'Cette version n’est plus prise en charge.\nMettez à jour pour continuer.',
    updateNow: 'Mettre à jour',
    updateLater: 'Plus tard',
    backupDownload: 'Téléchargement alternatif :',
    backupLink: (index) => `Lien ${index}`,
    downloading: 'Téléchargement…',
    downloadComplete: 'Téléchargé. Installation…',
    downloadFailed: 'Échec du téléchargement',
    downloadFailedMessage: 'Téléchargez et installez l’application via le navigateur.',
    openDownload: 'Ouvrir le téléchargement',
  },
  de: {
    optionalTitle: 'Update verfügbar',
    optionalDescription: 'Eine neue Version mit aktuellen Verbesserungen ist verfügbar.',
    forceTitle: 'Update erforderlich',
    forceDescription: 'Diese Version wird nicht mehr unterstützt.\nBitte aktualisieren.',
    updateNow: 'Jetzt aktualisieren',
    updateLater: 'Später',
    backupDownload: 'Alternativer Download:',
    backupLink: (index) => `Link ${index}`,
    downloading: 'Wird heruntergeladen…',
    downloadComplete: 'Download abgeschlossen. Installation…',
    downloadFailed: 'Download fehlgeschlagen',
    downloadFailedMessage: 'Bitte im Browser herunterladen und installieren.',
    openDownload: 'Download öffnen',
  },
  ar: {
    optionalTitle: 'يتوفر تحديث',
    optionalDescription: 'يتوفر إصدار جديد يتضمن أحدث التحسينات.',
    forceTitle: 'التحديث مطلوب',
    forceDescription: 'لم يعد هذا الإصدار مدعومًا.\nيرجى التحديث للمتابعة.',
    updateNow: 'التحديث الآن',
    updateLater: 'لاحقًا',
    backupDownload: 'تنزيل بديل:',
    backupLink: (index) => `الرابط ${index}`,
    downloading: 'جارٍ التنزيل…',
    downloadComplete: 'اكتمل التنزيل. جارٍ التثبيت…',
    downloadFailed: 'فشل التنزيل',
    downloadFailedMessage: 'يرجى التنزيل والتثبيت عبر المتصفح.',
    openDownload: 'فتح التنزيل',
  },
};

export function getUpdateCopy(lang: Lang): UpdateCopy {
  return COPY[lang] ?? COPY.en;
}
