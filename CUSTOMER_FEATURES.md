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
| Product reviews / ratings | ❌ | Customers cannot rate or review individual products yet |

---

## 3. Cart

| Feature | Status | Notes |
|---|---|---|
| Add to cart | ⚠️ | AJAX instant badge update — ⚠️ unguarded `int()` on quantity input crashes with 500 if non-integer sent (see Security §3) |
| View cart | ✅ | Full cart page with item list and order summary |
| Update item quantity | ⚠️ | +/- buttons per item — same `int()` crash risk as above |
| Remove item | ✅ | Remove button per item |
| Cart item count badge | ✅ | Live in navbar and sidebar |
| Cart persistence on login | ❌ | Session cart is lost when an anonymous user logs in — not merged |

---

## 4. Checkout & Order Placement

| Feature | Status | Notes |
|---|---|---|
| Delivery address form | ✅ | Full address fields with interactive map pin |
| Delivery map geocoding | ⚠️ | Leaflet map loads but Nominatim geocoding is blocked by CSP `connect-src` — address search/reverse geocoding silently fails in production (see Security §6) |
| Order notes | ✅ | Free-text field for special requests |
| Submit order | ✅ | Creates order atomically with `SELECT FOR UPDATE` stock check |
| Promo / voucher codes | ❌ | No discount code field at checkout yet |
| Saved delivery addresses | 📋 | Auto-fill from previous orders — in todo |
| Estimated delivery time | ❌ | No ETA shown after placing order |

---

## 5. Payment

| Feature | Status | Notes |
|---|---|---|
| Stripe card payment | ✅ | Redirects to Stripe Checkout; webhook auto-confirms with signature verification |
| Manual bank transfer / DuitNow | ✅ | Customer uploads proof image; admin reviews manually |
| Awaiting payment list | ✅ | Dedicated page listing all orders pending payment |
| Payment proof upload | ⚠️ | File type + Pillow verification for images — ⚠️ PDFs bypass content inspection (see Security §4) |
| Replay attack protection | ✅ | Blocks manual proof upload if Stripe already succeeded |
| Bank / QR payment details | ⚠️ | Placeholder account numbers still in `payment_utils.py` — not production-ready |

---

## 6. Order Management

| Feature | Status | Notes |
|---|---|---|
| Order history | ✅ | Tabs: Unpaid / Upcoming (active) / Previous (completed/rejected) |
| Order statistics | ✅ | Total orders, total spent, avg order value, favourite item |
| Cancel order | ✅ | Pending-only; restores stock; triggers Stripe refund if applicable |
| Re-order | ✅ | One-click button — repopulates cart, skips out-of-stock items |
| Order status tracking | ✅ | Status label on each order card |
| Visual status timeline | ❌ | Step-by-step progress indicator not yet built |
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
| Post-delivery rating | 📋 | 1–5 stars + optional comment after delivery — in todo |

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

### 🔴 Security issues — must fix before shipping

| # | Issue | Location | Impact |
|---|---|---|---|
| 1 | **Stored XSS in chat bubbles** — `msg.body` injected via `innerHTML` with no escaping | `templates/customers/complaint_detail.html`, `customer_support.html` | Malicious message executes JS in recipient's browser; escalates to admin takeover |
| 2 | **Missing `@customer_required`** — staff accounts can place orders, submit complaints, approve their own orders | `customers/views.py` (all views) | Privilege abuse / self-dealing; `@customer_required` exists in `auth_utils.py` but is never applied |
| 3 | **Unguarded `int()` on `quantity` input** — raises unhandled `ValueError` → 500 with debug stack trace | `customers/views.py:342`, `:386` | With `DEBUG=True` leaks DB config; in production breaks AJAX silently |

### 🟡 Security issues — fix before production

| # | Issue | Location | Impact |
|---|---|---|---|
| 4 | **PDF upload skips content inspection** — only checks extension, not magic bytes | `customers/payment_utils.py:199` | HTML/JS disguised as `.pdf` served to admin browser → XSS |
| 5 | **`AUTH_PASSWORD_VALIDATORS` disabled** — only 8-char minimum enforced | `zarlyOs/settings.py:103–116` | Trivial passwords (`password`, `12345678`) accepted |
| 6 | **Nominatim geocoding blocked by CSP** — `connect-src` missing `nominatim.openstreetmap.org` | `zarlyOs/settings.py:215` | Checkout address map silently broken in all production browsers |

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
| Account & Profile | 3 | 1 | 0 | 0 |
| Menu & Discovery | 5 | 0 | 0 | 1 |
| Cart | 3 | 2 | 0 | 1 |
| Checkout | 2 | 1 | 1 | 2 |
| Payment | 3 | 2 | 0 | 0 |
| Order Management | 6 | 0 | 0 | 1 |
| Loyalty | 4 | 0 | 1 | 0 |
| Notifications | 5 | 0 | 0 | 0 |
| Support | 3 | 1 | 0 | 0 |
| **Total** | **34** | **7** | **2** | **5** |

---

## Not Yet Implemented — Quick Reference

- **Cart persistence on login** — merge session cart when anonymous user authenticates
- **Product reviews** — rate and comment on items after delivery
- **Visual order timeline** — step-by-step status progress indicator
- **Promo / voucher codes** — discount code field at checkout
- **Estimated delivery time** — ETA displayed after order approval

## Security — Fix Priority Order

1. `[ ]` Fix stored XSS in chat (`innerHTML` → `textContent`) — **ship blocker**
2. `[ ]` Apply `@customer_required` to all customer views — **ship blocker**
3. `[ ]` Wrap `int(quantity)` in try/except in `add_to_cart` and `update_cart`
4. `[ ]` Add PDF magic-byte check + force `Content-Disposition: attachment` on uploads
5. `[ ]` Uncomment `AUTH_PASSWORD_VALIDATORS` + call `validate_password()` in profile view
6. `[ ]` Add `nominatim.openstreetmap.org` and `unpkg.com` to `CSP_CONNECT_SRC`
7. `[ ]` Set `ALLOWED_HOSTS`, enable HTTPS cookie flags before any production deploy
8. `[ ]` Replace placeholder bank details in `payment_utils.py`
