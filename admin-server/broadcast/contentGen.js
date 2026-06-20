const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ── Content deduplication cache (SHA-1 based, 1-hour TTL) ──────────────
const contentCache = new Map(); // key: sha1(body+platform+keyword) -> {content, timestamp}
const CACHE_TTL_MS = 3600000; // 1 hour

// ── Token usage tracking ───────────────────────────────────────────────
const usageMap = new Map(); // key: "YYYY-MM-DD:platform" -> {calls, inputTokens, outputTokens}

function _cacheKey(body, platform, keyword) {
  return crypto.createHash('sha1').update(`${body}\x00${platform}\x00${keyword}`).digest('hex');
}

function _todayStr() {
  return new Date().toISOString().slice(0, 10); // YYYY-MM-DD
}

function _recordUsage(platform, promptTokens, completionTokens) {
  const key = `${_todayStr()}:${platform}`;
  const prev = usageMap.get(key) || { calls: 0, inputTokens: 0, outputTokens: 0 };
  prev.calls += 1;
  prev.inputTokens += promptTokens;
  prev.outputTokens += completionTokens;
  usageMap.set(key, prev);
}

function getUsageStats() {
  const todayPrefix = _todayStr();
  let today = { calls: 0, inputTokens: 0, outputTokens: 0 };
  const byPlatform = {};
  for (const [key, val] of usageMap) {
    const [date, platform] = key.split(':');
    if (date === todayPrefix) {
      today.calls += val.calls;
      today.inputTokens += val.inputTokens;
      today.outputTokens += val.outputTokens;
    }
    if (!byPlatform[platform]) byPlatform[platform] = { calls: 0, inputTokens: 0, outputTokens: 0 };
    byPlatform[platform].calls += val.calls;
    byPlatform[platform].inputTokens += val.inputTokens;
    byPlatform[platform].outputTokens += val.outputTokens;
  }
  return { today, byPlatform };
}

let _envLoaded = false;

