#!/usr/bin/env bash
set -euo pipefail
OPENCLAW_HOME="/opt/openclaw"
BACKUP_BUCKET="$1"
AWS_REGION="$2"
LOG_FILE="/var/log/openclaw-s3-backup.log"

if [ ! -d "$OPENCLAW_HOME/.openclaw" ]; then
  echo "$(date -Iseconds) ERROR: $OPENCLAW_HOME/.openclaw does not exist" >> "$LOG_FILE" 2>&1
  exit 1
fi

{
  # Create timestamped snapshot (YYYY-MM-DD-HH-MM format in UTC)
  TIMESTAMP="$(date -u +%Y-%m-%d-%H-%M)"
  SNAPSHOT_PATH="snapshots/$TIMESTAMP"
  
  echo "$(date -Iseconds) Creating snapshot: s3://$BACKUP_BUCKET/$SNAPSHOT_PATH"
  aws s3 sync "$OPENCLAW_HOME/.openclaw/" "s3://$BACKUP_BUCKET/$SNAPSHOT_PATH/" --region "$AWS_REGION"
  
  echo "$(date -Iseconds) Updating latest: s3://$BACKUP_BUCKET/latest/"
  aws s3 sync "$OPENCLAW_HOME/.openclaw/" "s3://$BACKUP_BUCKET/latest/" --region "$AWS_REGION" --delete
  
  echo "$(date -Iseconds) Backup complete (snapshot: $SNAPSHOT_PATH)"
} >> "$LOG_FILE" 2>&1
