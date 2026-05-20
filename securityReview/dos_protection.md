# DoS Protection — Risk Register & Recommendations

**Scope:** `zarlyOs/settings.py`, `customers/views.py`, `admins/views.py`, infrastructure layer  
**Date:** 2026-05-20

---

## Layer 1 — Django Settings (fix in code now)

### DS-1 — `DATA_UPLOAD_MAX_NUMBER_FIELDS` Not Set ✅ Fixed
**Fixed: 2026-05-20**
**Risk: High** | **Effort: 1 line**

Django's default allows **1,000 POST fields** per request. An attacker can craft a single POST body with 999 fields and tie up a Gunicorn worker parsing it — no authentication required on any form endpoint.

```python
# zarlyOs/settings.py
DATA_UPLOAD_MAX_MEMORY_SIZE  = 5 * 1024 * 1024   # 5 MB  (matches proof cap)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100               # default 1000 → parser-flood risk
FILE_UPLOAD_MAX_MEMORY_SIZE  = 5 * 1024 * 1024   # 5 MB
```

---

### DS-2 — No `CONN_MAX_AGE` (PostgreSQL connection pooling) ✅ Fixed
**Fixed: 2026-05-20**
**Risk: Medium** | **Effort: 1 line**

Without connection reuse, each request opens and closes a DB connection. Under moderate load this can exhaust PostgreSQL's `max_connections`. `CONN_MAX_AGE = 60` keeps connections alive per worker, roughly equivalent to having PgBouncer at the app level.

```python
DATABASES = {
    'default': {
        ...
        'CONN_MAX_AGE': 60,   # reuse connections for 60 s per Gunicorn worker
    }
}
```

---

## Layer 2 — Infrastructure (outside codebase)

These require changes to your server config, not Django code.

### DS-3 — No Network-Level DoS Shield ⬜ Open
**Risk: Critical for volumetric attacks** | **Effort: 30 min**

`django-ratelimit` only fires after a request reaches a Gunicorn worker. A volumetric flood (thousands of requests/sec) exhausts your workers before any rate limit can trigger. **Cloudflare free tier** absorbs L3/L4 and basic L7 attacks entirely outside your server.

### DS-4 — Gunicorn Worker Timeout Not Configured ⬜ Open
**Risk: High** | **Effort: Config change**

Without `--timeout`, a single hung worker (e.g., a PyHanko call blocked on I/O) holds that slot permanently. Recommended flags:

```
gunicorn zarlyOs.wsgi:application \
  --workers 4 \
  --timeout 30 \
  --max-requests 1000 \
  --max-requests-jitter 100
```

`--max-requests` recycles workers after N requests, preventing slow memory leaks from accumulating over time.

### DS-5 — No Nginx Request-Level Gate ⬜ Open
**Risk: High** | **Effort: Config change**

Nginx can drop requests before they reach Django, costing microseconds vs. a full Django worker slot:

```nginx
limit_req_zone $binary_remote_addr zone=zarly:10m rate=30r/s;

server {
    client_max_body_size 6m;   # match 5 MB proof cap + overhead

    location / {
        limit_req zone=zarly burst=60 nodelay;
        proxy_pass http://127.0.0.1:8000;
    }
}
```

### DS-6 — PostgreSQL `statement_timeout` Not Set ⬜ Open
**Risk: Medium** | **Effort: 1 SQL command**

A runaway query holds a DB connection open for its full duration, blocking other requests. Set a server-side timeout:

```sql
ALTER ROLE zarly_user SET statement_timeout = '10s';
```

---

## Layer 3 — Application Findings (customer app)

### DS-7 — `verify_receipt` Runs PyHanko Synchronously on Every Request ✅ Fixed
**Fixed: 2026-05-20**
**Risk: Medium** | **Effort: Low (cache) / Medium (async)**

