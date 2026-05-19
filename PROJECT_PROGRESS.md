# ZarlyHQ — Project Progress by Role

**Last updated:** 2026-05-19
**Branch:** main (9 commits ahead of origin)

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ | Built and verified |
| ⚠️ | Built with known issues |
| 🔴 | Ship blocker — must fix before release |
| 🟡 | Fix before production |
| ❌ | Not yet implemented |
| 📋 | Planned / in backlog |

---

## Role 1 — Customer

### Account & Profile
| Feature | Status | Notes |
|---|---|---|
| Login / Logout | ✅ | Standard auth with audit logging, rate limit 10/min |
| Register | ❌ | No registration view — manual account creation only |
| Edit Profile (modal) | ✅ | First/last name, email, phone, default address, marketing opt-in |
| Change Password | ✅ | `validate_password()` now enforced via Django validators |
| Email verification on email change | ❌ | 🟡 No verification link sent — see H4 in security review |
| Marketing email opt-in/out | ✅ | Toggle inside Edit Profile modal |

### Menu & Product Discovery
| Feature | Status | Notes |
|---|---|---|
| Browse full menu | ✅ | Product grid with images, price, stock status |
| Filter by category | ✅ | Category pills + dropdown filter bar |
| Filter by allergy | ✅ | Dropdown hides products containing selected allergen |
| Hide Sold Out toggle | ✅ | Persists across filters |
| AJAX grid updates | ✅ | No full page reload |
| Pagination | ✅ | AJAX pagination inside grid |
| Product reviews / ratings | ✅ | `ProductReview` model; one review per product per order; delivered orders only |

### Cart
| Feature | Status | Notes |
|---|---|---|
| Add to cart | ✅ | AJAX badge update; quantity capped 1–99 with try/except guard |
| View cart | ✅ | Full cart page |
| Update / remove items | ✅ | +/- buttons; remove button |
| Cart item count badge | ✅ | Live in navbar |
| Cart persistence on login | ✅ | Pre-login anonymous cart merged into authenticated session on login |

### Checkout & Order Placement
| Feature | Status | Notes |
|---|---|---|
| Delivery address form | ✅ | Full address fields |
| Delivery map with geocoding | ✅ | Leaflet + Nominatim; CSP fixed to allow geocoding |
| Order notes | ✅ | Free-text field for special requests |
| Submit order (atomic) | ✅ | `SELECT FOR UPDATE` stock check prevents oversell |
| Promo / voucher codes | ❌ | Not implemented |
| Saved delivery addresses | 📋 | Last-order auto-fill partially done |
| Estimated delivery time | ❌ | Not implemented |
| Unbounded text field truncation | ✅ | Server-side slice on all address/notes fields — M6 fixed 2026-05-19 |
| Lat/lng bounds validation | ✅ | Coordinates bounds-checked against [-90,90] / [-180,180] — M7 fixed 2026-05-19 |

### Payment
| Feature | Status | Notes |
|---|---|---|
| Stripe card payment | ✅ | Stripe Checkout; webhook auto-confirms with HMAC signature |
| Manual bank transfer / DuitNow | ✅ | QR code generation; customer uploads proof image |
| Awaiting payment list | ✅ | Dedicated page listing all orders pending payment |
| Payment proof upload | ✅ | Extension allowlist + magic bytes + Pillow integrity check |
| Replay attack protection | ✅ | Blocks manual proof if Stripe already confirmed |
| Bank / QR config from env vars | ✅ | `DUITNOW_MERCHANT_ID`, `BANK_ACCOUNT_NUMBER`, etc. |
| Deterministic proof naming | ✅ | `YYYYMMDD-ORDER{id}.{ext}` — old file deleted on re-upload |
| Double-charge guard (reconnect) | ✅ | `start_stripe_payment` rejects if order already has a succeeded payment — NEW-5 |
| Checkout idempotency key | ✅ | One-time session key prevents duplicate orders on connection-drop retry — NEW-6 |
| Orphaned Stripe session cleanup | ✅ | Old pending sessions cancelled before new session is created — NEW-7 |

