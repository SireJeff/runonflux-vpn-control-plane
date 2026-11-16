"""
Stripe Payment Gateway Integration (International Credit/Debit Cards)

Stripe is used for international users to pay with credit/debit cards.
Documentation: https://stripe.com/docs/api
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, cast

import stripe

from app.core.config import settings

logger = logging.getLogger(__name__)


class StripeClient:
    """Client for Stripe payment gateway"""

    def __init__(self):
        """Initialize Stripe client"""
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.publishable_key = settings.STRIPE_PUBLISHABLE_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    def create_checkout_session(
        self,
        amount_usd: Decimal,
        currency: str,
        product_name: str,
        product_description: str,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Create Stripe Checkout Session

        Args:
            amount_usd: Amount in USD
            currency: Currency code (e.g., "usd")
            product_name: Product name
            product_description: Product description
            success_url: Success redirect URL
            cancel_url: Cancel redirect URL
            customer_email: Customer email (optional)
            metadata: Additional metadata (optional)

        Returns:
            {
                "success": True,
                "session_id": "cs_...",
                "checkout_url": "https://checkout.stripe.com/...",
                "payment_intent": "pi_..."
            }
        """
        logger.info(f"Creating Stripe checkout session: ${amount_usd}")

        try:
            # Convert to cents
            amount_cents = int(amount_usd * 100)

            # Create checkout session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": currency.lower(),
                            "unit_amount": amount_cents,
                            "product_data": {
                                "name": product_name,
                                "description": product_description,
                            },
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=customer_email,  # type: ignore[arg-type]  # stripe stub: Optional accepted at runtime
                metadata=metadata or {},
                payment_intent_data={"metadata": metadata or {}},
            )

            logger.info(f"Stripe checkout session created: {session.id}")

            return {
                "success": True,
                "session_id": session.id,
                "checkout_url": session.url,
                "payment_intent": session.payment_intent,
            }

        except Exception as e:
            logger.error(f"Stripe checkout session creation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_payment_intent(
        self,
        amount_usd: Decimal,
        currency: str = "usd",
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create Payment Intent (for custom payment flows)

        Args:
            amount_usd: Amount in USD
            currency: Currency code (default: "usd")
            customer_email: Customer email (optional)
            metadata: Additional metadata (optional)
            description: Payment description (optional)

        Returns:
            {
                "success": True,
                "payment_intent_id": "pi_...",
                "client_secret": "pi_..._secret_...",
                "status": "requires_payment_method"
            }
        """
        logger.info(f"Creating Stripe payment intent: ${amount_usd}")

        try:
            # Convert to cents
            amount_cents = int(amount_usd * 100)

            # Create payment intent
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                receipt_email=customer_email,  # type: ignore[arg-type]  # stripe stub: Optional accepted at runtime
                metadata=metadata or {},
                description=description,  # type: ignore[arg-type]  # stripe stub: Optional accepted at runtime
            )

            logger.info(f"Stripe payment intent created: {intent.id}")

            return {
                "success": True,
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
                "status": intent.status,
            }

        except Exception as e:
            logger.error(f"Stripe payment intent creation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def retrieve_payment_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        Retrieve payment intent details

        Args:
            payment_intent_id: Payment intent ID

        Returns:
            {
                "success": True,
                "id": "pi_...",
                "status": "succeeded",
                "amount": 1000,
                "currency": "usd",
                "created": 1234567890,
                "metadata": {...}
            }
        """
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            logger.info(
                f"Stripe payment intent retrieved: {intent.id} - {intent.status}"
            )

            return {
                "success": True,
                "id": intent.id,
                "status": intent.status,
                "amount": intent.amount / 100,  # Convert back to dollars
                "currency": intent.currency,
                "created": datetime.fromtimestamp(intent.created),
                "metadata": intent.metadata,
            }

        except Exception as e:
            logger.error(f"Stripe payment intent retrieval failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def verify_webhook_signature(
        self, payload: bytes, signature: str
    ) -> Optional[stripe.Event]:
        """
        Verify webhook signature and construct event

        Args:
            payload: Raw request body (bytes)
            signature: Stripe-Signature header value

        Returns:
            Stripe Event object or None if verification fails
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )

            logger.info(f"Stripe webhook verified: {event.type}")
            return event

        except ValueError as e:
            logger.error(f"Stripe webhook invalid payload: {str(e)}")
            return None

        except Exception as e:
            logger.error(f"Stripe webhook signature verification failed: {str(e)}")
            return None

    def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Create Stripe customer

        Args:
            email: Customer email
            name: Customer name (optional)
            metadata: Additional metadata (optional)

        Returns:
            {
                "success": True,
                "customer_id": "cus_...",
                "email": "user@example.com"
            }
        """
        logger.info(f"Creating Stripe customer: {email}")

        try:
            customer = stripe.Customer.create(
                email=email, name=name, metadata=metadata or {}  # type: ignore[arg-type]  # stripe stub: Optional accepted at runtime
            )

            logger.info(f"Stripe customer created: {customer.id}")

            return {
                "success": True,
                "customer_id": customer.id,
                "email": customer.email,
            }

        except Exception as e:
            logger.error(f"Stripe customer creation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_subscription(
        self, customer_id: str, price_id: str, metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Create Stripe subscription (for recurring payments)

        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID
            metadata: Additional metadata (optional)

        Returns:
            {
                "success": True,
                "subscription_id": "sub_...",
                "status": "active",
                "current_period_end": datetime
            }
        """
        logger.info(f"Creating Stripe subscription for customer: {customer_id}")

        try:
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": price_id}],
                metadata=metadata or {},
            )

            logger.info(f"Stripe subscription created: {subscription.id}")

            return {
                "success": True,
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_end": datetime.fromtimestamp(
                    subscription.current_period_end  # type: ignore[attr-defined]  # stripe stub lacks current_period_end
                ),
            }

        except Exception as e:
            logger.error(f"Stripe subscription creation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def cancel_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """
        Cancel Stripe subscription

        Args:
            subscription_id: Subscription ID

        Returns:
            {
                "success": True,
                "subscription_id": "sub_...",
                "status": "canceled"
            }
        """
        logger.info(f"Canceling Stripe subscription: {subscription_id}")

        try:
            subscription = cast(
                Dict[str, Any], stripe.Subscription.delete(cast(Any, subscription_id))
            )
            canceled_id = str(subscription.get("id", subscription_id))
            canceled_status = str(subscription.get("status", "canceled"))

            logger.info(f"Stripe subscription canceled: {canceled_id}")

            return {
                "success": True,
                "subscription_id": canceled_id,
                "status": canceled_status,
            }

        except Exception as e:
            logger.error(f"Stripe subscription cancellation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create refund

        Args:
            payment_intent_id: Payment intent ID to refund
            amount: Amount to refund (None for full refund)
            reason: Refund reason (optional)

        Returns:
            {
                "success": True,
                "refund_id": "re_...",
                "status": "succeeded",
                "amount": 10.00
            }
        """
        logger.info(f"Creating Stripe refund for: {payment_intent_id}")

        try:
            refund_data: Dict[str, Any] = {"payment_intent": payment_intent_id}

            if amount:
                refund_data["amount"] = int(amount * 100)

            if reason:
                refund_data["reason"] = reason

            refund = stripe.Refund.create(**refund_data)

            logger.info(f"Stripe refund created: {refund.id}")

            return {
                "success": True,
                "refund_id": refund.id,
                "status": refund.status,
                "amount": refund.amount / 100,
            }

        except Exception as e:
            logger.error(f"Stripe refund creation failed: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_payment_statuses(self) -> Dict[str, str]:
        """
        Get payment status descriptions

        Returns:
            Dictionary of status codes and descriptions
        """
        return {
            "requires_payment_method": "Waiting for payment method",
            "requires_confirmation": "Requires confirmation",
            "requires_action": "Requires additional action (3D Secure)",
            "processing": "Payment processing",
            "requires_capture": "Requires manual capture",
            "canceled": "Payment canceled",
            "succeeded": "Payment succeeded",
        }
