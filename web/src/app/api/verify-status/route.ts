/**
 * GET /api/verify-status?origin=xxx
 *
 * Check if verification cookies have been submitted for an origin.
 * Used by the verify-bridge page to poll for completion.
 */
import { NextRequest, NextResponse } from 'next/server';

const globalCookieStore = (globalThis as any).__cookieStore ??= new Map<string, { cookies: string; ts: number }>();

export async function GET(req: NextRequest) {
  const origin = req.nextUrl.searchParams.get('origin') || '';
  if (!origin) {
    return NextResponse.json({ has_cookies: false }, { status: 400 });
  }

  const entry = globalCookieStore.get(origin);
  const hasCookies = !!(entry && entry.cookies);

  const includeHtml = req.nextUrl.searchParams.get('html') === '1';
  return NextResponse.json({
    has_cookies: hasCookies,
    cookie_count: entry ? entry.cookies.split(';').length : 0,
    has_cf_clearance: entry ? entry.cookies.includes('cf_clearance') : false,
    preview: entry ? entry.cookies.slice(0, 200) : '',
    html_size: entry?.html ? entry.html.length : 0,
    ...(includeHtml && entry?.html ? { html: entry.html } : {}),
  });
}
