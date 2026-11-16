#!/bin/bash
# =============================================================================
# FluxVPN SSH PAM Authentication Helper
# =============================================================================
# Called by pam_exec.so on each SSH login attempt.
# Validates username/password against the Worker API in real-time.
#
# PAM provides:
#   PAM_USER      - The username attempting to log in
#   stdin         - The password (when expose_authtok is used)
#
# Exit codes:
#   0 = auth success
#   1 = auth failure
# =============================================================================

# Read password from stdin (pam_exec expose_authtok sends it this way)
PASSWORD=$(cat)

# Safety checks
if [ -z "$PAM_USER" ] || [ -z "$PASSWORD" ]; then
    exit 1
fi

if [ -z "$FLUXVPN_API_URL" ] || [ -z "$INTERNAL_API_KEY" ]; then
    exit 1
fi

# Build API URL
API_BASE="${FLUXVPN_API_URL%/}"
API_BASE="${API_BASE%/api/v1}"
AUTH_URL="${API_BASE}/api/v1/internal/user-credentials?username=${PAM_USER}&protocol=ssh"

# Call Worker API to fetch expected credentials
RESPONSE=$(curl -sf \
    --max-time 5 \
    -H "X-Internal-API-Key: ${INTERNAL_API_KEY}" \
    "$AUTH_URL" 2>/dev/null)

if [ $? -ne 0 ]; then
    exit 1
fi

# Extract expected password from response
EXPECTED_PASSWORD=$(echo "$RESPONSE" | jq -r '.credential_data.password // empty' 2>/dev/null)

if [ -z "$EXPECTED_PASSWORD" ]; then
    exit 1
fi

# Compare passwords
if [ "$PASSWORD" = "$EXPECTED_PASSWORD" ]; then
    exit 0
else
    exit 1
fi
