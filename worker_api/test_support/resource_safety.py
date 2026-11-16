"""Fail-closed configuration for tests that can drop tables or flush Redis.

This module is deliberately standard-library only: reject unsafe destinations
before importing application settings, SQLAlchemy, Redis or their clients.
"""

import re
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from ipaddress import IPv6Address, ip_address
from urllib.parse import SplitResult, unquote, urlsplit

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_POSTGRES_HOSTS = _LOOPBACK | {"postgres-test", "test-postgres"}
_REDIS_HOSTS = _LOOPBACK | {"redis-test", "test-redis"}
_POSTGRES_SCHEMES = {
    "postgres",
    "postgresql",
    "postgresql+psycopg2",
    "postgresql+psycopg",
}


class UnsafeTestTargetError(ValueError):
    """A test target was not explicitly safe; messages never include URLs."""


@dataclass(frozen=True)
class TestTargets:
    """Capture validated destinations without exposing credentials in repr."""

    database_url: str = field(repr=False)
    redis_url: str = field(repr=False)


def _reject(label: str, reason: str) -> None:
    raise UnsafeTestTargetError(
        f"Refusing unsafe test resources: {label} {reason}. "
        "Use the isolated scripts/test.sh runner or explicit disposable TEST_* URLs."
    ) from None


def _split(url: str, label: str, schemes: set[str]) -> SplitResult:
    try:
        parsed = urlsplit(url)
        valid = (
            bool(url)
            and url == url.strip()
            and not any(character in url for character in ("\r", "\n", "\t", "?", "#"))
            and parsed.scheme in schemes
            and bool(parsed.hostname)
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except (ValueError, TypeError):
        _reject(label, "must be an unambiguous supported URL")
    if not valid:
        _reject(label, "must be an unambiguous supported URL")
    return parsed


def _host(parsed: SplitResult) -> str:
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname in _LOOPBACK:
        return "loopback"
    try:
        address = ip_address(hostname)
    except ValueError:
        return hostname
    mapped = address.ipv4_mapped if isinstance(address, IPv6Address) else None
    if address.is_loopback or (mapped is not None and mapped.is_loopback):
        return "loopback"
    return str(address)


def _database_identity(url: str, label: str, *, test: bool) -> tuple[str, int, str]:
    parsed = _split(url, label, _POSTGRES_SCHEMES)
    name = unquote(parsed.path.removeprefix("/"))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", name):
        _reject(label, "must name one explicit PostgreSQL database")
    if test:
        if parsed.hostname not in _POSTGRES_HOSTS:
            _reject(label, "must use loopback or a dedicated PostgreSQL test service")
        if not (name.startswith("test_") or name.endswith("_test")):
            _reject(label, "database name must begin test_ or end _test")
    return _host(parsed), parsed.port or 5432, name


def _redis_identity(url: str, label: str, *, test: bool) -> tuple[str, int, int]:
    parsed = _split(url, label, {"redis", "rediss"})
    path = parsed.path
    if not test and path in {"", "/"}:
        database = 0
    elif re.fullmatch(r"/[0-9]+", path):
        database = int(path[1:])
    else:
        _reject(label, "must select one explicit numeric Redis database")
    if test:
        if parsed.hostname not in _REDIS_HOSTS:
            _reject(label, "must use loopback or a dedicated Redis test service")
        if not 1 <= database <= 15:
            _reject(label, "must select a disposable Redis database from 1 through 15")
    return _host(parsed), parsed.port or 6379, database


def prepare_test_environment(environ: MutableMapping[str, str]) -> TestTargets:
    """Validate both targets before applying any test configuration.

    Application destinations are compared without credentials/driver spelling;
    aliases must not turn a destructive test run into an application-data wipe.
    Explicit URLs and naming are safety conventions, not a sandbox against
    malicious test code. The supported runner adds disposable internal services.
    """
    database_url = environ.get("TEST_DATABASE_URL", "")
    redis_url = environ.get("TEST_REDIS_URL", "")
    database = _database_identity(database_url, "TEST_DATABASE_URL", test=True)
    redis = _redis_identity(redis_url, "TEST_REDIS_URL", test=True)
    application_database = environ.get("DATABASE_URL")
    application_redis = environ.get("REDIS_URL")
    if application_database and database == _database_identity(
        application_database, "DATABASE_URL", test=False
    ):
        _reject("TEST_DATABASE_URL", "matches the application database")
    if application_redis and redis == _redis_identity(
        application_redis, "REDIS_URL", test=False
    ):
        _reject("TEST_REDIS_URL", "matches the application Redis database")
    targets = TestTargets(database_url, redis_url)
    environ["DATABASE_URL"] = targets.database_url
    environ["REDIS_URL"] = targets.redis_url
    environ["ENVIRONMENT"] = "test"
    return targets
