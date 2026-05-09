import os
import django

os.environ['DJANGO_SETTINGS_MODULE'] = 'zarlyOs.settings'
django.setup()

from admins.models import Payment
from django.utils import timezone

# Get latest pending payment
p = Payment.objects.filter(payment_method='stripe', status='pending').order_by('-created_at').first()

if p:
    print(f'Found pending payment #{p.id} for order #{p.order_id}')
    print(f'Before: status={p.status}, intent_id={p.stripe_payment_intent_id}')
    
    # Simulate webhook update
    p.status = 'succeeded'
    p.stripe_payment_intent_id = f'pi_test_{p.id}'
    p.stripe_charge_id = f'ch_test_{p.id}'
    p.paid_at = timezone.now()
    p.save()
    
    print(f'After: status={p.status}, intent_id={p.stripe_payment_intent_id}')
    print('\n✅ Payment updated! Refresh the admin page to see "Payment Succeeded"')
else:
    print('❌ No pending Stripe payments found')
