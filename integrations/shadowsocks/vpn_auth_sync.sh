#!/bin/bash
# =============================================================================
# FluxVPN User Sync Daemon
# =============================================================================
# Periodically fetches active users from the Worker API and updates
# protocol-specific configuration files.
# Also collects per-user traffic statistics and reports to the Worker API.
#
# Environment Variables (required):
#   FLUXVPN_API_URL     - Worker API base URL
#   INTERNAL_API_KEY    - Shared secret for internal endpoints
#   FLUXVPN_PROTOCOL    - Protocol name (ssh/ss/vless/trojan/outline/http_proxy)
#
# Environment Variables (optional):
#   SYNC_INTERVAL       - Seconds between syncs (default: 60)
# =============================================================================

SYNC_INTERVAL="${SYNC_INTERVAL:-60}"
AUTH_LOG_PREFIX="\033[0;36m[AuthSync]\033[0m"

# Per-container boot id (regenerates on restart -> backend detects counter reset)
BOOT_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "boot-$$-$(date +%s)")

log_sync() {
    echo -e "$AUTH_LOG_PREFIX $1"
}

# Build the API URL (strip trailing /api/v1 if present)
API_BASE="${FLUXVPN_API_URL%/}"
API_BASE="${API_BASE%/api/v1}"
SYNC_URL="${API_BASE}/api/v1/internal/sync-users?protocol=${FLUXVPN_PROTOCOL}"

# =============================================================================
# Traffic reporting
# =============================================================================

# args: username  cumulative_in  cumulative_out
_report_traffic() {
    local username="$1"
    local cumulative_in="$2"
    local cumulative_out="$3"

    [ -z "$username" ] && return

    local resp
    resp=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/api/v1/internal/traffic-report" \
        -H "X-Internal-API-Key: ${INTERNAL_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "{
            \"username\": \"${username}\",
            \"protocol\": \"${FLUXVPN_PROTOCOL}\",
            \"region\": \"${FLUXVPN_REGION:-CH}\",
            \"bytes_in\": 0,
            \"bytes_out\": 0,
            \"report_version\": 2,
            \"cumulative_in\": ${cumulative_in:-0},
            \"cumulative_out\": ${cumulative_out:-0},
            \"boot_id\": \"${BOOT_ID}\",
            \"instance_id\": \"${FLUXVPN_INSTANCE_ID:-unknown}\",
            \"session_duration_seconds\": ${SYNC_INTERVAL},
            \"instance_ip\": \"${FLUXVPN_INSTANCE_ID:-unknown}\"
        }" 2>/dev/null)

    local http_code=$(echo "$resp" | tail -1)
    if [ "$http_code" = "200" ]; then
        log_sync "Traffic v2: ${username} cum_in=${cumulative_in} cum_out=${cumulative_out}"
    else
        log_sync "Traffic v2 FAILED: ${username} http=${http_code}"
    fi
}

# Collect per-user traffic from Xray/V2Ray stats API (works for SS, Outline, VLESS)
_collect_xray_traffic() {
    local stats_bin
    if command -v xray >/dev/null 2>&1; then
        stats_bin="xray"
    elif command -v v2ray >/dev/null 2>&1; then
        stats_bin="v2ray"
    else
        return
    fi

    local stats_json
    stats_json=$($stats_bin api statsquery --server=127.0.0.1:10085 2>/dev/null)

    if [ -z "$stats_json" ]; then
        return
    fi

    # Get unique usernames from stats
    local usernames
    usernames=$(echo "$stats_json" | jq -r '.stat[].name' 2>/dev/null | grep '^user>>>' | awk -F'>>>' '{print $2}' | sort -u)

    [ -z "$usernames" ] && return

    for username in $usernames; do
        local uplink=$(echo "$stats_json" | jq -r ".stat[] | select(.name==\"user>>>${username}>>>traffic>>>uplink\") | .value" 2>/dev/null | head -1)
        local downlink=$(echo "$stats_json" | jq -r ".stat[] | select(.name==\"user>>>${username}>>>traffic>>>downlink\") | .value" 2>/dev/null | head -1)

        uplink=${uplink:-0}
        downlink=${downlink:-0}
        # v2: report raw cumulative counters; backend computes the delta.
        if [ "$uplink" -gt 0 ] || [ "$downlink" -gt 0 ]; then
            _report_traffic "$username" "$uplink" "$downlink"
        fi
    done
}

# =============================================================================
# Protocol-specific sync functions (MUST be defined before the while loop)
# =============================================================================

