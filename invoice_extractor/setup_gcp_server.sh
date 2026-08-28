#!/usr/bin/env bash
set -e

echo "=================================================="
echo "  Telegram Invoice Extractor - GCP Linux Setup"
echo "=================================================="

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="$(whoami)"

echo "[1/6] Installing system dependencies (Python, Tesseract OCR, LibreOffice)..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv tesseract-ocr libreoffice fonts-dejavu-core

echo "[2/6] Setting up Python virtual environment..."
cd "$WORKDIR"
if [ -d "venv" ]; then
    VENV_DIR="$WORKDIR/venv"
elif [ -d ".venv" ]; then
    VENV_DIR="$WORKDIR/.venv"
else
    python3 -m venv "$WORKDIR/.venv"
    VENV_DIR="$WORKDIR/.venv"
fi

echo "[3/6] Installing Python packages..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r requirements.txt

echo "[4/6] Checking environment configuration (.env)..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ">> Created .env from .env.example. Please edit .env with your TELEGRAM_BOT_TOKEN and GEMINI_API_KEY."
fi

echo "[5/6] Initializing data folders and running tests..."
"$VENV_DIR/bin/python" invoice_bot.py --init-workbook
"$VENV_DIR/bin/python" -m unittest discover -s tests -v

echo "[6/6] Configuring systemd 24/7 service..."
SERVICE_FILE="/etc/systemd/system/invoice-bot.service"

sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Telegram Invoice Extractor Bot (24/7)
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$WORKDIR
ExecStart=$VENV_DIR/bin/python invoice_bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable invoice-bot

echo "=================================================="
echo "Setup complete!"
echo "To start the bot now:"
echo "  sudo systemctl start invoice-bot"
echo ""
echo "To check live logs:"
echo "  sudo journalctl -u invoice-bot -f"
echo ""
echo "To check status:"
echo "  sudo systemctl status invoice-bot"
echo "=================================================="
