from __future__ import annotations

import csv
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _open_csv(path: str) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                f.read()
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path} as UTF-8 or latin-1.")


def get_field(row: dict, field: str) -> str:
    """Case-insensitive field lookup. Returns empty string if not found."""
    for k, v in row.items():
        if k.lower() == field.lower():
            return v
    return ""


def stream(csv_path: str, *, _errors: list | None = None):
    """
    Generator that yields one valid row dict at a time.

    Column-name casing is preserved exactly as in the CSV header — required
    for PPTX {{Placeholder}} matching which is case-sensitive.

    Invalid rows (empty name/email, bad email format) are skipped.
    If _errors list is supplied, error messages are appended there instead
    of being printed — used by parse() for backward compatibility.
    """
    encoding = _open_csv(csv_path)

    with open(csv_path, newline="", encoding=encoding) as f:
        reader = csv.DictReader(f)

        headers = reader.fieldnames
        if not headers:
            raise ValueError("CSV file is empty or has no headers.")

        headers_lower = [h.strip().lower() for h in headers]
        if "name" not in headers_lower:
            raise ValueError("CSV is missing required column: 'name'.")
        if "email" not in headers_lower:
            raise ValueError("CSV is missing required column: 'email'.")

        for i, row in enumerate(reader, start=2):
            cleaned = {k.strip(): v.strip() for k, v in row.items() if k}

            name  = get_field(cleaned, "name")
            email = get_field(cleaned, "email")

            def _skip(msg: str):
                if _errors is not None:
                    _errors.append(msg)
                else:
                    print(f"[WARN] {msg}")

            if not name:
                _skip(f"Row {i}: skipped — 'name' is empty.")
                continue
            if not email:
                _skip(f"Row {i}: skipped — 'email' is empty.")
                continue
            if not EMAIL_RE.match(email):
                _skip(f"Row {i}: skipped — invalid email '{email}'.")
                continue

            yield cleaned


def count_valid(csv_path: str) -> int:
    """Returns the number of valid rows without loading them all into memory."""
    return sum(1 for _ in stream(csv_path))


def parse(csv_path: str) -> tuple[list[dict], list[str]]:
    """
    Backward-compatible loader. Returns (valid_rows, errors).
    Internally uses stream() — no duplicate parsing logic.
    """
    errors: list[str] = []
    rows = list(stream(csv_path, _errors=errors))
    return rows, errors
