import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))
from scraper import _safe_get
from bs4 import BeautifulSoup

url = "https://www.kijiji.ca/b-gold-jewellery/toronto/c689l1700273"
resp = _safe_get(url)
if not resp:
    print("Failed to get response")
    sys.exit(1)

soup = BeautifulSoup(resp.text, 'html.parser')

print("ALL CLASSES OF SECTION/ARTICLE/DIV tags that might be cards:")
cards = soup.select('section')[:5] + soup.select('article')[:5]
for c in cards:
    print(c.name, c.get('class'), c.get('data-testid'))

print("\n--- Let's look for testid=listing-card-list-item ---")
found = soup.select('[data-testid="listing-card-list-item"]')
print(f"Found {len(found)} via testid")
if not found:
    print("Checking section classes:")
    sections = soup.find_all('section')
    for s in sections[:5]:
        print(s.get('class'))
        
    print("\nChecking article elements:")
    articles = soup.find_all('article')
    for a in articles[:5]:
        print(a.get('class'))
        print("A HREF inside:")
        a_tag = a.find('a')
        if a_tag: print(a_tag.get('href'))
