"""HTML and embedded JSON parsers for Inmuebles24."""

from __future__ import annotations

import base64
import html as html_lib
import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

BASE_URL = "https://www.inmuebles24.com"
PROPERTY_PATH_RE = re.compile(r"/propiedades/clasificado/[^\"'\s?#]+", re.I)


def normalize_url(href: str) -> Optional[str]:
    return _normalize_inmuebles_url(href, required_fragment="/propiedades/")


def normalize_site_url(href: str) -> Optional[str]:
    return _normalize_inmuebles_url(href)


def _normalize_inmuebles_url(href: str, required_fragment: Optional[str] = None) -> Optional[str]:
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        href = urljoin(BASE_URL, href)
    parsed = urlparse(href)
    if "inmuebles24.com" not in parsed.netloc:
        return None
    if required_fragment and required_fragment not in parsed.path:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def extract_listing_urls(html: str) -> list[str]:
    """Collect property URLs from a Nuevo León search results page."""
    urls: set[str] = set()

    # Best source: JSON-LD mainEntity on listing pages
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        entities = data.get("mainEntity") or []
        if isinstance(entities, dict):
            entities = [entities]
        for item in entities:
            if isinstance(item, dict) and item.get("url"):
                url = normalize_url(str(item["url"]))
                if url and "/clasificado/" in url:
                    urls.add(url)
        if urls:
            return sorted(urls)

    # Fallback: posting card links only (avoids sidebar / other cities)
    for a in soup.select("[class*='postingCard'] a[href*='/propiedades/clasificado/']"):
        url = normalize_url(a.get("href", ""))
        if url:
            urls.add(url)
    if urls:
        return sorted(urls)

    for match in PROPERTY_PATH_RE.findall(html):
        url = normalize_url(match)
        if url:
            urls.add(url)
    return sorted(urls)