### Order Management
| Feature | Status | Notes |
|---|---|---|
| Order history | ✅ | Tabs: Unpaid / Upcoming / Previous |
| Order statistics | ✅ | Total orders, total spent, avg order value, favourite item |
| Cancel order | ✅ | Pending-only; restores stock; triggers Stripe refund |
| Re-order | ✅ | One-click — repopulates cart, skips out-of-stock |
| Order status tracking | ✅ | Status label on each order card |
| Visual order timeline | ❌ | Not implemented |
| Download invoice (PDF) | ✅ | Digitally signed PDF |
| Receipt verification | ⚠️ | 🟡 Public endpoint; customer data may be exposed — see M4 |
| Rejected orders list | ✅ | With rejection reason |
| Post-delivery order rating | ✅ | `OrderRating` model; 1–5 stars + optional comment |

### Loyalty Program
| Feature | Status | Notes |
|---|---|---|
| Loyalty tier (Bronze/Silver/Gold/Platinum) | ✅ | Thresholds: RM0/500/2000/5000 |
| Tier progress bar | ✅ | % and RM remaining to next tier |
| VIP badge | ✅ | Assigned by manager |
| Lifetime stats | ✅ | Total orders, spent, avg, favourite item |

### Notifications
| Feature | Status | Notes |
|---|---|---|
| In-app notification bell | ✅ | Unread count badge |
| Notifications list | ✅ | Newest first |
| Mark all as read | ✅ | |
| Open-redirect protection | ✅ | `url_has_allowed_host_and_scheme` check |

### Support & Complaints
| Feature | Status | Notes |
|---|---|---|
| Submit complaint | ✅ | Subject + message + evidence image; delivered orders only |
| Complaint status tracking | ✅ | Pending / Resolved pill |
| Encrypted support chat | ✅ | Fernet encryption; 1-min polling; Page Visibility API |
| Chat XSS prevention | ✅ | `textContent` DOM construction; no `innerHTML` on user data |
| SupportMessage immutability | ✅ | `delete()` blocked at model + queryset + DB (PROTECT) level |

### Security Summary — Customer
| Item | Status |
|---|---|
| IDOR protection | ✅ All views filter by `customer=request.user` |
| CSRF protection | ✅ Django CSRF active; only Stripe webhook is `@csrf_exempt` |
| Role enforcement | ✅ `@customer_required` on all protected views |
| SQL injection | ✅ ORM only |
| XSS — templates | ✅ Auto-escape active |
| XSS — chat bubbles | ✅ Fixed 2026-05-18 |
| File upload validation | ✅ Extension + magic bytes + Pillow |
| Password strength | ✅ Django validators + `validate_password()` |
| CSP headers | ✅ Per-request nonce; Nominatim in connect-src |
| HTTP security headers | ✅ DENY frame, nosniff, referrer-policy |
| Rate limiting | ✅ On all write endpoints |
| Stripe webhook integrity | ✅ HMAC-SHA256 |
| Audit logging | ✅ Key actions logged to hash-chained AuditLog |
| Double-charge on reconnect | ✅ Guard in `start_stripe_payment` |
| Duplicate order on retry | ✅ Session idempotency key in checkout |
| Email verification on email change | 🟡 Not implemented |
| verify_receipt data exposure | ✅ sig_record removed from context; error_detail removed — M4 fixed 2026-05-20 |
| Error detail disclosure | ✅ All str(e) replaced with generic messages + logger — M3/A3 fixed 2026-05-20 |

---

## Role 2 — Sales Admin

### Order Management
| Feature | Status | Notes |
|---|---|---|
| Sales admin dashboard | ✅ | Pending orders queue with search + filter |
| View order detail | ✅ | Full order with items, customer info, payment status |
| Approve order | ✅ | POST guard added; `<a>` links converted to `<form method="post">` |
| Reject order (single) | ✅ | POST-only with rejection reason; customer notified |
| Bulk reject orders | ✅ | Multi-select with refund processing |
| Approve pending payment | ✅ | POST guard added 2026-05-19 |
| Reject payment proof | ✅ | POST-only; old proof file deleted from storage |
| Mark order ready for delivery | ✅ | Status transition with prep group recording |
| Mark order out for delivery | ✅ | With tracking number update |
| Mark order delivered | ✅ | Final status; audit logged |
| Print order summary | ✅ | PDF print view |
| Order priority toggle | ✅ | AJAX POST-only; audit logged |

