"""Schema-level tests for WireOrderRequest (wire + crypto).

Note on the wire minimum: the 500,000-Toman minimum is NO LONGER enforced at
the schema boundary. It was relocated to the `submit_wire_order` endpoint,
which rejects amounts below the configurable `min_topup_tomans` platform
setting (default 500,000) with a 422. The schema only requires
`amount_tomans > 0` for wire orders; endpoint-level min coverage lives in the
endpoint tests (`test_wire_topup_below_min_rejected`).
"""

import pytest
from pydantic import ValidationError

from app.schemas.admin_api import WireOrderRequest


def _payload(**overrides):
    payload = {
        "amount_tomans": 500000,
        "contact_telegram": "@tester",
    }
    payload.update(overrides)
    return payload


def test_accepts_exact_minimum_500000():
    req = WireOrderRequest(**_payload(amount_tomans=500000))
    assert req.amount_tomans == 500000


def test_schema_accepts_below_500000_min_enforced_at_endpoint():
    # The schema no longer rejects sub-500k amounts; the endpoint does.
    req = WireOrderRequest(**_payload(amount_tomans=499999))
    assert req.amount_tomans == 499999
    assert req.payment_method == "wire"


def test_rejects_non_positive_amount_tomans():
    with pytest.raises(ValidationError):
        WireOrderRequest(**_payload(amount_tomans=0))


def test_crypto_requires_amount_usd_and_txid():
    with pytest.raises(ValidationError):
        WireOrderRequest(payment_method="crypto", contact_telegram="@a")  # no usd/txid
    with pytest.raises(ValidationError):
        WireOrderRequest(
            payment_method="crypto", amount_usd=50, contact_telegram="@a"
        )  # missing txid


def test_crypto_valid_payload():
    req = WireOrderRequest(
        payment_method="crypto",
        amount_usd=50,
        crypto_txid="0xabc",
        crypto_link="https://tronscan.org/#/transaction/0xabc",
        contact_telegram="@a",
    )
    assert req.amount_usd == 50
    assert req.crypto_txid == "0xabc"


def test_wire_requires_amount_tomans():
    with pytest.raises(ValidationError):
        WireOrderRequest(payment_method="wire", contact_telegram="@a")
    req = WireOrderRequest(amount_tomans=500000, contact_telegram="@a")
    assert req.payment_method == "wire"