def _decode_b64_coord(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(base64.b64decode(value).decode("utf-8"))
    except Exception:
        return None


def _extract_braced_value(text: str, start: int) -> tuple[str, int]:
    """Return substring for {...} or [...] starting at start index."""
    opener = text[start]
    if opener not in "{[":
        raise ValueError("not a brace")
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    quote = ""
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ('"', "'"):
            in_string = True
            quote = ch
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
    raise ValueError("unbalanced braces")


def _extract_js_const_object(html: str, name: str) -> Optional[str]:
    m = re.search(rf"const\s+{name}\s*=\s*(\{{)", html)
    if not m:
        return None
    try:
        block, _ = _extract_braced_value(html, m.start(1))
        return block
    except ValueError:
        return None


def _field_string(block: str, key: str) -> Optional[str]:
    for pat in (
        rf"'{key}'\s*:\s*\"((?:\\.|[^\"])*)\"",
        rf"'{key}'\s*:\s*'((?:\\.|[^'])*)'",
    ):
        m = re.search(pat, block)
        if m:
            return m.group(1)
    return None


def _extract_nested_block(block: str, key: str) -> Optional[str]:
    m = re.search(rf"'{key}'\s*:\s*(\{{)", block)
    if not m:
        return None
    try:
        sub, _ = _extract_braced_value(block, m.start(1))
        return sub
    except ValueError:
        return None


def _extract_publisher(block: str) -> dict[str, Any]:
    sub = _extract_nested_block(block, "publisher")
    if not sub:
        return {}
    record: dict[str, Any] = {}
    for src, dst in (
        ("publisherId", "advertiser_id"),
        ("id", "advertiser_id"),
        ("name", "advertiser_name"),
        ("url", "advertiser_url"),
        ("partialPhone", "phone"),
    ):
        val = _field_string(sub, src)
        if val and not record.get(dst):
            record[dst] = normalize_site_url(val) if dst == "advertiser_url" else val
    return record


def _field_json(block: str, key: str) -> Any:
    m = re.search(rf"'{key}'\s*:\s*(\{{|\[)", block)
    if not m:
        return None
    try:
        raw, _ = _extract_braced_value(block, m.start(1))
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None


def _walk_location_chain(location: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    neighborhood = city = state = None
    node = location
    depth = 0
    while isinstance(node, dict) and depth < 6:
        label = (node.get("label") or "").upper()
        name = node.get("name")
        if label == "ZONA" and not neighborhood:
            neighborhood = name
        elif label == "CIUDAD" and not city:
            city = name
        elif label in ("PROVINCIA", "ESTADO") and not state:
            state = name
        node = node.get("parent")
        depth += 1
    return neighborhood, city, state


def _feature_value(main_features: dict, *feature_ids: str) -> Any:
    for fid in feature_ids:
        item = main_features.get(fid)
        if isinstance(item, dict) and item.get("value") not in (None, ""):
            return item.get("value")
    return None


def _picture_urls(pictures: Any) -> str:
    urls: list[str] = []
    if not isinstance(pictures, list):
        return ""
    for pic in pictures:
        if not isinstance(pic, dict):
            continue
        for key in ("url1200x1200", "url730x532", "resizeUrl1200x1200", "url360x266"):
            val = pic.get(key)
            if val and "/avisos/" in str(val):
                urls.append(str(val))
                break
    return "|".join(dict.fromkeys(urls))


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def _extract_from_aviso_info(html: str) -> dict[str, Any]:
    block = _extract_js_const_object(html, "avisoInfo")
    if not block:
        return {}

    record: dict[str, Any] = {}
    listing_id = _field_string(block, "idAviso")
    if listing_id:
        record["listing_id"] = listing_id

    for key, out_key in (
        ("postingCode", "listing_code"),
        ("postingTitle", "title"),
        ("description", "description"),
        ("price", "price_text"),
        ("whatsApp", "whatsapp"),
        ("partialPhone", "phone"),
        ("publicationDateFormatted", "published_date"),
        ("expenses", "maintenance_expenses"),
    ):
        val = _field_string(block, key)
        if val:
            record[out_key] = _strip_html(val) if key == "description" else val

    prices_data = _field_json(block, "pricesData")
    if isinstance(prices_data, list) and prices_data:
        op = prices_data[0]
        if isinstance(op, dict):
            record["operation"] = _deep_get(op, "operationType", "name")
            prices = op.get("prices") or []
            if prices and isinstance(prices[0], dict):
                p0 = prices[0]
                record["price"] = p0.get("amount")
                record["currency"] = p0.get("isoCode") or p0.get("currency")
                if not record.get("price_text"):
                    record["price_text"] = f"{p0.get('currency', '')} {p0.get('formattedAmount', '')}".strip()

    location = _field_json(block, "location")
    if isinstance(location, dict):
        neighborhood, city, state = _walk_location_chain(location)
        record["neighborhood"] = neighborhood
        record["city"] = city
        record["state"] = state
        record["location"] = _field_string(block, "address") or location.get("name")
        if isinstance(record.get("location"), str):
            pass
        else:
            addr = _field_json(block, "address")
            if isinstance(addr, dict):
                record["location"] = addr.get("name")

    address = _field_json(block, "address")
    if isinstance(address, dict) and address.get("name"):
        record["location"] = address["name"]

    main_features = _field_json(block, "mainFeatures")
    if isinstance(main_features, dict):
        record["bedrooms"] = _feature_value(main_features, "CFT2")
        record["bathrooms"] = _feature_value(main_features, "CFT3")
        record["built_m2"] = _feature_value(main_features, "CFT101", "CFT100")
        record["land_m2"] = _feature_value(main_features, "CFT100")
        record["parking"] = _feature_value(main_features, "CFT7")
        record["antiquity_years"] = _feature_value(main_features, "CFT5")

    real_estate = _field_json(block, "realEstateType")
    if isinstance(real_estate, dict):
        record["property_type"] = real_estate.get("name")

    publisher = _extract_publisher(block)
    if publisher:
        for k, v in publisher.items():
            if v and (k not in record or not record[k]):
                record[k] = v

    pictures = _field_json(block, "pictures")
    img_urls = _picture_urls(pictures)
    if img_urls:
        record["image_urls"] = img_urls

    generated = _field_string(block, "generatedTitle")
    if generated and not record.get("title"):
        record["title"] = generated

    return record


def _extract_from_data_layer(html: str) -> dict[str, Any]:
    block = _extract_js_const_object(html, "dataLayerInfo")
    if not block:
        return {}
    record: dict[str, Any] = {}
    mapping = {
        "operationType": "operation",
        "propertyType": "property_type",
        "neighborhood": "neighborhood",
        "city": "city",
        "province": "state",
        "sellPrice": "price_text",
    }
    for src, dst in mapping.items():
        val = _field_string(block, src)
        if val and val.strip():
            record[dst] = val.strip()
    return record


def _extract_map_coords(html: str) -> dict[str, Any]:
    record: dict[str, Any] = {}
    lat_m = re.search(r'const\s+mapLatOf\s*=\s*"([^"]+)"', html)
    lng_m = re.search(r'const\s+mapLngOf\s*=\s*"([^"]+)"', html)
    if lat_m:
        record["latitude"] = _decode_b64_coord(lat_m.group(1))
    if lng_m:
        record["longitude"] = _decode_b64_coord(lng_m.group(1))
    antiquity_m = re.search(r"const\s+antiquity\s*=\s*'([^']*)'", html)
    if antiquity_m and antiquity_m.group(1).strip():
        record["publication_age"] = antiquity_m.group(1).strip()
    return record


def _deep_get(obj: Any, *keys: str) -> Any:
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _extract_from_html_dom(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    record: dict[str, Any] = {"url": url}

    title_el = soup.select_one("h1")
    if title_el:
        record["title"] = title_el.get_text(" ", strip=True)

    desc_el = soup.select_one("#description, [class*='description']")
    if desc_el:
        record["description"] = desc_el.get_text(" ", strip=True)

    price_el = soup.select_one(".price-value")
    if price_el:
        text = price_el.get_text(" ", strip=True)
        if text and "ocultar" not in text.lower():
            record["price_text"] = text

    loc_el = soup.select_one("[class*='location']")
    if loc_el:
        record["location"] = loc_el.get_text(" ", strip=True)

    adv_el = soup.select_one("[data-qa='linkMicrositioAnunciante'], [data-qa='linkMicrositioAnuncianteLeads']")
    if adv_el:
        record["advertiser_name"] = adv_el.get_text(" ", strip=True)
        record["advertiser_url"] = normalize_url(adv_el.get("href", ""))

    images = []
    for img in soup.select("img[src*='/avisos/']"):
        src = img.get("src") or img.get("data-src")
        if src and "/ficha/" not in src:
            images.append(src)
    if images:
        record["image_urls"] = "|".join(dict.fromkeys(images))

    return record


def extract_property_details(html: str, url: str) -> dict[str, Any]:
    """Extract all required fields from a property detail page."""
    record: dict[str, Any] = {"url": url}

    for source in (
        _extract_from_aviso_info(html),
        _extract_from_data_layer(html),
        _extract_map_coords(html),
    ):
        for k, v in source.items():
            if v not in (None, "", []):
                if k not in record or not record[k]:
                    record[k] = v

    soup = BeautifulSoup(html, "lxml")
    dom = _extract_from_html_dom(soup, url)
    for k, v in dom.items():
        if k not in record or not record[k]:
            record[k] = v

    if not record.get("listing_id"):
        m = re.search(r"-(\d+)\.html", url)
        if m:
            record["listing_id"] = m.group(1)

    if record.get("description"):
        record["description"] = _strip_html(str(record["description"]))

    return record


def build_listing_page_url(base: str, page: int, page_pattern: str) -> str:
    if page <= 1:
        return f"{base}.html"
    return page_pattern.format(base=base, page=page)
