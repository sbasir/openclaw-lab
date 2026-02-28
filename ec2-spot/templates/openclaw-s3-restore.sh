#!/usr/bin/env bash
set -euo pipefail
OPENCLAW_HOME="/opt/openclaw"
BACKUP_BUCKET="$1"
AWS_REGION="$2"
LOG_FILE="/var/log/openclaw-s3-restore.log"

openclaw_config() {
  if [ ! -f "$OPENCLAW_HOME/.openclaw/openclaw.json" ]; then
    cat > "$OPENCLAW_HOME/.openclaw/openclaw.json" <<-EOF
		{
			"gateway": {
				"controlUi": {
					"allowedOrigins": [
						"http://localhost:18789",
						"http://127.0.0.1:18789"
					]
				}
			}
		}
		EOF
  else
    echo "openclaw.json already exists, skipping creation to preserve existing configuration."
  fi
}

mkdir -p "$OPENCLAW_HOME/.openclaw"
{
  echo "$(date -Iseconds) Starting restore from s3://$BACKUP_BUCKET/latest/"
  aws s3 sync "s3://$BACKUP_BUCKET/latest/" "$OPENCLAW_HOME/.openclaw/" --region "$AWS_REGION" --delete
  openclaw_config # Ensure openclaw.json exists after restore (in case it was missing from backup, or to create it on first deployment)
  chown -R ec2-user:ec2-user "$OPENCLAW_HOME/.openclaw"
  restored_files_count="$(find "$OPENCLAW_HOME/.openclaw" -mindepth 1 -type f | wc -l || true)"
  if [ "${restored_files_count:-0}" -eq 0 ]; then
    echo "$(date -Iseconds) Restore completed, but no files were found in s3://$BACKUP_BUCKET/latest/ (bucket may be empty, e.g., on first deployment)"
  else
    echo "$(date -Iseconds) Restore complete; restored ${restored_files_count} file(s) from s3://$BACKUP_BUCKET/latest/"
  fi
  echo "$(date -Iseconds) Restore complete"



} >> "$LOG_FILE" 2>&1