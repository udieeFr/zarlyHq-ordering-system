# Nonrepudiation Architecture for Order Workflow
**Date:** 2026-06-01
**Project:** ZarlyHQ — Final Year Project (Cybersecurity)
**Focus:** Two-party nonrepudiation covering customer order commitment and company approval signing

---

## 1. Problem Statement

The existing order workflow has a nonrepudiation gap on the **customer side**. When a customer submits an order, their intent is recorded only via a session-authenticated POST — there is no cryptographic commitment binding the customer's identity to the exact order contents. This means:

- A customer could later deny placing the order ("I never ordered that")
- A customer could claim the items or total were different from what they agreed to
- There is no artifact the company can produce to prove the customer actively confirmed the specific contents

The **company side** already uses a PKCS#7 digital signature (PyHanko) on the approved invoice PDF. However, it does not embed which admin approved the order, and the customer's commitment is absent from the signed document.

---

## 2. Security Theory Basis

This design implements a **two-party nonrepudiation model** grounded in ITU-T X.813 and RFC 2828:

| NR Property | Full Name | Party | Proves |
|---|---|---|---|
| NRO | Nonrepudiation of Origin | Customer | Customer cannot deny initiating this exact order |
| NRF | Nonrepudiation of Finalization | Company | Company cannot deny accepting and committing to the order |

### Why different mechanisms for each party?

**Customer uses OTP + commitment hash** because:
- Individual consumers do not hold PKI certificates — PKI infrastructure is institutionally complex and unsuitable for B2C end-users
- An OTP proves the person controlling the registered email address actively confirmed a specific action at a specific time
- The SHA-256 commitment hash is what makes it cryptographically meaningful — it binds the OTP confirmation to the exact order contents, not just to a login event
- Under Malaysia's Electronic Commerce Act 2006, OTP-based electronic acknowledgment constitutes a valid electronic signature for consumer transactions

**Company uses PKCS#7 digital signature** because:
- The company is an organization making a legally binding promise to fulfill the order
- A PKI signature with a certificate binds the institutional identity ("Zarly BigFood Sdn Bhd") to the document in a way verifiable by any third party without trusting the company's word
- Under Malaysia's Digital Signature Act 1997, a digital signature by a licensed entity carries legal weight for binding commercial commitments
- The approval is the moment the contract becomes binding — it requires a formal, non-repudiable instrument

The asymmetry is intentional and correct: the right tool for each party's threat model and technical capability.

---

## 3. Architecture Overview

```
CUSTOMER                          SERVER                         ADMIN
    │                                │                              │
    │── fills checkout ─────────────>│                              │
    │                                │ creates Order                │
    │                                │ (pending_confirmation)       │
    │                                │ computes commitment_hash     │
    │                                │ sends OTP email              │
    │<── OTP email (order summary) ──│                              │
    │                                │                              │
    │── enters OTP ─────────────────>│                              │
    │                                │ verifies OTP                 │
    │                                │ stamps customer_confirmed_at │
    │                                │ logs AuditLog (chained)      │
    │                                │ Order → pending              │
    │                                │──── notifies admin ─────────>│
    │                                │                              │
    │                                │<── admin approves ───────────│
    │                                │ generates PDF (with          │
    │                                │   admin identity +           │
    │                                │   customer commitment hash)  │
    │                                │ signs with PKCS#7 (PyHanko)  │
    │                                │ stores DigitalSignature      │
    │<── notification (verify URL) ──│                              │
```

---

## 4. Customer Commitment Flow (NRO)

### Step 1 — Order Staging (`submit_order`)

1. Customer submits checkout form
2. Order is created with status `pending_confirmation`
3. Commitment hash is computed server-side:
   ```
   commitment_hash = SHA-256(
       order_id | customer_id | items_json | total_amount | shipping_fee | address | ISO-timestamp
   )
   ```
   Where `items_json` is a deterministic JSON string sorted by `product_id`, containing `product_id`, `quantity`, `unit_price`, `is_bundle` for each item.
