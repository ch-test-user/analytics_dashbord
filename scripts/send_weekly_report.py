#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.data import load_workbooks  # noqa: E402
from app_core.google_sheets import load_google_sheet  # noqa: E402
from app_core.metrics import add_derived_metrics  # noqa: E402
from app_core.weekly_email_report import build_weekly_email_report, save_report_html, send_email_report  # noqa: E402


def load_config():
    path = ROOT / "app.config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_local_streamlit_secrets():
    path = ROOT / ".streamlit" / "secrets.toml"
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def google_credentials_from_env_or_config(config):
    secret_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if secret_json:
        return json.loads(secret_json)
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH") or config.get("googleCredentialsPath")
    if credentials_path:
        path = Path(credentials_path).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        return str(path)
    return None


def load_report_data():
    config = load_config()
    spreadsheet_url = os.getenv("GOOGLE_SHEET_URL") or config.get("googleSheetUrl")
    if spreadsheet_url:
        credentials = google_credentials_from_env_or_config(config)
        return add_derived_metrics(load_google_sheet(spreadsheet_url, credentials))

    workbook = os.getenv("SOURCE_WORKBOOK") or config.get("sourceWorkbook")
    if workbook:
        return add_derived_metrics(load_workbooks([workbook], config.get("sourceSheet")))

    raise RuntimeError("No data source configured. Set GOOGLE_SHEET_URL or SOURCE_WORKBOOK.")


def recipients_from_env(value):
    value = value or os.getenv("REPORT_RECIPIENTS", "")
    return [email.strip() for email in value.split(",") if email.strip()]


def main():
    parser = argparse.ArgumentParser(description="Build and optionally send the Chef Hak's weekly email report.")
    parser.add_argument("--send", action="store_true", help="Send the email using SMTP environment variables.")
    parser.add_argument("--recipients", default="", help="Comma-separated recipient list. Defaults to REPORT_RECIPIENTS.")
    parser.add_argument("--output", default="artifacts/chef_haks_weekly_email_report.html", help="Path where the HTML report should be saved.")
    args = parser.parse_args()

    local_secrets = load_local_streamlit_secrets()
    for key, value in local_secrets.items():
        os.environ.setdefault(str(key), str(value))

    df = load_report_data()
    if df.empty:
        raise RuntimeError("Loaded data is empty; report was not generated.")

    report = build_weekly_email_report(df)
    output_path = save_report_html(report, ROOT / args.output)
    print(f"Saved report HTML: {output_path}")
    print(f"Subject: {report.subject}")
    print(f"Critical/Low rows: {len(report.action_rows)}")

    if args.send:
        recipients = recipients_from_env(args.recipients)
        send_email_report(report, recipients)
        print(f"Sent report to {len(recipients)} recipient(s).")


if __name__ == "__main__":
    main()
