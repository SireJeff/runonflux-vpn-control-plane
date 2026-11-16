"""
Zarinpal Payment Gateway Integration (Iranian Payment Processor)

Zarinpal is the primary payment gateway for Iranian users.
Documentation: https://www.zarinpal.com/docs/
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

import requests  # type: ignore[import-untyped]

from app.core.config import settings

logger = logging.getLogger(__name__)


class ZarinpalClient:
    """Client for Zarinpal payment gateway integration"""

    # Zarinpal endpoints
    SANDBOX_URL = "https://sandbox.zarinpal.com/pg/v4/payment/"
    PRODUCTION_URL = "https://api.zarinpal.com/pg/v4/payment/"

    # Payment URLs
    SANDBOX_PAYMENT_URL = "https://sandbox.zarinpal.com/pg/StartPay/"
    PRODUCTION_PAYMENT_URL = "https://www.zarinpal.com/pg/StartPay/"

    def __init__(self):
        """Initialize Zarinpal client"""
        self.merchant_id = settings.ZARINPAL_MERCHANT_ID
        self.is_sandbox = settings.ZARINPAL_SANDBOX
        self.base_url = self.SANDBOX_URL if self.is_sandbox else self.PRODUCTION_URL
        self.payment_url = (
            self.SANDBOX_PAYMENT_URL if self.is_sandbox else self.PRODUCTION_PAYMENT_URL
        )

    def create_payment_request(
        self,
        amount_irr: int,
        description: str,
        callback_url: str,
        email: Optional[str] = None,
        mobile: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create payment request

        Args:
            amount_irr: Amount in Iranian Rials (must be >= 1000)
            description: Payment description (max 255 chars)
            callback_url: Callback URL after payment
            email: Customer email (optional)
            mobile: Customer mobile (optional, 11 digits starting with 09)
            metadata: Additional metadata (optional)

        Returns:
            {
                "success": True/False,
                "authority": "A00000000000000000000000000123456789",
                "payment_url": "https://www.zarinpal.com/pg/StartPay/A00...",
                "fee": 15000,
                "fee_type": "Merchant"
            }
        """
        logger.info(f"Creating Zarinpal payment request for {amount_irr} IRR")

        # Validate amount
        if amount_irr < 1000:
            raise ValueError("Amount must be at least 1000 IRR")

        # Prepare request data
        data = {
            "merchant_id": self.merchant_id,
            "amount": amount_irr,
            "description": description[:255],
            "callback_url": callback_url,
        }

        if email:
            data["email"] = email

        if mobile:
            data["mobile"] = mobile

        if metadata:
            data["metadata"] = metadata

        try:
            # Make request
            response = requests.post(
                f"{self.base_url}request.json", json=data, timeout=10
            )

            response.raise_for_status()
            result = response.json()

            # Check response
            if result.get("data", {}).get("code") == 100:
                authority = result["data"]["authority"]
                payment_url = f"{self.payment_url}{authority}"

                logger.info(f"Zarinpal payment request created: {authority}")

                return {
                    "success": True,
                    "authority": authority,
                    "payment_url": payment_url,
                    "fee": result["data"].get("fee", 0),
                    "fee_type": result["data"].get("fee_type", "Merchant"),
                }
            else:
                error_code = result.get("errors", {}).get("code", "UNKNOWN")
                error_message = result.get("errors", {}).get("message", "Unknown error")

                logger.error(
                    f"Zarinpal payment request failed: {error_code} - {error_message}"
                )

                return {
                    "success": False,
                    "error_code": error_code,
                    "error_message": error_message,
                }

        except requests.exceptions.RequestException as e:
            logger.error(f"Zarinpal API request failed: {str(e)}")
            return {
                "success": False,
                "error_code": "NETWORK_ERROR",
                "error_message": str(e),
            }

    def verify_payment(self, authority: str, amount_irr: int) -> Dict[str, Any]:
        """
        Verify payment after callback

        Args:
            authority: Payment authority from callback
            amount_irr: Original payment amount

        Returns:
            {
                "success": True/False,
                "ref_id": "123456789",
                "card_pan": "123456******1234",
                "card_hash": "hashed_value",
                "fee_type": "Merchant",
                "fee": 15000
            }
        """
        logger.info(f"Verifying Zarinpal payment: {authority}")

        data = {
            "merchant_id": self.merchant_id,
            "amount": amount_irr,
            "authority": authority,
        }

        try:
            response = requests.post(
                f"{self.base_url}verify.json", json=data, timeout=10
            )

            response.raise_for_status()
            result = response.json()

            # Check response
            if result.get("data", {}).get("code") == 100:
                logger.info(
                    f"Zarinpal payment verified: RefID {result['data']['ref_id']}"
                )

                return {
                    "success": True,
                    "ref_id": result["data"]["ref_id"],
                    "card_pan": result["data"].get("card_pan"),
                    "card_hash": result["data"].get("card_hash"),
                    "fee_type": result["data"].get("fee_type"),
                    "fee": result["data"].get("fee", 0),
                }
            elif result.get("data", {}).get("code") == 101:
                # Already verified
                logger.warning(f"Zarinpal payment already verified: {authority}")

                return {
                    "success": True,
                    "ref_id": result["data"]["ref_id"],
                    "already_verified": True,
                }
            else:
                error_code = result.get("errors", {}).get("code", "UNKNOWN")
                error_message = result.get("errors", {}).get(
                    "message", "Verification failed"
                )

                logger.error(
                    f"Zarinpal verification failed: {error_code} - {error_message}"
                )

                return {
                    "success": False,
                    "error_code": error_code,
                    "error_message": error_message,
                }

        except requests.exceptions.RequestException as e:
            logger.error(f"Zarinpal verify request failed: {str(e)}")
            return {
                "success": False,
                "error_code": "NETWORK_ERROR",
                "error_message": str(e),
            }

    def get_usd_to_irr_rate(self) -> Optional[Decimal]:
        """
        Get USD to IRR exchange rate from Bonbast API

        Returns:
            Exchange rate (e.g., 580000 IRR per 1 USD) or None if failed
        """
        try:
            # Using Bonbast API for USD/IRR rate
            response = requests.get("https://www.bonbast.com/json", timeout=5)

            response.raise_for_status()
            data = response.json()

            # Get sell rate (what users pay)
            usd_sell = data.get("usd", {}).get("sell")

            if usd_sell:
                rate = Decimal(str(usd_sell))
                logger.info(f"USD to IRR rate: {rate}")
                return rate
            else:
                logger.warning("Could not fetch USD/IRR rate from Bonbast")
                return None

        except Exception as e:
            logger.error(f"Failed to fetch exchange rate: {str(e)}")
            # Fallback rate (update periodically)
            return Decimal("580000")

    def convert_usd_to_irr(self, amount_usd: Decimal) -> int:
        """
        Convert USD amount to Iranian Rials

        Args:
            amount_usd: Amount in USD

        Returns:
            Amount in IRR (integer)
        """
        rate = self.get_usd_to_irr_rate()

        if not rate:
            # Use fallback rate
            rate = Decimal("580000")

        amount_irr = int(amount_usd * rate)

        # Round to nearest 1000 IRR
        amount_irr = round(amount_irr / 1000) * 1000

        logger.info(f"Converted ${amount_usd} to {amount_irr} IRR (rate: {rate})")

        return amount_irr

    def get_payment_errors(self) -> Dict[int, str]:
        """
        Get Zarinpal error codes and messages in Persian

        Returns:
            Dictionary of error codes and messages
        """
        return {
            -1: "اطلاعات ارسال شده ناقص است",
            -2: "IP یا مرچنت کد پذیرنده صحیح نیست",
            -3: "با توجه به محدودیت‌های شاپرک امکان پرداخت با رقم درخواست شده میسر نمی‌باشد",
            -4: "سطح تایید پذیرنده پایین‌تر از سطح نقره‌ای است",
            -11: "درخواست مورد نظر یافت نشد",
            -12: "امکان ویرایش درخواست میسر نمی‌باشد",
            -21: "هیچ نوع عملیات مالی برای این تراکنش یافت نشد",
            -22: "تراکنش ناموفق می‌باشد",
            -33: "رقم تراکنش با رقم پرداخت شده مطابقت ندارد",
            -34: "سقف تقسیم تراکنش از لحاظ تعداد یا رقم عبور نموده است",
            -40: "اجازه دسترسی به متد مربوطه وجود ندارد",
            -41: "اطلاعات ارسال شده مربوط به AdditionalData غیرمعتبر می‌باشد",
            -42: "مدت زمان معتبر طول عمر شناسه پرداخت باید بین 30 دقیقه تا 45 روز می‌باشد",
            -54: "درخواست مورد نظر آرشیو شده است",
            100: "عملیات با موفقیت انجام گردیده است",
            101: "عملیات پرداخت موفق بوده و قبلا وریفای شده است",
        }
