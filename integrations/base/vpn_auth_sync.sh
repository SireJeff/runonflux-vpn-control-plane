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
    log_sync "TRAFFIC: collecting stats (protocol=$FLUXVPN_PROTOCOL)..."
    local stats_bin
    if command -v xray >/dev/null 2>&1; then
        stats_bin="xray"
    elif command -v v2ray >/dev/null 2>&1; then
        stats_bin="v2ray"
    else
        log_sync "TRAFFIC: no xray/v2ray binary found, skipping"
        return
    fi

    local stats_json
    local stats_cmd="api statsquery"
    if [ "$stats_bin" = "v2ray" ]; then
        stats_cmd="api stats"
    fi

    # Try the stats command with retry (xray may be restarting)
    local retry=0
    while [ $retry -lt 3 ]; do
        stats_json=$($stats_bin $stats_cmd --server=127.0.0.1:10085 2>/tmp/stats_err.log)
        if [ -n "$stats_json" ]; then
            break
        fi
        retry=$((retry + 1))
        [ $retry -lt 3 ] && sleep 2
    done

    # If empty, try alternate flags/commands for v2ray
    if [ -z "$stats_json" ] && [ "$stats_bin" = "v2ray" ]; then
        stats_json=$($stats_bin api stats -s 127.0.0.1:10085 2>/tmp/stats_err2.log)
        if [ -n "$stats_json" ]; then
            log_sync "TRAFFIC: v2ray 'api stats -s' worked"
        fi
    fi

    if [ -z "$stats_json" ]; then
        local err_msg=""
        [ -f /tmp/stats_err.log ] && err_msg=$(head -c 300 /tmp/stats_err.log)
        log_sync "TRAFFIC: $stats_bin $stats_cmd failed after 3 retries (err: ${err_msg:-none})"
        return
    fi

    # Log stats summary for debugging
    local stat_count
    stat_count=$(echo "$stats_json" | jq '.stat | length' 2>/dev/null || echo "?")
    log_sync "TRAFFIC: $stats_bin returned $stat_count stats"

    # Deep debug: dump raw response and try alternate queries
    if [ "$stat_count" = "0" ] || [ "$stat_count" = "?" ]; then
        log_sync "TRAFFIC DEBUG: raw response: ${stats_json:0:500}"

        # Try xray api stats (different command)
        if [ "$stats_bin" = "xray" ]; then
            local alt_stats
            alt_stats=$($stats_bin api stats --server=127.0.0.1:10085 2>/tmp/stats_alt.log)
            log_sync "TRAFFIC DEBUG: 'xray api stats' (first 500): ${alt_stats:0:500}"

            # Try querying with explicit pattern
            local pattern_stats
            pattern_stats=$($stats_bin api statsquery --server=127.0.0.1:10085 --pattern ".*" 2>/tmp/stats_pat.log)
            log_sync "TRAFFIC DEBUG: statsquery pattern='.*' (first 500): ${pattern_stats:0:500}"

            # Try specific stat name
            local specific_stat
            specific_stat=$($stats_bin api stats --server=127.0.0.1:10085 --name="inbound>>>vless>>>traffic>>>uplink" 2>/tmp/stats_spec.log)
            log_sync "TRAFFIC DEBUG: inbound vless uplink: ${specific_stat:0:200}"
        fi

        # Check Xray config for stats section
        if [ -f /app/config.json ]; then
            local stats_cfg
            stats_cfg=$(jq -c '.stats // "NOT_FOUND"' /app/config.json 2>/dev/null)
            log_sync "TRAFFIC DEBUG: config stats: $stats_cfg"
            local api_cfg
            api_cfg=$(jq -c '.api // "NOT_FOUND"' /app/config.json 2>/dev/null)
            log_sync "TRAFFIC DEBUG: config api: $api_cfg"
            local clients_sample
            clients_sample=$(jq -c '.inbounds[0].settings.clients[:2]' /app/config.json 2>/dev/null)
            log_sync "TRAFFIC DEBUG: first 2 clients: $clients_sample"
            local inbounds_tags
            inbounds_tags=$(jq -c '[.inbounds[] | {tag, protocol}]' /app/config.json 2>/dev/null)
            log_sync "TRAFFIC DEBUG: inbounds: $inbounds_tags"
        fi
    fi

    # Get unique usernames from stats
    local usernames
    usernames=$(echo "$stats_json" | jq -r '.stat[].name' 2>/dev/null | grep '^user>>>' | awk -F'>>>' '{print $2}' | sort -u)

    if [ -z "$usernames" ]; then
        # Debug: show first 3 stat names
        local sample_names
        sample_names=$(echo "$stats_json" | jq -r '.stat[:3][].name' 2>/dev/null | tr '\n' ' ')
        log_sync "TRAFFIC: no user>>> names found, sample: $sample_names"
        return
    fi

    log_sync "TRAFFIC: found users: $(echo $usernames | tr '\n' ' ')"

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

