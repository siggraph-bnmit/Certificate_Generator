from __future__ import annotations

import hashlib
import hmac
import io
import os

import qrcode

QR_PREFIX = "SIGGRAPH2025"


def _secret() -> bytes:
    key = os.getenv("QR_SECRET_KEY", "")
    if not key:
        raise EnvironmentError("QR_SECRET_KEY is not set in .env")
    return key.encode()


def generate_token(email: str) -> str:
    """HMAC-SHA256 of lowercase email, truncated to 32 hex chars."""
    return hmac.new(
        _secret(),
        email.strip().lower().encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()[:32]


def validate_token(email: str, token: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    expected = generate_token(email)
    return hmac.compare_digest(expected, token)


def qr_to_bytes(email: str, token: str) -> bytes:
    """Returns raw PNG bytes of the QR code for use as a CID inline attachment."""
    payload = f"{QR_PREFIX}:{email}:{token}"
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def parse_qr_data(raw: str) -> tuple[str, str] | None:
    """
    Parses raw QR string into (email, token).
    Returns None if the format is invalid or prefix doesn't match.
    """
    parts = raw.strip().split(":")
    if len(parts) != 3 or parts[0] != QR_PREFIX:
        return None
    _, email, token = parts
    return email, token
