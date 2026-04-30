"""LinkedIn authentication — login once, reuse session via persistent profile.

The persistent browser context (managed by :class:`~src.browser.engine.BrowserEngine`)
stores cookies across restarts, so :meth:`LinkedInAuth.ensure_logged_in` only
needs to call :meth:`_perform_login` on the very first run.
"""
from __future__ import annotations

import logging

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from src.utils.constants import Selectors, TIMEOUT_ELEMENT_APPEAR, TIMEOUT_PAGE_LOAD
from src.utils.helpers import human_delay, human_type

logger = logging.getLogger(__name__)


class LinkedInAuth:
    """Handle LinkedIn login and session validation.

    Parameters
    ----------
    page:
        Active Playwright page from :class:`~src.browser.engine.BrowserEngine`.
    email:
        LinkedIn account e-mail address (read from ``.env``).
    password:
        LinkedIn account password (read from ``.env``).
    """

    def __init__(self, page: Page, email: str, password: str) -> None:
        """Initialise authentication handler with credentials."""
        self._page = page
        self._email = email
        self._password = password

    def ensure_logged_in(self) -> bool:
        """Check session validity and log in if necessary.

        Returns
        -------
        bool
            ``True`` if the session is authenticated after this call,
            ``False`` if login failed.
        """
        logger.info("Checking session validity…")
        try:
            self._page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded",
                            timeout=TIMEOUT_PAGE_LOAD)
        except Exception:
            logger.error("Failed to navigate to LinkedIn feed", exc_info=True)
            return False

        # A profile photo in the top-nav means we are already logged in
        try:
            self._page.wait_for_selector(Selectors.LOGIN_SUCCESS,
                                         timeout=TIMEOUT_ELEMENT_APPEAR)
            logger.info("Session still valid — skipping login")
            return True
        except PlaywrightTimeoutError:
            logger.info("Session expired — performing login")

        return self._perform_login()

    def _perform_login(self) -> bool:
        """Navigate to the login page and submit credentials.

        Returns
        -------
        bool
            ``True`` on successful authentication, ``False`` otherwise.
        """
        try:
            self._page.goto("https://www.linkedin.com/login",
                            wait_until="domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)

            human_type(self._page, Selectors.LOGIN_EMAIL, self._email)
            human_delay(800, 2000)
            human_type(self._page, Selectors.LOGIN_PASSWORD, self._password)
            human_delay(500, 1200)

            self._page.click(Selectors.LOGIN_SUBMIT)
            self._page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_PAGE_LOAD)

            # Verify successful login by looking for the profile photo
            self._page.wait_for_selector(Selectors.LOGIN_SUCCESS,
                                         timeout=TIMEOUT_ELEMENT_APPEAR)
            logger.info("Login successful")
            return True

        except PlaywrightTimeoutError:
            # Check for a visible error banner before giving up
            error_el = self._page.query_selector(Selectors.LOGIN_ERROR)
            if error_el:
                logger.error("Login failed — error message: %s", error_el.inner_text())
            else:
                logger.error("Login timed out — LOGIN_SUCCESS selector not found")
            return False
        except Exception:
            logger.error("Unexpected error during login", exc_info=True)
            return False
