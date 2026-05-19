# Customer Module — Security Review

**Scope:** `customers/views.py`, `customers/models.py`, `customers/urls.py`,
`customers/auth_utils.py`, `customers/payment_utils.py`, `customers/stripe_utils.py`,
`templates/customers/**`

**Original date:** 2026-05-17
**Last updated:** 2026-05-19 — added NEW-5/6/7 (mid-payment connection-loss gaps); M6+M7 marked fixed

---

## Part 1 — Implemented Security Features

### Authentication & Authorization
- `@customer_required` on all sensitive views (cart, checkout, orders, profile, payments, complaints, notifications, ratings/reviews)
- Role-based access decorators in `auth_utils.py`: `role_required`, `customer_required`, `sales_admin_required`, `manager_required`
- Object-level ownership enforcement via `get_object_or_404(Order, id=order_id, customer=request.user)` — prevents IDOR attacks across all order/payment/rating views

### CSRF Protection
- `{% csrf_token %}` in every POST form across all customer templates
- `@csrf_exempt` applied only to the Stripe webhook, correctly replaced by Stripe HMAC signature verification

### Rate Limiting
Applied via `django-ratelimit`:
| View | Limit | Key |
|---|---|---|
| `add_to_cart` | 60/min | user |
| `submit_order` | 10/min | user |
| `upload_payment_proof` | 10/hr | user |
| `submit_complaint` | 5/hr | user |
| `cancel_order` | 5/min | user |
| `reorder` | 20/min | user |
| `rate_order` | 20/hr | user |
| `submit_product_review` | 30/hr | user |
| `customer_profile` | 10/hr | user |
| `toggle_favourite` | 60/min | user |
| `download_invoice` | 20/hr | user |
| `start_stripe_payment` | 5/min | user |
| `update_cart` | 60/min | user |
| `remove_from_cart` | 60/min | user |
| `verify_receipt` | 20/min | IP |
| `update_profile` | 10/hr | user |
| `customer_complaint_messages` (POST) | 30/min | user |

### File Upload Validation (`payment_utils.validate_payment_proof`)
- Size cap: 5 MB
- Extension allowlist: `jpg`, `jpeg`, `png`, `pdf` (gif/webp removed)
- Magic-byte verification for all types (JPEG: `\xFF\xD8\xFF`, PNG: `\x89PNG\r\n\x1a\n`, PDF: `%PDF`)
- `PIL.Image.verify()` for JPEG/PNG integrity

### Deterministic Payment Proof Naming
- Upload path: `payment_proofs/YYYYMMDD-ORDER{id}.{ext}`
- Original filename discarded — no path traversal via filename
- Old proof deleted from storage before replacement saved

### Stripe Webhook Security
- Signature verified with `stripe.Webhook.construct_event()` (HMAC-SHA256)
- Idempotency guard: skips double-processing if `payment.status == 'succeeded'`
- Replay attack block: rejects manual payment proof upload if Stripe has already confirmed

### SQL Injection Prevention
- Django ORM used exclusively — no raw SQL queries

### XSS Prevention
- Django auto-escaping active in all templates
- `|escapejs` filter applied to data embedded in `<script>` blocks (checkout.html `SAVED` object)
- Support chat uses safe DOM construction (`textContent`, `createElement`) — no `innerHTML` on user data

### Audit Logging
`log_audit()` called on: order creation, payment proof upload, complaint submission, order cancellation, receipt verification, logout, support message sent, Stripe checkout session started

### Receipt Integrity / Non-repudiation
- SHA-256 of signed PDF stored at signing time; recomputed on every `verify_receipt` request
- PyHanko PKCS#7 digital signature validated inline

### Session Hygiene
- Ghost product cleanup on cart read (removes DB-deleted products from session)
- `request.session.modified = True` set explicitly after every cart mutation
- Pre-login anonymous cart merged into authenticated session on login

### Password Validation
- `AUTH_PASSWORD_VALIDATORS` enabled (similarity, minimum length, common passwords, numeric-only)
- `validate_password()` called in `customer_profile` change_password handler

### SupportMessage Immutability
- `delete()` overridden on model and queryset — records cannot be deleted via ORM
- FK `on_delete` changed from `CASCADE` to `PROTECT` — deleting a complaint with messages is blocked at DB level

