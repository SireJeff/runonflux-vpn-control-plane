# =============================================================================
# FluxVPN SSH Tunnel Docker Image (API-based Auth)
# =============================================================================
# Base: Alpine Linux with OpenSSH
# Auth: Periodic user sync via Worker API (creates system accounts)
# Note: Alpine openssh-server is not compiled with PAM support
# =============================================================================

FROM alpine:3.19

# Install dependencies
RUN apk add --no-cache \
    curl \
    jq \
    bash \
    python3 \
    openssh-server \
    netcat-openbsd \
    shadow \
    iptables

# Create app directory
WORKDIR /app

# Copy entrypoint wrapper (copied from base/ during build process)
COPY entrypoint-wrapper.sh /usr/local/bin/entrypoint-wrapper.sh
RUN chmod +x /usr/local/bin/entrypoint-wrapper.sh

# Copy telemetry sidecar (copied from base/ during build process)
COPY telemetry_server.py /usr/local/bin/telemetry_server.py
COPY telemetry_helpers.sh /usr/local/bin/telemetry_helpers.sh
RUN chmod +x /usr/local/bin/telemetry_helpers.sh

# Copy auth helpers (copied from base/ during build process)
COPY vpn_pam_auth.sh /usr/local/bin/vpn_pam_auth.sh
COPY vpn_auth_sync.sh /usr/local/bin/vpn_auth_sync.sh
RUN chmod +x /usr/local/bin/vpn_pam_auth.sh /usr/local/bin/vpn_auth_sync.sh

# Copy protocol-specific startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment variables (set by FluxCloud deployment)
ENV FLUXVPN_CONFIG_FILE=/app/config.json

# Expose ports
EXPOSE 2222/tcp
EXPOSE 9090/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD PORT=$(jq -r '.port // 2222' /app/config.json 2>/dev/null || echo 2222) && nc -z localhost $PORT || exit 1

# Use FluxVPN entrypoint wrapper which validates deployment
ENTRYPOINT ["/usr/local/bin/entrypoint-wrapper.sh"]
CMD ["/usr/local/bin/start.sh"]