`verify_receipt` (`customers/views.py:1170`) is a **public, unauthenticated** endpoint that:
1. Reads a PDF from disk
2. Computes SHA-256 over the full file
3. Calls `validate_pdf_signature` (PyHanko) — CPU-intensive, ~100–300 ms per call

The result is **immutable** — a signed receipt never changes. Running all three steps on every request is wasteful and makes this the cheapest CPU-amplification point in the app despite the 20/min IP rate limit.

**Fix:** Cache the verification result keyed by `order_id`:

```python
from django.core.cache import cache

VERIFY_CACHE_TTL = 60 * 60 * 24  # 24 hours — result never changes

@ratelimit(key='ip', rate='20/m', block=False)
def verify_receipt(request, order_id):
    if getattr(request, 'limited', False):
        ...
    cache_key = f'receipt_verify:{order_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return render(request, 'customers/verify_receipt.html', cached)
    # ... full verification logic ...
    cache.set(cache_key, result, VERIFY_CACHE_TTL)
    return render(request, 'customers/verify_receipt.html', result)
```

---

### DS-8 — `customer_orders` Fetches Unbounded Order History ✅ Fixed
**Fixed: 2026-05-20**
**Risk: Low–Medium** | **Effort: Low**

`customer_orders` (`customers/views.py:984`) runs three unbounded queries on every page load:

```python
unpaid_orders   = Order.objects.filter(...).order_by('-created_at')       # no limit
upcoming_orders = Order.objects.filter(...).order_by('-created_at')       # no limit
previous_orders = Order.objects.filter(...).order_by('-created_at')       # no limit
```

A customer with hundreds of orders drives all three queries to full table scans on every visit. The `OrderItem.prefetch_related` compounds this — it fetches all items for all orders, potentially thousands of rows.

**Fix:** Slice `previous_orders` (historical orders are the only unbounded category in practice):

```python
previous_orders = Order.objects.filter(
    customer=request.user, status__in=previous_statuses
).prefetch_related('items__product').order_by('-created_at')[:50]
```

---

### DS-9 — `customer_support` Fetches All Complaints Without a Limit ✅ Fixed
**Fixed: 2026-05-20**
**Risk: Low** | **Effort: Low**

```python
complaints = Complaint.objects.filter(customer=request.user).select_related('order').order_by('-created_at')
```

No upper bound. Unlikely to be large for food-order customers, but trivial to cap:

```python
complaints = Complaint.objects.filter(customer=request.user).select_related('order').order_by('-created_at')[:100]
```

---

### DS-10 — `download_invoice` Calls `generate_invoice_pdf` Synchronously 🟡 Open
**Risk: Low–Medium** | **Effort: Medium (async)**

`download_invoice` (`customers/views.py:225`) generates a PDF on every request. Rate-limited to 20/hr per user which significantly reduces risk. However the PDF is generated from scratch each time; it could be generated once and served from storage instead.

Short-term: the 20/hr rate limit is sufficient. Long-term: cache or store the generated PDF.

---

## Layer 4 — Application Findings (admin app)

### DS-11 — `bulk_accept_orders` Calls PyHanko in a Loop 🟡 Partial Fix
**Partially fixed: 2026-05-20** — batch capped at 20 orders server-side. Full fix requires Celery.
**Risk: Medium** | **Effort: High (Celery)**

`bulk_accept_orders` (`admins/views.py:1465`) loops over selected orders and calls `finalize_order_approval()` (PyHanko PDF signing) synchronously for each one. Accepting 10 orders = 10 sequential PyHanko calls in a single request, easily consuming 3–5 seconds and holding a Gunicorn worker for the full duration.

This is the highest-risk synchronous CPU operation in the app. The 10/min rate limit reduces it, but a legitimate admin accepting a large batch still blocks a worker.

**Fix (short-term):** Cap the batch size server-side:
```python
order_ids = request.POST.getlist('order_ids')[:20]   # hard cap at 20 per batch
```

**Fix (long-term):** Offload `finalize_order_approval` to a Celery task; return immediately with a "processing" status that polls for completion.

