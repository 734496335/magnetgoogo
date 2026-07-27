import crypto from 'node:crypto';
import fs from 'node:fs';

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

const url = argument('--url');
const output = argument('--output');
const report = argument('--report');
if (!url?.startsWith('https://') || !output || !report) {
  console.error('invalid fetch-media-file arguments');
  process.exit(2);
}

try {
  const response = await fetch(url, {
    headers: { 'user-agent': 'MagnetGoogo-Media-Control-Verify/1' },
    signal: AbortSignal.timeout(20_000),
  });
  const payload = Buffer.from(await response.arrayBuffer());
  if (response.status === 200) fs.writeFileSync(output, payload);
  fs.writeFileSync(report, JSON.stringify({
    status: response.status,
    bytes: payload.length,
    sha256: payload.length ? crypto.createHash('sha256').update(payload).digest('hex') : null,
  }));
} catch (error) {
  fs.writeFileSync(report, JSON.stringify({
    status: 0,
    error: error instanceof Error ? error.message : String(error),
  }));
  process.exit(1);
}
