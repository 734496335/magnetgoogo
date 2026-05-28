#!/usr/bin/env python3
"""Check detail pages for magnet links on promising sites."""
import requests, re, urllib3
from bs4 import BeautifulSoup
urllib3.disable_warnings()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# cilisousuo.co detail page
print("=== cilisousuo.co detail page ===")
r = requests.get("https://cilisousuo.co/magnet/7k4a", timeout=10, verify=False, headers=H)
print(f"Status: {r.status_code}, Len: {len(r.text)}")

soup = BeautifulSoup(r.text, "html.parser")
title = soup.find("title")
print(f"Title: {title.text.strip()[:80] if title else 'N/A'}")

# Find all magnet links
magnets = re.findall(r"magnet:\?xt=urn:btih:[a-fA-F0-9]+", r.text)
print(f"Magnet regex: {len(magnets)}")
for m in magnets[:3]:
    print(f"  {m[:80]}")

# Find <a> tags with magnet
for a in soup.find_all("a", href=True):
    href = a["href"]
    if "magnet" in href:
        print(f"  <a href>: {href[:80]}")

# Print key HTML structure
for line in r.text.split("\n"):
    stripped = line.strip()
    if stripped and ("magnet" in stripped.lower() or "hash" in stripped.lower() or
                     "info_hash" in stripped.lower() or "btih" in stripped.lower()):
        print(f"  HTML: {stripped[:150]}")

# Show body structure
body = soup.find("body")
if body:
    print(f"\nBody text: {body.get_text(strip=True)[:300]}")

# Check existing cilisousuo.cc vs .co difference
print("\n\n=== cilisousuo.cc search ===")
r2 = requests.get("https://cilisousuo.cc/search?q=spider", timeout=10, verify=False, headers=H)
print(f"Status: {r2.status_code}, Len: {len(r2.text)}")
soup2 = BeautifulSoup(r2.text, "html.parser")
items = soup2.select("li.item")
print(f"li.item count: {len(items)}")
if items:
    links_in_item = items[0].find_all("a", href=True)
    for a in links_in_item:
        print(f"  link: {a['href'][:60]}")

print("\n\n=== Check existing 0cili.org ===")
for domain in ["0cili.org", "0cili.com", "wuji.me"]:
    try:
        r3 = requests.get(f"https://{domain}", timeout=8, verify=False, headers=H, allow_redirects=True)
        print(f"{domain}: status={r3.status_code} len={len(r3.text)} final={r3.url[:60]}")
    except Exception as e:
        print(f"{domain}: {str(e)[:60]}")