_collect_ssh_traffic() {
    log_sync "TRAFFIC SSH: collecting per-UID stats..."

    if ! command -v iptables >/dev/null 2>&1; then
        log_sync "TRAFFIC SSH: iptables not available, skipping"
        return
    fi

    local allowed_users
    allowed_users=$(grep '^AllowUsers' /etc/ssh/sshd_config 2>/dev/null | sed 's/^AllowUsers //')

    if [ -z "$allowed_users" ]; then
        log_sync "TRAFFIC SSH: no allowed users found"
        return
    fi

    for username in $allowed_users; do
        local uid
        uid=$(id -u "$username" 2>/dev/null)
        [ -z "$uid" ] && continue

        # Ensure iptables rule exists for this UID (idempotent)
        if ! iptables -C OUTPUT -m owner --uid-owner "$uid" -j ACCEPT 2>/dev/null; then
            iptables -A OUTPUT -m owner --uid-owner "$uid" -j ACCEPT 2>/dev/null
            log_sync "TRAFFIC SSH: added iptables rule for $username (uid=$uid)"
        fi

        # Read byte counter for this rule
        local rule_line
        rule_line=$(iptables -L OUTPUT -n -v 2>/dev/null | grep "owner UID match ${uid}" | head -1)

        if [ -z "$rule_line" ]; then
            continue
        fi

        # Extract bytes field (2nd column in iptables -L -v output)
        local bytes_str
        bytes_str=$(echo "$rule_line" | awk '{print $2}')

        # Parse human-readable byte suffixes
        local total_bytes=0
        case "$bytes_str" in
            *K) total_bytes=$(echo "$bytes_str" | sed 's/K//' | awk '{printf "%.0f", $1 * 1024}') ;;
            *M) total_bytes=$(echo "$bytes_str" | sed 's/M//' | awk '{printf "%.0f", $1 * 1048576}') ;;
            *G) total_bytes=$(echo "$bytes_str" | sed 's/G//' | awk '{printf "%.0f", $1 * 1073741824}') ;;
            *) total_bytes="$bytes_str" ;;
        esac

        # v2: report raw cumulative counter; backend computes the delta.
        # The iptables -owner ACCEPT rule counter is cumulative since rule creation.
        if [ "$total_bytes" -gt 0 ]; then
            _report_traffic "$username" 0 "$total_bytes"
        fi
    done
}

