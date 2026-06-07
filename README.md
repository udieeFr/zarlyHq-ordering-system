# ZarlyHQ — Secure Food Ordering Management System

A signature-based online ordering platform built for **Zarly BigFood Sdn. Bhd.** (Big Food Industries Sdn. Bhd.). Replaces informal order intake (WhatsApp, verbal agreements) with a centralized, tamper-proof, and legally defensible system.

---

## Overview

ZarlyHQ covers the full order lifecycle — from customer placement to digital invoice generation — with cryptographic guarantees at every critical step.

**Live system:** [zarlybigfood.my](https://zarlybigfood.my)

---

## Features by Role

### Customer

| Feature | Description |
|---|---|
| Product catalogue | Browse products with category filters, bundle options, and allergy tags |
| Cart | Add items, update quantities, session-based stock reservation |
| Checkout | Address form with live delivery fee calculated by state and weight |
| OTP confirmation | 6-digit code sent to email to confirm order — locks in order contents |
| Stripe payment | Pay by card via Stripe hosted checkout |
| Manual payment | Upload bank transfer / DuitNow screenshot as proof |
| Order history | View all past and upcoming orders with status labels |
| Signed receipt | Download cryptographically signed PDF invoice |
| Receipt verification | Public URL to verify receipt authenticity and integrity |
| Complaint submission | Raise a complaint on any delivered order |

### Sales Admin

| Feature | Description |
|---|---|
| Order queue | Live dashboard of all incoming orders needing action |
| Order approval | Approve or reject orders with reason logging |
| Step-back | Push an order back to a previous status with mandatory reason |
| Payment review | View uploaded proof and approve manual payments |
| Walk-in orders | Create orders directly for counter customers — no account needed |
| Prep group | Bulk-batch approved orders for kitchen, mark ready in one action |
| Delivery tracking | Mark orders Out for Delivery and Delivered individually |
| Refunds | Initiate refund — automatic via Stripe, flagged for manual otherwise |
| Sudo re-auth | Re-authentication required for high-risk actions like refunds |

### Manager

| Feature | Description |
|---|---|
| Sales analytics | Revenue, order volume, and top products dashboard |
| Customer CRM | View customer profiles, tag VIP customers |
| Email campaigns | Compose and blast marketing emails to customers |
| Inventory management | Add, edit, and delete products with weight and bundle configuration |
| Audit log | Tamper-evident log of every action with hash chain integrity check |
| Ratings dashboard | View customer ratings and feedback by product |

---

## Security Architecture

| Feature | Implementation |
|---|---|
| Digital signatures | PyHanko PKCS#7 embedded in PDF, RSA private key |
| Receipt integrity | SHA-256 hash stored at signing, recomputed on verify |
| Non-repudiation | Customer commitment hash (SHA-256 of order contents at OTP confirmation) |
| Audit log | Tamper-evident hash chain — any edit or deletion is detectable |
| OTP authentication | 6-digit code, 5-minute TTL, Redis-backed, rate-limited |
| Support chat encryption | Fernet symmetric encryption (AES-128-CBC) |
| RBAC | Three roles: `customer`, `sales_admin`, `manager` with decorator-enforced access |
| Step-up auth | Sudo re-authentication for refunds, deletions, and audit log access |
| Rate limiting | django-ratelimit on login, OTP, payment upload, and order submission |
| CSRF protection | Django middleware on all POST endpoints |
| Private media | nginx X-Accel-Redirect with ownership verification before serving |
| Input validation | Server-side length limits, file type validation at byte level |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 6.0, Python 3.13 |
| Database | PostgreSQL 17 |
| Cache / OTP | Redis |
| PDF generation | ReportLab |
| PDF signing | PyHanko (PKCS#7) |
| Payment | Stripe |
| Web server | Nginx (reverse proxy + SSL) |
| WSGI | Gunicorn |
| Containerisation | Docker + Docker Compose |
| Hosting | AWS Lightsail (Ubuntu) |
| Domain | zarlybigfood.my (with Let's Encrypt SSL) |

---
## Deployment

The production system runs on AWS Lightsail via Docker Compose


## User Roles

| Role | Access |
|---|---|
| `customer` | Menu, cart, checkout, orders, complaints, receipts |
| `sales_admin` | Order queue, approvals, payments, kitchen, delivery, walk-in |
| `manager` | Everything above + analytics, campaigns, audit log, inventory |



-

Built as a Final Year Project (PSM) at **Universiti Tun Hussein Onn Malaysia (UTHM)**.

- **Title:** Secure Signature-Based Online Ordering System
- **Methodology:** Evolutionary Prototyping (3 iterations)
- **Focus:** Non-repudiation, digital signatures, tamper-evident audit trails in an SME food ordering context
