import requests
import os

sites = [
    ('btso.cc', 'https://btso.cc/search?q=Ubuntu'),
    ('btdb.to', 'https://btdb.to/search/Ubuntu'),
    ('extratorrent.ag', 'https://extratorrent.ag/search?q=Batman')
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

os.makedirs('brain/0b14d3b1-195f-40f0-ba2c-b5d333094aa7/scratch/html_samples', exist_ok=True)

for name, url in sites:
    print(f"Sampling {name}...")
    try:
        resp = requests.get(url, timeout=30, headers=headers)
        with open(f"brain/0b14d3b1-195f-40f0-ba2c-b5d333094aa7/scratch/html_samples/{name}.html", 'w', encoding='utf-8') as f:
            f.write(resp.text)
        print(f"  Saved {len(resp.text)} bytes")
    except Exception as e:
        print(f"  Failed: {e}")
