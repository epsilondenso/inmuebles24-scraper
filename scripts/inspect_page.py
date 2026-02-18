import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup
from scraper.browser import BrowserSession

url = "https://www.inmuebles24.com/propiedades/clasificado/veclapin-departamento-cumbres-campanario-monterrey-venta-150326359.html"

with BrowserSession(headless=False) as s:
    html = s.fetch(url)

Path("output/debug_detail.html").write_text(html, encoding="utf-8")

soup = BeautifulSoup(html, "lxml")
for script in soup.find_all("script"):
    text = script.string or ""
    if "whatsApp" in text and len(text) > 10000:
        # try to find JSON object with posting
        for pat in (
            r"window\.__PRELOADED_STATE__\s*=\s*(\{.+?\})\s*;",
            r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;",
            r'"posting"\s*:\s*(\{.+?"postingId".+?\})\s*,',
            r"var\s+posting\s*=\s*(\{.+?\});",
        ):
            m = re.search(pat, text, re.DOTALL)
            if m:
                print("MATCH", pat[:40], "len", len(m.group(1)))
                try:
                    obj = json.loads(m.group(1))
                    print("keys", list(obj.keys())[:20])
                except Exception as e:
                    print("json err", e)
                    print(m.group(1)[:300])

# DOM extraction probes
selectors = {
    "price": ".price-value, [data-qa='PRICE']",
    "views": "[data-qa='VISITS'], [class*='views'], [class*='visit']",
    "phone": "[data-qa='PHONE'], a[href^='tel:']",
    "whatsapp": "a[href*='whatsapp'], [data-qa='WHATSAPP']",
    "advertiser": "[class*='publisher'] a, [data-qa='PUBLISHER']",
    "location": "[data-qa='LOCATION'], [class*='location']",
    "features": "[class*='main-features'] li, [data-qa='MAIN_FEATURES'] li",
    "map": "img[src*='ficha/map']",
}
for name, sel in selectors.items():
    els = soup.select(sel)
    print(name, len(els), [e.get_text(" ", strip=True)[:60] if hasattr(e, "get_text") else e.get("src", "")[:60] for e in els[:3]])

# lat/lng from map image
for img in soup.select("img[src*='ficha/map']"):
    src = img.get("src", "")
    print("map src", src)
    m = re.search(r"/(\d+)E\.png", src)
    if m:
        print("map id", m.group(1))
