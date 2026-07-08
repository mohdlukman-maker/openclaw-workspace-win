# Invoice Extractor Transfer Guide

Use this guide to move Invoice Extractor to another OpenClaw Windows laptop.

## What Is Included

The prepared transfer package includes:

- Bot source code
- Python requirements
- Excel templates
- Invoice register, so running numbers continue correctly
- Generated invoice and procurement records
- Tests
- Setup helper script

The package does not include:

- `.env` with Telegram/OpenAI secrets
- Raw Telegram images
- OCR/temp enhanced images
- Logs
- Python cache files

## New Laptop Setup

1. Extract the zip into the new OpenClaw workspace, for example:

```powershell
C:\Users\<user>\.openclaw\workspace\invoice_extractor
```

2. Open PowerShell in the extracted `invoice_extractor` folder.

3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_transfer.ps1
```

4. Edit the new `.env` file and fill in:

```text
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
TELEGRAM_ALLOWED_CHAT_IDS=
```

Use `/whoami` from the Telegram bot if the new chat ID is different.

5. If local OCR is required, install Tesseract OCR on the new laptop and set this only if it is not already in PATH:

```text
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

6. Run verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile invoice_bot.py procurement.py pending_store.py retention.py suppliers.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe invoice_bot.py --init-workbook
```

7. Start the bot manually for a first check:

```powershell
.\.venv\Scripts\python.exe invoice_bot.py
```

8. After the manual check works, register the scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_transfer.ps1 -RegisterTask
```

## Scheduled Task

The setup script creates a scheduled task named:

```text
Invoice Extractor Bot
```

It starts when the Windows user logs in and runs:

```text
.\.venv\Scripts\python.exe invoice_bot.py
```

## Important

Only run one Invoice Extractor bot at a time with the same Telegram bot token. Before activating the new laptop, stop or disable the scheduled task on the old laptop to avoid duplicate Telegram polling.
