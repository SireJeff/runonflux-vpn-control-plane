from datetime import datetime, timezone

from app.models import ConnectionLog, ProtocolInstance
from app.services.credentials.credential_service import CredentialService


def _create_instance(db, protocol_id: int, app_suffix: str, country: str = "US"):
    instance = ProtocolInstance(
        protocol_id=protocol_id,
        flux_app_name=f"fluxvpn-{app_suffix}",
        component_name="ssh",
        instance_number=1,
        flux_node_name=f"node-{app_suffix}",
        ip_address="10.0.0.1" if app_suffix.endswith("1") else "10.0.0.2",
        country_code=country,
        country_name="United States" if country == "US" else "Netherlands",
        health_status="healthy",
        is_active=True,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def test_select_instance_prefers_lower_live_load(db, test_user, protocol_factory):
    protocol = protocol_factory.create(name="ssh", slug="ssh", display_name="SSH")
    db.add(protocol)
    db.commit()
    db.refresh(protocol)

    inst1 = _create_instance(db, protocol.id, "us-1", "US")
    inst2 = _create_instance(db, protocol.id, "us-2", "US")

    for _ in range(5):
        db.add(
            ConnectionLog(
                user_id=test_user.id,
                protocol_id=protocol.id,
                instance_id=inst1.id,
                connected_at=datetime.now(timezone.utc).replace(tzinfo=None),
                disconnected_at=None,
                bytes_uploaded=1,
                bytes_downloaded=1,
            )
        )
    db.commit()

    service = CredentialService(db)
    selected = service._select_instance(protocol.id)

    assert selected is not None
    assert selected.id == inst2.id


def test_select_instance_uses_preferred_country_with_weighted_load(
    db, test_user, protocol_factory
):
    protocol = protocol_factory.create(name="ssh", slug="ssh", display_name="SSH")
    db.add(protocol)
    db.commit()
    db.refresh(protocol)

    _create_instance(db, protocol.id, "us-1", "US")
    nl1 = _create_instance(db, protocol.id, "nl-1", "NL")
    nl2 = _create_instance(db, protocol.id, "nl-2", "NL")

    for _ in range(3):
        db.add(
            ConnectionLog(
                user_id=test_user.id,
                protocol_id=protocol.id,
                instance_id=nl1.id,
                connected_at=datetime.now(timezone.utc).replace(tzinfo=None),
                disconnected_at=None,
                bytes_uploaded=1,
                bytes_downloaded=1,
            )
        )
    db.commit()

    service = CredentialService(db)
    selected = service._select_instance(protocol.id, preferred_country="NL")

    assert selected is not None
    assert selected.country_code == "NL"
    assert selected.id == nl2.id
