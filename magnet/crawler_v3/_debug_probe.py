"""Quick CloakBrowser probe — visit a URL, dump title + magnet count + first 2KB of HTML.

Usage: python -m magnet.crawler_v3._debug_probe <url>
"""
from __future__ import annotations

import re
import sys
import time

from cloakbrowser import launch

MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:[A-Za-z0-9]{32,}", re.I)


def main(url: str, query: str | None = None):
    print(f"[probe] launching CloakBrowser → {url}")
    t0 = time.time()
    browser = launch(headless=True, humanize=True)
    try:
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Poll content for up to 30s, sampling every 2s
        for i in range(15):
            html = page.content() or ""
            magnets = MAGNET_RE.findall(html)
            title = page.title()
            elapsed = time.time() - t0
            print(f"[probe t={elapsed:.1f}s] title={title!r} html_len={len(html)} magnets={len(magnets)}")
            if magnets:
                print(f"[probe] sample magnet: {magnets[0][:96]}")
                break
            time.sleep(2)
        # Final dump
        head = (html or "")[:2000].replace("\n", " ")
        print(f"\n[probe] HTML head:\n{head}\n")
        # If a query was provided, try filling search box
        if query:
            print(f"\n[probe] trying to fill search input with {query!r}")
            try:
                # generic: any input with name=q/keyword/word/wd/search
                for sel in ["input[name=q]", "input[name=keyword]", "input[name=word]", "input[name=wd]", "input[name=search]", "input[type=search]"]:
                    el = page.query_selector(sel)
                    if el:
                        print(f"  found {sel}, filling...")
                        el.fill(query)
                        page.keyboard.press("Enter")
                        time.sleep(8)
                        html = page.content() or ""
                        magnets = MAGNET_RE.findall(html)
                        print(f"  after submit: html_len={len(html)} magnets={len(magnets)} title={page.title()!r}")
                        if magnets:
                            print(f"  sample: {magnets[0][:96]}")
                        break
                else:
                    print("  no recognizable search input found")
            except Exception as e:
                print(f"  fill error: {e}")
    finally:
        browser.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("usage: python -m magnet.crawler_v3._debug_probe <url> [query]")
        raise SystemExit(2)
    main(args[0], args[1] if len(args) > 1 else None)
