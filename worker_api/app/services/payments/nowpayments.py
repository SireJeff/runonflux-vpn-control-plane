"""
NOWPayments Cryptocurrency Payment Gateway Integration

NOWPayments supports 200+ cryptocurrencies including:
- FLUX, BTC, ETH, USDT, USDC, BNB, XRP, ADA, and more

Documentation: https://documenter.getpostman.com/view/7907941/S1a32n38
"""

import hashlib
import hmac
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests  # type: ignore[import-untyped]

from app.core.config import settings

logger = logging.getLogger(__name__)


class NOWPaymentsClient:
    """Client for NOWPayments cryptocurrency gateway"""

    # API endpoints
    SANDBOX_URL = "https://api-sandbox.nowpayments.io/v1"
    PRODUCTION_URL = "https://api.nowpayments.io/v1"

    def __init__(self):
        """Initialize NOWPayments client"""
        self.api_key = settings.NOWPAYMENTS_API_KEY
        self.ipn_secret = settings.NOWPAYMENTS_IPN_SECRET
        self.is_sandbox = settings.NOWPAYMENTS_SANDBOX
        self.base_url = self.SANDBOX_URL if self.is_sandbox else self.PRODUCTION_URL

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        return {"x-api-key": self.api_key, "Content-Type": "application/json"}

    def get_available_currencies(self) -> List[str]:
        """
        Get list of available cryptocurrencies

        Returns:
            List of currency codes (e.g., ["btc", "eth", "flux", "usdt"])
        """
        try:
            response = requests.get(
                f"{self.base_url}/currencies", headers=self._get_headers(), timeout=10
            )

            response.raise_for_status()
            data = response.json()

            currencies = data.get("currencies", [])
            logger.info(f"NOWPayments: {len(currencies)} currencies available")

            return currencies

        except requests.exceptions.RequestException as e:
            logger.error(f"NOWPayments API error: {str(e)}")
            return []

    def get_estimate(
        self, amount: Decimal, currency_from: str, currency_to: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get estimated exchange amount

        Args:
            amount: Amount in source currency
            currency_from: Source currency (e.g., "usd")
            currency_to: Target cryptocurrency (e.g., "btc")

        Returns:
            {
                "currency_from": "usd",
                "amount_from": 100,
                "currency_to": "btc",
                "estimated_amount": 0.00234567
            }
        """
        try:
            params = {
                "amount": float(amount),
                "currency_from": currency_from.lower(),
                "currency_to": currency_to.lower(),
            }

            response = requests.get(
                f"{self.base_url}/estimate",
                headers=self._get_headers(),
                params=params,  # type: ignore[arg-type]  # requests params stub over-strict
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            logger.info(
                f"NOWPayments estimate: {amount} {currency_from} = {data.get('estimated_amount')} {currency_to}"
            )

            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"NOWPayments estimate error: {str(e)}")
            return None

    def create_payment(
        self,
        price_amount: Decimal,
        price_currency: str,
        pay_currency: str,
        order_id: str,
        order_description: str,
        ipn_callback_url: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create payment

        Args:
            price_amount: Amount in fiat currency (e.g., 10.00)
            price_currency: Fiat currency (e.g., "usd")
            pay_currency: Cryptocurrency to receive (e.g., "btc")
            order_id: Unique order ID
            order_description: Payment description
            ipn_callback_url: IPN callback URL
            success_url: Success redirect URL (optional)
            cancel_url: Cancel redirect URL (optional)

        Returns:
            {
                "payment_id": "1234567890",
                "payment_status": "waiting",
                "pay_address": "bc1qxy...",
                "price_amount": 10.00,
                "price_currency": "usd",
                "pay_amount": 0.00023456,
                "pay_currency": "btc",
                "order_id": "ORDER-123",
                "order_description": "VPN Subscription",
                "created_at": "2024-01-01T00:00:00.000Z",
                "updated_at": "2024-01-01T00:00:00.000Z",
                "expiration_estimate_date": "2024-01-01T01:00:00.000Z"
            }
        """
        logger.info(
            f"Creating NOWPayments payment: {price_amount} {price_currency} in {pay_currency}"
        )

        data = {
            "price_amount": float(price_amount),
            "price_currency": price_currency.lower(),
            "pay_currency": pay_currency.lower(),
            "order_id": order_id,
            "order_description": order_description,
            "ipn_callback_url": ipn_callback_url,
        }

        if success_url:
            data["success_url"] = success_url

        if cancel_url:
            data["cancel_url"] = cancel_url

        try:
            response = requests.post(
                f"{self.base_url}/payment",
                headers=self._get_headers(),
                json=data,  # type: ignore[arg-type]  # requests json= stub over-strict; dict is JSON-serializable at runtime
                timeout=10,
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"NOWPayments payment created: {result.get('payment_id')}")

            return {"success": True, **result}

        except requests.exceptions.RequestException as e:
            logger.error(f"NOWPayments payment creation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Get payment status

        Args:
            payment_id: Payment ID from create_payment

        Returns:
            {
                "payment_id": "1234567890",
                "payment_status": "finished",  # waiting, confirming, confirmed, sending, partially_paid, finished, failed, refunded, expired
                "pay_address": "bc1qxy...",
                "price_amount": 10.00,
                "price_currency": "usd",
                "pay_amount": 0.00023456,
                "actually_paid": 0.00023456,
                "pay_currency": "btc",
                "order_id": "ORDER-123",
                "created_at": "2024-01-01T00:00:00.000Z",
                "updated_at": "2024-01-01T00:00:05.000Z"
            }
        """
        try:
            response = requests.get(
                f"{self.base_url}/payment/{payment_id}",
                headers=self._get_headers(),
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            logger.info(
                f"NOWPayments payment status: {payment_id} - {data.get('payment_status')}"
            )

            return {"success": True, **data}

        except requests.exceptions.RequestException as e:
            logger.error(f"NOWPayments status check failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def verify_ipn_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify IPN callback signature

        Args:
            payload: Raw request body (bytes)
            signature: x-nowpayments-sig header value

        Returns:
            True if signature is valid, False otherwise
        """
        expected_sig = hmac.new(
            self.ipn_secret.encode("utf-8"), payload, hashlib.sha512
        ).hexdigest()

        is_valid = hmac.compare_digest(expected_sig, signature)

        if is_valid:
            logger.info("NOWPayments IPN signature verified successfully")
        else:
            logger.warning("NOWPayments IPN signature verification failed")

        return is_valid

    def get_minimum_payment_amount(self, currency: str) -> Optional[Decimal]:
        """
        Get minimum payment amount for a cryptocurrency

        Args:
            currency: Currency code (e.g., "btc")

        Returns:
            Minimum amount or None if failed
        """
        try:
            response = requests.get(
                f"{self.base_url}/min-amount",
                headers=self._get_headers(),
                params={"currency_from": "usd", "currency_to": currency.lower()},
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            min_amount = Decimal(str(data.get("min_amount", 0)))
            logger.info(f"NOWPayments minimum amount for {currency}: {min_amount}")

            return min_amount

        except Exception as e:
            logger.error(f"Failed to get minimum amount: {str(e)}")
            return None

    def create_invoice(
        self,
        price_amount: Decimal,
        price_currency: str,
        order_id: str,
        order_description: str,
        ipn_callback_url: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create invoice (hosted payment page)

        This creates a hosted payment page where users can select cryptocurrency.

        Args:
            price_amount: Amount in fiat currency
            price_currency: Fiat currency (e.g., "usd")
            order_id: Unique order ID
            order_description: Payment description
            ipn_callback_url: IPN callback URL
            success_url: Success redirect URL (optional)
            cancel_url: Cancel redirect URL (optional)

        Returns:
            {
                "id": "1234567890",
                "token_id": "token_abc123",
                "order_id": "ORDER-123",
                "order_description": "VPN Subscription",
                "price_amount": "10.00",
                "price_currency": "usd",
                "pay_currency": null,
                "ipn_callback_url": "https://...",
                "invoice_url": "https://nowpayments.io/payment/?iid=...",
                "success_url": "https://...",
                "cancel_url": "https://...",
                "created_at": "2024-01-01T00:00:00.000Z",
                "updated_at": "2024-01-01T00:00:00.000Z"
            }
        """
        logger.info(f"Creating NOWPayments invoice: {price_amount} {price_currency}")

        data = {
            "price_amount": float(price_amount),
            "price_currency": price_currency.lower(),
            "order_id": order_id,
            "order_description": order_description,
            "ipn_callback_url": ipn_callback_url,
        }

        if success_url:
            data["success_url"] = success_url

        if cancel_url:
            data["cancel_url"] = cancel_url

        try:
            response = requests.post(
                f"{self.base_url}/invoice",
                headers=self._get_headers(),
                json=data,  # type: ignore[arg-type]  # requests json= stub over-strict; dict is JSON-serializable at runtime
                timeout=10,
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"NOWPayments invoice created: {result.get('id')}")

            return {"success": True, **result}

        except requests.exceptions.RequestException as e:
            logger.error(f"NOWPayments invoice creation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_payment_statuses(self) -> Dict[str, str]:
        """
        Get payment status descriptions

        Returns:
            Dictionary of status codes and descriptions
        """
        return {
            "waiting": "Waiting for payment",
            "confirming": "Payment received, confirming",
            "confirmed": "Payment confirmed",
            "sending": "Sending to your wallet",
            "partially_paid": "Partially paid (underpayment)",
            "finished": "Payment completed successfully",
            "failed": "Payment failed",
            "refunded": "Payment refunded",
            "expired": "Payment expired (not paid in time)",
        }
