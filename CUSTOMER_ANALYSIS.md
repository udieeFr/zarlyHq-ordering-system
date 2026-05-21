# Customer Application — Comprehensive Analysis

> Scope: every file under `customers/`, every customer-facing template, every URL path beneath `/menu/`, and every customer-triggerable interaction in `zarlyOs/urls.py` and the wider middleware stack.
> Generated: 2026-05-21.

---

## 1. Application Overview

ZarlyHQ is a Django 6.0 food-ordering SaaS for a Malaysian F&B business. The `customers` Django app encapsulates everything a paying customer can do — discovery, cart, checkout, payment, post-purchase support, ratings, and account management. The three-role model (`customer`, `sales_admin`, `manager`) is defined on the single `customers.User` model (`customers/models.py:4`); a customer is anyone whose `role == 'customer'`.

### 1.1 Files in `customers/`

| File | Purpose |
| --- | --- |
| `models.py` | `User`, `Category`, `Allergy`, `Product`, `Favourite`, `CustomerProfile`, `OrderRating`, `ProductReview` |
| `views.py` | 35 view functions covering catalog, cart, checkout, payment, complaints, ratings, notifications, profile |
| `urls.py` | 26 URL patterns mounted at `/menu/` |
| `auth_utils.py` | Decorators (`customer_required`, `sales_admin_required`, `manager_required`, `role_required`) and role-aware redirect helpers |
| `payment_utils.py` | DuitNow/bank transfer QR generation and payment-proof file validation (magic-byte + Pillow verify) |
| `stripe_utils.py` | Stripe Checkout session creation, webhook handlers, refund handling |
| `otp_utils.py` | Email-keyed 6-digit OTP generation/verification (currently dormant; no view wires it up) |
| `context_processors.py` | `cart_context` — adds `cart_count` and `cart_total` to every template for authenticated customers |
| `admin.py` | Django admin registrations for `User`, `Product`, `Category`, `Allergy`, `Favourite`, `CustomerProfile` |
| `tests.py` | 25+ unit tests for QR generation, file validation, payment-proof workflow |
| `migrations/` | 14 migrations — baseline + email-verification fields, CRM profile, indexes, OrderRating/ProductReview |

### 1.2 Data Model Surface

- **`User`** (extends `AbstractUser`): adds `email` (unique), `role`, `phone_number`, `email_verified` (default `False`, **not enforced anywhere**).
- **`CustomerProfile`**: 1-to-1 with `User`. Holds `total_orders`, `total_spent`, `loyalty_tier` (bronze→silver→gold→platinum), `marketing_opt_in`, `preferred_payment_method`, `default_phone`, `default_address`, `admin_notes` (internal-only), `is_vip`.
- **`Product`** + **`Category`** + **`Allergy`**: catalog. `Favourite` is the heart/wishlist join table.
- **`OrderRating`** (1-to-1 with `Order`) and **`ProductReview`** (per-customer-per-product-per-order) gate reviews behind `status='delivered'`.
- **`Order` / `OrderItem` / `Payment` / `Complaint` / `SupportMessage` / `DigitalSignature` / `Refund` / `Notification` / `AuditLog`** live in `admins/models.py` but are heavily consumed by customer views.

---

## 2. Customer URL Surface (`/menu/...`)

All routes are prefixed with `/menu/` from `zarlyOs/urls.py:89`.

