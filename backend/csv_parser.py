import csv
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _open_csv(path: str):
    for encoding in ("utf-8", "latin-1"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                f.read()
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path} as UTF-8 or latin-1.")


def parse(csv_path: str) -> tuple[list[dict], list[str]]:
    """
    Returns (valid_rows, errors).
    valid_rows: list of dicts with at least 'name' and 'email' keys.
    errors: list of human-readable strings describing skipped rows.
    """
    encoding = _open_csv(csv_path)
    valid_rows: list[dict] = []
    errors: list[str] = []

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
            cleaned = {k.strip().lower(): v.strip() for k, v in row.items() if k}

            name = cleaned.get("name", "")
            email = cleaned.get("email", "")

            if not name:
                errors.append(f"Row {i}: skipped — 'name' is empty.")
                continue
            if not email:
                errors.append(f"Row {i}: skipped — 'email' is empty.")
                continue
            if not EMAIL_RE.match(email):
                errors.append(f"Row {i}: skipped — invalid email '{email}'.")
                continue

            valid_rows.append(cleaned)

    return valid_rows, errors
