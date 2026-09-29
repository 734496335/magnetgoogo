'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const rootEnv = path.resolve(__dirname, '..', '..', '.env');
if (!fs.existsSync(rootEnv)) {
  console.error('ADMIN_SECRET sync blocked: root .env not found');
  process.exit(2);
}

const line = fs.readFileSync(rootEnv, 'utf8')
  .split(/\r?\n/)
  .find((row) => row.trim().startsWith('ADMIN_SECRET='));
if (!line) {
  console.error('ADMIN_SECRET sync blocked: ADMIN_SECRET missing from root .env');
  process.exit(3);
}

const value = line.slice(line.indexOf('=') + 1).trim().replace(/^["']|["']$/g, '');
if (!value) {
  console.error('ADMIN_SECRET sync blocked: ADMIN_SECRET is empty');
  process.exit(4);
}

const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const result = spawnSync(npx, ['wrangler@4.126.0', 'secret', 'put', 'ADMIN_SECRET'], {
  cwd: path.resolve(__dirname, '..'),
  input: `${value}\n`,
  encoding: 'utf8',
  stdio: ['pipe', 'pipe', 'pipe'],
  shell: process.platform === 'win32',
});

if (result.status !== 0) {
  const safeParts = [result.error?.message, result.stderr, result.stdout]
    .filter(Boolean)
    .map((part) => String(part).replaceAll(value, '[REDACTED]').trim())
    .filter(Boolean);
  console.error(safeParts.join('\n') || `wrangler secret put failed (status=${result.status})`);
  process.exit(result.status || 5);
}

console.log('PASS: ADMIN_SECRET stored as Cloudflare Secret binding');
