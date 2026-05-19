# Admin & Manager Module — Security Review

**Scope:** `admins/views.py`, `admins/models.py`, `admins/middleware.py`,
`admins/sudo.py`, `admins/notifications.py`, `admins/refund_utils.py`,
`customers/auth_utils.py`, `templates/admins/**`

**Original date:** 2026-05-19
**Reviewed by:** Security audit — branch `main` (9 commits ahead of origin)

---

## Part 1 — Implemented Security Features

### Role-Based Access Control
- `@sales_admin_required` — allows `role in ['sales_admin', 'manager']` + superuser
- `@manager_required` — allows `role == 'manager'` + superuser only
- Applied consistently across all admin views:
  - Order management (approve/reject/prepare/deliver): `@sales_admin_required`
  - Inventory add/edit/delete: `@manager_required`
  - Analytics dashboard: `@manager_required`
  - Support chat (admin side): `@sales_admin_required`
  - Audit log: `@manager_required`
- Privilege boundary enforced: a sales_admin cannot access manager-only views (inventory write, analytics, audit log, refund management, VIP toggle)

### Step-Up Authentication (Sudo Mode)
- `@sudo_required` decorator in `admins/sudo.py`
- Re-prompts for password on sensitive operations; grants a 15-minute window
- Session-stored expiry timestamp (`sudo_expires_at`)
- Failed step-up attempts logged to AuditLog

### Login Security
- Rate limit: 10 POST requests per minute per IP on `unified_login` via `django-ratelimit`
- Failed attempts logged to AuditLog (`login_failed`)
- Successful logins logged to AuditLog (`login_success`)
- Role-based redirect after login (customers → product list, staff → dashboard)

### CSRF Protection
- Django CSRF middleware active globally
- All admin state-change forms include `{% csrf_token %}`
- Exceptions: none — all admin forms are POST

### Audit Log Integrity
- `AuditLog` with SHA-256 hash chain: each entry hashes `(timestamp + actor + action + description + previous_hash)`
- `AuditLog.verify_chain()` detects tampering; result surfaced on the audit log page
- `chain_hash` is `readonly_fields` in Django admin
- Actions logged: order lifecycle, payment events, product mutations (add/edit/delete/toggle), complaint resolution, login/logout, step-up auth, refund events, tracking updates

### SupportMessage Immutability
- `_ImmutableQuerySet.delete()` raises `PermissionError` — bulk delete blocked at ORM level
- `SupportMessage.delete()` raises `PermissionError` — single-instance delete blocked
- FK `on_delete=PROTECT` — deleting a Complaint with messages raises `ProtectedError`
- Admin chat messages are Fernet-encrypted at rest; key stored in `SUPPORT_CHAT_KEY` env var

### Payment Proof Handling (Admin Side)
- On rejection: `proof_image.delete(save=False)` removes file from storage before clearing the DB field, preventing orphaned files
- Storage deletion failure isolated with try/except — does not abort the rejection flow
- Deterministic file naming (`YYYYMMDD-ORDER{id}.{ext}`) prevents path traversal via filename

### File Upload Security
- Payment proof extension allowlist: jpg, jpeg, png, pdf
- Magic-byte validation for all types
- `PIL.Image.verify()` for JPEG/PNG integrity

### Session Management
- `SESSION_COOKIE_HTTPONLY = True` — JS cannot read session cookie
- `CSRF_COOKIE_HTTPONLY = True` — JS cannot read CSRF cookie
- `update_session_auth_hash()` called after password change to preserve session

### HTTP Security Headers
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- CSP with per-request nonce (`django-csp`)

### Product Image Upload (Manager)
- Product images uploaded via `request.FILES` — Django handles multipart parsing
- No magic-byte validation on product images (lower risk: images served publicly, not used as payment proof)

