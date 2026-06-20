const { Router } = require('express');
const config = require('./config');
const { canonicalPlatform, resolveAccount } = config;
const store = require('./store');
const { canAct } = require('./rateLimiter');

const router = Router();

/**
 * PF-05: Unified helper for job-level approve/reject.
 * Updates job status, syncs related discovered_post, and refreshes task counts.
 * Used by both job-level and task-level approve/reject endpoints.
 */
function _transitionJobApproval(jobId, newStatus) {
  const job = store.getJob(jobId);
  if (!job) throw new Error(`job ${jobId} not found`);
  store.updateJob(jobId, { status: newStatus });
  // Sync discovered_post if one is linked to this job
  const post = store.getDiscoveredByReplyJobId(jobId);
  if (post) {
    store.updateDiscoveredPost(post.id, { status: store.discoveredStatusForJobStatus(newStatus) });
  }
  // Refresh parent task counts if job belongs to a task
  if (job.task_id) {
    store.refreshTaskCounts(job.task_id);
  }
  return store.getJob(jobId);
}

router.get('/status', (req, res) => {
  try {
    const cfg = config.loadConfig();
    const platforms = {};
    for (const [name, pCfg] of Object.entries(cfg.platforms)) {
      const acct = pCfg.account_profile || 'default';
      platforms[name] = {
        config: pCfg,
        today_count: store.countActionsToday(name, acct),
        last_action_ts: store.lastActionTs(name, acct),
      };
    }
    const c = store.jobStatusCounts();
    res.json({
      global: cfg.global,
      platforms,
      queue: {
        queued: c.queued || 0,
        awaiting_approval: c.awaiting_approval || 0,
        done: c.done || 0,
        failed: c.failed || 0,
      },
    });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/kill', (req, res) => {
  try {
    const { on } = req.body;
    if (typeof on !== 'boolean') {
      return res.status(400).json({ ok: false, error: 'on must be boolean' });
    }
    const cfg = config.loadConfig();
    cfg.global.kill_switch = on;
    config.saveConfig(cfg);
    res.json({ ok: true, global: cfg.global });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.get('/config', (req, res) => {
  try {
    res.json(config.loadConfig());
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/config', (req, res) => {
  try {
    const saved = config.saveConfig(req.body);
    res.json({ ok: true, config: saved });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.get('/templates', (req, res) => {
  try {
    const filter = {};
    if (req.query.platform) filter.platform = req.query.platform;
    if (req.query.status) filter.status = req.query.status;
    res.json(store.listTemplates(filter));
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/templates', (req, res) => {
  try {
    const { platform, kind, title, body, vars_json } = req.body;
    if (!platform || !kind) {
      return res.status(400).json({ ok: false, error: 'platform and kind required' });
    }
    const tpl = store.createTemplate({ platform, kind, title, body, vars_json });
    res.status(201).json({ ok: true, template: tpl });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/templates/:id/approve', (req, res) => {
  try {
    const id = Number(req.params.id);
    const tpl = store.getTemplate(id);
    if (!tpl) return res.status(404).json({ ok: false, error: 'not found' });
    store.setTemplateStatus(id, 'approved');
    res.json({ ok: true, template: store.getTemplate(id) });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/templates/:id/retire', (req, res) => {
  try {
    const id = Number(req.params.id);
    const tpl = store.getTemplate(id);
    if (!tpl) return res.status(404).json({ ok: false, error: 'not found' });
    store.setTemplateStatus(id, 'retired');
    res.json({ ok: true, template: store.getTemplate(id) });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.get('/jobs', (req, res) => {
  try {
    const filter = {};
    if (req.query.status) filter.status = req.query.status;
    if (req.query.platform) filter.platform = req.query.platform;
    if (req.query.campaign_id) filter.campaign_id = req.query.campaign_id;
    res.json(store.listJobs(filter));
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/check', (req, res) => {
  try {
    const { platform, account } = req.body;
    if (!platform) return res.status(400).json({ ok: false, error: 'platform required' });
    res.json({ ok: true, ...canAct(platform, account) });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

/* M2 job & log endpoints */
router.post('/jobs', (req, res) => {
  try {
    const { platform, account, template_id, payload_json, scheduled_at } = req.body;
    if (!platform) {
      return res.status(400).json({ ok: false, error: 'platform is required' });
    }
    const cfg = config.loadConfig();
    const status = cfg.global.approval_required ? 'awaiting_approval' : 'queued';
    const job = store.createJob({
      platform,
      account: account || null,
      template_id: template_id || null,
      payload_json: payload_json || null,
      scheduled_at: scheduled_at || null,
      status
    });
    res.status(201).json({ ok: true, job });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/jobs/:id/approve', (req, res) => {
  try {
    const id = Number(req.params.id);
    if (!store.getJob(id)) {
      return res.status(404).json({ ok: false, error: 'job not found' });
    }
    const job = _transitionJobApproval(id, 'queued');
    res.json({ ok: true, job });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/jobs/:id/reject', (req, res) => {
  try {
    const id = Number(req.params.id);
    if (!store.getJob(id)) {
      return res.status(404).json({ ok: false, error: 'job not found' });
    }
    const job = _transitionJobApproval(id, 'rejected');
    res.json({ ok: true, job });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.get('/logs', (req, res) => {
  try {
    const filter = {};
    if (req.query.platform) filter.platform = req.query.platform;
    if (req.query.account) filter.account = req.query.account;
    if (req.query.job_id) filter.job_id = Number(req.query.job_id);
    if (req.query.status) filter.status = req.query.status;
    res.json(store.listLogs(filter));
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

/* M3 campaign endpoints */
const campaign = require('./campaign');
router.post('/campaigns', async (req, res) => {
  try {
    const { platform, templateId, count, keywordList, startAt } = req.body;
    const camp = await campaign.launchCampaign({ platform, templateId, count, keywordList, startAt });
    res.status(201).json({ ok: true, campaign: camp });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.get('/campaigns', (req, res) => {
  try {
    const cfg = config.loadConfig();
    res.json(cfg.campaigns || []);
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

/* Discovery endpoints */
const discovery = require('./discovery');

router.get('/discovery/posts', (req, res) => {
  try {
    // PF-04: Canonicalize platform filter so "twitter" queries match "x" in DB
    const posts = store.listDiscoveredPosts({
      platform: req.query.platform ? canonicalPlatform(req.query.platform) : undefined,
      status: req.query.status,
      limit: parseInt(req.query.limit) || 50,
    });
    res.json(posts);
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/discovery/scan', async (req, res) => {
  try {
    const result = await discovery.runDiscoveryCycle();
    res.json(result);
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/discovery/approve/:id', (req, res) => {
  try {
    store.updateDiscoveredPost(parseInt(req.params.id), { status: 'approved' });
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/discovery/reject/:id', (req, res) => {
  try {
    store.updateDiscoveredPost(parseInt(req.params.id), { status: 'rejected' });
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/discovery/reply/:id', async (req, res) => {
  try {
    const post = store.listDiscoveredPosts({ limit: 1000 }).find(p => p.id === parseInt(req.params.id));
    if (!post) return res.status(404).json({ ok: false, error: 'post not found' });
    const contentGen = require('./contentGen');
    const cfg = config.loadConfig();
    const productName = cfg.global?.discovery?.product_name || 'MagnetGoogo';
    const reply = await contentGen.generateReply(post.post_title, post.post_excerpt || '', post.platform, productName);

    const initialStatus = cfg.global.approval_required ? 'awaiting_approval' : 'queued';
    const canonPlatform = canonicalPlatform(post.platform);
    const resolvedAccount = resolveAccount(canonPlatform, 'default', cfg);
    const job = store.createJob({
      platform: canonPlatform,
      account: resolvedAccount,
      payload_json: JSON.stringify({ kind: 'comment', target: post.post_url, body: reply }),
      status: initialStatus,
    });
    // P0-4 fix: mark as 'queued' (not 'replied') — only executor success should mark replied
    // FR-04: use discoveredStatusForJobStatus to keep post status in sync with job status
    const { discoveredStatusForJobStatus } = require('./discovery');
    store.updateDiscoveredPost(post.id, { status: discoveredStatusForJobStatus(job.status), reply_job_id: job.id });
    res.json({ ok: true, jobId: job.id, reply });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

/* Task management endpoints */
router.get('/tasks', (req, res) => {
  try {
    const tasks = store.listTasks({
      status: req.query.status,
      platform: req.query.platform,
      source_type: req.query.source_type,
    });
    res.json(tasks);
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/tasks', (req, res) => {
  try {
    const { name, platform, description, items, interval_min, account, payload_json, template_id, reply_style } = req.body;
    if (!name || !platform || !items || !items.length) {
      return res.status(400).json({ error: 'name, platform, and items[] required' });
    }

    // Resolve template body injection
    let templateBody = null;
    let resolvedTemplateId = template_id || null;

    if (reply_style === 'ai_smart') {
      return res.status(400).json({ error: 'AI smart reply is not supported for manual tasks — use random_template or provide explicit body' });
    }

    // Pre-load approved templates for random_template
    let approvedTemplates = null;
    if (reply_style === 'random_template' || (!reply_style && !items[0]?.body)) {
      approvedTemplates = store.listTemplates({ status: 'approved' });
      if ((!approvedTemplates || approvedTemplates.length === 0) && !items[0]?.body) {
        return res.status(400).json({ error: 'No approved templates available and no explicit body provided. Create and approve templates first.' });
      }
    } else if (template_id) {
      const tpl = store.getTemplate(template_id);
      if (tpl) {
        templateBody = tpl.body;
        resolvedTemplateId = tpl.id;
      }
    }

    // Store platform config in task payload (daily_cap, min_gap, reply_style, enabled)
    const taskPayload = payload_json || '{}';
    const canonPlatform = canonicalPlatform(platform);
    const taskId = store.createTask({ name, platform: canonPlatform, description, source_type: 'manual', total_items: items.length, payload_json: taskPayload, template_id: resolvedTemplateId });
    const jobIds = [];
    const gapMs = (interval_min || 0) * 60 * 1000;
    const cfg = config.loadConfig();
    const initialStatus = cfg.global.approval_required ? 'awaiting_approval' : 'queued';

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      // REVIEW-02: Pick random template per-item (not same for all)
      let itemBody = item.body || '';
      let itemTemplateId = resolvedTemplateId;
      if (!itemBody && approvedTemplates && approvedTemplates.length > 0) {
        const picked = approvedTemplates[Math.floor(Math.random() * approvedTemplates.length)];
        itemBody = picked.body;
        itemTemplateId = picked.id;
      } else if (!itemBody) {
        itemBody = templateBody || '';
      }
      if (!itemBody || itemBody.trim().length < 2) {
        return res.status(400).json({ error: `Item ${i + 1} has no body and no template could be resolved. Provide body or use random_template with approved templates.` });
      }
      const scheduled_at = gapMs > 0 ? new Date(Date.now() + i * gapMs).toISOString() : null;
      const j = store.createJob({
        platform, account: account || 'default',
        payload_json: JSON.stringify({ kind: item.kind || 'comment', target: item.target_url, body: itemBody }),
        template_id: itemTemplateId,
        task_id: taskId,
        scheduled_at,
        status: initialStatus,
      });
      jobIds.push(j.id);
    }
    // REVIEW-10: Sync task status with job status (not left as 'draft')
    store.updateTask(taskId, { status: initialStatus === 'awaiting_approval' ? 'awaiting_approval' : 'queued' });
    res.json({ ok: true, taskId, jobIds });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.get('/tasks/:id', (req, res) => {
  try {
    const task = store.getTask(req.params.id);
    if (!task) return res.status(404).json({ error: 'Not found' });
    const jobs = store.getTaskJobs(req.params.id);
    res.json({ ...task, jobs });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.delete('/tasks/:id', (req, res) => {
  try {
    const task = store.getTask(req.params.id);
    if (!task) return res.status(404).json({ error: 'Not found' });
    if (task.status === 'running') return res.status(400).json({ error: 'Cannot delete running task' });
    store.deleteTask(req.params.id);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/tasks/:id/start', (req, res) => {
  try {
    const task = store.getTask(req.params.id);
    if (!task) return res.status(404).json({ error: 'Not found' });
    // FR-03: Reject start if task is awaiting approval — use approve instead
    if (task.status === 'awaiting_approval') {
      return res.status(409).json({ error: 'Task is awaiting approval. Use /tasks/:id/approve to approve it first.' });
    }
    store.updateTask(task.id, { status: 'queued', started_at: new Date().toISOString() });
    // Clear failure streak for this platform to avoid blocking resumed tasks
    const { clearFailureStreak } = require('./rateLimiter');
    const jobs = store.getTaskJobs(task.id);
    const cfg = config.loadConfig();
    const canonPlat = canonicalPlatform(task.platform);
    const acct = jobs[0]?.account || resolveAccount(canonPlat, null, cfg);
    clearFailureStreak(canonPlat, acct);
    for (const j of jobs) {
      if (j.status === 'draft' || j.status === 'failed' || j.status === 'paused') {
        store.updateJob(j.id, { status: 'queued' });
      }
    }
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

router.post('/tasks/:id/pause', (req, res) => {
  try {
    const task = store.getTask(req.params.id);
    if (!task) return res.status(404).json({ error: 'Not found' });
    store.updateTask(task.id, { status: 'paused' });
    const jobs = store.getTaskJobs(task.id);
    for (const j of jobs) {
      if (j.status === 'queued') {
        store.updateJob(j.id, { status: 'paused' });
      }
    }
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// FR-02: Task-level approve — batch approve all awaiting_approval jobs
router.post('/tasks/:id/approve', (req, res) => {
  try {
    const task = store.getTask(req.params.id);
    if (!task) return res.status(404).json({ ok: false, error: 'task not found' });
    const jobs = store.getTaskJobs(task.id);
    for (const j of jobs) {
      if (j.status === 'awaiting_approval') {
        _transitionJobApproval(j.id, 'queued');
      }
    }
    store.updateTask(task.id, { status: 'queued' });
    store.refreshTaskCounts(task.id);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// FR-02: Task-level reject — batch reject all awaiting_approval jobs
router.post('/tasks/:id/reject', (req, res) => {
  try {
    const task = store.getTask(req.params.id);
    if (!task) return res.status(404).json({ ok: false, error: 'task not found' });
    const jobs = store.getTaskJobs(task.id);
    for (const j of jobs) {
      if (j.status === 'awaiting_approval') {
        _transitionJobApproval(j.id, 'rejected');
      }
    }
    store.updateTask(task.id, { status: 'rejected' });
    store.refreshTaskCounts(task.id);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Boot the OpenCLI job executor polling loop (runs every 60 seconds)
const { startExecutor } = require('./executor');
startExecutor(60);

module.exports = router;
