/**
 * Fetch bt4gprx.com via Tier 2 (Chromium + extension) and save HTML for selector analysis.
 */
import { execFile } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Find Playwright Chromium
const home = process.env.USERPROFILE || '';
const pwDir = path.join(home, 'AppData', 'Local', 'ms-playwright');
let chromiumPath = '';
if (fs.existsSync(pwDir)) {
  const dirs = fs.readdirSync(pwDir).filter(d => d.startsWith('chromium-')).sort().reverse();
  for (const dir of dirs) {
    for (const sub of ['chrome-win64', 'chrome-win']) {
      const exe = path.join(pwDir, dir, sub, 'chrome.exe');
      if (fs.existsSync(exe)) { chromiumPath = exe; break; }
    }
    if (chromiumPath) break;
  }
}
if (!chromiumPath) { console.error('Chromium not found'); process.exit(1); }

const extDir = path.resolve(path.join(__dirname, 'verify-extension'));
const tmpDir = path.join(process.env.TEMP || '/tmp', `magnet-html-${Date.now()}`);
const url = process.argv[2] || 'https://bt4gprx.com/search?q=test&p=1';

console.log(`URL: ${url}`);
console.log(`Chromium: ${chromiumPath}\n`);

const args = [
  `--user-data-dir=${tmpDir}`,
  '--no-first-run', '--no-default-browser-check',
  '--window-size=1024,700',
  '--disable-blink-features=AutomationControlled',
  `--load-extension=${extDir}`,
  `--disable-extensions-except=${extDir}`,
  url,
];

const child = execFile(chromiumPath, args, { windowsHide: false });
child.unref();

console.log('Chromium launched. Waiting for HTML via /api/verify...\n');

const startTs = Date.now();
const poll = setInterval(async () => {
  if (Date.now() - startTs > 90_000) {
    console.log('Timeout');
    clearInterval(poll);
    process.exit(1);
  }
  try {
    const origin = new URL(url).origin;
    const resp = await fetch(`http://localhost:3000/api/verify-status?origin=${encodeURIComponent(origin)}`);
    const data = await resp.json();
    if (data.has_cookies) {
      // Wait for content.js to submit HTML (3s delay + processing)
      console.log('Cookies arrived, waiting for HTML...');
      await new Promise(r => setTimeout(r, 6000));
      
      // Fetch with HTML
      const r2 = await fetch(`http://localhost:3000/api/verify-status?origin=${encodeURIComponent(origin)}&html=1`);
      const d2 = await r2.json();
      
      console.log(`Cookies: ${d2.cookie_count}`);
      console.log(`HTML size: ${d2.html_size} bytes`);
      
      if (d2.html) {
        const outFile = path.join(__dirname, 'debug-page.html');
        fs.writeFileSync(outFile, d2.html, 'utf-8');
        console.log(`\nHTML saved to: ${outFile}`);
        console.log(`Open in browser to inspect structure.`);
      } else {
        console.log('No HTML received.');
      }
      
      clearInterval(poll);
      try { child.kill(); } catch {}
      fs.rm(tmpDir, { recursive: true, force: true }, () => {});
      setTimeout(() => process.exit(0), 1000);
    }
  } catch {}
}, 3000);
