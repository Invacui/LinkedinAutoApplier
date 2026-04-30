"""LinkedIn Easy Apply Automation — Entry Point.

Orchestrates all modules in the correct order:
  CV parsing → browser start → auth → job loop → logging → summary.

Usage::

    python main.py

Environment variables are loaded from ``.env`` (see ``.env.example``).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from src.auth.linkedin_auth import LinkedInAuth
from src.browser.engine import BrowserEngine
from src.cv_parser.parser import CVParser
from src.detection.captcha_handler import CaptchaHandler
from src.form.ai_answerer import AIAnswerer
from src.form.filler import FormFiller
from src.logger.app_logger import ApplicationLogger
from src.utils.constants import AppStatus, Selectors, TIMEOUT_ELEMENT_APPEAR
from src.utils.helpers import human_delay

console = Console()


def _setup_logging(logs_dir: Path) -> None:
    """Configure root logger: Rich console output + rotating file handler."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_filename = logs_dir / f"run_{time.strftime('%Y-%m-%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(rich_tracebacks=True, show_path=False),
            logging.FileHandler(log_filename, encoding="utf-8"),
        ],
    )


def _validate_env() -> dict[str, str]:
    """Load and validate required environment variables.

    Returns a dict of the loaded values.  Exits with code 1 if any required
    variable is missing so the operator sees a clear error immediately.
    """
    load_dotenv()
    required = ["LINKEDIN_EMAIL", "LINKEDIN_PASSWORD", "ANTHROPIC_API_KEY"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        console.print(
            f"[bold red]Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in your values.[/bold red]"
        )
        sys.exit(1)

    return {
        "email": os.environ["LINKEDIN_EMAIL"],
        "password": os.environ["LINKEDIN_PASSWORD"],
        "api_key": os.environ["ANTHROPIC_API_KEY"],
        "cv_path": os.getenv("CV_PATH", "input/cv/your_cv.pdf"),
        "session_path": os.getenv("SESSION_PATH", "sessions"),
        "headless": os.getenv("HEADLESS_MODE", "false").lower() == "true",
        "dry_run": os.getenv("DRY_RUN", "false").lower() == "true",
        "delay_min": int(os.getenv("DELAY_BETWEEN_JOBS_MIN", "15")),
        "delay_max": int(os.getenv("DELAY_BETWEEN_JOBS_MAX", "45")),
    }


def extract_job_description(page) -> str:
    """Return up to 3 000 chars of the job description text.

    Gracefully returns an empty string if the element is not found — the AI
    can still answer questions without it.
    """
    try:
        el = page.query_selector(Selectors.JOB_DESCRIPTION)
        if el:
            return el.inner_text()[:3000]
    except Exception:
        logging.getLogger(__name__).debug("Job description not found", exc_info=True)
    return ""


def _print_summary(app_logger: ApplicationLogger) -> None:
    """Render a Rich table summarising the run outcomes."""
    summary = app_logger.get_summary()
    if not summary:
        return

    table = Table(title="Run Summary", show_header=True, header_style="bold cyan")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    status_styles = {
        "success": "green",
        "failed": "red",
        "skipped": "yellow",
        "captcha_abort": "bold red",
        "dry_run": "blue",
    }
    for status, count in sorted(summary.items()):
        style = status_styles.get(status, "white")
        table.add_row(f"[{style}]{status}[/{style}]", str(count))

    console.print(table)


def main() -> None:
    """Run the full LinkedIn Easy Apply automation pipeline."""
    env = _validate_env()

    logs_dir = Path("logs")
    _setup_logging(logs_dir)
    log = logging.getLogger(__name__)

    # ── CV ──────────────────────────────────────────────────────────────
    cv_path = Path(env["cv_path"])
    if not cv_path.exists():
        console.print(
            f"[bold red]CV not found: {cv_path}\n"
            "Update CV_PATH in .env or add your PDF to input/cv/.[/bold red]"
        )
        sys.exit(1)

    cv_data = CVParser(cv_path).parse()

    # ── Preferences ─────────────────────────────────────────────────────
    prefs_path = Path("input/user_preferences.json")
    try:
        with open(prefs_path, encoding="utf-8") as fh:
            preferences = json.load(fh)
    except FileNotFoundError:
        console.print(f"[bold red]Preferences file not found: {prefs_path}[/bold red]")
        sys.exit(1)

    # ── Job list ─────────────────────────────────────────────────────────
    jobs_path = Path("input/job_urls.json")
    try:
        with open(jobs_path, encoding="utf-8") as fh:
            jobs: list[dict] = json.load(fh)["jobs"]
    except (FileNotFoundError, KeyError):
        console.print(f"[bold red]Jobs file not found or malformed: {jobs_path}[/bold red]")
        sys.exit(1)

    # ── Logger & deduplication ────────────────────────────────────────────
    app_logger = ApplicationLogger(str(logs_dir))
    applied_urls = app_logger.get_applied_urls()
    pending_jobs = [j for j in jobs if j["url"] not in applied_urls]

    if not pending_jobs:
        console.print("[bold yellow]All jobs already applied to — nothing to do.[/bold yellow]")
        return

    console.print(
        f"[bold green]Starting run: {len(pending_jobs)} pending job(s) "
        f"({len(jobs) - len(pending_jobs)} already applied)[/bold green]"
    )

    # ── Browser & Auth ───────────────────────────────────────────────────
    browser = BrowserEngine(
        session_path=env["session_path"],
        headless=bool(env["headless"]),
    )
    page = browser.start()

    auth = LinkedInAuth(page, env["email"], env["password"])
    if not auth.ensure_logged_in():
        console.print("[bold red]Login failed — check credentials in .env[/bold red]")
        browser.close()
        sys.exit(1)

    ai = AIAnswerer(env["api_key"], cv_data, preferences)
    captcha_handler = CaptchaHandler(page)

    # ── Main job loop ─────────────────────────────────────────────────────
    try:
        for idx, job in enumerate(pending_jobs, start=1):
            job_id = job.get("id", f"job_{idx:03d}")
            company = job.get("company", "Unknown")
            title = job.get("title", "Unknown")
            url = job["url"]

            console.print(
                f"\n[bold cyan][{idx}/{len(pending_jobs)}][/bold cyan] "
                f"{company} — {title}"
            )
            log.info("Processing job %s: %s @ %s", job_id, title, company)

            start_time = time.monotonic()
            status = AppStatus.FAILED

            try:
                page.goto(url, wait_until="domcontentloaded")
                human_delay(2000, 4000)

                # Check for CAPTCHA before interacting with the page
                if captcha_handler.is_captcha_present():
                    solved = captcha_handler.wait_for_manual_solve()
                    if not solved:
                        status = AppStatus.CAPTCHA_ABORT
                        raise RuntimeError("CAPTCHA not solved within timeout")

                job_description = extract_job_description(page)

                filler = FormFiller(
                    page=page,
                    ai_answerer=ai,
                    cv_path=cv_path,
                    dry_run=bool(env["dry_run"]),
                )
                status = filler.run(title, job_description)

            except Exception:
                log.error("Error processing job %s", job_id, exc_info=True)
                status = AppStatus.FAILED

            duration = time.monotonic() - start_time
            app_logger.record(
                job_id=job_id,
                company=company,
                title=title,
                status=status.value,
                url=url,
                duration_seconds=duration,
            )

            console.print(f"  → [{'green' if status == AppStatus.SUCCESS else 'yellow'}]{status.value}[/] ({duration:.1f}s)")

            # Delay between jobs — reduces bot detection risk
            if idx < len(pending_jobs):
                delay_s = int(
                    __import__("random").uniform(
                        int(env["delay_min"]), int(env["delay_max"])
                    )
                )
                log.info("Waiting %ds before next job…", delay_s)
                human_delay(delay_s * 1000, delay_s * 1000)

    finally:
        browser.close()

    _print_summary(app_logger)


if __name__ == "__main__":
    main()
