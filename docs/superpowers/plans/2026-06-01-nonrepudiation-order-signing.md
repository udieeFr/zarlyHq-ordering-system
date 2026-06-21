# Nonrepudiation Order Signing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two-party nonrepudiation to the order workflow — customers commit to exact order contents via OTP + SHA-256 hash (NRO), and the company's signed PDF embeds the approving admin's identity (NRF).

**Architecture:** The existing `submit_order` view is split into two steps: staging (creates order as `pending_confirmation`, computes commitment hash, sends OTP) and `confirm_order` (verifies OTP, moves order to `pending`, logs audit). The commitment hash is written into the signed PDF at approval time alongside the admin's identity, so a single signed document covers both parties.

**Tech Stack:** Django 6.0, PyHanko (PDF signing), ReportLab (PDF generation), Django cache (OTP), existing `otp_utils.py` patterns, pytest + `pytest-django`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `admins/models.py` | Modify | Add `pending_confirmation` status, `customer_commitment_hash`, `customer_confirmed_at`, new AuditLog action |
| `admins/migrations/XXXX_customer_commitment.py` | Create | DB migration for new fields |
| `customers/otp_utils.py` | Modify | Add order-confirmation OTP functions (separate cache key prefix) |
| `customers/views.py` | Modify | Split `submit_order` into staging + add `confirm_order` view |
| `customers/urls.py` | Modify | Add `confirm_order` URL |
| `admins/utils.py` | Modify | Embed admin identity + customer commitment hash in invoice PDF |
| `admins/views.py` | Modify | Exclude `pending_confirmation` from admin dashboard `base_pending` query |
| `templates/customers/order_confirmation.html` | Create | Order summary + OTP input page |
| `templates/customers/verify_receipt.html` | Modify | Show admin identity + commitment hash |
| `admins/management/commands/cancel_unconfirmed_orders.py` | Create | Cancel orders stuck in `pending_confirmation` > 30 min |
| `tests/test_nonrepudiation.py` | Create | All tests for this feature |

---

## Task 1: Model Fields + AuditLog Action

**Files:**
- Modify: `admins/models.py`
- Create: `admins/migrations/XXXX_customer_commitment.py` (auto-generated)
- Test: `tests/test_nonrepudiation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_nonrepudiation.py`:

```python
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from admins.models import Order, AuditLog

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestOrderCommitmentFields:

    def test_order_has_pending_confirmation_status(self, test_customer):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
        )
        order.refresh_from_db()
        assert order.status == 'pending_confirmation'

    def test_order_commitment_hash_defaults_empty(self, test_customer):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending',
        )
        assert order.customer_commitment_hash == ''

    def test_order_confirmed_at_defaults_null(self, test_customer):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending',
        )
        assert order.customer_confirmed_at is None

    def test_order_commitment_hash_can_be_stored(self, test_customer):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
            customer_commitment_hash='a' * 64,
        )
        order.refresh_from_db()
        assert order.customer_commitment_hash == 'a' * 64

    def test_audit_log_has_order_confirmed_action(self, test_customer):
        action_types = [a[0] for a in AuditLog.ACTION_CHOICES]
        assert 'order_confirmed_by_customer' in action_types
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_nonrepudiation.py -v
```

Expected: 5 failures — `pending_confirmation` not in STATUS_CHOICES, fields don't exist, action not in choices.

- [ ] **Step 3: Add fields and action to models**

In `admins/models.py`, add `('pending_confirmation', 'Pending Customer Confirmation')` as the **first** entry in `Order.STATUS_CHOICES`:

```python
STATUS_CHOICES = (
    ('pending_confirmation', 'Pending Customer Confirmation'),
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    # ... rest unchanged
)
```

Add two fields to the `Order` model, after the `otp_code` field (line ~35):

```python
customer_commitment_hash = models.CharField(max_length=64, blank=True, default='')
customer_confirmed_at    = models.DateTimeField(null=True, blank=True)
```

In `AuditLog.ACTION_CHOICES`, add after `('order_created', 'Order Created')`:

```python
('order_confirmed_by_customer', 'Order Confirmed by Customer (OTP)'),
```

- [ ] **Step 4: Generate and apply migration**

```
python manage.py makemigrations admins --name customer_commitment
python manage.py migrate
```

Expected output includes: `Applying admins.XXXX_customer_commitment... OK`

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_nonrepudiation.py::TestOrderCommitmentFields -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```
git add admins/models.py admins/migrations/ tests/test_nonrepudiation.py
git commit -m "feat: add customer_commitment_hash fields and pending_confirmation status to Order"
```

---

## Task 2: Commitment Hash Utility

**Files:**
- Modify: `customers/views.py` (add helper function at top of file)
- Test: `tests/test_nonrepudiation.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_nonrepudiation.py`:

