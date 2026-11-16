"""Phase 4.7a: migrate_tld confirmation guard.

migrate_tld is superseded by POST /settings/tlds/{id}/activate and has no
frontend caller, but performs a destructive cascade (bulk DNS deletion +
domain rewrite) with no confirmation step. This adds a required `confirm`
field to the request schema and an early guard in the endpoint.
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest


def _run(coro):
    return asyncio.run(coro)


def test_migrate_tld_request_requires_confirm_field():
    """confirm has no default -- omitting it must fail Pydantic validation
    before the request ever reaches the endpoint body."""
    import pydantic

    from app.schemas.super_admin import MigrateTldRequest

    with pytest.raises(pydantic.ValidationError):
        MigrateTldRequest(new_domain="new.com", new_zone_id="zoneabc1234567890")


def test_migrate_tld_rejects_when_confirm_false():
    """confirm=False must raise the endpoint's own 400 before any DNS config
    lookup happens -- the guard must fire before the destructive cascade's
    first step, not after."""
    from fastapi import HTTPException

    from app.api.v1.endpoints import super_admin
    from app.schemas.super_admin import MigrateTldRequest

    request = MigrateTldRequest(
        new_domain="new.com", new_zone_id="zoneabc1234567890", confirm=False
    )
    mock_db = MagicMock()

    with patch("app.services.dns_config.get_dns_config") as mock_get_dns_config:
        with pytest.raises(HTTPException) as exc_info:
            _run(super_admin.migrate_tld(request, mock_db, {}))

    assert exc_info.value.status_code == 400
    mock_get_dns_config.assert_not_called()
