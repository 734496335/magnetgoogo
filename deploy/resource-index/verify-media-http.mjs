import crypto from 'node:crypto';
import fs from 'node:fs';

function argument(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function fail(message, context = {}) {
  process.stdout.write(`${JSON.stringify({ status: 'failed', message, context })}\n`);
  process.exit(1);
}

const base = (argument('--base') || '').replace(/\/$/, '');
const planPath = argument('--plan');
const expectedCurrentStatus = Number(argument('--expected-current-status', '404'));
const expectedCurrentHash = argument('--expected-current-sha256');
if (!base.startsWith('https://') || !planPath) fail('invalid endpoint verification arguments');

const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
if (plan.schema_version !== 'media-publish-plan/1' || !Array.isArray(plan.files)) {
  fail('invalid media publish plan');
}

const kinds = ['catalog', 'cover', 'detail', 'resources', 'manifest'];
const samples = kinds.map((kind) => plan.files.find((item) => item.object_kind === kind)).filter(Boolean);
const checks = [];
for (const sample of samples) {
  const response = await fetch(`${base}/${sample.key}`, {
    headers: { 'user-agent': 'MagnetGoogo-Media-Endpoint-Verify/1' },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) fail('media sample request failed', { key: sample.key, status: response.status });
  const payload = Buffer.from(await response.arrayBuffer());
  const digest = crypto.createHash('sha256').update(payload).digest('hex');
  if (payload.length !== sample.size || digest !== sample.sha256) {
    fail('media sample hash or size mismatch', {
      key: sample.key,
      expected_size: sample.size,
      actual_size: payload.length,
      expected_sha256: sample.sha256,
      actual_sha256: digest,
    });
  }
  checks.push({ key: sample.key, size: payload.length, sha256: digest, match: true });
}

const currentResponse = await fetch(`${base}/v1/current.json`, {
  headers: { 'user-agent': 'MagnetGoogo-Media-Endpoint-Verify/1' },
  signal: AbortSignal.timeout(20_000),
});
if (currentResponse.status !== expectedCurrentStatus) {
  fail('unexpected current pointer HTTP status', {
    expected: expectedCurrentStatus,
    actual: currentResponse.status,
  });
}
let currentSha256 = null;
if (expectedCurrentStatus === 200) {
  const payload = Buffer.from(await currentResponse.arrayBuffer());
  currentSha256 = crypto.createHash('sha256').update(payload).digest('hex');
  if (expectedCurrentHash && currentSha256 !== expectedCurrentHash) {
    fail('current pointer SHA-256 mismatch', { expected: expectedCurrentHash, actual: currentSha256 });
  }
}

process.stdout.write(`${JSON.stringify({
  status: 'pass',
  base,
  checks,
  current_status: currentResponse.status,
  current_sha256: currentSha256,
})}\n`);
