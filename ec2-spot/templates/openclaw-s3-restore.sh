#!/usr/bin/env bash
set -euo pipefail
OPENCLAW_HOME="/opt/openclaw"
BACKUP_BUCKET="$1"
AWS_REGION="$2"
LOG_FILE="/var/log/openclaw-s3-restore.log"

mkdir -p "$OPENCLAW_HOME/.openclaw"
{
  echo "$(date -Iseconds) Starting restore from s3://$BACKUP_BUCKET/latest/"
  aws s3 sync "s3://$BACKUP_BUCKET/latest/" "$OPENCLAW_HOME/.openclaw/" --region "$AWS_REGION" --delete
  chown -R ec2-user:ec2-user "$OPENCLAW_HOME/.openclaw"
  restored_files_count="$(find "$OPENCLAW_HOME/.openclaw" -mindepth 1 -type f | wc -l || true)"
  if [ "${restored_files_count:-0}" -eq 0 ]; then
    echo "$(date -Iseconds) Restore completed, but no files were found in s3://$BACKUP_BUCKET/latest/ (bucket may be empty, e.g., on first deployment)"
  else
    echo "$(date -Iseconds) Restore complete; restored ${restored_files_count} file(s) from s3://$BACKUP_BUCKET/latest/"
  fi
  echo "$(date -Iseconds) Restore complete"
} >> "$LOG_FILE" 2>&1
