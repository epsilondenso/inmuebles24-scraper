"""Phase 2: extract property details from collected URLs."""

from __future__ import annotations

import logging
from typing import Any

from scraper.browser import BrowserSession, CloudflareBlockedError
from scraper.parsers import extract_property_details
from scraper.storage import Storage

logger = logging.getLogger(__name__)


def extract_details(
    config: dict[str, Any],
    storage: Storage,
    limit: int | None = None,
    force: bool = False,
) -> int:
    """Visit property URLs and export details. Returns number of records scraped."""
    url_meta = storage.load_url_meta()
    scraped_urls = set() if force else storage.load_scraped_urls()
    scraped_ids = set() if force else storage.load_scraped_ids()

    pending: list[tuple[str, dict]] = []
    for url, meta in url_meta.items():
        lid = str(meta.get("listing_id") or "")
        if url in scraped_urls or (lid and lid in scraped_ids):
            continue
        pending.append((url, meta))

    max_properties = limit or config["scraping"].get("max_properties")
    if max_properties:
        pending = pending[:max_properties]

    if not pending:
        logger.info("No pending property URLs to scrape")
        return 0

    checkpoint = storage.load_checkpoint()
    start_idx = checkpoint.get("details_index", 0)
    pending = pending[start_idx:]

    details_per_session = config["scraping"].get("details_per_session", 25)
    batch: list[dict] = []
    scraped_count = 0

    session: BrowserSession | None = None
    session_count = 0

    try:
        for i, (url, meta) in enumerate(pending, start=start_idx):
            logger.info("Detail %s/%s: %s", i + 1, start_idx + len(pending), url)

            if session is None or session_count >= details_per_session:
                if session:
                    session.close()
                session = BrowserSession()
                session.start()
                session_count = 0

            try:
                session.random_delay()
                html = session.fetch(url)
                record = extract_property_details(html, url)
                session_count += 1
            except CloudflareBlockedError:
                logger.warning("Cloudflare block — saving checkpoint at index %s", i)
                if batch:
                    storage.append_details(batch)
                    scraped_count += len(batch)
                storage.save_checkpoint({"details_index": i, "phase": "extract"})
                return scraped_count

            record["listing_type"] = meta.get("listing_type") or _infer_listing_type(record, url)
            record["source_page"] = meta.get("source_page")
            _normalize_contact_fields(record)

            batch.append(record)
            scraped_count += 1

            if len(batch) >= 10:
                storage.append_details(batch)
                batch = []
                storage.save_checkpoint({"details_index": i + 1, "phase": "extract"})
    finally:
        if session:
            session.close()

    if batch:
        storage.append_details(batch)

    storage.save_checkpoint({"details_index": start_idx + len(pending), "phase": "extract_done"})
    return scraped_count


def _normalize_contact_fields(record: dict) -> None:
    phone = str(record.get("phone") or "").strip()
    if phone.endswith("8") and len(phone) < 12 and record.get("whatsapp"):
        record["phone_partial"] = phone
        record["phone"] = record.get("whatsapp")


def _infer_listing_type(record: dict, url: str) -> str:
    op = str(record.get("operation") or "").lower()
    if "renta" in op or "rent" in op:
        return "rent"
    if "venta" in op or "sale" in op:
        return "sale"
    if "veclapin" in url or "renta" in url:
        return "rent"
    return "sale"
