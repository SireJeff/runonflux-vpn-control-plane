#!/bin/bash
# =============================================================================
# FluxVPN Squid Basic Auth Helper
# =============================================================================
# Squid external ACL helper that validates proxy credentials against
# the Worker API in real-time.
#
# Squid protocol:
#   Input:  "username password" (one per line on stdin)
#   Output: "OK" or "ERR" (one per line on stdout)
#
# Environment Variables (required):
#   FLUXVPN_API_URL     - Worker API base URL
#   INTERNAL_API_KEY    - Shared secret for internal endpoints
# =============================================================================

API_BASE="${FLUXVPN_API_URL%/}"
API_BASE="${API_BASE%/api/v1}"

# Simple in-memory cache to avoid hammering the API on rapid requests
# Format: "username:password" → timestamp
declare -A AUTH_CACHE
CACHE_TTL=30  # seconds

log_auth() {
    echo -e "\033[0;36m[SquidAuth]\033[0m $1" >&2
}

log_auth "Starting API-based auth helper"

while IFS=' ' read -r username password; do
    # Safety checks
    if [ -z "$username" ] || [ -z "$password" ]; then
        echo "ERR"
        continue
    fi

    CACHE_KEY="${username}:${password}"
    NOW=$(date +%s)

    # Check cache
    if [ -n "${AUTH_CACHE[$CACHE_KEY]:-}" ]; then
        CACHED_AT="${AUTH_CACHE[$CACHE_KEY]}"
        AGE=$(( NOW - CACHED_AT ))
        if [ "$AGE" -lt "$CACHE_TTL" ]; then
            echo "OK"
            continue
        fi
    fi

    # Call Worker API
    AUTH_URL="${API_BASE}/api/v1/internal/user-credentials?username=${username}&protocol=http_proxy"

    RESPONSE=$(curl -sf \
        --max-time 3 \
        -H "X-Internal-API-Key: ${INTERNAL_API_KEY}" \
        "$AUTH_URL" 2>/dev/null)

    if [ $? -ne 0 ]; then
        echo "ERR"
        continue
    fi

    # Extract expected password
    EXPECTED_PASSWORD=$(echo "$RESPONSE" | jq -r '.credential_data.password // empty' 2>/dev/null)

    if [ -z "$EXPECTED_PASSWORD" ]; then
        echo "ERR"
        continue
    fi

    # Compare
    if [ "$password" = "$EXPECTED_PASSWORD" ]; then
        AUTH_CACHE["$CACHE_KEY"]="$NOW"
        echo "OK"
    else
        echo "ERR"
    fi
done
