"""CAPTCHA/security-challenge detection and manual-solve coordination.

NO third-party bypass services are used.  The operator solves the challenge
in the visible browser window; this handler polls until the challenge
disappears or a 5-minute timeout is reached.
Keep ``HEADLESS_MODE=false`` so the browser window stays visible.
"""
from __future__ import annotations

import logging
import time

from playwright.sync_api import Page
from rich.console import Console
from rich.panel import Panel

from src.utils.constants import Selectors, TIMEOUT_CAPTCHA_MANUAL

logger = logging.getLogger(__name__)
console = Console()


class CaptchaHandler:
    """Detect CAPTCHAs and pause execution for manual operator solving.

    Parameters
    ----------
    page:
        Active Playwright page.
    """

    # Text fragments that indicate a security/verification page
    _CHALLENGE_TEXTS: tuple[str, ...] = (
        "security verification",
        "unusual activity",
        "verify you're human",
        "verify you are human",
        "let's do a quick security check",
    )

    def __init__(self, page: Page) -> None:
        """Initialise the CAPTCHA handler with the active page."""
        self._page = page

    def is_captcha_present(self) -> bool:
        """Return ``True`` if a CAPTCHA or security challenge is detected.

        Checks both iframe-based CAPTCHAs (reCAPTCHA / hCaptcha) and
        text-based LinkedIn security verification pages.
        """
        # 1. Look for a visible CAPTCHA iframe
        for selector in Selectors.CAPTCHA_IFRAME.split(","):
            el = self._page.query_selector(selector.strip())
            if el and el.is_visible():
                return True

        # 2. Scan visible page body text for challenge indicators
        try:
            body_text = self._page.inner_text("body").lower()
        except Exception:
            return False

        return any(phrase in body_text for phrase in self._CHALLENGE_TEXTS)

    def wait_for_manual_solve(self) -> bool:
        """Block until the CAPTCHA is solved or the timeout expires.

        Displays a prominent terminal alert and polls every 3 seconds.

        Returns
        -------
        bool
            ``True`` if the challenge was solved within the timeout window,
            ``False`` if the operator did not solve it in time.
        """
        self._print_alert()

        deadline = time.monotonic() + TIMEOUT_CAPTCHA_MANUAL / 1000
        poll_interval = 3  # seconds

        while time.monotonic() < deadline:
            time.sleep(poll_interval)
            if not self.is_captcha_present():
                console.print("[bold green]✅  CAPTCHA solved — resuming automation[/bold green]")
                time.sleep(2)  # Short pause before continuing to let page settle
                return True

        logger.error("CAPTCHA was not solved within the %ds timeout", TIMEOUT_CAPTCHA_MANUAL // 1000)
        return False

    def _print_alert(self) -> None:
        """Print a prominent, operator-facing CAPTCHA alert to the terminal."""
        message = (
            "1. Look at the browser window\n"
            "2. Complete the security challenge\n"
            "3. Automation resumes automatically\n\n"
            f"[yellow]Waiting up to {TIMEOUT_CAPTCHA_MANUAL // 60_000} minutes…[/yellow]"
        )
        console.print(
            Panel(
                message,
                title="[bold red]⚠️  CAPTCHA DETECTED — ACTION REQUIRED[/bold red]",
                border_style="bold yellow",
                expand=False,
            )
        )
