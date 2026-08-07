const ALLOWED_PATHS = new Set([
  '/sources.enc.json',
  '/sources-green.enc.json',
]);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!ALLOWED_PATHS.has(url.pathname)) {
      return new Response('Not found', { status: 404 });
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method not allowed', {
        status: 405,
        headers: { Allow: 'GET, HEAD' },
      });
    }

    const upstreamUrl = `${env.SOURCE_AUTHORITY}${url.pathname}`;
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: {
        Accept: 'application/json',
        'Cache-Control': 'no-cache',
      },
      cf: { cacheTtl: 0 },
    });

    if (!upstream.ok) {
      return new Response('Source authority unavailable', {
        status: 502,
        headers: {
          'Cache-Control': 'no-store',
          'X-Source-Authority': 'github-raw',
        },
      });
    }

    const headers = new Headers();
    headers.set('Content-Type', upstream.headers.get('Content-Type') || 'application/json; charset=utf-8');
    headers.set('Cache-Control', 'no-store, no-cache, must-revalidate');
    headers.set('X-Source-Authority', 'github-raw');
    const etag = upstream.headers.get('ETag');
    if (etag) headers.set('ETag', etag);
    const lastModified = upstream.headers.get('Last-Modified');
    if (lastModified) headers.set('Last-Modified', lastModified);

    return new Response(request.method === 'HEAD' ? null : upstream.body, {
      status: 200,
      headers,
    });
  },
};
