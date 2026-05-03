"""
Entry point — run with:  python backend/run.py

Modes (set MODE in .env):
  html        — sends personalised HTML email (subject from <title> tag)
  attachment  — generates a personalised PDF from a PPTX template and sends
                it as an attachment with a plain-text body from email_body.txt
"""
import os
import re
import signal
import sys
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import certificate_generator
import csv_parser
import log_manager
import mailer

_DIR = os.path.dirname(__file__)
HTML_TEMPLATE_PATH = os.path.join(_DIR, "template", "email_template.html")
EMAIL_BODY_PATH = os.path.join(_DIR, "template", "email_body.txt")
OUTPUT_DIR = os.path.join(_DIR, "output")


_shutdown_requested = False


def _handle_sigint(sig, frame):
    global _shutdown_requested
    _shutdown_requested = True
    print("\n[WARN] Interrupt received — will stop after current email completes.")
    print("[INFO] Re-run to resume from where you left off.")


signal.signal(signal.SIGINT, _handle_sigint)


def _preflight(mode: str, participants: list):
    errors = []

    if not os.getenv("GMAIL_ADDRESS"):
        errors.append("GMAIL_ADDRESS is not set in .env")
    if not os.getenv("GMAIL_APP_PASSWORD"):
        errors.append("GMAIL_APP_PASSWORD is not set in .env")

    if mode == "html":
        if not os.path.exists(HTML_TEMPLATE_PATH):
            errors.append(f"HTML template not found: {HTML_TEMPLATE_PATH}")
        elif participants:
            try:
                with open(HTML_TEMPLATE_PATH, encoding="utf-8") as f:
                    template = f.read()
                mailer.render_html(template, participants[0])
            except ValueError as e:
                errors.append(f"HTML template error: {e}")

    elif mode == "attachment":
        pptx_path = os.getenv("PPTX_TEMPLATE_PATH", "")
        if not pptx_path:
            errors.append("PPTX_TEMPLATE_PATH is not set in .env")
        elif not os.path.exists(pptx_path):
            errors.append(f"PPTX template not found: {pptx_path}")

        if not os.getenv("ATTACHMENT_SUBJECT", "").strip():
            errors.append("ATTACHMENT_SUBJECT is not set in .env")

        if not os.path.exists(EMAIL_BODY_PATH):
            errors.append(f"Email body file not found: {EMAIL_BODY_PATH}")
        elif participants:
            try:
                with open(EMAIL_BODY_PATH, encoding="utf-8") as f:
                    body = f.read()
                row_lower = {k.lower(): v for k, v in participants[0].items()}
                body.format_map(row_lower)
            except KeyError as e:
                errors.append(
                    f"email_body.txt references {{{e}}} which is not a CSV column."
                )

        try:
            import win32com.client  # noqa: F401
        except ImportError:
            errors.append("pywin32 is not installed. Run: pip install pywin32")

    if errors:
        print("[ERROR] Pre-flight checks failed:")
        for err in errors:
            print(f"        • {err}")
        sys.exit(1)

    print("[INFO] Pre-flight checks passed.")


def _load_html_template() -> str:
    with open(HTML_TEMPLATE_PATH, encoding="utf-8") as f:
        return f.read()


def _load_email_body() -> str:
    with open(EMAIL_BODY_PATH, encoding="utf-8") as f:
        return f.read()


def _run_html_mode(remaining: list, smtp, sender: str):
    template = _load_html_template()
    subject = mailer.extract_subject(template)
    print(f"[INFO] Subject : {subject}")

    total = len(remaining)
    sent_count = failed_count = 0

    print(f"[INFO] Starting send batch ({total} emails)…\n")

    for i, row in enumerate(remaining, start=1):
        if _shutdown_requested:
            print("[INFO] Stopping batch early.")
            break

        name = csv_parser.get_field(row, "name")
        email = csv_parser.get_field(row, "email")
        prefix = f"[{i}/{total}] {name} <{email}>"

        try:
            smtp = mailer.ensure_connected(smtp)
            html_body = mailer.render_html(template, row)
            mailer.send(smtp, sender, email, subject, html_body)
            log_manager.append(email, name, "sent")
            sent_count += 1
            print(f"  OK  {prefix}")
        except Exception as e:
            log_manager.append(email, name, "failed", str(e))
            failed_count += 1
            print(f" FAIL {prefix}  —  {e}")

        if i < total and not _shutdown_requested:
            time.sleep(mailer.SEND_DELAY)

    return sent_count, failed_count, smtp


