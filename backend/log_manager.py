import csv
import os
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(__file__), "sent_log.csv")
HEADERS = ["email", "name", "status", "timestamp", "error"]


def _ensure_log():
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADERS)


def already_sent() -> set[str]:
    """Returns set of emails that were successfully sent in a previous run."""
    _ensure_log()
    sent = set()
    with open(LOG_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "sent":
                sent.add(row["email"].strip().lower())
    return sent


def append(email: str, name: str, status: str, error: str = ""):
    _ensure_log()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            email,
            name,
            status,
            datetime.now().isoformat(timespec="seconds"),
            error,
        ])


def clear():
    with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(HEADERS)


def summary() -> dict:
    _ensure_log()
    entries = []
    with open(LOG_PATH, newline="", encoding="utf-8") as f:
        entries = list(csv.DictReader(f))
    sent = sum(1 for e in entries if e.get("status") == "sent")
    failed = sum(1 for e in entries if e.get("status") == "failed")
    return {"total": len(entries), "sent": sent, "failed": failed, "entries": entries}
