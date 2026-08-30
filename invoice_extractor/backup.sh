#!/usr/bin/env bash
set -e

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_NAME="invoice_bot_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
BACKUP_PATH="$HOME/$BACKUP_NAME"

echo "=================================================="
echo "  Creating Full Invoice Bot Backup"
echo "=================================================="

cd "$WORKDIR"

# Ensure data directory exists
mkdir -p data

# Create compressed archive containing .env and data/
tar -czvf "$BACKUP_PATH" \
    --exclude="data/cleanup_archive" \
    --exclude="data/ocr" \
    --exclude="data/enhanced" \
    .env data/

echo "--------------------------------------------------"
echo "✅ Backup successfully created at:"
echo "   $BACKUP_PATH"
echo "   Size: $(du -h "$BACKUP_PATH" | cut -f1)"
echo ""
echo "To download this backup to your laptop, run this on your laptop:"
echo "  gcloud compute scp hermes-agent-workspace:$BACKUP_PATH ./ --zone=asia-southeast1-c"
echo "=================================================="
