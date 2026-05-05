"""
Entry point — run with:  python backend/run.py

Set MODE in .env before running:

  html        — personalised HTML email (subject from <title> tag)
  attachment  — personalised PDF from PPTX sent as attachment
                (producer-consumer pipeline: PDF generation overlaps with sending)
  qr          — HMAC QR codes emailed to all participants
  scan        — local scanner server at http://localhost:8080
"""
from __future__ import annotations

import os
import queue
import re
import signal
import smtplib
import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import attendance
import certificate_generator
import csv_parser
import log_manager
import mailer
import qr_generator

_DIR = os.path.dirname(__file__)
HTML_TEMPLATE_PATH = os.path.join(_DIR, "template", "email_template.html")
QR_TEMPLATE_PATH   = os.path.join(_DIR, "template", "qr_email.html")
EMAIL_BODY_PATH    = os.path.join(_DIR, "template", "email_body.txt")
OUTPUT_DIR         = os.path.join(_DIR, "output")

VALID_MODES    = ("html", "attachment", "qr", "scan")
_RETRY_DELAYS  = (5.0, 15.0)   # seconds between retry 1 and retry 2


# ---------------------------------------------------------------------------
# Graceful Ctrl+C — finish current email then stop
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _handle_sigint(sig, frame):
    global _shutdown_requested
    _shutdown_requested = True
    print("\n[WARN] Interrupt received — will stop after current email completes.")
    print("[INFO] Re-run to resume from where you left off.")


signal.signal(signal.SIGINT, _handle_sigint)


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

def _send_with_retry(send_fn, label: str):
    """
    Calls send_fn() up to 3 times (1 attempt + 2 retries).
    Only retries on transient SMTP / network errors.
    Returns None on success, the final exception on exhausted retries.
    """
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            send_fn()
            return None
        except (smtplib.SMTPException, OSError, ConnectionError) as e:
            if attempt < len(_RETRY_DELAYS):
                wait = _RETRY_DELAYS[attempt]
                print(f"\n  RETRY [{attempt + 1}/{len(_RETRY_DELAYS)}] {label}  —  {e}")
                print(f"         Retrying in {wait:.0f}s…")
                time.sleep(wait)
            else:
                return e


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------

def _preflight(mode: str, sample_row: dict | None):
    import shutil
    errors = []

    if mode in ("html", "attachment", "qr"):
        if not os.getenv("GMAIL_ADDRESS"):
            errors.append("GMAIL_ADDRESS is not set in .env")
        if not os.getenv("GMAIL_APP_PASSWORD"):
            errors.append("GMAIL_APP_PASSWORD is not set in .env")

    if mode == "html":
        if not os.path.exists(HTML_TEMPLATE_PATH):
            errors.append(f"HTML template not found: {HTML_TEMPLATE_PATH}")
        elif sample_row:
            try:
                with open(HTML_TEMPLATE_PATH, encoding="utf-8") as f:
                    mailer.render_html(f.read(), sample_row)
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
        elif sample_row:
            try:
                with open(EMAIL_BODY_PATH, encoding="utf-8") as f:
                    body = f.read()
                {k.lower(): v for k, v in sample_row.items()} and body.format_map(
                    {k.lower(): v for k, v in sample_row.items()}
                )
            except KeyError as e:
                errors.append(f"email_body.txt references {{{e}}} not in CSV.")
        if sys.platform == "win32":
            try:
                import win32com.client  # noqa: F401
            except ImportError:
                errors.append("pywin32 is not installed. Run: pip install pywin32")
        else:
            if not shutil.which("libreoffice"):
                errors.append("LibreOffice is not installed or not in PATH.")

    elif mode == "qr":
        if not os.getenv("QR_SECRET_KEY", ""):
            errors.append("QR_SECRET_KEY is not set in .env")
        if not os.path.exists(QR_TEMPLATE_PATH):
            errors.append(f"QR email template not found: {QR_TEMPLATE_PATH}")
        try:
            import qrcode  # noqa: F401
        except ImportError:
            errors.append("qrcode is not installed. Run: pip install qrcode[pil]")

    elif mode == "scan":
        if not os.getenv("QR_SECRET_KEY", ""):
            errors.append("QR_SECRET_KEY is not set in .env")
        csv_path = os.getenv("CSV_FILE_PATH", "")
        if csv_path and os.path.exists(csv_path):
            if not attendance.has_tracking_columns(csv_path):
                errors.append(
                    "CSV has no Token/Attended columns yet. Run MODE=qr first."
                )
        try:
            import uvicorn  # noqa: F401
        except ImportError:
            errors.append("uvicorn is not installed. Run: pip install uvicorn[standard]")

    if errors:
        print("[ERROR] Pre-flight checks failed:")
        for err in errors:
            print(f"        • {err}")
        sys.exit(1)

    print("[INFO] Pre-flight checks passed.")


