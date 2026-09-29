import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..');
const SITE_DIR = path.join(PROJECT_ROOT, 'magnetgoogo-site');
const RUNTIME_DIR = path.join(PROJECT_ROOT, 'growth-ops', 'runtime');
const STATUS_FILE = path.join(RUNTIME_DIR, 'public-status-refresh.json');

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

function run(label, command, args, cwd, timeoutMs = 10 * 60_000) {
  const started = Date.now();
  const result = spawnSync(command, args, {
    cwd,
    env: process.env,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: timeoutMs,
    windowsHide: true,
  });
  const output = `${result.stdout || ''}${result.stderr || ''}`.trim();
  if (output) console.log(`[${label}]\n${output}`);
  return {
    label,
    status: result.status === 0 ? 'PASS' : 'FAIL',
    exit_code: result.status,
    signal: result.signal || null,
    duration_ms: Date.now() - started,
    output_tail: output.slice(-1600),
  };
}

function main() {
  const startedAt = new Date().toISOString();
  const npx = process.platform === 'win32' ? (process.env.ComSpec || 'cmd.exe') : 'npx';
  const npxArgs = process.platform === 'win32'
    ? ['/d', '/s', '/c', 'npx wrangler@4.126.0 pages deploy . --project-name magnetgoogo-site --branch main --commit-dirty=true']
    : ['wrangler@4.126.0', 'pages', 'deploy', '.', '--project-name', 'magnetgoogo-site', '--branch', 'main', '--commit-dirty=true'];
  const steps = [];
  steps.push(run('probe', process.execPath, [path.join(PROJECT_ROOT, 'scripts', 'probe-public-reachability.js'), '--write'], PROJECT_ROOT));
  if (steps.at(-1).status === 'PASS') {
    steps.push(run('local-watchdog', process.execPath, [path.join(SITE_DIR, 'scripts', 'status-freshness-watchdog.js')], PROJECT_ROOT));
  }
  if (steps.every((step) => step.status === 'PASS')) {
    steps.push(run('pages-deploy', npx, npxArgs, SITE_DIR, 15 * 60_000));
  }
  if (steps.every((step) => step.status === 'PASS')) {
    steps.push(run('production-watchdog', process.execPath, [path.join(SITE_DIR, 'scripts', 'status-freshness-watchdog.js'), '--url', 'https://magnetgoogo.com/data/status-public.json'], PROJECT_ROOT));
  }
  const ok = steps.length === 4 && steps.every((step) => step.status === 'PASS');
  const status = {
    schema_version: 1,
    status: ok ? 'PASS' : 'FAIL',
    started_at: startedAt,
    finished_at: new Date().toISOString(),
    steps,
    policy: {
      frequency_target_hours: 4,
      freshness_sla_hours: 6,
      immutable_history: true,
      direct_upload_pages: true,
      fail_closed_on_probe_or_deploy_failure: true,
    },
  };
  atomicWriteJson(STATUS_FILE, status);
  console.log(JSON.stringify({ status: status.status, status_file: STATUS_FILE, steps: steps.map(({ label, status: s }) => ({ label, status: s })) }, null, 2));
  if (!ok) process.exitCode = 1;
}

main();