| URL | View | Auth | Method | Purpose |
| --- | --- | --- | --- | --- |
| `/` (root menu) | `product_list` | Public | GET | Catalog browse + AJAX partial |
| `/menu/` | `product_list` | Public | GET | Alias |
| `/menu/add-to-cart/` | `add_to_cart` | Customer | POST | Add item, returns JSON or redirect |
| `/menu/cart/` | `cart_view` | Customer | GET | Cart contents |
| `/menu/cart/update/` | `update_cart` | Customer | POST | Quantity update / clear cart |
| `/menu/cart/remove/` | `remove_from_cart` | Customer | POST | Remove line item |
| `/menu/checkout/` | `checkout` | Customer | GET | Checkout form + `checkout_key` issued |
| `/menu/submit-order/` | `submit_order` | Customer | POST | Persist order, branch to Stripe or manual |
| `/menu/order-details/<id>/` | `order_success` | Customer (own) | GET | Receipt + payment widget |
| `/menu/order/<id>/payment/` | `payment_page` | Customer (own) | GET | Choose Stripe vs manual |
| `/menu/order/<id>/payment/stripe/` | `start_stripe_payment` | Customer (own) | POST | Create new Stripe session |
| `/menu/stripe/success/<id>/` | `stripe_success` | Customer (own) | GET | After-Stripe landing |
| `/menu/stripe/cancel/<id>/` | `stripe_cancel` | Customer (own) | GET | Stripe cancelled |
| `/menu/stripe/webhook/` & `/stripe/webhook/` | `stripe_webhook` | **Public (signed)** | POST | Stripe event sink |
| `/menu/order/<id>/invoice/` | `download_invoice` | Customer (own) | GET | Unsigned PDF for pending orders |
| `/menu/order/<id>/pay/` | `upload_payment_proof` | Customer (own) | POST | Bank-transfer receipt upload |
| `/menu/orders/` | `customer_orders` | Customer | GET | Dashboard with loyalty + stats |
| `/menu/rejected-orders/` | `rejected_orders` | Customer | GET | Past rejections |
| `/menu/awaiting-payment/` | `awaiting_payment_orders` | Customer | GET | Pay-later queue |
| `/menu/logout/` | `logout_view` | Auth | GET | Logout (customers/views.py) |
| `/menu/submit-complaint/` | `submit_complaint` | Customer | POST | File a complaint (with evidence) |
| `/menu/support/` | `customer_support` | Customer | GET | Complaint list + chat launcher |
| `/menu/support/complaint/<id>/` | `customer_complaint_detail` | Customer (own) | GET | Encrypted chat thread |
| `/menu/support/complaint/<id>/messages/` | `customer_complaint_messages` | Customer (own) | GET/POST | Poll + send chat (Fernet) |
| `/menu/verify/<id>/` | `verify_receipt` | **Public** | GET | PDF signature verification |
| `/menu/notifications/` | `notifications_list` | Customer | GET | Bell-icon feed |
| `/menu/notifications/<id>/open/` | `notification_open` | Customer (own) | **GET** | Mark read + redirect |
| `/menu/notifications/mark-all-read/` | `notifications_mark_all_read` | Customer | **GET** | Mark all read |
| `/menu/order/<id>/reorder/` | `reorder` | Customer (own) | **GET** | Repopulate cart from past order |
| `/menu/profile/` | `customer_profile` | Customer | GET/POST | Profile + password change |
| `/menu/profile/update/` | `update_profile` | Customer | POST (JSON) | Inline updates |
| `/menu/order/<id>/cancel/` | `cancel_order` | Customer (own) | POST | Cancel pending order |
| `/menu/favourites/` | `favourites_list` | Customer | GET | Wishlist |
| `/menu/favourites/toggle/` | `toggle_favourite` | Customer | POST | Heart toggle |
| `/menu/order/<id>/rate/` | `rate_order` | Customer (own) | POST | 1–5 star OrderRating |
| `/menu/product/<id>/review/` | `submit_product_review` | Customer (own) | POST | Per-product review |
| `/login/`, `/signup/`, `/logout/` | unified flows | — | — | Wired in `zarlyOs/urls.py` |

---

## 3. Customer Session Lifecycle

