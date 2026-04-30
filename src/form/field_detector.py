"""DOM field scanner for LinkedIn Easy Apply modal steps.

Scans the currently visible modal step and returns a typed list of
:class:`FormField` objects ready for the AI answerer and form filler.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from playwright.sync_api import Locator, Page

from src.utils.constants import FieldType, Selectors

logger = logging.getLogger(__name__)


@dataclass
class FormField:
    """Structured representation of a single form field on the current step."""

    field_type: FieldType
    label: str          # Human-readable question text
    locator: Locator    # Playwright locator for interaction
    options: list[str] = field(default_factory=list)  # Choices for radio/dropdown
    current_value: str = ""  # Pre-filled value, if any
    is_required: bool = False
    field_id: str = ""


class FieldDetector:
    """Scan the active Easy Apply modal step and enumerate all interactive fields.

    Parameters
    ----------
    page:
        Active Playwright page.
    """

    def __init__(self, page: Page) -> None:
        """Initialise the detector with the active page."""
        self._page = page

    def detect_all_fields(self) -> list[FormField]:
        """Return every interactive field found on the current modal step."""
        fields: list[FormField] = []
        fields.extend(self._detect_text_inputs())
        fields.extend(self._detect_textareas())
        fields.extend(self._detect_dropdowns())
        fields.extend(self._detect_radio_groups())
        fields.extend(self._detect_checkboxes())
        fields.extend(self._detect_file_inputs())
        logger.debug("Detected %d field(s) on current step", len(fields))
        return fields

    # ------------------------------------------------------------------
    # Private detection methods — one per field type
    # ------------------------------------------------------------------

    def _detect_text_inputs(self) -> list[FormField]:
        """Detect text, number, email, and tel input fields."""
        results: list[FormField] = []
        type_map: dict[str, FieldType] = {
            "text": FieldType.TEXT,
            "number": FieldType.NUMBER,
            "email": FieldType.EMAIL,
            "tel": FieldType.PHONE,
        }

        for input_type, field_type in type_map.items():
            selector = f'input[type="{input_type}"]:not([disabled])'
            for locator in self._page.locator(selector).all():
                fid = locator.get_attribute("id") or ""
                results.append(
                    FormField(
                        field_type=field_type,
                        label=self._get_label(locator, fid),
                        locator=locator,
                        current_value=locator.input_value() or "",
                        is_required=self._is_required(locator),
                        field_id=fid,
                    )
                )
        return results

    def _detect_textareas(self) -> list[FormField]:
        """Detect multi-line textarea fields."""
        results: list[FormField] = []
        for locator in self._page.locator(Selectors.TEXTAREA).all():
            fid = locator.get_attribute("id") or ""
            results.append(
                FormField(
                    field_type=FieldType.TEXTAREA,
                    label=self._get_label(locator, fid),
                    locator=locator,
                    current_value=locator.input_value() or "",
                    is_required=self._is_required(locator),
                    field_id=fid,
                )
            )
        return results

    def _detect_dropdowns(self) -> list[FormField]:
        """Detect ``<select>`` dropdown fields and extract their options."""
        results: list[FormField] = []
        for locator in self._page.locator(Selectors.DROPDOWN).all():
            fid = locator.get_attribute("id") or ""
            options = self._get_select_options(locator)
            results.append(
                FormField(
                    field_type=FieldType.DROPDOWN,
                    label=self._get_label(locator, fid),
                    locator=locator,
                    options=options,
                    current_value=locator.input_value() or "",
                    is_required=self._is_required(locator),
                    field_id=fid,
                )
            )
        return results

    def _detect_radio_groups(self) -> list[FormField]:
        """Detect radio-button groups — one :class:`FormField` per ``<fieldset>``."""
        results: list[FormField] = []
        for fieldset in self._page.locator(Selectors.RADIO_GROUP).all():
            legend = fieldset.locator("legend").first
            label = legend.inner_text().strip() if legend.count() else ""

            radios = fieldset.locator('input[type="radio"]').all()
            options: list[str] = []
            for radio in radios:
                rid = radio.get_attribute("id") or ""
                opt_text = ""
                if rid:
                    option_label = self._page.locator(f'label[for="{rid}"]')
                    if option_label.count():
                        opt_text = option_label.first.inner_text().strip()
                # Fallback: use the value attribute when no label is found
                if not opt_text:
                    opt_text = radio.get_attribute("value") or ""
                if opt_text:
                    options.append(opt_text)

            # Use the first radio's locator as the group representative
            group_locator = fieldset.locator('input[type="radio"]').first
            results.append(
                FormField(
                    field_type=FieldType.RADIO,
                    label=label,
                    locator=group_locator,
                    options=[o for o in options if o],
                    is_required=True,  # Radio groups are almost always required
                )
            )
        return results

    def _detect_checkboxes(self) -> list[FormField]:
        """Detect individual checkbox fields."""
        results: list[FormField] = []
        for locator in self._page.locator(Selectors.CHECKBOX).all():
            fid = locator.get_attribute("id") or ""
            results.append(
                FormField(
                    field_type=FieldType.CHECKBOX,
                    label=self._get_label(locator, fid),
                    locator=locator,
                    current_value="checked" if locator.is_checked() else "",
                    is_required=self._is_required(locator),
                    field_id=fid,
                )
            )
        return results

    def _detect_file_inputs(self) -> list[FormField]:
        """Detect file-upload inputs (used for CV/resume upload)."""
        results: list[FormField] = []
        for locator in self._page.locator(Selectors.FILE_UPLOAD).all():
            fid = locator.get_attribute("id") or ""
            results.append(
                FormField(
                    field_type=FieldType.FILE_UPLOAD,
                    label=self._get_label(locator, fid),
                    locator=locator,
                    field_id=fid,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Label resolution helpers
    # ------------------------------------------------------------------

    def _get_label(self, locator: Locator, field_id: str) -> str:
        """Resolve the human-readable label for *locator* using three strategies.

        1. ``<label for="field_id">`` — most reliable
        2. ``aria-label`` attribute
        3. Nearest ancestor ``<fieldset> > <legend>`` text
        """
        # Strategy 1: associated <label>
        if field_id:
            label_el = self._page.locator(f'label[for="{field_id}"]')
            if label_el.count():
                return label_el.first.inner_text().strip()

        # Strategy 2: aria-label attribute
        aria = locator.get_attribute("aria-label")
        if aria:
            return aria.strip()

        # Strategy 3: ancestor fieldset legend
        try:
            legend = locator.locator("xpath=ancestor::fieldset//legend").first
            if legend.count():
                return legend.inner_text().strip()
        except Exception:
            pass

        return ""

    @staticmethod
    def _is_required(locator: Locator) -> bool:
        """Return ``True`` if the element carries a ``required`` attribute."""
        return locator.get_attribute("required") is not None

    @staticmethod
    def _get_select_options(locator: Locator) -> list[str]:
        """Return text of all ``<option>`` elements inside a ``<select>``."""
        return locator.locator("option").all_inner_texts()
