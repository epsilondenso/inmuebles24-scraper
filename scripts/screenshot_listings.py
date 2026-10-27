"""Take a screenshot of every listing URL in a CSV.

Each capture goes from the top of the page down to the
"Cód. del anunciante / Cód. Inmuebles24" block. Files are numbered
in the same order as the CSV rows (001, 002, ...).

Usage:
  python scripts/screenshot_listings.py output/ventas1.csv
  python scripts/screenshot_listings.py output/ventas1.csv --column url --out capturas_test --limit 5
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import yaml
from dotenv import load_dotenv

from scraper.browser import BrowserSession, CloudflareBlockedError

logger = logging.getLogger("screenshots")

# Texts that mark the end of the capture; it goes down to the lowest one found.
# Not every listing shows the codes, so the fraud link is the main marker.
END_MARKERS = ("Cómo evitar fraudes inmobiliarios", "Cód. Inmuebles24")
# Optional text just below the end markers ("Publicado hace 13 días").
# If it is on the page the capture extends to it; otherwise it is ignored.
OPTIONAL_MARKER = "Publicado hace"
# Max distance (px) below the end markers to accept the optional marker
OPTIONAL_MAX_GAP = 300
# Extra pixels below the marker so it is fully visible
BOTTOM_MARGIN = 30


# Seconds to wait for a visible end marker after the page loads
MARKER_WAIT = 10


def _visible(page, text: str) -> list:
    """Return the elements containing text that are actually rendered.

    The same text also appears inside <script> tags, which have no position
    or size; asking for their rect raises, so those matches are skipped.
    """
    found = []
    for ele in page.eles(f"text:{text}", timeout=0.5):
        try:
            if ele.states.has_rect and ele.rect.size[1] > 0:
                found.append(ele)
        except Exception:
            continue
    return found


def _visible_markers(page) -> list:
    """Return the first rendered element of each end marker."""
    return [eles[0] for eles in (_visible(page, t) for t in END_MARKERS) if eles]


def _optional_bottom(page, base_bottom: float) -> float | None:
    """Bottom of the optional marker if it sits just below base_bottom."""
    for ele in _visible(page, OPTIONAL_MARKER):
        try:
            top = ele.rect.location[1]
            if base_bottom <= top <= base_bottom + OPTIONAL_MAX_GAP:
                return top + ele.rect.size[1]
        except Exception:
            continue
    return None


def capture_listing(session: BrowserSession, url: str, path: Path) -> bool:
    """Open url and save the screenshot. Returns True if an end marker was found."""
    session.fetch(url)
    page = session.page

    # Markers may render a bit after load, so poll for a visible one
    deadline = time.time() + MARKER_WAIT
    markers = _visible_markers(page)
    while not markers and time.time() < deadline:
        time.sleep(1)
        markers = _visible_markers(page)

    if not markers:
        logger.warning("No end marker found — saving full page: %s", url)
        page.get_screenshot(path=str(path), full_page=True)
        return False

    # Bring the markers into view once so lazy-loaded content above them renders
    try:
        markers[-1].scroll.to_see()
        markers[0].scroll.to_see()
        time.sleep(1)
        page.scroll.to_top()
        time.sleep(0.5)
    except Exception:
        pass

    # Scrolling makes the page re-render that section and replace the marker
    # nodes, so the old references lose their rect: look them up again
    bottom = None
    for _ in range(5):
        try:
            markers = _visible_markers(page)
            if markers:
                bottom = max(m.rect.location[1] + m.rect.size[1] for m in markers)
                extra = _optional_bottom(page, bottom)
                if extra is not None:
                    bottom = extra
                else:
                    logger.info("'%s' not found below the markers — keeping the usual length", OPTIONAL_MARKER)
                break
        except Exception:
            pass
        time.sleep(1)
    if bottom is None:
        logger.warning("End marker vanished after scrolling — saving full page: %s", url)
        page.get_screenshot(path=str(path), full_page=True)
        return False

    width, page_height = page.rect.size
    bottom = min(bottom + BOTTOM_MARGIN, page_height)
    page.get_screenshot(path=str(path), left_top=(0, 0), right_bottom=(width, bottom))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Screenshot listing URLs from a CSV")
    parser.add_argument("csv", help="CSV file with a column of listing URLs")
    parser.add_argument("--column", default="url", help="Name of the URL column (default: url)")
    parser.add_argument("--out", default="capturas_test", help="Output folder, relative to the project root")
    parser.add_argument("--limit", type=int, default=None, help="Only capture the first N rows")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    per_session = config["scraping"].get("details_per_session", 25)

    df = pd.read_csv(args.csv, dtype=str)
    if args.column not in df.columns:
        sys.exit(f"Column '{args.column}' not found. Available: {list(df.columns)}")
    urls = df[args.column].fillna("").str.strip().tolist()
    if args.limit:
        urls = urls[: args.limit]

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    digits = max(3, len(str(len(urls))))

    session: BrowserSession | None = None
    session_count = 0
    ok, partial, failed = 0, 0, []

    try:
        # Numbering follows the CSV row order; empty rows keep their number
        for n, url in enumerate(urls, start=1):
            if not url:
                logger.warning("Row %s has no URL — skipped", n)
                failed.append(n)
                continue

            if session is None or session_count >= per_session:
                if session:
                    session.close()
                session = BrowserSession()
                session.start()
                session_count = 0

            path = out_dir / f"{n:0{digits}d}.png"
            logger.info("Capture %s/%s: %s", n, len(urls), url)
            try:
                session.random_delay()
                if capture_listing(session, url, path):
                    ok += 1
                else:
                    partial += 1
                session_count += 1
            except CloudflareBlockedError:
                logger.warning("Cloudflare block on row %s — restarting browser", n)
                failed.append(n)
                session.close()
                session = None
            except Exception as exc:
                logger.warning("Row %s failed: %s", n, exc)
                failed.append(n)
    finally:
        if session:
            session.close()

    print(f"Done. {ok} cropped, {partial} full page (marker not found), {len(failed)} failed.")
    if failed:
        print(f"Failed rows: {failed}")
    print(f"Screenshots: {out_dir}")


if __name__ == "__main__":
    main()
