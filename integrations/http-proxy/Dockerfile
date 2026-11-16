# =============================================================================
# FluxVPN HTTP Proxy Docker Image (API-based Auth)
# =============================================================================
# Base: ubuntu/squid
# Auth: Custom Squid auth helper validates against Worker API
# =============================================================================

FROM ubuntu/squid:latest

# Switch to root for package installation
USER root

# Install dependencies for auth validation
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    bash \
    python3 \
    apache2-utils \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

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
COPY vpn_squid_auth.sh /usr/local/bin/vpn_squid_auth.sh
COPY vpn_auth_sync.sh /usr/local/bin/vpn_auth_sync.sh
RUN chmod +x /usr/local/bin/vpn_squid_auth.sh /usr/local/bin/vpn_auth_sync.sh

# Copy protocol-specific startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment variables (set by FluxCloud deployment)
ENV FLUXVPN_CONFIG_FILE=/app/config.json

# Expose port
EXPOSE 3128/tcp
EXPOSE 9095/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep squid >/dev/null || exit 1

# Use FluxVPN entrypoint wrapper which validates deployment
ENTRYPOINT ["/usr/local/bin/entrypoint-wrapper.sh"]
CMD ["/usr/local/bin/start.sh"]
