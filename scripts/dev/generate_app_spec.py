#!/usr/bin/env python3
"""Generate a FluxVPN deployment spec + per-protocol env for a new regional app.

Committable: contains NO secrets. Reads FLUXVPN_SECRET_KEY from scripts/_secrets.py
only at CLI runtime. Token-bearing OUTPUT is written to a gitignored path
(scripts/_generated/<app>/) — never commit generator output.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets as _rand
import sys
import uuid
from datetime import datetime, timedelta

FLUXVPN_API_URL = "https://api.operator7.example.invalid"
TOKEN_EXPIRY_YEARS = 10

# Canonical protocol table. token_proto -> token payload + FLUXVPN_INSTANCE_ID
# suffix + Flux component name (matches the ch-zur-01 reference). port_key ->
# FluxAppRegistration.protocol_ports key read by
# connection_string_service.PROTOCOL_ORDER = [ssh, ss, vless, trojan, outline, http_proxy].
# `ram` is the per-component Flux RAM (MB). Shadowsocks needs 300 (not 100):
# xray + its Python telemetry sidecar exceed 100MB even at idle, OOM-cycling
# the container (confirmed live on as01/na01/row01 2026-07-17; see ss_oom_gotcha).
# The other five idle cleanly at 100MB.
PROTOCOLS = [
    {"token_proto": "ssh",         "port_key": "ssh",        "telemetry": 9090, "ram": 100},
    {"token_proto": "shadowsocks", "port_key": "ss",         "telemetry": 9091, "ram": 300},
    {"token_proto": "vless",       "port_key": "vless",      "telemetry": 9092, "ram": 100},
    {"token_proto": "trojan",      "port_key": "trojan",     "telemetry": 9093, "ram": 100},
    {"token_proto": "outline",     "port_key": "outline",    "telemetry": 9094, "ram": 100},
    {"token_proto": "http-proxy",  "port_key": "http_proxy", "telemetry": 9095, "ram": 100},
]


def generate_token(secret_key, deployment_id, protocol, instance_id, now,
                   expiry_years=TOKEN_EXPIRY_YEARS):
    """Signed deployment token: base64url(payload) + '.' + base64url(hmac).rstrip('=').

    Payload padding is KEPT; signature padding is stripped — matches the worker
    API's DeploymentTokenService._sign and the ch-zur-01 reference tokens.
    """
    expiry = now + timedelta(days=expiry_years * 365)
    payload = {
        "deployment_id": deployment_id,
        "protocol": protocol,
        "instance_id": instance_id,
        "created_at": now.isoformat() + "Z",
        "expires_at": expiry.isoformat() + "Z",
        "nonce": _rand.token_hex(16),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    sig = hmac.new(secret_key.encode(), payload_b64.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{payload_b64}.{sig_b64}"


def build_protocol_env(app_name, proto_row, token):
    instance_id = f"{app_name}-{proto_row['token_proto']}"
    return [
        f"FLUXVPN_AUTH_TOKEN={token}",
        f"FLUXVPN_API_URL={FLUXVPN_API_URL}",
        f"FLUXVPN_INSTANCE_ID={instance_id}",
        f"TELEMETRY_PORT={proto_row['telemetry']}",
    ]


def build_protocol_ports(app_name, port_map, socks5_port=None):
    key_by_token = {p["token_proto"]: p["port_key"] for p in PROTOCOLS}
    ports = {}
    for token_proto, external_port in port_map.items():
        if token_proto not in key_by_token:
            raise ValueError(f"unknown protocol '{token_proto}' in port_map")
        ports[key_by_token[token_proto]] = external_port
    if socks5_port is not None:
        ports["socks5"] = socks5_port
    return ports


def _build_flux_component(app_name, proto_row, token, external_port):
    """One Flux v8 compose component. Container-internal ports follow the
    ch-zur-01 reference; external ports come from the user's Flux reservation."""
    instance_id = f"{app_name}-{proto_row['token_proto']}"
    return {
        "name": proto_row["token_proto"].replace("-", ""),
        "description": f"FluxVPN {proto_row['token_proto'].upper()}",
        "repotag": f"sandmanshiri/{proto_row['token_proto']}:latest",
        "ports": [external_port],
        "domains": [""],
        "environmentParameters": build_protocol_env(app_name, proto_row, token),
        "commands": [],
        "containerData": f"/data/{proto_row['token_proto']}",
        "cpu": 0.1,
        "ram": proto_row.get("ram", 100),
        "hdd": 2,
        "repoauth": "",
        "secrets": "",
    }


