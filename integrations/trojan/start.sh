#!/bin/bash
# =============================================================================
# FluxVPN Trojan Startup Script (Xray Multi-User)
# =============================================================================
# Uses Xray-core with Trojan inbound for multi-user support.
# Each user gets their own password and per-user traffic statistics.
# Called by entrypoint-wrapper.sh after successful deployment validation.
# =============================================================================

set -e

log_info() {
    echo -e "\033[0;32m[Trojan]\033[0m $1"
}

log_error() {
    echo -e "\033[0;31m[Trojan]\033[0m $1"
}

# Check if we were validated by the entrypoint wrapper
if [ "$FLUXVPN_VALIDATED" != "true" ]; then
    log_error "Container not validated by FluxVPN. Exiting."
    exit 1
fi

log_info "Starting Trojan service (Xray multi-user)..."
log_info "Protocol: $FLUXVPN_PROTOCOL"
log_info "Deployment ID: $FLUXVPN_DEPLOYMENT_ID"

# Initialize telemetry sidecar
TELEMETRY_PORT="${TELEMETRY_PORT:-9093}"
source /usr/local/bin/telemetry_helpers.sh
init_telemetry
log_info "Telemetry initialized on port $TELEMETRY_PORT"

# Extract configuration from FLUXVPN_CONFIG
TROJAN_PASSWORD=$(echo "$FLUXVPN_CONFIG" | jq -r '.password // empty')
TROJAN_PORT=$(echo "$FLUXVPN_CONFIG" | jq -r '.port // 8443')
TROJAN_SNI=$(echo "$FLUXVPN_CONFIG" | jq -r '.sni // "operator7.example.invalid"')

# Validate required fields
if [ -z "$TROJAN_PASSWORD" ]; then
    log_error "No password found in configuration"
    exit 1
fi

log_info "Configuration loaded:"
log_info "  Port: $TROJAN_PORT"
log_info "  SNI: $TROJAN_SNI"

# Generate self-signed certificate if not provided
if [ ! -f /app/certs/server.crt ] || [ ! -f /app/certs/server.key ]; then
    log_info "Generating self-signed certificate..."
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout /app/certs/server.key \
        -out /app/certs/server.crt \
        -days 365 \
        -subj "/CN=$TROJAN_SNI"
fi

# Generate Xray config with initial user (sync daemon will replace with all users)
cat > /app/config.json << EOF
{
    "stats": {},
    "api": {"tag": "api", "services": ["StatsService"]},
    "policy": {
        "levels": {"0": {"statsUserUplink": true, "statsUserDownlink": true}},
        "system": {"statsInboundUplink": true, "statsInboundDownlink": true}
    },
    "log": {"loglevel": "warning"},
    "inbounds": [
        {
            "tag": "trojan",
            "port": $TROJAN_PORT,
            "protocol": "trojan",
            "settings": {
                "clients": [
                    {"password": "$TROJAN_PASSWORD", "email": "initial", "level": 0}
                ]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {
                    "certificates": [{
                        "certificateFile": "/app/certs/server.crt",
                        "keyFile": "/app/certs/server.key"
                    }]
                }
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

log_info "Xray config generated at /app/config.json (1 initial user)"

# Start background user sync daemon
if [ -n "$INTERNAL_API_KEY" ]; then
    log_info "Starting user sync daemon..."
    /usr/local/bin/vpn_auth_sync.sh &
    SYNC_PID=$!
    log_info "Sync daemon started (PID: $SYNC_PID)"
else
    log_info "WARNING: INTERNAL_API_KEY not set, sync daemon disabled"
fi

# Start Xray in restart loop (sync daemon can pkill to trigger reload)
log_info "Starting Xray - Trojan mode (restart-loop mode)..."
while true; do
    # set -e is on: without '|| EXIT_CODE=$?' a failing xray kills the
    # whole container instead of being retried by this loop.
    EXIT_CODE=0
    xray run -c /app/config.json || EXIT_CODE=$?
    log_info "Xray exited with code $EXIT_CODE, restarting in 3s..."
    sleep 3
done
