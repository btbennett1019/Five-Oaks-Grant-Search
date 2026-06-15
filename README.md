# Five Oaks RFP & Grant Opportunity Tracker

A professional RFP/grant tracking app for Five Oaks Ag Research and Education Center.

## What it does

- Searches Grants.gov for relevant RFPs.
- Monitors key federal, nonprofit, and private foundation grant pages.
- Tracks opening dates, closing dates, source URLs, funders, status, fit score, stage, owner, notes, match, and project idea.
- Provides a professional dashboard with priority cards, pipeline tracking, deadline view, export, and scan history.
- Runs daily scans using Windows Task Scheduler.
- Optional email alerts if you add email settings.

## Easiest way to run

1. Unzip this folder.
2. Double-click:

```text
START_APP_WINDOWS.bat
```

That will install what it needs and open the dashboard.

## Install automatic daily search

After you have opened the app once, double-click:

```text
INSTALL_DAILY_SCAN_WINDOWS.bat
```

This creates a Windows scheduled task that runs every day at 7:00 AM.

## Manual daily scan

Double-click:

```text
RUN_DAILY_SCAN_WINDOWS.bat
```

## Optional email alerts

1. Copy `.env.example` and rename the copy to `.env`.
2. Add your SMTP/email settings.
3. Run the daily scan.

If email settings are blank, the app still works; it just won’t send alerts.

## Data storage

The app stores everything in:

```text
grant_tracker.sqlite3
```

Use the **Export** tab in the app to download a CSV backup.

## App URL

When running locally, the app opens at something like:

```text
http://localhost:8501
```

This version is intentionally built for simplicity and reliability on your computer. A hosted team URL can be added later after the workflow is working locally.
