"""Application result logger — writes to JSON and CSV.

Every job processed by the runner is recorded here regardless of outcome.
The logger also exposes :meth:`get_applied_urls` so ``main.py`` can skip
jobs that were already applied to in a previous run.
"""
from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_JSON_FILENAME = "applications.json"
_CSV_FILENAME = "applications.csv"
_CSV_FIELDNAMES = [
    "timestamp",
    "job_id",
    "company",
    "title",
    "status",
    "url",
    "error",
    "duration_seconds",
]


class ApplicationLogger:
    """Persist application results and query historical records.

    Parameters
    ----------
    logs_dir:
        Directory where ``applications.json`` and ``applications.csv`` live.
        Created automatically if it does not exist.
    """

    def __init__(self, logs_dir: str = "logs") -> None:
        """Initialise the logger and ensure the output directory exists."""
        self._dir = Path(logs_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._json_path = self._dir / _JSON_FILENAME
        self._csv_path = self._dir / _CSV_FILENAME
        self._records: list[dict[str, Any]] = self._load_existing_json()

    def record(
        self,
        *,
        job_id: str,
        company: str,
        title: str,
        status: str,
        url: str,
        error: str = "",
        duration_seconds: float = 0.0,
    ) -> None:
        """Append a result record to both JSON and CSV stores.

        Parameters
        ----------
        job_id:
            Unique identifier from ``job_urls.json``.
        company:
            Company name.
        title:
            Job title.
        status:
            One of the :class:`~src.utils.constants.AppStatus` values.
        url:
            LinkedIn job URL.
        error:
            Error message if the application failed.
        duration_seconds:
            Wall-clock time taken to process the job.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "job_id": job_id,
            "company": company,
            "title": title,
            "status": status,
            "url": url,
            "error": error,
            "duration_seconds": round(duration_seconds, 1),
        }
        self._records.append(entry)
        self._write_json()
        self._append_csv(entry)
        logger.info("Recorded: [%s] %s @ %s", status, title, company)

    def get_applied_urls(self) -> set[str]:
        """Return the set of URLs where a successful application was submitted.

        Used by ``main.py`` to skip already-applied jobs on subsequent runs.
        """
        return {r["url"] for r in self._records if r.get("status") == "success"}

    def get_summary(self) -> dict[str, int]:
        """Return a count of results grouped by status."""
        summary: dict[str, int] = {}
        for r in self._records:
            summary[r["status"]] = summary.get(r["status"], 0) + 1
        return summary

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_existing_json(self) -> list[dict[str, Any]]:
        """Load previously recorded results from the JSON file."""
        if not self._json_path.exists():
            return []
        try:
            with open(self._json_path, encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not load existing JSON log — starting fresh", exc_info=True)
            return []

    def _write_json(self) -> None:
        """Overwrite the JSON file with the current in-memory records."""
        try:
            with open(self._json_path, "w", encoding="utf-8") as fh:
                json.dump(self._records, fh, indent=2, ensure_ascii=False)
        except OSError:
            logger.error("Failed to write JSON log", exc_info=True)

    def _append_csv(self, entry: dict[str, Any]) -> None:
        """Append a single record row to the CSV file."""
        write_header = not self._csv_path.exists() or os.path.getsize(self._csv_path) == 0
        try:
            with open(self._csv_path, "a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDNAMES)
                if write_header:
                    writer.writeheader()
                writer.writerow({k: entry.get(k, "") for k in _CSV_FIELDNAMES})
        except OSError:
            logger.error("Failed to append to CSV log", exc_info=True)
