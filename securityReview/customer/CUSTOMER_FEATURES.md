# Customer Features Reference
> Use this as a build tracker and future user guide base.
> Status: ✅ Built | ⚠️ Built with issues | 📋 Planned (in todo) | ❌ Not yet implemented
>
> **Last reviewed:** 2026-05-18 — security + functionality audit complete. See `5/18customerreview.md` for full findings.

---

## 1. Account & Profile

| Feature | Status | Notes |
|---|---|---|
| Login / Logout | ✅ | Standard auth with audit logging |
| Edit Profile (popup modal) | ✅ | First/last name, email, phone, default address, marketing opt-in |
| Change Password | ✅ | Implemented in `customer_profile` view with current-password verification and `update_session_auth_hash` — ⚠️ no strength validation (see Security §5) |
| Marketing email opt-in/out | ✅ | Toggle inside Edit Profile modal |

---

## 2. Menu & Product Discovery

| Feature | Status | Notes |
|---|---|---|
| Browse full menu | ✅ | Product grid with images, price, stock status |
| Filter by category | ✅ | Category pills at top + dropdown in filter bar |
| Filter by allergy | ✅ | Dropdown hides products containing selected allergen |
| Hide Sold Out toggle | ✅ | Button in filter bar; state persists across filters |
| AJAX grid updates | ✅ | Filters and pagination update the grid without full page reload |
| Pagination | ✅ | Page links inside the AJAX grid |
| Product reviews / ratings | ✅ | `ProductReview` model; submit via `/product/<id>/review/` after a delivered order; one review per product per order |

---

## 3. Cart

| Feature | Status | Notes |
|---|---|---|
| Add to cart | ✅ | AJAX instant badge update; `int()` guarded with try/except, capped at 99 |
| View cart | ✅ | Full cart page with item list and order summary |
| Update item quantity | ✅ | +/- buttons per item; guarded quantity input |
| Remove item | ✅ | Remove button per item |
| Cart item count badge | ✅ | Live in navbar and sidebar |
| Cart persistence on login | ✅ | Pre-login session cart merged into authenticated session on login — `unified_login` in `admins/views.py` |

---

## 4. Checkout & Order Placement

| Feature | Status | Notes |
|---|---|---|
| Delivery address form | ✅ | Full address fields with interactive map pin |
| Delivery map geocoding | ✅ | Nominatim added to `CSP_CONNECT_SRC`; geocoding works in production |
| Order notes | ✅ | Free-text field for special requests |
| Submit order | ✅ | Creates order atomically with `SELECT FOR UPDATE` stock check |
| Promo / voucher codes | ❌ | Not yet implemented |
| Saved delivery addresses | 📋 | Auto-fill from previous orders — in todo |
| Estimated delivery time | ❌ | Not yet implemented |

---

## 5. Payment

| Feature | Status | Notes |
|---|---|---|
| Stripe card payment | ✅ | Redirects to Stripe Checkout; webhook auto-confirms with signature verification |
| Manual bank transfer / DuitNow | ✅ | Customer uploads proof image; admin reviews manually |
| Awaiting payment list | ✅ | Dedicated page listing all orders pending payment |
| Payment proof upload | ✅ | File type + Pillow + PDF magic-byte (`%PDF`) check |
| Replay attack protection | ✅ | Blocks manual proof upload if Stripe already succeeded |
| Bank / QR payment details | ✅ | Config moved to env vars (`DUITNOW_MERCHANT_ID`, `BANK_ACCOUNT_NUMBER`) in `payment_utils.py` |

---

## 6. Order Management

