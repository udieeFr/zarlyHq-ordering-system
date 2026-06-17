# ZarlyOS Receipt Watermarking — System Workflow

## What is this?

Every approved order in ZarlyOS gets a **tamper-proof digital receipt**. The receipt carries two layers of proof:

1. **A hidden fingerprint** — a SHA-256 hash stored in the database at signing time
2. **A visible seal** — a coloured watermark stamped onto the PDF every time someone downloads it

If anyone alters the receipt file — even by a single byte — the watermark turns from a **green AUTHENTIC seal** into a **red VOID stamp**. You can tell at a glance whether the document is genuine.

---

## The Big Picture

```
                    ┌──────────┐     ┌──────────┐     ┌──────────┐
  Customer          │  Place   │     │  Confirm │     │  Receive │
  Journey           │  Order   │ ──> │   OTP    │ ──> │  Signed  │
                    └──────────┘     └──────────┘     │  Receipt │
                                                       └──────────┘
                                                             │
                    ┌──────────┐     ┌──────────┐            │
  Admin             │  Review  │     │ Approve  │            │
  Journey           │  Order   │ ──> │ + Sign   │ ──────────┘
                    └──────────┘     └──────────┘
                                          │
                                          ▼
                                    ┌──────────┐     ┌──────────┐
  Verification                      │ Download │     │  Public  │
  Journey                           │ Receipt  │     │  Verify  │
                                    │ (AUTH)   │     │  (UUID)  │
                                    └──────────┘     └──────────┘
```

---

## Step-by-Step Workflow

### Phase 1 — Customer places an order

```
Customer fills cart → enters address → clicks "Submit Order"
```

**What happens behind the scenes:**

1. The system locks the product stock in the database so nobody else can buy the same items.
2. A **commitment fingerprint** is calculated — a unique code generated from the exact order contents (what items, what quantities, what price, who ordered it, when).
3. A 6-digit **OTP code** is sent to the customer's email. This code expires after 5 minutes and can only be used once.
4. The order is now in a `pending_confirmation` state — it exists but is not yet active.

> **Why the commitment fingerprint matters:** The fingerprint locks in exactly what the customer saw when they clicked "Submit." If the database were later altered to change the price or items, the fingerprint would no longer match. This is the **customer's proof** — they cannot later claim "I ordered something different."

### Phase 2 — Customer confirms via OTP

```
Customer enters the 6-digit code → order moves to "pending" queue
```

**What happens behind the scenes:**

1. The system checks the OTP against what was sent. Only 5 wrong attempts are allowed.
2. On success, the **commitment fingerprint is saved permanently** to the order record.
3. An audit trail entry is written: "Customer confirmed order #X at 2:15 PM."
4. The customer is routed to payment (Stripe card payment or manual bank transfer).

### Phase 3 — Admin reviews and approves

```
Admin sees the order in the dashboard → verifies payment → clicks "Approve"
```

**What happens behind the scenes:**

1. The system checks whether payment is confirmed (Stripe webhook received, or manual proof uploaded).
2. An invoice PDF is generated — a professional A4 document with company letterhead, item table, totals, and terms.
3. The PDF is **digitally signed** using the company's private key. This embeds a cryptographic signature (PKCS#7 standard) directly into the PDF file — similar to how a handwritten signature proves who signed a paper document, but mathematically unforgeable.
4. A **SHA-256 hash** of the signed PDF file is computed and stored in a `DigitalSignature` record alongside the file path and a random UUID verification token.
5. The order status changes to `approved` and the customer is notified.

> **Why the digital signature matters:** Anyone with the signed PDF can verify it came from Zarly BigFood. Even if someone downloads and edits the file, the signature will break. This is the **company's proof** — Zarly cannot later deny approving the order.

### Phase 4 — Customer downloads the watermarked receipt

```
Customer opens order details → clicks "View Signed Receipt (Watermarked)" → PDF opens
```

**What happens behind the scenes — EVERY TIME the receipt is downloaded:**

1. The system finds the signed PDF on disk.
2. It recomputes the **SHA-256 hash** of the file and compares it to the stored hash from signing time.
3. Two outcomes are possible:

   | Hash Match? | Watermark Applied | What the customer sees |
   |---|---|---|
   | **Yes — file is unchanged** | Green diagonal stamp: **AUTHENTIC** with subtitle "Digitally Signed · PKCS#7 · Tamper-Proof" | A professional receipt with a green seal of authenticity |
   | **No — file was altered** | Red diagonal stamp: **VOID** with subtitle "Verification Failed · Do Not Accept" | An obviously invalid document with a red warning |

4. The watermark is applied as a layer **on top of** the invoice content. It includes:
   - A **pantograph background** — tiny text ("ZARLY BIGFOOD SDN BHD") repeated in diagonal rows across the entire page. This pattern breaks apart if someone photocopies or scans the receipt, making forgery obvious.
   - A **diagonal seal** across the centre — large bold text inside a double border, rotated 45 degrees.
5. The watermarked PDF is streamed to the browser. **The original signed file on disk is never touched** — the watermark only exists in the downloaded copy.

> **Key insight:** The watermark is generated fresh on every download. If someone tampered with the stored PDF file between two downloads, the second download would show VOID while the first showed AUTHENTIC.

### Phase 5 — Public verification (anyone can check)

```
Anyone visits /menu/verify/<uuid-token>/ in their browser
```

This is a public page — **no login required**. It lets anyone who receives a Zarly receipt verify it is genuine.

**What happens behind the scenes:**

