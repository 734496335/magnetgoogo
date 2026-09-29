#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { SITE_DIR, HOST, urlToFile, normalizeUrl } = require('./seo-common');

const sitemapPath = path.join(SITE_DIR, 'sitemap.xml');
const sitemap = fs.readFileSync(sitemapPath, 'utf8');
const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/gi)].map((m) => normalizeUrl(m[1])).filter(Boolean);
const latestConfig = JSON.parse(fs.readFileSync(path.join(SITE_DIR, 'config.json'), 'utf8').replace(/^\uFEFF/, ''));
const latestVersion = String(latestConfig.latest_version || '').trim();
if (!/^\d+\.\d+\.\d+$/.test(latestVersion)) throw new Error(`invalid latest_version: ${latestVersion}`);

const staleVersionPattern = /(?:\/download\/v|releases\/download\/v)(0\.2\.6|0\.2\.5|0\.2\.4|0\.2\.3|0\.2\.2|0\.2\.1)(?:\/|\b)/i;
const staleLanzouPattern = /wwbdy\.lanzn\.com\/irfev42qyyne/i;
const trackedPattern = /https:\/\/api\.naoshiquan\.com\/go\/download\?[^"'<>\s]+/i;
const visibleSemverPattern = /\b(?:v\s*)?0\.\d+\.\d+\b/i;

const mustTrack = new Map([
  [`${HOST}/`, 'home'],
  [`${HOST}/en/`, 'home-en'],
  [`${HOST}/ja/`, 'home-ja'],
  [`${HOST}/ko/`, 'home-ko'],
  [`${HOST}/ru/`, 'home-ru'],
  [`${HOST}/es/`, 'home-es'],
  [`${HOST}/pt/`, 'home-pt'],
  [`${HOST}/de/`, 'home-de'],
  [`${HOST}/fr/`, 'home-fr'],
  [`${HOST}/ar/`, 'home-ar'],
  [`${HOST}/hi/`, 'home-hi'],
  [`${HOST}/guide/free-magnet-search`, 'guide-free-magnet-search'],
  [`${HOST}/guide/magnet-search-engine`, 'guide-magnet-search-engine'],
  [`${HOST}/guide/torrent-search`, 'guide-torrent-search'],
  [`${HOST}/guide/cili-sousuo`, 'cn-guide-cili-sousuo'],
  [`${HOST}/guide/cili-lianjie-sousuo`, 'cn-guide-cili-link-search'],
  [`${HOST}/blog/best-magnet-search-2026`, 'blog-best-magnet-search'],
  [`${HOST}/guide/2026-nengyong-de-cili-zhan`, 'guide-live-sites'],
  [`${HOST}/faq`, 'faq'],
  [`${HOST}/alt/bt1207-alternative`, 'gsc-bt1207-opportunity'],
  [`${HOST}/alt/cilimei-alternative`, 'gsc-cilimei-opportunity'],
  [`${HOST}/status/`, 'status'],
  [`${HOST}/sites/`, 'sites'],
  [`${HOST}/tools/magnet-link-parser/`, 'magnet-parser'],
]);

const expectedGrowthPageKey = new Map([
  [`${HOST}/`, 'home'],
  [`${HOST}/en/`, 'home'], [`${HOST}/ja/`, 'home'], [`${HOST}/ko/`, 'home'], [`${HOST}/ru/`, 'home'],
  [`${HOST}/es/`, 'home'], [`${HOST}/pt/`, 'home'], [`${HOST}/de/`, 'home'], [`${HOST}/fr/`, 'home'],
  [`${HOST}/ar/`, 'home'], [`${HOST}/hi/`, 'home'],
  [`${HOST}/guide/free-magnet-search`, 'guide:free-magnet-search'],
  [`${HOST}/guide/magnet-search-engine`, 'guide:magnet-search-engine'],
  [`${HOST}/guide/torrent-search`, 'guide:torrent-search'],
  [`${HOST}/guide/cili-sousuo`, 'guide:cili-sousuo'],
  [`${HOST}/guide/cili-lianjie-sousuo`, 'guide:cili-lianjie-sousuo'],
  [`${HOST}/blog/best-magnet-search-2026`, 'blog:best-magnet-search-2026'],
  [`${HOST}/guide/2026-nengyong-de-cili-zhan`, 'guide:2026-nengyong-de-cili-zhan'],
  [`${HOST}/faq`, 'faq'],
  [`${HOST}/alt/bt1207-alternative`, 'alt:bt1207-alternative'],
  [`${HOST}/alt/cilimei-alternative`, 'alt:cilimei-alternative'],
  [`${HOST}/status/`, 'status'],
  [`${HOST}/sites/`, 'sites-directory'],
  [`${HOST}/tools/magnet-link-parser/`, 'tools:magnet-parser'],
]);

const errors = [];
for (const [url, label] of mustTrack) {
  if (/\.html(?:$|[?#])/i.test(url)) errors.push(`growth-critical canonical must use Cloudflare Pages final extensionless URL (${label}): ${url}`);
}
let staleIndexable = 0;
let trackedCore = 0;
let attributionTrackedCore = 0;
let attributionTrackedAll = 0;
for (const url of urls) {
  const file = urlToFile(url);
  if (!file || !fs.existsSync(file)) {
    errors.push(`missing local file for sitemap URL: ${url}`);
    continue;
  }
  const html = fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
  const label = mustTrack.get(url);
  if (!html.includes('/js/growth-attribution.js')) {
    errors.push(`${path.relative(SITE_DIR, file)}: indexable page missing privacy-safe acquisition attribution tracker`);
  } else {
    attributionTrackedAll += 1;
  }
  let growthSurface = html;
  if (url === `${HOST}/status/`) growthSurface += fs.readFileSync(path.join(SITE_DIR, 'status', 'status.js'), 'utf8');
  if (url === `${HOST}/tools/magnet-link-parser/`) growthSurface += fs.readFileSync(path.join(SITE_DIR, 'tools', 'magnet-tool.js'), 'utf8');
  const visibleText = html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ');
  const visibleSemver = visibleText.match(visibleSemverPattern);
  if (visibleSemver) {
    errors.push(`${path.relative(SITE_DIR, file)}: SEO-visible App semver is forbidden by BL-049 (${visibleSemver[0]})`);
  }
  const stale = html.match(staleVersionPattern);
  if (stale) {
    staleIndexable += 1;
    errors.push(`${path.relative(SITE_DIR, file)}: stale versioned download link ${stale[1]}`);
  }
  if (staleLanzouPattern.test(html)) {
    errors.push(`${path.relative(SITE_DIR, file)}: stale Lanzou landing irfev42qyyne`);
  }
  if (label) {
    if (!trackedPattern.test(growthSurface)) {
      errors.push(`${path.relative(SITE_DIR, file)}: growth-critical page missing tracked /go/download CTA (${label})`);
    } else {
      trackedCore += 1;
    }
    const pageKey = expectedGrowthPageKey.get(url);
    if (!pageKey) {
      errors.push(`${path.relative(SITE_DIR, file)}: missing expected growth page key contract (${label})`);
    } else {
      const escapedPageKey = pageKey.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const trackerPattern = new RegExp(`growth-attribution\\.js(?:\\?[^\"]*)?\" data-growth-page=\"${escapedPageKey}\"`);
      if (!trackerPattern.test(html)) {
        errors.push(`${path.relative(SITE_DIR, file)}: growth-critical page missing attribution tracker page key ${pageKey} (${label})`);
      } else if (!growthSurface.includes(`page=${pageKey}`)) {
        errors.push(`${path.relative(SITE_DIR, file)}: tracker page key ${pageKey} does not match any tracked download CTA (${label})`);
      } else {
        attributionTrackedCore += 1;
      }
    }
  }
}

const domesticCore = [...mustTrack.keys()].filter((url) => url.includes('/guide/cili-') || url === `${HOST}/`).length;
const internationalCore = [...mustTrack.keys()].filter((url) => url.includes('/en/') || url.includes('magnet-search') || url.includes('torrent-search')).length;
console.log(`SEO growth audit: sitemap=${urls.length} latest=${latestVersion} core=${mustTrack.size} tracked_core=${trackedCore} attribution_tracked_core=${attributionTrackedCore} attribution_tracked_all=${attributionTrackedAll}/${urls.length} domestic_core=${domesticCore} international_core=${internationalCore} stale_indexable=${staleIndexable}`);
if (errors.length) {
  console.error(`Errors (${errors.length}):`);
  errors.slice(0, 200).forEach((error) => console.error(`  ERROR ${error}`));
  if (errors.length > 200) console.error(`  ... ${errors.length - 200} more`);
  process.exitCode = 1;
} else {
  console.log('PASS: every indexable page is stale-release-free, semver-free, and acquisition-tracked; all growth-critical pages have matched download + attribution page keys.');
}
