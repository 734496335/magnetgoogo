import { NextRequest, NextResponse } from 'next/server';

// Share cookie store with search route via module-level global
// (In production, use Redis or similar)
const globalCookieStore = (globalThis as any).__cookieStore ??= new Map<string, { cookies: string; html?: string; url?: string; ts: number }>();

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS_HEADERS });
}

export async function POST(req: NextRequest) {
  try {
    const { origin, cookies, html, url: pageUrl } = await req.json();
    if (!origin || !cookies) {
      return NextResponse.json({ error: 'Missing origin or cookies' }, { status: 400, headers: CORS_HEADERS });
    }
    // Merge: keep existing HTML if new submission doesn't include it
    const existing = globalCookieStore.get(origin);
    const mergedHtml = html || existing?.html;
    const mergedUrl = pageUrl || existing?.url;
    globalCookieStore.set(origin, { cookies, html: mergedHtml, url: mergedUrl, ts: Date.now() });
    const htmlSize = mergedHtml ? `${Math.round(mergedHtml.length / 1024)}KB HTML` : 'no HTML';
    console.log(`[Verify] Stored for ${origin}: ${cookies.slice(0, 60)}... + ${htmlSize}`);
    return NextResponse.json({ ok: true }, { headers: CORS_HEADERS });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500, headers: CORS_HEADERS });
  }
}