def _run_attachment_mode(remaining: list, smtp, sender: str):
    pptx_path = os.getenv("PPTX_TEMPLATE_PATH")
    body_template = _load_email_body()
    subject = os.getenv("ATTACHMENT_SUBJECT", "Your Certificate of Participation")

    print(f"[INFO] PPTX template : {pptx_path}")
    print(f"[INFO] Subject       : {subject}")

    total = len(remaining)
    sent_count = failed_count = 0

    print(f"[INFO] Starting send batch ({total} emails)…\n")

    for i, row in enumerate(remaining, start=1):
        if _shutdown_requested:
            print("[INFO] Stopping batch early.")
            break

        name = csv_parser.get_field(row, "name")
        email = csv_parser.get_field(row, "email")
        prefix = f"[{i}/{total}] {name} <{email}>"

        # Clean display name shown to the recipient as the attachment filename
        display_name = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_") + ".pdf"

        pdf_path = None
        try:
            print(f"  ... {prefix}  generating PDF…", end="\r")
            pdf_path = certificate_generator.generate(pptx_path, OUTPUT_DIR, row)

            row_lower = {k.lower(): v for k, v in row.items()}
            body = body_template.format_map(row_lower)

            smtp = mailer.ensure_connected(smtp)
            mailer.send_with_attachment(
                smtp, sender, email, subject, body, pdf_path,
                display_filename=display_name,
            )
            log_manager.append(email, name, "sent")
            sent_count += 1
            print(f"  OK  {prefix}                    ")
        except Exception as e:
            log_manager.append(email, name, "failed", str(e))
            failed_count += 1
            print(f" FAIL {prefix}  —  {e}            ")
        finally:
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)

        if i < total and not _shutdown_requested:
            time.sleep(mailer.SEND_DELAY)

    return sent_count, failed_count, smtp


def main():
    mode = os.getenv("MODE", "html").strip().lower()
    if mode not in ("html", "attachment"):
        sys.exit(f"[ERROR] MODE must be 'html' or 'attachment', got '{mode}'.")

    csv_path = os.getenv("CSV_FILE_PATH", "")
    if not csv_path:
        sys.exit("[ERROR] CSV_FILE_PATH is not set in .env")
    if not os.path.exists(csv_path):
        sys.exit(f"[ERROR] CSV file not found: {csv_path}")

    print(f"[INFO] Mode : {mode}")
    print(f"[INFO] CSV  : {csv_path}")

    participants, parse_errors = csv_parser.parse(csv_path)

    if parse_errors:
        print("[WARN] Some rows were skipped:")
        for err in parse_errors:
            print(f"       {err}")

    if not participants:
        sys.exit("[ERROR] No valid participants found in CSV.")

    print(f"[INFO] {len(participants)} valid participant(s) found.")

    # Validate everything before touching SMTP
    _preflight(mode, participants)

    already_sent = log_manager.already_sent()
    remaining = [
        p for p in participants
        if csv_parser.get_field(p, "email").lower() not in already_sent
    ]
    skipped = len(participants) - len(remaining)

    if skipped:
        print(f"[INFO] Skipping {skipped} already-sent participant(s).")

    if not remaining:
        print("[INFO] All participants already sent to. Nothing to do.")
        return

    print("[INFO] Connecting to Gmail SMTP…")
    try:
        smtp = mailer.open_smtp_connection()
    except Exception as e:
        sys.exit(f"[ERROR] Could not connect to Gmail SMTP: {e}")

    sender = os.getenv("GMAIL_ADDRESS")

    if mode == "html":
        sent_count, failed_count, smtp = _run_html_mode(remaining, smtp, sender)
    else:
        sent_count, failed_count, smtp = _run_attachment_mode(remaining, smtp, sender)

    try:
        smtp.quit()
    except Exception:
        pass

    total = len(remaining)
    print(f"\n[DONE] Sent: {sent_count}  |  Failed: {failed_count}  |  Total: {total}")
    if failed_count:
        print("[INFO] Failed entries recorded in backend/sent_log.csv")
        print("[INFO] Re-run the same command to retry only failed participants.")


if __name__ == "__main__":
    main()