### Payment Verification
| Feature | Status | Notes |
|---|---|---|
| Pending payments list | ✅ | Sortable, searchable, filterable by days |
| Approve payment proof | ⚠️ | 🔴 Shared with approve order — GET-based CSRF |
| Reject payment proof | ✅ | POST-only; proof file deleted; customer notified |
| Manual payment proof review | ✅ | Image viewer in admin panel |

### Delivery Management
| Feature | Status | Notes |
|---|---|---|
| Delivery orders list | ✅ | Ready for delivery / out for delivery / delivered tabs |
| Update tracking number | ✅ | Audit logged |
| Bulk delivery status update | 📋 | Not implemented |

### Support
| Feature | Status | Notes |
|---|---|---|
| Support chat list | ✅ | Deduplicated by order; shows preview + unread count |
| Admin complaint detail + chat | ✅ | Fernet-decrypted; textContent DOM (no XSS) |
| Resolve complaint | ✅ | Actions: refund / remake / dismiss; customer notified |
| Complaint list view | ✅ | Filter by status |

### Prep Groups
| Feature | Status | Notes |
|---|---|---|
| Create prep group | ✅ | Groups orders prepared together |
| View prep groups | ✅ | |

### Profile
| Feature | Status | Notes |
|---|---|---|
| Edit profile (name, phone) | ✅ | |
| Change password | ⚠️ | 🟡 Only checks length ≥ 8; `validate_password()` not called — see A2 |
| Performance stats | ✅ | Approved / rejected counts this week and all-time |

### Security Summary — Sales Admin
| Item | Status |
|---|---|
| Role enforcement | ✅ `@sales_admin_required` on all views |
| CSRF on state-change forms | ✅ POST guard added on `approve_order`, `approve_pending_payment` |
| Login rate limiting | ✅ 10/min per IP |
| Step-up auth (sudo) | ✅ 15-min window, password re-confirm |
| Audit logging | ✅ All order lifecycle actions logged |
| Password strength | ✅ `validate_password()` enforced — A2 fixed 2026-05-20 |
| Rate limit on password change | ⬜ Not implemented |

---

## Role 3 — Manager

### Analytics Dashboard
| Feature | Status | Notes |
|---|---|---|
| Revenue (today / week / total) | ✅ | |
| Order counts and status distribution | ✅ | |
| Top products by revenue and volume | ✅ | |
| Category revenue breakdown | ✅ | |
| Customer CRM (tier distribution) | ✅ | Bronze/Silver/Gold/Platinum counts |
| Retention rate / repeat customers | ✅ | Repeat-customer % and weekly new/returning |
| Conversion rate | ✅ | Customers who placed ≥1 order / total customers |
| Refund summary | ✅ | Total refunds, count, rate; pending refunds widget |
| Page views analytics | ✅ | Today / this week; unique sessions; top 5 pages |

### Inventory Management
| Feature | Status | Notes |
|---|---|---|
| Product list | ✅ | With availability toggle (AJAX) |
| Add product | ✅ | Name, price, stock, category, allergies, image; audit logged |
| Edit product | ✅ | Before/after diff logged to AuditLog |
| Delete product | ✅ | Snapshot logged to AuditLog |
| Toggle availability | ✅ | AJAX POST-only; audit logged |
| Stock staging (bulk update) | ✅ | Stage changes before committing |
| Product image upload | ✅ | No magic-byte check (lower risk for public images) |

### Customer Management
| Feature | Status | Notes |
|---|---|---|
| Customer list | ✅ | |
| Customer detail | ✅ | Orders, loyalty tier, spending stats |
| VIP toggle | ⚠️ | Missing return statement — returns no JSON response — see A6 |
| Loyalty tier management | ✅ | Auto-calculated; manually overridable via Django admin |

### Email Campaigns
| Feature | Status | Notes |
|---|---|---|
| Email template management | ✅ | HTML templates stored in DB |
| Send campaign | ✅ | To all / filtered recipients; audit logged |
| Email log | ✅ | Per-recipient delivery status |

### Refund Management
| Feature | Status | Notes |
|---|---|---|
| Process Stripe refund | ✅ | Automatic on order cancellation / rejection |
| Manual refund flag | ✅ | Marks for manual processing |
| Refund list / pending refunds | ✅ | With source and status filter |

### Audit Log
| Feature | Status | Notes |
|---|---|---|
| View audit log | ✅ | Paginated (configurable page size 1–1000) |
| Filter by action type | ✅ | |
| Filter by actor / target / days | ✅ | |
| Full-text search | ✅ | |
| Chain integrity indicator | ✅ | SHA-256 hash chain; broken-at pointer displayed |