1. The system looks up the receipt by its **UUID token** — a random, unguessable identifier. This prevents anyone from guessing order numbers and viewing other people's receipts.
2. It recomputes the SHA-256 hash of the PDF on disk and compares it to the stored hash.
3. If the hashes match, the page shows a **green "Receipt Authentic & Unmodified"** banner with a download button for the watermarked PDF.
4. If the hashes do not match, the page shows a **red "Tampering Detected"** banner.
5. Results are **cached for 24 hours** — a signed receipt never changes, so there's no need to recompute.

The verification page is designed for non-technical users. It does not display hash values or technical certificate details. The instruction is simple: **download the PDF and look for the green AUTHENTIC seal.**

---

## The Two Proofs (Non-Repudiation Explained Simply)

ZarlyOS solves a legal problem: **in a dispute, who is telling the truth?**

| Scenario | What the customer claims | What ZarlyOS proves |
|---|---|---|
| "I never ordered this" | Customer denies placing the order | The commitment fingerprint + OTP confirmation prove the customer actively confirmed this exact order at this exact time. |
| "The price was different" | Customer claims the total was lower | The commitment fingerprint encodes the original price. If someone changed the database, the fingerprint won't match. |
| "Zarly never approved my order" | Customer claims the company never accepted | The PKCS#7 digital signature on the PDF proves the company's private key was used to sign. Only Zarly holds that key. |
| "This receipt is fake" | Someone presents a forged receipt | The public verification page shows whether the hash matches. A forged receipt will have no matching signature record. |

**In legal terms:** The customer cannot deny initiating the order (Non-Repudiation of Origin). The company cannot deny accepting it (Non-Repudiation of Finalization).

---

## Visual Summary

### AUTHENTIC receipt (everything is fine)

```
┌───────────────────────────────────────────┐
│  ZARLY                          INVOICE   │
│  Big Food Industries Sdn. Bhd.            │
│  ════════════════════════════════════     │
│                                           │
│  Bill To: Ahmad bin Ali                   │
│  No 42 Jalan Selasih 15, Pasir Putih      │
│                                           │
│  ┌─────────────────────────────────────┐  │
│  │ #  Description          Qty  Amt   │  │
│  │ 1  Ayam Gunting Cheese   2   56.00 │  │
│  │ 2  Kentang Putar         1   12.50 │  │
│  ├─────────────────────────────────────┤  │
│  │    Total (MYR)              84.40  │  │
│  └─────────────────────────────────────┘  │
│                                           │
│         ╱ AUTHENTIC ╲                     │
│        ╱ Digitally Signed ╲               │
│       ╱ PKCS#7 ·Tamper-Proof╲             │
│                                           │
│  Signature: Zarly BigFood Sdn. Bhd.       │
└───────────────────────────────────────────┘
     Background: diagonal micro-text
     "ZARLY BIGFOOD SDN BHD" repeated
```

### VOID receipt (file was tampered with)

```
┌───────────────────────────────────────────┐
│  ZARLY                          INVOICE   │
│  Big Food Industries Sdn. Bhd.            │
│  ════════════════════════════════════     │
│                                           │
│  ... (invoice content same as above) ...  │
│                                           │
│           ╱   VOID   ╲                    │
│          ╱ Do Not Trust ╲                 │
│                                           │
│  Signature: VERIFICATION FAILED           │
└───────────────────────────────────────────┘
```

---

## How to Demo the Watermark

### Quick demo (no real order needed)

On the VPS, run:

```bash
docker-compose exec django python manage.py test_watermark --sample
```

This generates four files in the media directory that you can download and open:

| File | What it shows |
|---|---|
| `_sample_AUTHENTIC.pdf` | A receipt with the green seal — use this in your presentation |
| `_sample_VOID.pdf` | A receipt with the red VOID stamp — show what tampering looks like |
| `_sample_watermark_raw.pdf` | The watermark layer by itself — helps explain how it works |
| `_sample_fake_receipt.pdf` | A clean invoice with no watermark — the "before" state |

### Demo with a real order

```bash
# Watermark a specific approved order
docker-compose exec django python manage.py test_watermark --order-id 1

# Force the VOID stamp (simulate tampering)
docker-compose exec django python manage.py test_watermark --order-id 1 --void
```

### Demo via the website

1. Log in as a customer who has an approved order
2. Go to Order Details → click **"View Signed Receipt (Watermarked)"**
3. The PDF opens with either the green AUTHENTIC seal or red VOID stamp
4. Share the public verification URL (`/menu/verify/<uuid>/`) — anyone can open it and verify

---

## Key Design Decisions

**Why stamp the watermark on every download instead of once at signing time?**
Because the live tamper check happens on every download. If someone replaces the signed PDF file on the server between two downloads, the watermark changes from AUTHENTIC to VOID. This is a continuous integrity check — not a one-time event.

**Why are the watermark colours pale instead of bold?**
The watermark sits on top of the invoice content. Pale colours keep the invoice fully readable while still being clearly visible. Earlier versions used transparency (alpha channel), but this broke when merging PDFs — so we use opaque light colours instead.

**Why use a UUID token instead of the order ID for public verification?**
Order IDs are sequential (1, 2, 3...). A UUID is random and unguessable. This prevents anyone from typing `/verify/1`, `/verify/2`, `/verify/3` and viewing every receipt in the system.

**Why is the watermark PDF separate from the signed PDF?**
The signed PDF is the official record — it must never be modified after signing or the PKCS#7 signature would break. The watermark is applied dynamically to a copy, preserving the original signed file as the authoritative source of truth.
