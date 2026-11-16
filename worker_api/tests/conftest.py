"""
Pytest configuration and shared fixtures for FluxVPN tests
"""

import os
from decimal import Decimal
from typing import Generator

import pytest
from test_support.resource_safety import UnsafeTestTargetError, prepare_test_environment

# Validate before importing any service/application module. Never inherit app
# targets or synthesize consent from ENVIRONMENT=test or a pytest marker.
try:
    _TEST_TARGETS = prepare_test_environment(os.environ)
except UnsafeTestTargetError as exc:
    raise pytest.UsageError(str(exc)) from None

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
os.environ["JWT_SECRET_KEY"] = "test_secret_key_for_unit_tests"
os.environ["INTERNAL_API_KEY"] = "test_internal_api_key"
os.environ["FLUX_WALLET_ADDRESS"] = "test_wallet_address"
os.environ[
    "FLUX_WALLET_PRIVATE_KEY"
] = "0x0000000000000000000000000000000000000000000000000000000000000001"
os.environ["SUPER_ADMIN_PASSWORD"] = "test_super_admin_password"

from app import models as _all_models  # noqa: E402,F401  # Register all model metadata
from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models import ProtocolInstance, UserCredential  # noqa: E402

_METADATA_LOGGER_PREFIX = "[tests.conftest]"

# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture(scope="session")
def engine():
    """
    Create a test database engine (session-scoped)
    Uses StaticPool to share connection across tests
    """
    test_engine = create_engine(
        _TEST_TARGETS.database_url,
        poolclass=StaticPool,
        echo=False,  # Set to True for SQL debugging
    )
    return test_engine


@pytest.fixture(scope="session")
def tables(engine):
    """
    Create all database tables before tests, drop after
    Session-scoped: tables persist across all tests
    """
    # Start every run from a clean slate.
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine, checkfirst=True)
    yield
    try:
        Base.metadata.drop_all(bind=engine, checkfirst=True)
    except SQLAlchemyError as exc:
        # Some test modules perform hard-deletes and schema mutations that can
        # race table dependency ordering during teardown.
        print(f"{_METADATA_LOGGER_PREFIX} teardown drop_all failed: {exc}")


@pytest.fixture(scope="function")
def db_session(engine, tables) -> Generator[Session, None, None]:
    """
    Create a new database session for each test
    Function-scoped: each test gets a fresh session
    Automatically rolls back after each test
    """
    connection = engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def db(db_session) -> Generator[Session, None, None]:
    """
    Alias for db_session (shorter name for convenience)
    """
    yield db_session


# ============================================================================
# REDIS FIXTURES
# ============================================================================


