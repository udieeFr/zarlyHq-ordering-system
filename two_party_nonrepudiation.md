# Two-Party Non-Repudiation — How It Works

## The Problem

In a normal food ordering system (WhatsApp, Grab, Shopee Food), when a dispute happens:

| Dispute | What happens |
|---|---|
| Customer says "I never ordered that" | The platform has a database record. But a database record can be edited by the platform owner. The customer has **no independent proof** of what they actually agreed to. |
| Customer says "The price was different when I ordered" | Same problem. Only the platform has the records. |
| Company denies ever accepting the order | The customer has a screenshot at best. Screenshots are not legal proof. |

**Both parties depend on the platform to be honest. There is no cryptographic truth.**

---

## The Solution: Two Keys for Two Parties

ZarlyOS gives each party their own **cryptographic proof** that the other party cannot forge or deny.

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│   CUSTOMER SIDE                          COMPANY SIDE
│   ─────────────                          ────────────
│                                                     │
│   "I ordered THIS"                      "I accepted THIS"
│         │                                      │
│         ▼                                      ▼
│   ┌──────────────┐                    ┌──────────────┐
│   │  Commitment  │                    │   PKCS#7     │
│   │    Hash      │                    │  Digital     │
│   │  (SHA-256)   │                    │  Signature   │
│   │              │                    │  (PyHanko)   │
│   └──────────────┘                    └──────────────┘
│         │                                      │
│         ▼                                      ▼
│   "I cannot deny                       "I cannot deny
│    ordering this"                       approving this"
│                                                     │
│   Non-Repudiation                      Non-Repudiation
│   of Origin (NRO)                      of Finalization (NRF)
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Part 1 — Binding the Customer (Non-Repudiation of Origin)

### Why not just a password?

A login password proves the customer logged in. But it does not prove they saw and agreed to **specific order contents**. If the database is altered after the fact, a simple login record does not help.

### How the commitment hash works

```
Step 1: Customer fills cart and clicks "Submit Order"

        Cart contents:
        ┌──────────────────────────────────┐
        │ 2x Ayam Gunting Cheese  RM 56.00 │
        │ 1x Kentang Putar          RM 12.50 │
        │ Shipping                  RM  8.00 │
        │ Total:                    RM 76.50 │
        │ Customer: Ahmad (ID #42)           │
        │ Address: Jalan Selasih 15          │
        │ Time: 2026-06-17 14:23:00          │
        └──────────────────────────────────┘
                │
                ▼
Step 2: System computes a SHA-256 hash of all this data

        SHA-256("42|Ahmad|2xAyamGunting|1xKentangPutar|76.50|...")
                │
                ▼
        a7f3c8e1b2d4... (64-character fingerprint)
                │
                ▼
Step 3: System sends a 6-digit OTP to Ahmad's email
        ┌─────────────────────────────────────┐
        │  From: noreply@zarlybigfood.com      │
        │  Subject: Confirm Your Order #88     │
        │                                     │
        │  Your order:                        │
        │    2x Ayam Gunting Cheese           │
        │    1x Kentang Putar                 │
        │    Total: RM 76.50                   │
        │                                     │
        │  Your OTP code: 4 8 2 7 3 1         │
        │  Expires in: 5 minutes              │
        └─────────────────────────────────────┘
                │
                ▼
Step 4: Ahmad enters the OTP

        The system now has TWO things locked together:
        ┌────────────────────────────────────────────┐
        │                                            │
        │   OTP ENTERED  ──proves──▶  Ahmad saw     │
        │   (email access)            the email      │
        │                                            │
        │   COMMITMENT   ──proves──▶  The EXACT      │
        │   HASH SAVED                contents Ahmad │
        │                             confirmed      │
        │                                            │
        └────────────────────────────────────────────┘
```

### Why this binds the customer

If Ahmad later says "I ordered 1 item, not 2," the system can answer:

> "Here is the commitment hash: `a7f3c8e1...` This hash was computed from the exact order contents and saved at 2:23 PM. You entered OTP code 482731 — sent to your email — which confirms you saw and accepted these contents. If the items had been different, the hash would be different. You cannot have confirmed a different hash."

The hash is **one-way** — you cannot work backwards from the hash to discover the order contents. But you can take the current order data, recompute the hash, and prove it matches what was originally saved.

---

## Part 2 — Binding the Company (Non-Repudiation of Finalization)

### Why not just a database status?

A database status (`order.status = 'approved'`) can be changed by anyone with database access. It proves nothing to an external party.

### How the PKCS#7 digital signature works

```
Step 1: Admin reviews Ahmad's order
        - Payment confirmed (Stripe webhook received)
        - Everything looks correct
        - Admin clicks "Approve"

Step 2: System generates the invoice PDF
        ┌──────────────────────────────────┐
        │  ZARLY                  INVOICE  │
        │  Order #88                       │
        │  Ahmad bin Ali                   │
        │  2x Ayam Gunting    RM 56.00     │
        │  1x Kentang Putar    RM 12.50     │
        │  Total:               RM 76.50    │
        └──────────────────────────────────┘

Step 3: System signs the PDF with the company's private key

        ┌─────────────┐
        │  Zarly's    │     The private key is a secret file
        │  PRIVATE    │     stored on the server. Only Zarly
        │  KEY        │     possesses it. It is NEVER shared.
        └──────┬──────┘
               │
               ▼
        PyHanko embeds a PKCS#7 signature into the PDF
               │
               ▼
        ┌──────────────────────────────────────┐
        │  The PDF now contains:               │
        │                                      │
        │  1. The invoice content              │
        │  2. An encrypted signature block     │
        │     (created using Zarly's private   │
        │      key — mathematically impossible  │
        │      to forge without the key)        │
        └──────────────────────────────────────┘

Step 4: System stores a SHA-256 hash of the signed PDF
        ┌──────────────────────────────────────┐
        │  DigitalSignature record             │
        │  ────────────────────                │
        │  signature_hash: b9d2f1... (64 chars)│
        │  pdf_path: signed_pdfs/order_88.pdf  │
        │  verify_token: f8a3c-7b2d-4e1f-...  │
        │  timestamp: 2026-06-17 14:45:00      │
        └──────────────────────────────────────┘
```