```
┌──── PUBLIC ────────────────────────────────────────────────────────────┐
│  /start/ landing → /menu/ catalog (browse + add-to-cart allowed only   │
│  for authenticated customers; anonymous users see prices but can't     │
│  POST to cart endpoints because of customer_required).                 │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──── AUTH ──────────────────────────────────────────────────────────────┐
│  /signup/ (customer_signup): username + email + password (min 6).      │
│       — User row created with role='customer', email_verified=False.   │
│       — No email confirmation sent. No OTP gating.                     │
│  /login/ (unified_login, in admins/views.py):                          │
│       — Rate-limited 10/m by IP.                                       │
│       — Anonymous cart is preserved across login (session merged).     │
│       — Audit log entries: login_success / login_failed.               │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──── BROWSE & CART ─────────────────────────────────────────────────────┐
│  product_list filter chain: category / allergy / search-q / sold-out.  │
│  Cart lives in request.session['cart'] = {product_id: quantity}.       │
│  Ghost-product cleanup on every read (get_cart_from_session).          │
│  Quantity clamped to [1, 99]; >99 silently capped.                     │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──── CHECKOUT ──────────────────────────────────────────────────────────┐
│  /menu/checkout/ issues a one-time `checkout_key` into both the form   │
│  and the session. submit_order pops it from session and rejects if     │
│  missing/mismatched — idempotency guard against double-submits.        │
│                                                                        │
│  Geolocation: client sends lat/lng; server clamps to ±90/±180 and      │
│  trims free-text fields (M6 length limits at views.py:621-627).        │
│                                                                        │
│  _create_order_atomic SELECT FOR UPDATEs products and decrements stock │
│  inside one transaction — prevents overselling under concurrency.      │
└────────────────────────────────────────────────────────────────────────┘
        │
        ├── payment_method == 'stripe' → create Stripe session → redirect
        │                                 webhook flips Payment to succeeded
        │
        └── payment_method == 'manual' → choose 'now' (upload proof) or
                                          'later' (wait for admin approval)
        │
        ▼
┌──── FULFILMENT (read-only from customer side) ─────────────────────────┐
│  Order status: pending → approved → prepared → ready_for_delivery →    │
│  out_for_delivery → delivered.  Customer may cancel ONLY while         │
│  status == 'pending'.  Stock is restored on cancel.                    │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──── POST-PURCHASE ─────────────────────────────────────────────────────┐
│  Signed receipt: PDF generated, hash + signature stored on             │
│  DigitalSignature.  Public verify_receipt endpoint computes SHA-256 +  │
│  validates PKCS#7 with PyHanko.                                        │
│  Complaints: file via form (with evidence); chat thread is Fernet-     │
│  encrypted (SUPPORT_CHAT_KEY).                                         │
│  Ratings & reviews: gated to status='delivered'; ProductReview unique  │
│  per (product, customer, order).                                       │
│  Loyalty: CustomerProfile.recalculate() runs on each order read of     │
│  /menu/orders/ — bronze/silver/gold/platinum thresholds at 0/500/      │
│  2000/5000 MYR.                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Implicit Actions (not prompted by the user)

These run as side-effects of user-driven actions:

- **Audit logging** on signup, login, logout, order create, payment proof upload, order cancel, complaint submit, support message send, receipt verify.
- **Admin notifications** on new order, payment proof upload, customer complaint, customer cancellation.
- **Customer notifications** on order approval, refund confirmation, payment-failure events.
- **CRM recalculation** on every visit to `customer_orders` (re-aggregates totals + tier).
- **Stock decrement** on order creation; **stock restore** on customer cancel.
- **Stripe pending-session cancellation**: when a new Stripe session is created for an order, prior pending Stripe payments on the same order are flipped to `cancelled`.
- **Ghost product cleanup** in cart (deleted products removed silently).
- **Session activity heartbeat**: `SessionTimeoutMiddleware` writes `_last_activity` on every authenticated request and forces logout after 60 minutes of inactivity.

---

## 4. Existing Features — Strengths and What to Improve

### 4.1 Strengths (keep these)

- **Atomic stock decrement with row-level locks** (`_create_order_atomic`, `views.py:537`) — solid concurrency safety.
- **Idempotent checkout** via single-use `checkout_key`. Prevents double-charges.
- **Server-side payment-proof validation**: magic bytes + Pillow `verify()` + extension allow-list + 5 MB size cap (`payment_utils.py:183`).
- **Webhook signature verification** with explicit error logging (`stripe_utils.py:265`).
- **Replay protection**: manual proof upload is blocked if a Stripe payment has already succeeded for the order (`views.py:277-281`).
- **Receipt non-repudiation**: SHA-256 chain hash plus PyHanko PKCS#7 validation, results cached 24 h.
- **AuditLog hash chain** (`admins/models.py:465`) — tamper-evident with `verify_chain()`.
- **CSP with per-request nonce** (`zarlyOs/middleware.py:58-82`) blocks injected `<script>` tags.
- **Open-redirect guard on notifications** (`url_has_allowed_host_and_scheme` at `views.py:1304`).
- **Encrypted support chat** via Fernet (key rotation possible via `SUPPORT_CHAT_KEY`).
- **`limit_choices_to`** on FKs in admin (e.g., Order.customer must be role='customer').

### 4.2 Existing Features That Should Be Improved

| # | Area | What's Suboptimal | Suggested Improvement |
|---|------|-------------------|----------------------|
| F1 | **Signup password policy** | Manual `len(password) < 6` check bypasses Django's `AUTH_PASSWORD_VALIDATORS` | Run `validate_password(password, user)` like `customer_profile`'s change-password branch does |
| F2 | **Email verification** | `email_verified` field exists but is never set or checked | Wire `otp_utils.generate_and_cache_signup_otp` into `customer_signup` — block first order until verified |
| F3 | **Password reset** | No reset/forgot-password flow at all — users locked out of their accounts have no recovery | Add Django's `PasswordResetView` chain or a custom OTP-based reset using existing `otp_utils` |
| F4 | **Profile email-change** | `update_profile` lets a session change `user.email` with **no** password re-prompt and **no** OTP confirmation | Require current password (already pattern in change-password) or send confirmation OTP to old + new address before commit |
| F5 | **OTP brute-force** | `verify_otp` (and `verify_signup_otp`) has no attempt counter — 6-digit code can be brute-forced inside the 5-min TTL | Track attempt count in cache, lock after 5 failures, throw `expired` thereafter |
| F6 | **Reorder verb** | `reorder` accepts GET and silently overwrites the cart (see §5, Vuln #1) | Change to POST + CSRF, or require user confirmation before replacing cart |
| F7 | **Notification "mark read" verbs** | `notification_open` and `notifications_mark_all_read` mutate state on GET | Change to POST or treat as idempotent only |
| F8 | **Public `verify_receipt`** | Discloses existence of any order ID (`not_found` vs other statuses), only IP-rate-limited | Either gate behind an opaque token (sign the order_id + signature_hash into the share-link URL), or require login |
| F9 | **`get_client_ip` trusts `X-Forwarded-For` blindly** | Leftmost IP is client-controllable; spoofs audit log IPs | Use Django's `SECURE_PROXY_SSL_HEADER` analogue: configure `TRUSTED_PROXIES` list and validate that the immediate upstream is trusted before honoring `X-Forwarded-For` |
| F10 | **Webhook secret prefix in logs** | `[WEBHOOK] Secret prefix in use: <12 chars>` (views.py:924-925) is INFO level | Strip to first 6 or fully redact; or demote to DEBUG-only and turn off in prod |
| F11 | **`update_profile` JSON parsing** | Falls back to `request.POST` on JSONDecodeError, then accepts strings without length cap | Apply same length caps as `submit_order` (full_name[:150], phone[:20], address[:500]) |
| F12 | **`signup` view captcha** | No bot deterrent; ratelimit only by IP | Add a hCaptcha/Turnstile challenge on signup + login |
| F13 | **CSP `style-src 'unsafe-inline'`** | Defeats nonce protection for style attribute injection | Move all inline styles to stylesheets and remove `'unsafe-inline'`. Style nonces require a small refactor of the templates' inline `<style>` blocks |
| F14 | **Stripe Checkout uses `unit_amount = product.price * 100` cast to int** | Re-derives from current product price, not OrderItem.subtotal — if a product's price changes between order creation and Stripe redirect, customer is charged the new price (`stripe_utils.py:48`) | Use `order.total_amount` as a single line item or read `OrderItem.subtotal` |
| F15 | **`stripe_webhook` swallows handler exceptions** | Generic `except Exception` returns 200 to Stripe even if processing failed (views.py:976) | Distinguish "we processed it OK" vs "transient error" — return 500 on transient so Stripe retries; only return 200 on success or definitive failure |
| F16 | **Decimal cart prices via templates** | `RM {{ item.subtotal }}` doesn't apply `floatformat:2` consistently (some templates do, some don't) | Standardize on `floatformat:2` everywhere customer-facing |
| F17 | **Order detail XSS surface** | Templates render `order.full_name`, `order.street_address`, etc. — Django autoescapes, but the chat drawer manually sets `textContent` (good) while `order_notes` is concatenated server-side and re-rendered (`order_notes = (order.order_notes or '') + f'\n[CANCELLED…]'`); safe under autoescape but watch for `|safe` regressions | Add a unit test that asserts `<script>` in order fields renders escaped |
| F18 | **Cart session sprawl** | Anonymous browse creates session rows; cleared only on `clearsessions` cron | Lower `SESSION_COOKIE_AGE` for anonymous, or only set cart when a customer actually adds something |
| F19 | **Loyalty recalc on every page** | `customer_orders` calls `profile.recalculate()` unconditionally; runs SUM/COUNT/MAX every page view | Move recalc into order status-change signals; cache the result with a short TTL |
| F20 | **`customer_required` swallows superusers** | `request.user.role != 'customer'` blocks superusers from customer pages — useful for production, but breaks debug | Allow `role == 'customer' or is_superuser` if intentional, or document the choice |

---

## 5. Security Findings

The risks below are **specific to the customer surface** and are listed with severity + a concrete mitigation. Confidence is the analyst's confidence that the issue is genuinely exploitable as described.

### Vuln 1 — CSRF on `reorder` (GET-based state change) — `customers/views.py:1416-1448` | `customers/urls.py:46`

- **Severity**: Medium
- **Category**: `csrf` / `unsafe_method`
- **Confidence**: 9/10
- **Description**: `@customer_required @ratelimit(key='user', rate='20/m', block=False)` decorates `reorder` without any method check. Any GET request silently overwrites `request.session['cart']` with the items from the targeted order and redirects to checkout.
- **Exploit scenario**: Attacker hosts a page with `<img src="https://zarly.example.com/menu/order/12345/reorder/">`. A logged-in customer (who owns order 12345) visits the page; their existing cart is wiped and replaced with order 12345's items. The victim is redirected to checkout on their next click. Repeated across many `order_id` values, an attacker can disrupt a customer's session, or — combined with a phishing flow — coerce them into placing a copy of a past order.
- **Recommendation**: Require POST and rely on Django's CSRF middleware: `if request.method != 'POST': return redirect('customer_orders')`. Update `templates/customers/customer_orders.html:436` so the "Reorder" link becomes a `<form method="post">` button with `{% csrf_token %}`.

### Vuln 2 — Customer signup bypasses `AUTH_PASSWORD_VALIDATORS` — `customers/views.py:33-80`

- **Severity**: Medium
- **Category**: `weak_authentication`
- **Confidence**: 9/10
- **Description**: `customer_signup` performs only `len(password) < 6`. It then calls `User.objects.create_user(...)` which does **not** invoke `validate_password`. Django's configured validators (NumericPasswordValidator, CommonPasswordValidator, UserAttributeSimilarityValidator) are bypassed only on signup — `customer_profile` correctly runs them on password change.
- **Exploit scenario**: Attackers register accounts with `password=123456` or `password=password` and abuse them for credential-stuffing demonstrations, spam orders, or password-reuse pivots into other customer accounts (since this signup form also accepts passwords reused on other breached sites).
- **Recommendation**: Import `from django.contrib.auth.password_validation import validate_password` and call it inside the validation block; collect `DjangoValidationError.messages` into `errors['password']`. Bump the minimum to 8 characters and align with the change-password flow.

### Vuln 3 — `update_profile` allows email change without re-authentication — `customers/views.py:1380-1413`

- **Severity**: Medium
- **Category**: `account_takeover_amplifier`
- **Confidence**: 8/10
- **Description**: A POST (form or JSON) updates `user.email`, `user.first_name`, `user.last_name`, `user.phone_number`, and `profile.default_address` with no current-password prompt and no email-ownership challenge. Email uniqueness is checked but ownership is not. There is also no length cap on the JSON payload (the form-fallback path bypasses the M6 caps applied elsewhere).
- **Exploit scenario**: An attacker who obtains a session (via XSS in a third-party library, session fixation on a shared machine, or stolen session cookie) flips the victim's email to one they control. The instant a forgot-password flow is implemented (see F3 above), this becomes account takeover. Even without password reset, the attacker now receives the victim's order notifications, invoices, and signed receipts at their own inbox.
- **Recommendation**: Before persisting an email change, require the user's current password (mirror the password-change branch in `customer_profile`). Send a confirmation OTP to the *new* address and only commit on verify. Apply length caps server-side regardless of POST vs JSON path.

### Vuln 4 — `get_client_ip` trusts arbitrary `X-Forwarded-For` — `admins/notifications.py:13-16`

- **Severity**: Medium
- **Category**: `audit_log_spoofing` / `rate_limit_bypass`
- **Confidence**: 8/10 (assumes app may be deployed without nginx stripping the header)
- **Description**: `forwarded.split(',')[0].strip()` returns the leftmost value, which is fully client-controlled. The result is written to `AuditLog.ip_address` and `_compute_hash` includes it in the chain. The audit log is otherwise tamper-evident, but the recorded IP is not trustworthy.
- **Exploit scenario**: An attacker performing credential stuffing on `/login/` (10/m IP rate-limited) sends `X-Forwarded-For: 8.8.8.8` on each request. Even if Django's ratelimit uses `REMOTE_ADDR` rather than `X-Forwarded-For`, the `AuditLog` IP and any forensic correlation is poisoned. Investigators chasing a brute-force trail are sent to 8.8.8.8 instead of the real source.
- **Recommendation**: Maintain a `TRUSTED_PROXIES` setting; only honor `X-Forwarded-For` when `REMOTE_ADDR` is in that list, and take the **rightmost** untrusted hop from the header rather than the leftmost. Document the deployment requirement that nginx (or the cloud LB) must strip incoming `X-Forwarded-For` before adding its own.

### Vuln 5 — GET-based "mark as read" mutates state — `customers/views.py:1297-1318`, `customers/urls.py:42-43`

- **Severity**: Low
- **Category**: `csrf` / `unsafe_method`
- **Confidence**: 9/10
- **Description**: `notification_open` (GET, marks one notification read + redirects) and `notifications_mark_all_read` (GET, marks every notification read) lack method checks. `notification_open` does validate `notif.link` against the host allowlist (good), but the read-flag flip is still a side-effect on GET.
- **Exploit scenario**: Any malicious page can include `<img src="/menu/notifications/mark-all-read/">` to clear the unread badge for a logged-in customer, masking attacker-relevant notifications (e.g., "your order address was changed", "a refund was issued"). Low impact in isolation.
- **Recommendation**: Convert both endpoints to POST and update the templates to use form buttons. Treat GET as a 405.

### Vuln 6 — Stripe webhook secret prefix logged at INFO — `customers/views.py:924-928`

- **Severity**: Low
- **Category**: `sensitive_data_exposure`
- **Confidence**: 7/10
- **Description**: `logger.info(f'[WEBHOOK] Secret prefix in use: {secret_preview}...')` writes the first 12 characters of `STRIPE_WEBHOOK_SECRET` into the application log on every webhook hit. The secret begins with the constant prefix `whsec_test_` or `whsec_live_`, so up to 6 characters of the true random portion are exposed.
- **Exploit scenario**: An attacker with read access to application logs (compromised log aggregator, leaked log file, exposed Sentry) obtains a head-start on brute-forcing the webhook secret. The remaining entropy is still substantial, but the leak is unnecessary and the same line is repeated per request.
- **Recommendation**: Redact entirely or shorten to 4 characters of the random portion only; alternatively gate this behind `if settings.DEBUG`. Removing the line altogether is fine — the surrounding lines already log header presence and verification outcome.

### Vuln 7 — Public `verify_receipt` discloses order existence — `customers/views.py:1170-1275`

- **Severity**: Low
- **Category**: `information_disclosure`
- **Confidence**: 7/10
- **Description**: `verify_receipt` is unauthenticated. For any sequential `order_id`, the response distinguishes `not_found`, `tampered`, `valid`, etc. Order IDs are monotonic integers, so anyone can enumerate every signed order, learn the signing timestamp, and download the signed PDF via `pdf_download_url` if `MEDIA_ROOT` is served openly.
- **Exploit scenario**: An attacker scrapes `/menu/verify/1/`, `/menu/verify/2/`, … to enumerate signed orders and harvest the public PDFs (which contain customer name, delivery address, items, and total). The IP rate limit (20/m) is bypassed by IP rotation or — as noted in Vuln 4 — by spoofing `X-Forwarded-For` if the deployment honours it.
- **Recommendation**: Switch the verification link to include an unguessable token (e.g., `verify/<order_id>/<base64-hmac>/`), or require login. At minimum, make the PDF storage non-listable and serve through Django with `customer == request.user` (or a similar HMAC) checks.

### Other Items Considered and Ruled Out

| Considered | Outcome |
|---|---|
| SQL injection via `category`, `allergy`, `q` query params (`product_list`) | Safe — Django ORM uses parameterized queries; `name__icontains` doesn't allow operator injection |
| Path traversal in `download_invoice`, `verify_receipt`, `submit_complaint` (the `pdf_path` reads) | Safe — `pdf_path` comes from `DigitalSignature.pdf_path` (a FileField set by the admin signing flow); customers cannot influence the filename |
| Stored XSS via `order_notes`, complaint `subject`/`message`, profile fields | Safe — Django autoescape, no `\|safe` in any customer template; chat drawer uses `.textContent` (templates/customers/complaint_detail.html:94, customer_support.html:551) |
| CSRF on `stripe_webhook` | Intentional — `@csrf_exempt` with Stripe signature verification |
| Open redirect via `notification_open` | Mitigated — `url_has_allowed_host_and_scheme(notif.link, allowed_hosts={request.get_host()})` |
| OTP brute force | Code exists but is not wired into any view; not exploitable today (but plug the gap when wiring it in — see F5) |
| IDOR on orders/complaints/notifications | All views scope with `customer=request.user` or `recipient=request.user`; no IDOR found |
| Cart overselling under concurrency | Mitigated via `SELECT FOR UPDATE` in `_create_order_atomic` |
| Stripe replay attack (manual upload after card payment) | Mitigated at `views.py:277-281` |

---

## 6. Features That Should Be Added

These are gaps in the customer journey rather than security findings, ordered by approximate user value.

### 6.1 P0 — Auth & Account Health
1. **Forgot-password flow** (F3). Currently a locked-out customer must contact support. Implement either Django's stock `PasswordResetView` chain or an OTP-driven reset reusing `otp_utils`.
2. **Email verification on signup** (F2). `email_verified` exists. Block first checkout until verified, or at least restrict marketing-opt-in to verified addresses.
3. **2FA / TOTP for high-value accounts**. Optional but recommended for VIP customers (`CustomerProfile.is_vip`).
4. **Confirm email/password change with re-auth** (Vuln 3 mitigation).

### 6.2 P1 — Checkout & Order Experience
5. **Saved delivery addresses**. Today only the most recent order is offered as "use this address". Add a proper `CustomerAddress` model with multiple labeled addresses.
6. **Order ETA / estimated delivery time** on the customer dashboard. Status transitions are timestamped on `OrderEvent`; surface a forecast based on average past elapsed time per status.
7. **Live order status push** (Server-Sent Events or polling endpoint). The "In Progress" card on `/menu/orders/` is currently static between full page loads.
8. **Promo / coupon codes**. Migration `0012` has `coupon` mentioned in a name but no model. Implement first-order discounts and tier-based perks (platinum gets 5% off, etc.).
9. **Tip / service charge** option at checkout for delivery riders.
10. **Multi-currency display** (settings.STRIPE_CURRENCY already exists; expose to user as preference).

### 6.3 P1 — Loyalty & Engagement
11. **Loyalty redemption**. Tiers (`bronze`/`silver`/`gold`/`platinum`) exist but unlock nothing. Surface concrete perks per tier (free delivery threshold, early access to new menu items, birthday vouchers).
12. **Referral programme**. "Refer a friend → both get RM10". Reuse existing notification + audit pipeline.
13. **Wishlist sharing**. `Favourite` already exists; allow customers to share their wishlist URL with friends.

### 6.4 P1 — Trust & Transparency
14. **In-app order chat with admins** for non-complaint queries (extend the encrypted `SupportMessage` system to general inquiries).
15. **Order history export** (PDF / CSV) for tax/expense purposes.
16. **Refund status page**. Refunds are tracked in `admins.Refund` and a single notification fires; expose a refund-by-refund history view.

### 6.5 P2 — Discovery
17. **Search-as-you-type with product image previews** (the current `product_list` AJAX is debounced 350 ms; can be improved with skeleton states).
18. **Recommendations**. "Customers who liked X also liked Y" — derive from `Favourite` + `OrderItem`.
19. **Allergy profile**. Persist a user's allergy preferences on `CustomerProfile` instead of forcing them to refilter every visit.
20. **Filter by dietary tag** (vegan/halal/etc.) — the current `Allergy` model only handles exclusions.

### 6.6 P2 — Accessibility & Internationalisation
21. **Locale + currency selection** (settings.LANGUAGE_CODE is hard-coded to `en-us`).
22. **WCAG audit** of the cart/checkout (`templates/customers/cart.html`, `checkout.html`). The stepper buttons (`crt-step-btn`) lack `aria-live` updates for screen readers when quantities change.
23. **High-contrast / dark mode** (the brand orange `#ff9933` over `oklch(99%…)` runs into AA contrast issues on small text).

