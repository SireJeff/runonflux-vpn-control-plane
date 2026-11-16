"""
Unit tests for Payment models
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.models import Payment, WalletTransaction, WithdrawalRequest
from tests.factories import (
    PaymentFactory,
    UserFactory,
    WalletTransactionFactory,
    WithdrawalRequestFactory,
)


class TestPaymentModel:
    """Test cases for Payment model"""

    def test_create_payment(self, db):
        """Test creating a payment"""
        user = UserFactory.create(telegram_user_id=12345)
        db.add(user)
        db.commit()

        payment = PaymentFactory.create(user.id)
        db.add(payment)
        db.commit()
        db.refresh(payment)

        assert payment.id is not None
        assert payment.user_id == user.id
        assert payment.amount_usd == Decimal("10.00")
        assert payment.payment_method == "wallet"
        assert payment.status == "pending"

    def test_create_completed_payment(self, db):
        """Test creating completed payment"""
        user = UserFactory.create(telegram_user_id=23456)
        db.add(user)
        db.commit()

        payment = PaymentFactory.create_completed(user.id, amount_usd=Decimal("50.00"))
        db.add(payment)
        db.commit()
        db.refresh(payment)

        assert payment.status == "completed"
        assert payment.completed_at is not None
        assert payment.transaction_id is not None

    def test_create_failed_payment(self, db):
        """Test creating failed payment"""
        user = UserFactory.create(telegram_user_id=34567)
        db.add(user)
        db.commit()

        payment = PaymentFactory.create_failed(user.id)
        db.add(payment)
        db.commit()
        db.refresh(payment)

        assert payment.status == "failed"

    def test_wallet_deposit_payment(self, db):
        """Test wallet deposit payment"""
        user = UserFactory.create(telegram_user_id=45678)
        db.add(user)
        db.commit()

        payment = PaymentFactory.create_wallet_deposit(user.id, Decimal("100.00"))
        db.add(payment)
        db.commit()
        db.refresh(payment)

        assert payment.deposit_to_wallet is True
        assert payment.amount_usd == Decimal("100.00")
        assert payment.status == "completed"

    def test_payment_with_metadata(self, db):
        """Test payment with metadata"""
        user = UserFactory.create(telegram_user_id=56789)
        db.add(user)
        db.commit()

        payment = PaymentFactory.create(
            user.id, metadata={"gateway": "stripe", "customer_id": "cus_123"}
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        assert payment.metadata["gateway"] == "stripe"
        assert payment.metadata["customer_id"] == "cus_123"

    def test_payment_methods(self, db):
        """Test different payment methods"""
        user = UserFactory.create(telegram_user_id=67890)
        db.add(user)
        db.commit()

        methods = ["zarinpal", "nowpayments", "stripe", "flux", "wallet"]
        payments = []

        for method in methods:
            payment = PaymentFactory.create(user.id, payment_method=method)
            payments.append(payment)
            db.add(payment)

        db.commit()

        db_payments = db.query(Payment).filter_by(user_id=user.id).all()
        assert len(db_payments) == 5
        assert set(p.payment_method for p in db_payments) == set(methods)


class TestWalletTransactionModel:
    """Test cases for WalletTransaction model"""

    def test_create_wallet_transaction(self, db):
        """Test creating a wallet transaction"""
        user = UserFactory.create(telegram_user_id=12345)
        db.add(user)
        db.commit()

        transaction = WalletTransactionFactory.create(user.id)
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        assert transaction.id is not None
        assert transaction.user_id == user.id
        assert transaction.amount_usd == Decimal("10.00")
        assert transaction.transaction_type == "deposit"

    def test_deposit_transaction(self, db):
        """Test deposit transaction"""
        user = UserFactory.create(telegram_user_id=23456)
        db.add(user)
        db.commit()

        transaction = WalletTransactionFactory.create_deposit(user.id, Decimal("50.00"))
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        assert transaction.transaction_type == "deposit"
        assert transaction.amount_usd == Decimal("50.00")
        assert transaction.amount_usd > 0  # Deposits are positive

    def test_purchase_transaction(self, db):
        """Test purchase transaction (debit)"""
        user = UserFactory.create(telegram_user_id=34567)
        db.add(user)
        db.commit()

        transaction = WalletTransactionFactory.create_purchase(
            user.id, Decimal("20.00")
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        assert transaction.transaction_type == "purchase"
        assert transaction.amount_usd == Decimal("-20.00")  # Negative for debit
        assert transaction.subscription_id is None

    def test_referral_commission_transaction(self, db):
        """Test referral commission transaction"""
        user = UserFactory.create(telegram_user_id=45678)
        db.add(user)
        db.commit()

        transaction = WalletTransactionFactory.create_referral_commission(
            user.id, Decimal("5.00")
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        assert transaction.transaction_type == "referral_commission"
        assert transaction.amount_usd == Decimal("5.00")

    def test_withdrawal_transaction(self, db):
        """Test withdrawal transaction (debit)"""
        user = UserFactory.create(telegram_user_id=56789)
        db.add(user)
        db.commit()

        transaction = WalletTransactionFactory.create_withdrawal(
            user.id, Decimal("30.00")
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        assert transaction.transaction_type == "withdrawal"
        assert transaction.amount_usd == Decimal("-30.00")  # Negative for debit

    def test_transaction_balance_tracking(self, db):
        """Test balance before/after tracking"""
        user = UserFactory.create(telegram_user_id=67890)
        db.add(user)
        db.commit()

        transaction = WalletTransactionFactory.create(
            user.id,
            amount_usd=Decimal("25.00"),
            balance_before=Decimal("100.00"),
            balance_after=Decimal("125.00"),
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        assert transaction.balance_before == Decimal("100.00")
        assert transaction.balance_after == Decimal("125.00")
        assert transaction.balance_after - transaction.balance_before == Decimal(
            "25.00"
        )


class TestWithdrawalRequestModel:
    """Test cases for WithdrawalRequest model"""

    def test_create_withdrawal_request(self, db):
        """Test creating a withdrawal request"""
        user = UserFactory.create(telegram_user_id=12345)
        db.add(user)
        db.commit()

        request = WithdrawalRequestFactory.create(user.id)
        db.add(request)
        db.commit()
        db.refresh(request)

        assert request.id is not None
        assert request.user_id == user.id
        assert request.amount_usd == Decimal("50.00")
        assert request.withdrawal_method == "zarinpal"
        assert request.status == "pending"

    def test_pending_withdrawal_request(self, db):
        """Test pending withdrawal request"""
        user = UserFactory.create(telegram_user_id=23456)
        db.add(user)
        db.commit()

        request = WithdrawalRequestFactory.create_pending(user.id)
        db.add(request)
        db.commit()
        db.refresh(request)

        assert request.status == "pending"
        assert request.processed_by is None
        assert request.processed_at is None

    def test_approved_withdrawal_request(self, db):
        """Test approved withdrawal request"""
        user = UserFactory.create(telegram_user_id=34567)
        admin = UserFactory.create_admin(telegram_user_id=99999)
        db.add_all([user, admin])
        db.commit()

        request = WithdrawalRequestFactory.create_approved(user.id, admin.id)
        db.add(request)
        db.commit()
        db.refresh(request)

        assert request.status == "approved"
        assert request.processed_by == admin.id
        assert request.processed_at is not None
        assert request.admin_notes == "Approved"

    def test_rejected_withdrawal_request(self, db):
        """Test rejected withdrawal request"""
        user = UserFactory.create(telegram_user_id=45678)
        admin = UserFactory.create_admin(telegram_user_id=88888)
        db.add_all([user, admin])
        db.commit()

        request = WithdrawalRequestFactory.create_rejected(
            user.id, admin.id, "Insufficient balance"
        )
        db.add(request)
        db.commit()
        db.refresh(request)

        assert request.status == "rejected"
        assert request.processed_by == admin.id
        assert request.admin_notes == "Insufficient balance"

    def test_crypto_withdrawal_request(self, db):
        """Test cryptocurrency withdrawal request"""
        user = UserFactory.create(telegram_user_id=56789)
        db.add(user)
        db.commit()

        request = WithdrawalRequestFactory.create_crypto_withdrawal(user.id)
        db.add(request)
        db.commit()
        db.refresh(request)

        assert request.withdrawal_method == "bitcoin"
        assert "crypto_address" in request.withdrawal_details

    def test_withdrawal_details_json(self, db):
        """Test withdrawal details stored as JSONB"""
        user = UserFactory.create(telegram_user_id=67890)
        db.add(user)
        db.commit()

        request = WithdrawalRequestFactory.create(
            user.id,
            withdrawal_details={
                "card_number": "1234567890123456",
                "bank_name": "Test Bank",
                "account_holder": "John Doe",
            },
        )
        db.add(request)
        db.commit()
        db.refresh(request)

        assert request.withdrawal_details["card_number"] == "1234567890123456"
        assert request.withdrawal_details["bank_name"] == "Test Bank"
        assert request.withdrawal_details["account_holder"] == "John Doe"

    def test_withdrawal_methods(self, db):
        """Test different withdrawal methods"""
        user = UserFactory.create(telegram_user_id=78901)
        db.add(user)
        db.commit()

        methods = ["zarinpal", "bitcoin", "ethereum", "bank_transfer"]
        requests = []

        for method in methods:
            request = WithdrawalRequestFactory.create(user.id, withdrawal_method=method)
            requests.append(request)
            db.add(request)

        db.commit()

        db_requests = db.query(WithdrawalRequest).filter_by(user_id=user.id).all()
        assert len(db_requests) == 4
        assert set(r.withdrawal_method for r in db_requests) == set(methods)
