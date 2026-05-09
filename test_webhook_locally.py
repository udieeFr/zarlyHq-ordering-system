"""
Test Stripe webhook locally by simulating the webhook event.
This helps verify your webhook handler works without needing Stripe CLI.
"""

import os
import django
import json
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zarlyOs.settings")
django.setup()

from customers.stripe_utils import handle_checkout_session_completed
from admins.models import Payment, Order
from django.conf import settings

def test_webhook_simulation():
    """Simulate a Stripe webhook by directly calling the handler."""
    
    # Get the most recent pending payment
    pending_payment = Payment.objects.filter(
        payment_method='stripe',
        status='pending'
    ).order_by('-created_at').first()
    
    if not pending_payment:
        print("❌ No pending Stripe payments found to test!")
        return
    
    print(f"\n🧪 Testing webhook for Payment ID: {pending_payment.id}")
    print(f"   Order: {pending_payment.order_id}")
    print(f"   Session ID: {pending_payment.stripe_session_id}")
    
    # Simulate the webhook event
    simulated_event = {
        'id': 'evt_test_123',
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'id': pending_payment.stripe_session_id,
                'payment_intent': 'pi_test_1234567890',  # Simulated payment intent
                'customer': 'cus_test_1234567890'
            }
        }
    }
    
    print("\n📨 Calling webhook handler...")
    success, message = handle_checkout_session_completed(
        pending_payment.stripe_session_id,
        simulated_event
    )
    
    if success:
        print(f"✅ Webhook processed successfully: {message}")
    else:
        print(f"❌ Webhook failed: {message}")
        return
    
    # Refresh from database to see updated values
    pending_payment.refresh_from_db()
    
    print(f"\n📊 Updated Payment Record:")
    print(f"   Status: {pending_payment.status}")
    print(f"   Intent ID: {pending_payment.stripe_payment_intent_id}")
    print(f"   Charge ID: {pending_payment.stripe_charge_id}")
    print(f"   Customer ID: {pending_payment.stripe_customer_id}")
    print(f"   Paid At: {pending_payment.paid_at}")
    
    # Check if order_has_confirmed_payment() would now return True
    from admins.views import order_has_confirmed_payment
    order = pending_payment.order
    has_payment = order_has_confirmed_payment(order)
    
    print(f"\n🔍 Order Payment Confirmation Check:")
    print(f"   Order ID: {order.id}")
    print(f"   Order Status: {order.status}")
    print(f"   order_has_confirmed_payment(): {has_payment}")
    
    if has_payment:
        print(f"   ✅ Order is READY for admin approval → will go to APPROVED table")
    else:
        print(f"   ❌ Order still needs manual payment proof")

if __name__ == '__main__':
    test_webhook_simulation()
