# ZarlyHQ Security Implementation

> Documents all security controls implemented in this project — patterns, rationale, and configuration notes for future developers.

---

## 1. Authentication & Access Control

### Role Hierarchy
Three user roles enforced at the decorator level in `admins/views.py`:

| Role | Decorator | Access |
|---|---|---|
| `customer` | `@customer_required` | Menu, orders, support, profile |
| `sales_admin` | `@sales_admin_required` | Order ops, complaints, stock |
| `manager` | `@manager_required` | Analytics, CRM, campaigns, products |
| superuser | — | All of the above |

### Step-Up Authentication (Sudo)
Sensitive irreversible actions (audit log, refunds, sales report, product delete) require a second password confirmation within a 15-minute session window. Implemented in `admins/views.py::sudo_confirm`. The sudo flag is stored in `request.session['sudo_until']` as a Unix timestamp.

Sudo-gated views use `@sudo_required` decorator.

---

## 2. Private Media Serving (Vuln 1 Fix — 2026-05-22)

### Problem
`nginx.conf` previously served `/media/` as a public static alias with `Cache-Control: public`. This exposed:
- `payment_proofs/` — bank transfer screenshots with customer names and account numbers
- `signed_pdfs/` — digitally signed invoices containing full name, address, phone, order items
- `complaint_evidence/` — customer-uploaded complaint images

Payment proof filenames follow a deterministic pattern (`payment_proofs/{date}-ORDER{id}.{ext}`) with sequential integer order IDs, making enumeration trivial.

### Solution: X-Accel-Redirect with internal nginx alias

**nginx.conf** blocks direct HTTP access to all three private subdirectories:

```nginx
# Block direct access to sensitive media subdirectories
location ~ ^/media/(payment_proofs|signed_pdfs|complaint_evidence)/ {
    deny all;
}

# Internal alias — only accessible via X-Accel-Redirect from Django
location /private-media/ {
    internal;
    alias /app/media/;
}
```

**Django view** (`customers/views.py::serve_private_media`) handles authenticated file requests at `/files/<path:filepath>`:

1. Validates the subdir is in the allowed set (`payment_proofs`, `signed_pdfs`, `complaint_evidence`)
2. Staff roles (`sales_admin`, `manager`, superuser) are granted access immediately
3. Customers are granted access only after an ownership DB lookup:
   - `payment_proofs/` → `Payment.proof_image == filepath AND order.customer == user`
   - `signed_pdfs/` → `DigitalSignature.pdf_path == filepath AND order.customer == user`
   - `complaint_evidence/` → `Complaint.evidence_image == filepath AND customer == user`
4. Returns `X-Accel-Redirect: /private-media/{filepath}` — nginx serves the file from disk without the response body passing through Django (efficient)

**URL**: Registered in `zarlyOs/urls.py` at `path('files/<path:filepath>', serve_private_media)`.

### Files Changed
- `nginx.conf` — block private dirs, add internal alias
- `customers/views.py` — `serve_private_media` view added
- `zarlyOs/urls.py` — URL registered
- `templates/admins/pending_payment_orders.html` — replaced `.url` with `{% url 'serve_private_media' %}`
- `templates/admins/order_detail.html` — replaced `.url` with `{% url 'serve_private_media' %}`
- `templates/admins/sales_admin_dashboard.html` — replaced `.url` with `{% url 'serve_private_media' %}`
- `templates/customers/order_success.html` — replaced direct PDF link with `serve_private_media`
- `templates/customers/verify_receipt.html` — removed PDF download link (verification page only)

---

## 3. Receipt Verification — IDOR Prevention (Vuln 3 Fix — 2026-05-22)

### Problem
The public receipt verification endpoint was at `/menu/verify/<int:order_id>/`. Sequential integer order IDs allowed unauthenticated enumeration of all signed orders and retrieval of PII-containing signed PDFs (via the download URL on the same page).

### Solution: UUID Verification Token

**Model change** (`admins/models.py::DigitalSignature`):
```python
verify_token = models.UUIDField(default=uuid.uuid4, unique=True)
```

