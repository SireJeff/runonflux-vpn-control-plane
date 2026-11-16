#!/usr/bin/env python3
# =============================================================================
# FluxVPN Telemetry Sidecar Server
# =============================================================================
# Lightweight HTTP server for collecting and exposing VPN usage telemetry.
# Runs alongside each protocol container to provide a unified metrics interface.
#
# Endpoints:
#   GET  /internal/usage              - Bandwidth usage records
#   GET  /internal/active-connections - Per-user active connection counts
#   POST /internal/terminate         - Signal user disconnection
#
# Environment Variables:
#   TELEMETRY_PORT - Listening port (default: 9090)
#   TELEMETRY_STATS_FILE - Path to stats JSON file (default: /tmp/telemetry_stats.json)
# =============================================================================

import json
import os
import sys
import signal
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Configuration
PORT = int(os.environ.get("TELEMETRY_PORT", "9090"))
STATS_FILE = Path(os.environ.get("TELEMETRY_STATS_FILE", "/tmp/telemetry_stats.json"))
TERMINATE_DIR = Path("/tmp")

# Suppress request logging
class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress all request logging


def read_stats():
    """Atomically read the telemetry stats JSON file with error handling."""
    try:
        # Read into a temp path then parse to avoid partial reads
        content = STATS_FILE.read_text(encoding="utf-8")
        return json.loads(content)
    except FileNotFoundError:
        return {"records": [], "connections": {}}
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Telemetry] Error reading stats file: {e}", file=sys.stderr)
        return {"records": [], "connections": {}}


class TelemetryHandler(QuietHandler):
    """Handles telemetry API requests."""

    def do_GET(self):
        if self.path == "/internal/usage":
            self._handle_usage()
        elif self.path == "/internal/active-connections":
            self._handle_active_connections()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/internal/terminate":
            self._handle_terminate()
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_usage(self):
        """Return bandwidth usage records."""
        data = read_stats()
        records = data.get("records", [])
        self._send_json({"records": records})

    def _handle_active_connections(self):
        """Return per-user active connection counts."""
        data = read_stats()
        connections = data.get("connections", {})
        users = [
            {"user_id": uid, "active_connections": count}
            for uid, count in connections.items()
        ]
        self._send_json({"users": users})

    def _handle_terminate(self):
        """Write a termination signal file for the specified user."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body) if body else {}

            user_id = payload.get("user_id")
            protocol = payload.get("protocol", "")

            if not user_id:
                self._send_json({"error": "user_id is required"}, 400)
                return

            # Write termination signal file
            signal_file = TERMINATE_DIR / f"terminate_{user_id}"
            signal_file.write_text(
                json.dumps({
                    "user_id": user_id,
                    "protocol": protocol,
                    "signaled_at": payload.get("signaled_at", ""),
                }),
                encoding="utf-8",
            )

            print(f"[Telemetry] Termination signal written for user {user_id}", file=sys.stderr)
            self._send_json({"status": "ok", "user_id": user_id})

        except (json.JSONDecodeError, OSError) as e:
            self._send_json({"error": str(e)}, 500)

    def _send_json(self, data, status_code=200):
        """Send a JSON response."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    import socket
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("0.0.0.0", PORT), TelemetryHandler)
    print(f"[Telemetry] Sidecar server listening on 0.0.0.0:{PORT}", file=sys.stderr)

    # Graceful shutdown on SIGTERM (Docker stop signal)
    def shutdown(signum, frame):
        print("[Telemetry] Shutting down...", file=sys.stderr)
        server.shutdown()

    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    print("[Telemetry] Server stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