function loadEnv() {
  if (_envLoaded) return;
  const paths = [
    path.resolve(__dirname, '../../.env'),
    path.resolve(__dirname, '../.env'),
    path.resolve(__dirname, '.env')
  ];
  for (const p of paths) {
    if (fs.existsSync(p)) {
      try {
        const content = fs.readFileSync(p, 'utf8');
        for (const line of content.split('\n')) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
          const [key, ...parts] = trimmed.split('=');
          const val = parts.join('=').trim().replace(/^['"]|['"]$/g, '');
          if (key.trim() && !process.env[key.trim()]) {
            process.env[key.trim()] = val;
          }
        }
      } catch (e) {
        // ignore errors reading env file
      }
    }
  }
  _envLoaded = true;
}

function resolveLLM() {
  if (process.env.OPENAI_API_KEY) {
    return {
      key: process.env.OPENAI_API_KEY,
      baseUrl: process.env.OPENAI_API_BASE || 'https://api.openai.com/v1',
      model: process.env.OPENAI_MODEL || 'gpt-4o-mini'
    };
  }
  if (process.env.ARK_API_KEY || process.env.VOLCES_API_KEY) {
    return {
      key: process.env.ARK_API_KEY || process.env.VOLCES_API_KEY,
      baseUrl: process.env.VOLCES_API_URL || 'https://ark.cn-beijing.volces.com/api/v3',
      model: process.env.VOLCES_MODEL || 'doubao-seed-1-6-250615'
    };
  }
  if (process.env.DEEPSEEK_API_KEY) {
    return {
      key: process.env.DEEPSEEK_API_KEY,
      baseUrl: process.env.DEEPSEEK_API_BASE || 'https://api.deepseek.com/v1',
      model: process.env.DEEPSEEK_MODEL || 'deepseek-chat'
    };
  }
  if (process.env.MIMO_API_KEY) {
    return {
      key: process.env.MIMO_API_KEY,
      baseUrl: process.env.MIMO_API_BASE || 'https://token-plan-cn.xiaomimimo.com/v1',
      model: process.env.MIMO_MODEL || 'mimo-v2.5-pro'
    };
  }
  return null;
}

function getPlatformStyle(platform) {
  const styles = {
    zhihu: 'academic, professional, logical, structured, objective analysis, typically longer and detailed.',
    xiaohongshu: 'lively, emotional, lots of emojis, friendly tone ("小红书宝宝"), spacious layout with line breaks, include relevant topic hashtags.',
    x: 'extremely short, concise, sharp viewpoints, attention-grabbing, strictly under 140/280 characters.',
    twitter: 'extremely short, concise, sharp viewpoints, attention-grabbing, strictly under 140/280 characters.',
    bilibili: 'ACG subculture style, includes internet slang/memes, interactive and engaging tone.',
    reddit: 'geeky, rational discussion, objective sharing, Reddit-specific community tone.'
  };
  return styles[platform.toLowerCase()] || 'neutral, clear social media post';
}

async function generateVariant(templateBody, platform, keyword) {
  // ── Cache sweep (prevent unbounded growth) ────────────────────────
  if (contentCache.size > 500) {
    const now = Date.now();
    for (const [k, v] of contentCache) {
      if (now - v.timestamp >= CACHE_TTL_MS) contentCache.delete(k);
    }
  }

  // ── Cache check ────────────────────────────────────────────────────
  const ck = _cacheKey(templateBody, platform, keyword);
  const cached = contentCache.get(ck);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.content;
  }

  loadEnv();
  const llm = resolveLLM();
  if (!llm) {
    throw new Error('No LLM API keys found in environment. Please set OPENAI_API_KEY, ARK_API_KEY, DEEPSEEK_API_KEY or MIMO_API_KEY.');
  }

  const systemPrompt = 'You are a professional social media content writer. Your task is to rewrite a given message template to fit the tone, style, and formatting of a specific platform (Zhihu, X/Twitter, Xiaohongshu, Bilibili, Reddit), and naturally embed a specific keyword into the content. Maintain the core meaning but adapt the expression. Return ONLY the rewritten text, without any additional explanations, notes, or markdown fences.';

  const platformStyle = getPlatformStyle(platform);
  const userPrompt = `Platform: ${platform} (Style: ${platformStyle})
Keyword: ${keyword}
Original Template:
${templateBody}

Rewritten Content:`;

  const url = `${llm.baseUrl.replace(/\/$/, '')}/chat/completions`;
  const bodyStr = JSON.stringify({
    model: llm.model,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt }
    ],
    temperature: 0.7
  });

  // ── Retry with exponential backoff (max 2 retries = 3 attempts) ────
  const MAX_RETRIES = 2;
  const DELAYS = [2000, 4000];
  const NO_RETRY_STATUSES = new Set([400, 401, 403]);
  let lastError;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let response;
    try {
      // P2-11: Add 45s timeout to prevent indefinite hanging
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 45000);
      response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${llm.key}`
        },
        body: bodyStr,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
    } catch (err) {
      // Network error — retry if attempts remain
      lastError = err;
      if (attempt < MAX_RETRIES) {
        await new Promise(r => setTimeout(r, DELAYS[attempt]));
        continue;
      }
      throw new Error(`LLM API network error after ${MAX_RETRIES + 1} attempts: ${err.message}`);
    }

    if (response.ok) {
      const data = await response.json();
      if (!data.choices || !data.choices[0] || !data.choices[0].message) {
        throw new Error(`Invalid LLM response format: ${JSON.stringify(data)}`);
      }

      const content = data.choices[0].message.content.trim();
      if (!content || content.length < 10) {
        throw new Error('LLM returned empty or too-short content');
      }

      // ── Token usage tracking ─────────────────────────────────────
      let promptTokens, completionTokens;
      if (data.usage && data.usage.prompt_tokens != null && data.usage.completion_tokens != null) {
        promptTokens = data.usage.prompt_tokens;
        completionTokens = data.usage.completion_tokens;
      } else {
        // Estimate: ~4 chars per token
        promptTokens = Math.ceil((systemPrompt.length + userPrompt.length) / 4);
        completionTokens = Math.ceil(content.length / 4);
      }
      _recordUsage(platform, promptTokens, completionTokens);

      // ── Store in cache ───────────────────────────────────────────
      contentCache.set(ck, { content, timestamp: Date.now() });

      return content;
    }

    // Non-OK response
    const errorText = await response.text();

    // Non-retryable status codes
    if (NO_RETRY_STATUSES.has(response.status)) {
      throw new Error(`LLM API returned HTTP ${response.status}: ${errorText}`);
    }

    // Retryable: 429 or 5xx
    if (attempt < MAX_RETRIES) {
      let delay = DELAYS[attempt];
      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After');
        if (retryAfter) {
          const parsed = parseInt(retryAfter, 10);
          if (!isNaN(parsed) && parsed > 0) delay = parsed * 1000;
        }
      }
      await new Promise(r => setTimeout(r, delay));
      continue;
    }

    throw new Error(`LLM API returned HTTP ${response.status} after ${MAX_RETRIES + 1} attempts: ${errorText}`);
  }

  // Should not reach here, but just in case
  throw lastError || new Error('LLM API call failed after all retries');
}

async function generateReply(postTitle, postExcerpt, platform, productName, templateBody) {
  // ── Cache sweep (prevent unbounded growth) ────────────────────────
  if (contentCache.size > 500) {
    const now = Date.now();
    for (const [k, v] of contentCache) {
      if (now - v.timestamp >= CACHE_TTL_MS) contentCache.delete(k);
    }
  }

  // ── Cache check (use "reply:" prefix to avoid collision with generateVariant) ──
  const ck = _cacheKey(`reply:${postTitle}:${templateBody || ''}`, platform, productName);
  const cached = contentCache.get(ck);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.content;
  }

  loadEnv();
  const llm = resolveLLM();
  if (!llm) {
    throw new Error('No LLM API keys found in environment. Please set OPENAI_API_KEY, ARK_API_KEY, DEEPSEEK_API_KEY or MIMO_API_KEY.');
  }

  const systemPrompt = `You are a normal social media user replying to a post. Rules:
