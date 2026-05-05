"""
Local scanner server for event-day QR verification.

Start with:  python backend/run.py  (MODE=scan)
Then open:   http://localhost:8080  in your browser.

The server reads and writes the CSV file at CSV_FILE_PATH from .env.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import attendance
import qr_generator

app = FastAPI()

_SCANNER_HTML = Path(__file__).parent / "template" / "scanner.html"


def _csv_path() -> str:
    path = os.getenv("CSV_FILE_PATH", "")
    if not path or not os.path.exists(path):
        raise RuntimeError(f"CSV file not found: {path!r}. Check CSV_FILE_PATH in .env")
    return path


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return _SCANNER_HTML.read_text(encoding="utf-8")


class ScanPayload(BaseModel):
    data: str  # raw string decoded from QR code


@app.post("/scan")
async def scan(payload: ScanPayload):
    parsed = qr_generator.parse_qr_data(payload.data)
    if parsed is None:
        return {"status": "invalid", "message": "Unrecognised QR code format."}

    email, token = parsed

    if not qr_generator.validate_token(email, token):
        return {"status": "invalid", "message": "QR code verification failed — possible forgery."}

    csv_path = _csv_path()
    result = attendance.mark_attended(csv_path, email)
    name = attendance.get_name(csv_path, email)

    if result == "ok":
        return {"status": "ok", "message": name, "email": email}
    if result == "already":
        return {"status": "already", "message": name, "email": email}
    return {"status": "not_found", "message": "Participant not found in CSV."}


@app.get("/stats")
async def stats():
    return attendance.get_stats(_csv_path())
