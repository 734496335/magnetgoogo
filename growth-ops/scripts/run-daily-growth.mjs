import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..');
const RUNTIME_DIR = path.join(PROJECT_ROOT, 'growth-ops', 'runtime');
const STATUS_FILE = path.join(RUNTIME_DIR, 'daily-growth-status.json');

function loadDotEnv() {
  const file = path.join(PROJECT_ROOT, '.env');
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    if (!line || /^\s*#/.test(line)) continue;
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match || process.env[match[1]] !== undefined) continue;
    process.env[match[1]] = match[2].trim();
  }
}

function atomicWriteJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
  try {
    fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
    fs.renameSync(tmp, file);
  } finally {
    try { if (fs.existsSync(tmp)) fs.unlinkSync(tmp); } catch { /* best effort */ }
  }
}

function runNode(label, relativeScript, args = [], allowedBlockedExitCodes = []) {
  const started = Date.now();
  const result = spawnSync(process.execPath, [path.join(PROJECT_ROOT, relativeScript), ...args], {
    cwd: PROJECT_ROOT,
    env: process.env,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 10 * 60_000,
  });
  const output = `${result.stdout || ''}${result.stderr || ''}`.trim();
  if (output) console.log(`[${label}]\n${output}`);
  const status = result.status === 0
    ? 'PASS'
    : allowedBlockedExitCodes.includes(result.status)
      ? 'BLOCKED_EXTERNAL_AUTH'
      : 'FAIL';
  return {
    label,
    status,
    exit_code: result.status,
    signal: result.signal || null,
    duration_ms: Date.now() - started,
    output_tail: output.slice(-1200),
  };
}

function main() {
  loadDotEnv();
  const startedAt = new Date().toISOString();
  const steps = [];
  steps.push(runNode('search-console-ingest', 'growth-ops/scripts/search-console-ingest.mjs', ['--write'], [2]));
  const nsqIngest = runNode('nsq-search-console-ingest', 'growth-ops/scripts/search-console-ingest.mjs', [
    '--site-url', 'sc-domain:naoshiquan.com',
    '--out', 'growth-ops/search-console/nsq-latest.json',
    '--status-out', 'growth-ops/search-console/nsq-ingest-status.json',
    '--write',
  ], [2]);
  steps.push(nsqIngest);
  if (nsqIngest.status === 'PASS') {
    steps.push(runNode('nsq-search-opportunities', 'growth-ops/scripts/nsq-search-console-opportunities.mjs', ['--write']));
  }
  steps.push(runNode('growth-kpi', 'growth-ops/scripts/growth-kpi.mjs'));
  steps.push(runNode('opportunity-report', 'growth-ops/scripts/growth-opportunity-report.mjs', ['--write']));
  const ok = steps.every((step) => step.status === 'PASS' || step.status === 'BLOCKED_EXTERNAL_AUTH');
  const status = {
    schema_version: 1,
    status: ok ? 'PASS' : 'FAIL',
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    steps,
    rules: {
      no_new_indexable_urls: true,
      no_auto_publish_page_changes: true,
      search_console_scope: 'webmasters.readonly',
      raw_query_data_location: 'gitignored local growth-ops/search-console',
    },
  };
  atomicWriteJson(STATUS_FILE, status);
  console.log(JSON.stringify({ status: status.status, status_file: STATUS_FILE, steps: steps.map(({ label, status: s }) => ({ label, status: s })) }, null, 2));
  if (!ok) process.exitCode = 1;
}

main();
