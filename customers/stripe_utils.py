"""
Stripe payment utilities for handling Checkout Sessions and webhook events.
This module encapsulates all Stripe API interactions to make testing and
refactoring easier.
"""

import stripe
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from admins.models import Order, Payment

logger = logging.getLogger(__name__)

# Configure Stripe API key
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_stripe_checkout_session(order, request):
    """
    Creates a Stripe Checkout Session for an order.
    
    Args:
        order: Order instance to create payment for
        request: Django request object (for building success/cancel URLs)
    
    Returns:
        tuple: (session_id, session) on success
               (None, error_message) on failure
    """
    try:
        # Build the URLs for redirect after payment
        success_url = request.build_absolute_uri(reverse('stripe_success', args=[order.id]))
        cancel_url = request.build_absolute_uri(reverse('stripe_cancel', args=[order.id]))
        
        # Prepare line items from order
        line_items = []
        for item in order.items.all():
            line_items.append({
                'price_data': {
                    'currency': settings.STRIPE_CURRENCY.lower(),
                    'product_data': {
                        'name': item.product.name,
                        'description': f'Order #{order.id}',
                    },
                    'unit_amount': int(item.product.price * 100),  # Stripe expects cents
                },
                'quantity': item.quantity,
            })
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=order.customer.email,
            metadata={
                'order_id': order.id,
                'customer_id': order.customer.id,
            },
        )
        
        # Save session info to Payment record
        Payment.objects.create(
            order=order,
            payment_method='stripe',
            status='pending',
            amount=order.total_amount,
            currency=settings.STRIPE_CURRENCY,
            stripe_session_id=session.id,
        )
        
        logger.info(f'Created Stripe session {session.id} for order {order.id}')
        return session.id, None
        
    except stripe.error.StripeError as e:
        error_message = f"Stripe error: {str(e)}"
        logger.error(error_message)
        return None, error_message
    except Exception as e:
        error_message = f"Unexpected error creating Stripe session: {str(e)}"
        logger.error(error_message)
        return None, error_message


def handle_checkout_session_completed(session_id, event):
    """
    Handles the checkout.session.completed webhook event.
    This is called when a customer completes payment in Stripe Checkout.
    
    Args:
        session_id: Stripe session ID from webhook event
        event: Full webhook event dictionary
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Retrieve the full session from Stripe to confirm it
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Find the Payment record by session ID
        payment = Payment.objects.get(stripe_session_id=session_id)
        order = payment.order
        
        # Check if already processed to avoid duplicate processing
        if payment.status == 'succeeded':
            logger.warning(f'Session {session_id} already marked as succeeded, skipping.')
            return True, 'Payment already processed'
        
        # Update payment with Stripe IDs
        payment.stripe_payment_intent_id = session.payment_intent
        payment.stripe_customer_id = session.customer
        payment.status = 'succeeded'
        payment.last_webhook_event = 'checkout.session.completed'
        payment.webhook_event_timestamp = timezone.now()
        payment.paid_at = timezone.now()
        payment.save()
        
        # Move order to pending_payment so admin can review and approve
        # For Stripe, we trust the payment is real, but we still want manual approval
        # of the order before fulfillment
        if order.status == 'pending':
            order.status = 'pending_payment'
            order.save()
            logger.info(f'Order {order.id} marked as pending_payment after Stripe payment')
        
        return True, f'Payment confirmed for order {order.id}'
        
    except Payment.DoesNotExist:
        error_msg = f'No payment found for session {session_id}'
        logger.error(error_msg)
        return False, error_msg
    except stripe.error.StripeError as e:
        error_msg = f'Stripe error retrieving session: {str(e)}'
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f'Unexpected error handling session completion: {str(e)}'
        logger.error(error_msg)
        return False, error_msg


def handle_payment_intent_failed(payment_intent_id, event):
    """
    Handles payment_intent.payment_failed webhook event.
    Called when a payment attempt fails.
    
    Args:
        payment_intent_id: Stripe Payment Intent ID
        event: Full webhook event dictionary
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Find payment by intent ID
        payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
        payment.status = 'failed'
        payment.last_webhook_event = 'payment_intent.payment_failed'
        payment.webhook_event_timestamp = timezone.now()
        payment.save()
        
        order = payment.order
        if order.status == 'pending':
            order.status = 'pending'  # Keep as pending, customer can retry
            order.save()
        
        logger.warning(f'Payment failed for order {order.id}, intent {payment_intent_id}')
        return True, f'Payment failed for order {order.id}'
        
    except Payment.DoesNotExist:
        error_msg = f'No payment found for intent {payment_intent_id}'
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f'Error handling payment failure: {str(e)}'
        logger.error(error_msg)
        return False, error_msg


def handle_charge_refunded(charge_id, event):
    """
    Handles charge.refunded webhook event.
    Called when a charge is refunded.
    
    Args:
        charge_id: Stripe Charge ID
        event: Full webhook event dictionary
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        payment = Payment.objects.get(stripe_charge_id=charge_id)
        payment.status = 'refunded'
        payment.last_webhook_event = 'charge.refunded'
        payment.webhook_event_timestamp = timezone.now()
        payment.save()
        
        order = payment.order
        # You might want to create a refund record or trigger special handling here
        logger.info(f'Charge refunded for order {order.id}, charge {charge_id}')
        return True, f'Refund processed for order {order.id}'
        
    except Payment.DoesNotExist:
        error_msg = f'No payment found for charge {charge_id}'
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f'Error handling refund: {str(e)}'
        logger.error(error_msg)
        return False, error_msg


def verify_webhook_signature(payload, sig_header, webhook_secret):
    """
    Verifies that a webhook came from Stripe using the signature header.
    
    Args:
        payload: Raw request body (bytes)
        sig_header: Stripe-Signature header value
        webhook_secret: Webhook signing secret from Stripe dashboard
    
    Returns:
        tuple: (event_dict or None, error_message or None)
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return event, None
    except ValueError as e:
        # Invalid payload
        error_msg = f'Invalid payload: {str(e)}'
        logger.error(error_msg)
        return None, error_msg
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        error_msg = f'Invalid signature: {str(e)}'
        logger.error(error_msg)
        return None, error_msg


def get_session_url(session_id):
    """
    Retrieves the Stripe Checkout URL for a session.
    Used for redirecting the customer to pay.
    
    Args:
        session_id: Stripe Session ID
    
    Returns:
        str: The Stripe checkout URL, or None if not found
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.url
    except stripe.error.StripeError as e:
        logger.error(f'Error retrieving session {session_id}: {str(e)}')
        return None
