"""
Smart List Detector — 通用列表行结构归纳（无 LLM，无样本，纯启发）。

设计原则（实证驱动，2026-05-21 经多个真实站点 bake-off 验证胜出）：
  1. URL path-shape 归纳：将 /!bfUI、/torrent/123、/view/abc.html 等映射为结构骨架
  2. 同 (tag, path-shape) 的兄弟节点归为一组 → 候选"列表行"
  3. 过滤掉所有行 anchor href 相同的组（= 重复 CTA/banner）
  4. 中位行文本长度 < 30 chars 的组淘汰（= 侧边栏/归档/导航）
  5. 评分 = n^0.7 × median_text_len（轻微惩罚极大 n 避免选侧边栏 widget）
  6. 行内选 title：长文本优先 + CTA 关键词惩罚（donate/download/login/...）

实证表现：
  0cili.nl: v1 完全失败 → smart detector 提取 74/74、5/5（完美）
  比 AutoScraper / Trafilatura / regex_only 都强（其它三者在 0cili.nl 都返回 0）

接口：
  detect_list_rows(html: str) → List[dict{title, detail_url, row_text_len}]

设计选择：
  - 返回 detail_url，不返回 magnet 本身。Magnet 通常需要点详情页才能拿到。
  - 调用方负责对 detail_url 做二次抓取 + 提取 magnet。
"""
import re
from bs4 import BeautifulSoup
from collections import defaultdict
from urllib.parse import urlparse

_CTA_WORDS = ('donate', 'download', 'subscribe', 'share', 'reply',
              'comment', 'login', 'register', 'home', 'next', 'prev',
              'more', 'view', 'click', 'open', 'free')

_MIN_ROWS = 3            # Below this, we don't trust the pattern
_MIN_MEDIAN_TEXT = 30    # Below this, likely sidebar/archive/nav widget


def _path_shape(href):
    """Normalize URL path into structural signature.
    /search/q?id=42 → /search/q
    /!bfUI → /!N
    /torrent/12345 → /torrent/N
    """
    if not href or href.startswith('#'):
        return None
    if href.startswith('http'):
        href = urlparse(href).path
    if not href.startswith('/'):
        return None
    parts = []
    for seg in href.split('?')[0].split('/'):
        if not seg:
            continue
        if seg.startswith('!'):
            parts.append('!N')
        elif re.fullmatch(r'\d+', seg):
            parts.append('N')
        elif re.fullmatch(r'[0-9a-fA-F]{32,40}', seg):
            parts.append('HASH')
        elif re.fullmatch(r'[a-zA-Z0-9_-]+\.html', seg):
            parts.append('N.html')
        elif re.fullmatch(r'[a-zA-Z0-9_-]{1,30}', seg):
            parts.append('N' if len(seg) <= 10 else seg)
        else:
            parts.append(seg[:20])
    return '/' + '/'.join(parts)


def _row_signature(row):
    """A row's signature = sorted unique anchor path-shapes."""
    sigs = []
    for a in row.find_all('a', href=True):
        sh = _path_shape(a['href'])
        if sh:
            sigs.append(sh)
    return tuple(sorted(set(sigs))) if sigs else None


def detect_list_rows(html, min_rows=_MIN_ROWS, min_median_text=_MIN_MEDIAN_TEXT):
    """Return list of {title, detail_url, row_text_len} for the most likely list rows.
    
    Args:
        html: raw HTML string
        min_rows: minimum number of repeated rows to consider a list (default 3)
        min_median_text: minimum median row text length (default 30)
    
    Returns:
        List of dicts; empty list if no confident detection.
    """
    soup = BeautifulSoup(html, 'lxml')

    # Collect candidate rows grouped by (tag, anchor-path-shapes)
    by_sig = defaultdict(list)
    for tag in ('tr', 'li', 'article', 'div'):
        for row in soup.find_all(tag):
            sig = _row_signature(row)
            if not sig:
                continue
            if not row.find_all('a', href=True):
                continue
            if not row.get_text(strip=True):
                continue
            by_sig[(tag, sig)].append(row)

    if not by_sig:
        return []

    # Pre-filter: drop groups where every row has identical anchor hrefs
    def varying_links(rows):
        hrefs_per_row = set()
        for r in rows:
            hs = tuple(sorted(a['href'] for a in r.find_all('a', href=True)))
            hrefs_per_row.add(hs)
        return len(hrefs_per_row) >= max(2, len(rows) // 3)

    by_sig = {k: rows for k, rows in by_sig.items() if varying_links(rows)}
    if not by_sig:
        return []

    # Score: n^0.7 × median text length. Threshold: median >= min_median_text.
    def score(rows):
        n = len(rows)
        if n < min_rows:
            return 0
        texts = sorted(len(r.get_text(strip=True)) for r in rows)
        median = texts[len(texts) // 2]
        if median < min_median_text:
            return 0
        return int(n ** 0.7 * median)

    scored = sorted(((score(rows), key, rows) for key, rows in by_sig.items()), reverse=True)
    if not scored or scored[0][0] == 0:
        return []
    _, _best_key, best_rows = scored[0]

    # Extract title + detail_url per row: prefer long anchor text, penalize CTAs
    results = []
    for row in best_rows:
        candidates = []
        for a in row.find_all('a', href=True):
            href = a['href']
            txt = a.get_text(strip=True)
            if href.startswith('magnet:') or href.startswith('#') or href == '/':
                continue
            if not txt or len(txt) < 3:
                continue
            txt_low = txt.lower()
            penalty = 0
            for cta in _CTA_WORDS:
                if cta == txt_low or (len(txt) < 20 and cta in txt_low):
                    penalty = 100
                    break
            candidates.append((len(txt) - penalty, txt, href))
        if not candidates:
            continue
        candidates.sort(reverse=True)
        _, title, detail_url = candidates[0]
        results.append({
            'title': title,
            'detail_url': detail_url,
            'row_text_len': len(row.get_text(strip=True)),
        })

    # Deduplicate by detail_url; if too many duplicates, treat as misdetection
    seen = set()
    unique = []
    for r in results:
        if r['detail_url'] in seen:
            continue
        seen.add(r['detail_url'])
        unique.append(r)
    if len(unique) < max(3, len(results) // 3):
        return []
    return unique
