# Telegram Receipt Extractor

This local bot receives receipt photos in Telegram, extracts the details with OpenAI vision, and appends them to an Excel workbook.

## Setup

1. Create a Telegram bot with `@BotFather`.
2. Copy this folder's environment template:

```powershell
Copy-Item .env.example .env
```

3. Edit `.env` and fill in your Telegram bot token:

```text
TELEGRAM_BOT_TOKEN=...
```

For OpenAI auth, choose one:

```text
OPENAI_API_KEY=...
```

or:

```text
OPENAI_BEARER_TOKEN=...
```

or, for short-lived OAuth/workload-identity tokens:

```text
OPENAI_TOKEN_COMMAND=your-command-that-prints-a-token
```

4. Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

5. Start the bot:

```powershell
python receipt_bot.py
```

6. In Telegram, open your bot and send `/start`, then send a receipt photo.

The Excel file will be created at:

```text
data/receipts.xlsx
```

## What It Extracts

The workbook has two sheets:

- `Receipts`: one row per receipt, including merchant, date, currency, subtotal, tax, total, payment method, category, confidence, and image path.
- `Items`: one row per detected receipt item.

## Privacy Note

Images are sent to OpenAI for extraction. The original receipt photos are also stored locally in `data/images/`.

## Auth Notes

Telegram bots still require a Telegram bot token from `@BotFather`; Telegram OAuth is not a replacement for that.

For OpenAI, this bot accepts either a normal OpenAI Platform API key, a bearer access token, or a command that prints a fresh bearer token. A normal ChatGPT login/subscription is not accepted by the OpenAI API. If your OAuth login is only a ChatGPT/Codex browser login, that token is not normally available to standalone Python programs.

## Optional Chat Lock

To prevent other people from using the bot, set:

```text
TELEGRAM_ALLOWED_CHAT_ID=your_chat_id
```

Send `/whoami` to the bot to see your chat ID.
