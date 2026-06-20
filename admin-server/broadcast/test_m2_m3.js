const fs = require('fs');
const path = require('path');
const assert = require('assert');

// 1. Mock child_process before requiring executor
const cp = require('child_process');
let lastSpawnArgs = null;
let spawnMockResult = { status: 0, stdout: 'Mock post success', stderr: '' };

cp.spawnSync = (cmd, args, opts) => {
  lastSpawnArgs = { cmd, args, opts };
  return spawnMockResult;
};

// 2. Mock global.fetch before requiring contentGen / campaign
let lastFetchParams = null;
global.fetch = async (url, options) => {
  lastFetchParams = { url, options };
  return {
    ok: true,
    status: 200,
    text: async () => 'Mock response text',
    json: async () => ({
      choices: [
        {
          message: {
            content: 'Mocked rewritten post content with keyword'
          }
        }
      ]
    })
  };
};

// Now import modules
const store = require('./store');
const config = require('./config');
const contentGen = require('./contentGen');
const campaign = require('./campaign');
const executor = require('./executor');

// Backups
const configPath = path.resolve(__dirname, '..', '..', 'broadcast-config.json');
const configBackup = path.resolve(__dirname, '..', '..', 'broadcast-config.json.bak');
if (fs.existsSync(configPath)) {
  fs.copyFileSync(configPath, configBackup);
}

function restoreAll() {
  if (fs.existsSync(configBackup)) {
    fs.copyFileSync(configBackup, configPath);
    fs.unlinkSync(configBackup);
  }
  // Clear any test data from database
  const db = new (require('better-sqlite3'))(path.resolve(__dirname, '..', 'broadcast.db'));
  db.prepare("DELETE FROM templates WHERE platform = 'testplatform'").run();
  db.prepare("DELETE FROM jobs WHERE platform = 'testplatform'").run();
  db.prepare("DELETE FROM logs WHERE platform = 'testplatform'").run();
}

async function runTests() {
  console.log('Starting M2 & M3 tests...');

  try {
    // Clean start
    restoreAll();

    // Setup config for testplatform
    const cfg = config.loadConfig();
    cfg.global.enabled = true;
    cfg.global.kill_switch = false;
    cfg.global.approval_required = false; // direct queuing
    cfg.platforms.testplatform = {
      enabled: true,
      engine: 'opencli',
      daily_cap: 5,
      min_gap_min: 10,
      account_profile: 'test_user'
    };
    config.saveConfig(cfg);

    // Set mock env for content gen
    process.env.OPENAI_API_KEY = 'mock-key';

    // Test 1: LLM Content Generator
    console.log('Running Test 1: Content Generator...');
    const variant = await contentGen.generateVariant('Hello, this is a test template.', 'testplatform', 'mykeyword');
    assert.strictEqual(variant, 'Mocked rewritten post content with keyword');
    assert.ok(lastFetchParams.url.includes('/chat/completions'));
    assert.strictEqual(lastFetchParams.options.headers.Authorization, 'Bearer mock-key');
    console.log('✓ Test 1 Passed.');

    // Test 2: Campaign Coordinator
    console.log('Running Test 2: Campaign Coordinator...');
    // Create template
    const tpl = store.createTemplate({
      platform: 'testplatform',
      kind: 'post',
      title: 'Test Title',
      body: 'Test Body',
      vars_json: {}
    });
    
    const camp = await campaign.launchCampaign({
      platform: 'testplatform',
      templateId: tpl.id,
      count: 2,
      keywordList: ['kw1', 'kw2'],
      startAt: new Date().toISOString()
    });

    assert.ok(camp.id);
    assert.strictEqual(camp.count, 2);

    // Verify jobs in DB
    const jobs = store.listJobs({ platform: 'testplatform' });
    assert.strictEqual(jobs.length, 2);
    
    // Sort by scheduled_at ascending
    jobs.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
    assert.strictEqual(jobs[0].status, 'queued'); // global approval_required was false
    assert.strictEqual(jobs[0].account, 'test_user');
    
    // Check staggering
    const timeDiffMs = new Date(jobs[1].scheduled_at) - new Date(jobs[0].scheduled_at);
    assert.strictEqual(timeDiffMs, 10 * 60 * 1000); // 10 minutes in ms
    console.log('✓ Test 2 Passed.');

    // Test 3: Executor execution
    console.log('Running Test 3: Executor execution...');
    
    // Execute poll manually
    await executor.pollAndExecute();

    // Verify first job was executed, second not (since scheduled_at for job 2 is 10 min from now)
    const updatedJobs = store.listJobs({ platform: 'testplatform' });
    updatedJobs.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
    
    assert.strictEqual(updatedJobs[0].status, 'done');
    assert.strictEqual(updatedJobs[1].status, 'queued'); // not executed yet
    
    // Check spawn args
    assert.ok(lastSpawnArgs);
    assert.strictEqual(lastSpawnArgs.cmd, 'opencli');
    // For testplatform (generic), should fall back to twitter reply/post style args (since not zhihu/reddit/xiaohongshu)
    assert.deepStrictEqual(lastSpawnArgs.args, ['--profile', 'test_user', 'twitter', 'post', 'Mocked rewritten post content with keyword']);

    // Verify logs
    const logs = store.listLogs({ platform: 'testplatform' });
    assert.strictEqual(logs.length, 1);
    assert.strictEqual(logs[0].status, 'done');
    assert.strictEqual(logs[0].job_id, updatedJobs[0].id);
    console.log('✓ Test 3 Passed.');

    // Test 4: Rate Limiter integration & skipping
    console.log('Running Test 4: Rate Limiter integration & skipping...');
    
    // Set scheduled_at for job 2 to past so it's runnable, but min_gap is violated (since job 1 just ran)
    store.updateJob(updatedJobs[1].id, { scheduled_at: new Date().toISOString() });
    
    // Poll again
    await executor.pollAndExecute();

    // Job 2 should be skipped due to rate limiting
    const updatedJobs2 = store.listJobs({ platform: 'testplatform' });
    updatedJobs2.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
    assert.strictEqual(updatedJobs2[1].status, 'skipped');

    const logs2 = store.listLogs({ platform: 'testplatform' });
    // Should have 2 logs: 1 done, 1 skipped (which is order-wise at index 0 because ordered by id desc)
    assert.strictEqual(logs2.length, 2);
    assert.strictEqual(logs2[0].status, 'skipped');
    assert.ok(logs2[0].detail.includes('min_gap_not_elapsed'));
    console.log('✓ Test 4 Passed.');

    console.log('M2-M3 validation passed');
  } catch (err) {
    console.error('Test failed:', err);
    process.exitCode = 1;
  } finally {
    restoreAll();
    console.log('Cleanup completed.');
  }
}

runTests();
