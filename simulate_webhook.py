#!/usr/bin/env python
"""
Manual Webhook Simulator for Testing Stripe Payment Flow Locally
This script simulates Stripe webhook events to test the payment flow
without needing Stripe CLI or internet connectivity.
"""
import os
import sys
import django
import json
import stripe

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zarlyOs.settings")
django.setup()

from django.conf import settings
from admins.models import Payment, Order
from customers.stripe_utils import handle_checkout_session_completed
from django.utils import timezone

print("=" * 70)
print("STRIPE WEBHOOK SIMULATOR FOR LOCAL TESTING")
print("=" * 70)

# Get the most recent pending Stripe payment
pending = Payment.objects.filter(
    payment_method='stripe',
    status='pending'
).order_by('-created_at').first()

if not pending:
    print("\n❌ No pending Stripe payments found!")
    print("   Please create an order with Stripe payment first.")
    sys.exit(1)

print(f"\n✓ Found pending Stripe payment:")
print(f"  Payment ID: {pending.id}")
print(f"  Order ID: {pending.order_id}")
print(f"  Session ID: {pending.stripe_session_id}")
print(f"  Amount: RM {pending.amount}")

# Confirm action
print(f"\n⚠️  This will update Payment #{pending.id} to 'succeeded' status")
response = input("   Continue? (y/n): ").strip().lower()
if response != 'y':
    print("Cancelled.")
    sys.exit(0)

# Simulate webhook event
print(f"\n📨 Simulating webhook: checkout.session.completed...")
print(f"   Stripe Session ID: {pending.stripe_session_id}")

simulated_event = {
    'id': f'evt_test_{pending.id}',
    'type': 'checkout.session.completed',
    'data': {
        'object': {
            'id': pending.stripe_session_id,
            'payment_intent': f'pi_test_{pending.id}',
            'customer': f'cus_test_{pending.id}'
        }
    }
}

try:
    success, message = handle_checkout_session_completed(
        pending.stripe_session_id,
        simulated_event
    )
    
    if success:
        print(f"\n✅ Webhook processed successfully!")
        print(f"   Message: {message}")
    else:
        print(f"\n❌ Webhook processing failed!")
        print(f"   Error: {message}")
        sys.exit(1)
        
except Exception as e:
    print(f"\n❌ Exception during webhook processing:")
    print(f"   {str(e)}")
    sys.exit(1)

# Verify the payment was updated
pending.refresh_from_db()
print(f"\n✓ Updated Payment Record:")
print(f"  Status: {pending.status}")
print(f"  Intent ID: {pending.stripe_payment_intent_id}")
print(f"  Charge ID: {pending.stripe_charge_id}")
print(f"  Paid At: {pending.paid_at}")

# Check order confirmation
from admins.views import order_has_confirmed_payment
order = pending.order
confirmed = order_has_confirmed_payment(order)

print(f"\n✓ Order Status:")
print(f"  Order ID: {order.id}")
print(f"  Order Status: {order.status}")
print(f"  Has Confirmed Payment: {confirmed}")

if confirmed:
    print(f"\n✅ SUCCESS! Payment is confirmed.")
    print(f"   Admin can now approve this order → it will go to APPROVED table")
else:
    print(f"\n❌ Payment not confirmed. Check the admin panel.")

print("\n" + "=" * 70)
print("NEXT STEPS:")
print("=" * 70)
print("""
1. Refresh the admin order detail page in your browser
2. The payment status should now show "✅ Stripe Payment Confirmed"
3. The "Approve & Generate Signed Receipt" button should be available
4. Click it to approve the order → order goes to APPROVED table
""")
