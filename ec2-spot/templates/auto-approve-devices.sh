#!/bin/bash
# Auto-approve pending OpenClaw device pairing requests
# This is safe in dev environments with local-only access via SSM port forwarding
set -eu

OPENCLAW_HOME="${1:-.}"
DEVICES_DIR="$OPENCLAW_HOME/.openclaw/devices"
PENDING_FILE="$DEVICES_DIR/pending.json"

if [ ! -f "$PENDING_FILE" ]; then
    echo "No pending device pairing requests found ($PENDING_FILE does not exist)"
    exit 0
fi

# Check if pending.json is empty or contains no requests
if ! jq -e '.[] | select(.id)' "$PENDING_FILE" >/dev/null 2>&1; then
    echo "No pending device pairing requests to approve"
    exit 0
fi

# Extract all request IDs and approve them
echo "Auto-approving pending device pairing requests..."
jq -r '.[] | select(.id) | .id' "$PENDING_FILE" | while read -r request_id; do
    if [ -n "$request_id" ]; then
        echo "  Approving device pairing request: $request_id"
        openclaw devices approve "$request_id" >/dev/null 2>&1 || echo "  Warning: Failed to approve $request_id"
    fi
done

echo "Done!"