### 6.7 P3 — Mobile Polish
24. **Native-feeling PWA** (`manifest.json`, install prompt, offline cart). The site is already responsive but doesn't install.
25. **Push notifications** instead of in-app bell (Notification model already abstracts the recipient).
26. **Image-CDN-backed product photos** with `srcset` and AVIF fallback.

---

## 7. Quick-Win Mitigation Plan (1-week sprint)

1. **Day 1** — Vuln 1 (POST-ify `reorder`) + Vuln 5 (POST-ify notification reads). Pure refactor, no schema changes. Update three templates.
2. **Day 1** — F1 + Vuln 2: drop in `validate_password` on signup and bump min length to 8.
3. **Day 2** — Vuln 6: redact webhook secret log line; demote remaining diagnostics to DEBUG.
4. **Day 2** — F10/F11 + Vuln 3: require current-password on email change; add server-side length caps to the JSON path of `update_profile`.
5. **Day 3** — Vuln 4: introduce `TRUSTED_PROXIES`, validate `REMOTE_ADDR` against it before honouring `X-Forwarded-For`.
6. **Day 4** — Vuln 7: rework `verify_receipt` URL to `verify/<order_id>/<hmac>/`. Add migration for a signed-link token (or compute on the fly with `signing.dumps`).
7. **Day 5** — F2 + F3: wire `otp_utils.generate_and_cache_signup_otp` into `customer_signup`, add `/menu/verify-email/` + a `PasswordResetView` chain.

