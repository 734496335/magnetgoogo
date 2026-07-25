export interface ResourceFeedSummary {
  generated_at: string;
  source_id: string;
  record_count: number;
  canonical_content_count: number;
  content_observation_count: number;
  resource_count: number;
  resource_observation_count: number;
  people_count: number;
  tag_count: number;
  records_without_resources: number;
  missing_urls: string[];
  running_runs: number;
  partial_runs: number;
}

export interface ResourcePerson {
  display_name: string;
  role: string;
  sort_order: number;
}

export interface ResourceFeedItem {
  rank: number;
  content_id: string;
  content_code: string;
  title: string;
  listing_title: string;
  release_date: string | null;
  duration_minutes: number | null;
  maker_name: string | null;
  publisher_name: string | null;
  series_name: string | null;
  cover_source_url: string;
  detail_url: string;
  people: ResourcePerson[];
  tags: string[];
  resource_count: number;
  source_first_seen_at: string;
  source_last_seen_at: string;
}

export interface ResourceFeed {
  summary: ResourceFeedSummary;
  items: ResourceFeedItem[];
}

export class ResourceFeedValidationError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'ResourceFeedValidationError';
    this.code = code;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requiredString(record: Record<string, unknown>, key: string, context: string): string {
  const value = record[key];
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new ResourceFeedValidationError('INVALID_STRING', `${context}.${key} must be a non-empty string`);
  }
  return value.trim();
}

function nullableString(record: Record<string, unknown>, key: string, context: string): string | null {
  const value = record[key];
  if (value === null || value === undefined || value === '') return null;
  if (typeof value !== 'string') {
    throw new ResourceFeedValidationError('INVALID_NULLABLE_STRING', `${context}.${key} must be string or null`);
  }
  return value.trim() || null;
}

function integer(record: Record<string, unknown>, key: string, context: string, minimum = 0): number {
  const value = record[key];
  if (!Number.isInteger(value) || (value as number) < minimum) {
    throw new ResourceFeedValidationError('INVALID_INTEGER', `${context}.${key} must be an integer >= ${minimum}`);
  }
  return value as number;
}

function nullableInteger(record: Record<string, unknown>, key: string, context: string): number | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (!Number.isInteger(value) || (value as number) < 0) {
    throw new ResourceFeedValidationError('INVALID_NULLABLE_INTEGER', `${context}.${key} must be an integer >= 0 or null`);
  }
  return value as number;
}

function stringArray(value: unknown, context: string): string[] {
  if (!Array.isArray(value)) {
    throw new ResourceFeedValidationError('INVALID_STRING_ARRAY', `${context} must be an array`);
  }
  return value.map((entry, index) => {
    if (typeof entry !== 'string' || entry.trim().length === 0) {
      throw new ResourceFeedValidationError('INVALID_STRING_ARRAY_ITEM', `${context}[${index}] must be a non-empty string`);
    }
    return entry.trim();
  });
}

function parsePerson(value: unknown, context: string): ResourcePerson {
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_PERSON', `${context} must be an object`);
  }
  return {
    display_name: requiredString(value, 'display_name', context),
    role: requiredString(value, 'role', context),
    sort_order: integer(value, 'sort_order', context),
  };
}

function parseSummary(value: unknown): ResourceFeedSummary {
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_SUMMARY', 'summary must be an object');
  }
  return {
    generated_at: requiredString(value, 'generated_at', 'summary'),
    source_id: requiredString(value, 'source_id', 'summary'),
    record_count: integer(value, 'record_count', 'summary'),
    canonical_content_count: integer(value, 'canonical_content_count', 'summary'),
    content_observation_count: integer(value, 'content_observation_count', 'summary'),
    resource_count: integer(value, 'resource_count', 'summary'),
    resource_observation_count: integer(value, 'resource_observation_count', 'summary'),
    people_count: integer(value, 'people_count', 'summary'),
    tag_count: integer(value, 'tag_count', 'summary'),
    records_without_resources: integer(value, 'records_without_resources', 'summary'),
    missing_urls: stringArray(value.missing_urls, 'summary.missing_urls'),
    running_runs: integer(value, 'running_runs', 'summary'),
    partial_runs: integer(value, 'partial_runs', 'summary'),
  };
}

function parseItem(value: unknown, index: number): ResourceFeedItem {
  const context = `items[${index}]`;
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_ITEM', `${context} must be an object`);
  }
  const peopleValue = value.people;
  if (!Array.isArray(peopleValue)) {
    throw new ResourceFeedValidationError('INVALID_PEOPLE', `${context}.people must be an array`);
  }

  return {
    rank: integer(value, 'rank', context, 1),
    content_id: requiredString(value, 'content_id', context),
    content_code: requiredString(value, 'content_code', context),
    title: requiredString(value, 'title', context),
    listing_title: requiredString(value, 'listing_title', context),
    release_date: nullableString(value, 'release_date', context),
    duration_minutes: nullableInteger(value, 'duration_minutes', context),
    maker_name: nullableString(value, 'maker_name', context),
    publisher_name: nullableString(value, 'publisher_name', context),
    series_name: nullableString(value, 'series_name', context),
    cover_source_url: requiredString(value, 'cover_source_url', context),
    detail_url: requiredString(value, 'detail_url', context),
    people: peopleValue.map((person, personIndex) => parsePerson(person, `${context}.people[${personIndex}]`)),
    tags: stringArray(value.tags, `${context}.tags`),
    resource_count: integer(value, 'resource_count', context),
    source_first_seen_at: requiredString(value, 'source_first_seen_at', context),
    source_last_seen_at: requiredString(value, 'source_last_seen_at', context),
  };
}

export function parseResourceFeed(value: unknown): ResourceFeed {
  if (!isRecord(value)) {
    throw new ResourceFeedValidationError('INVALID_ROOT', 'resource feed must be an object');
  }
  if (!Array.isArray(value.items)) {
    throw new ResourceFeedValidationError('INVALID_ITEMS', 'items must be an array');
  }

  const summary = parseSummary(value.summary);
  const items = value.items.map(parseItem);

  if (summary.record_count !== items.length) {
    throw new ResourceFeedValidationError(
      'COUNT_MISMATCH',
      `summary.record_count=${summary.record_count} does not match items.length=${items.length}`,
    );
  }

  items.forEach((item, index) => {
    const expectedRank = index + 1;
    if (item.rank !== expectedRank) {
      throw new ResourceFeedValidationError(
        'RANK_NOT_CONTINUOUS',
        `items[${index}].rank=${item.rank}, expected ${expectedRank}`,
      );
    }
  });

  return { summary, items };
}

export function resourceFeedItemKey(item: ResourceFeedItem): string {
  return `${item.rank}:${item.content_id}:${item.detail_url}`;
}
