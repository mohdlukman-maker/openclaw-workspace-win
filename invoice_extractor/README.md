# Telegram Invoice Extractor

This local bot receives paired TUJU Delivery Order and Tax Invoice photos in Telegram, uses AI-primary extraction with local OCR verification, compares both documents, replies with the matched item list for review, and saves each approved pair into its own Excel purchase-order and Material Requisition template workbooks.

The later document-formatting program can read each invoice workbook from `data/invoices/` and generate your fixed-format document.

## Setup

1. Create a Telegram bot with `@BotFather`.
2. Copy the environment template:

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

5. Optional but recommended for local OCR: install the Tesseract OCR engine for Windows and make sure `tesseract.exe` is in PATH. If it is not in PATH, set `TESSERACT_CMD` in `.env`.

```text
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

If Tesseract is not installed, the bot will still work by using AI extraction.

You can test local OCR without Telegram:

```powershell
python local_ocr_test.py data\images\your-invoice-photo.jpg
```

6. Create the invoice workbook folder:

```powershell
python invoice_bot.py --init-workbook
```

7. Start the bot:

```powershell
python invoice_bot.py
```

8. In Telegram, open your invoice bot and send `/start`, then send the D.O photo and the matching invoice photo.
9. Review the D.O/invoice comparison and extracted item numbers/descriptions in Telegram.
10. Send `/save` to write the invoice to Excel with the next automatic running number, `/editnothensave <number>` to choose the running number before saving, `/review` to show the extracted items again, or `/cancel` to discard that extraction.
   If that invoice's Excel file is open, the bot keeps the extracted invoice waiting, asks you to close the file, and retries automatically for about 15 minutes. You can also send `/save` again after closing Excel.
11. Invoices from chat IDs in `TELEGRAM_TEST_CHAT_IDS` are treated as testing by default and use `TEST BFE PO TUJU ...` filenames. Use `/saverecord` only when a testing sender's invoice should become an official record.
12. If the same Tax Invoice number already has an Excel file, the bot warns you before saving. Send `/save` again to save only additional/new item rows, `/saveall` to force saving all extracted rows, or `/cancel` to stop.
13. Use `/status` to check the bot configuration, latest save, PDF setting, OCR setting, template path, and pending-review state.
14. Use `/cleanup check` to preview old OCR/temp files that would be archived, or `/cleanup` to archive them immediately.
15. Use `/last` to resend the latest saved Excel/PDF invoice files.

Excel and PDF files will be created at:

```text
data/invoices/<SENDER CHAT ID>/BFE PO TUJU <CURRENT MONTH> <RUNNING NUMBER>.xlsx
data/invoices/<SENDER CHAT ID>/BFE PO TUJU <CURRENT MONTH> <RUNNING NUMBER>.pdf
data/invoices/<SENDER CHAT ID>/BFE PO TUJU <CURRENT MONTH> <RUNNING NUMBER> - MR.xlsx
data/invoices/<SENDER CHAT ID>/BFE PO TUJU <CURRENT MONTH> <RUNNING NUMBER> - MR.pdf
```

Example: `BFE PO TUJU JUNE 0001.xlsx`. The running number starts from `0001` again each month.
Each sender gets a separate local folder using their Telegram chat ID.

A procurement packet is also created at:

```text
data/PROCUREMENT/<SUPPLIER NAME>/<D.O OR INVOICE NUMBER>/<P.O FILE NAME>/
```

That folder contains:

```text
1. MR.pdf
2. PO.pdf
3. Invoice.pdf
4. D.O.pdf
```

The Invoice and D.O PDFs are converted from the original Telegram images used for the matched pair.
The extra P.O file-name level prevents repeated tests or re-saves of the same D.O/invoice number from overwriting older procurement packets.
The supplier folder is detected from extracted supplier/vendor text, document notes, or invoice prefixes. If no supplier can be detected, the bot falls back to `PROCUREMENT_SUPPLIER_NAME`, currently `TUJU GALAXY`.

Each successful save is also appended to:

```text
data/invoice_register.csv
```

The bot can be restricted to multiple approved Telegram chats by setting:

```text
TELEGRAM_ALLOWED_CHAT_IDS=5037627395,123456789
TELEGRAM_TEST_CHAT_IDS=5037627395
```

Ask a new user to send `/whoami` to the bot, then add the returned chat ID to this list. The register records the submitter chat ID and name for saved invoices.

## Workbook Sheet

- Each invoice workbook is created from `data/templates/purchase_order_template.xlsx` when `INVOICE_TEMPLATE_PATH` is set.
- The bot fills the `PURCHASEORDER` sheet from the matched pair: PR number at `J15` using the output filename, PO date at `J16` using D.O date minus four days, invoice number at `J17` using the invoice number, delivery order number at `J18` using the matching D.O number, person to contact at `H59` from the D.O, and item rows from rows `26` to `54`. If D.O date minus four days lands on Sunday, the bot moves the PO date back one more day to Saturday.
- Item columns: `B` Item, `C` Description, `G` Quantity with unit when visible, `H` Unit Price, and `J` Amount.
- The template keeps its existing formatting and total formula.
- When `EXPORT_PDF=1`, the bot exports the filled workbook to a matching PDF file after saving Excel.

## Material Requisition Sheet

- Each Material Requisition workbook is created from `data/templates/material_requisition_template.xlsx` when `MATERIAL_REQUISITION_TEMPLATE_PATH` is set.
- The bot fills the `MATERIAL REQUISITION` sheet: reference number at `N10` using the same P.O filename stem, date request at `N12` using P.O date minus two days, requested by at `D15` using the D.O contact person, and item rows from rows `19` to `40`.
- MR item columns: `B` No., `C` Description, `K` Quantity with unit, `L` Unit Price, and `N` Amount.
- The MR output file is saved beside the P.O as `<P.O filename> - MR.xlsx`, with a matching PDF when PDF export is enabled.

## Current Flow

1. Capture the TUJU Delivery Order and matching Tax Invoice using phone camera.
2. Upload both images to Telegram. The order can be D.O first or invoice first.
3. Bot downloads the image locally.
4. Bot prepares OCR-cleaned and table-friendly image variants.
5. When `AI_PRIMARY_ENABLED=1`, the bot sends full-page images plus TUJU header/details/contact/table crops to AI first.
6. Local OCR remains enabled as a verifier/log source, but it does not decide whether AI is allowed to run.
7. AI output is post-validated so unclear document numbers, dates, and contact fields are rejected instead of silently accepted.
8. Bot stores the first extracted document and asks for the matching D.O or invoice image.
9. After both documents are received, the bot compares D.O number vs invoice number, line items, quantities, and extra/missing rows.
10. The P.O payload uses D.O date/contact/items as the authority and fills invoice unit price/amount values from the invoice where the item rows match.
11. The pending pair is saved under `data/pending/<chat_id>.json`, so a bot restart does not lose the waiting D.O/invoice pair.
12. User reviews the comparison and sends `/save` only when the pair looks acceptable, or `/editnothensave <number>` when they need to choose the P.O running number manually. Testing senders can use `/saverecord` to save an official record instead of a test invoice.
13. Bot shows review warnings for missing fields, low confidence, reconciliation, pair mismatches, or amount mismatches.
14. Bot builds a safe Excel filename in the monthly PO format, such as `BFE PO TUJU JUNE 0001`.
15. Bot builds a new workbook from the configured Excel template.
16. Bot checks whether Excel has locked that invoice workbook, then saves the approved pair into the P.O template when the workbook is available.
17. Bot creates the matching Material Requisition workbook using the same P.O reference.
18. Bot exports the saved P.O and MR workbooks to PDFs. If PDF export fails, the Excel files remain saved and the bot reports the PDF error.
19. Bot creates the procurement packet folder and copies/converts the four required PDFs: MR, P.O, invoice image, and D.O image.
20. Bot clears the saved pending pair state after a successful save or `/cancel`.
21. Bot sends a copy of the generated file(s) back to the original Telegram sender.
22. Bot appends the save details to the invoice register.

## Supplier Routing

The procurement supplier folder defaults to:

```text
PROCUREMENT_SUPPLIER_NAME=TUJU GALAXY
```

You can add supplier aliases with JSON:

```text
SUPPLIER_ALIASES={"TUJU GALAXY":["tuju galaxy","tuju galaksi","tg-"]}
```

Each JSON key becomes the supplier folder name under `data/PROCUREMENT/`. Prefix-style aliases such as `tg-` match invoice numbers like `TG-K08849`.

## Cleanup / Retention

Startup cleanup is enabled by default and archives only generated OCR/temp files older than 30 days:

```text
CLEANUP_ENABLED=1
CLEANUP_RETENTION_DAYS=30
CLEANUP_ARCHIVE_DIR=./data/cleanup_archive
CLEANUP_TARGET_DIRS=./data/enhanced;./data/ocr
```

Raw Telegram images in `data/images/` and extraction JSON in `data/extractions/` are not part of the default cleanup target list.

## AI/OCR Settings

These optional `.env` values control the AI-primary flow:

```text
AI_PRIMARY_ENABLED=1
LOCAL_OCR_ENABLED=1
LOCAL_OCR_MIN_CONFIDENCE=70
LOCAL_OCR_MIN_ITEMS=1
TESSERACT_LANG=eng
TESSERACT_CONFIG=--oem 3 --psm 6
TUJU_PROFILE_ENABLED=1
```

Keep `LOCAL_OCR_ENABLED=1` when using AI-primary mode if you still want local OCR verification logs. Set `AI_PRIMARY_ENABLED=0` only if you want to return to the older local-OCR-first flow.

## Privacy Note

With AI-primary mode enabled, invoice photos and focused crops are sent to the configured AI provider for extraction. The original invoice photos are stored locally in `data/images/`, enhanced table crops in `data/enhanced/`, OCR-prepared images and text in `data/ocr/`, extraction cache entries in `data/extraction_cache/`, and raw extraction JSON in `data/extractions/`.
