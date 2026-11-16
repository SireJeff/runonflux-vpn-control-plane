"""Unit tests for scripts/dev/generate_app_spec.py.

Hermetic (stdlib only): imports the generator by file path and re-derives the
production token scheme independently. No worker_api import, no scripts/_secrets
needed, so it runs anywhere via `pytest`.

The stronger guarantee — that a token signed with the REAL FLUXVPN_SECRET_KEY
validates under the production DeploymentTokenService — is confirmed separately
by the controller via a `docker exec` round-trip into the live worker_api
container (see the plan's "real-validator oracle" step). worker_api is only
importable on the VM, so that check is intentionally NOT a committed test.
"""
import base64
import hashlib
import hmac
import importlib.util
import json
import os
from datetime import datetime, timedelta

# --- locate repo root: worker_api/tests/unit/ -> repo root is three levels up ---
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_GEN_PATH = os.path.join(_REPO_ROOT, "scripts", "dev", "generate_app_spec.py")


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = _load_module(_GEN_PATH, "generate_app_spec")

# A dummy key: these tests verify the signing SCHEME, not the real secret. The
# real key is exercised only by the controller's docker-exec oracle round-trip.
TEST_KEY = "test-secret-key-not-a-real-secret"


def _expected_sig(payload_b64: str, key: str) -> str:
    """Re-implements DeploymentTokenService._sign: HMAC-SHA256, urlsafe b64,
    signature padding stripped."""
    sig = hmac.new(key.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def test_token_signature_matches_production_scheme():
    """The generated token carries an independently-recomputed HMAC-SHA256
    signature; payload padding kept, signature padding stripped; payload fields
    and 10-year expiry are correct."""
    now = datetime(2026, 7, 17, 12, 0, 0)
    token = gen.generate_token(
        secret_key=TEST_KEY,
        deployment_id="11111111-1111-4111-8111-111111111111",
        protocol="shadowsocks",
        instance_id="as01-shadowsocks",
        now=now,
    )
    payload_b64, sig = token.split(".")
    assert sig == _expected_sig(payload_b64, TEST_KEY)
    assert not sig.endswith("=")  # signature padding stripped

    payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()))
    assert payload["protocol"] == "shadowsocks"
    assert payload["instance_id"] == "as01-shadowsocks"
    assert payload["deployment_id"] == "11111111-1111-4111-8111-111111111111"
    assert len(payload["nonce"]) == 32  # secrets.token_hex(16)
    assert payload["created_at"] == now.isoformat() + "Z"
    assert payload["expires_at"] == (now + timedelta(days=10 * 365)).isoformat() + "Z"


def test_protocol_table_matches_two_naming_spaces():
    by_token = {p["token_proto"]: p for p in gen.PROTOCOLS}
    assert by_token["shadowsocks"]["port_key"] == "ss"
    assert by_token["http-proxy"]["port_key"] == "http_proxy"
    # telemetry port map, fixed
    assert {p["token_proto"]: p["telemetry"] for p in gen.PROTOCOLS} == {
        "ssh": 9090,
        "shadowsocks": 9091,
        "vless": 9092,
        "trojan": 9093,
        "outline": 9094,
        "http-proxy": 9095,
    }


def test_build_protocol_env_matches_reference_shape():
    row = {"token_proto": "ssh", "port_key": "ssh", "telemetry": 9090}
    env = gen.build_protocol_env("as01", row, "TOK.SIG")
    assert env == [
        "FLUXVPN_AUTH_TOKEN=TOK.SIG",
        "FLUXVPN_API_URL=https://api.operator7.example.invalid",
        "FLUXVPN_INSTANCE_ID=as01-ssh",
        "TELEMETRY_PORT=9090",
    ]


def test_protocol_ports_uses_connection_string_keys():
    port_map = {
        "ssh": 34568,
        "shadowsocks": 37734,
        "vless": 31443,
        "trojan": 38443,
        "outline": 39443,
        "http-proxy": 33128,
    }
    ports = gen.build_protocol_ports("as01", port_map, socks5_port=31080)
    assert ports == {
        "ssh": 34568,
        "ss": 37734,
        "vless": 31443,
        "trojan": 38443,
        "outline": 39443,
        "http_proxy": 33128,
        "socks5": 31080,
    }


def test_generate_app_assigns_unique_deployment_id_per_protocol():
    port_map = {p["token_proto"]: 30000 + i for i, p in enumerate(gen.PROTOCOLS)}
    now = datetime(2026, 7, 17, 12, 0, 0)
    # pass secret_key explicitly to stay hermetic (no scripts/_secrets read)
    out = gen.generate_app("as01", port_map, now=now, secret_key=TEST_KEY)
    # every protocol present in env + tokens
    assert set(out["env"]) == {p["token_proto"] for p in gen.PROTOCOLS}
    # unique deployment_id per protocol (decode payloads)
    ids = set()
    for proto, token in out["tokens"].items():
        payload_b64 = token.split(".")[0]
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()))
        assert payload["instance_id"] == f"as01-{proto}"
        ids.add(payload["deployment_id"])
    assert len(ids) == len(gen.PROTOCOLS)


def test_flux_spec_ram_shadowsocks_300_others_100():
    """SS gets 300MB (xray+telemetry OOM at 100MB); the other five stay 100MB."""
    port_map = {p["token_proto"]: 30000 + i for i, p in enumerate(gen.PROTOCOLS)}
    now = datetime(2026, 7, 17, 12, 0, 0)
    out = gen.generate_app("as01", port_map, now=now, secret_key=TEST_KEY)
    ram_by_component = {c["name"]: c["ram"] for c in out["flux_spec"]["compose"]}
    # component names are token_proto with hyphens stripped (shadowsocks, httpproxy)
    assert ram_by_component["shadowsocks"] == 300
    for name, ram in ram_by_component.items():
        if name != "shadowsocks":
            assert ram == 100, f"{name} should be 100MB, got {ram}"
    # cpu/hdd unchanged across all components
    assert all(c["cpu"] == 0.1 and c["hdd"] == 2 for c in out["flux_spec"]["compose"])


def test_write_output_creates_gitignored_artifacts(tmp_path):
    port_map = {p["token_proto"]: 30000 + i for i, p in enumerate(gen.PROTOCOLS)}
    now = datetime(2026, 7, 17, 12, 0, 0)
    result = gen.generate_app("as01", port_map, now=now, secret_key=TEST_KEY)
    paths = gen.write_output(result, "as01", str(tmp_path))
    names = {os.path.basename(p) for p in paths}
    # one env file per protocol + protocol_ports.json + flux_spec.json
    assert "protocol_ports.json" in names
    assert "flux_spec.json" in names
    assert "ssh.json" in names and "http-proxy.json" in names
    # env file content matches the reference 4-line array
    import json as _json

    with open(os.path.join(str(tmp_path), "ssh.json")) as f:
        ssh_env = _json.load(f)
    assert ssh_env[1] == "FLUXVPN_API_URL=https://api.operator7.example.invalid"
    assert ssh_env[2] == "FLUXVPN_INSTANCE_ID=as01-ssh"
