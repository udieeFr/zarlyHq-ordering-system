# Customer Module — Security Review

**Scope:** `customers/views.py`, `customers/models.py`, `customers/urls.py`,
`customers/auth_utils.py`, `customers/payment_utils.py`, `customers/stripe_utils.py`,
`templates/customers/**`

**Date:** 2026-05-17

---

## Part 1 — Implemented Security Features

### Authentication & Authorization
- `@login_required` on all sensitive views (cart, checkout, orders, profile, payments, complaints, notifications)
- Role-based access decorators in `auth_utils.py`: `role_required`, `customer_required`, `sales_admin_required`, `manager_required`
- Object-level ownership enforcement via `get_object_or_404(Order, id=order_id, customer=request.user)` — prevents IDOR attacks across all order/payment views

### CSRF Protection
- `{% csrf_token %}` in every POST form across all customer templates
- `@csrf_exempt` applied only to the Stripe webhook, correctly replaced by Stripe HMAC signature verification

### Rate Limiting
Applied via `django-ratelimit`:
| View | Limit |
|---|---|
| `add_to_cart` | 60/min per user |
| `submit_order` | 10/min per user |
| `upload_payment_proof` | 10/hr per user |
| `submit_complaint` | 5/hr per user |
| `cancel_order` | 5/min per user |
| `reorder` | 20/min per user |

### File Upload Validation (`payment_utils.validate_payment_proof`)
- Size cap: 5 MB
- Extension allowlist: `jpg`, `jpeg`, `png`, `gif`, `webp`, `pdf`
- Image integrity check via `PIL.Image.verify()` for non-PDF uploads

### Stripe Webhook Security
- Signature verified with `stripe.Webhook.construct_event()` (HMAC-SHA256)
- Idempotency guard: skips double-processing if `payment.status == 'succeeded'`
- Replay attack block: rejects manual payment proof upload if Stripe has already confirmed

### SQL Injection Prevention
- Django ORM used exclusively in all customer views — no raw SQL queries

### XSS Prevention
- Django auto-escaping active in all templates
- `|escapejs` filter applied to data embedded in `<script>` blocks (checkout.html `SAVED` object)

### Audit Logging
`log_audit()` called on: order creation, payment proof upload, complaint submission, order cancellation, receipt verification, logout

### Receipt Integrity / Non-repudiation
- SHA-256 of signed PDF stored at signing time; recomputed on every `verify_receipt` request
- PyHanko PKCS#7 digital signature validated inline

### Session Hygiene
- Ghost product cleanup on cart read (removes DB-deleted products from session)
- `request.session.modified = True` set explicitly after every cart mutation

---

## Part 2 — Missing / Needed Security Features

Severity: **Critical** > **High** > **Medium** > **Low**
Complexity: **High** = significant refactor | **Medium** = moderate work | **Low** = quick fix

---

### CRITICAL

#### C1 — Stock Race Condition (Overselling)
**Complexity: High**

`submit_order` reads product stock, subtracts quantities, and saves — all without a DB-level lock. Two concurrent requests for the same product can both pass the stock check and both decrement, resulting in `stock < 0`.

**File:** `customers/views.py:488–496`

**Fix:** Wrap the stock decrement in `select_for_update()` inside an atomic transaction:
```python
from django.db import transaction

with transaction.atomic():
    for item in cart_items:
        product = Product.objects.select_for_update().get(id=item['product'].id)
        if product.stock < item['quantity']:
            raise ValueError(f"{product.name} is out of stock.")
        product.stock -= item['quantity']
        product.save(update_fields=['stock'])
```

---

### HIGH

#### H1 — No Content Security Policy (CSP) Headers
**Complexity: High**

No CSP headers are set anywhere. XSS protection relies entirely on Django template escaping. An XSS in a future template or third-party JS would have unrestricted access.

**Fix:** Add `django-csp` middleware and configure a strict policy. Start with `Content-Security-Policy: default-src 'self'; script-src 'self' unpkg.com; ...`

---

#### H2 — Missing HTTP Security Headers
**Complexity: Low**

The following headers are not set:
- `X-Frame-Options` (clickjacking)
- `X-Content-Type-Options: nosniff` (MIME sniffing)
- `Referrer-Policy`
- `Permissions-Policy`

