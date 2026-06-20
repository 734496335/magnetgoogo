'use strict';

const { spawn, execSync } = require('child_process');
const path = require('path');
const store = require('./store');
const config = require('./config');
const { canonicalPlatform } = config;

// Resolve opencli: on Windows use node + main.js directly
let OPENCLI_CMD = 'opencli';
let OPENCLI_ARGS_PREFIX = [];
try {
  if (process.platform === 'win32') {
    const npmRoot = execSync('npm root -g', { encoding: 'utf8', timeout: 5000 }).trim();
    const mainJs = path.join(npmRoot, '@jackwener', 'opencli', 'dist', 'src', 'main.js');
    OPENCLI_CMD = process.execPath;
    OPENCLI_ARGS_PREFIX = [mainJs];
  } else {
    OPENCLI_CMD = execSync('which opencli', { encoding: 'utf8', timeout: 5000 }).trim().split(/\r?\n/)[0];
  }
} catch (_) { /* fallback to bare 'opencli' */ }

// ── Relevance keywords per platform ────────────────────────────────────
const RELEVANT_KEYWORDS = {
  zhihu: ['磁力', '搜索', '下载', '种子', 'BT', 'torrent', 'magnet', '网盘', '资源'],
  reddit: ['magnet', 'torrent', 'download', 'search', 'pirate', 'free', 'app', 'tool'],
  x: ['磁力', '搜索', '下载', '种子', 'BT', 'torrent', 'magnet', '网盘', '资源', 'magnet', 'search', 'torrent', 'download'],
  twitter: ['磁力', '搜索', '下载', '种子', 'BT', 'torrent', 'magnet', '网盘', '资源', 'magnet', 'search', 'torrent', 'download'],
};

// Keywords that give a strong relevance signal when found in titles
const MAGNET_KEYWORDS_CN = ['磁力', '搜索', '下载', '种子'];
const MAGNET_KEYWORDS_EN = ['magnet', 'search', 'torrent', 'download'];

// ── Helpers ─────────────────────────────────────────────────────────────

/**
 * Map a job status to the corresponding discovered_post status.
 * Kept in discovery.js for backward compatibility; canonical copy is in store.js.
 */
function discoveredStatusForJobStatus(jobStatus) {
  return store.discoveredStatusForJobStatus(jobStatus);
}

/** Safely require contentGen (may not exist yet). */
function _getContentGen() {
  try {
    return require('./contentGen');
  } catch (_) {
    return null;
  }
}

/**
 * Spawn `opencli` with the given arguments.
 * Returns a promise that resolves with stdout or rejects on error/timeout.
 */
