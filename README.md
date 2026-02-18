# Inmuebles24 Real Estate Scraper (Nuevo León, Mexico)

Fully automated Python pipeline that collects property listings from [Inmuebles24.com](https://www.inmuebles24.com) for **Nuevo León** — both **sale** and **rent** — and exports structured data to Excel/CSV.

Built as a production-style alternative to a manual Octoparse workflow: **no manual browsing, no copy-paste, no clicking through pages by hand.** You run one command; the scraper handles pagination, detail pages, Cloudflare, checkpoints, and deduplication.

---

## What it does

| Phase | What happens automatically | Output |
|-------|---------------------------|--------|
| **1. URL discovery** | Walks search result pages (`pagina-1`, `pagina-2`, …) for sale & rent | `property_urls.jsonl` |
| **2. Detail extraction** | Visits each listing URL and parses structured fields | `properties.xlsx` + `properties.csv` |

You never need to open the website yourself, scroll listings manually, or export data by hand.

---

## Key features

- **End-to-end automation** — discover hundreds of URLs, then scrape thousands of detail pages unattended
- **Cloudflare-aware** — uses [DrissionPage](https://github.com/g1879/DrissionPage) with real Chrome (not brittle HTTP-only requests)
- **Rich field extraction** — parses embedded `avisoInfo` JavaScript on detail pages (price, coords, WhatsApp, advertiser, m², images, etc.)
- **Resume & checkpoint** — interrupted runs continue from the last page/index
- **Deduplication** — by property URL and `listing_id`
- **Configurable** — search URLs, page limits, session rotation via `config.yaml`
- **No secrets in code** — proxies and tuning via `.env` only (never committed)

---

## Architecture

```mermaid
flowchart LR
    A[config.yaml] --> B[main.py CLI]
    B --> C[Phase 1: discover]
    B --> D[Phase 2: extract]
    C --> E[DrissionPage / Chrome]
    D --> E
    E --> F[Inmuebles24.com]
    C --> G[property_urls.jsonl]
    D --> H[parsers.py]
    H --> I[properties.csv / .xlsx]
    B --> J[checkpoint.json]
```

---

## Tech stack

- **Python 3.10+**
- **DrissionPage** — browser automation that passes Cloudflare on Inmuebles24
- **BeautifulSoup + regex** — HTML/JSON-LD/`avisoInfo` parsing
- **pandas / openpyxl** — export
- **PyYAML / python-dotenv** — config

---

## Extracted fields (30+)

`url`, `listing_id`, `listing_code`, `listing_type`, `title`, `description`, `price`, `currency`, `operation`, `property_type`, `location`, `neighborhood`, `city`, `state`, `latitude`, `longitude`, `bedrooms`, `bathrooms`, `built_m2`, `land_m2`, `parking`, `maintenance_expenses`, `whatsapp`, `phone`, `advertiser_name`, `advertiser_id`, `advertiser_url`, `published_date`, `image_urls`, `scraped_at`

See [`docs/sample_output_columns.json`](docs/sample_output_columns.json) for an example row shape (synthetic data only).

---

## Quick start

```bash
git clone https://github.com/Haseeb536/inmuebles24-scraper.git
cd inmuebles24-scraper
pip install -r requirements.txt
copy .env.example .env   # Windows — use cp on macOS/Linux
python main.py proof-test
```

**Requirements:** Google Chrome installed locally.

---

## Commands

```bash
python main.py discover          # Phase 1 — collect listing URLs
python main.py extract           # Phase 2 — scrape property details
python main.py run               # Both phases
python main.py resume            # Continue after interruption
python main.py status            # Checkpoint progress
python main.py proof-test        # Small validation run (7 pages × 2 types, 25 details)

# Re-scrape with improved parser (replaces export)
python main.py extract --force --output-dir output/proof_test
```

---

## Configuration

**`config.yaml`** — search URLs, pagination, session rotation, output paths.

**`.env`** (local only, gitignored):

```env
HEADLESS=false
REQUEST_DELAY_MIN=2
REQUEST_DELAY_MAX=5
CF_MANUAL_WAIT_SEC=120
# PROXY_SERVER=http://user:pass@host:port
```

---

## How automation works (no manual steps)

1. **Listing pages** — the scraper opens each search URL, waits for Cloudflare if needed, and reads listing URLs from JSON-LD `mainEntity` (no manual scrolling).
2. **Detail pages** — each property URL is opened in sequence with random delays and periodic browser restarts to reduce blocks.
3. **Parsing** — fields are read from the page's embedded `avisoInfo` object (primary source), not from copy-pasted visible text.
4. **Persistence** — URLs and details append to disk; duplicates are skipped; checkpoints allow multi-hour runs.

---

## Project structure

```
├── main.py              # CLI entry point
├── config.yaml          # Search URLs & scraping settings
├── requirements.txt
├── .env.example         # Template (safe to commit)
├── scraper/
│   ├── browser.py       # DrissionPage session + Cloudflare handling
│   ├── discover.py      # Phase 1 — URL collection
│   ├── extract.py       # Phase 2 — detail scraping
│   ├── parsers.py       # Field extraction from page source
│   └── storage.py       # Checkpoint, dedup, export
└── docs/
    └── sample_output_columns.json
```

---

## Security & privacy

This repository intentionally **does not** include:

- `.env` files or proxy credentials
- Browser cookies / Chrome profiles
- Scraped listing exports (`output/`, `.csv`, `.xlsx`)
- Real phone numbers or client data

All sensitive/runtime artifacts are listed in [`.gitignore`](.gitignore).

---

## Disclaimer

This tool is for educational and portfolio purposes. Respect [Inmuebles24](https://www.inmuebles24.com) terms of service, robots policies, and applicable data laws. Use reasonable request rates; do not overload the site.

---

## License

[MIT](LICENSE)