**Fix:** Add to `settings.py`:
```python
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
```
And add `SecurityMiddleware` to `MIDDLEWARE` (it's likely already there — verify it is first in the list).

---

#### H3 — Open Redirect via Notification Link
**Complexity: Low**

`notification_open` redirects to `notif.link` which is stored in the DB. If a notification is created with a fully qualified external URL (e.g., `http://evil.com`), it will redirect the user off-site without warning.

**File:** `customers/views.py:1131`

**Fix:** Validate `notif.link` is a relative path before redirecting:
```python
from django.utils.http import url_has_allowed_host_and_scheme
if notif.link and url_has_allowed_host_and_scheme(notif.link, allowed_hosts={request.get_host()}):
    return redirect(notif.link)
return redirect('notifications_list')
```

---

#### H4 — No Email Verification on Email Change
**Complexity: Medium**

Both `update_profile` (API) and `customer_profile` (form) allow changing the account email without sending a verification link. An attacker with brief access to a session could silently reroute account recovery emails.

**Fix:** On email change, send a verification link to the *new* address and only apply the change after the link is clicked. Store the pending email separately until confirmed.

---

#### H5 — File Upload: MIME Type Not Validated (Magic Bytes)
**Complexity: Medium**

`validate_payment_proof` checks file extension only. A file with a renamed extension (e.g., an SVG or PHP file named `receipt.jpg`) passes the check. `PIL.Image.verify()` catches corrupt images but not disguised non-image content for all formats.

**File:** `customers/payment_utils.py:199–211`

**Fix:** Read the first bytes and verify against known magic numbers, or use `python-magic`:
```python
import magic
mime = magic.from_buffer(file_obj.read(2048), mime=True)
file_obj.seek(0)
allowed_mimes = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf'}
if mime not in allowed_mimes:
    return False, "File type not permitted."
```

---

### MEDIUM

#### M1 — No Rate Limiting on Password Change
**Complexity: Low**

`customer_profile` handles password changes but has no rate limit. An attacker with a valid session could attempt to brute-force the current password field without lockout.

**Fix:** Add `@ratelimit(key='user', rate='10/h', method='POST', block=True)` to `customer_profile`.

---

#### M2 — Unbounded Quantity in Cart
**Complexity: Low**

`add_to_cart` and `update_cart` cast `quantity` to `int` but do not cap the value. A user could set `quantity=999999`, causing incorrect totals and stock deduction.

**Files:** `customers/views.py:335`, `customers/views.py:379`

**Fix:**
```python
quantity = max(1, min(int(request.POST.get('quantity', 1)), 99))
```

---

#### M3 — Error Detail Disclosure to Users
**Complexity: Low**

Exception messages are passed directly into `messages.error()` in several places, potentially exposing stack traces, DB schema info, or file paths to end users.

**Files:** `customers/views.py:183`, `customers/views.py:268`

```python
# Current — exposes internal error
messages.error(request, f"Error generating invoice: {str(e)}")

# Fix — generic user message, log the detail
logger.error(f"Invoice generation error for order {order_id}: {e}")
messages.error(request, "Something went wrong. Please try again or contact support.")
```

---

#### M4 — `verify_receipt` Exposes Customer Data Publicly
**Complexity: Low**

`verify_receipt` has no `@login_required`. It passes `sig_record` (which has a `order.customer` FK) to the template. If the template ever renders customer name or email, that's an unauthenticated data leak.

**File:** `customers/views.py:1021`, `templates/customers/verify_receipt.html`

**Fix:** Either add `@login_required` or audit the template to ensure it renders *only* verification status (valid/invalid/tampered) and nothing customer-identifying.

---

#### M5 — Payment Config Hardcoded in Source
**Complexity: Low**

DuitNow merchant ID and bank account numbers are hardcoded in `PAYMENT_CONFIG` inside `payment_utils.py`. These should be treated as sensitive operational config.

**File:** `customers/payment_utils.py:14–28`

**Fix:** Move to `settings.py` (loaded from environment variables):
```python
DUITNOW_MERCHANT_ID = os.environ.get('DUITNOW_MERCHANT_ID', '')
BANK_ACCOUNT_NUMBER = os.environ.get('BANK_ACCOUNT_NUMBER', '')
```

---

#### M6 — Unbounded Text Fields on Order Submission
**Complexity: Low**

`full_name`, `phone_number`, `street_address`, `city`, `state`, `postcode`, `order_notes`, `cancel_reason` are accepted from POST with only `.strip()`. No max-length enforcement server-side (only DB-level truncation).

**File:** `customers/views.py:463–484`, `customers/views.py:1171`

**Fix:** Truncate or reject fields exceeding a reasonable length:
```python
street_address = request.POST.get('street_address', '').strip()[:255]
order_notes = request.POST.get('order_notes', '').strip()[:500]
```

---

#### M7 — Geolocation Coordinates Not Bounds-Checked
**Complexity: Low**

Latitude and longitude from POST are parsed with a try/except but not validated against valid geographic ranges (lat: −90 to 90, lng: −180 to 180).

**File:** `customers/views.py:454–461`

**Fix:**
```python
if latitude is not None and not (-90 <= latitude <= 90):
    latitude = None
if longitude is not None and not (-180 <= longitude <= 180):
    longitude = None
```

---

### LOW

#### L1 — Duplicate `@login_required` on `update_profile`
**Complexity: Low**

`update_profile` has `@login_required` applied twice (lines 1206–1207). No security impact, but indicates a copy-paste error.

**Fix:** Remove the duplicate decorator.

---

#### L2 — No Rate Limiting on Notification Endpoints
**Complexity: Low**

`notifications_mark_all_read` and `notification_open` have no rate limits. A script could spam-mark thousands of notifications or trigger many redirects.

**Fix:** Add `@ratelimit(key='user', rate='60/m', method='GET')` to both views.

---

#### L3 — `logout_view` Doesn't Use `@login_required`
**Complexity: Low**

`logout_view` handles the unauthenticated case manually rather than using `@login_required`. This is not a vulnerability, but inconsistent with the rest of the codebase and could become one if the manual check is ever removed.

**Fix:** Add `@login_required` and remove the `if request.user.is_authenticated` guard.

---

## Summary Table

| ID | Title | Severity | Complexity |
|---|---|---|---|
| C1 | Stock race condition (overselling) | Critical | High |
| H1 | No Content Security Policy | High | High |
| H2 | Missing HTTP security headers | High | Low |
| H3 | Open redirect via notification link | High | Low |
| H4 | No email verification on email change | High | Medium |
| H5 | File upload: MIME not validated (magic bytes) | High | Medium |
| M1 | No rate limit on password change | Medium | Low |
| M2 | Unbounded cart quantity | Medium | Low |
| M3 | Error detail disclosure to users | Medium | Low |
| M4 | `verify_receipt` exposes customer data publicly | Medium | Low |
| M5 | Payment config hardcoded in source | Medium | Low |
| M6 | Unbounded text fields on order submission | Medium | Low |
| M7 | Geolocation coordinates not bounds-checked | Medium | Low |
| L1 | Duplicate `@login_required` on `update_profile` | Low | Low |
| L2 | No rate limit on notification endpoints | Low | Low |
| L3 | `logout_view` inconsistency | Low | Low |