```python
from customers.views import compute_order_commitment_hash
from admins.models import OrderItem
from customers.models import Product


class TestCommitmentHash:

    def test_hash_is_64_char_hex(self, test_customer, test_product):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('60.00'),
            shipping_fee=Decimal('10.00'),
            status='pending_confirmation',
            formatted_address='123 Jalan Test, KL',
        )
        OrderItem.objects.create(
            order=order, product=test_product,
            quantity=1, unit_price=Decimal('50.00'),
            is_bundle=False, subtotal=Decimal('50.00'),
        )
        h = compute_order_commitment_hash(order)
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)

    def test_hash_is_deterministic(self, test_customer, test_product):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('60.00'),
            shipping_fee=Decimal('10.00'),
            status='pending_confirmation',
            formatted_address='123 Jalan Test, KL',
        )
        OrderItem.objects.create(
            order=order, product=test_product,
            quantity=2, unit_price=Decimal('25.00'),
            is_bundle=False, subtotal=Decimal('50.00'),
        )
        assert compute_order_commitment_hash(order) == compute_order_commitment_hash(order)

    def test_hash_changes_if_total_changes(self, test_customer, test_product):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('60.00'),
            shipping_fee=Decimal('10.00'),
            status='pending_confirmation',
        )
        OrderItem.objects.create(
            order=order, product=test_product,
            quantity=1, unit_price=Decimal('50.00'),
            is_bundle=False, subtotal=Decimal('50.00'),
        )
        h1 = compute_order_commitment_hash(order)
        order.total_amount = Decimal('70.00')
        order.save(update_fields=['total_amount'])
        h2 = compute_order_commitment_hash(order)
        assert h1 != h2
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_nonrepudiation.py::TestCommitmentHash -v
```

Expected: ImportError — `compute_order_commitment_hash` not defined.

- [ ] **Step 3: Add the function to customers/views.py**

Add this function near the top of `customers/views.py`, after the imports section (before `customer_signup`):

```python
def compute_order_commitment_hash(order):
    """
    SHA-256 of the order's identity-bound contents.
    Stored at staging time to lock what the customer was shown.
    Recomputing and comparing proves the DB was not altered post-confirmation.
    """
    import json
    items = list(
        order.items.values('product_id', 'quantity', 'unit_price', 'is_bundle')
    )
    items_sorted = sorted(items, key=lambda x: x['product_id'])
    for item in items_sorted:
        item['unit_price'] = str(item['unit_price'])
    items_json = json.dumps(items_sorted, sort_keys=True)
    content = '|'.join([
        str(order.id),
        str(order.customer_id),
        items_json,
        str(order.total_amount),
        str(order.shipping_fee),
        order.formatted_address or '',
        order.created_at.isoformat(),
    ])
    return hashlib.sha256(content.encode('utf-8')).hexdigest()
```

`hashlib` is already imported in `customers/views.py` at line 29.

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_nonrepudiation.py::TestCommitmentHash -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add customers/views.py tests/test_nonrepudiation.py
git commit -m "feat: add compute_order_commitment_hash utility"
```

---

## Task 3: Order Confirmation OTP Functions

**Files:**
- Modify: `customers/otp_utils.py`
- Test: `tests/test_nonrepudiation.py`

The existing `generate_and_cache_otp` uses cache key `email_otp_{user_pk}`. We need a **separate** key prefix so the order OTP does not collide with email verification OTPs (e.g., if the customer verifies email while an order confirmation is pending).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_nonrepudiation.py`:

```python
from customers.otp_utils import (
    generate_and_cache_order_otp,
    verify_order_otp,
)
from django.core.cache import cache


class TestOrderOtp:

    def test_generate_order_otp_returns_6_digits(self, test_customer):
        otp = generate_and_cache_order_otp(test_customer)
        assert len(otp) == 6
        assert otp.isdigit()

    def test_verify_order_otp_ok(self, test_customer):
        otp = generate_and_cache_order_otp(test_customer)
        assert verify_order_otp(test_customer, otp) == 'ok'

    def test_verify_order_otp_invalid(self, test_customer):
        generate_and_cache_order_otp(test_customer)
        assert verify_order_otp(test_customer, '000000') == 'invalid'

    def test_verify_order_otp_expired_when_not_generated(self, test_customer):
        cache.delete(f'order_confirm_otp_{test_customer.pk}')
        assert verify_order_otp(test_customer, '123456') == 'expired'

    def test_order_otp_does_not_collide_with_email_otp(self, test_customer):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        email_otp = generate_and_cache_otp(test_customer)
        order_otp = generate_and_cache_order_otp(test_customer)
        # Verifying email OTP still works after order OTP was generated
        assert verify_otp(test_customer, email_otp) == 'ok'
        assert verify_order_otp(test_customer, order_otp) == 'ok'
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_nonrepudiation.py::TestOrderOtp -v
```

Expected: ImportError — functions not yet defined.

- [ ] **Step 3: Add functions to customers/otp_utils.py**

Add at the end of `customers/otp_utils.py`:

```python
# ── Order confirmation OTP (separate key prefix — must not collide with email_otp_) ──

def _order_confirm_cache_key(user_pk):
    return f'order_confirm_otp_{user_pk}'


def _order_confirm_attempts_key(user_pk):
    return f'order_confirm_otp_attempts_{user_pk}'


def generate_and_cache_order_otp(user):
    """Generate a 6-digit OTP for order confirmation. Separate from email verification OTP."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_order_confirm_cache_key(user.pk), code, OTP_TTL)
    cache.delete(_order_confirm_attempts_key(user.pk))
    return code


def verify_order_otp(user, submitted_code):
    """
    Verify an order-confirmation OTP.
    Returns: 'ok' | 'invalid' | 'expired'
    Single-use; invalidated after MAX_ATTEMPTS wrong guesses.
    """
    key = _order_confirm_cache_key(user.pk)
    stored = cache.get(key)
    if stored is None:
        return 'expired'

    att_key = _order_confirm_attempts_key(user.pk)
    attempts = (cache.get(att_key) or 0) + 1

    if stored != submitted_code:
        if attempts >= MAX_ATTEMPTS:
            cache.delete(key)
            cache.delete(att_key)
            return 'expired'
        cache.set(att_key, attempts, OTP_TTL)
        return 'invalid'

    cache.delete(key)
    cache.delete(att_key)
    return 'ok'


def send_order_confirmation_email(user, otp, order):
    """Send OTP with order summary so customer can confirm the exact contents."""
    try:
        items = list(order.items.select_related('product').all())
        send_mail(
            subject=f'Confirm your order #{order.id} — ZarlyHQ',
            message=(
                f'Hi {user.username},\n\n'
                f'Your confirmation code for Order #{order.id} is: {otp}\n'
                f'It expires in 5 minutes.\n\n'
                f'Order total: RM {order.total_amount}\n'
                f'Items: {", ".join(f"{i.product.name} x{i.quantity}" for i in items)}\n\n'
                f'Enter this code on the confirmation page to place your order.'
            ),
            from_email=None,
            recipient_list=[user.email],
        )
    except Exception as e:
        logger.warning(f'Could not send order confirmation email to {user.email}: {e}')
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_nonrepudiation.py::TestOrderOtp -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add customers/otp_utils.py tests/test_nonrepudiation.py
git commit -m "feat: add order confirmation OTP functions with separate cache key prefix"
```

---

## Task 4: Split submit_order into Staging + confirm_order

**Files:**
- Modify: `customers/views.py`
- Test: `tests/test_nonrepudiation.py`

**What changes in `submit_order`:**
- Status becomes `pending_confirmation` instead of `pending`
- After order creation: compute commitment hash, store on order, send OTP
- Payment method saved to session (not processed yet — moved to `confirm_order`)
- Redirect to `confirm_order` instead of Stripe/`order_success`

**What `confirm_order` does:**
- Verifies OTP
- Stamps `customer_confirmed_at`, sets status → `pending`
- Reads payment method from session, processes Stripe or manual payment
- Logs audit + notifies admins

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_nonrepudiation.py`:

```python
from django.test import Client
from django.urls import reverse