4. `Order.customer_commitment_hash` is stored immediately — locks in what the customer was shown
5. OTP generated via existing `otp_utils.generate_and_cache_otp()` and emailed with full order summary
6. Customer redirected to new order confirmation page showing order summary + OTP input

**Why hash before OTP, not after:** The hash is computed and stored at staging time so the order contents are locked before the customer is asked to confirm. If the hash were computed after OTP entry, a server-side attacker could modify order contents between the two steps.

### Step 2 — OTP Confirmation (`confirm_order`)

1. Customer enters OTP on the confirmation page
2. `verify_otp()` validates the code
3. On success:
   - `Order.customer_confirmed_at = timezone.now()`
   - `Order.status = 'pending'`
   - `log_audit('order_confirmed_by_customer', metadata={'commitment_hash': ..., 'ip': ..., 'user_agent': ...})`
   - `OrderEvent` created with status `pending`, actor = customer
   - Admin notification sent
4. On OTP failure: customer can retry (max 3 attempts, then order cancelled and stock restored)
5. On timeout (30 minutes unconfirmed): management command cancels the order and restores stock

### Commitment Hash Inputs

| Field | Source | Notes |
|---|---|---|
| `order_id` | `Order.id` | Ties hash to this specific DB record |
| `customer_id` | `request.user.id` | Ties hash to this identity |
| `items_json` | `OrderItem` records | Sorted by product_id, deterministic |
| `total_amount` | `Order.total_amount` | Includes shipping fee |
| `shipping_fee` | `Order.shipping_fee` | Separate for auditability |
| `address` | `Order.formatted_address` | Full delivery address |
| `timestamp` | `Order.created_at` (ISO 8601) | Prevents replay across orders |

---

## 5. Company Signing Flow (NRF)

The existing `finalize_order_approval` + `sign_pdf_digitally` is retained. The following additions are made:

### Admin Identity Embedded in PDF

Before signing, the invoice PDF includes a visible section:

```
Approved by: [admin username] ([role]) on [ISO timestamp UTC]
Customer confirmed: [customer_confirmed_at ISO timestamp UTC]
Customer commitment hash: [first 32 chars]...
```

This binds three things into one signed document: order contents, approving admin identity, and the customer's commitment hash. The signed PDF becomes the single artifact covering both parties' nonrepudiation.

### New AuditLog Action

```python
('order_confirmed_by_customer', 'Order Confirmed by Customer (OTP)'),
```

Written at Step 2 of the customer flow, before `finalize_order_approval` runs.

### Known Limitations (Documented, Not Fixed)

**Self-signed certificate:** `zarly_cert.pem` has no trusted CA chain. PyHanko validates the signature as cryptographically intact (`sig_status.intact = True`) but `sig_status.valid` will be False without a trusted root. The SHA-256 hash check is the primary integrity mechanism; the PKCS#7 layer provides the identity claim. Acceptable for FYP scope.

**No Trusted Timestamp Authority (TSA):** The signing timestamp is server-generated, not from an RFC 3161 TSA. A TSA would provide third-party attestation of when the signature was created, preventing backdating claims. Documented as a production hardening gap.

These limitations are acknowledged rather than hidden — demonstrating security maturity is more valuable than pretending they do not exist.

---

## 6. Data Model Changes

### `admins/models.py` — Order

```python
STATUS_CHOICES = (
    ('pending_confirmation', 'Pending Customer Confirmation'),  # NEW
    # ... existing statuses unchanged
)

customer_commitment_hash = models.CharField(max_length=64, blank=True, default='')
customer_confirmed_at    = models.DateTimeField(null=True, blank=True)
```

### `admins/models.py` — AuditLog ACTION_CHOICES

```python
('order_confirmed_by_customer', 'Order Confirmed by Customer (OTP)'),
```

### `DigitalSignature` — No changes

