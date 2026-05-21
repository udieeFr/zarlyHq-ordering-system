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

*Last updated: 2026-05-22*
