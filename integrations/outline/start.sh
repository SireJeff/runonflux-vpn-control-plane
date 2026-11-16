#!/bin/bash
# =============================================================================
# FluxVPN Outline Startup Script (Xray Multi-User)
# =============================================================================
# Uses Xray-core with Shadowsocks inbound for multi-user Outline support.
# Each user gets their own password and per-user traffic statistics.
# Called by entrypoint-wrapper.sh after successful deployment validation.
# =============================================================================

set -e

log_info() {
    echo -e "\033[0;32m[Outline]\033[0m $1"
}

log_error() {
    echo -e "\033[0;31m[Outline]\033[0m $1"
}

# Check if we were validated by the entrypoint wrapper
if [ "$FLUXVPN_VALIDATED" != "true" ]; then
    log_error "Container not validated by FluxVPN. Exiting."
    exit 1
fi

log_info "Starting Outline service (Xray multi-user)..."
log_info "Protocol: $FLUXVPN_PROTOCOL"
log_info "Deployment ID: $FLUXVPN_DEPLOYMENT_ID"

# Initialize telemetry sidecar
TELEMETRY_PORT="${TELEMETRY_PORT:-9094}"
source /usr/local/bin/telemetry_helpers.sh
init_telemetry
log_info "Telemetry initialized on port $TELEMETRY_PORT"

# Extract configuration from FLUXVPN_CONFIG
OUTLINE_PASSWORD=$(echo "$FLUXVPN_CONFIG" | jq -r '.password // empty')
OUTLINE_PORT=$(echo "$FLUXVPN_CONFIG" | jq -r '.port // 9443')
OUTLINE_METHOD=$(echo "$FLUXVPN_CONFIG" | jq -r '.method // "chacha20-ietf-poly1305"')

# Validate required fields
if [ -z "$OUTLINE_PASSWORD" ]; then
    log_error "No password found in configuration"
    exit 1
fi

log_info "Configuration loaded:"
log_info "  Method: $OUTLINE_METHOD"
log_info "  Port: $OUTLINE_PORT"

# Generate Xray config with initial user (sync daemon will replace with all users)
cat > /app/config.json << EOF
{
    "stats": {},
    "api": {"tag": "api", "services": ["StatsService"]},
    "policy": {
        "levels": {"0": {"statsUserUplink": true, "statsUserDownlink": true}},
        "system": {"statsInboundUplink": true, "statsInboundDownlink": true}
    },
    "inbounds": [
        {
            "tag": "ss",
            "port": ${OUTLINE_PORT},
            "protocol": "shadowsocks",
            "settings": {
                "method": "${OUTLINE_METHOD}",
                "password": "${OUTLINE_PASSWORD}",
                "clients": [
                    {"email": "initial", "password": "${OUTLINE_PASSWORD}", "method": "${OUTLINE_METHOD}"}
                ],
                "network": "tcp,udp"
            }
        },
        {
            "tag": "api",
            "port": 10085,
            "listen": "127.0.0.1",
            "protocol": "dokodemo-door",
            "settings": {}
        }
    ],
    "outbounds": [
        {"tag": "direct", "protocol": "freedom", "settings": {}}
    ],
    "routing": {
        "rules": [
            {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
        ]
    }
}
EOF

log_info "Xray config generated at /app/config.json"

# Start background user sync daemon
if [ -n "$INTERNAL_API_KEY" ]; then
    log_info "Starting user sync daemon..."
    /usr/local/bin/vpn_auth_sync.sh &
    SYNC_PID=$!
    log_info "Sync daemon started (PID: $SYNC_PID)"
fi

# Start Xray in restart loop (sync daemon can pkill to trigger reload)
log_info "Starting Xray - Outline mode (restart-loop mode)..."
while true; do
    # set -e is on: without '|| EXIT_CODE=$?' a failing xray kills the
    # whole container instead of being retried by this loop.
    EXIT_CODE=0
    xray run -c /app/config.json || EXIT_CODE=$?
    log_info "Xray exited with code $EXIT_CODE, restarting in 3s..."
    sleep 3
done