| Feature | Status | Notes |
|---|---|---|
| Order history | ✅ | Tabs: Unpaid / Upcoming (active) / Previous (completed/rejected) |
| Order statistics | ✅ | Total orders, total spent, avg order value, favourite item |
| Cancel order | ✅ | Pending-only; restores stock; triggers Stripe refund if applicable |
| Re-order | ✅ | One-click button — repopulates cart, skips out-of-stock items |
| Order status tracking | ✅ | Status label on each order card |
| Visual status timeline | ❌ | Not yet implemented |
| Download invoice (PDF) | ✅ | Digitally signed PDF, available once order is approved |
| Receipt verification | ✅ | Customer verifies digital signature at `/verify/<order_id>/` |
| Rejected orders list | ✅ | Separate page with rejection reason |

---

## 7. Loyalty Program

| Feature | Status | Notes |
|---|---|---|
| Loyalty tier | ✅ | Bronze → Silver (RM 500) → Gold (RM 2,000) → Platinum (RM 5,000) |
| Tier progress bar | ✅ | Shows % progress and RM remaining to next tier |
| VIP badge | ✅ | Gold pill badge assigned by manager, visible on My Orders |
| Lifetime stats | ✅ | Total orders, total spent, avg order value, favourite item |
| Post-delivery rating | ✅ | `OrderRating` model; 1–5 stars + optional comment; rate button on delivered orders (`/order/<id>/rate/`) |

---

## 8. Notifications

| Feature | Status | Notes |
|---|---|---|
| In-app notification bell | ✅ | Bell icon in navbar with unread count badge |
| Notifications list | ✅ | Full list of system notifications |
| Mark all as read | ✅ | Button on notifications page |
| Open-redirect protection | ✅ | `url_has_allowed_host_and_scheme` used on notification click-through |
| Email notifications | ✅ | Sent on key events (order approved, rejected, prepared) |

---

## 9. Support & Complaints

| Feature | Status | Notes |
|---|---|---|
| Submit complaint | ✅ | Form with subject + message + evidence image, linked to completed orders only |
| Support page | ✅ | Accessible from sidebar |
| Complaint status tracking | ✅ | Pending/Resolved pill shown on complaint cards and detail page — *(was incorrectly marked ❌ in old doc)* |
| Support chat (encrypted) | ⚠️ | Fernet-encrypted messages, 1-min polling, Page Visibility API — ⚠️ **stored XSS vulnerability in chat bubbles** (see Security §1) |

---

## 10. Security

> Security features that protect the customer side. See `5/18customerreview.md` for full exploitability details.

### ✅ Implemented and correct

| Feature | Notes |
|---|---|
| IDOR protection | All views filter by `customer=request.user` — customers cannot access other customers' orders, complaints, or messages |
| CSRF protection | Django CSRF middleware active; only Stripe webhook is `@csrf_exempt` (correct) |
| Stripe webhook signature verification | `stripe.Webhook.construct_event` used — replay/forgery attacks blocked |
| Fernet encryption on chat messages | Messages encrypted at rest and in transit between DB and templates |
| AuditLog with SHA-256 hash chain | Key customer actions logged; chain tamper-detectable |
| SupportMessage immutability | `delete()` blocked at model + queryset level; FK changed to `PROTECT` — non-repudiation enforced |
| CSP headers with per-request nonce | Content-Security-Policy applied on all pages |
| `X-Frame-Options: DENY` | Clickjacking protection |
| `X-Content-Type-Options: nosniff` | MIME-type sniffing protection |
| Open-redirect protection on notifications | `url_has_allowed_host_and_scheme` check |
| Stock atomicity | `SELECT FOR UPDATE` prevents oversell on concurrent orders |

### ✅ Security issues fixed on 2026-05-18

