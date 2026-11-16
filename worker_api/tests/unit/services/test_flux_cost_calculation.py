from app.services.flux.client import FluxCloudClient


def test_calculate_payment_amount_uses_pricing_data_precisely():
    client = FluxCloudClient(wallet_address="test-wallet", private_key="1" * 64)

    pricing_data = {
        "fluxprice": "0.50",
        "cpuusd": "0.04",
        "ramusd": "0.01",
        "hddusd": "0.001",
    }
    app_spec = {
        "instances": 3,
        "expire": 22000,
        "compose": [
            {
                "cpu": 1,
                "ram": 1024,
                "hdd": 10,
            }
        ],
    }

    sats = client._calculate_payment_amount(pricing_data, app_spec)
    assert sats == 36_000_000


def test_calculate_payment_amount_applies_period_multiplier_and_key_fallbacks():
    client = FluxCloudClient(wallet_address="test-wallet", private_key="1" * 64)

    pricing_data = {
        "fluxPrice": "1.00",
        "cpuPriceUsd": "0.02",
        "ramPriceUsd": "0.01",
        "hddPriceUsd": "0.01",
    }
    app_spec = {
        "instances": 2,
        "expire": 44000,
        "compose": [
            {
                "cpu": 1,
                "ram": 1024,
                "hdd": 5,
            }
        ],
    }

    sats = client._calculate_payment_amount(pricing_data, app_spec)
    assert sats == 32_000_000


def test_calculate_payment_amount_has_minimum_guardrail():
    client = FluxCloudClient(wallet_address="test-wallet", private_key="1" * 64)

    pricing_data = {
        "fluxprice": "10",
        "cpuusd": "0.000001",
        "ramusd": "0.000001",
        "hddusd": "0.000001",
    }
    app_spec = {
        "instances": 1,
        "expire": 22000,
        "compose": [{"cpu": 0.1, "ram": 100, "hdd": 1}],
    }

    sats = client._calculate_payment_amount(pricing_data, app_spec)
    assert sats == 10_000