function _spawnOpenCLI(args, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    const child = spawn(OPENCLI_CMD, [...OPENCLI_ARGS_PREFIX, ...args], { shell: false, windowsHide: true });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });

    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      reject(new Error(`opencli ${args.join(' ')} timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 0) {
        resolve(stdout);
      } else {
        reject(new Error(`opencli ${args.join(' ')} exited with code ${code}: ${stderr.trim()}`));
      }
    });

    child.on('error', (err) => {
      clearTimeout(timer);
      reject(new Error(`opencli ${args.join(' ')} spawn error: ${err.message}`));
    });
  });
}

/**
 * Parse opencli JSON output. opencli may return either a JSON array directly
 * or a JSON object with a results/items/posts key.
 */
function _parseResults(raw) {
  if (!raw || !raw.trim()) return [];

  let parsed;
  try {
    parsed = JSON.parse(raw.trim());
  } catch (_) {
    // Not valid JSON — return empty
    return [];
  }

  if (Array.isArray(parsed)) return parsed;
  // Try common wrapper keys
  for (const key of ['results', 'items', 'posts', 'data', 'search_results']) {
    if (Array.isArray(parsed[key])) return parsed[key];
  }
  return [];
}

// ── Core functions ──────────────────────────────────────────────────────

/**
 * Search a single platform for multiple queries via opencli.
 *
 * @param {string} platform  e.g. 'zhihu', 'reddit'
 * @param {string[]} queries list of search query strings
 * @returns {Promise<Array<{title: string, url: string, author: string, score: number, platform: string, query: string}>>}
 */
async function searchPlatform(platform, queries) {
  const cfg = config.loadConfig();
  const maxResults = cfg.global.discovery.max_results_per_query || 20;
  const allResults = [];

  for (const query of queries) {
    // Map platform names to opencli commands
    const cliPlatform = platform === 'x' ? 'twitter' : platform;
    const args = [cliPlatform, 'search', query, '--limit', String(maxResults), '-f', 'json'];

    let stdout;
    try {
      stdout = await _spawnOpenCLI(args);
    } catch (err) {
      console.error(`[discovery] searchPlatform ${platform} query="${query}" error: ${err.message}`);
      continue;
    }

    const items = _parseResults(stdout);
    for (const item of items) {
      const title = item.title || item.name || item.headline || '';
      const url = item.url || item.link || item.permalink || '';
      if (!url) continue; // skip entries without a URL

      allResults.push({
        title,
        url,
        author: item.author || item.user || item.username || '',
        score: typeof item.score === 'number' ? item.score : 0,
        comments: typeof item.comments === 'number' ? item.comments : (item.comment_count || 0),
        platform,
        query,
        created_at: item.created_at || item.date || item.timestamp || null,
        excerpt: item.description || item.snippet || item.content || item.body || item.text || title || '',
      });
    }
  }

  return allResults;
}

/**
 * Score and filter results by relevance.
 *
 * Scoring rules:
 *   +0.3  title contains magnet/torrent/download CN keywords
 *   +0.3  title contains magnet/torrent/download EN keywords
 *   +0.3  title contains other platform-specific keywords
 *   +0.1  post has < 50 comments (not oversaturated)
 *   +0.1  post is recent (< 7 days old)
 *
 * @param {Array} posts    raw post objects from searchPlatform
 * @param {string} platform
 * @returns {Array} posts that score >= 0.3, sorted descending by relevance
 */
function filterResults(posts, platform) {
  // Filter out posts that have already been replied to (but allow generation_failed retry after cooldown)
  const unreplied = posts.filter((p) => {
    const existing = store.getDiscoveredByUrl(p.url);
    if (!existing) return true;
    if (existing.status === 'replied') return false;
    // FR-10: Allow generation_failed posts past the 1-hour cooldown to be re-processed
    if (existing.status === 'generation_failed') {
      const retryCount = existing.generation_retry_count || 0;
      if (retryCount >= 3) return false; // permanently failed after 3 attempts
      const anchor = existing.last_attempt_at || existing.discovered_at;
      const anchorTime = new Date(anchor).getTime();
      return Date.now() - anchorTime >= 60 * 60 * 1000;
    }
    return true;
  });

  const platformKeywords = RELEVANT_KEYWORDS[platform] || [];
  const now = Date.now();
  const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;

  const scored = unreplied.map((post) => {
    let rel = 0;
    // Combine title + excerpt for keyword matching (X/Twitter has no title, only text)
    const searchText = ((post.title || '') + ' ' + (post.excerpt || '')).trim();
    const searchLower = searchText.toLowerCase();

    // CN magnet keywords
    if (MAGNET_KEYWORDS_CN.some((kw) => searchText.includes(kw))) {
      rel += 0.3;
    }

    // EN magnet keywords
    if (MAGNET_KEYWORDS_EN.some((kw) => searchLower.includes(kw))) {
      rel += 0.3;
    }

    // Platform-specific keywords (catches BT, 网盘, 资源, pirate, etc.)
    if (platformKeywords.some((kw) => searchLower.includes(kw.toLowerCase()))) {
      // Only add if not already covered by the CN/EN magnet sets above
      const alreadyCounted =
        MAGNET_KEYWORDS_CN.some((kw) => searchText.includes(kw)) ||
        MAGNET_KEYWORDS_EN.some((kw) => searchLower.includes(kw));
      if (!alreadyCounted) {
        rel += 0.3;
      }
    }

    // Low comment count (not oversaturated)
    if (typeof post.comments === 'number' && post.comments < 50) {
      rel += 0.1;
    }

    // Recent post (< 7 days)
    if (post.created_at) {
      const ts = new Date(post.created_at).getTime();
      if (!isNaN(ts) && now - ts < sevenDaysMs) {
        rel += 0.1;
      }
    }

    return { ...post, relevance: Math.min(rel, 1.0) };
  });

  return scored
    .filter((p) => p.relevance >= 0.3)
    .sort((a, b) => b.relevance - a.relevance);
}

/**
 * Select a random approved template (platform-agnostic).
 * Templates are universal core messages; the LLM adapts them to the target platform.
 */
function _pickRandomTemplate() {
  const approved = store.listTemplates({ status: 'approved' });
  if (!approved || approved.length === 0) return null;
  return approved[Math.floor(Math.random() * approved.length)];
}

/**
 * Enqueue a reply job for a discovered post.
 *
 * Template selection is platform-agnostic: any approved template can provide
 * the "core message" for any platform. The LLM (generateReply) handles the
 * platform-specific adaptation via its style guide.
 *
 * @param {object} post   post object with title, url, platform, query, relevance, etc.
 * @param {boolean} dryRun if true, only log — do not create DB records or jobs
 */
async function enqueueReply(post, dryRun, taskId) {
  if (dryRun) {
    console.log(
      `[discovery:dry] Would reply to [${post.platform}] "${post.title}" (${post.url}) ` +
      `score=${post.relevance.toFixed(2)} query="${post.query}"`
    );
    return { created: false, status: 'dry_run', postId: null };
  }

  // Check if this post URL was already replied to
  const existingPost = store.getDiscoveredByUrl(post.url);
  if (existingPost && existingPost.status === 'replied') {
    console.log(`[discovery] Already replied to ${post.url}, skipping`);
    return { created: false, status: 'replied', postId: existingPost.id };
  }

  // FR-10: Allow re-processing of generation_failed posts after 1-hour cooldown
  if (existingPost && existingPost.status === 'generation_failed') {
    const retryCount = existingPost.generation_retry_count || 0;
    if (retryCount >= 3) {
      console.log(`[discovery] ${post.url} generation_failed after ${retryCount} attempts — permanently failed.`);
      return { created: false, status: 'generation_failed_permanent', postId: existingPost.id };
    }
    const anchor = existingPost.last_attempt_at || existingPost.discovered_at;
    const anchorTime = new Date(anchor).getTime();
    const cooldownMs = 60 * 60 * 1000; // 1 hour
    if (Date.now() - anchorTime < cooldownMs) {
      console.log(`[discovery] ${post.url} is generation_failed (attempt ${retryCount}), still in cooldown. Skipping.`);
      return { created: false, status: 'generation_failed_cooldown', postId: existingPost.id };
    }
    // Cooldown expired — reset status to generating and re-attempt
    console.log(`[discovery] ${post.url} generation_failed cooldown expired, retrying (attempt ${retryCount + 1}).`);
    store.updateDiscoveredPost(existingPost.id, { status: 'generating', last_attempt_at: new Date().toISOString(), generation_retry_count: retryCount + 1 });
  }

  // PF-04: Canonicalize platform for DB/storage identity
  const canonPlatform = canonicalPlatform(post.platform);

  // Persist the discovered post
  const postId = store.upsertDiscoveredPost({
    platform: canonPlatform,
    post_url: post.url,
    post_title: post.title || '',
    post_excerpt: post.excerpt || '',
    search_query: post.query || '',
    relevance_score: post.relevance,
    status: 'generating',
  });

  // Pick a universal core-message template (any platform)
  const tpl = _pickRandomTemplate();
  const templateBody = tpl ? tpl.body : null;

  // Generate reply text (lazily import contentGen)
  let replyText = '';
  const contentGen = _getContentGen();
  if (contentGen && typeof contentGen.generateReply === 'function') {
    try {
      const cfg = config.loadConfig();
      const productName = cfg.global?.discovery?.product_name || 'MagnetGoogo';
      replyText = await contentGen.generateReply(post.title, post.excerpt || '', post.platform, productName, templateBody);
    } catch (err) {
      console.error(`[discovery] generateReply failed for ${post.url}: ${err.message}`);
      replyText = '';
    }
  }

  // P1-8 + P2-12: If LLM fails, mark as generation_failed — do NOT create spam job
  if (!replyText) {
    console.error(`[discovery] No reply generated for ${post.url} — marking generation_failed`);
    const existingRetryCount = (existingPost && existingPost.generation_retry_count) || 0;
    store.updateDiscoveredPost(postId, {
      status: 'generation_failed',
      last_attempt_at: new Date().toISOString(),
      generation_retry_count: existingRetryCount + 1,
    });
    return { created: false, status: 'generation_failed', postId };
  }

  // P1-8: Respect approval_required
  const cfg = config.loadConfig();
  const initialStatus = cfg.global.approval_required ? 'awaiting_approval' : 'queued';

  // Create a job
  let job;
  try {
    job = store.createJob({
      platform: canonPlatform,
      account: 'default',
      payload_json: {
        kind: 'comment',
        target: post.url,
        body: replyText,
      },
      ...(taskId ? { task_id: taskId } : {}),
      status: initialStatus,
    });
  } catch (err) {
    console.error(`[discovery] createJob failed for ${post.url}: ${err.message}`);
    store.updateDiscoveredPost(postId, { status: 'error' });
    return { created: false, status: 'error', postId };
  }

  // FR-04: Use shared helper to map job status -> discovered_post status
  store.updateDiscoveredPost(postId, {
    status: discoveredStatusForJobStatus(job.status),
    reply_job_id: job.id,
  });

  console.log(
    `[discovery] Enqueued reply job #${job.id} for [${post.platform}] "${post.title}" -> ${post.url}`
  );

  return { created: true, status: job.status, postId };
}