| # | Issue | Location | Status |
|---|---|---|---|
| 1 | **Stored XSS in chat bubbles** — `innerHTML` → safe `textContent` DOM construction | `templates/customers/complaint_detail.html`, `customer_support.html`, `admins/complaint_detail.html` | ✅ Fixed |
| 2 | **Missing `@customer_required`** — all customer views now use `@customer_required`; `logout_view` keeps `@login_required` | `customers/views.py` | ✅ Fixed |
| 3 | **Unguarded `int()` on `quantity` input** — wrapped in try/except, defaults to 1/0 on bad input | `customers/views.py:342`, `:386` | ✅ Fixed |
| 4 | **PDF upload skips content inspection** — magic-byte check (`%PDF`) added | `customers/payment_utils.py` | ✅ Fixed |
| 5 | **`AUTH_PASSWORD_VALIDATORS` disabled** — validators uncommented; `validate_password()` called in profile view | `zarlyOs/settings.py`, `customers/views.py` | ✅ Fixed |
| 6 | **Nominatim geocoding blocked by CSP** — `nominatim.openstreetmap.org` and `unpkg.com` added to `connect-src` | `zarlyOs/settings.py` | ✅ Fixed |

### ⚙️ Pre-production config — not vulnerabilities, but required before deploy

| Item | Status |
|---|---|
| `ALLOWED_HOSTS` set | ❌ Currently `[]` |
| `SESSION_COOKIE_SECURE = True` | ❌ Commented out |
| `CSRF_COOKIE_SECURE = True` | ❌ Commented out |
| `SECURE_SSL_REDIRECT = True` | ❌ Commented out |
| Bank / QR placeholder details replaced | ❌ Still `0123456789` / `123456789012` |

---

## Summary

| Category | ✅ Built | ⚠️ Issues | 📋 Planned | ❌ Not Yet |
|---|---|---|---|---|
| Account & Profile | 4 | 0 | 0 | 0 |
| Menu & Discovery | 6 | 0 | 0 | 0 |
| Cart | 6 | 0 | 0 | 0 |
| Checkout | 3 | 0 | 1 | 2 |
| Payment | 5 | 0 | 0 | 0 |
| Order Management | 6 | 0 | 0 | 1 |
| Loyalty | 5 | 0 | 0 | 0 |
| Notifications | 5 | 0 | 0 | 0 |
| Support | 4 | 0 | 0 | 0 |
| **Total** | **44** | **0** | **1** | **3** |

---

## Not Yet Implemented — Quick Reference

- **Visual order timeline** — step-by-step status progress indicator
- **Promo / voucher codes** — discount code field at checkout
- **Estimated delivery time** — ETA displayed after order approval
- **Saved delivery addresses** — auto-fill from previous orders at checkout (partially done via last-order auto-fill)

## Functionality — Fix Progress (2026-05-18)

1. `[x]` Cart persistence on login — session cart merged in `unified_login` ✅ 2026-05-18
2. `[x]` Product reviews / ratings — `ProductReview` model + view at `/product/<id>/review/` ✅ 2026-05-18
3. `[ ]` Visual order timeline — reverted
4. `[ ]` Promo / voucher codes — reverted
5. `[ ]` Estimated delivery time — reverted
6. `[x]` Post-delivery order rating — `OrderRating` model + view at `/order/<id>/rate/` ✅ 2026-05-18
7. `[x]` Bank payment config → env vars — `payment_utils.py` reads `DUITNOW_MERCHANT_ID`, `BANK_ACCOUNT_NUMBER` ✅ 2026-05-18

## Security — Fix Progress

1. `[x]` Fix stored XSS in chat (`innerHTML` → `textContent`) ✅ 2026-05-18
2. `[x]` Apply `@customer_required` to all customer views ✅ 2026-05-18
3. `[x]` Wrap `int(quantity)` in try/except in `add_to_cart` and `update_cart` ✅ 2026-05-18
4. `[x]` Add PDF magic-byte check on uploads ✅ 2026-05-18
5. `[x]` Uncomment `AUTH_PASSWORD_VALIDATORS` + call `validate_password()` in profile view ✅ 2026-05-18
6. `[x]` Add `nominatim.openstreetmap.org` + `unpkg.com` to `CSP_CONNECT_SRC` ✅ 2026-05-18
7. `[ ]` Set `ALLOWED_HOSTS`, enable HTTPS cookie flags before production deploy
