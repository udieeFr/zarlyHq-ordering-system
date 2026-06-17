# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_stripe_payments.py

# Run a single test by name
pytest tests/test_stripe_payments.py::TestStripePayments::test_webhook_success -v

# Run tests without coverage (faster)
pytest --no-cov

# Start dev server
python manage.py runserver

# Apply migrations
python manage.py migrate

# Cancel unconfirmed orders (dry-run by default; pass --dry-run false to actually cancel)
python manage.py cancel_unconfirmed_orders --dry-run false

# Collect static files
python manage.py collectstatic --noinput
```

## Architecture

ZarlyOS is a **food-ordering SaaS** built on Django 5.1 with two main apps:

- **`customers/`** — storefront: product catalog, cart (session-based), checkout, OTP confirmation, Stripe payment, order history, complaints, customer profile/CRM
- **`admins/`** — operations: order queue, approval/rejection, payment verification, inventory, prep groups, delivery tracking, refunds, audit log, manager analytics, email campaigns

### Order Lifecycle

```
[Cart] → submit_order → pending_confirmation (OTP sent)
       → confirm_order (OTP verified) → pending
       → admin approve_order
           ├── payment confirmed? → finalize_order_approval() → approved (PDF + DigitalSignature created)
           └── no payment? → pending_payment (customer uploads proof or pays Stripe)
       → approve_pending_payment / force_approve_unpaid → approved
       → mark_orders_prepared (bulk, creates PrepGroup) → prepared
       → mark_prep_group_ready → ready_for_delivery
       → mark_order_out_for_delivery → out_for_delivery
       → mark_order_delivered → delivered
```

Key behaviours:
- **Stock is decremented at `pending_confirmation` time** (inside `_create_order_atomic` with `SELECT FOR UPDATE`). It is only restored if the OTP confirmation is abandoned (cron: `cancel_unconfirmed_orders`) or customer/admin cancels.
- **OTP uses Redis cache** (`order_confirm_otp_<user_pk>` key). Key-space separations exist for email-verify OTP, signup OTP, password-change OTP, and order OTP — they must not share key prefixes.
- **`finalize_order_approval()`** generates a PDF invoice and signs it via PyHanko. It is called from `approve_order`, `approve_pending_payment`, and `set_pending_payment` — but **not** `force_approve_unpaid`.
- **Payment**: two paths — Stripe Checkout (webhook `checkout.session.completed` marks `Payment.status='succeeded'`) and manual proof (customer uploads; admin verifies via `approve_pending_payment`).
- **`order_has_confirmed_payment(order)`** is the single check used everywhere: Stripe → `stripe_payment_intent_id` set + `status='succeeded'`; manual → `proof_image` exists and not empty.

### Key Files

| File | Purpose |
|---|---|
| `customers/views.py` | All customer-facing views (cart, checkout, OTP confirm, Stripe callbacks, payment proof upload) |
| `admins/views.py` | All admin-facing views (approval, prep, delivery, complaints, analytics) |
| `customers/stripe_utils.py` | Stripe Checkout session creation, webhook handlers (`handle_checkout_session_completed`, `handle_payment_intent_failed`, `handle_charge_refunded`) |
| `admins/refund_utils.py` | `process_refund()` (auto Stripe or manual flag) and `remake_order()` |
| `customers/otp_utils.py` | All OTP generation/verification (separate key prefixes per use-case) |
| `customers/delivery_utils.py` | Shipping fee calculator (weight tiers × peninsular/east Malaysia zones) |
| `customers/payment_utils.py` | QR code generation for DuitNow and bank transfer; `validate_payment_proof()` (magic-byte + Pillow check) |
| `admins/models.py` | `Order`, `OrderItem`, `Payment`, `DigitalSignature`, `Refund`, `PrepGroup`, `AuditLog`, `OrderEvent` |
| `customers/models.py` | `User` (custom auth), `Product`, `CustomerProfile` (CRM/loyalty), `OrderRating`, `ProductReview` |
| `zarlyOs/settings.py` | Redis cache config (falls back to LocMemCache in dev), Stripe keys, email, CSP, session config |
| `admins/management/commands/cancel_unconfirmed_orders.py` | Cron job — cancels orders stuck in `pending_confirmation` after 30 min and restores stock |

### Auth & Roles

Three roles on `customers.User.role`: `customer`, `sales_admin`, `manager`. Decorators in `customers/auth_utils.py`:
- `@customer_required` — login + `role == 'customer'`
- `@sales_admin_required` — login + `role in ['sales_admin', 'manager']` or superuser
- `@manager_required` — login + `role == 'manager'` or superuser

Step-up auth (`sudo`) for sensitive admin actions: `admins/sudo.py`.

### Infrastructure

- **Runtime**: Gunicorn (`gunicorn_config.py`) behind Nginx, deployed via Docker (`docker-compose.yml` + `Dockerfile`)
- **Database**: PostgreSQL 17
- **Cache/Sessions**: Redis (required for OTP to work across Gunicorn workers; falls back to LocMemCache in dev which breaks multi-worker OTP)
- **Static files**: `collectstatic` runs on every container start via `entrypoint.sh`
- **Stripe webhook** is registered at both `/menu/stripe/webhook/` and `/stripe/webhook/` (alias)

### Walk-in Orders

Admin can create orders for walk-in customers via `admin_create_order`. Walk-ins use a sentinel `__walkin__` user (`_get_walkin_user()` creates it if absent). Walk-in orders skip all customer-facing OTP, email, and notification flows.

### Deployment

Build, push to Docker Hub, and pull on VPS — see `DEPLOYMENT.md`. No repo clone on the VPS.

```bash
docker build -t udieefr/zarlyhq:latest .
docker push udieefr/zarlyhq:latest
# On VPS:
docker-compose pull && docker-compose up -d
```
