#!/bin/bash
# =============================================================================
# FluxVPN VLESS/Xray Startup Script (Multi-user Sync)
# =============================================================================
# Uses Xray-core which natively supports VLESS protocol with per-user stats
# Auth flow:
#   1. Starts with initial UUID from FLUXVPN_CONFIG
#   2. Background sync daemon fetches all active users periodically
#   3. Xray config is rebuilt with all user UUIDs + stats API
# =============================================================================

set -e

log_info() {
    echo -e "\033[0;32m[VLESS]\033[0m $1"
}

log_error() {
    echo -e "\033[0;31m[VLESS]\033[0m $1"
}

# Check if we were validated by the entrypoint wrapper
if [ "$FLUXVPN_VALIDATED" != "true" ]; then
    log_error "Container not validated by FluxVPN. Exiting."
    exit 1
fi

log_info "Starting VLESS service (multi-user sync, Xray engine)..."
log_info "Protocol: $FLUXVPN_PROTOCOL"
log_info "Deployment ID: $FLUXVPN_DEPLOYMENT_ID"

# Initialize telemetry sidecar
TELEMETRY_PORT="${TELEMETRY_PORT:-9092}"
source /usr/local/bin/telemetry_helpers.sh
init_telemetry
log_info "Telemetry initialized on port $TELEMETRY_PORT"

# Extract configuration from FLUXVPN_CONFIG
VLESS_UUID=$(echo "$FLUXVPN_CONFIG" | jq -r '.uuid // empty')
VLESS_PORT=$(echo "$FLUXVPN_CONFIG" | jq -r '.port // 443')
VLESS_PATH=$(echo "$FLUXVPN_CONFIG" | jq -r '.path // "/vless"')

# Validate required fields
if [ -z "$VLESS_UUID" ]; then
    log_error "No UUID found in configuration"
    exit 1
fi

log_info "Configuration loaded:"
log_info "  UUID: ${VLESS_UUID:0:8}..."
log_info "  Port: $VLESS_PORT"
log_info "  Path: $VLESS_PATH"

# Generate Xray config file with initial user
cat > /app/config.json << EOF
{
    "log": {
        "loglevel": "warning"
    },
    "inbounds": [
        {
            "port": $VLESS_PORT,
            "protocol": "vless",
            "settings": {
                "clients": [
                    {
                        "id": "$VLESS_UUID",
                        "level": 0
                    }
                ],
                "decryption": "none"
            },
            "streamSettings": {
                "network": "ws",
                "wsSettings": {
                    "path": "$VLESS_PATH"
                }
            }
        }
    ],
    "outbounds": [
        {
            "protocol": "freedom",
            "settings": {}
        }
    ]
}
EOF

log_info "Config file generated at /app/config.json (1 initial user)"

# Start background user sync daemon
if [ -n "$INTERNAL_API_KEY" ]; then
    log_info "Starting user sync daemon..."
    /usr/local/bin/vpn_auth_sync.sh &
    SYNC_PID=$!
    log_info "Sync daemon started (PID: $SYNC_PID)"
else
    log_info "WARNING: INTERNAL_API_KEY not set, sync daemon disabled"
fi

# Start Xray in a restart loop (so sync daemon can restart it without killing the container)
log_info "Starting xray (restart-loop mode)..."
while true; do
    # set -e is on: without '|| EXIT_CODE=$?' a failing xray kills the
    # whole container instead of being retried by this loop.
    EXIT_CODE=0
    xray run -c /app/config.json || EXIT_CODE=$?
    log_info "Xray exited with code $EXIT_CODE, restarting in 3s..."
    sleep 3
done
