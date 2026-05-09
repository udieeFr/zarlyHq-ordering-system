#!/usr/bin/env python
"""
Diagnostic script to check webhook signature verification
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zarlyOs.settings")
django.setup()

from django.conf import settings
from customers.stripe_utils import verify_webhook_signature
import json

print("=" * 60)
print("WEBHOOK SIGNATURE VERIFICATION DIAGNOSTIC")
print("=" * 60)

# Check webhook secret
webhook_secret = settings.STRIPE_WEBHOOK_SECRET
print(f"\n✓ STRIPE_WEBHOOK_SECRET from settings:")
print(f"  {webhook_secret[:20]}...{webhook_secret[-20:]}")

# Check if it matches expected format
if webhook_secret.startswith('whsec_'):
    print(f"  ✓ Correct format (starts with 'whsec_')")
else:
    print(f"  ✗ WRONG FORMAT! Should start with 'whsec_'")

# List recent payments to understand state
from admins.models import Payment

print(f"\n✓ Recent Payment Records:")
recent = Payment.objects.all().order_by('-created_at')[:3]
for p in recent:
    print(f"\n  Payment ID: {p.id}")
    print(f"    Order: {p.order_id}")
    print(f"    Method: {p.payment_method}")
    print(f"    Status: {p.status}")
    print(f"    Session ID: {p.stripe_session_id[:20]}...")
    print(f"    Intent ID: {p.stripe_payment_intent_id or 'NOT SET (webhook not fired!)'}")
    print(f"    Last webhook: {p.last_webhook_event or 'None'}")
    print(f"    Paid at: {p.paid_at or 'Not set'}")

print("\n" + "=" * 60)
print("WHAT TO DO NEXT:")
print("=" * 60)
print("""
1. Check if Stripe CLI is running in another terminal
   Command: stripe listen --forward-to localhost:8000/stripe/webhook/

2. Check if the webhook secret matches:
   - Copy the 'whsec_...' from Stripe CLI output
   - Paste it into .env as STRIPE_WEBHOOK_SECRET=...
   - Restart Django

3. Create a new test order and complete Stripe checkout

4. Check the Stripe CLI terminal for 'checkout.session.completed' event

5. If payment still shows "Initiated", check Django logs for:
   "Webhook signature verification failed"
""")