Each `DigitalSignature` record receives a cryptographically random UUID at creation time. This token is the only way to access the verification page.

**URL** changed from `verify/<int:order_id>/` to `verify/<uuid:token>/`.

**View** (`customers/views.py::verify_receipt`) now looks up by `verify_token` instead of `order_id`. The integer order ID is never exposed in this public endpoint.

**PDF download link removed** from the public verification page. The verify page serves non-repudiation only (hash check + signature validation result). Authenticated customers download their signed PDF from the order detail page via the `serve_private_media` view.

**Token distribution**: The verify token URL is generated in `order_success.html` using `{% url 'verify_receipt' verify_token %}` and passed from the `order_success` view context. The customer receives this URL in their order confirmation page (and should be included in the post-signing email).

### Files Changed
- `admins/models.py` — `verify_token` field added to `DigitalSignature`
- `admins/migrations/0031_digitalsignature_verify_token.py` — migration
- `customers/views.py::verify_receipt` — lookup changed to `verify_token`
- `customers/urls.py` — URL pattern changed to `<uuid:token>`
- `customers/views.py::order_success` — `verify_token` added to context
- `templates/customers/order_success.html` — verify link uses token, PDF download uses `serve_private_media`
- `templates/customers/verify_receipt.html` — PDF download link removed

---

## 4. Audit Log (Immutable, Hash-Chained)

Every sensitive action is recorded in `admins/models.py::AuditLog` with:
- Actor (user FK), action_type, target model/ID, description, IP address, user agent
- `chain_hash`: SHA-256 of this entry's content chained with the previous entry's hash — provides tamper-evidence without a database trigger

The audit log viewer (`/dashboard/audit-log/`) is sudo-gated (15-minute step-up required).

**Action types registered in ACTION_CHOICES** (as of migration 0029):
All action_type values passed to `log_audit()` must be registered in `AuditLog.ACTION_CHOICES`. Using an unregistered type silently saves to DB but hides the event from the filter UI. Check the choices list before adding new audit calls.

---

## 5. Rate Limiting

Implemented via `django-ratelimit` on all public-facing and sensitive views:

| Endpoint | Limit | Key |
|---|---|---|
| Login | 10/min | IP |
| Order submission | (see view) | User |
| Payment proof upload | (see view) | User |
| Campaign send | (see view) | User |
| Sudo confirm | 5/min | User |
| Receipt verification | 20/min | IP |
| Support chat | 30/min | User |

---

## 6. Content Security Policy

Django CSP middleware (`zarlyOs.middleware.EagerNonceCSPMiddleware`) injects a per-request nonce into `script-src`. All inline `<script>` tags in templates must use `{{ request.csp_nonce }}`.

Settings in `zarlyOs/settings.py`:
```python
CSP_SCRIPT_SRC = ("'self'", "https://cdn.jsdelivr.net", "https://unpkg.com")
CSP_INCLUDE_NONCE_IN = ["script-src"]
```

Note: `https://unpkg.com` is broadly trusted. Scope to specific package versions if possible.

---

## 7. Digital Signatures on Invoices

Approved orders receive a PKCS#7 digital signature (PyHanko) on the PDF invoice:
- `DigitalSignature.signature_hash` — SHA-256 of the signed PDF at time of creation
- `DigitalSignature.signature_value` — PKCS#7 hex representation
- `DigitalSignature.verify_token` — UUID for the public verification URL

The public verification endpoint (`/menu/verify/<uuid:token>/`) recomputes the SHA-256 and re-validates the PyHanko signature on each verification request (result cached 24h).

---

## 8. PDPA Compliance Notes

- Email campaigns enforce opt-in: only customers with `marketing_opt_in=True` receive emails
- Campaign sends are rate-limited and logged under `campaign_sent` audit action
- Payment proof images are private (Vuln 1 fix) — no longer publicly accessible
- Customers can delete their own account via `/menu/account/delete/` with OTP confirmation
- All support chat messages are Fernet-encrypted at rest (`FERNET_KEY` in `.env.prod`)

