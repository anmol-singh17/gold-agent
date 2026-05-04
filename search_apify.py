import requests, re
url = 'https://html.duckduckgo.com/html/?q=' + requests.utils.quote('site:apify.com/store/actors craigslist scraper')
html = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}).text
links = re.findall(r'apify\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)', html)
print(set([l for l in links if 'craigslist' in l.lower()]))
