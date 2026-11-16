#!/bin/bash
# =============================================================================
# FluxVPN SSH Tunnel Startup Script (API-based Auth)
# =============================================================================
# Called by entrypoint-wrapper.sh after successful deployment validation.
#
# Auth flow:
#   1. Container starts with initial user from FLUXVPN_CONFIG
#   2. PAM validates each login against Worker API in real-time
#   3. Background sync daemon adds/removes system users periodically
# =============================================================================

set -e

log_info() {
    echo -e "\033[0;32m[SSH]\033[0m $1"
}

log_error() {
    echo -e "\033[0;31m[SSH]\033[0m $1"
}

# Check if we were validated by the entrypoint wrapper
if [ "$FLUXVPN_VALIDATED" != "true" ]; then
    log_error "Container not validated by FluxVPN. Exiting."
    exit 1
fi

log_info "Starting SSH Tunnel service (API-based auth)..."
log_info "Protocol: $FLUXVPN_PROTOCOL"
log_info "Deployment ID: $FLUXVPN_DEPLOYMENT_ID"

# Initialize telemetry sidecar
TELEMETRY_PORT="${TELEMETRY_PORT:-9090}"
source /usr/local/bin/telemetry_helpers.sh
init_telemetry
log_info "Telemetry initialized on port $TELEMETRY_PORT"

# Extract configuration from FLUXVPN_CONFIG
SSH_PORT=$(echo "$FLUXVPN_CONFIG" | jq -r '.port // 2222')

log_info "SSH Port: $SSH_PORT"

# =============================================================================
# Configure sshd (user sync via API, no PAM - Alpine doesn't support it)
# =============================================================================
log_info "Setting up API-based user sync (Alpine has no PAM support)..."
mkdir -p /usr/local/bin
chmod +x /usr/local/bin/vpn_auth_sync.sh

# =============================================================================
# Create initial system user from FLUXVPN_CONFIG (for first login)
# =============================================================================
SSH_USERNAME=$(echo "$FLUXVPN_CONFIG" | jq -r '.username // empty')
SSH_PASSWORD=$(echo "$FLUXVPN_CONFIG" | jq -r '.password // empty')

if [ -n "$SSH_USERNAME" ] && [ -n "$SSH_PASSWORD" ]; then
    if ! id "$SSH_USERNAME" &>/dev/null; then
        log_info "Creating initial user $SSH_USERNAME..."
        adduser -D -s /bin/sh "$SSH_USERNAME"
    fi
    echo "$SSH_USERNAME:$SSH_PASSWORD" | chpasswd
    INITIAL_ALLOW="$SSH_USERNAME"
    log_info "Initial user created: $SSH_USERNAME"
else
    INITIAL_ALLOW=""
fi

# =============================================================================
# Start background user sync daemon
# =============================================================================
if [ -n "$INTERNAL_API_KEY" ]; then
    log_info "Starting user sync daemon..."
    /usr/local/bin/vpn_auth_sync.sh &
    SYNC_PID=$!
    log_info "Sync daemon started (PID: $SYNC_PID)"
else
    log_info "WARNING: INTERNAL_API_KEY not set, sync daemon disabled"
    log_info "Only initial user from deployment token will work"
fi

# =============================================================================
# Configure sshd
# =============================================================================
mkdir -p /etc/ssh

# Build AllowUsers list: initial user + any synced users
# The sync daemon will update this dynamically
if [ -z "$INITIAL_ALLOW" ]; then
    ALLOW_DIRECTIVE="# AllowUsers will be populated by sync daemon"
else
    ALLOW_DIRECTIVE="AllowUsers $INITIAL_ALLOW"
fi

cat > /etc/ssh/sshd_config << EOF
Port $SSH_PORT
PermitRootLogin no
PasswordAuthentication yes
PermitEmptyPasswords no
ChallengeResponseAuthentication no
X11Forwarding no
PrintMotd no
AcceptEnv LANG LC_*
Subsystem sftp /usr/lib/ssh/sftp-server
$ALLOW_DIRECTIVE
AllowTcpForwarding yes
GatewayPorts yes
PermitTunnel yes
EOF

log_info "sshd config generated"

# Generate host keys if they don't exist
if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
    log_info "Generating SSH host keys..."
    ssh-keygen -A
fi

# Start SSH daemon
log_info "Starting sshd on port $SSH_PORT (PAM auth via Worker API)..."
exec /usr/sbin/sshd -D -e
