async function test(name, rule) {
  try {
    const r = await fetch('http://localhost:3000/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rule, query: 'spider' }),
    });
    const d = await r.json();
    const n = d.results?.length || 0;
    const first = d.results?.[0];
    console.log(`${name}: ${n} results, status=${r.status}`);
    if (first) {
      console.log(`  title=${first.title?.substring(0,50)}`);
      console.log(`  size=${first.size} mag=${first.magnet?.substring(0,60)}`);
    }
    if (d.error) console.log(`  error=${d.error}`);
  } catch (e) {
    console.log(`${name} ERR: ${e.message}`);
  }
}

// CiliMo
await test('CiliMo', {
  id: 'zhihu_cilimo',
  site: { name: '磁力魔(CiliMo)', origin: 'https://cilimo.com' },
  search: {
    request_template: '/api/search?q={query}',
    handler: 'cilimo',
    parse_metadata: { selectors: { list_item: '', title: '', magnet: '' } }
  },
  quality: { score: 70, tags: ['chinese'] },
  health: { status: 'green' }
});

// CLKD
await test('CLKD', {
  id: 'zhihu_kd705',
  site: { name: '磁力口袋(kd705)', origin: 'https://kd705.site' },
  search: {
    request_template: '/api/search?q={query}',
    handler: 'clkd',
    parse_metadata: { selectors: { list_item: '', title: '', magnet: '' } }
  },
  quality: { score: 65, tags: ['chinese'] },
  health: { status: 'green' }
});

// LuLuTang (standard handler with detail-follow)
await test('LuLuTang', {
  id: 'zhihu_lulutang',
  site: { name: '噜噜糖(LuLuTang)', origin: 'https://lulutang.com' },
  capabilities: { supports_detail: true },
  search: {
    request_template: '/search/results?keyword={query}',
    parse_metadata: {
      selectors: {
        list_item: 'div.result-item',
        title: 'a.item-title',
        size: 'span.meta-info:nth-of-type(1)',
        detail_link: 'a.item-title'
      }
    },
    detail: {
      selectors: {
        magnet: "a[href^='magnet:']",
        title: 'h1'
      }
    }
  },
  quality: { score: 65, tags: ['chinese'] },
  health: { status: 'green' }
});
