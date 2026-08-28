# Deploying Invoice Extractor 24/7 on Google Cloud

This guide explains how to deploy and run the Telegram Invoice Extractor bot 24/7 on a Google Cloud Compute Engine Linux VM (Ubuntu).

---

## 1. Create a Google Cloud VM Instance

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Navigate to **Compute Engine** > **VM instances**.
3. Click **Create Instance**:
   - **Name**: `invoice-bot-vm`
   - **Region / Zone**: Choose your nearest region (e.g. `asia-southeast1` Singapore, `us-central1`, etc.)
   - **Machine Configuration**:
     - Series: **E2**
     - Machine type: **e2-micro** (2 vCPU, 1 GB memory — eligible for GCP Free Tier) or **e2-small** (2 vCPU, 2 GB memory recommended for heavy OCR).
   - **Boot Disk**:
     - OS: **Ubuntu**
     - Version: **Ubuntu 24.04 LTS** or **22.04 LTS**
     - Size: **20 GB** (Standard Persistent Disk)
   - **Firewall**: No HTTP/HTTPS inbound traffic checkboxes are needed! Telegram bot uses outbound long-polling to Telegram servers.
4. Click **Create**.

---

## 2. Connect to the VM via SSH

In the Google Cloud Console VM list, click the **SSH** button next to your `invoice-bot-vm` instance.

A browser terminal will open.

---

## 3. Clone or Copy the Repository

Clone your GitHub repository to the server:

```bash
git clone https://github.com/mohdlukman-maker/invoice_extractor.git
cd invoice_extractor
```

*(Or if your repository is named differently, replace with your GitHub repository URL).*

---

## 4. Run the Automated GCP Setup Script

Make the setup script executable and run it:

```bash
chmod +x setup_gcp_server.sh
./setup_gcp_server.sh
```

The script will automatically:
1. Install Python 3, `tesseract-ocr`, and `libreoffice` (for Excel to PDF conversion).
2. Create the Python virtual environment (`.venv`) and install dependencies from `requirements.txt`.
3. Create `.env` from `.env.example`.
4. Initialize the data directories and run the automated test suite.
5. Create and enable the `invoice-bot` systemd service.

---

## 5. Configure Your Credentials (`.env`)

Open `.env` in `nano`:

```bash
nano .env
```

Fill in your secrets:

```text
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
OPENAI_API_KEY=sk-...
TELEGRAM_ALLOWED_CHAT_IDS=5037627395
```

Save and exit `nano` by pressing `Ctrl + O`, `Enter`, then `Ctrl + X`.

---

## 6. Start the 24/7 Service

Start the bot using systemd:

```bash
sudo systemctl start invoice-bot
```

Check the status to ensure it is active and running:

```bash
sudo systemctl status invoice-bot
```

You should see: `Active: active (running)`.

---

## 7. Useful Management Commands

### View Live Logs:
```bash
sudo journalctl -u invoice-bot -f
```

### Restart the Bot (e.g. after code update):
```bash
sudo systemctl restart invoice-bot
```

### Stop the Bot:
```bash
sudo systemctl stop invoice-bot
```

### Update Code from GitHub:
```bash
cd ~/invoice_extractor
git pull
sudo systemctl restart invoice-bot
```

---

## 8. Backup & File Retrieval

All generated invoices, procurement packages, and registers are saved on the server under:
- `~/invoice_extractor/data/invoices/`
- `~/invoice_extractor/data/PROCUREMENT/`
- `~/invoice_extractor/data/invoice_register.csv`

You can download files directly from the GCP browser SSH terminal using the **Download File** menu option in the top right gear icon, or via `gcloud compute scp`.
