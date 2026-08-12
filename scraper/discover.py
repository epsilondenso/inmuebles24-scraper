"""Phase 1: discover property URLs from search result pages."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from scraper.browser import BrowserSession, CloudflareBlockedError
from scraper.parsers import build_listing_page_url, extract_listing_urls
from scraper.storage import Storage

logger = logging.getLogger(__name__)


def discover_urls(
    config: dict[str, Any],
    storage: Storage,
    listing_types: list[str] | None = None,
) -> int:
    """Crawl search pages and append unique property URLs. Returns count of new URLs."""
    listing_types = ["sale"]#listing_types or ["sale", "rent"]
    checkpoint = storage.load_checkpoint()
    pages_done = checkpoint.get("listing_pages_done", {})
    new_count = 0
    pages_per_session = config["scraping"].get("listing_pages_per_session", 4)
    max_pages = config["scraping"].get("max_listing_pages")

    for listing_type in listing_types:
        search_cfg = config["search_urls"][listing_type]
        base = search_cfg["base"]
        pattern = search_cfg["page_pattern"]
        page = pages_done.get(listing_type, 0) + 1

        while True:
            if max_pages and page > max_pages:
                break

            url = build_listing_page_url(base, page, pattern)
            logger.info("[%s] Listing page %s: %s", listing_type, page, url)

            try:
                urls = _fetch_with_session_rotation(url, pages_per_session, page)
            except CloudflareBlockedError:
                logger.warning("Cloudflare block on page %s — saving checkpoint", page)
                pages_done[listing_type] = max(page - 1, 0)
                storage.save_checkpoint({"listing_pages_done": pages_done})
                return new_count

            if not urls:
                logger.info("[%s] No listings on page %s — done", listing_type, page)
                pages_done[listing_type] = page
                break

            for prop_url in urls:
                lid_match = re.search(r"-(\d+)\.html", prop_url)
                listing_id = lid_match.group(1) if lid_match else None
                if storage.append_url(prop_url, listing_type, url, listing_id=listing_id):
                    new_count += 1

            pages_done[listing_type] = page
            storage.save_checkpoint({"listing_pages_done": pages_done, "phase": "discover"})
            page += 1

    return new_count


# Module-level session cache for page-batch rotation
_session: BrowserSession | None = None
_session_page_count = 0


def _fetch_with_session_rotation(url: str, pages_per_session: int, page_num: int) -> list[str]:
    global _session, _session_page_count

    if _session is None or _session_page_count >= pages_per_session:
        if _session:
            _session.close()
            time.sleep(2)
        _session = BrowserSession()
        _session.start()
        _session_page_count = 0
        logger.debug("Started new browser session at page %s", page_num)

    _session.random_delay()
    html = _session.fetch(url, wait_selector="/propiedades/")
    _session_page_count += 1
    return extract_listing_urls(html)


def close_discovery_session() -> None:
    global _session, _session_page_count
    if _session:
        _session.close()
        _session = None
        _session_page_count = 0
