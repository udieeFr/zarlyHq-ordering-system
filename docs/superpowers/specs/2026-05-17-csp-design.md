# Content Security Policy (CSP) — Design Spec

**Date:** 2026-05-17
**Approach:** Nonce-based CSP via `django-csp`

---

## Problem

ZarlyHQ has no `Content-Security-Policy` header. Without one, a successful XSS injection (e.g., a stored payload in a complaint message, order note, or product name) could load and execute arbitrary JavaScript from any origin — exfiltrating session cookies, forging requests, or hijacking admin sessions. CSP is the browser-enforced last line of defence.

---

## Approach: Nonce-based CSP (Option B)

`django-csp` middleware generates a cryptographically random nonce on every request and injects it into the `Content-Security-Policy` header as `'nonce-<value>'` in `script-src`. Only `<script>` tags carrying that exact nonce value will execute. Inline scripts without a nonce are blocked — even if an attacker manages to inject a `<script>` tag into the HTML.

**Why not `'unsafe-inline'` for scripts:** `'unsafe-inline'` disables the core XSS protection of CSP entirely. An attacker who finds an XSS hole can still run arbitrary code. Nonces make injected scripts inert.

**Why `'unsafe-inline'` is acceptable for styles:** CSS injection is dangerous but far harder to weaponise (no direct code execution, no cookie access). The app has 38 inline script blocks but also hundreds of `style=` HTML attributes which cannot be nonced — so `style-src` needs `'unsafe-inline'` anyway. Restricting external style origins (Google Fonts, Bootstrap CDN) still provides real value.

---

## CSP Directives

| Directive | Value | Reason |
|---|---|---|
| `default-src` | `'self'` | Catch-all fallback |
| `script-src` | `'self' 'nonce-{n}' cdn.jsdelivr.net unpkg.com` | Bootstrap JS + Chart.js (jsdelivr), Leaflet (unpkg) |
| `style-src` | `'self' 'unsafe-inline' cdn.jsdelivr.net unpkg.com fonts.googleapis.com` | Bootstrap CSS (jsdelivr), Leaflet CSS (unpkg), Google Fonts |
| `font-src` | `'self' fonts.gstatic.com` | Google Font files |
| `img-src` | `'self' data: blob:` | Uploaded images (same-origin), data URIs in code, blob for Leaflet tiles |
| `connect-src` | `'self'` | All AJAX is same-origin |
| `frame-ancestors` | `'none'` | Redundant with X-Frame-Options: DENY but explicit |
| `object-src` | `'none'` | No Flash / plugins |
| `base-uri` | `'self'` | Prevents `<base>` tag hijacking |
| `form-action` | `'self'` | Forms submit to same origin; Stripe redirect is server-side |

**Not needed:** `js.stripe.com` — Stripe is a server-side redirect, no Stripe.js embedded.

---

## External Resources Inventory

| Origin | Currently used for |
|---|---|
| `cdn.jsdelivr.net` | Bootstrap 5 CSS + JS (django-bootstrap5 default), Chart.js |
| `unpkg.com` | Leaflet CSS + JS (checkout map) |
| `fonts.googleapis.com` | Google Fonts CSS @import (product_list, home, customer_orders, sales_admin_dashboard) |
| `fonts.gstatic.com` | Google Font binary files |

---

## Inline Script Inventory

38 inline `<script>` blocks across 35 templates — all need `nonce="{{ request.csp_nonce }}"` added to the opening tag.

**Base templates (inherited by all pages):**
- `base.html` — 3 blocks (user dropdown, toast auto-dismiss, profile modal)
- `admin_base.html` — 1 block (toast auto-dismiss)

**Customer templates:**
- `customers/cart.html`, `customers/checkout.html` (3 blocks), `customers/complaint_detail.html`
- `customers/customer_orders.html`, `customers/customer_profile.html`, `customers/customer_support.html` (2 blocks)
- `customers/awaiting_payment.html`, `customers/favourites.html`, `customers/order_success.html`, `customers/product_list.html`

