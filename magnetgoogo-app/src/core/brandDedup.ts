/**
 * Brand-level deduplication for search sources — runtime tracker.
 *
 * Many sources are mirrors of the same backend (e.g. 19 TPB proxies).
 * Searching all mirrors wastes concurrency and returns identical results.
 *
 * Strategy: don't pre-filter — instead track successful (non-empty) responses
 * per brand at runtime. Once a brand has enough successes, skip its remaining
 * mirrors. Failed/empty responses don't count, so we auto-fallback to other
 * mirrors if the first ones are unreachable.
 */

const MAX_HITS_PER_BRAND = 2;

/** Domain-pattern → brand inference for sources without an explicit brand. */
const DOMAIN_BRAND_PATTERNS: [RegExp, string][] = [
  [/thepiratebay|piratebay|pirateproxy|tpb\.|mirrorbay|pirate-proxy/i, 'TPB'],
  [/yts\./i, 'YTS'],
  [/magnetdl\./i, 'MagnetDL'],
  [/rutor\./i, 'Rutor'],
  [/529\d+\.xyz/i, '52BT'],
  [/tokyotosho\./i, 'TokyoTosho'],
  [/0cili\./i, '0cili'],
  [/btsow\./i, 'BTSOW'],
  [/zzb\d+\.top|zhongziba\.|seed8\./i, '种子吧'],
  [/clb\d+\./i, '磁力宝'],
  [/clm\d+\./i, '磁力猫'],
  [/sobt\d+\./i, 'SOBT'],
  [/clg\d+\./i, '磁力狗'],
  [/cld\d+\./i, '磁力帝'],
];

/** Infer a brand key for a source rule. */
function inferBrand(rule: any): string {
  const explicit = rule.site?.brand;
  if (explicit) return explicit;

  const origin: string = rule.site?.origin || '';
  for (const [re, brand] of DOMAIN_BRAND_PATTERNS) {
    if (re.test(origin)) return brand;
  }

  // No brand → unique key (no dedup)
  return `__unique__${rule.site?.name || origin}`;
}

/**
 * Runtime brand tracker.
 * Create one per search session; call shouldSkip() before searching,
 * recordSuccess() after a non-empty response, recordDone() when finished.
 *
 * Tracks in-flight searches to prevent concurrent workers from all starting
 * the same brand's mirrors simultaneously (race condition with async workers).
 */
export class BrandTracker {
  private hits = new Map<string, number>();
  private inflight = new Map<string, number>();
  private skipped = 0;

  /** Get the brand key for a source rule. */
  getBrand(rule: any): string {
    return inferBrand(rule);
  }

  /**
   * Check if this source should be skipped. If not, reserves an in-flight slot
   * so concurrent workers won't over-commit to the same brand.
   */
  shouldSkip(rule: any): boolean {
    const brand = inferBrand(rule);
    const successes = this.hits.get(brand) || 0;
    if (successes >= MAX_HITS_PER_BRAND) {
      this.skipped++;
      return true;
    }
    const flying = this.inflight.get(brand) || 0;
    if (successes + flying >= MAX_HITS_PER_BRAND) {
      this.skipped++;
      return true;
    }
    // Reserve in-flight slot
    this.inflight.set(brand, flying + 1);
    return false;
  }

  /** Record a successful (non-empty) response for this source's brand. */
  recordSuccess(rule: any) {
    const brand = inferBrand(rule);
    this.hits.set(brand, (this.hits.get(brand) || 0) + 1);
  }

  /** Release the in-flight slot after a search finishes (success or failure). */
  recordDone(rule: any) {
    const brand = inferBrand(rule);
    const flying = this.inflight.get(brand) || 0;
    if (flying > 0) this.inflight.set(brand, flying - 1);
  }

  /** Log summary (dev only). */
  logSummary() {
    if (__DEV__ && this.skipped > 0) {
      console.log(`[BrandDedup] Skipped ${this.skipped} redundant mirrors at runtime`);
    }
  }
}