1. Reply in the SAME language as the original post
2. Sound like a real casual user, NOT a marketer or bot
3. Keep it SHORT (1-2 sentences for Chinese, 2-3 sentences for English)
4. If relevant, casually mention you use "${productName}" for this — like "I use ${productName}" or "${productName} works for me", NOT "I recommend" or "You should try"
5. NEVER use phrases like "check out", "worth trying", "I recommend", "you might find useful" — these sound like ads
6. Talk like a friend giving a quick tip, not a product review
7. If the post is not about magnets/search/downloads, just give a normal helpful reply without mentioning ${productName}
${templateBody ? '8. Use the reference message as inspiration for your tone, but write naturally' : ''}

Product info: ${productName} is a free magnet link search app that aggregates 80+ sources.`;

  const platformStyle = getPlatformStyle(platform);
  const templateHint = templateBody ? `\nReference core message (adapt, don't copy): ${templateBody}` : '';
  const userPrompt = `Platform: ${platform} (Style: ${platformStyle})
Original post title: ${postTitle}
Original post excerpt: ${postExcerpt}${templateHint}

Write a natural, helpful reply (3-6 sentences for English, 100-300 characters for Chinese):`;

  const url = `${llm.baseUrl.replace(/\/$/, '')}/chat/completions`;
  const bodyStr = JSON.stringify({
    model: llm.model,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt }
    ],
    temperature: 0.9
  });

  // ── Retry with exponential backoff (max 2 retries = 3 attempts) ────
  const MAX_RETRIES = 2;
  const DELAYS = [2000, 4000];
  const NO_RETRY_STATUSES = new Set([400, 401, 403]);
  let lastError;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let response;
    try {
      // P2-11: Add 45s timeout to prevent indefinite hanging
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 45000);
      response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${llm.key}`
        },
        body: bodyStr,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
    } catch (err) {
      lastError = err;
      if (attempt < MAX_RETRIES) {
        await new Promise(r => setTimeout(r, DELAYS[attempt]));
        continue;
      }
      throw new Error(`LLM API network error after ${MAX_RETRIES + 1} attempts: ${err.message}`);
    }

    if (response.ok) {
      const data = await response.json();
      if (!data.choices || !data.choices[0] || !data.choices[0].message) {
        throw new Error(`Invalid LLM response format: ${JSON.stringify(data)}`);
      }

      const content = data.choices[0].message.content.trim();
      if (!content || content.length < 10) {
        throw new Error('LLM returned empty or too-short content');
      }

      // ── Token usage tracking ─────────────────────────────────────
      let promptTokens, completionTokens;
      if (data.usage && data.usage.prompt_tokens != null && data.usage.completion_tokens != null) {
        promptTokens = data.usage.prompt_tokens;
        completionTokens = data.usage.completion_tokens;
      } else {
        promptTokens = Math.ceil((systemPrompt.length + userPrompt.length) / 4);
        completionTokens = Math.ceil(content.length / 4);
      }
      _recordUsage(platform, promptTokens, completionTokens);

      // ── Store in cache ───────────────────────────────────────────
      contentCache.set(ck, { content, timestamp: Date.now() });

      return content;
    }

    const errorText = await response.text();

    if (NO_RETRY_STATUSES.has(response.status)) {
      throw new Error(`LLM API returned HTTP ${response.status}: ${errorText}`);
    }

    if (attempt < MAX_RETRIES) {
      let delay = DELAYS[attempt];
      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After');
        if (retryAfter) {
          const parsed = parseInt(retryAfter, 10);
          if (!isNaN(parsed) && parsed > 0) delay = parsed * 1000;
        }
      }
      await new Promise(r => setTimeout(r, delay));
      continue;
    }

    throw new Error(`LLM API returned HTTP ${response.status} after ${MAX_RETRIES + 1} attempts: ${errorText}`);
  }

  throw lastError || new Error('LLM API call failed after all retries');
}

module.exports = { generateVariant, generateReply, getUsageStats };
