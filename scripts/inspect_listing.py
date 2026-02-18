import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bs4 import BeautifulSoup
from scraper.browser import BrowserSession

url = "https://www.inmuebles24.com/inmuebles-en-venta-en-nuevo-leon-ordenado-por-fechaonline-descendente-pagina-3.html"
with BrowserSession(headless=False) as s:
    html = s.fetch(url)
Path("output/debug_listing.html").write_text(html, encoding="utf-8")
soup = BeautifulSoup(html, "lxml")
for sel in ["#postingsList", "#list-postings", "[id*='posting']", "[class*='listPostings']", "[class*='ListPostings']"]:
    el = soup.select_one(sel)
    if el:
        links = el.select("a[href*='/propiedades/clasificado/']")
        print(sel, "links", len(links))
