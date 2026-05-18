# ZarlyHQ — Features & Security Updates

This document tracks features implemented and planned, alongside their security design.
Companion to `security_implementation.md`.

---

## 1. Database Performance Improvements (Implemented — 2026-05-17)

### Indexes Added
- **Order**: `status`, `(status, created_at DESC)`, `(customer, created_at DESC)`, `(is_priority, status)`
- **Complaint**: `status`, `(order, status)`
- **Refund**: `(order, created_at DESC)`, `(status, created_at DESC)`
- **Payment**: removed redundant explicit index on `stripe_session_id` (`unique=True` already covers it)
- **User.role**: `db_index=True`
- **Product.is_available**: `db_index=True`

### Bug Fixes
- `CustomerProfile.recalculate()` — replaced Python iteration over all orders with a single `aggregate(Sum, Count, Max)` call. Previously loaded every completed order into memory.
- `PrepGroup.item_summary` — added `prefetch_related('items__product')` to eliminate N+1 queries (was firing 1 + N DB queries per call).
- `PrepGroup.save()` — fixed lexicographic ordering bug on `group_id` string sort. Sequential IDs above 9 (e.g. `OP-260517-10`) were generated out of order. Fixed by ordering on `-id` (PK) instead of `-group_id`.

### Migrations
- `admins/migrations/0023_db_indexes_and_perf.py`
- `customers/migrations/0011_db_indexes_and_perf.py`

### CI/CD Test Coverage
- `tests/test_database_performance.py` — 35 tests covering query counts, index declarations, AuditLog chain integrity, PrepGroup seq IDs, Notification unread count.

---

## 2. Support Chat — Encrypted Complaint Thread (Planned)

### Purpose
Allow customers and sales admins to exchange messages within an active complaint, replacing back-channel communication (WhatsApp, email) with an in-app auditable thread.

### Agreed Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Delivery mechanism | Short polling (1 req/min) | Zero infrastructure cost; acceptable latency for support context |
| Polling trigger | Page Visibility API only | Pauses automatically when tab is hidden/backgrounded |
| Encryption | Fernet symmetric (at rest) | Simple, auditable, no key exchange needed — server holds key in env var |
| Scope | Per-complaint thread | Chat is tied to a specific `Complaint` record |
| Customer entry point | New page: `/support/complaint/<id>/` | Customers currently have no complaint detail page |
| Admin entry point | Existing `admins/complaint_detail.html` | Add chat panel to the existing page |

### Security Design
- Messages stored as **Fernet-encrypted ciphertext** in the DB — unreadable without the server key
- **Access control**: only `complaint.customer` or a `sales_admin`/`manager` can read/write
- All messages logged to **AuditLog** (`action_type='support_message_sent'`)
- Chat **locked** (read-only) once complaint status = `resolved`
- Encryption key stored in Django `settings.py` env var (`SUPPORT_CHAT_KEY`), never committed

### Planned Model

```python
class SupportMessage(models.Model):
    complaint   = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='messages')
    sender      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    body        = models.TextField()          # Fernet-encrypted ciphertext
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read     = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']
        indexes  = [
            models.Index(fields=['complaint', 'created_at']),
        ]
```

### Planned Endpoints

| Method | URL | Purpose |
|---|---|---|
| GET | `/support/complaint/<id>/` | Customer complaint detail + chat thread |
| GET | `/support/complaint/<id>/messages/?since=<ts>` | Polling endpoint — returns new messages as JSON |
| POST | `/support/complaint/<id>/messages/` | Send a message |
| GET | `/dashboard/complaints/<id>/messages/?since=<ts>` | Admin polling endpoint |

### Planned JS (polling loop)
```javascript
// Pause when tab is hidden, resume on focus — avoids wasted queries
let pollTimer;
function startPolling() {
    pollTimer = setInterval(fetchNewMessages, 60000); // 1 req/min
}
document.addEventListener('visibilitychange', () => {
    document.hidden ? clearInterval(pollTimer) : startPolling();
});
startPolling();
```

### What Is NOT in Scope
- Real-time delivery (WebSockets / SSE) — deliberately excluded; 1 min latency is acceptable
- File attachments in chat — complaint already has `evidence_image`; no extra uploads in chat
- Chat between admins — this is customer↔admin only
- End-to-end encryption — server-side Fernet is sufficient; E2E would require key exchange complexity

---

## 3. AuditLog Hash Chain (Implemented — prior session)

Every `AuditLog` row computes a SHA-256 of its own content chained with the previous row's hash. Deleting or altering any row breaks every subsequent hash, detectable via `AuditLog.verify_chain()`.

- Write serialised through `select_for_update()` — one lock per insert, acceptable at current scale
- `verify_chain()` tested in `tests/test_database_performance.py::TestAuditLogChain`

---

## 4. Digital Signature on Orders (Implemented — prior session)

`DigitalSignature` model stores a SHA-256 hash + signed PDF path per order. Created when order reaches `delivered` status. Supports receipt verification by customers.

---

## 5. Content Security Policy — Nonce-Based (Implemented — 2026-05-18)

### What Was Built
- `django-csp==3.8` installed; `EagerNonceCSPMiddleware` (subclass of `CSPMiddleware`) added to `MIDDLEWARE` via `zarlyOs/middleware.py`
- `CSP_*` settings in `zarlyOs/settings.py` configure all directives
- `CSP_INCLUDE_NONCE_IN = ["script-src"]` enables per-request nonce generation
- 38 inline `<script>` blocks across 35 templates updated with `nonce="{{ request.csp_nonce }}"`
- `'unsafe-inline'` absent from `script-src` — injected scripts are blocked
- External origins whitelisted: `cdn.jsdelivr.net`, `unpkg.com`, `fonts.googleapis.com`, `fonts.gstatic.com`
- 13 automated tests in `tests/test_csp.py`

### Security Design
- Nonces are cryptographically random, per-request — attacker cannot predict them
- `EagerNonceCSPMiddleware` forces nonce evaluation on every request so the header always carries a nonce (workaround for django-csp 3.x lazy evaluation)
- `style-src` uses `'unsafe-inline'` (pragmatic — hundreds of `style=` attributes; CSS injection is lower risk)
- `frame-ancestors 'none'` redundant with `X-Frame-Options: DENY` but explicit in CSP
- `form-action 'self'` prevents form hijacking; Stripe redirect is server-side only