### Ratings & Reviews Authorization
- `rate_order` enforces `customer=request.user` ownership + `status='delivered'` check
- `submit_product_review` verifies a delivered order containing the product exists for the user
- `unique_together = ('product', 'customer', 'order')` DB-level duplicate review prevention

---

## Part 2 — Security Issues

Severity: **Critical** > **High** > **Medium** > **Low**
Complexity: **High** = significant refactor | **Medium** = moderate work | **Low** = quick fix
Status: ✅ Fixed | 🔴 Open — ship blocker | 🟡 Open — fix before production | ⬜ Open — low priority

---

### CRITICAL

#### C1 — Stock Race Condition (Overselling) ✅ Fixed
**Complexity: High** | **Fixed: 2026-05-17**

`submit_order` now wraps stock decrement in `select_for_update()` inside an `atomic()` transaction.

---

### HIGH

#### H1 — No Content Security Policy (CSP) Headers ✅ Fixed
**Complexity: High** | **Fixed: 2026-05-17**

`django-csp` middleware with per-request nonce. `Content-Security-Policy` header sent on all responses.

---

#### H2 — Missing HTTP Security Headers ✅ Fixed
**Complexity: Low** | **Fixed: 2026-05-17**

`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` active.

---

#### H3 — Open Redirect via Notification Link ✅ Fixed
**Complexity: Low** | **Fixed: 2026-05-17**

`notification_open` validates `notif.link` with `url_has_allowed_host_and_scheme`.

---

#### H4 — No Email Verification on Email Change 🟡 Open
**Complexity: Medium**

Both `update_profile` (API) and `customer_profile` (form) allow changing the account email without sending a verification link. An attacker with brief session access could silently reroute account recovery emails.

**Fix:** Add `pending_email` and `pending_email_token` fields to the User model. On email change, send a verification link to the new address and apply the change only after the link is clicked. Use `secrets.token_urlsafe(32)` for the token; expire it after 24 hours.

```python
# On email change submission:
token = secrets.token_urlsafe(32)
user.pending_email = new_email
user.pending_email_token = token
user.pending_email_token_expires = timezone.now() + timedelta(hours=24)
user.save(update_fields=['pending_email', 'pending_email_token', 'pending_email_token_expires'])
send_verification_email(user, new_email, token)
messages.info(request, 'Check your new email address for a verification link.')

# Verification view /verify-email/<token>/:
user = get_object_or_404(User, pending_email_token=token, pending_email_token_expires__gt=timezone.now())
user.email = user.pending_email
user.pending_email = ''
user.pending_email_token = ''
user.save(update_fields=['email', 'pending_email', 'pending_email_token'])
```

---

#### H5 — File Upload: MIME Type Not Validated (Magic Bytes) ✅ Fixed
**Fixed: 2026-05-18**

Magic-byte check added for all types including PDF (`%PDF`). Extension allowlist tightened to jpg/jpeg/png/pdf.

---

#### NEW-1 — Stored XSS in Support Chat Bubbles ✅ Fixed
**Fixed: 2026-05-18**

`innerHTML` replaced with safe `textContent` DOM construction in all chat templates (customer and admin sides).

---

#### NEW-2 — Missing `@customer_required` — Staff Can Act as Customers ✅ Fixed
**Fixed: 2026-05-18**

All customer views now use `@customer_required`. Decorator enforces `role == 'customer'` check.

---

### MEDIUM

#### M1 — No Rate Limiting on Password Change ⬜ Open
**Complexity: Low**

`customer_profile` handles password changes but has no POST rate limit. An attacker with a valid session could brute-force the current password field without lockout.

**Fix:**
```python
@customer_required
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def customer_profile(request):
    ...
```

---

#### M2 — Unbounded / Unguarded Quantity in Cart ✅ Fixed
**Fixed: 2026-05-18**

`add_to_cart` and `update_cart` now wrap `int(quantity)` in try/except with bounds cap (1–99).

---

#### M3 — Error Detail Disclosure to Users ✅ Fixed
**Complexity: Low** | **Fixed: 2026-05-20**

Exception messages passed directly into `messages.error()` in several places (invoice generation, document signing at `admins/views.py:1480`).

**Fix:**
```python
# Current — exposes internal error
messages.error(request, f"Error signing document: {str(e)}")

# Fix — log internally, show generic message
logger.error("Document signing failed for order %s: %s", order.id, e)
messages.error(request, "Something went wrong. Please try again or contact support.")
```

