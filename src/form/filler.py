"""Form filler orchestrator — drives the full LinkedIn Easy Apply flow.

Iterates through modal steps (up to ``MAX_FORM_STEPS``), fills every field
via :class:`~src.form.ai_answerer.AIAnswerer`, and handles navigation buttons.
Supports ``DRY_RUN`` mode: fills everything but skips the final Submit click.
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from src.detection.captcha_handler import CaptchaHandler
from src.form.ai_answerer import AIAnswerer
from src.form.field_detector import FieldDetector, FormField
from src.utils.constants import (
    MAX_FORM_STEPS,
    AppStatus,
    FieldType,
    Selectors,
    TIMEOUT_ELEMENT_APPEAR,
)
from src.utils.helpers import human_delay

logger = logging.getLogger(__name__)


class FormFiller:
    """Orchestrate the complete Easy Apply form submission for a single job.

    Parameters
    ----------
    page:
        Active Playwright page.
    ai_answerer:
        Initialised :class:`AIAnswerer` instance.
    cv_path:
        Path to the PDF CV — used for file-upload fields.
    dry_run:
        When ``True``, every step is filled but the Submit button is never
        clicked, allowing safe testing without actual application submission.
    """

    def __init__(
        self,
        page: Page,
        ai_answerer: AIAnswerer,
        cv_path: str | Path,
        dry_run: bool = False,
    ) -> None:
        """Initialise the form filler."""
        self._page = page
        self._ai = ai_answerer
        self._cv_path = Path(cv_path)
        self._dry_run = dry_run
        self._detector = FieldDetector(page)
        self._captcha = CaptchaHandler(page)

    def run(self, job_title: str, job_description: str) -> AppStatus:
        """Execute the full Easy Apply flow for the currently loaded job page.

        Parameters
        ----------
        job_title:
            Job title extracted from the page (for logging/context).
        job_description:
            First 3 000 chars of the job posting text.

        Returns
        -------
        AppStatus
            Outcome of the application attempt.
        """
        # Open the Easy Apply modal
        try:
            self._page.click(Selectors.EASY_APPLY_BTN, timeout=TIMEOUT_ELEMENT_APPEAR)
            human_delay(1500, 3000)
        except PlaywrightTimeoutError:
            logger.warning("Easy Apply button not found on job: %s", job_title)
            return AppStatus.SKIPPED
        except Exception:
            logger.error("Failed to click Easy Apply button", exc_info=True)
            return AppStatus.SKIPPED

        for step in range(1, MAX_FORM_STEPS + 1):
            logger.info("Processing form step %d/%d", step, MAX_FORM_STEPS)

            # Pause for manual CAPTCHA solve if one is detected mid-flow
            if self._captcha.is_captcha_present():
                solved = self._captcha.wait_for_manual_solve()
                if not solved:
                    return AppStatus.CAPTCHA_ABORT

            human_delay(1500, 3000)

            # Scan the current step for fields and fill them
            fields = self._detector.detect_all_fields()
            self._fill_all_fields(fields, job_description)

            # Decide which navigation button to click next
            status = self._advance_or_submit()
            if status is not None:
                return status

        logger.error("Exceeded MAX_FORM_STEPS (%d) — aborting", MAX_FORM_STEPS)
        return AppStatus.FAILED

    def _fill_all_fields(self, fields: list[FormField], job_description: str) -> None:
        """Fill every detected field on the current step."""
        for form_field in fields:
            try:
                self._fill_single_field(form_field, job_description)
                human_delay(400, 1200)
            except Exception:
                logger.error(
                    "Failed to fill field '%s' (%s)",
                    form_field.label,
                    form_field.field_type.name,
                    exc_info=True,
                )

    def _fill_single_field(self, form_field: FormField, job_description: str) -> None:
        """Dispatch to the appropriate fill strategy for *form_field*."""
        ft = form_field.field_type

        if ft == FieldType.FILE_UPLOAD:
            self._fill_file_upload(form_field)

        elif ft in (FieldType.TEXT, FieldType.NUMBER, FieldType.EMAIL, FieldType.PHONE):
            # Skip if already pre-filled to avoid overwriting correct values
            if form_field.current_value:
                logger.debug("Skipping pre-filled field: %s", form_field.label)
                return
            answer = self._ai.get_answer(form_field.label, ft,
                                         job_description=job_description)
            if answer:
                form_field.locator.fill("")
                form_field.locator.type(answer, delay=80)

        elif ft == FieldType.TEXTAREA:
            if form_field.current_value:
                logger.debug("Skipping pre-filled textarea: %s", form_field.label)
                return
            answer = self._ai.get_answer(form_field.label, ft,
                                         job_description=job_description)
            if answer:
                form_field.locator.fill("")
                form_field.locator.type(answer, delay=60)

        elif ft == FieldType.DROPDOWN:
            answer = self._ai.get_answer(
                form_field.label, ft,
                options=form_field.options,
                job_description=job_description,
            )
            if answer:
                form_field.locator.select_option(label=answer)

        elif ft == FieldType.RADIO:
            answer = self._ai.get_answer(
                form_field.label, ft,
                options=form_field.options,
                job_description=job_description,
            )
            if answer:
                self._select_radio(form_field, answer)

        elif ft == FieldType.CHECKBOX:
            answer = self._ai.get_answer(form_field.label, ft,
                                         job_description=job_description)
            if answer and answer.lower() == "check" and not form_field.locator.is_checked():
                # LinkedIn requires a click (not a programmatic check) to register
                form_field.locator.click()

    def _fill_file_upload(self, form_field: FormField) -> None:
        """Upload the CV PDF to a file-upload input."""
        if not self._cv_path.exists():
            logger.error("CV file not found at %s — skipping upload", self._cv_path.name)
            return
        form_field.locator.set_input_files(str(self._cv_path))
        logger.info("Uploaded CV: %s", self._cv_path.name)

    def _select_radio(self, form_field: FormField, answer: str) -> None:
        """Click the radio button whose label matches *answer*.

        LinkedIn requires a real click on the label element (not the hidden
        radio input) to register the selection.
        """
        radios = self._page.locator(
            f'fieldset input[type="radio"]'
        ).all()
        for radio in radios:
            rid = radio.get_attribute("id") or ""
            if rid:
                label_el = self._page.locator(f'label[for="{rid}"]')
                if label_el.count():
                    label_text = label_el.first.inner_text().strip()
                    if label_text.lower() == answer.lower() or answer.lower() in label_text.lower():
                        label_el.first.click()
                        logger.debug("Selected radio option: %s", label_text)
                        return
        logger.warning("Radio option not found: '%s' for question '%s'",
                       answer, form_field.label)

    def _advance_or_submit(self) -> AppStatus | None:
        """Click the appropriate modal navigation button.

        Returns an :class:`AppStatus` when the flow is complete, or ``None``
        to signal that another step should be processed.
        """
        # Submit button takes priority over Review/Next
        if self._page.locator(Selectors.SUBMIT_BUTTON).is_visible():
            return self._handle_submission()

        if self._page.locator(Selectors.REVIEW_BUTTON).is_visible():
            self._page.click(Selectors.REVIEW_BUTTON)
            human_delay(1500, 3000)
            return None  # Continue to the submission step

        if self._page.locator(Selectors.NEXT_BUTTON).is_visible():
            self._page.click(Selectors.NEXT_BUTTON)
            human_delay(1500, 3000)
            return None  # More steps to process

        logger.warning("No navigation button found on current step")
        return AppStatus.FAILED

    def _handle_submission(self) -> AppStatus:
        """Click Submit (unless in dry-run mode) and verify the result.

        DRY_RUN must be respected here — no application is ever submitted
        when the flag is set.
        """
        if self._dry_run:
            logger.info("DRY_RUN — skipping Submit click")
            return AppStatus.DRY_RUN

        self._page.click(Selectors.SUBMIT_BUTTON)
        human_delay(3000, 5000)

        if self._page.locator(Selectors.APP_SUCCESS).is_visible():
            logger.info("Application submitted successfully")
            return AppStatus.SUCCESS

        error_el = self._page.query_selector(Selectors.APP_ERROR)
        if error_el:
            logger.error("Submission error: %s", error_el.inner_text())

        return AppStatus.FAILED
