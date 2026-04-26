import requests
import json
import sys
import os

def test_connectivity():
    sites = [
        'https://animetosho.org/search?q=One%20Piece',
        'https://btso.cc/search?q=Ubuntu'
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for url in sites:
        print(f"Testing {url}...")
        try:
            resp = requests.get(url, timeout=30, headers=headers)
            print(f"  Status: {resp.status_code}, Length: {len(resp.text)}")
            if resp.status_code == 200:
                print(f"  Sample text: {resp.text[:200]}")
        except Exception as e:
            print(f"  Failed: {e}")

if __name__ == "__main__":
    test_connectivity()