---

#### M4 — `verify_receipt` Exposes Customer Data Publicly ✅ Fixed
**Complexity: Low** | **Fixed: 2026-05-20**

`verify_receipt` has no `@login_required`. Integer order IDs are sequentially guessable, enabling unauthenticated enumeration. If the template renders customer name/email, it is an unauthenticated data leak.

**Fix options (pick one):**
1. Audit template — render only verification status (valid/invalid/tampered), no PII
2. Add `@login_required` so only authenticated users can verify
3. Replace bare `order_id` in URL with HMAC token embedded in the signed PDF:
```python
import hmac, hashlib
token = hmac.new(settings.SECRET_KEY.encode(), f'receipt:{order_id}'.encode(), hashlib.sha256).hexdigest()
# URL: /verify/<token>/
```

---

#### M5 — Payment Config Hardcoded in Source ✅ Fixed
**Fixed: 2026-05-18**

`DUITNOW_MERCHANT_ID`, `BANK_ACCOUNT_NUMBER`, `BANK_ACCOUNT_HOLDER`, `BANK_NAME`, `BANK_SWIFT_CODE` now read from environment variables.

---

#### M6 — Unbounded Text Fields on Order Submission ✅ Fixed
**Complexity: Low** | **Fixed: 2026-05-19**

All free-text fields in `submit_order` are now sliced server-side: `full_name[:150]`, `phone_number[:20]`, `street_address[:255]`, `city[:100]`, `state[:100]`, `postcode[:20]`, `order_notes[:500]`, `formatted_address[:500]`.

---

#### M7 — Geolocation Coordinates Not Bounds-Checked ✅ Fixed
**Complexity: Low** | **Fixed: 2026-05-19**

`submit_order` now rejects lat/lng outside valid geographic ranges: latitude must be in `[-90, 90]`, longitude in `[-180, 180]`; out-of-range values are set to `None`.

---

#### NEW-5 — Double Stripe Charge on Reconnect ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-19**

If a customer pays via Stripe but loses connection before the `stripe_success` redirect lands, they may return to the order page and click "Pay with Stripe" again. `start_stripe_payment` had no guard for an already-succeeded payment — it would create a second Stripe Checkout session, allowing the customer to pay twice.

**Fix:** Added guard at the top of `start_stripe_payment` (before session creation):
```python
if order.payments.filter(payment_method='stripe', status='succeeded').exists():
    messages.info(request, 'This order has already been paid. No action needed.')
    return redirect('order_success', order_id=order.id)
```

---

#### NEW-6 — Duplicate Order on Checkout Retry ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-19**

`submit_order` had no idempotency protection. If the POST completes server-side (order created, stock deducted) but the redirect response is lost mid-network, the customer could resubmit the same form and create a second order.

**Fix:** Session-based one-time idempotency key. `checkout` generates `checkout_key = secrets.token_hex(16)` and stores it in the session. The form carries it as a hidden field. `submit_order` pops the key from the session and rejects the submission if the key is missing or mismatched — any retry after the first successful POST fails gracefully.

---

#### NEW-7 — Orphaned Pending Stripe Payment Records ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-19**

Each call to `start_stripe_payment` unconditionally created a new `Payment` record. If a customer tried to pay multiple times (e.g., cancelled the Stripe page and tried again), previous `pending` sessions were never cleaned up, leaving orphaned records that clutter the admin payment view.

**Fix:** `create_stripe_checkout_session` now cancels all existing `pending` Stripe payments for the order before creating a new one:
```python
order.payments.filter(payment_method='stripe', status='pending').update(status='cancelled')
```

---

#### NEW-3 — CSP `connect-src` Blocks Nominatim ✅ Fixed
**Fixed: 2026-05-18**

`nominatim.openstreetmap.org` and `unpkg.com` added to `CSP_CONNECT_SRC`.

---

#### NEW-4 — `AUTH_PASSWORD_VALIDATORS` Disabled ✅ Fixed
**Fixed: 2026-05-18**

All four Django password validators uncommented. `validate_password()` called in `customer_profile`.

---

### LOW

#### L1 — Duplicate `@login_required` on `update_profile` ⬜ Open
**Complexity: Low**

