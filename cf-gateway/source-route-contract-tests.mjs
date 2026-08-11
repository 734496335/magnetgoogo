import fs from 'node:fs';

const source = fs.readFileSync(new URL('./src/index.js', import.meta.url), 'utf8');

const checks = [
  ['handler accepts explicit source file', /async function handleSources\(request, env, sourceFile = '\/sources\.enc\.json'\)/],
  ['full route passes full pack', /case '\/sources\.enc\.json':[\s\S]{0,120}handleSources\(request, env, '\/sources\.enc\.json'\)/],
  ['green route passes green pack', /case '\/sources-green\.enc\.json':[\s\S]{0,120}handleSources\(request, env, '\/sources-green\.enc\.json'\)/],
  ['handler fetches selected pack', /fetchUpstream\(env, sourceFile,/],
];

for (const [label, pattern] of checks) {
  if (!pattern.test(source)) {
    console.error(`FAIL: ${label}`);
    process.exit(1);
  }
}

const hardcodedAssignments = source.match(/const sourceFile = '\/sources\.enc\.json'/g) || [];
if (hardcodedAssignments.length > 0) {
  console.error('FAIL: handler still hardcodes the full pack');
  process.exit(1);
}

console.log(JSON.stringify({status: 'PASS', routes: ['/sources.enc.json', '/sources-green.enc.json']}));
