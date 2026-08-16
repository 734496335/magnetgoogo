export function cookiePairsFromSetCookie(raw: string): string {
  if (!raw) return '';
  return raw
    .split(/,(?=\s*[^;,=\s]+=[^;,]*)/)
    .map((cookie) => cookie.split(';', 1)[0].trim())
    .filter((pair) => pair.includes('='))
    .join('; ');
}
