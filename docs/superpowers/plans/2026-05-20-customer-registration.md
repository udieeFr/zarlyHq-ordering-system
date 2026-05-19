# Customer Registration + Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add customer self-registration with a 3-field signup form, 6-digit OTP email verification (5-minute TTL stored in Django cache), and an order-placement gate for unverified accounts.

**Architecture:** A new `customers/otp_utils.py` module handles all OTP generation, caching, and email sending. Five new views are added to `customers/views.py`. The checkout gate sits inside the existing `submit_order` view, checked before the idempotency key is consumed. Verification is not required to browse — only to place an order.

**Tech Stack:** Django 6.0, django-ratelimit 4.1.0, Django cache (LocMemCache in dev / Redis in prod), Django's built-in `send_mail`, `secrets` module for cryptographic OTP generation.

---

## File Map

| Action | File | What changes |
|---|---|---|
| Create | `customers/otp_utils.py` | OTP generation, cache storage, email sending, email masking |
| Modify | `customers/models.py` | Add `email_verified = BooleanField(default=False)` |
| Create | `customers/migrations/0013_user_email_verified.py` | Schema migration |
| Create | `customers/migrations/0014_backfill_email_verified.py` | Data migration — sets `True` for all existing users |
| Modify | `customers/views.py` | `CustomerRegistrationForm`, 5 new views, checkout gate, `_process_otp_post` helper |
| Modify | `zarlyOs/urls.py` | 5 new URL patterns, new imports |
| Create | `templates/registration/register.html` | Signup form page |
| Create | `templates/registration/verify_email.html` | OTP entry + skip button |
| Create | `templates/registration/verify_required.html` | Checkout gate page |
| Create | `templates/emails/email_verification.html` | Transactional OTP email |
| Modify | `templates/registration/login.html` | Replace "Contact staff" text with "Create account" link |
| Create | `tests/test_registration.py` | All registration + verification tests |
| Modify | `tests/conftest.py` | Set `email_verified=True` on existing fixtures so checkout tests don't break |

---

## Task 1: OTP Utilities Module

**Files:**
- Create: `customers/otp_utils.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Create the test file with OTP utility tests**

```python
# tests/test_registration.py
"""
Tests for customer registration, email OTP verification, and checkout gate.
"""
import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()
pytestmark = pytest.mark.django_db


def make_customer(username='cust1', email=None, password='Pass123!ZZ', verified=False):
    user = User.objects.create_user(
        username=username,
        email=email or f'{username}@test.com',
        password=password,
        role='customer',
    )
    user.email_verified = verified
    user.save(update_fields=['email_verified'])
    return user


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# ── OTP utilities ─────────────────────────────────────────────────────────────

