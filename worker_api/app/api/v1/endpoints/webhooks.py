"""
Payment Gateway Webhook Handlers
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User, WalletTransaction
from app.schemas import SuccessResponse
from app.services.payments import NOWPaymentsClient, StripeClient, ZarinpalClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _event_value(payload_obj: Any, field: str) -> Any:
    if isinstance(payload_obj, dict):
        return payload_obj.get(field)
    return getattr(payload_obj, field, None)


# ============================================================================
# ZARINPAL WEBHOOK
# ============================================================================


@router.get("/zarinpal/callback")
async def zarinpal_callback(Authority: str, Status: str, db: Session = Depends(get_db)):
    """
    Zarinpal payment callback (GET request)

    After user completes payment on Zarinpal, they are redirected here.

    Query Parameters:
    - Authority: Payment authority code
    - Status: Payment status ("OK" or "NOK")
    """
    logger.info(f"Zarinpal callback received: Authority={Authority}, Status={Status}")

    if Status != "OK":
        logger.warning(f"Zarinpal payment canceled by user: {Authority}")
        return {
            "success": False,
            "message": "پرداخت توسط کاربر لغو شد",
            "authority": Authority,
        }

    # Find transaction by authority code
    transaction = (
        db.query(WalletTransaction)
        .filter_by(reference_id=f"zarinpal_{Authority}", status="pending")
        .first()
    )

    if not transaction:
        logger.error(f"Zarinpal transaction not found: {Authority}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="تراکنش یافت نشد"
        )

    # Verify payment with Zarinpal
    zarinpal = ZarinpalClient()
    # extra_data is nullable at the DB level (no default); fall back to an
    # empty dict so a missing/NULL payload behaves like a missing key below.
    amount_irr = int((transaction.extra_data or {}).get("amount_irr", 0))

    verification = zarinpal.verify_payment(Authority, amount_irr)

    if verification["success"]:
        # Payment successful
        user = db.query(User).filter_by(id=transaction.user_id).first()
        transaction_obj = cast(Any, transaction)

        if user:
            # Credit user's wallet
            user.wallet_balance = _as_decimal(user.wallet_balance) + _as_decimal(
                transaction.amount_usd
            )

            # Update transaction
            transaction_obj.status = "completed"
            transaction_obj.extra_data["ref_id"] = verification["ref_id"]
            transaction_obj.extra_data["card_pan"] = verification.get("card_pan")
            transaction_obj.extra_data["verified_at"] = (
                datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            )

            db.commit()

            logger.info(
                f"Zarinpal payment verified: RefID={verification['ref_id']}, User={user.id}"
            )

            return {
                "success": True,
                "message": "پرداخت با موفقیت انجام شد",
                "ref_id": verification["ref_id"],
                "amount_usd": float(_as_decimal(transaction.amount_usd)),
                "new_balance": float(_as_decimal(user.wallet_balance)),
            }
    else:
        # Payment failed
        transaction_obj = cast(Any, transaction)
        transaction_obj.status = "failed"
        transaction_obj.extra_data["error"] = verification.get("error_message")

        db.commit()

        logger.error(
            f"Zarinpal payment verification failed: {verification.get('error_message')}"
        )

        return {
            "success": False,
            "message": "تأیید پرداخت با خطا مواجه شد",
            "error": verification.get("error_message"),
        }


# ============================================================================
# NOWPAYMENTS WEBHOOK (IPN)
# ============================================================================


@router.post("/nowpayments/ipn")
async def nowpayments_ipn(
    request: Request,
    x_nowpayments_sig: str = Header(...),
    db: Session = Depends(get_db),
):
    """
    NOWPayments IPN (Instant Payment Notification) webhook

    Headers:
    - x-nowpayments-sig: HMAC signature for verification

    Body: JSON payload with payment details
    """
    # Get raw body for signature verification
    raw_body = await request.body()

    # Verify signature
    nowpayments = NOWPaymentsClient()

    if not nowpayments.verify_ipn_signature(raw_body, x_nowpayments_sig):
        logger.error("NOWPayments IPN signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature"
        )

    # Parse payload
    payload = await request.json()

    logger.info(
        f"NOWPayments IPN received: {payload.get('payment_id')} - {payload.get('payment_status')}"
    )

    # Find transaction
    order_id = payload.get("order_id")
    payment_status = payload.get("payment_status")
    payment_id = payload.get("payment_id")

    transaction = db.query(WalletTransaction).filter_by(reference_id=order_id).first()

    if not transaction:
        logger.error(f"NOWPayments transaction not found: {order_id}")
        return {"success": False, "error": "Transaction not found"}

    # Update transaction based on status
    transaction_obj = cast(Any, transaction)
    if payment_status == "finished":
        # Payment completed successfully
        user = db.query(User).filter_by(id=transaction.user_id).first()

        if user and transaction.status != "completed":
            # Credit user's wallet
            user.wallet_balance = _as_decimal(user.wallet_balance) + _as_decimal(
                transaction.amount_usd
            )

            # Update transaction
            transaction_obj.status = "completed"
            transaction_obj.extra_data["payment_id"] = payment_id
            transaction_obj.extra_data["payment_status"] = payment_status
            transaction_obj.extra_data["actually_paid"] = payload.get("actually_paid")
            transaction_obj.extra_data["completed_at"] = (
                datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            )

            db.commit()

            logger.info(f"NOWPayments payment completed: {payment_id}, User={user.id}")

    elif payment_status in ["failed", "expired", "refunded"]:
        # Payment failed
        transaction_obj.status = "failed"
        transaction_obj.extra_data["payment_status"] = payment_status
        transaction_obj.extra_data["failed_at"] = (
            datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        )

        db.commit()

        logger.warning(f"NOWPayments payment {payment_status}: {payment_id}")

    elif payment_status in ["confirming", "confirmed", "sending"]:
        # Payment in progress
        transaction_obj.status = "processing"
        transaction_obj.extra_data["payment_status"] = payment_status

        db.commit()

        logger.info(f"NOWPayments payment {payment_status}: {payment_id}")

    return {"success": True}


# Alias for backward compatibility with integration tests
nowpayments_webhook = nowpayments_ipn


# ============================================================================
# STRIPE WEBHOOK
# ============================================================================


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    """
    Stripe webhook handler

    Handles various Stripe events:
    - payment_intent.succeeded
    - payment_intent.payment_failed
    - checkout.session.completed
    - customer.subscription.created
    - customer.subscription.deleted

    Headers:
    - Stripe-Signature: Webhook signature for verification
    """
    # Get raw body for signature verification
    raw_body = await request.body()

    # Verify signature and construct event
    stripe_client = StripeClient()
    event = stripe_client.verify_webhook_signature(raw_body, stripe_signature)

    if not event:
        logger.error("Stripe webhook signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature"
        )

    logger.info(f"Stripe webhook received: {event.type}")

    # Handle different event types
    if event.type == "payment_intent.succeeded":
        payment_intent = event.data.object
        payment_intent_id = _event_value(payment_intent, "id")
        if not payment_intent_id:
            return {"success": False, "error": "Missing payment_intent id"}

        # Find transaction by payment intent ID
        transaction = (
            db.query(WalletTransaction)
            .filter_by(reference_id=f"stripe_{payment_intent_id}")
            .first()
        )

        if transaction and transaction.status != "completed":
            user = db.query(User).filter_by(id=transaction.user_id).first()
            transaction_obj = cast(Any, transaction)

            if user:
                # Credit user's wallet
                user.wallet_balance = _as_decimal(user.wallet_balance) + _as_decimal(
                    transaction.amount_usd
                )

                # Update transaction
                transaction_obj.status = "completed"
                transaction_obj.extra_data["payment_intent_id"] = str(payment_intent_id)
                transaction_obj.extra_data["completed_at"] = (
                    datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                )

                db.commit()

                logger.info(
                    f"Stripe payment completed: {payment_intent_id}, User={user.id}"
                )

    elif event.type == "payment_intent.payment_failed":
        payment_intent = event.data.object
        payment_intent_id = _event_value(payment_intent, "id")
        if not payment_intent_id:
            return {"success": False, "error": "Missing payment_intent id"}

        # Find transaction
        transaction = (
            db.query(WalletTransaction)
            .filter_by(reference_id=f"stripe_{payment_intent_id}")
            .first()
        )

        if transaction:
            transaction_obj = cast(Any, transaction)
            last_payment_error = _event_value(payment_intent, "last_payment_error")
            error_message = (
                last_payment_error.get("message")
                if isinstance(last_payment_error, dict)
                else "Payment failed"
            )
            transaction_obj.status = "failed"
            transaction_obj.extra_data["error"] = error_message
            transaction_obj.extra_data["failed_at"] = (
                datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            )

            db.commit()

            logger.warning(f"Stripe payment failed: {payment_intent_id}")

    elif event.type == "checkout.session.completed":
        session = event.data.object
        session_id = _event_value(session, "id")
        if not session_id:
            return {"success": False, "error": "Missing checkout session id"}

        # Handle checkout session completion
        logger.info(f"Stripe checkout session completed: {session_id}")

        # Extract metadata and process payment
        payment_intent_id = _event_value(session, "payment_intent")

        if payment_intent_id:
            transaction = (
                db.query(WalletTransaction)
                .filter_by(reference_id=f"stripe_session_{session_id}")
                .first()
            )

            if transaction:
                transaction_obj = cast(Any, transaction)
                transaction_obj.extra_data["payment_intent_id"] = payment_intent_id
                transaction_obj.extra_data["session_completed_at"] = (
                    datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                )

                db.commit()

    elif event.type in [
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ]:
        subscription = event.data.object
        subscription_id = _event_value(subscription, "id")

        logger.info(f"Stripe subscription event: {event.type} - {subscription_id}")

        # Handle subscription events (for recurring payments)
        # This can be expanded based on requirements

    return {"success": True}


# ============================================================================
# WEBHOOK STATUS CHECK
# ============================================================================


@router.get("/status/{transaction_id}")
async def check_webhook_status(transaction_id: str, db: Session = Depends(get_db)):
    """
    Check webhook processing status for a transaction

    This endpoint can be polled by frontend to check payment status.
    """
    transaction = (
        db.query(WalletTransaction).filter_by(reference_id=transaction_id).first()
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )

    return {
        "transaction_id": transaction_id,
        "status": transaction.status,
        "amount_usd": float(_as_decimal(transaction.amount_usd)),
        "created_at": (
            transaction.created_at.isoformat()
            if transaction.created_at is not None
            else None
        ),
        "metadata": transaction.extra_data,
    }