### Rate Limiting (Admin/Manager)
Applied via `django-ratelimit`:
| View | Limit | Key |
|---|---|---|
| `unified_login` | 10/min | IP |
| `sudo_confirm` | 5/min | user |
| `admin_profile` / `manager_profile` | 10/hr | user |
| `approve_order` / `reject_order` | 60/min | user |
| `approve_pending_payment` / `reject_pending_payment` | 60/min | user |
| `bulk_accept_orders` / `bulk_reject_orders` | 10/min | user |
| `mark_orders_prepared` / `mark_prep_group_ready` | 30/min | user |
| `mark_order_out_for_delivery` / `mark_order_delivered` | 60/min | user |
| `update_order_tracking` | 30/min | user |
| `force_approve_unpaid` | 30/min | user |
| `resolve_complaint` | 30/min | user |
| `admin_complaint_messages` (POST) | 30/min | user |
| `add_product` / `delete_product` | 10/min | user |
| `edit_product` | 20/min | user |
| `manage_categories` | 20/min | user |
| `stage_stock_update` | 120/min | user |
| `confirm_stock_changes` / `clear_stock_staging` | 10/min | user |
| `toggle_product_availability` | 60/min | user |
| `toggle_order_priority` | 60/min | user |
| `toggle_customer_vip` | 30/min | user |
| `admin_create_order` | 20/min | user |
| `save_internal_note` | 30/min | user |
| `mark_refund_processed` | 20/min | user |
| `customer_crm_detail` (POST) | 20/min | user |
| `email_template_create` / `email_template_delete` | 10/min | user |
| `email_template_edit` | 20/min | user |
| `campaign_compose` | 3/hr | user |

### SQL Injection
- Django ORM used exclusively across all admin/manager views — no raw SQL

### PageView Analytics (New)
- `PageViewMiddleware` records path, session key, IP, user for GET 200 responses
- Wrapped in `try/except` — analytics failure never disrupts requests
- IP read from `X-Forwarded-For` header (first entry) for proxy-aware deployments
- Analytics data only; no security decisions made on recorded IP

---

## Part 2 — Security Issues

Severity: **Critical** > **High** > **Medium** > **Low**
Status: ✅ Fixed | 🔴 Open — ship blocker | 🟡 Open — fix before production | ⬜ Open — low priority

---

### HIGH

#### A1 — GET-Based CSRF on Order Approval Views ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-19** | **Confidence: 8/10**

`approve_order` (`admins/views.py:1466`) and `approve_pending_payment` (`admins/views.py:892`) both perform full, irreversible state transitions on any HTTP method — including GET — with no method guard.

`finalize_order_approval` (called from both views) writes a `DigitalSignature` record, generates a signed PDF invoice, sets `order.status = 'approved'`, sends a customer notification, and updates the CRM loyalty profile. This cannot be undone.

**Exploit scenario:**
1. Attacker guesses or knows an order ID (sequential integers)
2. Sends the authenticated sales admin a phishing link or embeds `<img src="/admins/approve-order/1337/">` in an email/chat
3. Admin's browser fetches the URL while their session is active
4. Django's CSRF middleware does not block GET requests — the approval executes silently
5. Order transitions to `approved`, signed PDF committed, customer notified — without the admin consciously clicking Approve

Compare with `reject_order` (`admins/views.py:1498`) which correctly guards: `if request.method != 'POST': return redirect(...)`.

**Files:** `admins/views.py:892` (`approve_pending_payment`), `admins/views.py:1466` (`approve_order`)

**Fix:** Add a POST method guard to both views:
```python
@sales_admin_required
def approve_pending_payment(request, order_id):
    if request.method != 'POST':
        return redirect('pending_payment_orders_list')
    order = get_object_or_404(Order, id=order_id, status='pending_payment')
    ...

@sales_admin_required
def approve_order(request, order_id):
    if request.method != 'POST':
        return redirect('sales_admin_dashboard')
    order = get_object_or_404(Order, id=order_id)
    ...
```
Or equivalently: add `@require_http_methods(['POST'])` and wrap the template "Approve" buttons in `<form method="post">` if they are currently plain `<a>` links.

---

### MEDIUM

#### A2 — Admin/Manager Password Change Skips `validate_password()` ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-20**

`admin_profile` (`admins/views.py:2277`) and `manager_profile` (`admins/views.py:2333`) both check only `len(new_pw) < 8`. The customer-facing profile view was updated in this branch to call `validate_password(new_pw, user)`, but the admin-side equivalents were not updated.

Weak passwords like `password1`, `aaaaaaaa`, or `12345678` are accepted for admin accounts — accounts with full access to approve orders, manage inventory, and view all customer data.

**Fix:**
```python
# In admin_profile and manager_profile change_password blocks:
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
try:
    validate_password(new_pw, user)
except DjangoValidationError as e:
    for msg in e.messages:
        messages.error(request, msg)
    show_pw_form = True
else:
    user.set_password(new_pw)
    user.save()
    update_session_auth_hash(request, user)
    messages.success(request, 'Password changed successfully.')
    return redirect('admin_profile')  # or 'manager_profile'
```

