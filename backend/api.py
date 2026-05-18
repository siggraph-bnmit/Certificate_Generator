"""
FastAPI REST API for the certificate generator.
Serves the React frontend and exposes all 4 modes as HTTP endpoints.

Run locally:  cd backend && uvicorn api:app --reload --port 8000
On Render:    uvicorn api:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import queue
import re
import shutil
import smtplib
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))

import attendance
import certificate_generator
import csv_parser
import log_manager
import mailer
import qr_generator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

_DIR = Path(__file__).parent
TEMPLATE_DIR = _DIR / "template"
OUTPUT_DIR   = _DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Certificate Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Supabase — CSV persistence for the attendance scanner
# ---------------------------------------------------------------------------

_SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_KEY", "")
_SUPABASE_BUCKET = os.getenv("SUPABASE_CSV_BUCKET", "scanner-csv")
_CSV_CACHE_PATH  = _DIR / "scanner_csv_cache.csv"

_supabase_client = None


def _get_supabase():
    global _supabase_client
    if _supabase_client is None and _SUPABASE_URL and _SUPABASE_KEY:
        from supabase import create_client
        _supabase_client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return _supabase_client


def _supabase_upload(key: str, data: bytes):
    """Upload bytes to Supabase Storage, overwriting if exists."""
    sb = _get_supabase()
    if not sb:
        return
    bucket = sb.storage.from_(_SUPABASE_BUCKET)
    try:
        bucket.upload(key, data)
    except Exception:
        try:
            bucket.update(key, data)
        except Exception:
            pass


def _supabase_download(key: str) -> bytes | None:
    """Download bytes from Supabase Storage. Returns None on failure."""
    sb = _get_supabase()
    if not sb:
        return None
    try:
        data = sb.storage.from_(_SUPABASE_BUCKET).download(key)
        return data if data else None
    except Exception:
        return None


def _push_csv_to_supabase(local_path: str):
    with open(local_path, "rb") as f:
        _supabase_upload("scanner.csv", f.read())


def _pull_csv_from_supabase() -> bool:
    data = _supabase_download("scanner.csv")
    if data:
        with open(_CSV_CACHE_PATH, "wb") as f:
            f.write(data)
        return True
    return False


def _upload_send_csv(content: bytes):
    """Store the send CSV in Supabase so any container can access it."""
    _supabase_upload("send.csv", content)


def _download_send_csv() -> str | None:
    """Download send.csv from Supabase into a temp file. Returns path or None."""
    data = _supabase_download("send.csv")
    if not data:
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    tmp.write(data)
    tmp.close()
    return tmp.name


def _get_scan_csv_path() -> str | None:
    """Returns the active CSV path for scanner ops: Supabase cache, then env var fallback."""
    if _CSV_CACHE_PATH.exists():
        return str(_CSV_CACHE_PATH)
    csv_path = os.getenv("CSV_FILE_PATH", "")
    return csv_path if csv_path and os.path.exists(csv_path) else None


@app.on_event("startup")
async def _on_startup():
    _pull_csv_from_supabase()


# ---------------------------------------------------------------------------
# Job state — one concurrent send job at a time
# ---------------------------------------------------------------------------

class _Job:
    def __init__(self):
        self.status     = "idle"   # idle | running | done | error
        self.sent       = 0
        self.failed     = 0
        self.total      = 0
        self.started_at = 0.0
        self._q: queue.Queue = queue.Queue()

    def emit(self, type_: str, message: str, **kw):
        self._q.put({"type": type_, "message": message, **kw})

    def finish(self):
        self._q.put(None)  # sentinel — tells SSE stream to close


_current_job: _Job = _Job()
_job_lock = threading.Lock()
_JOB_TIMEOUT = 30 * 60  # auto-reset after 30 min — guards against crashed threads

# ---------------------------------------------------------------------------
# Retry helper (mirrors run.py)
# ---------------------------------------------------------------------------

_RETRY_DELAYS = (5.0, 15.0)


def _send_with_retry(send_fn, label: str, emit):
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            send_fn()
            return None
        except (smtplib.SMTPException, OSError, ConnectionError) as e:
            if attempt < len(_RETRY_DELAYS):
                wait = _RETRY_DELAYS[attempt]
                emit("retry", f"RETRY [{attempt + 1}] {label} — {e}. Retrying in {wait:.0f}s…")
                time.sleep(wait)
            else:
                return e


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    return {
        "gmail_address":      os.getenv("GMAIL_ADDRESS", ""),
        "gmail_configured":   bool(os.getenv("GMAIL_APP_PASSWORD")),
        "mode":               os.getenv("MODE", "html"),
        "send_delay":         os.getenv("SEND_DELAY_SECONDS", "0.6"),
        "default_subject":    os.getenv("DEFAULT_SUBJECT", "Your Certificate"),
        "attachment_subject": os.getenv("ATTACHMENT_SUBJECT", ""),
        "qr_secret_set":      bool(os.getenv("QR_SECRET_KEY")),
        "pptx_template_set":  bool(os.getenv("PPTX_TEMPLATE_PATH")),
    }


# ---------------------------------------------------------------------------
# CSV upload and validation
# ---------------------------------------------------------------------------

@app.post("/api/validate-csv")
async def validate_csv(file: UploadFile = File(...)):
    content = await file.read()
    # Validate using a short-lived temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    try:
        tmp.write(content)
        tmp.close()
        rows, errors = csv_parser.parse(tmp.name)
        if errors:
            raise HTTPException(status_code=422, detail="; ".join(errors))
        # Store validated CSV in Supabase — any container can retrieve it for the send job
        _upload_send_csv(content)
        columns = list(rows[0].keys()) if rows else []
        return {
            "total":   len(rows),
            "columns": columns,
            "preview": rows[:5],
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Send job
# ---------------------------------------------------------------------------

@app.post("/api/reset-job")
def reset_job():
    global _current_job
    with _job_lock:
        _current_job = _Job()
    return {"status": "reset"}


@app.post("/api/send")
async def start_send(mode: str = Form("html")):
    global _current_job
    with _job_lock:
        # Auto-reset if job has been "running" for longer than the timeout
        if _current_job.status == "running":
            elapsed = time.time() - _current_job.started_at
            if elapsed < _JOB_TIMEOUT:
                raise HTTPException(status_code=409, detail="A send job is already running.")
        job = _Job()
        job.status = "running"
        job.started_at = time.time()
        _current_job = job

    def run():
        try:
            _execute_send(job, mode)
        except Exception as e:
            job.emit("error", f"Fatal: {e}")
        finally:
            if job.status == "running":
                job.status = "done"
            job.finish()

    threading.Thread(target=run, daemon=True).start()
    return {"started": True}


@app.get("/api/progress")
async def stream_progress():
    async def generate() -> AsyncGenerator[str, None]:
        loop = asyncio.get_event_loop()
        while True:
            try:
                event = await loop.run_in_executor(
                    None, lambda: _current_job._q.get(timeout=2)
                )
            except queue.Empty:
                yield 'data: {"type":"heartbeat"}\n\n'
                continue

            if event is None:
                payload = {
                    "type":   "done",
                    "sent":   _current_job.sent,
                    "failed": _current_job.failed,
                    "total":  _current_job.total,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                break

            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/job-status")
def job_status():
    return {
        "status":  _current_job.status,
        "sent":    _current_job.sent,
        "failed":  _current_job.failed,
        "total":   _current_job.total,
    }


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

@app.get("/api/logs")
def get_logs():
    log_path = _DIR / "sent_log.csv"
    if not log_path.exists():
        return []
    with open(log_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Scanner (merged from scanner_server.py)
# ---------------------------------------------------------------------------

class ScanPayload(BaseModel):
    data: str


@app.get("/scanner", response_class=HTMLResponse)
def scanner_ui():
    return (TEMPLATE_DIR / "scanner.html").read_text(encoding="utf-8")


@app.post("/api/upload-scan-csv")
async def upload_scan_csv(file: UploadFile = File(...)):
    """Upload the attendance CSV before an event-day scan session.
    Saves to local cache and syncs to Supabase Storage so it survives restarts.
    """
    with open(_CSV_CACHE_PATH, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        rows, _ = csv_parser.parse(str(_CSV_CACHE_PATH))
        if not rows:
            _CSV_CACHE_PATH.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail="CSV has no valid rows.")
        has_tracking = attendance.has_tracking_columns(str(_CSV_CACHE_PATH))
    except HTTPException:
        raise
    except ValueError as e:
        _CSV_CACHE_PATH.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))

    _push_csv_to_supabase(str(_CSV_CACHE_PATH))
    return {
        "total":         len(rows),
        "has_tokens":    has_tracking,
        "warning":       None if has_tracking else "CSV has no Token/Attended columns — run MODE=qr first.",
    }


@app.get("/api/scan-csv-status")
def scan_csv_status():
    csv_path = _get_scan_csv_path()
    if not csv_path:
        return {"loaded": False}
    stats = attendance.get_stats(csv_path)
    return {"loaded": True, **stats}


@app.post("/scan")
def scan_qr(payload: ScanPayload):
    csv_path = _get_scan_csv_path()
    if not csv_path:
        return {"status": "error", "message": "No scan CSV loaded. Upload one first."}

    parsed = qr_generator.parse_qr_data(payload.data)
    if not parsed:
        return {"status": "invalid", "message": "Unrecognised QR code."}

    email, token = parsed
    if not qr_generator.validate_token(email, token):
        return {"status": "invalid", "message": "Token validation failed."}

    result = attendance.mark_attended(csv_path, email)

    if result == "ok":
        _push_csv_to_supabase(csv_path)

    messages = {
        "ok":        f"Marked {email} as attended.",
        "already":   f"{email} already attended.",
        "not_found": f"{email} not found in CSV.",
    }
    return {"status": result, "message": messages.get(result, result)}


@app.get("/stats")
def get_stats():
    csv_path = _get_scan_csv_path()
    if not csv_path:
        return {"total": 0, "attended": 0, "absent": 0}
    return attendance.get_stats(csv_path)


# ---------------------------------------------------------------------------
# Core send execution (runs in background thread)
# ---------------------------------------------------------------------------

def _execute_send(job: _Job, mode: str):
    sender = os.getenv("GMAIL_ADDRESS")
    if not sender:
        job.emit("error", "GMAIL_ADDRESS not set in server environment.")
        return

    # Download CSV from Supabase into a short-lived temp file
    job.emit("info", "Fetching CSV from Supabase…")
    csv_path = _download_send_csv()
    if not csv_path:
        job.emit("error", "No CSV found in Supabase. Upload a CSV first.")
        return

    try:
        already_done = log_manager.already_sent("qr_sent" if mode == "qr" else "sent")
        attended_set = None
        if mode in ("html", "attachment") and attendance.has_tracking_columns(csv_path):
            attended_set = attendance.get_attended_emails(csv_path)

        remaining = 0
        try:
            for row in csv_parser.stream(csv_path):
                email = csv_parser.get_field(row, "email").lower()
                if attended_set is not None and email not in attended_set:
                    continue
                if email in already_done:
                    continue
                remaining += 1
        except Exception as e:
            job.emit("error", f"CSV error: {e}")
            return

        job.total = remaining
        job.emit("info", f"Starting {mode} batch — {remaining} email(s) to send.")

        if remaining == 0:
            job.emit("info", "Nothing to send (all already processed).")
            return

        def make_stream():
            for row in csv_parser.stream(csv_path):
                email = csv_parser.get_field(row, "email").lower()
                if attended_set is not None and email not in attended_set:
                    continue
                if email in already_done:
                    continue
                yield row

        try:
            smtp = mailer.open_smtp_connection()
            job.emit("info", "Connected to Gmail SMTP.")
        except Exception as e:
            job.emit("error", f"SMTP connection failed: {e}")
            return

        try:
            if mode == "html":
                _html_loop(job, make_stream, smtp, sender)
            elif mode == "qr":
                _qr_loop(job, make_stream, csv_path, smtp, sender)
            elif mode == "attachment":
                _attachment_loop(job, make_stream, smtp, sender)
            else:
                job.emit("error", f"Unknown mode: {mode}")
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
    finally:
        # Always clean up the temp CSV downloaded from Supabase
        try:
            os.unlink(csv_path)
        except OSError:
            pass

    job.emit("summary", f"Done — Sent: {job.sent} | Failed: {job.failed} | Total: {job.total}")


def _html_loop(job: _Job, stream_fn, smtp, sender: str):
    _smtp = [smtp]
    template = (TEMPLATE_DIR / "email_template.html").read_text("utf-8")
    subject  = mailer.extract_subject(template)

    for i, row in enumerate(stream_fn(), start=1):
        name  = csv_parser.get_field(row, "name")
        email = csv_parser.get_field(row, "email")
        label = f"[{i}/{job.total}] {name} <{email}>"

        try:
            html_body = mailer.render_html(template, row)

            def do_send(_e=email, _h=html_body):
                _smtp[0] = mailer.ensure_connected(_smtp[0])
                mailer.send(_smtp[0], sender, _e, subject, _h)

            err = _send_with_retry(do_send, label, job.emit)
            if err:
                raise err

            log_manager.append(email, name, "sent")
            job.sent += 1
            job.emit("ok", label)
        except Exception as e:
            log_manager.append(email, name, "failed", str(e))
            job.failed += 1
            job.emit("fail", f"{label} — {e}")

        if i < job.total:
            time.sleep(mailer.SEND_DELAY)


def _qr_loop(job: _Job, stream_fn, csv_path: str, smtp, sender: str):
    _smtp = [smtp]
    template = (TEMPLATE_DIR / "qr_email.html").read_text("utf-8")
    subject  = mailer.extract_subject(template)

    token_map = {
        csv_parser.get_field(r, "email").lower(): qr_generator.generate_token(
            csv_parser.get_field(r, "email")
        )
        for r in csv_parser.stream(csv_path)
    }
    attendance.add_tracking_columns(csv_path, token_map)

    for i, row in enumerate(stream_fn(), start=1):
        name  = csv_parser.get_field(row, "name")
        email = csv_parser.get_field(row, "email")
        label = f"[{i}/{job.total}] {name} <{email}>"

        try:
            token     = qr_generator.generate_token(email)
            qr_bytes  = qr_generator.qr_to_bytes(email, token)
            row_lower = {k.lower(): v for k, v in row.items()}
            html_body = template.format_map(row_lower)

            def do_send(_e=email, _h=html_body, _q=qr_bytes):
                _smtp[0] = mailer.ensure_connected(_smtp[0])
                mailer.send_with_inline_image(_smtp[0], sender, _e, subject, _h, _q)

            err = _send_with_retry(do_send, label, job.emit)
            if err:
                raise err

            log_manager.append(email, name, "qr_sent")
            job.sent += 1
            job.emit("ok", label)
        except Exception as e:
            log_manager.append(email, name, "qr_failed", str(e))
            job.failed += 1
            job.emit("fail", f"{label} — {e}")

        if i < job.total:
            time.sleep(mailer.SEND_DELAY)


def _attachment_loop(job: _Job, stream_fn, smtp, sender: str):
    _smtp = [smtp]
    pptx_path     = os.getenv("PPTX_TEMPLATE_PATH", "")
    body_template = (TEMPLATE_DIR / "email_body.txt").read_text("utf-8")
    subject       = os.getenv("ATTACHMENT_SUBJECT", "Your Certificate of Participation")

    SENTINEL  = object()
    pdf_queue: queue.Queue = queue.Queue(maxsize=2)

    def producer():
        for row in stream_fn():
            try:
                pdf_path = certificate_generator.generate(pptx_path, str(OUTPUT_DIR), row)
                pdf_queue.put((row, pdf_path, None))
            except Exception as e:
                pdf_queue.put((row, None, e))
        pdf_queue.put(SENTINEL)

    threading.Thread(target=producer, daemon=True).start()

    i = 0
    while True:
        item = pdf_queue.get()
        if item is SENTINEL:
            break

        i += 1
        row, pdf_path, gen_error = item
        name  = csv_parser.get_field(row, "name")
        email = csv_parser.get_field(row, "email")
        label = f"[{i}/{job.total}] {name} <{email}>"
        display_name = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_") + ".pdf"

        try:
            if gen_error:
                raise gen_error
            body = body_template.format_map({k.lower(): v for k, v in row.items()})

            def do_send(_e=email, _b=body, _p=pdf_path, _d=display_name):
                _smtp[0] = mailer.ensure_connected(_smtp[0])
                mailer.send_with_attachment(
                    _smtp[0], sender, _e, subject, _b, _p, display_filename=_d
                )

            err = _send_with_retry(do_send, label, job.emit)
            if err:
                raise err

            log_manager.append(email, name, "sent")
            job.sent += 1
            job.emit("ok", label)
        except Exception as e:
            log_manager.append(email, name, "failed", str(e))
            job.failed += 1
            job.emit("fail", f"{label} — {e}")
        finally:
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)

        if i < job.total:
            time.sleep(mailer.SEND_DELAY)