@pytest.fixture(scope="session")
def redis_client():
    """
    Create a Redis client for testing
    """
    import redis

    client = redis.from_url(
        _TEST_TARGETS.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    yield client
    # Clean up test data, but don't fail test teardown on optional redis outages.
    try:
        client.flushdb()
    except Exception as exc:
        print(f"{_METADATA_LOGGER_PREFIX} redis flush skipped: {exc}")
    finally:
        client.close()


# ============================================================================
# FASTAPI FIXTURES
# ============================================================================


@pytest.fixture(scope="module")
def app():
    """
    Create FastAPI app instance for testing
    """
    from app.main import app

    return app


@pytest.fixture(scope="function")
def client(app, db_session):
    """
    Create a test client for making HTTP requests
    """
    from fastapi.testclient import TestClient

    from app.core.database import get_db

    # Override the get_db dependency to use test database
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def internal_api_headers():
    """
    Build internal-auth headers for endpoints protected by verify_internal_api_key.
    """
    headers = {}
    if settings.INTERNAL_API_KEY:
        headers["X-Internal-API-Key"] = settings.INTERNAL_API_KEY
    return headers


# ============================================================================
# FACTORY FIXTURES
# ============================================================================


@pytest.fixture
def user_factory(db_session):
    """
    Factory for creating test users
    """
    from tests.factories import UserFactory

    return UserFactory


@pytest.fixture
def protocol_factory(db_session):
    """
    Factory for creating test protocols
    """
    from tests.factories import ProtocolFactory

    return ProtocolFactory


@pytest.fixture
def subscription_plan_factory(db_session):
    """
    Factory for creating test subscription plans
    """
    from tests.factories import SubscriptionPlanFactory

    return SubscriptionPlanFactory


@pytest.fixture
def subscription_factory(db_session):
    """
    Factory for creating test subscriptions
    """
    from tests.factories import SubscriptionFactory

    return SubscriptionFactory


# ============================================================================
# COMMON TEST DATA FIXTURES
# ============================================================================


@pytest.fixture
def test_user(db_session, user_factory):
    """
    Create a single test user
    """
    user = user_factory.create(
        telegram_user_id=12345,
        telegram_username="test_user",
        language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_admin_user(db_session, user_factory):
    """
    Create a test admin user
    """
    user = user_factory.create(
        telegram_user_id=99999,
        telegram_username="admin_user",
        is_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_admin(test_admin_user):
    """
    Backward-compatible alias used by older integration/e2e suites.
    """
    return test_admin_user


@pytest.fixture
def test_protocols(db_session, protocol_factory):
    """
    Create standard test protocols (VLESS, SSH, Clash)
    """
    protocols = [
        protocol_factory.create(name="vless", display_name="VLESS"),
        protocol_factory.create(name="ssh", display_name="SSH"),
        protocol_factory.create(name="clash", display_name="Clash"),
    ]
    for protocol in protocols:
        db_session.add(protocol)
    db_session.commit()
    for protocol in protocols:
        db_session.refresh(protocol)
    return protocols


@pytest.fixture
def test_protocol(test_protocols):
    """
    Backward-compatible single protocol fixture used by legacy tests.
    """
    protocol = test_protocols[0]
    # Older code paths expect this attribute on Protocol.
    if not hasattr(protocol, "price_usd_monthly"):
        protocol.price_usd_monthly = Decimal("9.99")
    return protocol


@pytest.fixture
def test_subscription_plans(db_session, subscription_plan_factory):
    """
    Create standard test subscription plans
    """
    plans = [
        subscription_plan_factory.create(
            name="Bronze Monthly",
            tier="bronze",
            duration_months=1,
            price_usd=5.00,
        ),
        subscription_plan_factory.create(
            name="Silver Monthly",
            tier="silver",
            duration_months=1,
            price_usd=10.00,
        ),
        subscription_plan_factory.create(
            name="Gold Monthly",
            tier="gold",
            duration_months=1,
            price_usd=20.00,
        ),
    ]
    for plan in plans:
        db_session.add(plan)
    db_session.commit()
    for plan in plans:
        db_session.refresh(plan)
    return plans


@pytest.fixture
def active_subscription(
    db_session,
    subscription_factory,
    subscription_plan_factory,
    test_user,
    test_protocol,
):
    """
    Create an active subscription for fixtures that exercise credential/IP flows.
    """
    plan = subscription_plan_factory.create(
        name="Active Test Plan",
        tier="silver",
        duration_months=1,
        price_usd=Decimal("9.99"),
        max_connections=3,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    subscription = subscription_factory.create_active(
        user_id=test_user.id,
        plan_id=plan.id,
        auto_renew=True,
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)

    # Legacy tests still reference old field names.
    subscription.protocol_id = test_protocol.id
    subscription.start_date = subscription.started_at
    subscription.end_date = subscription.expires_at
    subscription.price_usd = plan.price_usd
    return subscription


@pytest.fixture
def test_instances(db_session, test_protocol):
    """
    Create a small pool of healthy protocol instances for assignment tests.
    """
    instances = [
        ProtocolInstance(
            protocol_id=test_protocol.id,
            flux_app_name="fluxvpn-us-01",
            component_name=test_protocol.slug,
            instance_number=1,
            flux_node_name="us-nyc-01.flux.local",
            ip_address="10.10.0.10",
            country_code="US",
            country_name="United States",
            city="New York",
            health_status="healthy",
            is_active=True,
        ),
        ProtocolInstance(
            protocol_id=test_protocol.id,
            flux_app_name="fluxvpn-nl-01",
            component_name=test_protocol.slug,
            instance_number=2,
            flux_node_name="nl-ams-01.flux.local",
            ip_address="10.10.0.11",
            country_code="NL",
            country_name="Netherlands",
            city="Amsterdam",
            health_status="healthy",
            is_active=True,
        ),
        ProtocolInstance(
            protocol_id=test_protocol.id,
            flux_app_name="fluxvpn-de-01",
            component_name=test_protocol.slug,
            instance_number=3,
            flux_node_name="de-fra-01.flux.local",
            ip_address="10.10.0.12",
            country_code="DE",
            country_name="Germany",
            city="Frankfurt",
            health_status="healthy",
            is_active=True,
        ),
    ]
    for instance in instances:
        db_session.add(instance)
    db_session.commit()
    for instance in instances:
        db_session.refresh(instance)
        # Legacy tests refer to `public_ip`; current model uses `ip_address`.
        instance.public_ip = str(instance.ip_address)
        instance.ports = [test_protocol.default_port or 443]
    return instances


@pytest.fixture
def test_instance(test_instances):
    """
    Backward-compatible single instance fixture used by older tests.
    """
    return test_instances[0]


@pytest.fixture
def test_credential(
    db_session,
    test_user,
    test_protocol,
    active_subscription,
    test_instance,
):
    """
    Create a credential row with compatibility fields for legacy test modules.
    """
    credential_data = {
        "username": "test_user",
        "password": "test_password",
        "server": test_instance.public_ip,
        "server_ip": test_instance.public_ip,
        "port": 443,
        "is_active": True,
        "instance_id": test_instance.id,
        "connection_uri": f"{test_protocol.name}://test_user@test-instance:443",
    }

    credential = UserCredential(
        user_id=test_user.id,
        subscription_id=active_subscription.id,
        protocol_id=test_protocol.id,
        credential_data=credential_data,
        server_location=f"{test_instance.country_name} ({test_instance.city})",
    )
    db_session.add(credential)
    db_session.commit()
    db_session.refresh(credential)

    # Legacy attribute aliases used by old endpoint tests.
    credential.username = credential_data["username"]
    credential.password = credential_data["password"]
    credential.server_ip = credential_data["server_ip"]
    credential.port = credential_data["port"]
    credential.is_active = credential_data["is_active"]
    credential.instance_id = credential_data["instance_id"]
    return credential


# ============================================================================
# UTILITY FIXTURES
# ============================================================================


@pytest.fixture
def freeze_time():
    """
    Freeze time for testing time-dependent functionality
    """
    from freezegun import freeze_time as _freeze_time

    return _freeze_time


@pytest.fixture
def mock_flux_api(monkeypatch):
    """
    Mock FluxCloud API calls
    """

    def mock_response(*args, **kwargs):
        return {"status": "success", "data": {}}

    # This will be used to mock httpx or aiohttp calls
    return mock_response


# ============================================================================
# CLEANUP FIXTURES
# ============================================================================
# Note: Per-test cleanup is handled by `db_session`'s transaction rollback
# when a test uses it. We deliberately do NOT define an `autouse=True`
# fixture taking `db_session` here — doing so would force every test in the
# suite (including unit tests that bypass app imports via the `_bootstrap()`
# pattern) to trigger the engine → tables → db_session chain, which calls
# `create_engine()` and tries to connect to PostgreSQL. Locally that fails
# with `OperationalError: password authentication failed for user "fluxvpn"`,
# blocking all unit-test runs.


# ============================================================================
# PYTEST HOOKS
# ============================================================================


def pytest_configure(config):
    """
    Configure pytest with custom settings
    """
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "payment: mark test as payment gateway test")
    config.addinivalue_line("markers", "celery: mark test as Celery task test")


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to add markers automatically
    """
    for item in items:
        # Automatically mark tests based on their location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
