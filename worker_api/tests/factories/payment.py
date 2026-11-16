"""
Payment-related model factories for testing
"""

from datetime import datetime
from decimal import Decimal

from app.models import Payment, WalletTransaction, WithdrawalRequest


class PaymentFactory:
    """Factory for creating Payment instances"""

    @staticmethod
    def create(user_id: int, **kwargs):
        """Create a Payment instance with default values"""
        defaults = {
            "user_id": user_id,
            "subscription_id": None,
            "amount_usd": Decimal("10.00"),
            "payment_method": "wallet",
            "status": "pending",
            "transaction_id": None,
            "deposit_to_wallet": False,
            "metadata": {},
        }
        defaults.update(kwargs)
        return Payment(**defaults)

    @staticmethod
    def create_completed(user_id: int, **kwargs):
        """Create a completed payment"""
        defaults = {
            "status": "completed",
            "completed_at": datetime.now(),
            "transaction_id": f"TXN{datetime.now().timestamp()}",
        }
        defaults.update(kwargs)
        return PaymentFactory.create(user_id, **defaults)

    @staticmethod
    def create_failed(user_id: int, **kwargs):
        """Create a failed payment"""
        defaults = {
            "status": "failed",
        }
        defaults.update(kwargs)
        return PaymentFactory.create(user_id, **defaults)

    @staticmethod
    def create_wallet_deposit(user_id: int, amount: Decimal, **kwargs):
        """Create a wallet deposit payment"""
        defaults = {
            "amount_usd": amount,
            "deposit_to_wallet": True,
            "status": "completed",
            "completed_at": datetime.now(),
        }
        defaults.update(kwargs)
        return PaymentFactory.create(user_id, **defaults)

    @staticmethod
    def create_subscription_payment(
        user_id: int, subscription_id: int, amount: Decimal, **kwargs
    ):
        """Create a subscription payment"""
        defaults = {
            "subscription_id": subscription_id,
            "amount_usd": amount,
            "payment_method": "stripe",
            "status": "completed",
            "completed_at": datetime.now(),
        }
        defaults.update(kwargs)
        return PaymentFactory.create(user_id, **defaults)


class WalletTransactionFactory:
    """Factory for creating WalletTransaction instances"""

    @staticmethod
    def create(user_id: int, **kwargs):
        """Create a WalletTransaction instance with default values"""
        defaults = {
            "user_id": user_id,
            "amount_usd": Decimal("10.00"),
            "transaction_type": "deposit",
            "payment_id": None,
            "subscription_id": None,
            "description": "Test transaction",
            "balance_before": Decimal("0.00"),
            "balance_after": Decimal("10.00"),
        }
        defaults.update(kwargs)
        return WalletTransaction(**defaults)

    @staticmethod
    def create_deposit(user_id: int, amount: Decimal, **kwargs):
        """Create a deposit transaction"""
        defaults = {
            "amount_usd": amount,
            "transaction_type": "deposit",
            "description": "Wallet deposit",
        }
        defaults.update(kwargs)
        return WalletTransactionFactory.create(user_id, **defaults)

    @staticmethod
    def create_purchase(
        user_id: int,
        amount: Decimal,
        subscription_id: int | None = None,
        **kwargs,
    ):
        """Create a purchase transaction"""
        defaults = {
            "amount_usd": -amount,  # Negative for debit
            "transaction_type": "purchase",
            "subscription_id": subscription_id,
            "description": "Subscription purchase",
        }
        defaults.update(kwargs)
        return WalletTransactionFactory.create(user_id, **defaults)

    @staticmethod
    def create_referral_commission(user_id: int, amount: Decimal, **kwargs):
        """Create a referral commission transaction"""
        defaults = {
            "amount_usd": amount,
            "transaction_type": "referral_commission",
            "description": "Referral commission earned",
        }
        defaults.update(kwargs)
        return WalletTransactionFactory.create(user_id, **defaults)

    @staticmethod
    def create_withdrawal(user_id: int, amount: Decimal, **kwargs):
        """Create a withdrawal transaction"""
        defaults = {
            "amount_usd": -amount,  # Negative for debit
            "transaction_type": "withdrawal",
            "description": "Wallet withdrawal",
        }
        defaults.update(kwargs)
        return WalletTransactionFactory.create(user_id, **defaults)


class WithdrawalRequestFactory:
    """Factory for creating WithdrawalRequest instances"""

    @staticmethod
    def create(user_id: int, **kwargs):
        """Create a WithdrawalRequest instance with default values"""
        defaults = {
            "user_id": user_id,
            "amount_usd": Decimal("50.00"),
            "withdrawal_method": "zarinpal",
            "withdrawal_details": {"card_number": "1234567890123456"},
            "status": "pending",
            "admin_notes": None,
            "processed_by": None,
        }
        defaults.update(kwargs)
        return WithdrawalRequest(**defaults)

    @staticmethod
    def create_pending(user_id: int, **kwargs):
        """Create a pending withdrawal request"""
        defaults = {
            "status": "pending",
        }
        defaults.update(kwargs)
        return WithdrawalRequestFactory.create(user_id, **defaults)

    @staticmethod
    def create_approved(user_id: int, admin_id: int, **kwargs):
        """Create an approved withdrawal request"""
        defaults = {
            "status": "approved",
            "processed_by": admin_id,
            "admin_notes": "Approved",
            "processed_at": datetime.now(),
        }
        defaults.update(kwargs)
        return WithdrawalRequestFactory.create(user_id, **defaults)

    @staticmethod
    def create_rejected(user_id: int, admin_id: int, reason: str, **kwargs):
        """Create a rejected withdrawal request"""
        defaults = {
            "status": "rejected",
            "processed_by": admin_id,
            "admin_notes": reason,
            "processed_at": datetime.now(),
        }
        defaults.update(kwargs)
        return WithdrawalRequestFactory.create(user_id, **defaults)

    @staticmethod
    def create_crypto_withdrawal(user_id: int, **kwargs):
        """Create a cryptocurrency withdrawal request"""
        defaults = {
            "withdrawal_method": "bitcoin",
            "withdrawal_details": {
                "crypto_address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
            },
        }
        defaults.update(kwargs)
        return WithdrawalRequestFactory.create(user_id, **defaults)
