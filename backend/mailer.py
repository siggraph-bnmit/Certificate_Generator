import os
import smtplib
import time
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
    """Replace all {column} placeholders using the CSV row values."""
    try:
        return template.format_map(row)
    except KeyError as e:
        raise ValueError(f"HTML template references column {e} not found in CSV.")


def send(
    smtp: smtplib.SMTP,
    sender: str,
    recipient_email: str,
    subject: str,
    html_body: str,
):
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = recipient_email
    msg["Subject"] = subject

    plain = html_to_plaintext(html_body)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

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


SEND_DELAY = float(os.getenv("SEND_DELAY_SECONDS", "1.5"))