_sync_ssh_users() {
    local users_json
    users_json=$(cat /tmp/vpn_users_sync.json | jq -c '.users[]')

    echo "$users_json" | while IFS= read -r user_line; do
        local username
        username=$(echo "$user_line" | jq -r '.username')
        local password
        password=$(echo "$user_line" | jq -r '.credential_data.password')

        if [ -z "$username" ] || [ -z "$password" ]; then
            continue
        fi

        if ! id "$username" &>/dev/null; then
            adduser -D -s /bin/sh "$username" 2>/dev/null || true
        fi

        echo "$username:$password" | chpasswd 2>/dev/null
    done

    local allow_list
    allow_list=$(cat /tmp/vpn_users_sync.json | jq -r '.users[].credential_data.username' | tr '\n' ' ' | xargs)

    if [ -n "$allow_list" ]; then
        sed -i "s/^AllowUsers.*/AllowUsers $allow_list/" /etc/ssh/sshd_config
        kill -HUP "$(cat /run/sshd.pid 2>/dev/null || cat /var/run/sshd.pid 2>/dev/null)" 2>/dev/null || true
        log_sync "SSH: Updated AllowUsers ($allow_list)"
    fi
}

_sync_vless_users() {
    local port
    port=$(jq -r '.inbounds[0].port // 443' /app/config.json 2>/dev/null || echo "443")
    local path
    path=$(jq -r '.inbounds[0].streamSettings.wsSettings.path // "/vless"' /app/config.json 2>/dev/null || echo "/vless")

    local clients
    clients=$(cat /tmp/vpn_users_sync.json | jq -c '[.users[] | {id: .credential_data.uuid, email: .credential_data.username, level: 0}]')

    if [ "$clients" = "[]" ] || [ -z "$clients" ]; then
        return
    fi

    cat > /app/config_new.json << VLESSEOF
{
    "stats": {},
    "api": {"tag": "api", "services": ["StatsService"]},
    "log": {"loglevel": "warning"},
    "inbounds": [
        {
            "tag": "vless",
            "port": ${port},
            "protocol": "vless",
            "settings": {
                "clients": ${clients},
                "decryption": "none"
            },
            "streamSettings": {
                "network": "ws",
                "wsSettings": {
                    "path": "${path}"
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
            {"type": "field", "inboundTag": ["api"], "outboundTag": "direct"}
        ]
    }
}
VLESSEOF

    if diff -q /app/config.json /app/config_new.json > /dev/null 2>&1; then
        rm /app/config_new.json
        return
    fi

    mv /app/config_new.json /app/config.json
    log_sync "VLESS: Config changed ($(echo "$clients" | jq 'length') users), restarting V2Ray..."
    pkill v2ray 2>/dev/null || true
}

_sync_trojan_users() {
    local port
    port=$(jq -r '.local_port // 443' /app/config.json 2>/dev/null || echo "443")

    local ssl_cert="/app/certs/server.crt"
    local ssl_key="/app/certs/server.key"

    local passwords
    passwords=$(cat /tmp/vpn_users_sync.json | jq -c '[.users[] | .credential_data.password]')

    if [ "$passwords" = "[]" ] || [ -z "$passwords" ]; then
        return
    fi

    cat > /app/config_new.json << TROJANEOF
{
    "run_type": "server",
    "local_addr": "0.0.0.0",
    "local_port": ${port},
    "remote_addr": "127.0.0.1",
    "remote_port": 80,
    "password": ${passwords},
    "log_level": 1,
    "ssl": {
        "cert": "${ssl_cert}",
        "key": "${ssl_key}",
        "key_password": "",
        "cipher": "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256",
        "cipher_tls13": "TLS_AES_128_GCM_SHA256:TLS_CHACHA20_POLY1305_SHA256",
        "prefer_server_cipher": true,
        "alpn": ["http/1.1"],
        "reuse_session": true,
        "session_ticket": false,
        "session_timeout": 600
    },
    "tcp": {
        "prefer_ipv4": false,
        "no_delay": true,
        "keep_alive": true,
        "reuse_port": false,
        "fast_open": false,
        "fast_open_qlen": 20
    }
}
TROJANEOF

    mv /app/config_new.json /app/config.json
    pkill -HUP trojan 2>/dev/null || true
    log_sync "Trojan: Updated passwords ($(echo "$passwords" | jq 'length') users)"
}

_sync_ss_users() {
    # Xray multi-user Shadowsocks: each user has their own password
    local port
    port=$(jq -r '.inbounds[] | select(.tag=="ss") | .port // 8388' /app/config.json 2>/dev/null | head -1)
    [ -z "$port" ] && port=8388

    local socks_port
    socks_port=$(jq -r '.inbounds[] | select(.tag=="socks") | .port // 1080' /app/config.json 2>/dev/null | head -1)
    [ -z "$socks_port" ] && socks_port="${SOCKS5_PORT:-1080}"

    local method
    method=$(jq -r '.inbounds[] | select(.tag=="ss") | .settings.method // "chacha20-ietf-poly1305"' /app/config.json 2>/dev/null | head -1)
    [ -z "$method" ] && method="chacha20-ietf-poly1305"

    local root_password
    root_password=$(cat /tmp/vpn_users_sync.json | jq -r '.users[0].credential_data.password // "fallback_pass"')

    local clients
    clients=$(cat /tmp/vpn_users_sync.json | jq -c --arg m "$method" '[.users[] | {email: .username, password: .credential_data.password, method: $m}]')

    if [ "$clients" = "[]" ] || [ -z "$clients" ]; then
        return
    fi

    # Build SOCKS5 accounts from the same users
    local socks_accounts
    socks_accounts=$(cat /tmp/vpn_users_sync.json | jq -c '[.users[] | {user: .username, pass: .credential_data.password}]')

    cat > /app/config_new.json << SSEOF
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
            "port": ${port},
            "protocol": "shadowsocks",
            "settings": {
                "method": "${method}",
                "password": "${root_password}",
                "clients": ${clients},
                "network": "tcp,udp"
            }
        },
        {
            "tag": "socks",
            "port": ${socks_port},
            "protocol": "socks",
            "settings": {
                "auth": "password",
                "accounts": ${socks_accounts},
                "udp": false
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
            {"type": "field", "inboundTag": ["api"], "outboundTag": "direct"}
        ]
    }
}
SSEOF

    if diff -q /app/config.json /app/config_new.json > /dev/null 2>&1; then
        rm /app/config_new.json
        return
    fi

    mv /app/config_new.json /app/config.json
    log_sync "SS: Config changed ($(echo "$clients" | jq 'length') users, SOCKS5 on ${socks_port}), restarting Xray..."
    pkill xray 2>/dev/null || true
}

