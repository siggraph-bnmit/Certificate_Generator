# Certificate Email Sender

Sends personalised emails to event participants via Gmail SMTP.
Supports four modes: HTML email, PDF certificate attachment, QR code distribution, and event-day attendance scanning.


## Folder Structure

```
certificate_generator/
├── .env                         
├── .env.example                  
├── .gitignore
├── README.md
└── backend/
    ├── run.py                    
    ├── csv_parser.py            
    ├── mailer.py                 
    ├── certificate_generator.py 
    ├── attendance.py             
    ├── qr_generator.py           
    ├── scanner_server.py        
    ├── log_manager.py           
    ├── requirements.txt
    ├── sent_log.csv              
    ├── output/                  
    └── template/
        ├── email_template.html  (MODE=html)
        ├── email_body.txt       (MODE=attachment)
        ├── qr_email.html        (MODE=qr)
        └── scanner.html         (MODE=scan)
```

---

## Prerequisites

- Python 3.9 or higher
- Microsoft PowerPoint installed (required for `MODE=attachment` on Windows)
- A Gmail account with **2-Factor Authentication** enabled
- A Gmail **App Password** (16 characters)

---

## Gmail App Password Setup

1. Go to [myaccount.google.com](https://myaccount.google.com) → Security → 2-Step Verification → App passwords
2. Select **Mail**, click **Generate**
3. Copy the 16-character password — you will not see it again
4. Use it as `GMAIL_APP_PASSWORD` in your `.env`

---

## Setup

**Step 1 — Install dependencies**

```bash
cd backend
pip install -r requirements.txt
```

**Step 2 — Create your `.env` file**

```bash
cp .env.example .env
```

---

## CSV File Format

The CSV must have at least these two columns (case-insensitive, any order):

| Column | Required | Description |
|--------|----------|-------------|
| `name` | Yes | Participant's name |
| `email` | Yes | Recipient's email address |

Any extra columns are optional. Their exact names (case-sensitive) become placeholders in your templates.

```csv
Name,Email,Role
Alice Smith,alice@example.com,Speaker
Bob Jones,bob@example.com,Attendee
```

Both UTF-8 and latin-1 encodings are detected and handled automatically.

> **After running `MODE=qr`**, the script adds two columns to this same file:
> `Token`  and `Attended` (True/False). Do not delete them.

---

## Full Event Workflow

This is the intended end-to-end sequence for using all four modes together:

```
BEFORE EVENT          EVENT DAY           AFTER EVENT
─────────────         ─────────           ───────────
MODE=qr               MODE=scan           MODE=html
                                      or  MODE=attachment
Send QR codes    →    Scan at         →   Send certificates
to all                entrance,           only to those who
participants          mark attended        attended
```

**Step by step:**

1. Upload your CSV (`Name`, `Email` columns).
2. Run `MODE=qr` — each participant receives an email with their unique QR code. The CSV gains `Token` and `Attended=False` columns.
3. On event day, run `MODE=scan` — opens `http://localhost:8080`. Scan each attendee's QR at the entrance. Their `Attended` column is set to `True`.
4. After the event, run `MODE=html` or `MODE=attachment` — certificates are sent only to participants where `Attended=True`. Non-attendees are skipped automatically.

---

## Mode 1 — HTML Email (`MODE=html`)

Sends a personalised HTML email to each participant.

**Template:** `backend/template/email_template.html`
A sample template is already provided — replace with your own design.

```
MODE=html
```

---

## Mode 2 — PDF Attachment (`MODE=attachment`)

Generates a personalised PDF certificate from a PowerPoint template and sends it as an email attachment.

**How it works:**
1. Opens your PPTX template.
2. Replaces `{{ColumnName}}` placeholders with each participant's CSV values.
3. Exports to PDF via PowerPoint COM automation.
4. Sends the PDF as an attachment with a plain-text body from `email_body.txt`.
5. Deletes the local PDF after sending.


```
MODE=attachment
PPTX_TEMPLATE_PATH=C:/path/to/certificate_template.pptx
ATTACHMENT_SUBJECT=Your Certificate of Participation — SIGGRAPH 2025
```

---

## Mode 3 — QR Code Distribution (`MODE=qr`)

Generates a unique, tamper-proof QR code per participant and emails it to them.

**How it works:**
1. Computes an HMAC-SHA256 token for each email address using `QR_SECRET_KEY`.
2. Adds `Token` and `Attended=False` columns to your CSV file (in-place).
3. Sends each participant an HTML email with their QR code embedded inline.

```
MODE=qr
QR_SECRET_KEY=your-long-random-secret-here
```

Generate a strong secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> Keep `QR_SECRET_KEY` the same value for both `MODE=qr` and `MODE=scan`. If they differ, every scan will fail verification.

---

## Mode 4 — Event Day Scanner (`MODE=scan`)

Starts a local web server for scanning QR codes at the event entrance via webcam.

**How it works:**
1. Opens a scanner interface at `http://localhost:8080`.
2. The webcam continuously scans for QR codes.
3. On a valid scan: validates the HMAC token, marks `Attended=True` in the CSV.
4. Gives instant visual and audio feedback.

**Scanner UI features:**
- Green flash + beep for a new valid scan
- Yellow flash for an already-marked participant
- Red flash for an invalid or unrecognised QR
- Running count of attended / total / absent
- Scrollable log of recent scans with timestamps

```
MODE=scan
QR_SECRET_KEY=your-long-random-secret-here   ← must match the key used in MODE=qr
CSV_FILE_PATH=C:/path/to/participants.csv
```

---

## Running

```bash
cd backend
python run.py
```

---

## All `.env` Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GMAIL_ADDRESS` | Yes | — | Gmail address to send from |
| `GMAIL_APP_PASSWORD` | Yes | — | 16-character Gmail App Password |
| `CSV_FILE_PATH` | Yes | — | Absolute path to your CSV file |
| `MODE` | Yes | `html` | `html`, `attachment`, `qr`, or `scan` |
| `PPTX_TEMPLATE_PATH` | `attachment` only | — | Absolute path to PPTX template |
| `ATTACHMENT_SUBJECT` | `attachment` only | `Your Certificate of Participation` | Email subject |
| `QR_SECRET_KEY` | `qr` + `scan` | — | secret — must be identical in both modes |
| `SEND_DELAY_SECONDS` | No | `0.6` | Seconds between sends (Gmail limit: ~100/min) |

---

