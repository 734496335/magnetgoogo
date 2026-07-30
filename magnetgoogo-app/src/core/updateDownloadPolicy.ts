import type { Lang } from './i18n';

export type UpdateMirrorKind = 'lanzou' | 'gateway' | 'aliyun' | 'github' | 'other';

function parseHttpUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url : null;
  } catch {
    return null;
  }
}

function uniqueUrls(urls: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const raw of urls) {
    const value = String(raw || '').trim();
    if (!value || !parseHttpUrl(value) || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }

  return result;
}

export function getUpdateMirrorKind(url: string): UpdateMirrorKind {
  const parsed = parseHttpUrl(url);
  const host = parsed?.hostname.toLowerCase() || '';

  if (host.endsWith('lanzn.com') || host.endsWith('lanzou.com') || host.endsWith('lanzoui.com')) {
    return 'lanzou';
  }
  if (host === 'api.naoshiquan.com' || host.endsWith('.naoshiquan.com')) return 'gateway';
  if (host === 'cn.magnetgoogo.com') return 'aliyun';
  if (host === 'github.com' || host.endsWith('.githubusercontent.com')) return 'github';
  return 'other';
}

function mirrorPriority(url: string): number {
  switch (getUpdateMirrorKind(url)) {
    case 'lanzou':
      return 0;
    case 'gateway':
      return 1;
    case 'aliyun':
      return 2;
    case 'other':
      return 3;
    case 'github':
      return 4;
  }
}

/** Keep Lanzou first for mainland users and GitHub last as the global fallback. */
export function orderUpdateMirrors(urls: string[]): string[] {
  return uniqueUrls(urls)
    .map((url, index) => ({ url, index, priority: mirrorPriority(url) }))
    .sort((a, b) => a.priority - b.priority || a.index - b.index)
    .map((item) => item.url);
}

/** Browser landing pages such as Lanzou are not valid in-app APK byte sources. */
export function isDirectApkDownloadUrl(url: string): boolean {
  const parsed = parseHttpUrl(url);
  if (!parsed || getUpdateMirrorKind(url) === 'lanzou') return false;
  return parsed.pathname.toLowerCase().endsWith('.apk');
}

export function buildDirectDownloadCandidates(primary: string, mirrors: string[]): string[] {
  return uniqueUrls([primary, ...orderUpdateMirrors(mirrors)]).filter(isDirectApkDownloadUrl);
}

export function getBrowserFallbacks(primary: string, mirrors: string[]): string[] {
  return uniqueUrls([...orderUpdateMirrors(mirrors), primary]);
}

export function getEmergencyBrowserFallbacks(mirrors: string[]): string[] {
  const ordered = orderUpdateMirrors(mirrors);
  const preferredKinds: UpdateMirrorKind[] = ['lanzou', 'github'];
  const preferred = preferredKinds
    .map((kind) => ordered.find((url) => getUpdateMirrorKind(url) === kind))
    .filter((url): url is string => Boolean(url));
  return uniqueUrls([...preferred, ...ordered]).slice(0, 2);
}

export function getUpdateMirrorLabel(url: string, lang: Lang, index: number): string {
  const kind = getUpdateMirrorKind(url);
  const zh = lang === 'zh';

  switch (kind) {
    case 'lanzou':
      return zh ? '蓝奏云（推荐）' : 'LanzouCloud';
    case 'gateway':
      return zh ? '加速直链' : 'Accelerated download';
    case 'aliyun':
      return zh ? '阿里云直链' : 'China direct link';
    case 'github':
      return 'GitHub';
    default:
      return zh ? `备用链接 ${index}` : `Mirror ${index}`;
  }
}

export function getUpdateErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