_collect_squid_traffic() {
    log_sync "TRAFFIC HTTP Proxy: collecting Squid access.log stats..."

    local log_file="/var/log/squid/access.log"

    if [ ! -f "$log_file" ]; then
        log_sync "TRAFFIC HTTP Proxy: access.log not found, skipping"
        return
    fi

    # v2: aggregate bytes per username across the WHOLE log (lifetime-cumulative
    # per user); backend computes the delta, so no checkpoint/offset tracking
    # is needed anymore.
    # Squid log: timestamp elapsed client resultcode BYTES method url USERNAME ...
    local agg_tmp
    agg_tmp=$(mktemp)
    awk '{u=$8; b=$5; if(u!="-" && u!="" && b~/^[0-9]+$/) print u, b}' "$log_file" | \
        awk '{user_bytes[$1]+=$2} END {for(u in user_bytes) print u, user_bytes[u]}' > "$agg_tmp"

    while IFS=' ' read -r username cumulative_total; do
        [ -z "$username" ] || [ -z "$cumulative_total" ] && continue
        [ "$cumulative_total" -le 0 ] && continue

        # v2: report raw cumulative counter; backend computes the delta.
        # Squid bytes = response size (download). Report as cumulative_out.
        _report_traffic "$username" "0" "$cumulative_total"
    done < "$agg_tmp"
    rm -f "$agg_tmp"

    log_sync "TRAFFIC HTTP Proxy: reported cumulative totals from $log_file"
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

# Swap /app/config_new.json in only if Xray accepts it, then restart Xray.
# A rejected config (e.g. a duplicate user email) used to replace the working
# one; Xray then failed to start and the container died fleet-wide (2026-10-24).
_apply_xray_config() {
    local label="$1" count="$2" test_out
    if diff -q /app/config.json /app/config_new.json > /dev/null 2>&1; then
        rm /app/config_new.json
        return
    fi
    if ! test_out=$(xray run -test -c /app/config_new.json 2>&1); then
        mv /app/config_new.json /app/config_rejected.json
        log_sync "ERROR $label: Xray rejected the new config ($count users), keeping the current one: $(echo "$test_out" | grep -m1 -i 'failed')"
        return
    fi
    mv /app/config_new.json /app/config.json
    log_sync "$label: Config changed ($count users), restarting Xray..."
    pkill xray 2>/dev/null || pkill v2ray 2>/dev/null || true
}

_sync_vless_users() {
    local port
    port=$(jq -r '.inbounds[0].port // 443' /app/config.json 2>/dev/null || echo "443")
    local path
    path=$(jq -r '.inbounds[0].streamSettings.wsSettings.path // "/vless"' /app/config.json 2>/dev/null || echo "/vless")

    local clients
    clients=$(cat /tmp/vpn_users_sync.json | jq -c '[.users[] | {id: .credential_data.uuid, email: .username, level: 0}]')

    if [ "$clients" = "[]" ] || [ -z "$clients" ]; then
        return
    fi

    cat > /app/config_new.json << VLESSEOF
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
            {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
        ]
    }
}
VLESSEOF

    _apply_xray_config "VLESS" "$(echo "$clients" | jq 'length')"
}

_sync_trojan_users() {
    local port
    port=$(jq -r '.inbounds[] | select(.tag=="trojan") | .port // 8443' /app/config.json 2>/dev/null | head -1)
    [ -z "$port" ] && port=8443

    local ssl_cert="/app/certs/server.crt"
    local ssl_key="/app/certs/server.key"

    local clients
    clients=$(cat /tmp/vpn_users_sync.json | jq -c '[.users[] | {password: .credential_data.password, email: .username, level: 0}]')

    if [ "$clients" = "[]" ] || [ -z "$clients" ]; then
        return
    fi

    cat > /app/config_new.json << TROJANEOF
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
            "port": ${port},
            "protocol": "trojan",
            "settings": {
                "clients": ${clients}
            },
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {
                    "certificates": [{
                        "certificateFile": "${ssl_cert}",
                        "keyFile": "${ssl_key}"
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
TROJANEOF

    _apply_xray_config "Trojan" "$(echo "$clients" | jq 'length')"
}

_sync_ss_users() {
    # Xray multi-user Shadowsocks: each user has their own password
    local port
    port=$(jq -r '.inbounds[] | select(.tag=="ss") | .port // 8388' /app/config.json 2>/dev/null | head -1)
    [ -z "$port" ] && port=8388

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
SSEOF

    _apply_xray_config "SS" "$(echo "$clients" | jq 'length')"
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
    # Collect and report per-user traffic BEFORE user sync
    # (sync may restart xray, which makes stats API temporarily unavailable)
    case "$FLUXVPN_PROTOCOL" in
        ss|shadowsocks|outline|vless|trojan)
            _collect_xray_traffic
            ;;
        ssh)
            _collect_ssh_traffic
            ;;
        http_proxy|http-proxy)
            _collect_squid_traffic
            ;;
    esac

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

    sleep "$SYNC_INTERVAL"
done