class TestSubmitOrderStaging:

    def test_submit_order_creates_pending_confirmation(self, test_customer, test_product):
        test_customer.email_verified = True
        test_customer.save()
        client = Client()
        client.force_login(test_customer)
        session = client.session
        session['cart'] = {str(test_product.id): 1}
        session['checkout_key'] = 'testkey123'
        session.save()
        client.post(reverse('submit_order'), {
            'full_name': 'Test User',
            'phone_number': '0123456789',
            'street_address': '1 Jalan Test',
            'city': 'Kuala Lumpur',
            'state': 'Wilayah Persekutuan',
            'postcode': '50000',
            'payment_method': 'manual',
            'manual_payment_timing': 'later',
            'checkout_key': 'testkey123',
        })
        order = Order.objects.filter(customer=test_customer).first()
        assert order is not None
        assert order.status == 'pending_confirmation'

    def test_submit_order_stores_commitment_hash(self, test_customer, test_product):
        test_customer.email_verified = True
        test_customer.save()
        client = Client()
        client.force_login(test_customer)
        session = client.session
        session['cart'] = {str(test_product.id): 1}
        session['checkout_key'] = 'testkey456'
        session.save()
        client.post(reverse('submit_order'), {
            'full_name': 'Test User',
            'phone_number': '0123456789',
            'street_address': '1 Jalan Test',
            'city': 'Kuala Lumpur',
            'state': 'Wilayah Persekutuan',
            'postcode': '50000',
            'payment_method': 'manual',
            'manual_payment_timing': 'later',
            'checkout_key': 'testkey456',
        })
        order = Order.objects.filter(customer=test_customer).first()
        assert len(order.customer_commitment_hash) == 64

    def test_confirm_order_with_valid_otp_moves_to_pending(self, test_customer):
        from customers.otp_utils import generate_and_cache_order_otp
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
            customer_commitment_hash='a' * 64,
        )
        otp = generate_and_cache_order_otp(test_customer)
        client = Client()
        client.force_login(test_customer)
        session = client.session
        session[f'pending_payment_method_{order.id}'] = 'manual'
        session[f'pending_manual_timing_{order.id}'] = 'later'
        session.save()
        client.post(reverse('confirm_order', args=[order.id]), {'otp': otp})
        order.refresh_from_db()
        assert order.status == 'pending'
        assert order.customer_confirmed_at is not None

    def test_confirm_order_with_invalid_otp_stays_pending_confirmation(self, test_customer):
        from customers.otp_utils import generate_and_cache_order_otp
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
            customer_commitment_hash='a' * 64,
        )
        generate_and_cache_order_otp(test_customer)
        client = Client()
        client.force_login(test_customer)
        client.post(reverse('confirm_order', args=[order.id]), {'otp': '000000'})
        order.refresh_from_db()
        assert order.status == 'pending_confirmation'

    def test_confirm_order_logs_audit_with_commitment_hash(self, test_customer):
        from customers.otp_utils import generate_and_cache_order_otp
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
            customer_commitment_hash='b' * 64,
        )
        otp = generate_and_cache_order_otp(test_customer)
        client = Client()
        client.force_login(test_customer)
        session = client.session
        session[f'pending_payment_method_{order.id}'] = 'manual'
        session[f'pending_manual_timing_{order.id}'] = 'later'
        session.save()
        client.post(reverse('confirm_order', args=[order.id]), {'otp': otp})
        log = AuditLog.objects.filter(
            action_type='order_confirmed_by_customer',
            target_id=order.id,
        ).first()
        assert log is not None
        assert log.metadata.get('commitment_hash') == 'b' * 64
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_nonrepudiation.py::TestSubmitOrderStaging -v
```

Expected: failures — `confirm_order` URL not found, order status still `pending`, no audit log entry.

- [ ] **Step 3: Modify submit_order in customers/views.py**

Find the section in `submit_order` that creates the `OrderEvent` and calls `log_audit` (currently around line 727). **Replace everything from `OrderEvent.objects.create(...)` to the end of the view** with this:

```python
        from admins.models import OrderEvent
        OrderEvent.objects.create(order=order, status='pending_confirmation', actor=request.user)

        # Compute and store commitment hash — locks in what customer was shown
        order.customer_commitment_hash = compute_order_commitment_hash(order)
        order.save(update_fields=['customer_commitment_hash'])

        # Save payment intent to session — processed after OTP confirmation
        request.session[f'pending_payment_method_{order.id}'] = payment_method
        if payment_method == 'manual':
            request.session[f'pending_manual_timing_{order.id}'] = request.POST.get('manual_payment_timing', 'later')

        # Send OTP email with order summary
        from customers.otp_utils import generate_and_cache_order_otp, send_order_confirmation_email
        otp = generate_and_cache_order_otp(request.user)
        send_order_confirmation_email(request.user, otp, order)

        log_audit(request, 'order_created', target=order,
                  description=f"Customer staged Order #{order.id} — awaiting OTP confirmation",
                  metadata={'total': str(grand_total), 'items': len(cart_items),
                            'commitment_hash': order.customer_commitment_hash})

        # Clear cart now — stock was already decremented in _create_order_atomic
        request.session['cart'] = {}
        request.session.modified = True

        return redirect('confirm_order', order_id=order.id)

    return redirect('checkout')
```

Also update the `_create_order_atomic` call to pass `status='pending_confirmation'`:

```python
        order = _create_order_atomic(
            request.user, grand_total, cart_items,
            status='pending_confirmation',          # ← changed from default 'pending'
            shipping_fee=shipping_fee,
            ...
        )
```

`_create_order_atomic` currently hardcodes `status='pending'` inside. Update that function's `Order.objects.create(...)` call to accept the status from `order_fields`:

In `_create_order_atomic`, change:
```python
        order = Order.objects.create(
            customer=user,
            total_amount=total_price,
            status='pending',
            **order_fields,
        )
```
to:
```python
        order = Order.objects.create(
            customer=user,
            total_amount=total_price,
            **order_fields,
        )