def build_flux_spec(app_name, port_map, tokens, geolocation=None, instances=6):
    compose = []
    for row in PROTOCOLS:
        token_proto = row["token_proto"]
        compose.append(
            _build_flux_component(
                app_name, row, tokens[token_proto], port_map[token_proto]
            )
        )
    return {
        "name": app_name,
        "compose": compose,
        "description": f"FluxVPN Multi-Protocol VPN Service ({app_name}) - 6 Protocols",
        "enterprise": "",
        "expire": 92637,
        "geolocation": geolocation or [],
        "instances": instances,
        "nodes": [],
        "owner": "1xw845H9vKEjvcghMiYFy3htnBay7KpN9",
        "staticip": False,
        "version": 8,
    }


def generate_app(app_name, port_map, now, geolocation=None, instances=6,
                 socks5_port=None, secret_key=None):
    secret_key = secret_key or _load_secret_key()
    env = {}
    tokens = {}
    for row in PROTOCOLS:
        token_proto = row["token_proto"]
        deployment_id = str(uuid.uuid4())
        instance_id = f"{app_name}-{token_proto}"
        token = generate_token(
            secret_key=secret_key,
            deployment_id=deployment_id,
            protocol=token_proto,
            instance_id=instance_id,
            now=now,
        )
        tokens[token_proto] = token
        env[token_proto] = build_protocol_env(app_name, row, token)
    return {
        "env": env,
        "tokens": tokens,
        "protocol_ports": build_protocol_ports(app_name, port_map, socks5_port),
        "flux_spec": build_flux_spec(app_name, port_map, tokens, geolocation, instances),
    }


def _load_secret_key():
    """Read only the caller's explicitly supplied key; no private ops module."""
    key = os.environ.get("FLUXVPN_SECRET_KEY", "")
    if not key:
        raise ValueError("FLUXVPN_SECRET_KEY is required for local token generation")
    return key


def write_output(result, app_name, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for token_proto, env in result["env"].items():
        path = os.path.join(out_dir, f"{token_proto}.json")
        with open(path, "w") as f:
            json.dump(env, f, indent=2)
        written.append(path)
    for name, obj in (("protocol_ports", result["protocol_ports"]),
                      ("flux_spec", result["flux_spec"])):
        path = os.path.join(out_dir, f"{name}.json")
        with open(path, "w") as f:
            json.dump(obj, f, indent=2)
        written.append(path)
    return written


def _parse_port_map(pairs):
    """['ssh=34568', 'shadowsocks=37734', ...] -> {token_proto: int}."""
    port_map = {}
    for pair in pairs:
        proto, _, port = pair.partition("=")
        port_map[proto.strip()] = int(port)
    return port_map


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate a FluxVPN regional app spec.")
    parser.add_argument("--app", required=True, help="App name, e.g. as01")
    parser.add_argument(
        "--port", action="append", default=[], metavar="PROTO=PORT",
        help="External port per protocol (repeatable), e.g. --port ssh=34568 "
             "--port shadowsocks=37734. token_proto keys: "
             "ssh shadowsocks vless trojan outline http-proxy",
    )
    parser.add_argument("--socks5", type=int, default=None, help="Optional SSH SOCKS port")
    parser.add_argument("--geo", action="append", default=[],
                        help="Flux geolocation entry (repeatable)")
    parser.add_argument("--instances", type=int, default=6)
    parser.add_argument(
        "--out", default=None,
        help="Output dir (default: scripts/_generated/<app>/ — gitignored)",
    )
    args = parser.parse_args(argv)

    port_map = _parse_port_map(args.port)
    missing = [p["token_proto"] for p in PROTOCOLS if p["token_proto"] not in port_map]
    if missing:
        parser.error(f"missing --port for: {', '.join(missing)}")

    now = datetime.utcnow()
    result = generate_app(
        app_name=args.app,
        port_map=port_map,
        now=now,
        geolocation=args.geo,
        instances=args.instances,
        socks5_port=args.socks5,
    )

    scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out or os.path.join(scripts_dir, "_generated", args.app)
    written = write_output(result, args.app, out_dir)

    print(f"Wrote {len(written)} files to {out_dir}")
    print("protocol_ports (for POST /super/apps):")
    print(json.dumps(result["protocol_ports"], indent=2))
    print("\nWARNING: output contains bearer deployment tokens — never commit it.")


if __name__ == "__main__":
    main()