class TestOtpUtils:

    def test_generate_returns_six_digit_string(self):
        from customers.otp_utils import generate_and_cache_otp
        user = make_customer('otp_gen')
        code = generate_and_cache_otp(user)
        assert len(code) == 6
        assert code.isdigit()

    def test_generated_code_stored_in_cache(self):
        from customers.otp_utils import generate_and_cache_otp
        from django.core.cache import cache
        user = make_customer('otp_cache')
        code = generate_and_cache_otp(user)
        assert cache.get(f'email_otp_{user.pk}') == code

    def test_verify_ok_on_correct_code(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        user = make_customer('otp_ok')
        code = generate_and_cache_otp(user)
        assert verify_otp(user, code) == 'ok'

    def test_verify_deletes_cache_on_success(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        from django.core.cache import cache
        user = make_customer('otp_del')
        code = generate_and_cache_otp(user)
        verify_otp(user, code)
        assert cache.get(f'email_otp_{user.pk}') is None

    def test_verify_invalid_on_wrong_code(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        user = make_customer('otp_bad')
        generate_and_cache_otp(user)
        assert verify_otp(user, '000000') == 'invalid'

    def test_verify_expired_when_no_cache_entry(self):
        from customers.otp_utils import verify_otp
        user = make_customer('otp_exp')
        assert verify_otp(user, '123456') == 'expired'

    def test_resend_overwrites_old_code(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        user = make_customer('otp_resend')
        old_code = generate_and_cache_otp(user)
        new_code = generate_and_cache_otp(user)
        assert verify_otp(user, old_code) == 'invalid'
        assert verify_otp(user, new_code) == 'ok'

    def test_mask_email_hides_middle_chars(self):
        from customers.otp_utils import mask_email
        assert mask_email('johndoe@gmail.com') == 'j*****e@g****.com'

    def test_mask_email_short_local(self):
        from customers.otp_utils import mask_email
        assert mask_email('ab@test.com') == 'a*@t***.com'
```

- [ ] **Step 2: Run tests to confirm they all fail**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestOtpUtils -v
```

Expected: `ModuleNotFoundError: No module named 'customers.otp_utils'`

- [ ] **Step 3: Create `customers/otp_utils.py`**

```python
import secrets
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)

OTP_TTL = 300  # 5 minutes


def _cache_key(user_pk):
    return f'email_otp_{user_pk}'


def generate_and_cache_otp(user):
    """Generate a cryptographically random 6-digit code and store it in cache."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_cache_key(user.pk), code, OTP_TTL)
    return code


def verify_otp(user, submitted_code):
    """
    Check a submitted OTP against the cached value.
    Returns: 'ok' | 'invalid' | 'expired'
    Deletes the cache entry immediately on correct submission (single-use).
    """
    key = _cache_key(user.pk)
    stored = cache.get(key)
    if stored is None:
        return 'expired'
    if stored != submitted_code:
        return 'invalid'
    cache.delete(key)
    return 'ok'


def mask_email(email):
    """e.g. johndoe@gmail.com -> j*****e@g****.com"""
    local, domain = email.rsplit('@', 1)
    if len(local) <= 1:
        masked_local = local
    elif len(local) == 2:
        masked_local = local[0] + '*'
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]

    parts = domain.rsplit('.', 1)
    if len(parts) == 2:
        name, tld = parts
        masked_name = name[0] + '*' * max(1, len(name) - 1)
        masked_domain = f"{masked_name}.{tld}"
    else:
        masked_domain = domain

    return f"{masked_local}@{masked_domain}"


def send_verification_email(user, otp):
    """Send the 6-digit OTP to the user's email address."""
    try:
        body = render_to_string('emails/email_verification.html', {
            'username': user.username,
            'otp': otp,
        })
        send_mail(
            subject='Your ZarlyHQ verification code',
            message=f'Your verification code is: {otp}. It expires in 5 minutes.',
            from_email=None,
            recipient_list=[user.email],
            html_message=body,
        )
    except Exception as e:
        logger.warning(f'Could not send verification email to {user.email}: {e}')
```

- [ ] **Step 4: Run tests — all OTP utility tests should pass**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestOtpUtils -v
```

Expected: 9 tests PASSED

- [ ] **Step 5: Commit**

```
git add customers/otp_utils.py tests/test_registration.py
git commit -m "feat: add OTP utility module (generate, verify, mask, send)"
```

---

## Task 2: User Model Field + Migrations

**Files:**
- Modify: `customers/models.py`
- Create: `customers/migrations/0013_user_email_verified.py`
- Create: `customers/migrations/0014_backfill_email_verified.py`

- [ ] **Step 1: Write the migration tests**

Add to `tests/test_registration.py`:

```python
# ── Model field ───────────────────────────────────────────────────────────────

class TestEmailVerifiedField:

    def test_new_user_defaults_to_unverified(self):
        user = make_customer('new_unverified')
        assert user.email_verified is False

    def test_can_set_verified_true(self):
        user = make_customer('set_verified')
        user.email_verified = True
        user.save(update_fields=['email_verified'])
        user.refresh_from_db()
        assert user.email_verified is True
```

- [ ] **Step 2: Run tests — they should fail (field doesn't exist yet)**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestEmailVerifiedField -v
```

Expected: `AttributeError: 'User' object has no attribute 'email_verified'`

- [ ] **Step 3: Add field to `customers/models.py`**

In `customers/models.py`, inside the `User` class, after the `phone_number` line:

```python
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email_verified = models.BooleanField(default=False)
```

- [ ] **Step 4: Create schema migration**

```
venv\Scripts\python.exe manage.py makemigrations customers --name user_email_verified
```

This generates `customers/migrations/0013_user_email_verified.py`. Verify it contains:

```python
migrations.AddField(
    model_name='user',
    name='email_verified',
    field=models.BooleanField(default=False),
),
```

- [ ] **Step 5: Create data migration (backfill existing users to verified=True)**

Create `customers/migrations/0014_backfill_email_verified.py` manually:

```python
from django.db import migrations


def backfill_email_verified(apps, schema_editor):
    """All accounts that existed before this feature ships are considered verified."""
    User = apps.get_model('customers', 'User')
    User.objects.all().update(email_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0013_user_email_verified'),
    ]

    operations = [
        migrations.RunPython(backfill_email_verified, migrations.RunPython.noop),
    ]
```

- [ ] **Step 6: Apply migrations**

```
venv\Scripts\python.exe manage.py migrate
```

Expected: `Running migrations: Applying customers.0013... OK  Applying customers.0014... OK`

- [ ] **Step 7: Run model tests**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestEmailVerifiedField -v
```

Expected: 2 tests PASSED

- [ ] **Step 8: Commit**

```
git add customers/models.py customers/migrations/0013_user_email_verified.py customers/migrations/0014_backfill_email_verified.py tests/test_registration.py
git commit -m "feat: add email_verified field to User, backfill existing accounts"
```

---

## Task 3: Registration View + URL

**Files:**
- Modify: `customers/views.py`
- Modify: `zarlyOs/urls.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Write the registration view tests**

Add to `tests/test_registration.py`:

```python
# ── Registration view ─────────────────────────────────────────────────────────

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TestRegistrationView:

    def test_get_renders_form(self):
        c = Client()
        response = c.get(reverse('register'))
        assert response.status_code == 200
        assert b'username' in response.content.lower()

    def test_post_creates_user(self):
        c = Client()
        response = c.post(reverse('register'), {
            'username': 'newuser',
            'email': 'newuser@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        assert User.objects.filter(username='newuser').exists()

    def test_post_sets_role_customer(self):
        c = Client()
        c.post(reverse('register'), {
            'username': 'rolecheck',
            'email': 'rolecheck@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        assert User.objects.get(username='rolecheck').role == 'customer'

    def test_post_sets_email_verified_false(self):
        c = Client()
        c.post(reverse('register'), {
            'username': 'unverifcheck',
            'email': 'uv@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        assert User.objects.get(username='unverifcheck').email_verified is False

    def test_post_redirects_to_verify_page(self):
        c = Client()
        response = c.post(reverse('register'), {
            'username': 'redirectcheck',
            'email': 'rc@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        assert response.status_code == 302
        assert response['Location'] == reverse('verify_email')

    def test_duplicate_email_rejected(self):
        make_customer('existing', email='taken@test.com')
        c = Client()
        response = c.post(reverse('register'), {
            'username': 'newguy',
            'email': 'taken@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        assert response.status_code == 200
        assert not User.objects.filter(username='newguy').exists()

    def test_duplicate_username_rejected(self):
        make_customer('taken_name')
        c = Client()
        response = c.post(reverse('register'), {
            'username': 'taken_name',
            'email': 'different@test.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        assert response.status_code == 200
        assert User.objects.filter(username='taken_name').count() == 1

    def test_authenticated_user_redirected_away(self):
        user = make_customer('already_in', verified=True)
        c = Client()
        c.force_login(user)
        response = c.get(reverse('register'))
        assert response.status_code == 302
```

- [ ] **Step 2: Run tests — they should fail**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestRegistrationView -v
```

Expected: `NoReverseMatch: Reverse for 'register' not found`

- [ ] **Step 3: Add `CustomerRegistrationForm` and `register_customer` view to `customers/views.py`**

At the top of `customers/views.py`, add to the existing import line:

```python
from django.contrib.auth import logout, login as auth_login
```

(Replace the existing `from django.contrib.auth import logout` line.)

Then add the form class and view anywhere before the end of the file (after the existing imports section is a good place — add near the other auth-related code):

```python
# ── Customer Registration ──────────────────────────────────────────────────────

from django import forms as django_forms
from django.contrib.auth.forms import UserCreationForm as _UserCreationForm


class CustomerRegistrationForm(_UserCreationForm):
    email = django_forms.EmailField(
        required=True,
        widget=django_forms.EmailInput(attrs={'autocomplete': 'email', 'class': 'form-control'}),
    )

    class Meta:
        from customers.models import User as _User
        model = _User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not field.widget.attrs.get('class'):
                field.widget.attrs['class'] = 'form-control'

    def clean_email(self):
        from customers.models import User as _User
        email = self.cleaned_data['email'].lower()
        if _User.objects.filter(email__iexact=email).exists():
            raise django_forms.ValidationError('An account with this email already exists.')
        return email


@ratelimit(key='ip', rate='10/h', method='POST', block=False)
def register_customer(request):
    if request.user.is_authenticated:
        return redirect('product_list')

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many registration attempts. Please try again later.')
            return render(request, 'registration/register.html', {'form': CustomerRegistrationForm()})

        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            from customers.models import CustomerProfile
            from customers.otp_utils import generate_and_cache_otp, send_verification_email

            user = form.save(commit=False)
            user.role = 'customer'
            user.email_verified = False
            user.save()

            CustomerProfile.objects.get_or_create(user=user)

            auth_login(request, user)

            otp = generate_and_cache_otp(user)
            send_verification_email(user, otp)

            log_audit(request, 'registration_success', target=user,
                      description=f'New customer registration: {user.username}')

            return redirect('verify_email')
    else:
        form = CustomerRegistrationForm()

    return render(request, 'registration/register.html', {'form': form})
```

- [ ] **Step 4: Add URL to `zarlyOs/urls.py`**

Add the import at the top of `zarlyOs/urls.py`, updating the existing customers import line:

```python
from customers.views import (
    stripe_webhook,
    home as customer_home_view,
    register_customer,
)
```

Add the URL pattern inside `urlpatterns`, after the `path('login/', ...)` line:

```python
    path('register/', register_customer, name='register'),
```

- [ ] **Step 5: Run tests**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestRegistrationView -v
```

Expected: 8 tests PASSED

- [ ] **Step 6: Commit**

```
git add customers/views.py zarlyOs/urls.py tests/test_registration.py
git commit -m "feat: add customer registration view with email uniqueness validation"
```

---

## Task 4: Email Verification Views + URLs

**Files:**
- Modify: `customers/views.py`
- Modify: `zarlyOs/urls.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Write verification view tests**

Add to `tests/test_registration.py`:

```python
# ── Verification views ────────────────────────────────────────────────────────

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TestVerifyEmailView:

    def test_get_renders_otp_form(self):
        user = make_customer('v_get')
        c = Client()
        c.force_login(user)
        response = c.get(reverse('verify_email'))
        assert response.status_code == 200

    def test_already_verified_redirects(self):
        user = make_customer('v_already', verified=True)
        c = Client()
        c.force_login(user)
        response = c.get(reverse('verify_email'))
        assert response.status_code == 302

    def test_correct_otp_marks_verified(self):
        from customers.otp_utils import generate_and_cache_otp
        user = make_customer('v_correct')
        c = Client()
        c.force_login(user)
        code = generate_and_cache_otp(user)
        c.post(reverse('verify_email'), {'otp': code})
        user.refresh_from_db()
        assert user.email_verified is True

    def test_correct_otp_redirects_to_menu(self):
        from customers.otp_utils import generate_and_cache_otp
        user = make_customer('v_redirect')
        c = Client()
        c.force_login(user)
        code = generate_and_cache_otp(user)
        response = c.post(reverse('verify_email'), {'otp': code})
        assert response.status_code == 302
        assert response['Location'] == reverse('product_list')

    def test_correct_otp_with_checkout_redirect(self):
        from customers.otp_utils import generate_and_cache_otp
        user = make_customer('v_checkout')
        c = Client()
        c.force_login(user)
        session = c.session
        session['post_verify_redirect'] = 'checkout'
        session.save()
        code = generate_and_cache_otp(user)
        response = c.post(reverse('verify_email'), {'otp': code})
        assert response['Location'] == reverse('checkout')

    def test_wrong_otp_shows_error(self):
        from customers.otp_utils import generate_and_cache_otp
        user = make_customer('v_wrong')
        c = Client()
        c.force_login(user)
        generate_and_cache_otp(user)
        response = c.post(reverse('verify_email'), {'otp': '000000'})
        assert response.status_code == 200
        assert b'Incorrect' in response.content

    def test_expired_otp_shows_error(self):
        user = make_customer('v_expired')
        c = Client()
        c.force_login(user)
        response = c.post(reverse('verify_email'), {'otp': '123456'})
        assert response.status_code == 200
        assert b'expired' in response.content.lower()

    def test_non_digit_otp_shows_error(self):
        user = make_customer('v_nondigit')
        c = Client()
        c.force_login(user)
        response = c.post(reverse('verify_email'), {'otp': 'abcdef'})
        assert response.status_code == 200


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TestResendOtp:

    def test_resend_generates_new_code(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        user = make_customer('resend1')
        c = Client()
        c.force_login(user)
        old = generate_and_cache_otp(user)
        c.post(reverse('resend_otp'))
        assert verify_otp(user, old) == 'invalid'

    def test_resend_returns_json_ok(self):
        user = make_customer('resend2')
        c = Client()
        c.force_login(user)
        response = c.post(reverse('resend_otp'),
                          content_type='application/json',
                          HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        import json
        assert json.loads(response.content)['ok'] is True

    def test_resend_blocked_for_verified_user(self):
        user = make_customer('resend3', verified=True)
        c = Client()
        c.force_login(user)
        response = c.post(reverse('resend_otp'))
        assert response.status_code == 400
```

- [ ] **Step 2: Run tests — they should fail**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestVerifyEmailView tests/test_registration.py::TestResendOtp -v
```

Expected: `NoReverseMatch: Reverse for 'verify_email' not found`

- [ ] **Step 3: Add the shared OTP helper and three views to `customers/views.py`**

Add after the `register_customer` view:

```python
def _process_otp_post(request):
    """
    Shared POST logic for both verify_email and verification_required views.
    Returns ('ok', redirect_url) or ('error', error_message).
    """
    from customers.otp_utils import verify_otp

    submitted = request.POST.get('otp', '').strip()
    if not submitted.isdigit() or len(submitted) != 6:
        return 'error', 'Please enter the 6-digit code from your email.'

    result = verify_otp(request.user, submitted)

    if result == 'ok':
        request.user.email_verified = True
        request.user.save(update_fields=['email_verified'])
        log_audit(request, 'email_verified', target=request.user,
                  description=f'Email verified: {request.user.username}')
        redirect_to = request.session.pop('post_verify_redirect', None)
        url = 'checkout' if redirect_to == 'checkout' else 'product_list'
        return 'ok', url

    if result == 'expired':
        return 'error', 'That code has expired. Request a new one below.'

    log_audit(request, 'verify_failed', target=request.user,
              description=f'Failed OTP attempt: {request.user.username}')
    return 'error', 'Incorrect code. Please try again.'


@customer_required
@ratelimit(key='user', rate='10/5m', method='POST', block=False)
def verify_email(request):
    if request.user.email_verified:
        return redirect('product_list')

    error = None

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            error = 'Too many attempts. Please wait before trying again.'
        else:
            status, payload = _process_otp_post(request)
            if status == 'ok':
                return redirect(payload)
            error = payload

    from customers.otp_utils import mask_email
    return render(request, 'registration/verify_email.html', {
        'masked_email': mask_email(request.user.email),
        'error': error,
    })


@customer_required
@ratelimit(key='user', rate='10/5m', method='POST', block=False)
def verification_required(request):
    if request.user.email_verified:
        return redirect('product_list')

    error = None

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            error = 'Too many attempts. Please wait before trying again.'
        else:
            status, payload = _process_otp_post(request)
            if status == 'ok':
                messages.success(request, 'Email verified! Complete your order below.')
                return redirect(payload)
            error = payload

    from customers.otp_utils import mask_email, generate_and_cache_otp, send_verification_email
    if not request.session.get('_otp_sent_for_required'):
        otp = generate_and_cache_otp(request.user)
        send_verification_email(request.user, otp)
        request.session['_otp_sent_for_required'] = True

    return render(request, 'registration/verify_required.html', {
        'masked_email': mask_email(request.user.email),
        'error': error,
    })


@customer_required
@ratelimit(key='user', rate='1/m', method='POST', block=False)
def resend_verification_otp(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    if request.user.email_verified:
        return JsonResponse({'error': 'Already verified'}, status=400)

    if getattr(request, 'limited', False):
        return JsonResponse(
            {'error': 'Please wait a minute before requesting another code.'},
            status=429,
        )

    from customers.otp_utils import generate_and_cache_otp, send_verification_email
    otp = generate_and_cache_otp(request.user)
    send_verification_email(request.user, otp)
    log_audit(request, 'verify_resend', target=request.user,
              description=f'OTP resent: {request.user.username}')

    return JsonResponse({'ok': True})
```

- [ ] **Step 4: Add URLs to `zarlyOs/urls.py`**

Update the import at the top:

```python
from customers.views import (
    stripe_webhook,
    home as customer_home_view,
    register_customer,
    verify_email,
    verification_required,
    resend_verification_otp,
)
```

Add URL patterns after `path('register/', ...)`:

```python
    path('register/verify/', verify_email, name='verify_email'),
    path('register/resend/', resend_verification_otp, name='resend_otp'),
    path('verify-required/', verification_required, name='verification_required'),
```

- [ ] **Step 5: Run verification tests**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestVerifyEmailView tests/test_registration.py::TestResendOtp -v
```

Expected: all tests PASSED

- [ ] **Step 6: Commit**

```
git add customers/views.py zarlyOs/urls.py tests/test_registration.py
git commit -m "feat: add email OTP verification views (verify, resend, verification_required)"
```

---

## Task 5: Checkout Gate + Conftest Update

**Files:**
- Modify: `customers/views.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Write checkout gate tests**

Add to `tests/test_registration.py`:

```python
# ── Checkout gate ─────────────────────────────────────────────────────────────

class TestCheckoutGate:

    def _make_product(self):
        from customers.models import Product, Category
        from decimal import Decimal
        cat, _ = Category.objects.get_or_create(name='GateTest')
        return Product.objects.create(
            name='Gate Burger', category=cat, price=Decimal('10.00'), stock=5
        )

    def test_unverified_user_redirected_on_submit(self):
        user = make_customer('gate_unverified', verified=False)
        product = self._make_product()
        c = Client()
        c.force_login(user)
        session = c.session
        session['cart'] = {str(product.id): 1}
        session['checkout_key'] = 'testkey123'
        session.save()
        response = c.post(reverse('submit_order'), {
            'checkout_key': 'testkey123',
            'full_name': 'Test User',
            'phone_number': '0123456789',
            'street_address': '1 Jalan Test',
            'city': 'KL',
            'state': 'Selangor',
            'postcode': '50000',
            'payment_method': 'manual',
        })
        assert response.status_code == 302
        assert reverse('verification_required') in response['Location']

    def test_unverified_redirect_stores_session_key(self):
        user = make_customer('gate_session', verified=False)
        product = self._make_product()
        c = Client()
        c.force_login(user)
        session = c.session
        session['cart'] = {str(product.id): 1}
        session['checkout_key'] = 'key456'
        session.save()
        c.post(reverse('submit_order'), {
            'checkout_key': 'key456',
            'full_name': 'Test',
            'phone_number': '0123456789',
            'street_address': '1 Jalan',
            'city': 'KL',
            'state': 'Selangor',
            'postcode': '50000',
            'payment_method': 'manual',
        })
        assert c.session.get('post_verify_redirect') == 'checkout'

    def test_verified_user_not_redirected_to_verify(self):
        user = make_customer('gate_verified', verified=True)
        c = Client()
        c.force_login(user)
        response = c.post(reverse('submit_order'), {})
        assert response.status_code != 302 or reverse('verification_required') not in response.get('Location', '')
```

- [ ] **Step 2: Run gate tests — they should fail**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestCheckoutGate -v
```

Expected: `test_unverified_user_redirected_on_submit` FAILS (no redirect to verification_required)

- [ ] **Step 3: Add the gate to `submit_order` in `customers/views.py`**

In `submit_order`, after the rate limit check and before the idempotency key pop, insert:

```python
        # Email verification gate
        if not request.user.email_verified:
            request.session['post_verify_redirect'] = 'checkout'
            return redirect('verification_required')
```

The surrounding context should look like this after the edit:

```python
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many orders submitted. Please wait a moment before trying again.')
            return redirect('checkout')

        # Email verification gate
        if not request.user.email_verified:
            request.session['post_verify_redirect'] = 'checkout'
            return redirect('verification_required')

        # Idempotency guard: one-time key generated on checkout page load, consumed here.
        key = request.POST.get('checkout_key', '')
        session_key = request.session.pop('checkout_key', None)
```

- [ ] **Step 4: Run gate tests**

```
venv\Scripts\python.exe -m pytest tests/test_registration.py::TestCheckoutGate -v
```

Expected: 3 tests PASSED

- [ ] **Step 5: Update `tests/conftest.py` to prevent existing tests from breaking**

The `test_customer` fixture creates users that will now have `email_verified=False` by default (the backfill only runs on the real DB, not test DB). Any test that calls `submit_order` needs a verified customer.

In `tests/conftest.py`, update the `test_customer` fixture:

```python
@pytest.fixture
def test_customer():
    user = User.objects.create_user(
        username='testcustomer',
        email='customer1@test.com',
        password='TestPass123!',
        role='customer',
    )
    user.email_verified = True
    user.save(update_fields=['email_verified'])
    return user
```

- [ ] **Step 6: Run the full test suite to check for regressions**

```
venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

Expected: all previously passing tests still pass

- [ ] **Step 7: Commit**

```
git add customers/views.py tests/conftest.py tests/test_registration.py
git commit -m "feat: add checkout gate blocking unverified customers from placing orders"
```

---

## Task 6: Customer-Facing Templates

**Files:**
- Create: `templates/registration/register.html`
- Create: `templates/registration/verify_email.html`
- Create: `templates/registration/verify_required.html`
- Modify: `templates/registration/login.html`

- [ ] **Step 1: Create `templates/registration/register.html`**

```html
{% extends 'base.html' %}
{% load static %}

{% block content %}
<div class="container py-5">
    <div class="row justify-content-center min-vh-100 align-items-center">
        <div class="col-md-5">
            <div class="card border-0 login-card">
                <div class="card-body p-5">
                    <div class="text-center mb-4">
                        <div class="login-logo-wrap">🍊</div>
                        <h2 class="fw-bold mb-1" style="letter-spacing:-0.02em;">Create Account</h2>
                        <p class="text-muted mb-0" style="font-size:0.875rem;">Join Zarly BigFood</p>
                    </div>

                    {% if form.errors %}
                    <div class="alert alert-danger alert-dismissible fade show" role="alert">
                        {% for field in form %}
                            {% for error in field.errors %}
                                <div>{{ error }}</div>
                            {% endfor %}
                        {% endfor %}
                        {% for error in form.non_field_errors %}
                            <div>{{ error }}</div>
                        {% endfor %}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                    {% endif %}

                    {% if messages %}
                    {% for msg in messages %}
                    <div class="alert alert-warning alert-dismissible fade show" role="alert">
                        {{ msg }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                    {% endfor %}
                    {% endif %}

                    <form method="post" class="mb-4">
                        {% csrf_token %}

                        <div class="mb-3">
                            <label for="{{ form.username.id_for_label }}" class="form-label fw-bold small">Username</label>
                            {{ form.username }}
                            {% if form.username.errors %}
                                <div class="text-danger small mt-1">{{ form.username.errors.0 }}</div>
                            {% endif %}
                        </div>

                        <div class="mb-3">
                            <label for="{{ form.email.id_for_label }}" class="form-label fw-bold small">Email Address</label>
                            {{ form.email }}
                            {% if form.email.errors %}
                                <div class="text-danger small mt-1">{{ form.email.errors.0 }}</div>
                            {% endif %}
                        </div>

                        <div class="mb-3">
                            <label for="{{ form.password1.id_for_label }}" class="form-label fw-bold small">Password</label>
                            {{ form.password1 }}
                            {% if form.password1.errors %}
                                <div class="text-danger small mt-1">{{ form.password1.errors.0 }}</div>
                            {% endif %}
                        </div>

                        <div class="mb-4">
                            <label for="{{ form.password2.id_for_label }}" class="form-label fw-bold small">Confirm Password</label>
                            {{ form.password2 }}
                            {% if form.password2.errors %}
                                <div class="text-danger small mt-1">{{ form.password2.errors.0 }}</div>
                            {% endif %}
                        </div>

                        <button type="submit" class="btn btn-primary w-100 py-2 fw-bold">
                            Create Account
                        </button>
                    </form>

                    <div class="text-center pt-3 border-top">
                        <p class="text-muted small mb-0">
                            Already have an account? <a href="{% url 'login' %}" class="text-decoration-none fw-semibold" style="color:#ff9933;">Sign in</a>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    body { background: linear-gradient(135deg, #fff7ed 0%, #f8fafc 60%, #fff7ed 100%); }
    .login-card { border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 20px 50px rgb(0 0 0 / 0.08); }
    .login-logo-wrap { width: 64px; height: 64px; background: #ff9933; border-radius: 16px; display: flex; align-items: center; justify-content: center; font-size: 1.75rem; margin: 0 auto 1rem; box-shadow: 0 8px 20px rgba(255,153,51,0.3); }
    .form-control { border-radius: 8px; border: 1.5px solid #e2e8f0; font-size: 0.9rem; padding: 0.6rem 0.875rem; }
    .form-control:focus { border-color: #ff9933; box-shadow: 0 0 0 3px rgba(255,153,51,0.18); }
    .btn-primary { background: #ff9933; border: none; font-weight: 700; box-shadow: 0 4px 14px rgba(255,153,51,0.35); transition: all 0.2s; }
    .btn-primary:hover { background: #e07e1e; transform: translateY(-1px); }
</style>
{% endblock %}
```

- [ ] **Step 2: Create `templates/registration/verify_email.html`**

```html
{% extends 'base.html' %}

{% block content %}
<div class="container py-5">
    <div class="row justify-content-center min-vh-100 align-items-center">
        <div class="col-md-5">
            <div class="card border-0" style="border-radius:16px;border:1px solid #e2e8f0;box-shadow:0 20px 50px rgb(0 0 0 / 0.08);">
                <div class="card-body p-5">
                    <div class="text-center mb-4">
                        <div style="width:64px;height:64px;background:#ff9933;border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:1.75rem;margin:0 auto 1rem;box-shadow:0 8px 20px rgba(255,153,51,0.3);">✉</div>
                        <h2 class="fw-bold mb-1" style="letter-spacing:-0.02em;">Check your inbox</h2>
                        <p class="text-muted mb-0" style="font-size:0.875rem;">We sent a 6-digit code to <strong>{{ masked_email }}</strong></p>
                    </div>

                    {% if error %}
                    <div class="alert alert-danger alert-dismissible fade show" role="alert">
                        {{ error }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                    {% endif %}

                    <form method="post" class="mb-3">
                        {% csrf_token %}
                        <div class="mb-3">
                            <label class="form-label fw-bold small">Verification Code</label>
                            <input type="text" name="otp" maxlength="6" inputmode="numeric"
                                   autocomplete="one-time-code"
                                   class="form-control text-center fw-bold"
                                   style="font-size:1.5rem;letter-spacing:0.4em;border-radius:8px;border:1.5px solid #e2e8f0;"
                                   placeholder="_ _ _ _ _ _" autofocus>
                        </div>
                        <button type="submit" class="btn w-100 py-2 fw-bold"
                                style="background:#ff9933;color:#fff;border:none;border-radius:8px;">
                            Verify
                        </button>
                    </form>

                    <div class="text-center mb-3">
                        <form method="post" action="{% url 'resend_otp' %}" style="display:inline;">
                            {% csrf_token %}
                            <button type="submit" class="btn btn-link text-muted small p-0"
                                    style="font-size:0.85rem;">
                                Didn't get it? Resend code
                            </button>
                        </form>
                    </div>

                    <div class="text-center pt-3 border-top">
                        <a href="{% url 'product_list' %}" class="text-muted small text-decoration-none">
                            Skip — I'll verify later
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    body { background: linear-gradient(135deg, #fff7ed 0%, #f8fafc 60%, #fff7ed 100%); }
    .form-control:focus { border-color: #ff9933 !important; box-shadow: 0 0 0 3px rgba(255,153,51,0.18) !important; }
</style>
{% endblock %}
```

- [ ] **Step 3: Create `templates/registration/verify_required.html`**

```html
{% extends 'base.html' %}

{% block content %}
<div class="container py-5">
    <div class="row justify-content-center min-vh-100 align-items-center">
        <div class="col-md-5">
            <div class="card border-0" style="border-radius:16px;border:1px solid #e2e8f0;box-shadow:0 20px 50px rgb(0 0 0 / 0.08);">
                <div class="card-body p-5">
                    <div class="text-center mb-4">
                        <div style="width:64px;height:64px;background:oklch(14% 0.045 52);border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:1.75rem;margin:0 auto 1rem;">
                            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#ff9933" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                        </div>
                        <h2 class="fw-bold mb-1" style="letter-spacing:-0.02em;">Verify to place orders</h2>
                        <p class="text-muted mb-0" style="font-size:0.875rem;">Enter the code sent to <strong>{{ masked_email }}</strong> to complete your order</p>
                    </div>

                    {% if messages %}
                    {% for msg in messages %}
                    <div class="alert alert-success alert-dismissible fade show">
                        {{ msg }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                    {% endfor %}
                    {% endif %}

                    {% if error %}
                    <div class="alert alert-danger alert-dismissible fade show">
                        {{ error }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                    {% endif %}

                    <form method="post" class="mb-3">
                        {% csrf_token %}
                        <div class="mb-3">
                            <label class="form-label fw-bold small">Verification Code</label>
                            <input type="text" name="otp" maxlength="6" inputmode="numeric"
                                   autocomplete="one-time-code"
                                   class="form-control text-center fw-bold"
                                   style="font-size:1.5rem;letter-spacing:0.4em;border-radius:8px;border:1.5px solid #e2e8f0;"
                                   placeholder="_ _ _ _ _ _" autofocus>
                        </div>
                        <button type="submit" class="btn w-100 py-2 fw-bold"
                                style="background:#ff9933;color:#fff;border:none;border-radius:8px;">
                            Verify and continue
                        </button>
                    </form>

                    <div class="text-center">
                        <form method="post" action="{% url 'resend_otp' %}" style="display:inline;">
                            {% csrf_token %}
                            <button type="submit" class="btn btn-link text-muted small p-0"
                                    style="font-size:0.85rem;">
                                Resend code
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    body { background: linear-gradient(135deg, #fff7ed 0%, #f8fafc 60%, #fff7ed 100%); }
    .form-control:focus { border-color: #ff9933 !important; box-shadow: 0 0 0 3px rgba(255,153,51,0.18) !important; }
</style>
{% endblock %}
```

- [ ] **Step 4: Update `templates/registration/login.html` — replace "Contact staff" section**

Find this block (lines 97–103):

```html
                    <!-- Register Link -->
                    <div class="text-center mt-4 pt-3 border-top">
                        <p class="text-muted small mb-0">
                            Don't have an account? <br>
                            Contact staff to register
                        </p>
                    </div>
```

Replace with:

```html
                    <!-- Register Link -->
                    <div class="text-center mt-4 pt-3 border-top">
                        <p class="text-muted small mb-0">
                            New customer?
                            <a href="{% url 'register' %}" class="fw-semibold text-decoration-none" style="color:#ff9933;">
                                Create a free account
                            </a>
                        </p>
                    </div>
```

- [ ] **Step 5: Manual smoke test**

Start the dev server:

```
venv\Scripts\python.exe manage.py runserver
```

1. Go to `http://localhost:8000/login/` — confirm "Create a free account" link appears
2. Click the link — confirm the signup form loads at `/register/`
3. Register with a new username/email/password — confirm redirect to `/register/verify/`
4. Confirm the OTP form shows the masked email
5. Click "Skip" — confirm redirect to `/menu/`
6. Add a product to cart and go to checkout — click submit order — confirm redirect to `/verify-required/`

- [ ] **Step 6: Commit**

```
git add templates/registration/register.html templates/registration/verify_email.html templates/registration/verify_required.html templates/registration/login.html
git commit -m "feat: add registration, OTP verification, and checkout gate templates"
```

---

## Task 7: Verification Email Template

**Files:**
- Create: `templates/emails/email_verification.html`

- [ ] **Step 1: Create `templates/emails/email_verification.html`**

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; color: #333; margin: 0; padding: 0; }
        .container { max-width: 600px; margin: 0 auto; }
        .header { background-color: #ff9933; color: #fff; padding: 24px 20px; text-align: center; }
        .header h2 { margin: 0; font-size: 1.25rem; font-weight: 700; letter-spacing: -0.01em; }
        .content { padding: 32px 24px; border: 1px solid #e2e8f0; border-top: none; }
        .otp-box { background: #fff7ed; border: 2px solid #ff9933; border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0; }
        .otp-code { font-size: 2.5rem; font-weight: 900; letter-spacing: 0.3em; color: #c96d10; font-family: monospace; }
        .otp-label { font-size: 0.8rem; color: #64748b; margin-top: 6px; }
        .warning { background: #f8fafc; border-left: 3px solid #ff9933; padding: 12px 16px; border-radius: 4px; font-size: 0.875rem; color: #475569; margin-top: 16px; }
        .footer { text-align: center; color: #94a3b8; font-size: 0.75rem; margin-top: 24px; padding: 16px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Zarly BigFood — Verify Your Account</h2>
        </div>
        <div class="content">
            <p>Hi <strong>{{ username }}</strong>,</p>
            <p>Use the code below to verify your email address. It expires in <strong>5 minutes</strong>.</p>

            <div class="otp-box">
                <div class="otp-code">{{ otp }}</div>
                <div class="otp-label">Your verification code</div>
            </div>

            <div class="warning">
                Do not share this code with anyone. Zarly staff will never ask for your code.
            </div>

            <p style="margin-top:20px;">If you did not create a Zarly BigFood account, you can safely ignore this email.</p>
        </div>
        <div class="footer">
            <p>© 2025 Zarly BigFood. All rights reserved.</p>
            <p>This is an automated message. Please do not reply.</p>
        </div>
    </div>
</body>
</html>
```

- [ ] **Step 2: Run the full test suite one final time**

```
venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

Expected: all tests PASSED, no regressions

- [ ] **Step 3: Commit**

```
git add templates/emails/email_verification.html
git commit -m "feat: add OTP verification email template"
```

---

## Checklist Against Spec

| Spec requirement | Task |
|---|---|
| Username + email + password signup form | Task 3 |
| `email_verified = False` on new accounts | Task 2 |
| Existing accounts backfilled to `True` | Task 2 |
| Auto-login after registration | Task 3 |
| OTP generated with `secrets.randbelow` | Task 1 |
| OTP stored in cache with 5-min TTL | Task 1 |
| Verify-now option (OTP entry on verify page) | Task 4 |
| Verify-later option (skip link to menu) | Task 6 |
| Resend OTP (overwrites old code) | Task 4 |
| Checkout gate on `submit_order` | Task 5 |
| `post_verify_redirect` session key for checkout return | Tasks 4 + 5 |
| Rate limit: register 10/h IP | Task 3 |
| Rate limit: verify 10/5min user | Task 4 |
| Rate limit: resend 1/min user | Task 4 |
| Audit log: registration_success | Task 3 |
| Audit log: email_verified | Task 4 |
| Audit log: verify_failed | Task 4 |
| Audit log: verify_resend | Task 4 |
| "Create account" link on login page | Task 6 |
| OTP email template | Task 7 |
