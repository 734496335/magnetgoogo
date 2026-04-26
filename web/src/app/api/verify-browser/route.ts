/**
 * POST /api/verify-browser
 *
 * Launches a visible Chromium window for user to solve interactive
 * challenges (CF Turnstile, hCaptcha, etc.).
 *
 * Equivalent of Legado's SourceVerificationHelp.startBrowser() → WebViewActivity.
 *
 * Body: { url: string }
 * Returns: { success: boolean; cookies?: string; error?: string }
 */
import { NextRequest, NextResponse } from 'next/server';
import { interactiveVerify } from '@/core/browser-engine';

export async function POST(req: NextRequest) {
  try {
    const { url } = await req.json();
    if (!url) {
      return NextResponse.json({ error: 'Missing url' }, { status: 400 });
    }

    console.log(`[VerifyBrowser] Starting interactive verification for ${url}`);
    const result = await interactiveVerify(url, 120_000);

    return NextResponse.json(result);
  } catch (error: any) {
    console.error(`[VerifyBrowser] Error: ${error.message}`);
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
