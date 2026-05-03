# Certificate Email Sender

Sends personalised emails to a list of participants from a CSV file via Gmail SMTP.
Supports two modes: **HTML email** and **PDF certificate attachment**.
No paid services. No frontend. Runs entirely from the command line.

---

## Folder Structure

```
certificate_generator/
├── .env                             
├── .env.example                      ← copy this to create .env
├── .gitignore
├── README.md
└── backend/
    ├── run.py                        
    ├── csv_parser.py                 
    ├── mailer.py                     
    ├── certificate_generator.py     
    ├── log_manager.py               
    ├── requirements.txt
    ├── sent_log.csv                  
    ├── output/                      
    └── template/
        ├── email_template.html      
        ├── email_body.txt            
        └── certificate.pptx         
```


## Gmail App Password Setup

1. Go to [myaccount.google.com](https://myaccount.google.com) → Security → 2-Step Verification → App passwords
2. Select **Mail** as the app, then click **Generate**
3. Copy the 16-character password shown — you will not see it again
4. Use this password as `GMAIL_APP_PASSWORD` in your `.env` file

---

## Setup

**Step 1 — Install dependencies**

```bash
cd backend
pip install -r requirements.txt
```

**Step 2 — Create your `.env` file**

Copy `.env.example` to `.env` at the project root and fill in your values:

```
GMAIL_ADDRESS=yourname@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
CSV_FILE_PATH=C:/path/to/your/participants.csv
MODE=html
```

**Step 3 — Prepare your CSV file**

The CSV must have at least these two columns (validated case-insensitively, any order):

| Column | Required | Description |
|--------|----------|-------------|
| `name` | Yes | Participant's name |
| `email` | Yes | Recipient's email address |

Any additional columns are optional. Their exact names (case-sensitive) become
available as placeholders in both the HTML template and the PPTX slide.

Example:

```csv
Name,Email,Role
Alice Smith,alice@example.com,Speaker
Bob Jones,bob@example.com,Attendee
```

Both UTF-8 and latin-1 encoded CSVs are supported automatically.

---

## Mode 1 — HTML Email (`MODE=html`)

**How it works:** Sends a fully-rendered HTML email. The subject is read from the
`<title>` tag of your HTML file. Each email also includes an auto-generated
plain-text fallback for better deliverability.

**Template location:** `backend/template/email_template.html`

A sample template is already provided. Replace it with your own design.

**Placeholders in the HTML** use single curly braces, lowercase:

```html
<title>Your Certificate of Participation</title>

<p>Dear {name},</p>
<p>Thank you for joining as a {role}.</p>
```

> Placeholder names are always lowercase regardless of CSV column casing.
> So `{name}` works whether your CSV column is `name`, `Name`, or `NAME`.

**`.env` settings for this mode:**

```
MODE=html
```

---

## Mode 2 — PDF Attachment (`MODE=attachment`)

**How it works:**
1. Opens your PPTX template in PowerPoint.
2. Replaces `{{ColumnName}}` placeholders with each participant's CSV values.
3. Exports the slide to PDF.
4. Sends the PDF as an email attachment with a plain-text body.
5. Deletes the local PDF after sending.

**PPTX template design:**
- Design your certificate slide in PowerPoint normally.
- Wherever you want the participant's name to appear, type `{{Name}}` exactly.
- Any other CSV column can be used the same way: `{{Role}}`, `{{Email}}`, etc.
- Placeholder names are **case-sensitive** — `{{Name}}` only matches a CSV
  column literally named `Name`.
- Set the path to your PPTX file in `.env` as `PPTX_TEMPLATE_PATH`.

**Email body:** Edit `backend/template/email_body.txt` with the message to send
alongside the attachment. Supports `{name}` substitution (always lowercase):

```
Hi {name},

Please find your certificate of participation attached.

Best regards,
The SIGGRAPH 2025 Team
```

**`.env` settings for this mode:**

```
MODE=attachment
PPTX_TEMPLATE_PATH=C:/path/to/certificate_template.pptx
ATTACHMENT_SUBJECT=Your Certificate of Participation — SIGGRAPH 2025
```

---

## Running

```bash
cd backend
python run.py
```


---

## Email Priority Flag

All emails (both modes) are sent with high-importance headers:

| Header | Value |
|--------|-------|
| `X-Priority` | `1` |
| `X-MSMail-Priority` | `High` |
| `Importance` | `High` |

This marks the email with the high-priority flag (red `!`) in Gmail and Outlook.

> Note: Priority headers improve visibility but do not guarantee inbox delivery.
> Gmail spam filters evaluate sender reputation and content, not just headers.

---

## Resuming an Interrupted Run

If the process stops mid-batch (crash, network drop, manual stop), re-run the
same command:

```bash
python run.py
```

The script reads `backend/sent_log.csv` on startup and skips every participant
already marked as `sent`. Only the remaining ones are attempted — no duplicates.

---

## Send Log

`backend/sent_log.csv` is created automatically on the first run:

```
email,name,status,timestamp,error
alice@example.com,Alice Smith,sent,2025-05-01T10:32:11,
carol@example.com,Carol White,failed,2025-05-01T10:32:15,SMTPException: ...
```

To reset the log and re-send to everyone:

- Delete `backend/sent_log.csv`, or
- Clear its contents — it will be recreated with headers on the next run

---

## All `.env` Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GMAIL_ADDRESS` | Yes | — | Gmail address to send from |
| `GMAIL_APP_PASSWORD` | Yes | — | 16-character Gmail App Password |
| `CSV_FILE_PATH` | Yes | — | Absolute path to your CSV file |
| `MODE` | Yes | `html` | `html` or `attachment` |
| `PPTX_TEMPLATE_PATH` | Attachment mode | — | Absolute path to your PPTX template |
| `ATTACHMENT_SUBJECT` | Attachment mode | `Your Certificate of Participation` | Email subject |
| `SEND_DELAY_SECONDS` | No | `1.5` | Seconds between sends |
| `DEFAULT_SUBJECT` | No | `Your Certificate` | Fallback if HTML `<title>` tag is missing |

---