# ---------------------------------------------------------------------------
# Template loader
# ---------------------------------------------------------------------------

def _load(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Send loops
# ---------------------------------------------------------------------------

def _run_html_mode(stream_fn, smtp, sender: str, total: int):
    template = _load(HTML_TEMPLATE_PATH)
    subject  = mailer.extract_subject(template)
    print(f"[INFO] Subject : {subject}")
    print(f"[INFO] Starting send batch ({total} emails)…\n")

    sent_count = failed_count = 0

    for i, row in enumerate(stream_fn(), start=1):
        if _shutdown_requested:
            print("[INFO] Stopping batch early.")
            break

        name   = csv_parser.get_field(row, "name")
        email  = csv_parser.get_field(row, "email")
        prefix = f"[{i}/{total}] {name} <{email}>"

        try:
            html_body = mailer.render_html(template, row)

            def do_send():
                nonlocal smtp
                smtp = mailer.ensure_connected(smtp)
                mailer.send(smtp, sender, email, subject, html_body)

            err = _send_with_retry(do_send, prefix)
            if err:
                raise err

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


def _run_attachment_mode(stream_fn, smtp, sender: str, total: int):
    """
    Producer-consumer pipeline.

    Producer thread:  streams rows → generates PDFs → puts into queue
    Consumer (main):  takes from queue → sends email with retry → deletes PDF

    Queue size of 2 means the producer stays at most 2 PDFs ahead of the
    consumer, bounding disk usage while keeping the pipeline busy.
    """
    pptx_path     = os.getenv("PPTX_TEMPLATE_PATH")
    body_template = _load(EMAIL_BODY_PATH)
    subject       = os.getenv("ATTACHMENT_SUBJECT", "Your Certificate of Participation")

    print(f"[INFO] PPTX template : {pptx_path}")
    print(f"[INFO] Subject       : {subject}")
    print(f"[INFO] Starting pipelined send batch ({total} emails)…\n")

    SENTINEL  = object()
    pdf_queue = queue.Queue(maxsize=2)

    def producer():
        for row in stream_fn():
            if _shutdown_requested:
                break
            try:
                pdf_path = certificate_generator.generate(pptx_path, OUTPUT_DIR, row)
                pdf_queue.put((row, pdf_path, None))
            except Exception as e:
                pdf_queue.put((row, None, e))
        pdf_queue.put(SENTINEL)

    prod_thread = threading.Thread(target=producer, daemon=True)
    prod_thread.start()

    sent_count = failed_count = i = 0

    while True:
        item = pdf_queue.get()
        if item is SENTINEL:
            if _shutdown_requested:
                print("[INFO] Stopping batch early.")
            break

        i += 1
        row, pdf_path, gen_error = item
        name   = csv_parser.get_field(row, "name")
        email  = csv_parser.get_field(row, "email")
        prefix = f"[{i}/{total}] {name} <{email}>"
        display_name = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_") + ".pdf"

        try:
            if gen_error:
                raise gen_error

            row_lower = {k.lower(): v for k, v in row.items()}
            body      = body_template.format_map(row_lower)

            def do_send():
                nonlocal smtp
                smtp = mailer.ensure_connected(smtp)
                mailer.send_with_attachment(
                    smtp, sender, email, subject, body, pdf_path,
                    display_filename=display_name,
                )

            err = _send_with_retry(do_send, prefix)
            if err:
                raise err

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

    prod_thread.join(timeout=30)
    return sent_count, failed_count, smtp


def _run_qr_mode(stream_fn, csv_path: str, smtp, sender: str, total: int):
    template = _load(QR_TEMPLATE_PATH)
    subject  = mailer.extract_subject(template)
    print(f"[INFO] Subject : {subject}")

    # Build token map from full CSV then write Token+Attended columns
    print("[INFO] Generating tokens…")
    token_map = {}
    for row in csv_parser.stream(csv_path):
        email = csv_parser.get_field(row, "email")
        token_map[email.lower()] = qr_generator.generate_token(email)
    attendance.add_tracking_columns(csv_path, token_map)
    print(f"[INFO] CSV updated with Token and Attended columns.")
    print(f"[INFO] Starting QR email batch ({total} emails)…\n")

    sent_count = failed_count = 0

    for i, row in enumerate(stream_fn(), start=1):
        if _shutdown_requested:
            print("[INFO] Stopping batch early.")
            break

        name   = csv_parser.get_field(row, "name")
        email  = csv_parser.get_field(row, "email")
        prefix = f"[{i}/{total}] {name} <{email}>"

        try:
            token    = qr_generator.generate_token(email)
            qr_bytes = qr_generator.qr_to_bytes(email, token)

            row_lower = {k.lower(): v for k, v in row.items()}
            html_body = template.format_map(row_lower)

            def do_send():
                nonlocal smtp
                smtp = mailer.ensure_connected(smtp)
                mailer.send_with_inline_image(
                    smtp, sender, email, subject, html_body, qr_bytes
                )

            err = _send_with_retry(do_send, prefix)
            if err:
                raise err

            log_manager.append(email, name, "qr_sent")
            sent_count += 1
            print(f"  OK  {prefix}")
        except Exception as e:
            log_manager.append(email, name, "qr_failed", str(e))
            failed_count += 1
            print(f" FAIL {prefix}  —  {e}")

        if i < total and not _shutdown_requested:
            time.sleep(mailer.SEND_DELAY)

    return sent_count, failed_count, smtp


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    mode = os.getenv("MODE", "html").strip().lower()
    if mode not in VALID_MODES:
        sys.exit(f"[ERROR] MODE must be one of {VALID_MODES}, got '{mode}'.")

    csv_path = os.getenv("CSV_FILE_PATH", "")
    if not csv_path:
        sys.exit("[ERROR] CSV_FILE_PATH is not set in .env")
    if not os.path.exists(csv_path):
        sys.exit(f"[ERROR] CSV file not found: {csv_path}")

    print(f"[INFO] Mode : {mode}")
    print(f"[INFO] CSV  : {csv_path}")

    # Scan mode — no CSV processing or SMTP needed
    if mode == "scan":
        _preflight(mode, None)
        import uvicorn
        from scanner_server import app as scanner_app
        print("[INFO] Starting scanner at http://localhost:8080")
        print("[INFO] Open this URL in your browser to begin scanning.\n")
        uvicorn.run(scanner_app, host="0.0.0.0", port=8080)
        return

    # Validate CSV headers and peek one row for preflight — O(1) memory
    try:
        sample_row = next(csv_parser.stream(csv_path), None)
    except ValueError as e:
        sys.exit(f"[ERROR] {e}")

    if sample_row is None:
        sys.exit("[ERROR] No valid participants found in CSV.")

    _preflight(mode, sample_row)

    # Build filter sets (all O(n) reads of small data, not full row objects)
    attended_set = None
    if mode in ("html", "attachment") and attendance.has_tracking_columns(csv_path):
        attended_set = attendance.get_attended_emails(csv_path)
        if not attended_set:
            sys.exit(
                "[ERROR] No attendees found.\n"
                "        Has the event been scanned? Run MODE=scan on event day."
            )

    skip_status = "qr_sent" if mode == "qr" else "sent"
    already_done = log_manager.already_sent(skip_status)

    # Single streaming pass to count total valid rows and remaining rows
    total_valid = 0
    remaining_total = 0
    for row in csv_parser.stream(csv_path):
        total_valid += 1
        email = csv_parser.get_field(row, "email").lower()
        if attended_set is not None and email not in attended_set:
            continue
        if email in already_done:
            continue
        remaining_total += 1

    print(f"[INFO] {total_valid} valid participant(s) found.")

    if attended_set is not None:
        absent  = total_valid - len(attended_set)
        skipped = len(attended_set) - remaining_total
        print(f"[INFO] Attendance filter active: {len(attended_set)} attendee(s).")
        if absent:
            print(f"[INFO] Skipping {absent} non-attendee(s).")
        if skipped:
            print(f"[INFO] Skipping {skipped} already-sent participant(s).")
    else:
        skipped = total_valid - remaining_total
        if skipped:
            print(f"[INFO] Skipping {skipped} already-sent participant(s).")

    if remaining_total == 0:
        print("[INFO] All participants already processed. Nothing to do.")
        return

    # Filtered stream factory — called by send loops; opens CSV fresh each time
    def make_stream():
        for row in csv_parser.stream(csv_path):
            email = csv_parser.get_field(row, "email").lower()
            if attended_set is not None and email not in attended_set:
                continue
            if email in already_done:
                continue
            yield row

    print("[INFO] Connecting to Gmail SMTP…")
    try:
        smtp = mailer.open_smtp_connection()
    except Exception as e:
        sys.exit(f"[ERROR] Could not connect to Gmail SMTP: {e}")

    sender = os.getenv("GMAIL_ADDRESS")

    if mode == "html":
        sent_count, failed_count, smtp = _run_html_mode(
            make_stream, smtp, sender, remaining_total
        )
    elif mode == "attachment":
        sent_count, failed_count, smtp = _run_attachment_mode(
            make_stream, smtp, sender, remaining_total
        )
    elif mode == "qr":
        sent_count, failed_count, smtp = _run_qr_mode(
            make_stream, csv_path, smtp, sender, remaining_total
        )

    try:
        smtp.quit()
    except Exception:
        pass

    print(f"\n[DONE] Sent: {sent_count}  |  Failed: {failed_count}  |  Total: {remaining_total}")
    if failed_count:
        print("[INFO] Failed entries recorded in backend/sent_log.csv")
        print("[INFO] Re-run the same command to retry only failed participants.")


if __name__ == "__main__":
    main()