Duplicate decorator, no security impact. Remove one.

---

#### L2 — No Rate Limiting on Notification Endpoints ⬜ Open
**Complexity: Low**

`notifications_mark_all_read` has `@ratelimit(key='user', rate='10/m')` but `notification_open` could benefit from a stricter limit.

---

#### L3 — `logout_view` Doesn't Use `@login_required` ⬜ Open
**Complexity: Low**

Manual `if request.user.is_authenticated` check instead of decorator. Inconsistent pattern.

---

## Summary Table

| ID | Title | Severity | Complexity | Status |
|---|---|---|---|---|
| C1 | Stock race condition (overselling) | Critical | High | ✅ Fixed |
| H1 | No Content Security Policy | High | High | ✅ Fixed |
| H2 | Missing HTTP security headers | High | Low | ✅ Fixed |
| H3 | Open redirect via notification link | High | Low | ✅ Fixed |
| H4 | No email verification on email change | High | Medium | 🟡 Open |
| H5 | File upload: PDF MIME not validated | High | Medium | ✅ Fixed |
| NEW-1 | Stored XSS in support chat bubbles | High | Low | ✅ Fixed |
| NEW-2 | Missing `@customer_required` on all views | High | Low | ✅ Fixed |
| M1 | No rate limit on password change | Medium | Low | ⬜ Open |
| M2 | Unguarded `int(quantity)` → 500 + debug leak | Medium | Low | ✅ Fixed |
| M3 | Error detail disclosure to users | Medium | Low | ✅ Fixed |
| M4 | `verify_receipt` exposes customer data publicly | Medium | Low | ✅ Fixed |
| M5 | Payment config hardcoded in source | Medium | Low | ✅ Fixed |
| M6 | Unbounded text fields on order submission | Medium | Low | ✅ Fixed |
| M7 | Geolocation coordinates not bounds-checked | Medium | Low | ✅ Fixed |
| NEW-3 | CSP `connect-src` breaks checkout map geocoding | Medium | Low | ✅ Fixed |
| NEW-4 | `AUTH_PASSWORD_VALIDATORS` disabled | Medium | Low | ✅ Fixed |
| NEW-5 | Double Stripe charge on reconnect | Medium | Low | ✅ Fixed |
| NEW-6 | Duplicate order on checkout retry | Medium | Low | ✅ Fixed |
| NEW-7 | Orphaned pending Stripe Payment records | Low | Low | ✅ Fixed |
| L1 | Duplicate `@login_required` on `update_profile` | Low | Low | ⬜ Open |
| L2 | No rate limit on notification endpoints | Low | Low | ⬜ Open |
| L3 | `logout_view` inconsistency | Low | Low | ⬜ Open |

---

## Fix Priority Order

**Must fix before shipping:**
1. `[x]` NEW-1 — Stored XSS in chat (`innerHTML` → `textContent`) ✅ 2026-05-18
2. `[x]` NEW-2 — Apply `@customer_required` to all customer views ✅ 2026-05-18
3. See also admin/manager security review for A1 (GET CSRF on approval views) — ship blocker

**Fix before production:**
4. `[x]` M2 — Wrap `int(quantity)` in try/except with bounds cap ✅ 2026-05-18
5. `[x]` H5 — Add PDF magic-byte check + tighten extension allowlist ✅ 2026-05-18
6. `[x]` NEW-4 — Uncomment `AUTH_PASSWORD_VALIDATORS` + call `validate_password()` ✅ 2026-05-18
7. `[x]` NEW-3 — Add `nominatim.openstreetmap.org` to `CSP_CONNECT_SRC` ✅ 2026-05-18
8. `[ ]` H4 — Email verification on email change
9. `[x]` M5 — Move payment config to environment variables ✅ 2026-05-18

**Lower priority:**
10. `[x]` M3 — Replace exception messages with generic user-facing strings ✅ 2026-05-20
11. `[x]` M4 — Audit `verify_receipt` template for data exposure ✅ 2026-05-20
12. `[x]` M6 — Truncate unbounded POST text fields server-side ✅ 2026-05-19
13. `[x]` M7 — Bounds-check lat/lng values ✅ 2026-05-19
14. `[ ]` M1 — Rate-limit password change endpoint
15. `[ ]` L1 / L2 / L3 — Minor cleanup
