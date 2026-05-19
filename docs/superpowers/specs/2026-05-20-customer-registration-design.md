# Customer Registration + Email Verification — Design Spec

**Date:** 2026-05-20
**Status:** Approved

---

## Overview

New customers need an account to place orders. The registration flow must minimise
friction while creating a verifiable identity chain for non-repudiation — proving that
the person who placed an order owns the email address attached to that account.

---

## User Flow

```
/register
  → form: username + email + password
  → account created, auto-logged in
  → redirect to /register/verify/

/register/verify/
  ┌─────────────────────────────────────────┐
  │  "We sent a 6-digit code to you@..."    │
  │                                         │
  │  [  _ _ _ _ _ _  ]   [Verify]           │
  │                                         │
  │  Didn't get it? [Resend]  ·  [Skip — I'll do this later] │
  └─────────────────────────────────────────┘

Path A — verify now:
  enter 6-digit OTP (5 min window)
  → verified ✓ → redirect to /menu/

Path B — verify later:
  click skip
  → redirect to /menu/
  → wall appears at first checkout attempt
  → /verify-required/ shows resend + OTP entry
  → verified ✓ → back to checkout
```

Unverified customers can browse the menu and manage their cart freely. The only
blocked action is placing an order.

---

## Non-Repudiation Chain

1. Customer registers with email X
2. OTP sent to email X — only the inbox owner can receive it
3. Customer enters OTP → `email_verified = True` recorded with timestamp in audit log
4. Customer logs in → audit log records session
5. Customer places order → order linked to verified account
6. Order receipt is digitally signed (existing `DigitalSignature` model)

If a customer later disputes an order, the chain — verified email ownership →
authenticated session → signed receipt — establishes they authorised the transaction.

---

## Data Model

**`customers/models.py` — `User`**

Add one field:

```python
email_verified = models.BooleanField(default=False)
```

Two migrations required:

1. **Schema migration** `customers/migrations/0013_user_email_verified.py` — adds the field with `default=False`.
2. **Data migration** `customers/migrations/0014_backfill_email_verified.py` — sets `email_verified=True` for every account that existed before this feature ships. This ensures existing customers are never blocked at checkout. Only accounts created after deployment start with `False` and must verify.

No separate OTP model. Codes are stored in the Django cache layer only (see Security
section).

---

## Views

All new views live in `customers/views.py`.

### `register_customer` — `GET/POST /register/`

- Renders a form with: `username`, `email`, `password1`, `password2`
- Built on Django's `UserCreationForm` with email added
- Validations: username unique, email unique, passwords match, password strength
  (AUTH_PASSWORD_VALIDATORS)
- Rate-limited: 10 attempts / hour by IP
- On success:
  1. Create `User` with `email_verified=False`, `role='customer'`
  2. Auto-login
  3. Generate OTP and send verification email
  4. Audit log: `registration_success`
  5. Redirect to `/register/verify/`

### `verify_email_page` — `GET /register/verify/`

- Renders the OTP entry page
- Shows masked email address (`y**@g****.com`)
- If already verified, redirect to `/menu/`

### `verify_email_submit` — `POST /register/verify/`

- Reads submitted 6-digit code
- Looks up `cache.get(f'email_otp_{user.pk}')`
- If match: set `email_verified=True`, delete cache key, audit log
  `email_verified`, redirect to `/menu/`
- If no match or expired: show error ("Incorrect or expired code"), offer resend
- Rate-limited: 10 attempts / 5 minutes by user (brute-force protection)

### `resend_verification_otp` — `POST /register/resend/`

- Generates fresh OTP, overwrites cache key (old code invalidated automatically)
- Sends email again
- Rate-limited: 1 resend / minute by user
- Returns JSON `{ok: true}` or `{error: "..."}` for AJAX inline feedback

### `verification_required` — `GET /verify-required/`

- Shown when an unverified customer tries to check out
- Same OTP entry form + resend button
- On success: redirect to checkout

---

## Checkout Gate

In `customers/views.py → checkout` (POST handler), at the top:

```python
if not request.user.email_verified:
    request.session['post_verify_redirect'] = 'checkout'
    return redirect('verification_required')
```

After successful verification, the `verify_email_submit` view checks
`request.session.get('post_verify_redirect')` and redirects accordingly.

---

## OTP Generation and Storage

```python
import secrets
from django.core.cache import cache

def generate_and_cache_otp(user):
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(f'email_otp_{user.pk}', code, 300)  # 5 minutes
    return code

def verify_otp(user, submitted_code):
    stored = cache.get(f'email_otp_{user.pk}')
    if stored is None:
        return 'expired'
    if stored != submitted_code:
        return 'invalid'
    cache.delete(f'email_otp_{user.pk}')
    return 'ok'
```

`secrets.randbelow` is cryptographically random (unlike `random`).
The code is single-use: cache entry deleted immediately on correct submission.
Resend overwrites the cache key, invalidating any previous code.

---

## Email Template

New file: `templates/emails/email_verification.html`

Follows the existing transactional email style (same as `payment_proof_rejected.html`).
Content:
- Subject: `Verify your ZarlyHQ account`
- Body: greeting, 6-digit code in large text, "This code expires in 5 minutes", do-not-share warning

---

## URLs

```python
# zarlyOs/urls.py
path('register/',                  register_customer,         name='register'),
path('register/verify/',           verify_email_page,         name='verify_email'),
path('register/verify/submit/',    verify_email_submit,       name='verify_email_submit'),
path('register/resend/',           resend_verification_otp,   name='resend_otp'),
path('verify-required/',           verification_required,     name='verification_required'),
```

A "Sign up" link is added to the login page (`templates/registration/login.html`).

---

## Templates

| Template | Purpose |
|---|---|
| `templates/registration/register.html` | Signup form |
| `templates/registration/verify_email.html` | OTP entry + skip option |
| `templates/registration/verify_required.html` | Checkout gate page |
| `templates/emails/email_verification.html` | Transactional email |

All customer-facing templates follow the existing customer UI design system.

---

## Rate Limits Summary

| Endpoint | Limit | Key |
|---|---|---|
| `register_customer` | 10 / hour | IP |
| `verify_email_submit` | 10 / 5 min | User |
| `resend_verification_otp` | 1 / min | User |

---

## Audit Events

| Event | When |
|---|---|
| `registration_success` | New account created |
| `email_verified` | OTP accepted, `email_verified` set to True |
| `verify_resend` | Resend requested |
| `verify_failed` | Wrong OTP submitted |

---

## Out of Scope

- Social/OAuth login (Google, Facebook)
- Phone number at signup (collected at checkout if needed)
- Admin-side verification management
- Retroactive verification requirement for existing accounts
