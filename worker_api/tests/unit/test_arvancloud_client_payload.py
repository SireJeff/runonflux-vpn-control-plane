"""ArvanCloud DNS client payload + ensure_record_exists reconcile (#388, #402).

#388: the create/update payload must be a PLAIN single-IP A record with NO
load-balance fields (port/weight/country).

#402: ensure_record_exists must reconcile by NAME before creating. When
dns_record_id is None, a record may already exist on Arvan (orphan: id lost
from our DB). Blind-POSTing a create makes a same-name duplicate, which Arvan
classifies as "load balance" and the Basic (free) plan rejects -- the
self-reinforcing failure that kept #10's 4 domains dark. The fix looks the
record up by name and UPDATEs it (repairing the lost id via the caller's
persistence) instead of duplicate-creating.

Pure unit tests — no DB, no network (aiohttp methods are AsyncMocked).
"""
import asyncio
from unittest.mock import AsyncMock

from app.services.fdm.arvancloud_client import ArvanCloudDnsClient


def _client():
    return ArvanCloudDnsClient(api_key="test-key", domain="operator1.example.invalid")


def test_arvan_payload_is_plain_a_record_with_no_lb_fields():
    client = _client()
    payload = client._build_dns_record_payload(
        "us-01-a1.operator1.example.invalid", "203.0.113.5", 120
    )

    assert payload["type"] == "a"
    assert payload["name"] == "us-01-a1"  # zone suffix stripped
    assert payload["ttl"] == 120
    assert payload["cloud"] is False

    # single-IP A record — NO load-balance signaling
    assert payload["value"] == [{"ip": "203.0.113.5"}]
    member = payload["value"][0]
    for lb_field in ("port", "weight", "country"):
        assert (
            lb_field not in member
        ), f"LB field {lb_field!r} must not be sent (triggers 405 on Basic plan)"


def test_arvan_payload_snaps_invalid_ttl_through_helper():
    """TTL outside ArvanCloud's allowed set still snaps via _snap_ttl."""
    client = _client()
    # 200 is not in VALID_TTLS; nearest is 180
    payload = client._build_dns_record_payload("x.operator1.example.invalid", "203.0.113.5", 200)
    assert payload["ttl"] == 180


def test_ensure_record_exists_updates_orphan_by_name_instead_of_duplicate_create():
    """#402: dns_record_id is None but an orphan Arvan record exists for the name
    (id lost from our DB). ensure_record_exists must look it up by name and UPDATE
    it -- NOT POST a create, which Arvan rejects as load-balance on the Basic plan
    (the self-reinforcing failure that kept #10's 4 domains dark)."""
    client = _client()
    client.find_a_record_by_name = AsyncMock(
        return_value={"id": "orphan-uuid", "name": "img-06", "content": "1.2.3.4"}
    )
    client.update_dns_record = AsyncMock(
        return_value={"id": "orphan-uuid", "name": "img-06", "content": "9.9.9.9"}
    )
    client.create_dns_record = AsyncMock(return_value={"id": "should-not-happen"})

    result = asyncio.run(
        client.ensure_record_exists(
            name="img-06", ip="9.9.9.9", existing_record_id=None
        )
    )

    client.find_a_record_by_name.assert_awaited_once_with("img-06")
    client.update_dns_record.assert_awaited_once_with(
        "orphan-uuid", "img-06", "9.9.9.9", 120
    )
    client.create_dns_record.assert_not_awaited()
    assert result["id"] == "orphan-uuid"


def test_ensure_record_exists_creates_when_no_id_and_no_existing_record():
    """#402: no known id and no orphan by name -> genuine create (the happy path
    for a brand-new subdomain)."""
    client = _client()
    client.find_a_record_by_name = AsyncMock(return_value=None)
    client.update_dns_record = AsyncMock(return_value={"id": "x"})
    client.create_dns_record = AsyncMock(return_value={"id": "new-uuid"})

    result = asyncio.run(
        client.ensure_record_exists(
            name="brand-new", ip="9.9.9.9", existing_record_id=None
        )
    )

    client.find_a_record_by_name.assert_awaited_once_with("brand-new")
    client.create_dns_record.assert_awaited_once_with("brand-new", "9.9.9.9", 120)
    client.update_dns_record.assert_not_awaited()
    assert result["id"] == "new-uuid"
