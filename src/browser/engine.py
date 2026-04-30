"""Playwright browser engine with anti-detection hardening.

Launches Chromium with a persistent profile so session cookies survive between
runs.  Each call to :meth:`BrowserEngine.start` picks a random viewport and
User-Agent string so the fingerprint is slightly different each session.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

logger = logging.getLogger(__name__)

# Real-world Chrome UA strings to rotate through
_USER_AGENTS: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
]

_VIEWPORTS: list[dict[str, int]] = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
]

# JavaScript injected into every page before it loads to mask automation flags
_STEALTH_INIT_SCRIPT: str = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {}, loadTimes: function(){}, app: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
"""


class BrowserEngine:
    """Manage the Playwright browser lifecycle.

    Parameters
    ----------
    session_path:
        Directory where the persistent browser profile is stored.
    headless:
        Run headless when ``True``.  Keep ``False`` so CAPTCHA dialogs are
        visible to the operator.
    """

    def __init__(self, session_path: str = "sessions", headless: bool = False) -> None:
        """Initialise the engine — does not start the browser yet."""
        self._session_path = Path(session_path)
        self._session_path.mkdir(parents=True, exist_ok=True)
        self._headless = headless

        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def start(self) -> Page:
        """Launch Chromium with stealth args and return the active :class:`Page`.

        Uses a *persistent* context so authentication cookies are saved between
        runs and the operator only needs to log in once.
        """
        viewport = random.choice(_VIEWPORTS)
        user_agent = random.choice(_USER_AGENTS)

        logger.info(
            "Starting browser: headless=%s  viewport=%dx%d",
            self._headless,
            viewport["width"],
            viewport["height"],
        )

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._session_path),
            headless=self._headless,
            viewport=viewport,
            user_agent=user_agent,
            args=[
                "--disable-blink-features=AutomationControlled",  # Critical — hides automation
                "--disable-infobars",
                "--no-sandbox",
            ],
            ignore_default_args=["--enable-automation"],  # Remove automation flag
        )

        # Inject stealth script before every page navigation
        self._context.add_init_script(_STEALTH_INIT_SCRIPT)

        self._page = self._context.new_page()
        logger.info("Browser started successfully")
        return self._page

    def close(self) -> None:
        """Gracefully shut down the browser and Playwright instance."""
        if self._context:
            try:
                self._context.close()
            except Exception:
                logger.debug("Context already closed", exc_info=True)

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                logger.debug("Playwright already stopped", exc_info=True)

        logger.info("Browser closed")

    @property
    def page(self) -> Page:
        """Return the active page, raising if :meth:`start` has not been called."""
        if self._page is None:
            raise RuntimeError("BrowserEngine.start() must be called before accessing page")
        return self._page
