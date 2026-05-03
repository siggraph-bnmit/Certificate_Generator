import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html.parser import HTMLParser

class _TextStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str):
        text = data.strip()
        if text:
            self._chunks.append(text)

    def get_text(self) -> str:
        return "\n".join(self._chunks)


def html_to_plaintext(html: str) -> str:
    stripper = _TextStripper()
    stripper.feed(html)
    return stripper.get_text()


def extract_subject(html: str) -> str:
    """Pull subject from <title> tag. Falls back to env var DEFAULT_SUBJECT."""
    import re
    match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return os.getenv("DEFAULT_SUBJECT", "Your Certificate")


def render_html(template: str, row: dict) -> str:
    """Replace {column} placeholders using a lowercase copy of the CSV row."""
    row_lower = {k.lower(): v for k, v in row.items()}
    try:
        return template.format_map(row_lower)
    except KeyError as e:
        raise ValueError(f"HTML template references column {e} not found in CSV.")


def _apply_priority_headers(msg: MIMEMultipart):
    """Adds high-importance flags recognised by Gmail, Outlook, and Apple Mail."""
    msg["X-Priority"] = "1"
    msg["X-MSMail-Priority"] = "High"
    msg["Importance"] = "High"

def send(
    smtp: smtplib.SMTP,
    sender: str,
    recipient_email: str,
    subject: str,
    html_body: str,
):
    """HTML mode — sends multipart/alternative with plain-text fallback."""
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = recipient_email
    msg["Subject"] = subject
    _apply_priority_headers(msg)

    plain = html_to_plaintext(html_body)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    smtp.sendmail(sender, recipient_email, msg.as_string())


def send_with_attachment(
    smtp: smtplib.SMTP,
    sender: str,
    recipient_email: str,
    subject: str,
    text_body: str,
    attachment_path: str,
    display_filename: str | None = None,
):
    """Attachment mode — sends plain-text body with a PDF attachment.

    display_filename overrides what the recipient sees as the attachment name.
    Useful when the on-disk path contains an internal uid suffix.
    """
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient_email
    msg["Subject"] = subject
    _apply_priority_headers(msg)

    msg.attach(MIMEText(text_body, "plain", "utf-8"))

    shown_name = display_filename or os.path.basename(attachment_path)
    with open(attachment_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{shown_name}"')
    msg.attach(part)

    smtp.sendmail(sender, recipient_email, msg.as_string())


def open_smtp_connection() -> smtplib.SMTP:
    address = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not address or not password:
        raise EnvironmentError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env"
        )
    smtp = smtplib.SMTP("smtp.gmail.com", 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(address, password)
    return smtp


def ensure_connected(smtp: smtplib.SMTP) -> smtplib.SMTP:
    """Returns the existing connection if alive, silently reconnects if dropped."""
    try:
        smtp.noop()
        return smtp
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPException, OSError):
        try:
            smtp.quit()
        except Exception:
            pass
        print("[INFO] SMTP connection lost — reconnecting…")
        return open_smtp_connection()


SEND_DELAY = float(os.getenv("SEND_DELAY_SECONDS", "1.5"))
