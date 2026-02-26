#!/bin/bash
# Auto-approve pending OpenClaw device pairing requests
# This is safe in dev environments with local-only access via SSM port forwarding
set -eu

OPENCLAW_HOME="${1:-.}"
COMPOSE_FILE="$OPENCLAW_HOME/docker-compose.yaml"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "OpenClaw compose file not found at $COMPOSE_FILE"
    exit 0
fi

cd "$OPENCLAW_HOME"

list_json=$(docker compose run --rm openclaw-cli devices list --json 2>/dev/null || true)
if [ -z "$list_json" ]; then
    echo "No device pairing data returned"
    exit 0
fi

request_ids=$(printf '%s\n' "$list_json" | jq -r '(.pending // [])[] | if type == "object" then (.requestId // .id // empty) else . end' 2>/dev/null || true)
if [ -z "$request_ids" ]; then
    echo "No pending device pairing requests to approve"
    exit 0
fi

# Extract all request IDs and approve them
echo "Auto-approving pending device pairing requests..."
printf '%s\n' "$request_ids" | while read -r request_id; do
    if [ -n "$request_id" ]; then
        echo "  Approving device pairing request: $request_id"
        docker compose run --rm openclaw-cli devices approve "$request_id" >/dev/null 2>&1 || echo "  Warning: Failed to approve $request_id"
    fi
done

echo "Done!"