---

#### A3 — Error Detail Disclosure in `approve_order` ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-20**

`approve_order` at line 1480 passes the raw exception message directly to the user:
```python
except Exception as e:
    messages.error(request, f"Error signing document: {str(e)}")
```

If PDF signing fails (file system error, library exception, etc.), the exception string may contain internal paths, stack frames, or library internals visible to the sales admin.

**Fix:**
```python
except Exception as e:
    logger.error("Document signing failed for order %s: %s", order.id, e, exc_info=True)
    messages.error(request, "Failed to sign the invoice. Please try again or contact support.")
```

---

#### A4 — No Rate Limiting on Admin Password Change ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-20**

`admin_profile` and `manager_profile` now have `@ratelimit(key='user', rate='10/h', method='POST', block=False)`. All other admin/manager endpoints also rate-limited in the same pass.

---

### LOW

#### A5 — `bulk_reject_orders` Uses `print()` for Error Logging ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-20**

Several `except` clauses in `bulk_reject_orders` use `print(f"Error notifying customer: {e}")` instead of `logger.error(...)`. Print output goes to stdout and may be lost in production; structured logging is needed.

**Fix:** Replace `print(...)` with `logger.error(...)` or `logger.warning(...)`.

---

#### A6 — `toggle_customer_vip` Returns No Response on Manager_required Check ✅ Fixed
**Complexity: Low** | **Found: 2026-05-19** | **Fixed: 2026-05-20**

Added `return JsonResponse({'is_vip': profile.is_vip})` at the end of `toggle_customer_vip`, matching the pattern of `toggle_product_availability`.

---

## Summary Table

| ID | Title | Severity | Complexity | Status |
|---|---|---|---|---|
| A1 | GET-based CSRF on order approval views | High | Low | ✅ Fixed 2026-05-19 |
| A2 | Admin/manager password change skips `validate_password()` | Medium | Low | ✅ Fixed 2026-05-20 |
| A3 | Error detail disclosure in `approve_order` | Medium | Low | ✅ Fixed 2026-05-20 |
| A4 | No rate limit on admin password change | Low | Low | ✅ Fixed 2026-05-20 |
| A5 | `bulk_reject_orders` uses `print()` for errors | Low | Low | ✅ Fixed 2026-05-20 |
| A6 | `toggle_customer_vip` missing return statement | Low | Low | ✅ Fixed 2026-05-20 |

---

## Fix Priority Order

**Must fix before shipping:**
1. `[x]` A1 — POST method guard on `approve_order` and `approve_pending_payment` ✅ 2026-05-19

**Fix before production:**
2. `[x]` A2 — Call `validate_password()` in admin/manager profile password change ✅ 2026-05-20
3. `[x]` A3 — Generic error message for document signing failure ✅ 2026-05-20

**Lower priority:**
4. `[x]` A4 — Rate-limit admin/manager profile + all admin endpoints ✅ 2026-05-20
5. `[x]` A5 — Replace `print()` with structured logging ✅ 2026-05-20
6. `[x]` A6 — Add return statement to `toggle_customer_vip` ✅ 2026-05-20

---

## Security Architecture — Admin/Manager Threat Model

| Threat | Mitigation | Status |
|---|---|---|
| Unauthorized order approval/rejection | `@sales_admin_required` role check | ✅ |
| Sales admin accessing manager-only pages | `@manager_required` exclusively on inventory/analytics/audit | ✅ |
| GET-based CSRF triggering order approval | POST method guard on approval views | ✅ |
| Brute-force admin login | Rate limit 10/min per IP + audit log | ✅ |
| Privilege escalation via support chat | Chat is read/respond only; no state changes from chat | ✅ |
| Audit log tampering | SHA-256 hash chain; `chain_hash` readonly | ✅ |
| Support chat message deletion/modification | Immutable queryset + PROTECT FK | ✅ (`update(body=...)` not guarded) |
| Weak admin passwords | `validate_password()` enforced in admin/manager profile change | ✅ |
| Session fixation after step-up auth | `grant_sudo()` writes to existing session (no session rotation) | ⚠️ Low risk |
| Payment proof with malicious content | Extension allowlist + magic bytes + Pillow verify | ✅ |
| Orphaned payment proof files on rejection | `proof_image.delete(save=False)` before clearing field | ✅ |
| Product price/stock tampering by sales admin | Inventory write is `@manager_required` only | ✅ |
