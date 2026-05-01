"""
Entry point — run with:  python backend/run.py
"""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import csv_parser
import log_manager
import mailer

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "template", "email_template.html"
)


def load_template() -> str:
    if not os.path.exists(TEMPLATE_PATH):
        sys.exit(
            f"[ERROR] HTML template not found at: {TEMPLATE_PATH}\n"
            "Place your email_template.html file in backend/template/ and re-run."
        )
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        return f.read()


def main():
    csv_path = os.getenv("CSV_FILE_PATH")
    if not csv_path:
        sys.exit("[ERROR] CSV_FILE_PATH is not set in .env")
    if not os.path.exists(csv_path):
        sys.exit(f"[ERROR] CSV file not found: {csv_path}")

    print(f"[INFO] Loading CSV: {csv_path}")
    participants, parse_errors = csv_parser.parse(csv_path)

    if parse_errors:
        print("[WARN] Some rows were skipped:")
        for err in parse_errors:
            print(f"       {err}")

    if not participants:
        sys.exit("[ERROR] No valid participants found in CSV.")

    print(f"[INFO] {len(participants)} valid participant(s) found.")

    template = load_template()
    subject = mailer.extract_subject(template)
    print(f"[INFO] Subject: {subject}")

    already_sent = log_manager.already_sent()
    remaining = [p for p in participants if p["email"] not in already_sent]
    skipped = len(participants) - len(remaining)

    if skipped:
        print(f"[INFO] Skipping {skipped} already-sent participant(s).")

    if not remaining:
        print("[INFO] All participants already sent to. Nothing to do.")
        return

    print(f"[INFO] Connecting to Gmail SMTP…")
    try:
        smtp = mailer.open_smtp_connection()
    except Exception as e:
        sys.exit(f"[ERROR] Could not connect to Gmail SMTP: {e}")

    sender = os.getenv("GMAIL_ADDRESS")
    total = len(remaining)
    sent_count = 0
    failed_count = 0

    print(f"[INFO] Starting send batch ({total} emails)…\n")

    for i, row in enumerate(remaining, start=1):
        name = row["name"]
        email = row["email"]
        prefix = f"[{i}/{total}] {name} <{email}>"

        try:
            html_body = mailer.render_html(template, row)
            mailer.send(smtp, sender, email, subject, html_body)
            log_manager.append(email, name, "sent")
            sent_count += 1
            print(f"  OK  {prefix}")
        except Exception as e:
            error_msg = str(e)
            log_manager.append(email, name, "failed", error_msg)
            failed_count += 1
            print(f" FAIL {prefix}  —  {error_msg}")

        if i < total:
            time.sleep(mailer.SEND_DELAY)

    smtp.quit()

    print(f"\n[DONE] Sent: {sent_count}  |  Failed: {failed_count}  |  Total: {total}")
    if failed_count:
        print("[INFO] Failed entries are recorded in backend/sent_log.csv")
        print("[INFO] Re-run the same command to retry only failed participants.")


if __name__ == "__main__":
    main()