/**
 * Run one full discovery cycle:
 *   1. Read config, bail if discovery is disabled.
 *   2. For each platform/queries pair, search and filter.
 *   3. For new posts above the relevance threshold, enqueue reply jobs.
 *   4. Log a summary.
 */
async function runDiscoveryCycle() {
  const cfg = config.loadConfig();
  const discCfg = cfg.global.discovery;

  if (!discCfg.enabled) {
    console.log('[discovery] Discovery is disabled in config. Skipping.');
    return { searched: 0, newPosts: 0, enqueued: 0 };
  }

  const dryRun = !!discCfg.dry_run;

  // Create a task for this discovery cycle (skip in dry-run mode)
  let taskId = null;
  if (!dryRun) {
    const taskPlatform = canonicalPlatform(Object.keys(discCfg.queries || {})[0] || 'multi');
    taskId = store.createTask({
      name: `Discovery: ${new Date().toISOString().slice(0,10)}`,
      platform: taskPlatform,
      source_type: 'discovery',
    });
  }

  const threshold = typeof discCfg.relevance_threshold === 'number' ? discCfg.relevance_threshold : 0.5;
  const maxReplies = typeof discCfg.max_replies_per_run === 'number' ? discCfg.max_replies_per_run : 3;
  const queries = discCfg.queries || {};

  const platforms = Object.keys(queries);
  if (platforms.length === 0) {
    console.log('[discovery] No queries configured. Nothing to do.');
    return { searched: 0, newPosts: 0, enqueued: 0 };
  }

  let totalFound = 0;
  let totalNew = 0;
  let totalEnqueued = 0;

  for (const platform of platforms) {
    const platformQueries = queries[platform];
    if (!Array.isArray(platformQueries) || platformQueries.length === 0) continue;

    console.log(`[discovery] Searching ${platform} with ${platformQueries.length} query(ies) ...`);

    let results;
    try {
      results = await searchPlatform(platform, platformQueries);
    } catch (err) {
      console.error(`[discovery] searchPlatform(${platform}) failed: ${err.message}`);
      continue;
    }

    totalFound += results.length;
    console.log(`[discovery] ${platform}: ${results.length} raw results`);

    // Filter for relevance
    const relevant = filterResults(results, platform);

    // Deduplicate against already-known URLs and process
    for (const post of relevant) {
      if (totalEnqueued >= maxReplies) break;

      // Skip posts below the configured threshold
      if (post.relevance < threshold) continue;

      // Check if already discovered (skip unless generation_failed past cooldown)
      const existing = store.getDiscoveredByUrl(post.url);
      if (existing) {
        // FR-10: Allow re-processing of generation_failed posts after 1-hour cooldown
        if (existing.status === 'generation_failed') {
          const retryCount = existing.generation_retry_count || 0;
          if (retryCount >= 3) continue; // permanently failed
          const anchor = existing.last_attempt_at || existing.discovered_at;
          if (Date.now() - new Date(anchor).getTime() < 60 * 60 * 1000) continue; // still in cooldown
          // Past cooldown — fall through to enqueueReply which handles the retry
        } else {
          continue; // already discovered, not retryable
        }
      }

      totalNew++;
      const result = await enqueueReply(post, dryRun, taskId);
      // FR-10: Only count actual job creations as enqueued
      if (result && result.created) {
        totalEnqueued++;
      }
    }

    if (totalEnqueued >= maxReplies) {
      console.log(`[discovery] Reached max replies per run (${maxReplies}). Stopping.`);
      break;
    }
  }

  console.log(
    `[discovery] Cycle complete: ${totalFound} found, ${totalNew} new, ${totalEnqueued} enqueued` +
    (dryRun ? ' (DRY RUN)' : '')
  );

  if (taskId) {
    const total = store.getTaskJobs(taskId).length;
    // FR-05-style fix: set task status based on approval_required
    const discTaskStatus = cfg.global.approval_required ? 'awaiting_approval' : 'queued';
    store.updateTask(taskId, { total_items: total, status: total > 0 ? discTaskStatus : 'done' });
  }

  return { searched: totalFound, newPosts: totalNew, enqueued: totalEnqueued };
}

module.exports = { runDiscoveryCycle, searchPlatform, filterResults, enqueueReply, discoveredStatusForJobStatus };
