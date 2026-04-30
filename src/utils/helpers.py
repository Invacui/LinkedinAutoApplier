"""Shared utility helpers used across all modules."""
import random
import time
import logging

from playwright.sync_api import Page

logger = logging.getLogger(__name__)


def human_delay(min_ms: int = 500, max_ms: int = 2000) -> None:
    """Sleep a random duration to simulate human timing.

    Always use this instead of ``time.sleep()`` with a fixed value so that
    request patterns are less predictable to LinkedIn's anti-bot systems.
    """
    duration = random.uniform(min_ms / 1000, max_ms / 1000)
    logger.debug("human_delay: sleeping %.2fs", duration)
    time.sleep(duration)


def human_type(page: Page, selector: str, text: str) -> None:
    """Type *text* into *selector* character-by-character with random key delays.

    Mimics realistic typing cadence (50–150 ms per keystroke) instead of
    instantly filling the field, which would look robotic to LinkedIn.
    """
    page.click(selector)
    page.fill(selector, "")
    page.type(selector, text, delay=random.randint(50, 150))
