#!/usr/bin/env python3
"""
Inmuebles24 scraper — Nuevo León (sale + rent)

Workflow (matches Octoparse project scope):
  Phase 1  discover  — search pages → property URLs
  Phase 2  extract  — detail pages → Excel/CSV

Commands:
  python main.py discover
  python main.py extract
  python main.py run
  python main.py resume      # continue from checkpoint
  python main.py proof-test  # client feasibility test
  python main.py status
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from scraper.discover import close_discovery_session, discover_urls
from scraper.extract import extract_details
from scraper.storage import Storage

load_dotenv()


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_discover(config: dict, storage: Storage, args: argparse.Namespace) -> None:
    types = args.type.split(",") if args.type else None
    try:
        count = discover_urls(config, storage, listing_types=types)
    finally:
        close_discovery_session()
    print(f"Discovery complete. {count} new property URLs added.")
    print(f"URL list: {storage.urls_path}")


def cmd_extract(config: dict, storage: Storage, args: argparse.Namespace) -> None:
    force = getattr(args, "force", False)
    if force:
        storage.clear_details()
        storage.save_checkpoint({"details_index": 0, "phase": "extract"})

    count = extract_details(config, storage, limit=args.limit, force=force)
    print(f"Extraction complete. {count} properties scraped.")
    print(f"Excel: {storage.details_path}")
    print(f"CSV:   {storage.details_csv_path}")
    sample = storage.export_sample_csv()
    print(f"Sample: {sample}")


def cmd_run(config: dict, storage: Storage, args: argparse.Namespace) -> None:
    cmd_discover(config, storage, args)
    cmd_extract(config, storage, args)


def cmd_resume(config: dict, storage: Storage, args: argparse.Namespace) -> None:
    cp = storage.load_checkpoint()
    phase = cp.get("phase", "discover")
    print(f"Resuming from checkpoint (phase={phase})...")
    if phase in ("discover", None) and cp.get("details_index", 0) == 0:
        cmd_discover(config, storage, args)
    cmd_extract(config, storage, args)


def cmd_status(config: dict, storage: Storage, args: argparse.Namespace) -> None:
    stats = storage.stats()
    cp = storage.load_checkpoint()
    print("=== Scraper status ===")
    print(f"  URLs collected:    {stats['urls']}")
    print(f"  Details scraped:   {stats['details']}")
    print(f"  Checkpoint:        {storage.checkpoint_path}")
    if cp:
        print(f"  Phase:             {cp.get('phase')}")
        print(f"  Listing pages:     {cp.get('listing_pages_done')}")
        print(f"  Detail index:      {cp.get('details_index')}")


def cmd_proof_test(config: dict, storage: Storage, args: argparse.Namespace) -> None:
    """Proof test per client brief: pages 1-7 sale+rent, ~25 details."""
    proof_config = dict(config)
    proof_config["scraping"] = {
        **config["scraping"],
        "max_listing_pages": 7,
        "max_properties": 25,
        "listing_pages_per_session": 3,
        "details_per_session": 10,
    }
    proof_dir = Path("output") / "proof_test"
    proof_storage = Storage(str(proof_dir))

    print("=== Proof test: URL discovery (sale + rent, pages 1-7) ===")
    try:
        count = discover_urls(proof_config, proof_storage, listing_types=["sale", "rent"])
    finally:
        close_discovery_session()
    print(f"  New URLs discovered: {count}")
    print(f"  Total URLs: {len(proof_storage.load_urls())}")

    print("\n=== Proof test: detail extraction (up to 25 listings) ===")
    proof_storage.clear_details()
    scraped = extract_details(proof_config, proof_storage, limit=25, force=True)
    print(f"  Properties scraped: {scraped}")

    sample = proof_storage.export_sample_csv(proof_dir / "proof_sample.csv", limit=25)
    print(f"\nProof sample export: {sample}")
    print("\nRe-run in a new terminal session to verify consistency across runs.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inmuebles24 scraper — Nuevo León property listings (Python)"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-c", "--config", default="config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", help="Phase 1: collect property URLs")
    p_discover.add_argument("--type", help="sale, rent, or sale,rent")
    p_discover.add_argument("-o", "--output-dir", help="Output folder (default: config output.directory)")

    p_extract = sub.add_parser("extract", help="Phase 2: scrape property details")
    p_extract.add_argument("--limit", type=int, help="Max properties to scrape")
    p_extract.add_argument("--force", action="store_true", help="Re-scrape all URLs (replace export)")
    p_extract.add_argument("-o", "--output-dir", help="Output folder (default: config output.directory)")

    for name in ("run", "resume", "status", "proof-test"):
        p = sub.add_parser(name.replace("_", "-") if name == "proof_test" else name)
        if name == "proof-test":
            pass
        p.add_argument("-o", "--output-dir", help="Output folder")

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        import DrissionPage  # noqa: F401
    except ImportError:
        print("Install dependencies: pip install -r requirements.txt")
        return 1

    config = load_config(args.config)
    out = args.output_dir or config["output"]["directory"]
    storage = Storage(out)

    commands = {
        "discover": cmd_discover,
        "extract": cmd_extract,
        "run": cmd_run,
        "resume": cmd_resume,
        "status": cmd_status,
        "proof-test": cmd_proof_test,
    }
    commands[args.command](config, storage, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