---

### DS-12 — Product Image Upload Has No Explicit Size Validation ✅ Fixed
**Fixed: 2026-05-20**
**Risk: Low–Medium** | **Effort: Low**

`add_product` and `edit_product` accept `request.FILES['image']` with no size check before calling `product.save()`. Django's `FILE_UPLOAD_MAX_MEMORY_SIZE` (default 2.5 MB) acts as a soft limit, but without an explicit check the behavior depends on the server config. The payment proof endpoint has a hard 5 MB cap + magic bytes; product images have neither.

**Fix:**
```python
if request.FILES.get('image'):
    img = request.FILES['image']
    if img.size > 5 * 1024 * 1024:
        messages.error(request, 'Image must be under 5 MB.')
        return redirect('inventory_list')
    product.image = img
```

---

## Summary

| ID | Finding | Layer | Risk | Status |
|---|---|---|---|---|
| DS-1 | `DATA_UPLOAD_MAX_NUMBER_FIELDS` not set | Django settings | High | ✅ Fixed |
| DS-2 | No `CONN_MAX_AGE` | Django settings | Medium | ✅ Fixed |
| DS-3 | No network-level DoS shield (Cloudflare) | Infrastructure | Critical | ⬜ Open |
| DS-4 | Gunicorn `--timeout` not configured | Infrastructure | High | ⬜ Open |
| DS-5 | No Nginx `limit_req_zone` | Infrastructure | High | ⬜ Open |
| DS-6 | No PostgreSQL `statement_timeout` | Infrastructure | Medium | ⬜ Open |
| DS-7 | `verify_receipt` — sync PyHanko, no result cache | Customer app | Medium | ✅ Fixed |
| DS-8 | `customer_orders` — unbounded `previous_orders` query | Customer app | Low–Medium | ✅ Fixed |
| DS-9 | `customer_support` — unbounded complaints fetch | Customer app | Low | ✅ Fixed |
| DS-10 | `download_invoice` — PDF generated from scratch each time | Customer app | Low–Medium | 🟡 Open |
| DS-11 | `bulk_accept_orders` — PyHanko called in a loop | Admin app | Medium | 🟡 Partial |
| DS-12 | Product image upload — no size cap | Admin app | Low–Medium | ✅ Fixed |

## Fix Priority Order

**Do immediately (code changes, 1–2 lines each):**
1. `[x]` DS-1 — Set `DATA_UPLOAD_MAX_NUMBER_FIELDS = 100` in `settings.py` ✅ 2026-05-20
2. `[x]` DS-2 — Set `CONN_MAX_AGE = 60` in `DATABASES` config ✅ 2026-05-20
3. `[x]` DS-8 — Slice `previous_orders[:50]` in `customer_orders` ✅ 2026-05-20
4. `[x]` DS-9 — Slice `complaints[:100]` in `customer_support` ✅ 2026-05-20
5. `[x]` DS-12 — Add 5 MB size check to `add_product` and `edit_product` ✅ 2026-05-20

**Fix before production (moderate effort):**
6. `[ ]` DS-3 — Enable Cloudflare (free tier, 30 min)
7. `[ ]` DS-4 — Add Gunicorn `--timeout 30 --max-requests 1000 --max-requests-jitter 100`
8. `[ ]` DS-5 — Add Nginx `limit_req_zone` + `client_max_body_size 6m`
9. `[ ]` DS-6 — Set PostgreSQL `statement_timeout = '10s'`
10. `[x]` DS-7 — Cache `verify_receipt` result in Redis keyed by `order_id` ✅ 2026-05-20
11. `[x]` DS-11 — Cap `bulk_accept_orders` batch at 20 server-side ✅ 2026-05-20

**Longer-term:**
12. `[ ]` DS-11 — Move `finalize_order_approval` to Celery for true async signing
13. `[ ]` DS-10 — Store generated invoices on first creation; serve from storage
