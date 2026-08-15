import http from 'node:http';

const port = Number(process.env.PORT || 8787);
const batches = new Map();

function json(res, value, status = 200) {
  const body = JSON.stringify(value);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Access-Control-Allow-Origin': '*',
  });
  res.end(body);
}

function readBody(req, maxBytes = 32768) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on('data', (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        reject(new Error('payload_too_large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://127.0.0.1:${port}`);
  if (req.method === 'POST' && url.pathname === '/reset') {
    batches.clear();
    return json(res, { ok: true });
  }
  if (req.method === 'GET' && url.pathname === '/batches') {
    const values = [...batches.values()];
    return json(res, {
      count: values.length,
      batches: values,
      total_events: values.reduce((sum, batch) => sum + (batch.events || []).length, 0),
    });
  }
  if (req.method === 'POST' && url.pathname === '/api/events') {
    try {
      const body = await readBody(req);
      const data = JSON.parse(body);
      if (!data.batch_id || !data.device_id || !data.install_id || !Array.isArray(data.events) || data.events.length === 0) {
        return json(res, { error: 'missing_fields' }, 400);
      }
      const ids = new Set();
      const events = [];
      for (const event of data.events) {
        if (!event?.id || !event?.e || !Number.isFinite(event?.ts)) continue;
        if (ids.has(event.id)) continue;
        ids.add(event.id);
        events.push(event);
      }
      const stored = { ...data, events, receivedAt: new Date().toISOString(), bytes: Buffer.byteLength(body) };
      batches.set(data.batch_id, stored);
      console.log('[Receiver]', JSON.stringify({
        batch_id: data.batch_id,
        device_id: String(data.device_id).slice(-12),
        install_id: String(data.install_id).slice(-12),
        build_type: data.build_type,
        events: events.map((event) => event.e),
        bytes: stored.bytes,
      }));
      return json(res, { ok: true, batch_id: data.batch_id, count: events.length });
    } catch (error) {
      return json(res, { error: error instanceof Error ? error.message : String(error) }, 400);
    }
  }
  return json(res, { ok: true, service: 'analytics-v2-local-receiver', batches: batches.size });
});

server.listen(port, '127.0.0.1', () => {
  console.log(`[Receiver] http://127.0.0.1:${port}`);
});
