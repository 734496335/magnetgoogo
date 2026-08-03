/** Shared search-result date normalization.
 *
 * Only return a date when the value can be identified reliably. Unknown text,
 * sizes, counters, time-only values and implausible future dates are hidden.
 */

const MONTHS: Record<string, number> = {
  jan: 1, january: 1,
  feb: 2, february: 2,
  mar: 3, march: 3,
  apr: 4, april: 4,
  may: 5,
  jun: 6, june: 6,
  jul: 7, july: 7,
  aug: 8, august: 8,
  sep: 9, sept: 9, september: 9,
  oct: 10, october: 10,
  nov: 11, november: 11,
  dec: 12, december: 12,
};

const RU_MONTHS: Record<string, number> = {
  янв: 1, январ: 1,
  фев: 2, феврал: 2,
  мар: 3, март: 3,
  апр: 4, апрел: 4,
  май: 5, мая: 5,
  июн: 6, июня: 6,
  июл: 7, июля: 7,
  авг: 8, август: 8,
  сен: 9, сент: 9, сентябр: 9,
  окт: 10, октябр: 10,
  ноя: 11, ноябр: 11,
  дек: 12, декабр: 12,
};

const MAX_FUTURE_SKEW_MS = 2 * 24 * 60 * 60 * 1000;

function normalizeYear(raw: string): number {
  const value = Number.parseInt(raw.replace(/^['’]/, ''), 10);
  if (!Number.isFinite(value)) return 0;
  if (raw.replace(/^['’]/, '').length <= 2) return value >= 70 ? 1900 + value : 2000 + value;
  return value;
}

function validDate(year: number, month: number, day: number, nowMs = Date.now()): string {
  if (year < 1970 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) return '';
  const value = new Date(Date.UTC(year, month - 1, day));
  if (
    value.getUTCFullYear() !== year
    || value.getUTCMonth() !== month - 1
    || value.getUTCDate() !== day
    || value.getTime() > nowMs + MAX_FUTURE_SKEW_MS
  ) return '';
  return `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
}

function monthNumber(raw: string, map: Record<string, number>): number {
  const normalized = raw.toLowerCase().replace(/[.]/g, '');
  const exact = map[normalized];
  if (exact) return exact;
  const key = Object.keys(map).find((candidate) => normalized.startsWith(candidate));
  return key ? map[key] : 0;
}

function relativeDate(raw: string, nowMs: number): string {
  const lower = raw.toLowerCase();
  if (/^(?:today|сегодня|今天)$/.test(lower)) {
    const now = new Date(nowMs);
    return validDate(now.getUTCFullYear(), now.getUTCMonth() + 1, now.getUTCDate(), nowMs);
  }
  if (/^(?:yesterday|вчера|昨天)$/.test(lower)) {
    const value = new Date(nowMs - 24 * 60 * 60 * 1000);
    return validDate(value.getUTCFullYear(), value.getUTCMonth() + 1, value.getUTCDate(), nowMs);
  }

  const units: Array<[RegExp, number]> = [
    [/(\d+)\s*(?:years?|yrs?|年)/gi, 365 * 24 * 60 * 60 * 1000],
    [/(\d+)\s*(?:months?|mos?|个月|個月)/gi, 30 * 24 * 60 * 60 * 1000],
    [/(\d+)\s*(?:weeks?|wks?|周|週)/gi, 7 * 24 * 60 * 60 * 1000],
    [/(\d+)\s*(?:days?|天)/gi, 24 * 60 * 60 * 1000],
    [/(\d+)\s*(?:hours?|hrs?|小时|小時)/gi, 60 * 60 * 1000],
    [/(\d+)\s*(?:minutes?|mins?|分钟|分鐘)/gi, 60 * 1000],
    [/(\d+)\s*(?:seconds?|secs?|秒)/gi, 1000],
  ];
  let duration = 0;
  let matched = false;
  for (const [pattern, multiplier] of units) {
    pattern.lastIndex = 0;
    for (const match of raw.matchAll(pattern)) {
      duration += Number.parseInt(match[1], 10) * multiplier;
      matched = true;
    }
  }
  if (!matched || duration <= 0) return '';
  const value = new Date(nowMs - duration);
  return validDate(value.getUTCFullYear(), value.getUTCMonth() + 1, value.getUTCDate(), nowMs);
}

export function parseResourceDateLabel(raw?: string, nowMs = Date.now()): string {
  if (!raw) return '';
  const value = raw.replace(/[\r\n\u00a0]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!value) return '';

  const timestamp = value.match(/^\d{10}(?:\d{3})?$/);
  if (timestamp) {
    const numeric = Number(timestamp[0]);
    const ms = timestamp[0].length === 10 ? numeric * 1000 : numeric;
    const parsed = new Date(ms);
    if (!Number.isNaN(parsed.getTime())) {
      return validDate(parsed.getUTCFullYear(), parsed.getUTCMonth() + 1, parsed.getUTCDate(), nowMs);
    }
  }

  let match = value.match(/\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b/);
  if (match) return validDate(Number(match[1]), Number(match[2]), Number(match[3]), nowMs);

  match = value.match(/\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b/);
  if (match) return validDate(Number(match[3]), Number(match[1]), Number(match[2]), nowMs);

  match = value.match(/(\d{4})年(\d{1,2})月(\d{1,2})日?/);
  if (match) return validDate(Number(match[1]), Number(match[2]), Number(match[3]), nowMs);

  match = value.match(/\b([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(['’]?\d{2,4})\b/i);
  if (match) {
    const parsed = validDate(normalizeYear(match[3]), monthNumber(match[1], MONTHS), Number(match[2]), nowMs);
    if (parsed) return parsed;
  }

  match = value.match(/\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?[,]?\s+(['’]?\d{2,4})\b/i);
  if (match) {
    const parsed = validDate(normalizeYear(match[3]), monthNumber(match[2], MONTHS), Number(match[1]), nowMs);
    if (parsed) return parsed;
  }

  match = value.match(/\b(\d{1,2})\s+([А-Яа-яЁё]+)\.?\s+(['’]?\d{2,4})\b/u);
  if (match) {
    const parsed = validDate(normalizeYear(match[3]), monthNumber(match[2], RU_MONTHS), Number(match[1]), nowMs);
    if (parsed) return parsed;
  }

  return relativeDate(value, nowMs);
}