### Why this binds the company

If Zarly later says "We never approved that order," anyone with the signed PDF can answer:

> "This PDF contains a PKCS#7 digital signature created with Zarly's private key. Only Zarly holds that key. The signature is mathematically valid. The SHA-256 hash of the file matches the hash stored at signing time. Therefore, Zarly approved this order at 2:45 PM on June 17, 2026."

---

## Putting It All Together — One Order, Two Proofs

```
    CUSTOMER'S PROOF                        COMPANY'S PROOF
    (Commitment Hash + OTP)                 (PKCS#7 Digital Signature)

    ┌───────────────────┐                   ┌───────────────────┐
    │                   │                   │                   │
    │  "I, Ahmad,       │                   │  "We, Zarly       │
    │   confirmed this  │                   │   BigFood,        │
    │   exact order     │                   │   approved this   │
    │   at 2:23 PM"     │                   │   order at        │
    │                   │                   │   2:45 PM"        │
    │                   │                   │                   │
    │   Evidence:       │                   │   Evidence:       │
    │   · OTP entered   │                   │   · Signed PDF    │
    │   · Hash matches  │                   │   · Hash matches  │
    │   · Email record  │                   │   · Private key   │
    │   · Audit log     │                   │   · PKCS#7 block  │
    │                   │                   │                   │
    └────────┬──────────┘                   └────────┬──────────┘
             │                                       │
             └───────────────┬───────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │                              │
              │   NEITHER PARTY CAN DENY     │
              │   THE TRANSACTION            │
              │                              │
              │   This is TWO-PARTY          │
              │   NON-REPUDIATION            │
              │                              │
              └──────────────────────────────┘
```

---

## The Watermark Ties It Together Visually

The watermark is the **visible proof** that both bindings are intact:

| What the system checks | If OK | If tampered |
|---|---|---|
| Is the signed PDF file unchanged on disk? (SHA-256 comparison) | Green "AUTHENTIC" seal | Red "VOID" stamp |
| Did the PKCS#7 signature verify? | Seal shows "Digitally Signed · PKCS#7 · Tamper-Proof" | Seal subtitle changes to "Verification Failed" |

A customer downloading their receipt sees the green seal and knows: *my order is genuine, the company signed it, and nobody has altered it.*

A third party receiving the receipt sees the green seal and knows: *this document came from Zarly BigFood and has not been tampered with.*

A tampered receipt immediately shows the red VOID stamp — no technical knowledge needed.

---

## Dispute Scenarios — Who Wins?

| Scenario | What the customer says | What Zarly says | Who does the evidence support? |
|---|---|---|---|
| Customer denies ordering | "I never placed order #88" | "You confirmed it via OTP" | **Zarly wins.** The commitment hash + OTP log prove the customer actively confirmed. |
| Customer claims different items | "I ordered 1 item, not 2" | "You confirmed 2 items" | **Zarly wins.** Recomputation of the hash from the claimed items would produce a different hash. The stored hash matches 2 items. |
| Company denies approving | "Zarly never accepted my order" | "We have no record of this" | **Customer wins.** The signed PDF contains Zarly's PKCS#7 signature. Only Zarly's private key could have created it. |
| Someone presents a fake receipt | "Here is my receipt for RM 500" | "That is not our document" | **Zarly wins.** The fake receipt either has no valid PKCS#7 signature, or its SHA-256 hash does not match any stored DigitalSignature record. |
| Audit log tampering | — | — | **Detected automatically.** The hash chain breaks — `verify_chain()` returns `False` at the tampered row. |

---

## Why Different Mechanisms for Each Party?

| | Customer | Company |
|---|---|---|
| **What they prove** | "I confirmed this exact order" | "I approved and committed to this order" |
| **Mechanism** | OTP + SHA-256 commitment hash | PKCS#7 digital signature (RSA + X.509) |
| **Why this mechanism?** | Customers don't have digital certificates. OTP via email is something every customer already has. | The company is making a legally binding commercial commitment. PKI signatures are the standard for legal documents. |
| **Legal basis (Malaysia)** | Electronic Commerce Act 2006 — OTP as electronic signature | Digital Signature Act 1997 — PKI-based digital signatures |
| **What happens if you lie?** | The hash won't match your claim | The signature won't verify without Zarly's key |
| **Can you verify it yourself?** | Yes — download the watermarked receipt and check for the green seal | Yes — the green seal confirms the signature is intact |

---

## In Plain Language

**Before ZarlyOS:**
> Customer: "I didn't order that."
> Zarly: "Yes you did, I have it written down."
> → No way to prove who is right. Word against word.

**After ZarlyOS:**
> Customer: "I didn't order that."
> Zarly: "Here is the commitment hash computed from your exact order, timestamped to the moment you entered the OTP sent to your email. Here is the signed PDF with our PKCS#7 signature. Both are mathematically verifiable. Neither of us can alter them after the fact."
> → Cryptographic proof resolves the dispute.
