#!/bin/bash
# =============================================================================
# FluxVPN Telemetry Helpers
# =============================================================================
# Shell functions for protocol containers to record usage telemetry.
# Source this file in each protocol's start.sh after telemetry_server.py
# has been started by init_telemetry().
#
# Environment Variables:
#   TELEMETRY_STATS_FILE - Path to stats JSON file (default: /tmp/telemetry_stats.json)
#   TELEMETRY_PORT      - Port for telemetry server (default: 9090)
# =============================================================================

TELEMETRY_STATS_FILE="${TELEMETRY_STATS_FILE:-/tmp/telemetry_stats.json}"
TELEMETRY_PORT="${TELEMETRY_PORT:-9090}"

# -----------------------------------------------------------------------------
# init_telemetry()
#   Initialize the telemetry stats file and start the telemetry sidecar server.
#   Call this once from start.sh before the protocol service starts.
# -----------------------------------------------------------------------------
init_telemetry() {
    # Create initial stats file with empty structures
    echo '{"records": [], "connections": {}}' > "$TELEMETRY_STATS_FILE"

    # Start telemetry server in background
    python3 /usr/local/bin/telemetry_server.py &
    local server_pid=$!
    echo "[Telemetry] Sidecar started (PID: $server_pid, port: $TELEMETRY_PORT)"

    # Store PID so we can clean up on exit
    echo "$server_pid" > /tmp/telemetry_server.pid

    # Verify telemetry server started successfully by checking the port
    local retries=10
    while [ $retries -gt 0 ]; do
        if nc -z localhost "$TELEMETRY_PORT" 2>/dev/null; then
            echo "[Telemetry] Sidecar verified listening on port $TELEMETRY_PORT"
            break
        fi
        retries=$((retries - 1))
        sleep 0.5
    done

    if [ $retries -eq 0 ]; then
        echo "[Telemetry] WARNING: Sidecar failed to start on port $TELEMETRY_PORT after 5s"
        # Don't exit — the VPN service can still run without telemetry
    fi

    # Kill telemetry sidecar when this shell exits (handles SIGTERM from Docker/Flux)
    trap "kill $server_pid 2>/dev/null; rm -f /tmp/telemetry_server.pid" EXIT
}

# -----------------------------------------------------------------------------
# update_user_stats(user_id, bytes_uploaded, bytes_downloaded, connected_at)
#   Atomically append a bandwidth usage record for a user.
#   Uses jq to safely update the JSON file.
#
#   Arguments:
#     user_id         - The VPN user identifier
#     bytes_uploaded  - Bytes sent by the user
#     bytes_downloaded - Bytes received by the user
#     connected_at    - ISO timestamp of connection start
# -----------------------------------------------------------------------------
update_user_stats() {
    local user_id="$1"
    local bytes_uploaded="$2"
    local bytes_downloaded="$3"
    local connected_at="${4:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

    if [ -z "$user_id" ]; then
        echo "[Telemetry] ERROR: update_user_stats requires user_id" >&2
        return 1
    fi

    # Get current timestamp for disconnected_at
    local disconnected_at
    disconnected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Use jq to atomically append the new record
    # Write to a temp file first, then move to avoid corruption
    local tmp_file
    tmp_file=$(mktemp "${TELEMETRY_STATS_FILE}.XXXXXX")

    jq --arg uid "$user_id" \
       --arg up "$bytes_uploaded" \
       --arg down "$bytes_downloaded" \
       --arg conn "$connected_at" \
       --arg disc "$disconnected_at" \
       '.records += [{"user_id": $uid, "bytes_uploaded": ($up | tonumber), "bytes_downloaded": ($down | tonumber), "connected_at": $conn, "disconnected_at": $disc}]' \
       "$TELEMETRY_STATS_FILE" > "$tmp_file" 2>/dev/null

    if [ $? -eq 0 ]; then
        mv "$tmp_file" "$TELEMETRY_STATS_FILE"
    else
        rm -f "$tmp_file"
        echo "[Telemetry] ERROR: Failed to update stats for user $user_id" >&2
        return 1
    fi
}

# -----------------------------------------------------------------------------
# update_connection_count(user_id, count)
#   Atomically set the active connection count for a user.
#   Uses jq to safely update the JSON file.
#
#   Arguments:
#     user_id - The VPN user identifier
#     count   - Number of active connections
# -----------------------------------------------------------------------------
update_connection_count() {
    local user_id="$1"
    local count="${2:-0}"

    if [ -z "$user_id" ]; then
        echo "[Telemetry] ERROR: update_connection_count requires user_id" >&2
        return 1
    fi

    # Use jq to atomically update the connection count
    local tmp_file
    tmp_file=$(mktemp "${TELEMETRY_STATS_FILE}.XXXXXX")

    jq --arg uid "$user_id" \
       --argjson cnt "$count" \
       '.connections[$uid] = $cnt' \
       "$TELEMETRY_STATS_FILE" > "$tmp_file" 2>/dev/null

    if [ $? -eq 0 ]; then
        mv "$tmp_file" "$TELEMETRY_STATS_FILE"
    else
        rm -f "$tmp_file"
        echo "[Telemetry] ERROR: Failed to update connection count for user $user_id" >&2
        return 1
    fi
}

# -----------------------------------------------------------------------------
# cleanup_telemetry()
#   Stop the telemetry sidecar server and clean up PID file.
#   Call this on container exit if graceful shutdown is needed.
# -----------------------------------------------------------------------------
cleanup_telemetry() {
    if [ -f /tmp/telemetry_server.pid ]; then
        local pid
        pid=$(cat /tmp/telemetry_server.pid)
        kill "$pid" 2>/dev/null
        rm -f /tmp/telemetry_server.pid
        echo "[Telemetry] Sidecar stopped (PID: $pid)"
    fi
}
