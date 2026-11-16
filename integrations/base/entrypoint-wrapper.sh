#!/bin/bash
# =============================================================================
# FluxVPN Container Entrypoint Wrapper
# =============================================================================
#
# This script validates the container deployment with the FluxVPN Worker API
# before starting the actual VPN protocol service.
#
# Required Environment Variables:
#   FLUXVPN_AUTH_TOKEN  - Bootstrap token signed by Worker API
#   FLUXVPN_API_URL     - Worker API base URL (e.g., https://api.operator7.example.invalid)
#   FLUXVPN_INSTANCE_ID - FluxCloud instance identifier
#
# Optional Environment Variables:
#   FLUXVPN_RETRY_COUNT    - Number of validation retries (default: 3)
#   FLUXVPN_RETRY_DELAY    - Delay between retries in seconds (default: 5)
#   FLUXVPN_CONFIG_FILE    - Where to write the validated config (protocol-specific)
#
# Usage in Dockerfile:
#   COPY entrypoint-wrapper.sh /usr/local/bin/
#   RUN chmod +x /usr/local/bin/entrypoint-wrapper.sh
#   ENTRYPOINT ["/usr/local/bin/entrypoint-wrapper.sh"]
#   CMD ["your-service-command"]
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[FluxVPN]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[FluxVPN]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[FluxVPN]${NC} $1" >&2
}

