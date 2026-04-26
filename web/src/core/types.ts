import { z } from 'zod';

export const SourceRuleSchema = z.object({
  id: z.string(),
  site: z.object({
    name: z.string(),
    origin: z.string(),
  }),
  search: z.object({
    request_template: z.string(),
    requires_waf_bypass: z.boolean().optional(),
    requires_browser: z.boolean().optional(),
    requires_csrf: z.boolean().optional(),
    handler: z.string().optional(),
    request_method: z.string().optional(),
    request_body: z.record(z.string(), z.string()).optional(),
    parse_metadata: z.object({
      selectors: z.object({
        list_item: z.string().optional().default(''),
        title: z.string().optional().default(''),
        magnet: z.string().optional().default(''),
        size: z.string().optional(),
        date: z.string().optional(),
        seeders: z.string().optional(),
        leechers: z.string().optional(),
        detail_link: z.string().optional(),
      }),
    }),
    detail: z.object({
      selectors: z.object({
        magnet: z.string(),
        title: z.string().optional(),
        size: z.string().optional(),
        date: z.string().optional(),
        seeders: z.string().optional(),
        leechers: z.string().optional(),
      }),
    }).optional(),
  }),
  capabilities: z.object({
    supports_search: z.boolean().optional(),
    supports_detail: z.boolean().optional(),
  }).optional(),
  quality: z.object({
    score: z.number(),
    tags: z.array(z.string()),
  }),
  health: z.object({
    status: z.enum(['green', 'yellow', 'gray']),
    status_detail: z.string().optional(),
    last_checked_at: z.string().optional(),
  }).optional(),
});

export const RulesetSchema = z.object({
  ruleset_id: z.string(),
  rules: z.array(SourceRuleSchema),
});

export const SourcesSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  rulesets: z.array(RulesetSchema),
}).passthrough();

export type SourceRule = z.infer<typeof SourceRuleSchema>;
export type Ruleset = z.infer<typeof RulesetSchema>;
export type Sources = z.infer<typeof SourcesSchema>;

export interface MagnetResult {
  title: string;
  magnet: string;
  size: string;
  date: string;
  file_count?: number;
  seeders: number;
  leechers: number;
  source: string;
  score: number;
  site_name: string;
  relevance?: number;
}
