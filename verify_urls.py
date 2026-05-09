#!/usr/bin/env python
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zarlyOs.settings")
django.setup()

from django.urls import reverse
from customers.urls import urlpatterns

print("✓ URL patterns loaded successfully")
print(f"✓ Total patterns: {len(urlpatterns)}")

# Check for awaiting_payment_orders
found = False
for pattern in urlpatterns:
    if hasattr(pattern, 'name') and pattern.name == 'awaiting_payment_orders':
        found = True
        print(f"✓ URL pattern 'awaiting_payment_orders' found: {pattern.pattern}")
        break

if found:
    try:
        url = reverse('awaiting_payment_orders')
        print(f"✓ URL resolves to: {url}")
    except Exception as e:
        print(f"✗ URL error: {e}")
else:
    print("✗ URL pattern 'awaiting_payment_orders' not found in urlpatterns")

# List all available URL names
print("\nAvailable URL names:")
for pattern in urlpatterns:
    if hasattr(pattern, 'name'):
        print(f"  - {pattern.name}")