```

(`status` will now arrive via `**order_fields` with value `'pending_confirmation'`.)

- [ ] **Step 4: Add confirm_order view to customers/views.py**

Add this view after the `submit_order` function:

```python
@customer_required
@ratelimit(key='user', rate='5/m', method='POST', block=False)
def confirm_order(request, order_id):
    """
    Step 2 of order placement: customer enters the OTP emailed at staging time.
    Verifies OTP, stamps commitment, moves order to pending, then handles payment routing.
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user,
                              status='pending_confirmation')

    from customers.otp_utils import (
        verify_order_otp, generate_and_cache_order_otp, send_order_confirmation_email, mask_email,
    )

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many attempts. Please wait before trying again.')
            return redirect('confirm_order', order_id=order_id)

        code = request.POST.get('otp', '').strip()

        if request.POST.get('action') == 'resend':
            otp = generate_and_cache_order_otp(request.user)
            send_order_confirmation_email(request.user, otp, order)
            messages.success(request, f'A new code was sent to {mask_email(request.user.email)}.')
            return redirect('confirm_order', order_id=order_id)

        result = verify_order_otp(request.user, code)

        if result == 'ok':
            from django.utils import timezone as tz
            from admins.models import OrderEvent
            order.customer_confirmed_at = tz.now()
            order.status = 'pending'
            order.save(update_fields=['status', 'customer_confirmed_at'])

            OrderEvent.objects.create(order=order, status='pending', actor=request.user)
            log_audit(request, 'order_confirmed_by_customer', target=order,
                      description=f'Customer confirmed Order #{order.id} via OTP',
                      metadata={
                          'commitment_hash': order.customer_commitment_hash,
                          'confirmed_at': order.customer_confirmed_at.isoformat(),
                      })

            # Retrieve payment intent stored at staging
            payment_method = request.session.pop(f'pending_payment_method_{order.id}', 'manual')
            manual_timing = request.session.pop(f'pending_manual_timing_{order.id}', 'later')

            notify_admins(
                title='New order received',
                message=f'Customer {request.user.username} confirmed Order #{order.id} for RM {order.total_amount}.',
                link=f'/dashboard/order/{order.id}/detail/',
                notification_type='admin_alert',
            )

            # Route payment
            if payment_method == 'stripe':
                session_id, error = create_stripe_checkout_session(order, request)
                if error:
                    messages.error(request, f'Could not create Stripe session: {error}')
                    return redirect('order_success', order_id=order.id)
                checkout_url = get_session_url(session_id)
                if not checkout_url:
                    messages.error(request, 'Could not open Stripe checkout. Please try again.')
                    return redirect('order_success', order_id=order.id)
                log_audit(request, 'payment_initiated', target=order,
                          description=f'Stripe checkout started for Order #{order.id}',
                          metadata={'stripe_session_id': session_id})
                return redirect(checkout_url)

            else:  # manual
                Payment.objects.create(
                    order=order,
                    payment_method='manual',
                    status='pending',
                    amount=order.total_amount,
                    currency=settings.STRIPE_CURRENCY,
                )
                request.session[f'payment_timing_{order.id}'] = manual_timing
                if manual_timing == 'now':
                    messages.success(request, f'Order #{order.id} confirmed! Please complete payment below.')
                else:
                    messages.success(request, f'Order #{order.id} confirmed! Pay from your dashboard after approval.')
                return redirect('order_success', order_id=order.id)

        elif result == 'invalid':
            messages.error(request, 'Incorrect code. Please try again.')

        else:  # expired / max attempts
            _cancel_pending_confirmation_order(order, request.user)
            messages.error(request, 'Code expired. Your order was cancelled — please start again.')
            return redirect('checkout')

    return render(request, 'customers/order_confirmation.html', {
        'order': order,
        'masked_email': mask_email(request.user.email),
    })


def _cancel_pending_confirmation_order(order, user):
    """Restore stock and cancel an unconfirmed order."""
    from admins.models import OrderEvent
    for item in order.items.select_related('product').all():
        if item.is_bundle:
            if not item.product.is_unlimited_stock and item.product.bundle_stock is not None:
                item.product.bundle_stock += item.quantity
                item.product.save(update_fields=['bundle_stock'])
        else:
            if not item.product.is_unlimited_stock:
                item.product.stock += item.quantity
                item.product.save(update_fields=['stock'])
    order.status = 'cancelled'
    order.save(update_fields=['status'])
    OrderEvent.objects.create(order=order, status='cancelled', actor=user,
                              note='Cancelled: OTP confirmation expired')
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_nonrepudiation.py::TestSubmitOrderStaging -v
```

Expected: 5 passed.

- [ ] **Step 6: Run full test suite to check for regressions**

```
pytest tests/ -v --tb=short
```

Fix any failures before proceeding.

- [ ] **Step 7: Commit**

```
git add customers/views.py tests/test_nonrepudiation.py
git commit -m "feat: split submit_order into staging + confirm_order with OTP commitment"
```

---

## Task 5: URL + Order Confirmation Template

**Files:**
- Modify: `customers/urls.py`
- Create: `templates/customers/order_confirmation.html`

- [ ] **Step 1: Add URL to customers/urls.py**

After the `submit-order` line:

```python
path('order/<int:order_id>/confirm/', views.confirm_order, name='confirm_order'),
```

- [ ] **Step 2: Create templates/customers/order_confirmation.html**

```html
{% extends "base.html" %}

{% block title %}Confirm Your Order — ZarlyHQ{% endblock %}

{% block content %}
<div class="container py-5" style="max-width: 640px;">
  <h2 class="fw-bold mb-1">Confirm Your Order</h2>
  <p class="text-muted mb-4">
    We sent a 6-digit code to <strong>{{ masked_email }}</strong>.
    Enter it below to place your order.
  </p>

  <!-- Order Summary -->
  <div class="card mb-4 border-0 shadow-sm">
    <div class="card-header fw-semibold">Order #{{ order.id }} Summary</div>
    <ul class="list-group list-group-flush">
      {% for item in order.items.all %}
      <li class="list-group-item d-flex justify-content-between">
        <span>{{ item.product.name }} {% if item.is_bundle %}(Bundle){% endif %} × {{ item.quantity }}</span>
        <span>RM {{ item.subtotal }}</span>
      </li>
      {% endfor %}
      <li class="list-group-item d-flex justify-content-between text-muted">
        <span>Shipping</span>
        <span>RM {{ order.shipping_fee }}</span>
      </li>
      <li class="list-group-item d-flex justify-content-between fw-bold">
        <span>Total</span>
        <span>RM {{ order.total_amount }}</span>
      </li>
    </ul>
    <div class="card-footer text-muted small">
      Delivery to: {{ order.formatted_address|default:"—" }}
    </div>
  </div>

  <!-- Messages -->
  {% if messages %}
  {% for message in messages %}
  <div class="alert alert-{{ message.tags|default:'info' }} mb-3">{{ message }}</div>
  {% endfor %}
  {% endif %}

  <!-- OTP Form -->
  <form method="post">
    {% csrf_token %}
    <input type="hidden" name="action" value="verify">
    <div class="mb-3">
      <label class="form-label fw-semibold">Confirmation Code</label>
      <input type="text" name="otp" class="form-control form-control-lg text-center"
             maxlength="6" placeholder="_ _ _ _ _ _" autocomplete="one-time-code"
             inputmode="numeric" autofocus>
    </div>
    <button type="submit" class="btn btn-primary w-100 py-2 fw-semibold">
      Confirm Order
    </button>
  </form>

  <!-- Resend -->
  <form method="post" class="mt-3 text-center">
    {% csrf_token %}
    <input type="hidden" name="action" value="resend">
    <button type="submit" class="btn btn-link btn-sm text-muted">
      Didn't receive it? Resend code
    </button>
  </form>

  <p class="text-center text-muted small mt-3">
    By confirming, you acknowledge that the above order details are correct.
    This confirmation is cryptographically recorded for nonrepudiation purposes.
  </p>
</div>
{% endblock %}
```

- [ ] **Step 3: Verify manually**

Start the dev server, add items to cart, proceed through checkout. Verify:
- You are redirected to `/order/<id>/confirm/` after checkout submission
- The OTP email is sent (check terminal/email backend output)
- Entering the correct OTP redirects to `order_success`
- Entering the wrong OTP shows "Incorrect code"
- The order in the DB shows `status='pending'` and `customer_confirmed_at` is set after correct OTP

- [ ] **Step 4: Commit**

```
git add customers/urls.py templates/customers/order_confirmation.html
git commit -m "feat: add confirm_order URL and order confirmation template"
```

---

## Task 6: Embed Admin Identity + Commitment Hash in PDF

**Files:**
- Modify: `admins/utils.py`
- Test: `tests/test_nonrepudiation.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_nonrepudiation.py`:

```python
import os
from django.conf import settings
from admins.utils import generate_invoice_pdf
from customers.models import User as UserModel


class TestPdfAdminIdentity:

    def test_pdf_embeds_approver_name(self, test_customer, test_product, test_sales_admin):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('50.00'),
            status='pending',
            customer_commitment_hash='c' * 64,
            approved_by=test_sales_admin,
        )
        OrderItem.objects.create(
            order=order, product=test_product,
            quantity=1, unit_price=Decimal('50.00'),
            is_bundle=False, subtotal=Decimal('50.00'),
        )
        pdf_path = generate_invoice_pdf(order, approver=test_sales_admin)
        assert os.path.exists(pdf_path)
        # Read raw PDF bytes and check approver name is embedded as text
        with open(pdf_path, 'rb') as f:
            content = f.read()
        assert test_sales_admin.username.encode() in content

    def test_pdf_embeds_commitment_hash_prefix(self, test_customer, test_product, test_sales_admin):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('50.00'),
            status='pending',
            customer_commitment_hash='d' * 64,
        )
        OrderItem.objects.create(
            order=order, product=test_product,
            quantity=1, unit_price=Decimal('50.00'),
            is_bundle=False, subtotal=Decimal('50.00'),
        )
        pdf_path = generate_invoice_pdf(order, approver=test_sales_admin)
        with open(pdf_path, 'rb') as f:
            content = f.read()
        # First 16 chars of hash should appear in PDF
        assert ('d' * 16).encode() in content
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_nonrepudiation.py::TestPdfAdminIdentity -v
```

Expected: FAIL — approver name and hash prefix not in PDF content.

- [ ] **Step 3: Update generate_invoice_pdf in admins/utils.py**

At the end of `generate_invoice_pdf`, before `c.save()`, add the nonrepudiation footer section. Insert after the total line (`c.drawString(350, y-40, ...)`):

```python
    # Nonrepudiation section
    y_nr = y - 80
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.line(50, y_nr + 10, 550, y_nr + 10)
    c.drawString(50, y_nr, "NONREPUDIATION RECORD")
    y_nr -= 14
    if approver:
        c.drawString(50, y_nr,
            f"Approved by: {approver.username} ({approver.role})  |  "
            f"Approved at: {order.approved_at.strftime('%Y-%m-%d %H:%M UTC') if order.approved_at else 'pending'}"
        )
        y_nr -= 12
    if order.customer_confirmed_at:
        c.drawString(50, y_nr,
            f"Customer confirmed: {order.customer_confirmed_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        y_nr -= 12
    if order.customer_commitment_hash:
        c.drawString(50, y_nr,
            f"Commitment hash: {order.customer_commitment_hash[:32]}..."
        )
        y_nr -= 12
    c.setFillColorRGB(0, 0, 0)
```

This block goes **before** the existing `c.save()` at line 58. The `y_nr` variable is local to this block and does not affect the existing `y` used for items.

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_nonrepudiation.py::TestPdfAdminIdentity -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add admins/utils.py tests/test_nonrepudiation.py
git commit -m "feat: embed admin identity and customer commitment hash in invoice PDF"
```

---

## Task 7: Update verify_receipt.html

**Files:**
- Modify: `templates/customers/verify_receipt.html`

- [ ] **Step 1: Read the current template**

```
Read: templates/customers/verify_receipt.html
```

- [ ] **Step 2: Add commitment hash and admin identity display**

Inside the `status == 'valid'` block, add after the existing `Signed by` line:

```html
{% if result.cert_subject %}
<tr>
  <td class="text-muted">Signed by</td>
  <td>{{ result.cert_subject }}</td>
</tr>
{% endif %}
{% if result.signing_time %}
<tr>
  <td class="text-muted">Signed at</td>
  <td>{{ result.signing_time }}</td>
</tr>
{% endif %}
```

Add below those:

```html
{% comment %}Admin identity and customer commitment — embedded in PDF at approval time{% endcomment %}
<tr>
  <td class="text-muted">Approved by</td>
  <td>{{ order.approved_by.username|default:"—" }} ({{ order.approved_by.get_role_display|default:"—" }})</td>
</tr>
{% if order.customer_confirmed_at %}
<tr>
  <td class="text-muted">Customer confirmed</td>
  <td>{{ order.customer_confirmed_at|date:"Y-m-d H:i" }} UTC</td>
</tr>
{% endif %}
{% if order.customer_commitment_hash %}
<tr>
  <td class="text-muted">Commitment hash</td>
  <td><code>{{ order.customer_commitment_hash|slice:":16" }}…</code>
      <small class="text-muted d-block">SHA-256 of order contents at customer confirmation time</small>
  </td>
</tr>
{% endif %}
<tr>
  <td class="text-muted">Certificate trust</td>
  <td>
    <span class="text-warning">⚠ Self-signed</span>
    <small class="text-muted d-block">Identity claim unverified by a trusted CA</small>
  </td>
</tr>
```

The `verify_receipt` view needs to pass the `order` object to the template. Update `customers/views.py::verify_receipt` — in the `result` dict, add the order object. Find the line:

```python
    result = {
        'order_id': sig_record.order_id,
        'signed_at': sig_record.timestamp,
```

Change to:

```python
    from admins.models import Order as AdminOrder
    try:
        sig_order = AdminOrder.objects.select_related('approved_by').get(pk=sig_record.order_id)
    except AdminOrder.DoesNotExist:
        sig_order = None

    result = {
        'order_id': sig_record.order_id,
        'order': sig_order,
        'signed_at': sig_record.timestamp,
```

- [ ] **Step 3: Verify manually**

Approve an order in the admin dashboard, visit the verify URL from the order success page. Confirm that the admin identity and commitment hash appear in the verification result.

- [ ] **Step 4: Commit**

```
git add templates/customers/verify_receipt.html customers/views.py
git commit -m "feat: show admin identity and commitment hash on verify_receipt page"
```

---

## Task 8: Management Command — Cancel Unconfirmed Orders

**Files:**
- Create: `admins/management/commands/cancel_unconfirmed_orders.py`
- Test: `tests/test_nonrepudiation.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_nonrepudiation.py`:

```python
from django.utils import timezone
from datetime import timedelta
from django.core.management import call_command


class TestCancelUnconfirmedOrders:

    def test_cancels_orders_older_than_30_minutes(self, test_customer, test_product):
        old_order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
            customer_commitment_hash='e' * 64,
        )
        # Backdate created_at to 31 minutes ago
        Order.objects.filter(pk=old_order.pk).update(
            created_at=timezone.now() - timedelta(minutes=31)
        )
        call_command('cancel_unconfirmed_orders', '--dry-run=false')
        old_order.refresh_from_db()
        assert old_order.status == 'cancelled'

    def test_does_not_cancel_recent_orders(self, test_customer):
        recent_order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
            customer_commitment_hash='f' * 64,
        )
        call_command('cancel_unconfirmed_orders', '--dry-run=false')
        recent_order.refresh_from_db()
        assert recent_order.status == 'pending_confirmation'
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_nonrepudiation.py::TestCancelUnconfirmedOrders -v
```

Expected: FAIL — command not found.

- [ ] **Step 3: Create the management command**

Create `admins/management/commands/cancel_unconfirmed_orders.py`:

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from admins.models import Order, OrderEvent

TIMEOUT_MINUTES = 30


class Command(BaseCommand):
    help = f'Cancel orders stuck in pending_confirmation for more than {TIMEOUT_MINUTES} minutes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            default='true',
            help='Set to false to actually cancel orders (default: true = preview only)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run'].lower() != 'false'
        cutoff = timezone.now() - timedelta(minutes=TIMEOUT_MINUTES)
        stale = Order.objects.filter(
            status='pending_confirmation',
            created_at__lt=cutoff,
        ).select_related('customer').prefetch_related('items__product')

        count = stale.count()
        if dry_run:
            self.stdout.write(f'[DRY RUN] Would cancel {count} unconfirmed order(s).')
            for order in stale:
                self.stdout.write(f'  Order #{order.id} — {order.customer.username} — created {order.created_at}')
            return

        cancelled = 0
        for order in stale:
            # Restore stock
            for item in order.items.all():
                if item.is_bundle:
                    if not item.product.is_unlimited_stock and item.product.bundle_stock is not None:
                        item.product.bundle_stock += item.quantity
                        item.product.save(update_fields=['bundle_stock'])
                else:
                    if not item.product.is_unlimited_stock:
                        item.product.stock += item.quantity
                        item.product.save(update_fields=['stock'])
            order.status = 'cancelled'
            order.save(update_fields=['status'])
            OrderEvent.objects.create(
                order=order, status='cancelled', actor=None,
                note=f'Auto-cancelled: OTP confirmation timeout ({TIMEOUT_MINUTES} min)',
            )
            cancelled += 1

        self.stdout.write(self.style.SUCCESS(f'Cancelled {cancelled} unconfirmed order(s).'))
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_nonrepudiation.py::TestCancelUnconfirmedOrders -v
```

Expected: 2 passed.

- [ ] **Step 5: Test the command manually**

```
python manage.py cancel_unconfirmed_orders
```

Expected output: `[DRY RUN] Would cancel 0 unconfirmed order(s).`

```
python manage.py cancel_unconfirmed_orders --dry-run=false
```

Expected: `Cancelled 0 unconfirmed order(s).`

- [ ] **Step 6: Commit**

```
git add admins/management/commands/cancel_unconfirmed_orders.py tests/test_nonrepudiation.py
git commit -m "feat: add cancel_unconfirmed_orders management command for OTP timeout cleanup"
```

---

## Task 9: Exclude pending_confirmation from Admin Dashboard

**Files:**
- Modify: `admins/views.py`

Admin staff should only see orders the customer has confirmed. `pending_confirmation` orders are not yet customer-committed and should not appear in the admin queue.

- [ ] **Step 1: Find the base_pending query**

In `admins/views.py` at line 803:

```python
base_pending = Order.objects.filter(status='pending')
```

- [ ] **Step 2: Update the query**

```python
base_pending = Order.objects.filter(status='pending')  # excludes pending_confirmation by design
```

This line is already correct — `status='pending'` does not include `pending_confirmation`. Verify no other dashboard queries accidentally catch it:

```
grep -n "pending_confirmation\|status.*pending\b" admins/views.py
```

Check every `status='pending'` result — none should be changed to `status__in=['pending', 'pending_confirmation']`. The `pending_confirmation` status is customer-facing only.

- [ ] **Step 3: Verify the customer orders dashboard**

In `customers/views.py::customer_orders`, the `upcoming_orders` query filters on:

```python
status__in=['pending', 'prepared', 'ready_for_delivery', 'out_for_delivery'],
```

Add `'pending_confirmation'` so the customer can see their staged order while waiting to confirm:

```python
status__in=['pending_confirmation', 'pending', 'prepared', 'ready_for_delivery', 'out_for_delivery'],
```

- [ ] **Step 4: Run the full test suite**

```
pytest tests/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add admins/views.py customers/views.py
git commit -m "feat: show pending_confirmation in customer dashboard, exclude from admin queue"
```

---

## Self-Review

**Spec coverage check:**
- ✅ `pending_confirmation` status — Task 1
- ✅ `customer_commitment_hash` + `customer_confirmed_at` — Task 1
- ✅ `order_confirmed_by_customer` AuditLog action — Task 1
- ✅ Commitment hash utility — Task 2
- ✅ Order OTP separate from email verification OTP — Task 3
- ✅ Split `submit_order` into staging + `confirm_order` — Task 4
- ✅ `confirm_order` URL — Task 5
- ✅ `order_confirmation.html` template — Task 5
- ✅ Admin identity + commitment hash embedded in PDF — Task 6
- ✅ `verify_receipt.html` updated — Task 7
- ✅ Management command for 30-min timeout — Task 8
- ✅ `pending_confirmation` excluded from admin queue — Task 9

**Placeholder scan:** No TBDs, no "add validation" stubs, all code blocks complete.

**Type consistency:**
- `compute_order_commitment_hash(order)` — defined Task 2, used Task 4 ✅
- `verify_order_otp(user, code)` — defined Task 3, used Task 4 ✅
- `generate_and_cache_order_otp(user)` — defined Task 3, used Tasks 4 + 5 ✅
- `send_order_confirmation_email(user, otp, order)` — defined Task 3, used Tasks 4 + 5 ✅
- `_cancel_pending_confirmation_order(order, user)` — defined Task 4, used Task 4 ✅
