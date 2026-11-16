# =============================================================================
# FluxVPN VLESS/Xray Docker Image
# =============================================================================
# Base: Alpine + Xray-core (multi-user VLESS with per-user stats)
# Auth: FluxVPN Bootstrap Token Verification
# =============================================================================

FROM alpine:3.19

USER root

RUN apk add --no-cache \
    curl \
    jq \
    bash \
    python3 \
    netcat-openbsd \
    unzip \
    wget

# Download Xray-core (supports VLESS protocol natively)
RUN wget -q https://github.com/XTLS/Xray-core/releases/download/v26.3.27/Xray-linux-64.zip -O /tmp/xray.zip && \
    unzip /tmp/xray.zip -d /usr/local/bin xray && \
    chmod +x /usr/local/bin/xray && \
    rm /tmp/xray.zip

WORKDIR /app

# Copy entrypoint wrapper (copied from base/ during build process)
COPY entrypoint-wrapper.sh /usr/local/bin/entrypoint-wrapper.sh
RUN chmod +x /usr/local/bin/entrypoint-wrapper.sh

# Copy telemetry sidecar (copied from base/ during build process)
COPY telemetry_server.py /usr/local/bin/telemetry_server.py
COPY telemetry_helpers.sh /usr/local/bin/telemetry_helpers.sh
RUN chmod +x /usr/local/bin/telemetry_helpers.sh

# Copy auth helpers (copied from base/ during build process)
COPY vpn_auth_sync.sh /usr/local/bin/vpn_auth_sync.sh
RUN chmod +x /usr/local/bin/vpn_auth_sync.sh

# Copy protocol-specific startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment variables (set by FluxCloud deployment)
ENV FLUXVPN_CONFIG_FILE=/app/config.json

# Expose ports: VLESS traffic + telemetry
EXPOSE 443/tcp
EXPOSE 9092/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep xray >/dev/null || exit 1

# Use FluxVPN entrypoint wrapper which validates deployment
ENTRYPOINT ["/usr/local/bin/entrypoint-wrapper.sh"]
CMD ["/usr/local/bin/start.sh"]