log_debug_env_summary() {
    local token_present="no"
    local token_len=0
    local token_parts=0
    local token_has_whitespace="false"
    local token_has_newline="false"

    if [ -n "$FLUXVPN_AUTH_TOKEN" ]; then
        token_present="yes"
        token_len=${#FLUXVPN_AUTH_TOKEN}
        local dot_chars="${FLUXVPN_AUTH_TOKEN//[^.]}"
        token_parts=$(( ${#dot_chars} + 1 ))
    fi

    if [[ "$FLUXVPN_AUTH_TOKEN" =~ [[:space:]] ]]; then
        token_has_whitespace="true"
    fi

    if [[ "$FLUXVPN_AUTH_TOKEN" == *$'\n'* || "$FLUXVPN_AUTH_TOKEN" == *$'\r'* ]]; then
        token_has_newline="true"
    fi

    log_info "Debug env: component=${FLUXVPN_COMPONENT:-<unset>} app=${FLUXVPN_APP_NAME:-<unset>} protocol=${PROTOCOL:-<unset>}"
    log_info "Debug env: token_present=${token_present} token_len=${token_len} token_parts=${token_parts} token_has_whitespace=${token_has_whitespace} token_has_newline=${token_has_newline}"
    log_info "Debug env: instance_id=${FLUXVPN_INSTANCE_ID:-<unset>} api_url=${FLUXVPN_API_URL:-<unset>}"
}

# =============================================================================
# Environment Validation
# =============================================================================

log_info "Starting FluxVPN container validation..."
log_debug_env_summary

# Check required environment variables
if [ -z "$FLUXVPN_AUTH_TOKEN" ]; then
    log_error "ERROR: FLUXVPN_AUTH_TOKEN environment variable is not set"
    log_error "This container can only be run through authorized FluxVPN deployments"
    exit 1
fi

if [ -z "$FLUXVPN_API_URL" ]; then
    log_error "ERROR: FLUXVPN_API_URL environment variable is not set"
    exit 1
fi

if [ -z "$FLUXVPN_INSTANCE_ID" ]; then
    log_error "ERROR: FLUXVPN_INSTANCE_ID environment variable is not set"
    exit 1
fi

# Set defaults for optional variables
# ~5 minutes of retries: on some Flux nodes a freshly started container cannot
# reach the API for its first seconds, and 3 x 5s made it exit for good.
FLUXVPN_RETRY_COUNT=${FLUXVPN_RETRY_COUNT:-30}
FLUXVPN_RETRY_DELAY=${FLUXVPN_RETRY_DELAY:-10}

# Normalize API URL - strip trailing /api/v1 if present, then add it correctly
# This makes the code work regardless of whether env var has /api/v1 or not
API_BASE="${FLUXVPN_API_URL%/}"
API_BASE="${API_BASE%/api/v1}"
VALIDATE_URL="${API_BASE}/api/v1/nodes/validate-deployment"
API_HOST="${API_BASE#*://}"
API_HOST="${API_HOST%%[:/]*}"

log_info "Instance ID: $FLUXVPN_INSTANCE_ID"
log_info "API URL: $FLUXVPN_API_URL"
log_info "Validate URL: $VALIDATE_URL"
log_info "Retry settings: $FLUXVPN_RETRY_COUNT attempts, ${FLUXVPN_RETRY_DELAY}s delay"

# =============================================================================
# Deployment Validation
# =============================================================================

validate_deployment() {
    local attempt=1
    local max_attempts=$FLUXVPN_RETRY_COUNT
    local response=""
    local http_code=""

    while [ $attempt -le $max_attempts ]; do
        log_info "Validation attempt $attempt of $max_attempts..."

        # Make the validation request. No -f: HTTP errors are handled below via
        # the status code; a non-zero curl exit means no HTTP response at all.
        local curl_rc=0
        response=$(curl -sS \
            --connect-timeout 10 --max-time 30 \
            -w "\n%{http_code}" \
            -X POST "${VALIDATE_URL}" \
            -H "Content-Type: application/json" \
            -d "{\"token\": \"$FLUXVPN_AUTH_TOKEN\", \"instance_id\": \"$FLUXVPN_INSTANCE_ID\"}" \
            2>/tmp/fluxvpn_curl_err) || curl_rc=$?

        if [ $curl_rc -ne 0 ]; then
            log_warn "Cannot reach API (curl exit $curl_rc: $(tr -d '\n' < /tmp/fluxvpn_curl_err)); $API_HOST resolves to: $(getent hosts "$API_HOST" 2>/dev/null | awk '{print $1}' | tr '\n' ' ')"
            if [ $attempt -lt $max_attempts ]; then
                log_info "Retrying in ${FLUXVPN_RETRY_DELAY} seconds..."
                sleep $FLUXVPN_RETRY_DELAY
                attempt=$((attempt + 1))
                continue
            fi
            return 1
        fi

        # Split response into body and HTTP code
        http_code=$(echo "$response" | tail -n1)
        response=$(echo "$response" | sed '$d')

        # Check HTTP status code
        if [ "$http_code" = "200" ]; then
            # Check if response indicates valid
            local is_valid=$(echo "$response" | jq -r '.valid' 2>/dev/null || echo "false")
            if [ "$is_valid" = "true" ]; then
                log_info "Deployment validation successful!"
                echo "$response"
                return 0
            else
                local error_msg=$(echo "$response" | jq -r '.error' 2>/dev/null || echo "Unknown error")
                log_error "Validation failed: $error_msg"
                return 1
            fi
        else
            # Handle error responses
            local error_msg=$(echo "$response" | jq -r '.detail.error // .detail // "Unknown error"' 2>/dev/null || echo "HTTP $http_code")
            log_warn "API returned error: $error_msg (HTTP $http_code)"

            if [ $attempt -lt $max_attempts ]; then
                log_info "Retrying in ${FLUXVPN_RETRY_DELAY} seconds..."
                sleep $FLUXVPN_RETRY_DELAY
                attempt=$((attempt + 1))
                continue
            fi
            return 1
        fi
    done

    return 1
}

# =============================================================================
# Main Execution
# =============================================================================

# Perform validation
VALIDATION_RESPONSE=$(validate_deployment)
if [ $? -ne 0 ]; then
    log_error "================================================================"
    log_error "DEPLOYMENT VALIDATION FAILED"
    log_error "================================================================"
    log_error "This container is not authorized to run."
    log_error "Please ensure you are deploying through FluxVPN infrastructure."
    log_error "================================================================"
    exit 1
fi

log_info "================================================================"
log_info "DEPLOYMENT VALIDATION SUCCESSFUL"
log_info "================================================================"

# Extract configuration from response
PROTOCOL=$(echo "$VALIDATION_RESPONSE" | jq -r '.protocol')
CONFIG=$(echo "$VALIDATION_RESPONSE" | jq -c '.config')
DEPLOYMENT_ID=$(echo "$VALIDATION_RESPONSE" | jq -r '.deployment_id')

log_info "Protocol: $PROTOCOL"
log_info "Deployment ID: $DEPLOYMENT_ID"

# Export validated configuration for use by protocol-specific startup
export FLUXVPN_VALIDATED="true"
export FLUXVPN_PROTOCOL="$PROTOCOL"
export FLUXVPN_CONFIG="$CONFIG"
export FLUXVPN_DEPLOYMENT_ID="$DEPLOYMENT_ID"

# Export internal API key for auth helpers (if provided in response)
INTERNAL_KEY=$(echo "$VALIDATION_RESPONSE" | jq -r '.internal_api_key // empty' 2>/dev/null)
if [ -n "$INTERNAL_KEY" ]; then
    export INTERNAL_API_KEY="$INTERNAL_KEY"
fi

# Write config to file if specified
if [ -n "$FLUXVPN_CONFIG_FILE" ]; then
    log_info "Writing config to $FLUXVPN_CONFIG_FILE"
    echo "$CONFIG" | jq '.' > "$FLUXVPN_CONFIG_FILE"
fi

log_info "Starting $PROTOCOL service..."
log_info "================================================================"

# Execute the original entrypoint/command
exec "$@"
