"""
Manages the attendance state inside the original CSV file.

After QR generation the CSV gains two extra columns:
  Token    — HMAC token used to verify the QR code
  Attended — "True" or "False"

All reads and writes go through this module.
"""

import csv
import os

TOKEN_COL = "Token"
ATTENDED_COL = "Attended"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read(path: str) -> tuple[list[str], list[dict]]:
    for encoding in ("utf-8", "latin-1"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                rows = [dict(r) for r in reader]
            return fieldnames, rows
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path}")


def _write(path: str, fieldnames: list[str], rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _email_of(row: dict) -> str:
    for k, v in row.items():
        if k.lower() == "email":
            return v.strip().lower()
    return ""


def _name_of(row: dict) -> str:
    for k, v in row.items():
        if k.lower() == "name":
            return v.strip()
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def has_tracking_columns(csv_path: str) -> bool:
    """Returns True if the CSV already has Token and Attended columns."""
    fieldnames, _ = _read(csv_path)
    return TOKEN_COL in fieldnames and ATTENDED_COL in fieldnames


def add_tracking_columns(csv_path: str, token_map: dict[str, str]):
    """
    Adds Token and Attended columns to the CSV in-place.
    token_map: {lowercase_email: token}
    Safe to call multiple times — won't overwrite existing tokens.
    """
    fieldnames, rows = _read(csv_path)

    if TOKEN_COL not in fieldnames:
        fieldnames.append(TOKEN_COL)
    if ATTENDED_COL not in fieldnames:
        fieldnames.append(ATTENDED_COL)

    for row in rows:
        email = _email_of(row)
        if not row.get(TOKEN_COL):
            row[TOKEN_COL] = token_map.get(email, "")
        if not row.get(ATTENDED_COL):
            row[ATTENDED_COL] = "False"

    _write(csv_path, fieldnames, rows)


def mark_attended(csv_path: str, email: str) -> str:
    """
    Marks a participant as attended.
    Returns one of: 'ok', 'already', 'not_found'.
    """
    fieldnames, rows = _read(csv_path)

    found = False
    already = False

    for row in rows:
        if _email_of(row) == email.strip().lower():
            found = True
            if row.get(ATTENDED_COL, "False").strip() == "True":
                already = True
            else:
                row[ATTENDED_COL] = "True"
            break

    if not found:
        return "not_found"
    if already:
        return "already"

    _write(csv_path, fieldnames, rows)
    return "ok"


def get_name(csv_path: str, email: str) -> str:
    """Returns the participant's name for a given email, or the email itself."""
    _, rows = _read(csv_path)
    for row in rows:
        if _email_of(row) == email.strip().lower():
            return _name_of(row) or email
    return email


def get_attended_emails(csv_path: str) -> set[str]:
    """Returns the set of lowercase emails where Attended == True."""
    _, rows = _read(csv_path)
    return {
        _email_of(row)
        for row in rows
        if row.get(ATTENDED_COL, "False").strip() == "True"
    }


def get_stats(csv_path: str) -> dict:
    _, rows = _read(csv_path)
    total = len(rows)
    attended = sum(1 for r in rows if r.get(ATTENDED_COL, "False").strip() == "True")
    return {"total": total, "attended": attended, "absent": total - attended}
