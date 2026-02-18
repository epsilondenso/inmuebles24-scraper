"""Browser session using DrissionPage (passes Inmuebles24 Cloudflare)."""

from __future__ import annotations

import json
import os
import random
import re
import time
from pathlib import Path
from typing import Optional

import requests
from DrissionPage import ChromiumOptions, ChromiumPage
from DrissionPage.errors import PageDisconnectedError

COOKIES_PATH = Path("output") / "browser_cookies.json"
PROFILE_DIR = Path("output") / "drission_profile"

CLOUDFLARE_MARKERS = (
    "just a moment",
    "un momento",
    "cf-browser-verification",
    "challenge-platform",
    "verificar que usted es un ser humano",
    "checking your browser",
)


class BrowserSession:
    """DrissionPage-backed browser that clears Cloudflare on Inmuebles24."""

    def __init__(
        self,
        headless: Optional[bool] = None,
        proxy: Optional[str] = None,
        locale: str = "es-MX",
    ) -> None:
        self.headless = headless if headless is not None else os.getenv("HEADLESS", "false").lower() == "true"
        self.proxy = proxy or os.getenv("PROXY_SERVER")
        self.locale = locale
        self._page: Optional[ChromiumPage] = None
        self._warmed = False

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _build_options(self) -> ChromiumOptions:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        options = ChromiumOptions()
        options.set_user_data_path(str(PROFILE_DIR))
        options.set_argument("--lang=es-MX")
        options.set_argument("--disable-blink-features=AutomationControlled")
        options.set_argument("--no-first-run")
        options.set_argument("--no-default-browser-check")
        options.headless(self.headless)
        if self.proxy:
            options.set_proxy(self.proxy)
        return options

    def start(self) -> ChromiumPage:
        self._page = ChromiumPage(self._build_options())
        self._restore_cookies()
        return self._page

    def close(self) -> None:
        if self._page:
            try:
                self._save_cookies()
            except Exception:
                pass
            try:
                self._page.quit()
            except Exception:
                pass
        self._page = None
        self._warmed = False

    def restart(self) -> ChromiumPage:
        self.close()
        time.sleep(1)
        return self.start()

    @property
    def page(self) -> ChromiumPage:
        if not self._page:
            raise RuntimeError("Browser session not started")
        return self._page

    def random_delay(self) -> None:
        lo = float(os.getenv("REQUEST_DELAY_MIN", "2"))
        hi = float(os.getenv("REQUEST_DELAY_MAX", "5"))
        time.sleep(random.uniform(lo, hi))

    def is_cloudflare_page(self, html: str, title: str = "") -> bool:
        blob = (html[:8000] + " " + title).lower()
        if any(marker in blob for marker in CLOUDFLARE_MARKERS):
            return True
        if "/propiedades/" in html and ("posting-card" in html or "posting-title" in html):
            return False
        if "inmuebles24" in blob and any(w in blob for w in ("recámara", "recamara", "precio", "habitacion")):
            return False
        return "inmuebles24.com" in blob and len(html) < 50_000 and "momento" in blob

    def fetch(self, url: str, wait_selector: Optional[str] = None, timeout_ms: int = 90000) -> str:
        flaresolverr = os.getenv("FLARESOLVERR_URL")
        if flaresolverr:
            return fetch_via_flaresolverr(url, flaresolverr)

        timeout_sec = timeout_ms / 1000
        last_error: Optional[Exception] = None

        for attempt in range(3):
            try:
                return self._fetch_once(url, wait_selector, timeout_sec)
            except PageDisconnectedError as exc:
                last_error = exc
                self.restart()
                time.sleep(2)
            except CloudflareBlockedError:
                raise

        raise CloudflareBlockedError(url) from last_error

    def _fetch_once(self, url: str, wait_selector: Optional[str], timeout_sec: float) -> str:
        page = self.page

        if not self._warmed:
            page.get("https://www.inmuebles24.com/")
            self._wait_for_challenge(page, timeout_sec=min(timeout_sec, 45))
            self._warmed = True
            time.sleep(random.uniform(1, 2))

        page.get(url)
        self._wait_for_challenge(page, timeout_sec=timeout_sec)

        if wait_selector:
            needle = wait_selector.replace("[", "").replace("]", "").replace("href*=", "").strip("'\"")
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                if needle in self._safe_html(page):
                    break
                time.sleep(1)

        try:
            page.scroll.to_half()
        except Exception:
            pass
        time.sleep(random.uniform(0.5, 1.2))

        html = self._safe_html(page)
        title = self._safe_title(page)
        if self.is_cloudflare_page(html, title):
            raise CloudflareBlockedError(url)
        return html

    def _wait_for_challenge(self, page: ChromiumPage, timeout_sec: float = 60) -> None:
        manual_wait = float(os.getenv("CF_MANUAL_WAIT_SEC", "120"))
        deadline = time.time() + timeout_sec
        manual_deadline = time.time() + manual_wait
        prompted = False

        while time.time() < deadline:
            if not self.is_cloudflare_page(self._safe_html(page), self._safe_title(page)):
                return
            time.sleep(2)

        if not self.headless and time.time() < manual_deadline:
            if not prompted:
                print(
                    "\n[Cloudflare] If you see a challenge, complete it in the browser. "
                    f"Waiting up to {int(manual_deadline - time.time())}s...\n"
                )
            while time.time() < manual_deadline:
                if not self.is_cloudflare_page(self._safe_html(page), self._safe_title(page)):
                    return
                time.sleep(2)

        raise CloudflareBlockedError(page.url)

    def _safe_html(self, page: ChromiumPage) -> str:
        try:
            return page.html or ""
        except Exception:
            return ""

    def _safe_title(self, page: ChromiumPage) -> str:
        try:
            return page.title or ""
        except Exception:
            return ""

    def _save_cookies(self) -> None:
        cookies = self.page.cookies()
        COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

    def _restore_cookies(self) -> None:
        if not COOKIES_PATH.exists():
            return
        try:
            cookies = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
            if cookies:
                self.page.set.cookies(cookies)
        except Exception:
            pass


def fetch_via_flaresolverr(url: str, base_url: str) -> str:
    payload = {"cmd": "request.get", "url": url, "maxTimeout": 120000}
    resp = requests.post(f"{base_url.rstrip('/')}/v1", json=payload, timeout=130)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "ok":
        raise CloudflareBlockedError(url)
    html = data.get("solution", {}).get("response", "")
    if not html or any(m in html.lower() for m in ("just a moment", "un momento")):
        raise CloudflareBlockedError(url)
    return html


class CloudflareBlockedError(RuntimeError):
    def __init__(self, url: str) -> None:
        super().__init__(f"Cloudflare block on {url}")
