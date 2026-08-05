#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const checkOnly = args.includes('--check');
const rootArg = args.find((arg) => !arg.startsWith('--'));
const siteRoot = path.resolve(rootArg || path.join(__dirname, '..', 'magnetgoogo-site'));
const configPath = path.join(siteRoot, 'site-config.json');

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, ''));
}

function walkHtml(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '.git' || entry.name === 'node_modules') continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walkHtml(full, out);
    else if (entry.isFile() && entry.name.endsWith('.html')) out.push(full);
  }
  return out;
}

function withHref(attrs, url) {
  let next = attrs;
  if (/\bhref\s*=\s*(["']).*?\1/i.test(next)) {
    next = next.replace(/\bhref\s*=\s*(["']).*?\1/i, `href="${url}"`);
  } else {
    next = ` href="${url}"${next}`;
  }
  if (!/\btarget\s*=/i.test(next)) next += ' target="_blank"';
  if (!/\brel\s*=/i.test(next)) next += ' rel="noopener"';
  return next;
}

if (!fs.existsSync(configPath)) {
  throw new Error(`Missing site config: ${configPath}`);
}

const config = loadJson(configPath);
const primaryUrl = typeof config.download_url === 'string' ? config.download_url.trim() : '';
const backups = Array.isArray(config.backup_downloads) ? config.backup_downloads : [];
const github = backups.find((item) => item && item.label === 'GitHub');
const lanzou = backups.find((item) => item && item.label === '蓝奏云');
if (!primaryUrl) throw new Error('site-config.json is missing the primary download URL');
if (!github?.url) throw new Error('site-config.json is missing the GitHub backup URL');
if (!lanzou?.url) throw new Error('site-config.json is missing the Lanzou backup URL');
const password = String(lanzou.password || '8888');

const anchorPattern = /<a\b([^>]*)>\s*(备用下载（GitHub）|Backup Download \(GitHub\))\s*<\/a>/gi;
const htmlFiles = walkHtml(siteRoot);
let changedFiles = 0;
let insertedLinks = 0;
let missingFiles = 0;

for (const file of htmlFiles) {
  const original = fs.readFileSync(file, 'utf8');
  let updated = original
    .replace(/https:\/\/cn\.magnetgoogo\.com\/download\/magnetgoogo\.apk/g, primaryUrl)
    .replace(/https:\/\/api\.naoshiquan\.com\/download\/v[^"'<>/]+\/magnetgoogo-v[^"'<>/]+\.apk/g, primaryUrl)
    .replace(/https:\/\/github\.com\/734496335\/magnetgoogo\/releases\/download\/v[^"'<>/]+\/magnetgoogo-v[^"'<>/]+\.apk/g, github.url)
    .replace(/https:\/\/wwbdy\.lanzn\.com\/[A-Za-z0-9]+/g, lanzou.url)
    .replace(/蓝奏云（密码：\d+）/g, `蓝奏云（密码：${password}）`)
    .replace(/LanzouCloud \(password: \d+\)/g, `LanzouCloud (password: ${password})`);

  const hasGitHubBackup = /备用下载（GitHub）|Backup Download \(GitHub\)/i.test(updated);
  const hasLanzou = updated.includes(lanzou.url);
  if (hasGitHubBackup && !hasLanzou) {
    missingFiles += 1;
    updated = updated.replace(anchorPattern, (whole, attrs, label) => {
      insertedLinks += 1;
      const newAttrs = withHref(attrs, lanzou.url);
      const lanzouLabel = label.startsWith('Backup')
        ? `LanzouCloud (password: ${password})`
        : `蓝奏云（密码：${password}）`;
      return `${whole}\n      <a${newAttrs}>${lanzouLabel}</a>`;
    });
  }

  if (updated !== original) {
    if (!checkOnly) fs.writeFileSync(file, updated, 'utf8');
    changedFiles += 1;
  }
}

const summary = {
  siteRoot,
  checkOnly,
  htmlFiles: htmlFiles.length,
  missingFiles,
  changedFiles,
  insertedLinks,
  primaryUrl,
  lanzouUrl: lanzou.url,
  password,
};
console.log(JSON.stringify(summary, null, 2));

if (checkOnly && missingFiles > 0) process.exitCode = 1;
