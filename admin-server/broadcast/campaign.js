const store = require('./store');
const config = require('./config');
const { canonicalPlatform } = config;
const contentGen = require('./contentGen');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function launchCampaign(cfgParams) {
  const { platform: rawPlatform, templateId, count, keywordList, startAt } = cfgParams;

  if (!rawPlatform) throw new Error('platform is required');
  if (!templateId) throw new Error('templateId is required');
  const jobCount = parseInt(count, 10);
  if (isNaN(jobCount) || jobCount <= 0) {
    throw new Error('count must be a positive integer');
  }
  if (jobCount > 500) {
    throw new Error('count cannot exceed 500 jobs per campaign');
  }

  // PF-03: Canonicalize platform for config/DB identity; keep original for contentGen style guide
  const platform = canonicalPlatform(rawPlatform);

  const tpl = store.getTemplate(templateId);
  if (!tpl) {
    throw new Error(`Template not found: ${templateId}`);
  }

  const cfg = config.loadConfig();
  const pCfg = cfg.platforms[platform];
  if (!pCfg) {
    throw new Error(`Platform config not found for: ${rawPlatform}`);
  }

  let keywords = [];
  if (Array.isArray(keywordList)) {
    keywords = keywordList;
  } else if (typeof keywordList === 'string') {
    keywords = keywordList.split(',').map(s => s.trim()).filter(Boolean);
  }

  const minGapMin = pCfg.min_gap_min || 30;
  const startTime = startAt ? new Date(startAt).getTime() : Date.now();
  const campaignId = `camp_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

  // Create a task for this campaign
  const taskId = store.createTask({
    name: cfgParams.name || `Campaign ${new Date().toISOString().slice(0,10)}`,
    platform,
    source_type: 'campaign',
    source_id: campaignId,
    template_id: templateId,
    total_items: jobCount,
  });

  // Build job creation tasks (deferred, not yet invoked)
  const jobTasks = [];
  for (let i = 0; i < jobCount; i++) {
    const keyword = keywords.length > 0 ? keywords[i % keywords.length] : null;
    const scheduledTime = new Date(startTime + i * minGapMin * 60 * 1000).toISOString();

    jobTasks.push(async () => {
      let bodyText = tpl.body;
      if (keyword) {
        try {
          // PF-03: Use original platform name for contentGen style guide (e.g. zhihu/xiaohongshu are not aliases)
          bodyText = await contentGen.generateVariant(tpl.body, rawPlatform, keyword);
        } catch (err) {
          console.error(`[campaign] LLM variant generation failed for keyword "${keyword}":`, err.message);
          // fallback to original template body on failure
        }
      }

      const payload = {
        body: bodyText,
        title: tpl.title || null,
        target: null
      };

      const status = cfg.global.approval_required ? 'awaiting_approval' : 'queued';

      store.createJob({
        campaign_id: campaignId,
        platform,
        account: pCfg.account_profile || 'default',
        template_id: templateId,
        payload_json: payload,
        scheduled_at: scheduledTime,
        status,
        task_id: taskId,
      });
    });
  }

  // Generate variants sequentially with a 500ms delay between LLM calls
  for (let i = 0; i < jobTasks.length; i++) {
    await jobTasks[i]();
    if (i < jobTasks.length - 1) {
      await sleep(500);
    }
  }

  // Save campaign metadata to broadcast-config.json
  const campaignMeta = {
    id: campaignId,
    platform,  // canonical platform
    template_id: templateId,
    count: jobCount,
    keywords,
    start_at: new Date(startTime).toISOString(),
    created_at: new Date().toISOString()
  };

  cfg.campaigns = cfg.campaigns || [];
  cfg.campaigns.push(campaignMeta);
  config.saveConfig(cfg);

  // FR-05: Set task status based on approval_required (sync with job initial status)
  const taskStatus = cfg.global.approval_required ? 'awaiting_approval' : 'queued';
  store.updateTask(taskId, { status: taskStatus });

  return campaignMeta;
}

module.exports = { launchCampaign };
