# CLAUDE.md — Certificate Generator & Email Dispatcher

> A no-cost, self-hosted system for generating personalized certificates from a CSV file and emailing them via Gmail SMTP. Built for college projects and small-to-medium events (up to ~400 participants).

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Folder Structure](#folder-structure)
5. [Core Modules](#core-modules)
6. [Data Flow](#data-flow)
7. [API Reference](#api-reference)
8. [Gmail SMTP Setup](#gmail-smtp-setup)
9. [Certificate Template Design](#certificate-template-design)
10. [Error Handling & Resilience](#error-handling--resilience)
11. [Frontend Behaviour](#frontend-behaviour)
12. [Environment Variables](#environment-variables)
13. [Running the Project](#running-the-project)
14. [Known Constraints](#known-constraints)
15. [Future Improvements](#future-improvements)

---

## Project Overview

This system allows an organiser to:

1. Upload a CSV file containing participant names and email addresses via a React frontend.
2. Automatically generate a personalised PDF/PNG certificate for each participant.
3. Send each certificate as an email attachment directly through Gmail SMTP.
4. Track send status in real time (via WebSocket) and persist a log so interrupted batches can be safely resumed without re-sending to already-processed participants.

All components run locally. There are no third-party email services, no paid APIs, and no external dependencies beyond open-source Python libraries and Node.js packages.

---

## Architecture

```
┌─────────────────────────────────────────┐
│              React Frontend              │
│  - CSV upload & validation              │
│  - Live progress via WebSocket          │
│  - Send log viewer (sent / failed)      │
└────────────────┬────────────────────────┘
                 │  HTTP + WebSocket
                 ▼
┌─────────────────────────────────────────┐
│           FastAPI Backend               │
│                                         │
│  ┌──────────┐  ┌──────────────────────┐ │
│  │ CSV      │  │  Send Log Manager    │ │
│  │ Parser   │  │  (sent_log.csv)      │ │
│  └────┬─────┘  └──────────┬───────────┘ │
│       │                   │             │
│  ┌────▼─────────────────┐ │             │
│  │  Certificate Engine  │ │             │
│  │  (Pillow / fpdf2)    │ │             │
│  └────┬─────────────────┘ │             │
│       │                   │             │
│  ┌────▼──────────────────▼───────────┐  │
│  │       Email Dispatcher            │  │
│  │  (smtplib + Gmail SMTP)           │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
                 │
                 ▼
         Gmail (port 587, TLS)
                 │
                 ▼
      Recipient's inbox (with attachment)
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | React + Vite | Fast dev server, no config overhead |
| Backend | Python 3.11 + FastAPI | Async support, easy routing, great for file handling |
| Certificate generation | Pillow (image) or fpdf2 (PDF) | Free, pure Python, no system dependencies |
| Email transport | Python `smtplib` + Gmail SMTP | Zero cost, no third-party service |
| Real-time progress | FastAPI WebSockets | Push send status to frontend without polling |
| CSV parsing | Python built-in `csv` module | No extra install needed |
| Send log | Flat-file `sent_log.csv` | Simple, portable, survives crashes |
| Styling | Tailwind CSS (CDN) | No build step required |

---

## Folder Structure

```
certificate-mailer/
│
├── backend/
│   ├── main.py                  # FastAPI app, routes, WebSocket
│   ├── certificate.py           # Certificate generation logic
│   ├── mailer.py                # Gmail SMTP email dispatch
│   ├── csv_parser.py            # CSV reading and validation
│   ├── log_manager.py           # sent_log.csv read/write
│   ├── template/
│   │   └── certificate_bg.png   # Your certificate background image
│   ├── fonts/
│   │   └── Roboto-Bold.ttf      # Font for name rendering
│   ├── output/                  # Temporary per-run certificate files
│   │   └── .gitkeep
│   ├── sent_log.csv             # Auto-created; tracks sent emails
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── CsvUploader.jsx  # Drag-and-drop CSV upload
│   │   │   ├── ProgressPanel.jsx # WebSocket-powered live feed
│   │   │   └── LogViewer.jsx    # Shows sent/failed summary
│   │   └── main.jsx
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── .env                         # Gmail credentials (never commit this)
├── .gitignore
└── CLAUDE.md                    # This file
```

---

## Core Modules

### `csv_parser.py`

Responsibilities:
- Read the uploaded CSV file.
- Validate that required columns (`name`, `email`) are present.
- Strip whitespace from all fields.
- Skip rows where name or email is empty.
- Detect and reject malformed email addresses (regex check).
- Return a clean list of dicts: `[{"name": "...", "email": "..."}, ...]`.

**Important:** The parser must handle both `UTF-8` and `latin-1` encodings. Many Excel-exported CSVs use `latin-1`. Try `UTF-8` first, fall back to `latin-1` on decode error.

---

### `certificate.py`

Responsibilities:
- Accept a participant name and an output file path.
- Open the certificate background template (`template/certificate_bg.png`).
- Dynamically calculate font size based on name length so long names never overflow.
- Center the name horizontally on the certificate at a pre-configured Y position.
- Save the output as a high-quality PNG (or PDF via fpdf2).

**Font scaling rule:**
```
base_font_size = 72
max_name_length = 20
if len(name) > max_name_length:
    font_size = int(base_font_size * (max_name_length / len(name)))
else:
    font_size = base_font_size
```

This prevents overflow without manual adjustment per participant.

**Thread safety:** Certificate generation is CPU-bound. Run it synchronously within the async dispatch loop (one at a time) or use `asyncio.run_in_executor` with a `ThreadPoolExecutor` for better throughput.

---

### `log_manager.py`

Responsibilities:
- On first run, create `sent_log.csv` with headers: `email, name, status, timestamp, error`.
- After every send attempt (success or failure), append a row immediately.
- On a new batch run, read existing log to build a set of already-sent emails.
- Skip any participant whose email appears in the log with `status = sent`.

This means the batch is **resumable**. If the process crashes at participant 150 of 300, re-running the same CSV will skip the first 150 and continue from 151.

**Log format:**
```
email,name,status,timestamp,error
alice@example.com,Alice Smith,sent,2024-06-01T10:32:11,
bob@example.com,Bob Jones,failed,2024-06-01T10:32:15,SMTPException: [Errno 111]
```

---

### `mailer.py`

Responsibilities:
- Connect to Gmail SMTP at `smtp.gmail.com:587` using `STARTTLS`.
- Authenticate with the Gmail address and App Password from `.env`.
- Compose a `MIMEMultipart` email with:
  - A plain-text body (improves deliverability versus attachment-only emails).
  - The certificate file attached as `application/octet-stream`.
- Send the email and return success/failure.
- Include `time.sleep(1.5)` between sends to avoid triggering Gmail's rate limiter.

**Why a plain-text body matters:** Emails with only an attachment and no body text are flagged as spam far more often. Even a two-sentence body message significantly improves inbox delivery.

---

### `main.py`

Responsibilities:
- `POST /upload` — Accept CSV file upload, parse it, return participant count and preview.
- `POST /send` — Trigger the send batch. Runs asynchronously. Pushes progress events over WebSocket.
- `GET /log` — Return the current contents of `sent_log.csv` as JSON.
- `DELETE /log` — Clear the send log (to allow a fresh re-run of the same CSV).
- `WS /ws/progress` — WebSocket endpoint. Emits one JSON event per participant:
  ```json
  { "email": "alice@example.com", "name": "Alice", "status": "sent", "index": 1, "total": 120 }
  ```

---

## Data Flow

```
1. User drags CSV onto the frontend upload zone.

2. Frontend validates the file is .csv before sending.

3. POST /upload → backend parses CSV → returns { count, preview: [...first 5 rows] }

4. User clicks "Generate & Send".

5. POST /send → backend starts async batch loop.
   For each participant:
     a. Check sent_log.csv → skip if already sent.
     b. Generate certificate → save to output/{sanitised_name}.png
     c. Send email via Gmail SMTP.
     d. Append result to sent_log.csv immediately.
     e. Push WebSocket event to frontend.
     f. Sleep 1.5 seconds.

6. Frontend WebSocket listener updates progress bar and status list in real time.

7. On completion, frontend shows summary: X sent, Y failed.
   Failed entries are shown with error reason.
```

---

## API Reference

### `POST /upload`

**Request:** `multipart/form-data` with field `file` (CSV).

**Response:**
```json
{
  "count": 42,
  "preview": [
    { "name": "Alice Smith", "email": "alice@example.com" },
    ...
  ],
  "errors": []
}
```

`errors` contains rows that were skipped due to invalid email format or missing fields.

---

### `POST /send`

**Request:** `application/json`
```json
{
  "subject": "Your Certificate of Participation",
  "body": "Hi {name}, please find your certificate attached. Congratulations!"
}
```

The `{name}` placeholder in the body is replaced per participant at send time.

**Response:** `202 Accepted` — actual progress arrives over WebSocket.

---

### `GET /log`

**Response:**
```json
{
  "total": 42,
  "sent": 40,
  "failed": 2,
  "entries": [
    { "email": "...", "name": "...", "status": "sent", "timestamp": "...", "error": "" },
    ...
  ]
}
```

---

### `DELETE /log`

Clears `sent_log.csv`. Use this to reset and re-send to all participants.

**Response:** `200 OK`

---

### `WS /ws/progress`

Connect once before clicking "Send". Receives a stream of JSON messages:
```json
{ "email": "alice@example.com", "name": "Alice Smith", "status": "sent", "index": 3, "total": 42 }
{ "email": "bob@example.com", "name": "Bob Jones", "status": "failed", "index": 4, "total": 42, "error": "..." }
{ "type": "done", "sent": 40, "failed": 2 }
```

The final `done` message signals the end of the batch.

---

## Gmail SMTP Setup

**Step 1 — Enable 2-Factor Authentication** on the Gmail account you want to send from. This is required for App Passwords.

**Step 2 — Generate an App Password:**
- Go to `myaccount.google.com` → Security → 2-Step Verification → App passwords.
- Select "Mail" and your device, then click Generate.
- Copy the 16-character password shown. **You will not see it again.**

**Step 3 — Add to `.env`:**
```
GMAIL_ADDRESS=yourname@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

**Step 4 — Never commit `.env`.** It is already in `.gitignore`.

**Gmail daily limits (free account):**
- ~500 emails per day to external recipients.
- If you exceed this, Gmail will silently stop sending. The mailer will log these as failures.
- For batches over 400, split across two days or two Gmail accounts.

---

## Certificate Template Design

The background image (`template/certificate_bg.png`) must be designed externally (e.g., Canva, Figma, Adobe Express — all free) and exported as a PNG.

**Recommended specs:**
- Resolution: 1920 × 1350 px (landscape A4 equivalent at 160 DPI).
- Leave a clearly defined blank area for the participant's name (horizontally centred, vertically in the middle-lower third).
- Avoid busy backgrounds behind the name zone — solid or lightly textured backgrounds render text most cleanly.
- Export at highest quality / 300 DPI if possible.

**Name placement configuration** (set once in `certificate.py`):
```python
NAME_Y_POSITION = 620      # Pixels from the top of the image
NAME_CENTRE_X = 960        # Horizontal centre (half of 1920px width)
BASE_FONT_SIZE = 72
FONT_COLOUR = (30, 30, 30) # Near-black RGB
```

Test with a few sample names of varying lengths (short: "Li Wei", long: "Bartholomew Raghunathan") before the real run.

---

## Error Handling & Resilience

These fixes are baked into the core architecture, not added later.

### 1. Crash Recovery via `sent_log.csv`

Every send result (success or failure) is written to `sent_log.csv` immediately after the attempt — before moving to the next participant. If the process is killed, a re-run of the same CSV will skip everyone already in the log with `status = sent`.

### 2. Per-Participant Try/Catch

The send loop wraps each participant in its own `try/except` block. One failed email does not stop the rest of the batch. The error message is captured and stored in the log.

### 3. Font Size Auto-Scaling

Pillow calculates `textbbox` after choosing the font size. If the rendered text width exceeds 80% of the certificate width, the font size is reduced by 4pt and recalculated, repeating until it fits. This handles all name lengths without manual tweaking.

### 4. CSV Encoding Fallback

The parser tries `UTF-8` first. On `UnicodeDecodeError`, it retries with `latin-1`. This handles CSVs exported from Excel, Google Sheets, and LibreOffice without modification.

### 5. Email Body + Attachment

Every email is sent with both a plain-text body and the certificate attachment. The body includes the participant's name (via `{name}` substitution) and a short message. This reduces spam scoring compared to attachment-only emails.

### 6. Rate Limiting Protection

`time.sleep(1.5)` is called after every successful send. This keeps the send rate well below Gmail's limits and avoids triggering temporary account-level throttling.

### 7. Duplicate Protection

`log_manager.py` builds a `set` of sent emails at the start of every batch run. The loop skips any participant whose email is already in the set. Re-uploading the same CSV (e.g., after a crash) will never result in duplicate emails.

### 8. Output File Cleanup

After each certificate is emailed, the local PNG/PDF file in `output/` is deleted to avoid disk accumulation across large runs.

---

## Frontend Behaviour

### CSV Upload Component

- Accepts drag-and-drop or file picker.
- Validates file extension (`.csv` only) client-side before uploading.
- Displays a preview table of the first 5 rows after upload.
- Shows a warning for any rows the backend flagged as invalid (missing name, bad email format).

### Progress Panel

- Opens a WebSocket connection to `/ws/progress` when the user clicks "Generate & Send".
- Renders a progress bar: `{sent + failed} / {total}`.
- Shows a scrollable live feed of each participant with a green ✓ (sent) or red ✗ (failed) icon.
- Failed entries expand to show the error reason on click.

### Log Viewer

- Calls `GET /log` on mount and after the batch completes.
- Shows a summary card: total sent, total failed.
- Allows downloading `sent_log.csv` directly for the organiser's records.
- Provides a "Reset Log" button that calls `DELETE /log`, with a confirmation dialog.

---

## Environment Variables

All secrets and configuration live in `.env` at the project root. Never commit this file.

```env
# Gmail credentials
GMAIL_ADDRESS=yourname@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Email content defaults (can be overridden from frontend)
DEFAULT_SUBJECT=Your Certificate of Participation
DEFAULT_BODY=Hi {name}, congratulations! Please find your certificate attached.

# Certificate settings
CERTIFICATE_TEMPLATE_PATH=template/certificate_bg.png
FONT_PATH=fonts/Roboto-Bold.ttf
OUTPUT_DIR=output/

# Backend
BACKEND_PORT=8000
FRONTEND_ORIGIN=http://localhost:5173
```

---

## Running the Project

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Gmail account with 2FA and an App Password configured (see Gmail Setup above)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

### requirements.txt

```
fastapi
uvicorn[standard]
pillow
fpdf2
python-multipart
python-dotenv
websockets
```

---

## Known Constraints

| Constraint | Detail |
|---|---|
| Gmail daily limit | ~500 emails/day on a free Gmail account |
| Localhost only | Both frontend and backend must run on the same machine unless you expose the backend with `ngrok` or deploy to a free tier service like Render |
| No database | State is stored in `sent_log.csv` — sufficient for this use case but not suitable for concurrent multi-user access |
| Spam risk | Emails from personal Gmail addresses may land in spam for some recipients. Plain-text body helps but does not fully eliminate this |
| Sequential sending | Emails are sent one at a time (with a sleep delay). 300 participants ≈ ~8 minutes total run time |
| Template is static | The certificate background is a fixed image. Dynamic data other than the name (e.g., course title, date) requires separate template variants or additional Pillow compositing logic |

---

## Future Improvements

These are out of scope for the initial college project but worth noting for future iterations:

- **Background job queue** (Celery + Redis) to make the send process non-blocking and properly async.
- **Multiple certificate templates** selectable from the frontend (e.g., different events).
- **CC or BCC field** to send a copy of all emails to the organiser.
- **SMTP provider swap** (e.g., Brevo free tier — 300 emails/day) for better deliverability than personal Gmail.
- **Deployment** to a free-tier cloud service (Render, Railway) so the frontend doesn't need to be on the same machine as the backend.
- **Preview mode** — generate a sample certificate for one participant without sending, to verify layout before the full run.