### Profile
| Feature | Status | Notes |
|---|---|---|
| Edit profile (name, phone) | ✅ | |
| Change password | ⚠️ | 🟡 Only checks length ≥ 8; `validate_password()` not called — see A2 |
| Performance stats | ✅ | Approved / rejected counts |

### Security Summary — Manager
| Item | Status |
|---|---|
| Role enforcement | ✅ `@manager_required` on analytics, inventory write, audit log |
| Separation from sales admin | ✅ Sales admins cannot access manager-only views |
| CSRF on approval views | ✅ POST guard added — A1 fixed 2026-05-19 |
| Inventory mutations | ✅ Before/after diff in AuditLog |
| Audit log tamper detection | ✅ SHA-256 hash chain |
| Password strength | ✅ `validate_password()` enforced — A2 fixed 2026-05-20 |

---

## Cross-Cutting Security Status

| Item | Status | Notes |
|---|---|---|
| Django ORM (no raw SQL) | ✅ | SQL injection not possible via application code |
| Auto-escaping in all templates | ✅ | XSS baseline protected |
| CSP with per-request nonce | ✅ | Inline scripts require nonce |
| HTTP security headers | ✅ | DENY/nosniff/referrer-policy |
| `ALLOWED_HOSTS` | 🔴 | Currently `[]` — must be set for production |
| `SESSION_COOKIE_SECURE` | 🔴 | Commented out — must be enabled for HTTPS |
| `CSRF_COOKIE_SECURE` | 🔴 | Commented out — must be enabled for HTTPS |
| `SECURE_SSL_REDIRECT` | 🔴 | Commented out — must be enabled for HTTPS |
| `SECURE_HSTS_SECONDS` | 🔴 | Commented out — must be enabled for HTTPS |
| `DEBUG = False` in production | ⚠️ | Controlled by `DEBUG` env var; confirm set to `False` |
| Cache backend (ratelimit) | ✅ | Redis via `django-redis` when `REDIS_URL` set; LocMemCache fallback for dev — fixed 2026-05-20 |
| DB query efficiency | ✅ | Cart batch fetch; dashboard status counts collapsed to 1 aggregate — fixed 2026-05-20 |
| SUPPORT_CHAT_KEY | ✅ | Read from env var; empty default raises Fernet error if missing |

---

## Pre-Production Checklist

Before deploying to production, the following must be completed:

### Ship Blockers (🔴)
- [x] `A1` — POST guard on `approve_order` and `approve_pending_payment` ✅ 2026-05-19
- [ ] Set `ALLOWED_HOSTS` to production domain
- [ ] Uncomment `SESSION_COOKIE_SECURE = True`
- [ ] Uncomment `CSRF_COOKIE_SECURE = True`
- [ ] Uncomment `SECURE_SSL_REDIRECT = True`
- [ ] Uncomment `SECURE_HSTS_SECONDS`
- [ ] Set all required environment variables (`SECRET_KEY`, `STRIPE_*`, `SUPPORT_CHAT_KEY`, `DUITNOW_*`, `BANK_*`, `DB_*`)

### Fix Before Production (🟡)
- [x] `A2` — Call `validate_password()` in admin + manager password change ✅ 2026-05-20
- [x] `A3` — Generic error message for document signing failure ✅ 2026-05-20
- [ ] `H4` — Email verification on email change (customer)
- [x] `M3` — Replace `str(e)` in user-facing error messages (customer + admin) ✅ 2026-05-20
- [x] `M4` — Audit `verify_receipt` template for PII exposure ✅ 2026-05-20
- [x] Replace `LocMemCache` with Redis for multi-worker deployment ✅ 2026-05-20

### Lower Priority (⬜)
- [ ] `M1` — Rate-limit customer password change
- [x] `M6` — Server-side max-length on address/notes fields ✅ 2026-05-19
- [x] `M7` — Bounds-check lat/lng coordinates ✅ 2026-05-19
- [ ] `A4` — Rate-limit admin password change
- [x] `A5` — Replace `print()` with `logger.error()` in bulk_reject_orders ✅ 2026-05-20
- [ ] `A6` — Add return statement to `toggle_customer_vip`
- [ ] `L1`/`L3` — Minor decorator cleanup (customer views)
