"""Claude API answer engine — the intelligent core of the form filler.

Sends each form question to Claude claude-sonnet-4-20250514 together with the
candidate's CV and preferences.  Answers are cached per session so identical
questions are only sent to the API once.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.cv_parser.parser import CVData
from src.utils.constants import FieldType

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 300

_SYSTEM_PROMPT = """You are a job-application assistant filling out a LinkedIn Easy Apply form on behalf of a candidate.

Rules:
- Answer ONLY from the candidate's actual CV and preferences. Never fabricate or exaggerate.
- For DROPDOWN or RADIO fields, return EXACTLY one option string from the provided list — copy it verbatim.
- For NUMBER fields, return just the numeric value (no units, no text).
- For CHECKBOX fields, return "check" if the candidate should tick it, otherwise "skip".
- For TEXT / TEXTAREA / EMAIL / PHONE fields, return the answer only — no preamble, no labels.
- For cover letters (TEXTAREA where question mentions cover letter), write 100–150 words,
  professional, first-person, enthusiastic but genuine.
- If you cannot determine the answer from the provided data, return an empty string rather than guessing."""


class AIAnswerer:
    """Query Claude for each form question and cache results within the session.

    Parameters
    ----------
    api_key:
        Anthropic API key (from ``ANTHROPIC_API_KEY`` env var).
    cv_data:
        Parsed candidate CV.
    preferences:
        Loaded ``user_preferences.json`` dict.
    """

    def __init__(self, api_key: str, cv_data: CVData, preferences: dict[str, Any]) -> None:
        """Initialise the answerer with credentials and candidate data."""
        self._client = anthropic.Anthropic(api_key=api_key)
        self._cv_data = cv_data
        self._preferences = preferences
        self._cache: dict[str, str] = {}
        self._context_block = self._build_context_block()

    def get_answer(
        self,
        question: str,
        field_type: FieldType,
        options: list[str] | None = None,
        job_description: str = "",
    ) -> str:
        """Return the best answer for *question* given *field_type* and *options*.

        Results are cached: if the same question appears on multiple steps
        (e.g., "Are you authorised to work?") the API is only called once.

        Parameters
        ----------
        question:
            The label text of the form field.
        field_type:
            Enum value indicating field kind (text, dropdown, etc.).
        options:
            Available choices for DROPDOWN / RADIO fields.
        job_description:
            First 3 000 chars of the job posting — passed as extra context.
        """
        cache_key = f"{question}|{field_type.name}|{','.join(options or [])}"
        if cache_key in self._cache:
            logger.debug("Cache hit for question: %.60s…", question)
            return self._cache[cache_key]

        answer = self._call_claude(question, field_type, options, job_description)

        if field_type in (FieldType.DROPDOWN, FieldType.RADIO) and options:
            answer = self._validate_option(answer, options, question)

        self._cache[cache_key] = answer
        return answer

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_context_block(self) -> str:
        """Assemble the static candidate context inserted into every prompt."""
        prefs_str = json.dumps(self._preferences, indent=2)
        return (
            f"{self._cv_data.to_ai_context()}\n\n"
            "=== PREFERENCES ===\n"
            f"{prefs_str}\n"
            "=== END PREFERENCES ==="
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_claude(
        self,
        question: str,
        field_type: FieldType,
        options: list[str] | None,
        job_description: str,
    ) -> str:
        """Send the question to Claude and return the raw text response.

        Retried up to 3 times with exponential back-off on transient errors.
        """
        options_block = ""
        if options:
            options_block = "\nAvailable options (choose exactly one):\n" + "\n".join(
                f"  - {o}" for o in options
            )

        job_block = ""
        if job_description:
            job_block = f"\n=== JOB DESCRIPTION ===\n{job_description[:3000]}\n=== END JOB DESCRIPTION ==="

        user_message = (
            f"{self._context_block}\n"
            f"{job_block}\n\n"
            f"Field type: {field_type.name}\n"
            f"Question: {question}"
            f"{options_block}\n\n"
            "Your answer:"
        )

        try:
            response = self._client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            answer = response.content[0].text.strip()
            logger.debug("Claude answered %.60s… → %.80s", question, answer)
            return answer
        except Exception:
            logger.error("Claude API call failed for question: %s", question, exc_info=True)
            return self._fallback_answer(field_type, options)

    def _validate_option(self, answer: str, options: list[str], question: str) -> str:
        """Ensure *answer* exactly matches one of *options*.

        Tries in order:
        1. Exact case-insensitive match
        2. Partial / substring match
        3. First option as last resort (with a warning)
        """
        # 1. Exact match (case-insensitive)
        for opt in options:
            if opt.lower() == answer.lower():
                return opt

        # 2. Partial match
        for opt in options:
            if answer.lower() in opt.lower() or opt.lower() in answer.lower():
                logger.debug("Partial option match: '%s' → '%s'", answer, opt)
                return opt

        # 3. Last resort
        logger.warning(
            "Could not match answer '%s' to options %s for question '%s'. "
            "Falling back to first option.",
            answer,
            options,
            question,
        )
        return options[0]

    def _fallback_answer(self, field_type: FieldType, options: list[str] | None) -> str:
        """Return a safe default when the API call fails entirely."""
        if field_type in (FieldType.DROPDOWN, FieldType.RADIO) and options:
            return options[0]
        if field_type == FieldType.EMAIL:
            return self._preferences.get("personal", {}).get("email", "")
        if field_type == FieldType.PHONE:
            return self._preferences.get("personal", {}).get("phone", "")
        return ""