The existing `signature_hash`, `signature_value`, `verify_token`, and `timestamp` fields are sufficient. Admin identity and customer commitment hash are embedded in the PDF content rather than as additional DB columns.

### Migration

One migration covering:
- `customer_commitment_hash` CharField on Order
- `customer_confirmed_at` DateTimeField on Order

`STATUS_CHOICES` changes do not require a migration in Django (CharField choices are not enforced at the DB level).

---

## 7. Verification & Audit Trail

### Three Independent Evidence Layers

| Layer | Location | Covers | How to verify |
|---|---|---|---|
| `Order.customer_commitment_hash` | Database | Exact order contents at confirmation time | Recompute hash from DB records and compare |
| AuditLog entry `order_confirmed_by_customer` | Database, hash-chained | Customer IP, user agent, timestamp, hash | `AuditLog.verify_chain()` |
| Signed PDF | Filesystem + DigitalSignature | Order contents, admin identity, customer hash, PKCS#7 signature | `/menu/verify/<uuid>/` |

### Dispute Scenarios

**"Customer claims they never placed the order"**
Produce the AuditLog entry: customer's IP + user agent + timestamp + commitment_hash. OTP entry proves the registered email address was used to actively confirm the order.

**"Customer claims items or total were different"**
Recompute `SHA-256(order_id | customer_id | items_json | ...)` from current DB records. If it matches `Order.customer_commitment_hash`, the DB contents are exactly what was confirmed and have not been altered since.

**"Company claims they never approved the order"**
The signed PDF embeds the approving admin's username, role, and timestamp. `verify_receipt` recomputes the SHA-256 and validates the PyHanko signature. `sig_intact = True` proves the document is unmodified since signing.

**"Someone tampered with the audit log"**
`AuditLog.verify_chain()` walks every entry and recomputes each `chain_hash`. Returns `(False, broken_at_id)` identifying the tampered entry.

### Updated `verify_receipt` Page Display

```
✓ Signature intact       — PDF has not been modified since signing
✓ Hash match             — Stored hash matches computed hash of file
  Signed by:             Zarly BigFood Sdn Bhd
  Approved by:           ali_admin (sales_admin)
  Signed at:             2026-06-01 14:32 UTC
  Customer confirmed:    2026-06-01 14:10 UTC
  Commitment hash:       a3f9c1d2... (first 16 chars)
⚠ Certificate trust:    Self-signed — identity claim unverified by CA
```

---

## 8. Security Gap Summary

| Gap | Severity | Status |
|---|---|---|
| No customer-side cryptographic commitment at order submission | High | **Fixed by this design** |
| Admin identity not embedded in signed PDF | Medium | **Fixed by this design** |
| Self-signed certificate — no trusted CA chain | Medium | Documented known limitation |
| No Trusted Timestamp Authority for signing timestamp | Low | Documented known limitation |
| `signature_value` (PKCS#7 bytes) stored in DB but never used in verification | Low | Documented (not fixed — SHA-256 check is sufficient) |
| Private key stored on filesystem (`secure_keys/`) | Medium | Out of scope — production hardening |

---

## 9. Files to Change

| File | Change |
|---|---|
| `admins/models.py` | Add `pending_confirmation` status, `customer_commitment_hash`, `customer_confirmed_at`, new AuditLog action |
| `admins/migrations/XXXX_customer_commitment.py` | New migration |
| `customers/views.py` | Split `submit_order` into staging + `confirm_order` view |
| `customers/urls.py` | Add `confirm_order` URL |
| `admins/utils.py` | Embed admin identity + customer commitment hash in `generate_invoice_pdf` |
| `templates/customers/order_confirmation.html` | New template — order summary + OTP input |
| `templates/customers/verify_receipt.html` | Add commitment hash + admin identity display |
| `admins/management/commands/cancel_unconfirmed_orders.py` | New management command for 30-min timeout |
| `admins/views.py` (dashboard queries) | Exclude `pending_confirmation` orders from admin queue — admins should only see orders the customer has confirmed |