_sync_outline_users() {
    _sync_ss_users
}

_sync_http_proxy_users() {
    local htpasswd_file="/etc/squid/passwd"
    > "$htpasswd_file"

    cat /tmp/vpn_users_sync.json | jq -c '.users[]' | while IFS= read -r user_line; do
        local username
        username=$(echo "$user_line" | jq -r '.username')
        local password
        password=$(echo "$user_line" | jq -r '.credential_data.password')

        if [ -n "$username" ] && [ -n "$password" ]; then
            htpasswd -bB "$htpasswd_file" "$username" "$password" 2>/dev/null
        fi
    done

    log_sync "HTTP Proxy: Updated htpasswd ($USER_COUNT users)"
}

# =============================================================================
# Main sync loop
# =============================================================================

log_sync "Starting user sync daemon for protocol: $FLUXVPN_PROTOCOL"
log_sync "Sync URL: $SYNC_URL"
log_sync "Interval: ${SYNC_INTERVAL}s"

while true; do
    # Fetch active users from Worker API
    RESPONSE=$(curl -sf \
        -H "X-Internal-API-Key: ${INTERNAL_API_KEY}" \
        "$SYNC_URL" 2>/dev/null)

    if [ $? -ne 0 ]; then
        log_sync "WARN: Failed to fetch users from API"
        sleep "$SYNC_INTERVAL"
        continue
    fi

    USER_COUNT=$(echo "$RESPONSE" | jq -r '.users | length' 2>/dev/null || echo "0")

    if [ "$USER_COUNT" = "0" ]; then
        log_sync "No active users found"
        sleep "$SYNC_INTERVAL"
        continue
    fi

    log_sync "Synced $USER_COUNT users"

    # Write raw JSON for protocol-specific scripts to consume
    echo "$RESPONSE" | jq '.' > /tmp/vpn_users_sync.json

    # Protocol-specific user config update
    case "$FLUXVPN_PROTOCOL" in
        ssh)
            _sync_ssh_users
            ;;
        vless)
            _sync_vless_users
            ;;
        trojan)
            _sync_trojan_users
            ;;
        ss|shadowsocks)
            _sync_ss_users
            ;;
        outline)
            _sync_outline_users
            ;;
        http_proxy|http-proxy)
            _sync_http_proxy_users
            ;;
        *)
            log_sync "WARN: No sync handler for protocol $FLUXVPN_PROTOCOL"
            ;;
    esac

    # Collect and report per-user traffic (Xray stats API)
    case "$FLUXVPN_PROTOCOL" in
        ss|shadowsocks|outline)
            _collect_xray_traffic
            ;;
        vless)
            _collect_xray_traffic
            ;;
    esac

    sleep "$SYNC_INTERVAL"
done