---

---

## 9. How to Demo & Test Each Security Feature

All tests below assume the dev server is running (`python manage.py runserver`) with at least one manager account, one sales_admin account, and one customer account seeded in the DB.

---

### 9.1 Role-Based Access Control

**What to verify:** a customer cannot reach admin pages; a sales_admin cannot reach manager-only pages.

```
# As a logged-in customer, visit an admin-only URL
GET /dashboard/                      → redirected to product list (not 403)
GET /dashboard/inventory/            → redirected to product list

# As a sales_admin, visit a manager-only URL
GET /dashboard/analytics/            → "You don't have permission" redirect
GET /dashboard/add-product/          → "You don't have permission" redirect

# As a manager
GET /dashboard/analytics/            → 200 OK
```

---

### 9.2 Step-Up Authentication (Sudo)

**What to verify:** sensitive views require a second password even when already logged in as manager.

```
# Log in as manager, then visit directly:
GET /dashboard/audit-log/            → redirected to /dashboard/sudo/confirm/
GET /dashboard/refunds/              → redirected to /dashboard/sudo/confirm/

# POST correct password to sudo confirm → granted 15-min window
# Visit audit-log again within 15 min  → 200 OK (no re-prompt)
# Wait 15 min OR manually clear session key 'sudo_expires_at' → re-prompts
```

To manually expire sudo in the shell:
```python
# In Django shell
from django.contrib.sessions.backends.db import SessionStore
s = SessionStore(session_key='<your session key from cookie>')
del s['sudo_expires_at']
s.save()
```

---

### 9.3 Rate Limiting

**What to verify:** repeated requests are blocked at defined thresholds.

```bash
# Login rate limit (10/min per IP)
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/login/ \
    -d "username=wrong&password=wrong&csrfmiddlewaretoken=..." \
    -H "Cookie: csrftoken=..."
done
# Requests 11+ return 200 with "Too many login attempts" message (django-ratelimit block=False returns 200, not 429)

# Sudo confirm rate limit (5/min per user)
# POST wrong password 6 times as manager → "Too many attempts" message on 6th
```

---

### 9.4 Private Media Serving (IDOR Prevention)

**What to verify:** payment proofs, signed PDFs, and complaint evidence cannot be accessed without authentication and ownership.

```bash
# 1. Upload a payment proof as a customer, note the order ID
# 2. Try to fetch the file URL directly (unauthenticated):
curl http://localhost:8000/media/payment_proofs/20260522-ORDER42.jpg
# → 403 Forbidden (nginx blocks /media/payment_proofs/ directly)

# 3. Via Django's serve_private_media view:
curl http://localhost:8000/files/payment_proofs/20260522-ORDER42.jpg
# → 302 to login (unauthenticated)

# 4. Log in as a DIFFERENT customer → GET the same URL
# → 403 Forbidden (ownership check fails)

# 5. Log in as the OWNING customer → GET the same URL
# → 200 OK, file served via X-Accel-Redirect

# 6. Log in as sales_admin → GET any payment proof URL
# → 200 OK (staff bypass)
```

In development (without nginx), the `X-Accel-Redirect` header won't proxy — Django falls back to serving the file directly. To test the nginx layer, run docker-compose and hit port 80.

---

### 9.5 Receipt Verification (UUID Token, No IDOR)

**What to verify:** receipt verification requires the UUID token, not a guessable integer order ID.

```bash
# Old-style integer URL (should 404)
GET /menu/verify/42/                 → 404

# Correct UUID URL (from order_success page)
GET /menu/verify/3f2504e0-4f89-11d3-9a0c-0305e82c3301/   → 200, shows signature status

# Try a random UUID
GET /menu/verify/00000000-0000-0000-0000-000000000001/   → 404

# Tamper test: open signed PDF in hex editor, change 1 byte, re-upload manually
# Then visit verify URL → "Signature invalid" (hash mismatch)
```

---

