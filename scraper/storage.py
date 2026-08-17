"""Checkpoint, deduplication, and export helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import yaml
import pandas as pd

#read config.yaml:
import yaml

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

config = config["output"]

urls_file = config["urls_file"]
properties_excel = config["details_file"]
properties_csv = config["details_file_csv"]
checkpoint = config["checkpoint_file"]

# Columns aligned with Inmuebles24 project scope / Excel template
OUTPUT_COLUMNS = [
    "url",
    "price",
    "price_text",
    "currency",
    "operation",
    "property_type",
    "neighborhood",
    "city",
    "state",
    "built_m2",
    "land_m2",
    "publication_age",
    "published_date",
    "scraped_at",
    "source_page",
]


class Storage:
    def __init__(self, output_dir: str = "output") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.urls_path = self.output_dir / urls_file
        self.details_path = self.output_dir / properties_excel
        self.details_csv_path = self.output_dir / properties_csv
        self.checkpoint_path = self.output_dir / checkpoint
        self._seen_urls: set[str] = set()
        self._seen_ids: set[str] = set()
        self._replace_on_next_write = False
        self._load_seen_urls()

    def _load_seen_urls(self) -> None:
        if not self.urls_path.exists():
            return
        for line in self.urls_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("url"):
                    self._seen_urls.add(row["url"])
                if row.get("listing_id"):
                    self._seen_ids.add(str(row["listing_id"]))
            except json.JSONDecodeError:
                continue

    def load_checkpoint(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {}
        try:
            return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save_checkpoint(self, data: dict[str, Any]) -> None:
        existing = self.load_checkpoint()
        existing.update(data)
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.checkpoint_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append_url(
        self,
        url: str,
        listing_type: str,
        source_page: str,
        listing_id: Optional[str] = None,
    ) -> bool:
        """Append URL if new (by URL or listing_id). Returns True when added."""
        lid = str(listing_id) if listing_id else None
        if url in self._seen_urls or (lid and lid in self._seen_ids):
            return False
        row = {
            "url": url,
            "listing_id": lid,
            "listing_type": listing_type,
            "source_page": source_page,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.urls_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._seen_urls.add(url)
        if lid:
            self._seen_ids.add(lid)
        return True

    def load_urls(self, listing_type: Optional[str] = None) -> list[str]:
        return list(self.load_url_meta(listing_type).keys())

    def load_url_meta(self, listing_type: Optional[str] = None) -> dict[str, dict[str, Any]]:
        if not self.urls_path.exists():
            return {}
        meta: dict[str, dict[str, Any]] = {}
        for line in self.urls_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            url = row.get("url")
            if not url:
                continue
            if listing_type and row.get("listing_type") != listing_type:
                continue
            meta[url] = row
        return meta

    def load_scraped_urls(self) -> set[str]:
        if not self.details_path.exists() and not self.details_csv_path.exists():
            return set()
        try:
            path = self.details_path if self.details_path.exists() else self.details_csv_path
            if str(path).endswith(".csv"):
                df = pd.read_csv(path)
            else:
                df = pd.read_excel(path)
            return set(df["url"].dropna().astype(str))
        except Exception:
            return set()

    def load_scraped_ids(self) -> set[str]:
        path = self.details_path if self.details_path.exists() else self.details_csv_path
        if not path.exists():
            return set()
        try:
            if str(path).endswith(".csv"):
                df = pd.read_csv(path)
            else:
                df = pd.read_excel(path)
            if "listing_id" not in df.columns:
                return set()
            return set(df["listing_id"].dropna().astype(str))
        except Exception:
            return set()

    def append_details(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        now = datetime.now(timezone.utc).isoformat()
        for r in records:
            r.setdefault("scraped_at", now)

        new_df = pd.DataFrame(records)
        for col in OUTPUT_COLUMNS:
            if col not in new_df.columns:
                new_df[col] = None
        new_df = new_df[OUTPUT_COLUMNS]

        if self._replace_on_next_write or not self.details_path.exists():
            combined = new_df.drop_duplicates(subset=["url"], keep="last")
            self._replace_on_next_write = False
        elif self.details_csv_path.exists():
            old_df = pd.read_csv(self.details_csv_path)
            combined = pd.concat([old_df, new_df], ignore_index=True)
        elif self.details_path.exists():
            try:
                old_df = pd.read_excel(self.details_path)
                combined = pd.concat([old_df, new_df], ignore_index=True)
            except Exception:
                combined = new_df
        else:
            combined = new_df

        combined = self._deduplicate(combined)
        self._write_exports(combined)

    def _write_exports(self, df: pd.DataFrame) -> None:
        df.to_csv(self.details_csv_path, index=False, encoding="utf-8-sig")
        try:
            df.to_excel(self.details_path, index=False, engine="openpyxl")
        except PermissionError:
            alt = self.output_dir / "properties_updated.xlsx"
            df.to_excel(alt, index=False, engine="openpyxl")
            print(f"Note: close properties.xlsx in Excel. Saved to {alt}")

    def _deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.drop_duplicates(subset=["url"], keep="last")
        if "listing_id" in df.columns:
            has_id = df["listing_id"].notna() & (df["listing_id"].astype(str).str.strip() != "")
            with_id = df[has_id].drop_duplicates(subset=["listing_id"], keep="last")
            without_id = df[~has_id]
            df = pd.concat([with_id, without_id], ignore_index=True)
        return df

    def export_sample_csv(self, path: Optional[Path] = None, limit: int = 30) -> Path:
        path = path or (self.output_dir / "sample_export.csv")
        if self.details_csv_path.exists():
            df = pd.read_csv(self.details_csv_path).head(limit)
        elif self.details_path.exists():
            df = pd.read_excel(self.details_path).head(limit)
        else:
            df = pd.DataFrame(columns=OUTPUT_COLUMNS)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return path

    def clear_details(self) -> None:
        self._replace_on_next_write = True
        for path in (self.details_path, self.details_csv_path):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass  # file may be open in Excel — will overwrite on next save

    def stats(self) -> dict[str, int]:
        return {
            "urls": len(self.load_urls()),
            "details": len(self.load_scraped_urls()),
        }