**Admin templates:**
- `admins/add_product.html`, `admins/admin_create_order.html`, `admins/admin_profile.html`
- `admins/approved_orders.html`, `admins/campaign_compose.html`, `admins/complaint_detail.html`
- `admins/customers_crm.html`, `admins/delivery_orders.html`, `admins/edit_product.html`
- `admins/email_template_form.html`, `admins/inventory.html`, `admins/manager_dashboard.html`
- `admins/manager_profile.html`, `admins/manage_categories.html`, `admins/order_detail.html`
- `admins/pending_payment_orders.html`, `admins/prepared_orders.html`, `admins/refund_list.html`
- `admins/sales_admin_dashboard.html`, `admins/sales_report.html`

---

## Package

`django-csp==3.8` — stable, widely deployed, simple `CSP_*` settings API, nonce via `request.csp_nonce`.

---

## Settings Changes (`zarlyOs/settings.py`)

```python
# CONTENT SECURITY POLICY
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC  = ("'self'", "https://cdn.jsdelivr.net", "https://unpkg.com")
CSP_STYLE_SRC   = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://unpkg.com", "https://fonts.googleapis.com")
CSP_FONT_SRC    = ("'self'", "https://fonts.gstatic.com")
CSP_IMG_SRC     = ("'self'", "data:", "blob:")
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_OBJECT_SRC  = ("'none'",)
CSP_BASE_URI    = ("'self'",)
CSP_FORM_ACTION = ("'self'",)
CSP_INCLUDE_NONCE_IN = ["script-src"]
```

Middleware (add after `SecurityMiddleware`):
```python
'csp.middleware.CSPMiddleware',
```

---

## Template Changes

Every `<script>` opening tag becomes:
```html
<script nonce="{{ request.csp_nonce }}">
```

Single-line scripts:
```html
<script nonce="{{ request.csp_nonce }}">const SAVED = null;</script>
```

External scripts (already have `src=`) — add nonce if served from allowlisted CDN. Actually, external scripts from allowlisted origins do NOT need nonces — the origin allowlist covers them. Only inline scripts need nonces.

---

## Tests (`tests/test_csp.py`)

1. **`test_csp_header_present`** — GET login page (no auth), assert `Content-Security-Policy` header exists.
2. **`test_csp_no_unsafe_inline_in_script_src`** — Parse script-src, assert `'unsafe-inline'` is absent.
3. **`test_csp_nonce_in_script_src`** — Assert `nonce-` appears in script-src directive.
4. **`test_csp_cdn_origins_in_script_src`** — Assert `cdn.jsdelivr.net` and `unpkg.com` are in script-src.
5. **`test_csp_google_fonts_in_style_src`** — Assert `fonts.googleapis.com` in style-src.
6. **`test_csp_font_src_gstatic`** — Assert `fonts.gstatic.com` in font-src.
7. **`test_csp_object_src_none`** — Assert `object-src 'none'`.
8. **`test_csp_frame_ancestors_none`** — Assert `frame-ancestors 'none'`.
9. **`test_csp_base_uri_self`** — Assert `base-uri 'self'`.
10. **`test_csp_form_action_self`** — Assert `form-action 'self'`.
11. **`test_csp_nonce_rendered_in_base_template`** — GET authenticated customer page, check rendered HTML contains `nonce=` on script tags.
12. **`test_csp_nonce_unique_per_request`** — Make two requests, extract nonces, assert they differ.

---

## Documentation Updates

After implementation, two files are updated:

**`docs/security_implementation.md`** — Add §9 covering:
- What CSP is and what directive does what
- Why nonces (not `'unsafe-inline'`) for script-src
- What attack it prevents (stored XSS walkthrough)
- How to test it yourself (browser DevTools steps + manual XSS simulation)

**`docs/features_and_security_updates.md`** — Add §5 entry for CSP implementation.

---

## Scope Boundaries

**In scope:**
- Install package, configure settings, middleware
- Nonce all 38 inline script tags
- Tests (12 assertions)
- Security doc update

**Out of scope:**
- Moving inline styles to CSS classes (would eliminate `'unsafe-inline'` from style-src — separate refactor)
- CSP reporting endpoint (would need a server to receive violation reports)
- `'strict-dynamic'` (future upgrade path once nonces are stable)