Each of these is small, reversible, and covered by the existing audit log so a regression is detectable.

---

## 8. Appendix — File-by-file Findings Index

| File | Key observations |
|---|---|
| `customers/models.py` | Robust schema. `CustomerProfile.recalculate` is correct but expensive on hot paths. `OrderRating.unique` enforced via 1-to-1 + status guard in view |
| `customers/views.py` | Largest surface area. Issues clustered around: GET-mutates-state (Vuln 1/5), email change without re-auth (Vuln 3), signup password policy (Vuln 2), webhook log leakage (Vuln 6), public receipt verify (Vuln 7) |
| `customers/auth_utils.py` | Sound; `customer_required` strictly checks `role=='customer'`. No bypass found |
| `customers/payment_utils.py` | Magic-byte + Pillow `verify()` is a strong defence. PDF magic check is correct. DuitNow QR format is "simplified" — confirm with bank that it matches their decode spec |
| `customers/stripe_utils.py` | Webhook signature verification correct. `handle_charge_refunded` fallback (lookup by `payment_intent`) is good. F14 (price drift) is a real edge case |
| `customers/otp_utils.py` | Cache-backed, single-use, 5-min TTL. Missing attempt counter (F5). Not currently invoked by any view |
| `customers/context_processors.py` | Cheap and scoped to `role=='customer'`. No issues |
| `customers/admin.py` | Default Django admin; standard exposure |
| `customers/tests.py` | Good payment-utility coverage; expand to cover checkout idempotency and reorder method check after fix |
| `zarlyOs/middleware.py` | `SessionTimeoutMiddleware` correctly returns 401 JSON for AJAX; `EagerNonceCSPMiddleware` ensures every response carries a CSP nonce |
| `zarlyOs/settings.py` | Good CSP, decent security headers. Production HTTPS toggles commented but documented. `CSP_STYLE_SRC` includes `'unsafe-inline'` (F13) |
| `templates/customers/*.html` | Autoescape used consistently. Inline `<script>` blocks carry `request.csp_nonce`. Chat drawer correctly uses `.textContent` to avoid DOM XSS |

---

*End of report.*
