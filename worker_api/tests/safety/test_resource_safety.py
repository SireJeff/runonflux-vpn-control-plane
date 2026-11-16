"""Hermetic safety regressions: run with --confcutdir=tests/safety.

These tests never import the application's database/cache implementation.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from test_support.resource_safety import UnsafeTestTargetError, prepare_test_environment


def synthetic_environment(**overrides):
    """Synthetic configuration only; no resource is created or contacted."""
    return {
        "TEST_DATABASE_URL": "postgresql://tester:synthetic@postgres-test/fluxvpn_test",
        "TEST_REDIS_URL": "redis://redis-test:6379/15",
        **overrides,
    }


@pytest.mark.parametrize("key", ["TEST_DATABASE_URL", "TEST_REDIS_URL"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_requires_both_explicit_nonempty_targets(key, value):
    environment = synthetic_environment()
    if value is None:
        environment.pop(key)
    else:
        environment[key] = value
    original = environment.copy()
    with pytest.raises(UnsafeTestTargetError, match=key):
        prepare_test_environment(environment)
    assert environment == original


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost/application",
        "postgresql://localhost/not_testing",
        "postgresql://production.invalid/fluxvpn_test",
        "postgresql:///fluxvpn_test",
        "postgresql://localhost/fluxvpn_test?host=production.invalid",
        "postgresql://localhost/fluxvpn_test?dbname=application",
        "postgresql://localhost/fluxvpn_test?",
        "postgresql://localhost/fluxvpn_test#application",
        "postgresql://localhost:bad/fluxvpn_test",
        "postgresql://localhost:0/fluxvpn_test",
        "postgresql://localhost/fluxvpn_test%2Fapplication",
        "sqlite:///application_test.sqlite",
        "postgresql://localhost/fluxvpn_test\n",
        "postgresql://[broken/fluxvpn_test",
    ],
)
def test_rejects_unsafe_database_urls(url):
    environment = synthetic_environment(TEST_DATABASE_URL=url)
    with pytest.raises(UnsafeTestTargetError, match="TEST_DATABASE_URL"):
        prepare_test_environment(environment)


@pytest.mark.parametrize(
    "url",
    [
        "redis://localhost:6379/0",
        "redis://localhost:6379",
        "redis://localhost:6379/",
        "redis://localhost:6379/-1",
        "redis://localhost:6379/16",
        "redis://localhost:6379/1?db=0",
        "redis://localhost:6379/1?host=production.invalid",
        "redis://localhost:6379/1#0",
        "redis://production.invalid:6379/1",
        "redis://localhost:99999/1",
        "redis://localhost:0/1",
        "unix:///var/run/redis.sock?db=1",
        "http://localhost:6379/1",
        "redis://localhost:6379/%31",
    ],
)
def test_rejects_unsafe_redis_urls(url):
    environment = synthetic_environment(TEST_REDIS_URL=url)
    with pytest.raises(UnsafeTestTargetError, match="TEST_REDIS_URL"):
        prepare_test_environment(environment)


@pytest.mark.parametrize(
    "application_url,test_url",
    [
        (
            "postgresql://owner:synthetic@localhost:5432/fluxvpn_test",
            "postgresql+psycopg2://tester:different@127.0.0.1/fluxvpn_test",
        ),
        (
            "postgresql://localhost/fluxvpn_test",
            "postgresql://[::1]:5432/fluxvpn_test",
        ),
        (
            "postgresql://localhost/fluxvpn_test",
            "postgresql://localhost/fluxvpn%5Ftest",
        ),
        (
            "postgresql://[0:0:0:0:0:0:0:1]/fluxvpn_test",
            "postgresql://localhost/fluxvpn_test",
        ),
        (
            "postgresql://[::ffff:127.0.0.1]/fluxvpn_test",
            "postgresql://127.0.0.1/fluxvpn_test",
        ),
    ],
)
def test_rejects_database_identity_aliases(application_url, test_url):
    environment = synthetic_environment(
        DATABASE_URL=application_url, TEST_DATABASE_URL=test_url
    )
    with pytest.raises(UnsafeTestTargetError, match="application database"):
        prepare_test_environment(environment)


@pytest.mark.parametrize(
    "application_url,test_url",
    [
        ("redis://localhost:6379/1", "redis://127.0.0.1/01"),
        ("redis://user:synthetic@localhost/15", "redis://other:new@[::1]:6379/15"),
        ("rediss://localhost:6379/1", "redis://localhost/1"),
        ("redis://[0:0:0:0:0:0:0:1]/15", "redis://localhost/15"),
        ("redis://[::ffff:127.0.0.1]/15", "redis://127.0.0.1/15"),
    ],
)
def test_rejects_redis_identity_aliases(application_url, test_url):
    environment = synthetic_environment(
        REDIS_URL=application_url, TEST_REDIS_URL=test_url
    )
    with pytest.raises(UnsafeTestTargetError, match="application Redis"):
        prepare_test_environment(environment)


@pytest.mark.parametrize(
    "key,value",
    [
        ("DATABASE_URL", "postgresql://localhost/application?host=production.invalid"),
        ("REDIS_URL", "redis://localhost/1?db=15"),
        ("DATABASE_URL", "not-a-url"),
    ],
)
def test_rejects_ambiguous_application_configuration(key, value):
    with pytest.raises(UnsafeTestTargetError, match=key):
        prepare_test_environment(synthetic_environment(**{key: value}))


def test_applies_only_validated_targets_after_both_pass():
    environment = synthetic_environment(
        DATABASE_URL="postgresql://localhost/application",
        REDIS_URL="redis://localhost/0",
        ENVIRONMENT="development",
    )
    targets = prepare_test_environment(environment)
    assert environment["DATABASE_URL"] == (
        "postgresql://tester:synthetic@postgres-test/fluxvpn_test"
    )
    assert environment["REDIS_URL"] == "redis://redis-test:6379/15"
    assert environment["ENVIRONMENT"] == "test"
    environment["DATABASE_URL"] = "postgresql://localhost/application"
    assert targets.database_url.endswith("/fluxvpn_test")
    assert "synthetic" not in repr(targets)


def test_second_target_failure_leaves_first_and_environment_unchanged():
    environment = synthetic_environment(
        DATABASE_URL="postgresql://localhost/application",
        REDIS_URL="redis://localhost/0",
        TEST_REDIS_URL="redis://localhost/0",
        ENVIRONMENT="development",
    )
    original = environment.copy()
    with pytest.raises(UnsafeTestTargetError):
        prepare_test_environment(environment)
    assert environment == original


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "test-postgres"])
def test_accepts_explicit_local_test_resources(host):
    environment = synthetic_environment(
        TEST_DATABASE_URL=f"postgresql://{host}:5432/test_fluxvpn"
    )
    assert prepare_test_environment(environment).database_url.endswith("/test_fluxvpn")


@pytest.mark.parametrize("key", ["TEST_DATABASE_URL", "TEST_REDIS_URL", "DATABASE_URL"])
def test_errors_never_echo_url_credentials(key):
    secret = "SYNTHETIC_DO_NOT_ECHO"
    environment = synthetic_environment(
        **{
            key: f"postgresql://tester:{secret}@production.invalid/application?host=other"
        }
    )
    with pytest.raises(UnsafeTestTargetError) as exc:
        prepare_test_environment(environment)
    assert secret not in str(exc.value)
    assert "production.invalid" not in str(exc.value)


def test_unsafe_conftest_rejected_before_service_imports(tmp_path):
    """A removed/late guard must fail without ever reaching a service import."""
    database = tmp_path / "application.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('untouched')")
    environment = os.environ.copy()
    for key in ("TEST_DATABASE_URL", "TEST_REDIS_URL"):
        environment.pop(key, None)
    environment["DATABASE_URL"] = "sqlite:///" + database.as_posix()
    environment["REDIS_URL"] = "redis://localhost:6379/0"
    code = """
import importlib.abc
import runpy
import sys
class BlockServices(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'app', 'sqlalchemy', 'redis'}:
            raise RuntimeError('UNSAFE_SERVICE_IMPORT')
sys.meta_path.insert(0, BlockServices())
try:
    runpy.run_path('tests/conftest.py')
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc))
    sys.exit(2)
sys.exit(3)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "UNSAFE_SERVICE_IMPORT" not in result.stdout + result.stderr
    assert "TEST_DATABASE_URL" in result.stdout
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchall() == [
            ("untouched",)
        ]
