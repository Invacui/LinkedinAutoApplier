"""
Central constants. ALL selectors live here — never hardcode in other modules.
LinkedIn uses Artdeco design system. Prefer aria-* and data-* over class names.
"""
from enum import Enum, auto

# Timeouts (milliseconds)
TIMEOUT_PAGE_LOAD: int = 30_000
TIMEOUT_ELEMENT_APPEAR: int = 10_000
TIMEOUT_CAPTCHA_MANUAL: int = 300_000   # 5 min for user to solve CAPTCHA

# Form iteration limit — prevents infinite loops on unexpected modal structures
MAX_FORM_STEPS: int = 10


class Selectors:
    """All CSS/ARIA selectors for LinkedIn DOM elements."""

    # Login
    LOGIN_EMAIL: str = "input#username"
    LOGIN_PASSWORD: str = "input#password"
    LOGIN_SUBMIT: str = 'button[type="submit"]'
    LOGIN_SUCCESS: str = ".global-nav__me-photo"  # Profile photo = logged in
    LOGIN_ERROR: str = ".alert-content"

    # Job page
    EASY_APPLY_BTN: str = "button.jobs-apply-button"
    JOB_TITLE: str = "h1.job-details-jobs-unified-top-card__job-title"
    JOB_DESCRIPTION: str = ".jobs-description-content__text"

    # Easy Apply modal navigation
    NEXT_BUTTON: str = 'button[aria-label="Continue to next step"]'
    REVIEW_BUTTON: str = 'button[aria-label="Review your application"]'
    SUBMIT_BUTTON: str = 'button[aria-label="Submit application"]'

    # Form fields
    TEXT_INPUT: str = 'input[type="text"]:not([disabled])'
    NUMBER_INPUT: str = 'input[type="number"]:not([disabled])'
    EMAIL_INPUT: str = 'input[type="email"]:not([disabled])'
    PHONE_INPUT: str = 'input[type="tel"]:not([disabled])'
    TEXTAREA: str = "textarea:not([disabled])"
    DROPDOWN: str = "select:not([disabled])"
    RADIO_GROUP: str = 'fieldset:has(input[type="radio"])'
    CHECKBOX: str = 'input[type="checkbox"]:not([disabled])'
    FILE_UPLOAD: str = 'input[type="file"]'

    # CAPTCHA indicators
    CAPTCHA_IFRAME: str = 'iframe[src*="captcha"], iframe[src*="challenge"]'

    # Result indicators
    APP_SUCCESS: str = 'h3:has-text("Your application was sent")'
    APP_ERROR: str = ".artdeco-inline-feedback--error"


class FieldType(Enum):
    """Enumeration of supported form field types."""

    TEXT = auto()
    NUMBER = auto()
    EMAIL = auto()
    PHONE = auto()
    TEXTAREA = auto()
    DROPDOWN = auto()
    RADIO = auto()
    CHECKBOX = auto()
    FILE_UPLOAD = auto()
    UNKNOWN = auto()


class AppStatus(Enum):
    """Enumeration of possible application outcomes."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CAPTCHA_ABORT = "captcha_abort"
    DRY_RUN = "dry_run"
