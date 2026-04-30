"""CV PDF text extraction and structured parsing.

The PDF is read once at startup; subsequent callers receive the cached result.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Section-header patterns (case-insensitive).  Headers shorter than 50 chars
# that match these patterns are used as section boundaries.
_SECTION_PATTERNS: dict[str, str] = {
    "experience": r"experience|work history|employment",
    "education": r"education|qualifications|academic",
    "skills": r"skills|technologies|competencies|technical",
}


@dataclass
class CVData:
    """Structured representation of the candidate's CV."""

    full_text: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    experience_text: str = ""
    education_text: str = ""
    total_pages: int = 0

    def to_ai_context(self) -> str:
        """Return a compact string suitable for inclusion in Claude prompts."""
        skills_str = ", ".join(self.skills[:30]) if self.skills else "Not specified"
        return (
            "=== CANDIDATE CV SUMMARY ===\n"
            f"Name: {self.name}\n"
            f"Email: {self.email}\n"
            f"Phone: {self.phone}\n"
            f"Location: {self.location}\n"
            f"Skills: {skills_str}\n\n"
            f"Work Experience:\n{self.experience_text[:2000]}\n\n"
            f"Education:\n{self.education_text[:1000]}\n"
            "=== END CV ==="
        )


class CVParser:
    """Parse a PDF CV and expose structured data for downstream modules.

    Parameters
    ----------
    cv_path:
        Filesystem path to the candidate's PDF CV.
    """

    def __init__(self, cv_path: str | Path) -> None:
        """Initialise the parser with the path to the CV PDF."""
        self._path = Path(cv_path)
        self._cached: Optional[CVData] = None

    def parse(self) -> CVData:
        """Return parsed :class:`CVData`, reading the PDF only on the first call.

        The result is cached so the file is never opened more than once per
        process lifetime.
        """
        if self._cached is not None:
            return self._cached

        if not self._path.exists():
            raise FileNotFoundError(f"CV not found: {self._path}")

        logger.info("Parsing CV: %s", self._path.name)
        doc = fitz.open(str(self._path))
        pages_text: list[str] = []
        for page in doc:
            pages_text.append(page.get_text("text"))
        doc.close()

        full_text = "\n".join(pages_text)
        cv = CVData(full_text=full_text, total_pages=len(pages_text))

        self._extract_contact_info(cv)
        self._extract_sections(cv)

        self._cached = cv
        logger.info("CV parsed: %d pages, %d chars", cv.total_pages, len(full_text))
        return cv

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_contact_info(self, cv: CVData) -> None:
        """Populate *cv* fields: name, email, phone from raw text."""
        lines = [ln.strip() for ln in cv.full_text.splitlines() if ln.strip()]

        # Name — first non-empty line that is NOT an email/phone
        for line in lines[:5]:
            if not re.search(r"[@+]|\d{5,}", line):
                cv.name = line
                break

        # Email
        email_match = re.search(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", cv.full_text
        )
        if email_match:
            cv.email = email_match.group()

        # Phone — international or local formats
        phone_match = re.search(
            r"(\+?\d[\d\s\-\(\)]{7,}\d)", cv.full_text
        )
        if phone_match:
            cv.phone = phone_match.group().strip()

    def _extract_sections(self, cv: CVData) -> None:
        """Split the CV text into labelled sections and populate *cv*."""
        lines = cv.full_text.splitlines()

        # Map section key → start line index
        section_starts: dict[str, int] = {}
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or len(stripped) > 50:
                continue
            for key, pattern in _SECTION_PATTERNS.items():
                if re.search(pattern, stripped, re.IGNORECASE):
                    # Only keep the *first* occurrence of each section
                    if key not in section_starts:
                        section_starts[key] = idx

        # Extract text between consecutive section boundaries
        sorted_sections = sorted(section_starts.items(), key=lambda x: x[1])

        for i, (key, start_idx) in enumerate(sorted_sections):
            end_idx = sorted_sections[i + 1][1] if i + 1 < len(sorted_sections) else len(lines)
            section_text = "\n".join(lines[start_idx + 1 : end_idx]).strip()

            if key == "experience":
                cv.experience_text = section_text
            elif key == "education":
                cv.education_text = section_text
            elif key == "skills":
                cv.skills = _parse_skills(section_text)


def _parse_skills(text: str) -> list[str]:
    """Extract individual skill tokens from a skills section block."""
    # Split on common delimiters: comma, pipe, newline, bullet
    tokens = re.split(r"[,|\n•·▪\-]+", text)
    return [t.strip() for t in tokens if t.strip() and len(t.strip()) < 60]
