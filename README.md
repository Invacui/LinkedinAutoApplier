# LinkedinAutoApplier

> **Automate your LinkedIn Easy Apply job applications using AI.**

LinkedinAutoApplier is a Python-based automation tool that logs into your LinkedIn account, opens each job posting you specify, and automatically fills in and submits the Easy Apply form. It uses **Claude AI (Anthropic)** to intelligently answer form questions based on your CV and personal preferences — so you spend less time copy-pasting and more time preparing for interviews.

**What it does:**
- Reads your CV (PDF) and personal preferences to answer application questions
- Navigates LinkedIn Easy Apply forms end-to-end
- Handles multi-step forms, dropdowns, and text fields
- Detects CAPTCHAs and pauses for you to solve them manually
- Logs every application result and skips jobs you've already applied to
- Supports a **dry-run** mode so you can test without actually submitting

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
   - [Environment variables (.env)](#1-environment-variables-env)
   - [Add your CV](#2-add-your-cv)
   - [Set your preferences](#3-set-your-preferences-inputuser_preferencesjson)
   - [Add job URLs](#4-add-job-urls-inputjob_urlsjson)
4. [Running the bot](#running-the-bot)
5. [Dry-run mode (recommended for first use)](#dry-run-mode-recommended-for-first-use)
6. [Project structure](#project-structure)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before you begin, make sure you have the following installed on your computer:

| Requirement | Version | How to check |
|---|---|---|
| **Python** | 3.10 or newer | `python --version` |
| **pip** | bundled with Python | `pip --version` |
| **Git** | any recent version | `git --version` |

You will also need:
- A **LinkedIn account** (email + password)
- An **Anthropic API key** — get one for free at <https://console.anthropic.com>

---

## Installation

Follow these steps in your terminal (Command Prompt / PowerShell on Windows, Terminal on macOS/Linux).

### 1. Clone the repository

```bash
git clone https://github.com/Invacui/LinkedinAutoApplier.git
cd LinkedinAutoApplier
```

### 2. Create and activate a virtual environment

Using a virtual environment keeps the project's dependencies separate from the rest of your system.

**macOS / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows**
```bash
python -m venv venv
venv\Scripts\activate
```

You should see `(venv)` at the start of your terminal prompt once it's activated.

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install the Playwright browser

Playwright drives the browser that fills in the forms. Run this once to download the required browser binary:

```bash
playwright install chromium
```

---

## Configuration

### 1. Environment variables (.env)

Copy the example file and fill in your real values:

```bash
cp .env.example .env
```

Then open `.env` in any text editor and update the values:

```
LINKEDIN_EMAIL=your_email@gmail.com      # Your LinkedIn login email
LINKEDIN_PASSWORD=your_password          # Your LinkedIn password
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx     # Your Anthropic (Claude) API key
CV_PATH=input/cv/your_cv.pdf            # Path to your CV (see next step)
SESSION_PATH=sessions                    # Where login sessions are saved
HEADLESS_MODE=false                      # false = show the browser window
DELAY_BETWEEN_JOBS_MIN=15               # Min seconds to wait between jobs
DELAY_BETWEEN_JOBS_MAX=45               # Max seconds to wait between jobs
DRY_RUN=false                           # true = fill forms but don't submit
```

> **Tip:** Keep `HEADLESS_MODE=false` while getting started — you'll be able to watch the bot work and step in if anything goes wrong.

### 2. Add your CV

Place your CV as a **PDF file** inside the `input/cv/` folder:

```
input/
└── cv/
    └── your_cv.pdf   ← put your file here
```

Update `CV_PATH` in `.env` if you name the file differently (e.g. `input/cv/john_doe_cv.pdf`).

### 3. Set your preferences (`input/user_preferences.json`)

Open `input/user_preferences.json` and replace the sample data with your own information. This file tells the AI how to answer questions about salary, notice period, location, etc.

```json
{
  "personal": {
    "full_name": "Your Name",
    "email": "you@example.com",
    "phone": "+1-555-000-0000",
    "city": "New York",
    "linkedin_url": "https://linkedin.com/in/yourprofile"
  },
  "work_authorization": {
    "authorized_to_work_in_india": false,
    "requires_visa_sponsorship": false,
    "willing_to_relocate": true,
    "preferred_locations": ["New York", "Remote"]
  },
  "employment": {
    "notice_period_days": 30,
    "notice_period_text": "30 days",
    "willing_to_work_remote": true,
    "willing_to_work_hybrid": true
  },
  "compensation": {
    "current_ctc_inr_lpa": 0,
    "expected_ctc_inr_lpa": 0,
    "open_to_negotiation": true
  },
  "experience": {
    "total_years": 3,
    "primary_role": "Software Engineer",
    "current_company": "Acme Corp"
  },
  "education": {
    "highest_degree": "B.S.",
    "field": "Computer Science",
    "university": "State University",
    "graduation_year": 2021
  },
  "compliance": {
    "background_check_consent": true,
    "drug_test_consent": true
  },
  "cover_letter": {
    "use_ai_generated": true,
    "tone": "professional and enthusiastic",
    "max_words": 150
  }
}
```

### 4. Add job URLs (`input/job_urls.json`)

Open `input/job_urls.json` and replace the sample entries with the LinkedIn Easy Apply job URLs you want to apply to.

> **Important:** Only add jobs that show the **Easy Apply** button on LinkedIn — other jobs cannot be automated.

```json
{
  "metadata": {
    "description": "LinkedIn Easy Apply URLs — only add Easy Apply jobs",
    "last_updated": "2025-01-15"
  },
  "jobs": [
    {
      "id": "job_001",
      "url": "https://www.linkedin.com/jobs/view/1234567890",
      "company": "Example Company",
      "title": "Software Engineer",
      "priority": "high",
      "notes": "Optional notes about this job"
    }
  ]
}
```

To find a job URL: open the job on LinkedIn → copy the URL from your browser's address bar.

---

## Running the bot

Once all configuration steps are complete, run:

```bash
python main.py
```

The bot will:
1. Validate your `.env` values
2. Parse your CV
3. Open a browser and log in to LinkedIn
4. Work through each job in `job_urls.json` one by one
5. Print a summary table when finished

Logs are saved to the `logs/` folder (one file per day).

---

## Dry-run mode (recommended for first use)

Set `DRY_RUN=true` in your `.env` file to let the bot fill in every form field **without** clicking the final Submit button. This is a safe way to verify everything looks correct before you start sending real applications.

```
DRY_RUN=true
```

Switch back to `DRY_RUN=false` when you're ready to apply for real.

---

## Project structure

```
LinkedinAutoApplier/
├── main.py                    # Entry point — run this
├── requirements.txt           # Python dependencies
├── .env.example               # Copy to .env and fill in your values
├── input/
│   ├── cv/                    # Place your CV PDF here
│   ├── job_urls.json          # List of LinkedIn Easy Apply URLs
│   └── user_preferences.json # Your personal details & preferences
├── logs/                      # Application logs (auto-created)
├── sessions/                  # Saved browser sessions (auto-created)
└── src/
    ├── auth/                  # LinkedIn login logic
    ├── browser/               # Playwright browser engine
    ├── cv_parser/             # PDF CV parser
    ├── detection/             # CAPTCHA detection & handling
    ├── form/                  # Form filling & AI answering
    ├── logger/                # Application result logger
    └── utils/                 # Shared helpers & constants
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Missing required environment variables` | Make sure you copied `.env.example` to `.env` and filled in all three required values. |
| `CV not found` | Check that your PDF is in `input/cv/` and that `CV_PATH` in `.env` matches the filename. |
| `Login failed` | Double-check `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` in `.env`. Also make sure 2FA is not enabled on your account, or log in manually first so a session is saved. |
| Browser doesn't open | Make sure you ran `playwright install chromium` and that `HEADLESS_MODE=false`. |
| CAPTCHA detected | The bot will pause and print a message — solve the CAPTCHA in the browser window manually and the bot will continue automatically. |
| API errors from Anthropic | Check that your `ANTHROPIC_API_KEY` is valid and that your account has available credits. |