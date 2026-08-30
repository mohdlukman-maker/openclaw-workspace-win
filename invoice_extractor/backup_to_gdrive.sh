#!/usr/bin/env bash
set -e

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$HOME/backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_NAME="invoice_bot_backup_${TIMESTAMP}.tar.gz"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

echo "=================================================="
echo "  Invoice Bot Weekly Backup to Google Drive"
echo "  Timestamp: $TIMESTAMP"
echo "=================================================="

# 1. Create local compressed archive
cd "$WORKDIR"
tar -czvf "$BACKUP_PATH" \
    --exclude="data/cleanup_archive" \
    --exclude="data/ocr" \
    --exclude="data/enhanced" \
    .env data/

echo "Archive created: $BACKUP_PATH ($(du -h "$BACKUP_PATH" | cut -f1))"

# 2. Upload to Google Drive if rclone is configured
if command -v rclone &>/dev/null && rclone listremotes | grep -q "^gdrive:"; then
    echo "Uploading to Google Drive (gdrive:Invoice_Bot_Backups)..."
    rclone copy "$BACKUP_PATH" "gdrive:Invoice_Bot_Backups"
    echo "✅ Successfully uploaded to Google Drive folder 'Invoice_Bot_Backups'!"
    
    # Keep only last 8 weekly backups on Google Drive (2 months retention)
    # rclone delete --min-age 60d "gdrive:Invoice_Bot_Backups"
else
    echo "⚠️ rclone is not configured yet with a 'gdrive:' remote."
    echo "Run 'rclone config' once to connect your Google Drive."
fi

# 3. Clean up local backups older than 30 days
find "$BACKUP_DIR" -name "invoice_bot_backup_*.tar.gz" -mtime +30 -delete

echo "=================================================="
echo "Backup process finished."