### 9.6 Audit Log & Hash Chain Integrity

**What to verify:** every action is logged; tampering is detectable.

```
# 1. Log in as manager with sudo → visit /dashboard/audit-log/
#    → All actions appear in reverse-chronological order
#    → "Chain valid" badge shows green

# 2. In Django shell, tamper with one entry:
from admins.models import AuditLog
entry = AuditLog.objects.order_by('id')[5]
entry.description = "TAMPERED"
entry.save()  # bypasses chain logic (chain_hash not recomputed)

# 3. Reload audit-log page → "Chain broken at ID X" warning banner
```

```python
# Verify chain programmatically
from admins.models import AuditLog
valid, broken_at = AuditLog.verify_chain()
print(valid, broken_at)
```

---

### 9.7 Support Chat Encryption

**What to verify:** messages are stored as Fernet ciphertext, not plaintext.

```python
# In Django shell
from admins.models import SupportMessage
msg = SupportMessage.objects.last()
print(msg.body)          # → "gAAAAAB..." (Fernet ciphertext)

from admins.chat_crypto import decrypt_message
print(decrypt_message(msg.body))   # → actual message text

# Verify deletion is blocked
msg.delete()             # → raises PermissionError
SupportMessage.objects.all().delete()  # → raises PermissionError
```

---

### 9.8 Digital Signature on Invoices

**What to verify:** approving an order generates a signed PDF and the verify endpoint reports valid.

```
1. Create or find a pending order with confirmed payment
2. As sales_admin, click Approve → order moves to 'approved'
3. Check DigitalSignature record created:
   python manage.py shell -c "from admins.models import DigitalSignature; print(DigitalSignature.objects.last().__dict__)"
4. Visit the verify URL shown on the order success page:
   GET /menu/verify/<uuid>/   → "Signature valid ✓"
5. Download the signed PDF and confirm it has a visible signature field in a PDF viewer
```

---

### 9.9 CSP Nonce

**What to verify:** injected `<script>` tags without the nonce are blocked by the browser.

```
1. Open any admin page in Chrome DevTools → Network → response headers
   → Look for Content-Security-Policy: script-src 'self' ... 'nonce-xxxxx'

2. In browser console, inject a script tag:
   var s = document.createElement('script');
   s.textContent = "alert('xss')";
   document.body.appendChild(s);
   → CSP blocks it, DevTools console shows "Refused to execute inline script"

3. Verify all <script> tags in admin templates carry nonce="{{ request.csp_nonce }}"
   grep -r "<script" templates/admins/ | grep -v "nonce="
   → Should return empty (all scripts have nonce)
```

---

### 9.10 PDPA — Email Opt-Out & Account Deletion

**What to verify:** opted-out customers are skipped in campaigns; account deletion works with OTP.

```
# Email opt-out
1. As manager, go to CRM → select an opted-out customer → Send Campaign
   → EmailLog for that customer shows status='skipped', reason='Customer opted out'

# Account deletion
1. Log in as customer → /menu/account/delete/
   → OTP sent to registered email
2. Enter OTP → account deactivated, session terminated, redirect to home
3. Attempt login with same credentials → fails (account inactive)
```

---

### 9.11 Known Vulnerability — Stored XSS in Email Template Preview

**Status: Open (not yet fixed)**

**To reproduce (requires manager account):**
```
1. Log in as manager → /dashboard/email-templates/new/
2. In the Body field, enter:
   <img src=x onerror="alert('XSS: '+document.cookie)">
3. Save the template
4. Any manager who opens this template for editing will trigger the alert on page load
```

**Fix:** Add DOMPurify to `email_template_form.html` and `campaign_compose.html`:
```html
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"
        nonce="{{ request.csp_nonce }}"></script>
```
Then change `updatePreview` to:
```js
function updatePreview(html) {
    document.getElementById('previewPane').innerHTML =
        DOMPurify.sanitize(html) || '<span class="text-muted">Start typing…</span>';
}
```

---

*Last updated: 2026-05-22*
