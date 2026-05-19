# Customer-Side Review — May 18, 2026

> **Scope:** `customers/` directory — security vulnerabilities + functionality completeness
> **Reviewed by:** Claude Code security agent
> **Status legend:** `[ ]` not started · `[~]` in progress · `[x]` done
>
> **Fixed on 2026-05-18:** All 6 security findings resolved. Tests in `tests/test_security_fixes.py`.

---

## Security Findings

### 🔴 HIGH — Fix before shipping

- [x] **VULN 1 — Stored XSS in Chat Bubbles** ✅ Fixed 2026-05-18
  - **Files:** `templates/customers/complaint_detail.html`, `templates/customers/customer_support.html`
  - **Problem:** `appendMessage` injects `msg.body` via `innerHTML` with no escaping. A malicious chat message containing HTML/JS executes in the recipient's browser — escalates to admin account takeover.
  - **Fix:** Replace `innerHTML` with safe DOM construction:
    ```js
    const bodyEl = document.createElement('div');
    bodyEl.textContent = msg.body;
    wrap.appendChild(bodyEl);
    ```

- [x] **VULN 2 — Missing Role Enforcement (`@customer_required`)** ✅ Fixed 2026-05-18
  - **File:** `customers/views.py`
  - **Problem:** All customer views use `@login_required` but never `@customer_required`. A `sales_admin` or `manager` can place orders, submit complaints, and use support chat — including self-approving orders.
  - **Fix:** Replace `@login_required` with `@customer_required` (already exists in `customers/auth_utils.py`) on all customer-facing views.

- [x] **VULN 3 — Unguarded `int()` on POST Input → 500 + Debug Leak** ✅ Fixed 2026-05-18
  - **File:** `customers/views.py:342`, `customers/views.py:386`
  - **Problem:** `add_to_cart` and `update_cart` call `int(request.POST.get('quantity', ...))` with no try/except. With `DEBUG=True`, a non-integer input (e.g. `quantity=abc`) returns a full stack trace including DB config.
  - **Fix:**
    ```python
    try:
        quantity = max(1, min(int(request.POST.get('quantity', 1)), 99))
    except (TypeError, ValueError):
        quantity = 1
    ```

---

### 🟡 MEDIUM — Fix before production

- [x] **VULN 4 — PDF Upload Skips Content Inspection** ✅ Fixed 2026-05-18
  - **File:** `customers/payment_utils.py:199`
  - **Problem:** Extension check + Pillow verify only runs for images. PDFs skip content inspection — a file named `proof.pdf` containing HTML/JS is accepted. If served inline by nginx, it executes in the admin's browser.
  - **Fix:** Check first 4 bytes for `%PDF` magic number. Serve all uploads with `Content-Disposition: attachment`.

- [x] **VULN 5 — `AUTH_PASSWORD_VALIDATORS` Disabled** ✅ Fixed 2026-05-18
  - **File:** `zarlyOs/settings.py:103–116`, `customers/views.py:1361`
  - **Problem:** All Django password validators are commented out. Only a min-length of 8 is checked — passwords like `password` or `12345678` are accepted.
  - **Fix:** Uncomment `AUTH_PASSWORD_VALIDATORS` in settings. Call `validate_password(new_pw, user)` in the profile view.

- [x] **VULN 6 — Nominatim Geocoding Blocked by CSP (Checkout Map Broken)** ✅ Fixed 2026-05-18
  - **File:** `zarlyOs/settings.py:215`
  - **Problem:** `CSP_CONNECT_SRC = ("'self'",)` blocks fetch calls to `nominatim.openstreetmap.org`. The delivery address map in checkout silently fails in all production browsers.
  - **Fix:**
    ```python
    CSP_CONNECT_SRC = ("'self'", "https://nominatim.openstreetmap.org", "https://unpkg.com")
    ```

---

### ⚙️ Pre-Production Config (not vulnerabilities, but must-fix before deploy)

- [ ] Set `ALLOWED_HOSTS` — currently `[]`
- [ ] Enable `SESSION_COOKIE_SECURE = True`
- [ ] Enable `CSRF_COOKIE_SECURE = True`
- [ ] Enable `SECURE_SSL_REDIRECT = True`
- [ ] Replace placeholder bank/QR payment details in `payment_utils.py` (`0123456789`, `123456789012`)

---

## Functionality Completeness

### ✅ Complete

- [x] Login / Logout with audit logging
- [x] Edit profile + password change (`update_session_auth_hash` used correctly)
- [x] Marketing opt-in toggle
- [x] Browse menu, filter by category/allergy, search, hide sold-out
- [x] AJAX pagination on menu
- [x] Add to cart, update quantity, remove, clear
- [x] Checkout form with delivery address
- [x] Delivery map (Leaflet) — note: geocoding broken by CSP until VULN 6 is fixed
- [x] Stripe Checkout + webhook with signature verification
- [x] Manual payment (DuitNow/Bank Transfer) + QR generation
- [x] Payment proof upload with file validation
- [x] Replay attack protection (blocks manual proof if Stripe already succeeded)
- [x] Order history (unpaid / upcoming / previous tabs)
- [x] Order statistics (total spent, avg order, top item)
- [x] Cancel order (pending only, restores stock, triggers Stripe refund)
- [x] Re-order from history
- [x] Invoice PDF download
- [x] Receipt / digital signature verification (public endpoint)
- [x] Loyalty tiers (Bronze/Silver/Gold/Platinum) + VIP badge + progress bar
- [x] In-app notifications bell with unread count
- [x] Mark-all-read, click-through with open-redirect protection
- [x] Submit complaint linked to completed orders only
- [x] Evidence image upload on complaint
- [x] Complaint status tracking (pending / resolved pill)
- [x] Support chat with Fernet encryption + Page Visibility API polling
- [x] IDOR protection — all views consistently filter by `customer=request.user`
- [x] CSRF protection — only Stripe webhook is `@csrf_exempt` (correct)
- [x] Audit logging on key customer actions

### ✅ Functionality gaps closed on 2026-05-18

- [x] **Cart persistence on login** — pre-login session cart merged in `unified_login` (`admins/views.py`)
- [x] **Product reviews / ratings** — `ProductReview` model + `/product/<id>/review/` view
- [x] **Post-delivery order rating** — `OrderRating` model + `/order/<id>/rate/` view; star UI in `customer_orders.html` and `order_success.html`
- [ ] **Promo / voucher codes** — reverted
- [ ] **Estimated delivery time display** — reverted
- [ ] **Visual order timeline** — reverted
- [x] **Bank payment config → env vars** — `payment_utils.py` now reads `DUITNOW_MERCHANT_ID`, `BANK_ACCOUNT_NUMBER`, etc. from environment
- [x] **Checkout map geocoding** — Nominatim added to CSP_CONNECT_SRC ✅ 2026-05-18
- [x] **Support chat XSS** — innerHTML replaced with textContent DOM construction ✅ 2026-05-18

### ❌ Not Implemented (acknowledged gaps — requires larger effort)

- [ ] Email verification on registration / OTP flow — no registration view exists; needs new flow before this applies
- [ ] Saved delivery addresses — partially covered by last-order auto-fill

---

## Overall Verdict

The customer side is feature-complete and the core security architecture (CSRF, ORM SQL injection prevention, Stripe webhook verification, Fernet-encrypted chat, audit log hash chain) is solid. **Two issues block shipping:** the stored XSS in chat bubbles (VULN 1) and missing role enforcement (VULN 2). The remaining medium findings and pre-production config items are all small, targeted fixes. Resolve the six security items and configure production settings — the customer side is ready to ship.
