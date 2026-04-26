/**
 * GET /api/verify-bridge?origin=xxx
 *
 * Returns a helper page that guides the user through cookie submission
 * after completing CF Turnstile verification.
 *
 * Flow:
 *   1. User sees instructions on this page
 *   2. Switches to verification tab → completes Turnstile
 *   3. Opens console (F12) → pastes the one-liner → presses Enter
 *   4. Cookies are sent to /api/verify → server resumes search
 */
import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  const origin = req.nextUrl.searchParams.get('origin') || '';
  if (!origin) {
    return new NextResponse('Missing origin parameter', { status: 400 });
  }

  const snippet = `fetch('http://localhost:3000/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:location.origin,cookies:document.cookie})}).then(r=>r.json()).then(d=>document.title=d.ok?'✓ 已提交':'✗ 失败')`;

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>MagnetGoogo — 验证助手</title>
  <style>
    * { box-sizing: border-box; margin: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 580px;
           margin: 40px auto; padding: 24px; color: #1a1c1e; line-height: 1.6; }
    h1 { font-size: 22px; margin-bottom: 8px; }
    .subtitle { font-size: 14px; color: #545f70; margin-bottom: 28px; }
    .steps { list-style: none; padding: 0; counter-reset: step; }
    .steps li { position: relative; padding: 16px 16px 16px 52px; margin-bottom: 12px;
                background: #f8f9fa; border-radius: 12px; font-size: 14px; }
    .steps li::before { counter-increment: step; content: counter(step);
                        position: absolute; left: 16px; top: 16px; width: 28px; height: 28px;
                        border-radius: 50%; background: #003ec7; color: white;
                        display: flex; align-items: center; justify-content: center;
                        font-size: 13px; font-weight: 600; }
    .steps li.active { background: #e3f2fd; border: 1px solid #90caf9; }
    .code-box { position: relative; margin: 12px 0 0; padding: 10px 12px; border-radius: 8px;
                background: #1e293b; color: #e2e8f0; font-family: 'Cascadia Code', Consolas, monospace;
                font-size: 11.5px; line-height: 1.5; word-break: break-all; max-height: 80px; overflow: auto; }
    .copy-btn { position: absolute; top: 6px; right: 6px; padding: 4px 12px;
                border-radius: 6px; border: none; background: #334155; color: #cbd5e1;
                font-size: 11px; cursor: pointer; }
    .copy-btn:hover { background: #475569; }
    .copy-btn.copied { background: #22c55e; color: white; }
    .status-bar { margin-top: 24px; padding: 14px 16px; border-radius: 10px;
                  font-size: 14px; font-weight: 500; text-align: center; }
    .waiting { background: #fff3e0; color: #e65100; }
    .success { background: #e8f5e9; color: #2e7d32; }
    .origin { font-size: 12px; color: #94a3b8; margin-top: 20px; text-align: center; }
    code { background: #e8e8ea; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
    kbd { background: #e8e8ea; padding: 2px 6px; border-radius: 4px; font-size: 12px;
          border: 1px solid #d0d0d5; font-family: inherit; }
  </style>
</head>
<body>
  <h1>🔐 验证助手</h1>
  <p class="subtitle">请按照以下步骤完成人机验证并提交 Cookie</p>

  <ol class="steps">
    <li class="active">切换到左边的标签页，完成 Cloudflare 人机验证（点击复选框）</li>
    <li>验证通过后（看到搜索结果），按 <kbd>F12</kbd> 打开开发者工具</li>
    <li>点击顶部的 <code>Console</code>（控制台）标签</li>
    <li>
      粘贴以下代码并按 <kbd>Enter</kbd>
      <div class="code-box">
        <button class="copy-btn" onclick="copyCode(this)">复制</button>
        <span id="snippet">${snippet}</span>
      </div>
    </li>
    <li>看到标签页标题变为 <code>✓ 已提交</code> 即成功，可关闭此浏览器</li>
  </ol>

  <div id="status" class="status-bar waiting">⏳ 等待 Cookie 提交中...</div>
  <p class="origin">目标: ${origin}</p>

  <script>
    function copyCode(btn) {
      const text = document.getElementById('snippet').textContent;
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = '已复制!';
        btn.className = 'copy-btn copied';
        setTimeout(() => { btn.textContent = '复制'; btn.className = 'copy-btn'; }, 2000);
      });
    }

    // Poll server to check if cookies were received
    const ORIGIN = ${JSON.stringify(origin)};
    let checking = true;
    async function pollStatus() {
      while (checking) {
        await new Promise(r => setTimeout(r, 3000));
        try {
          // Quick check: try to search with the cookies
          // If /api/verify has cookies, the status bar updates
          const resp = await fetch('/api/verify-status?origin=' + encodeURIComponent(ORIGIN));
          const data = await resp.json();
          if (data.has_cookies) {
            document.getElementById('status').className = 'status-bar success';
            document.getElementById('status').textContent = '✅ Cookie 已收到！搜索将自动重试，可关闭此浏览器';
            checking = false;
          }
        } catch {}
      }
    }
    pollStatus();
  </script>
</body>
</html>`;

  return new NextResponse(html, {
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}
