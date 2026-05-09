# Zarly Payment System - Complete Context Summary
## Session: April 29 - May 9, 2026

---

## 1. PAYMENT SYSTEM ARCHITECTURE

### Technology Stack
- **Framework**: Django 6.0.1
- **Database**: PostgreSQL (running in Docker on port 5433)
- **Payment Gateway**: Stripe SDK 11.5.0
- **Python**: 3.13.13 (in venv)
- **Currency**: MYR (Malaysian Ringgit)

### Key Models

#### Order Model (admins/models.py)
```
- customer: ForeignKey(User)
- full_name, phone_number, address, coordinates
- total_amount: DecimalField
- status: CharField with choices [pending, approved, pending_payment, rejected, prepared, ready_for_delivery, out_for_delivery, delivered]
- payment_proof: ImageField (for manual uploads)
- approved_at, approved_by timestamps
```

#### Payment Model (admins/models.py) - Tracks all payment attempts
```
- order: ForeignKey(Order, related_name='payments')
- payment_method: CharField ['stripe', 'manual', 'cash']
- status: CharField ['pending', 'processing', 'succeeded', 'failed', 'cancelled', 'refunded']
- amount: DecimalField
- currency: CharField

Stripe-specific fields:
- stripe_session_id: Unique identifier for Checkout Session
- stripe_payment_intent_id: Set by webhook when checkout.session.completed fires
- stripe_charge_id: Set by webhook, proves payment charged
- stripe_customer_id: Stripe customer record
- paid_at: Timestamp set by webhook
- last_webhook_event: Stores event type
- webhook_event_timestamp: When event arrived

One Order can have multiple Payment records (for retry scenarios)
Payment record is the SOURCE OF TRUTH for payment confirmation
```

### Payment Flow (Intended Design)

1. **Customer Creates Order** → submit_order() in customers/views.py
   - Creates Order with status='pending' (NOT pending_payment)
   - If Stripe payment: calls create_stripe_checkout_session()
   - Creates Payment record with status='pending'
   - Redirects to Stripe Checkout

2. **Customer Completes Stripe Checkout** → Stripe processes payment

3. **Stripe Webhook Fires** → stripe_webhook() in customers/views.py
   - Event: `checkout.session.completed`
   - Verifies signature using STRIPE_WEBHOOK_SECRET
   - Calls handle_checkout_session_completed() in customers/stripe_utils.py
   - Updates Payment record:
     - status → 'succeeded'
     - stripe_payment_intent_id → filled (KEY INDICATOR webhook fired)
     - stripe_charge_id → filled
     - paid_at → set to current time
   - Order stays status='pending' (waiting for admin review)

4. **Admin Reviews Order** → admin_order_detail() shows:
   - Stripe payment evidence if available
   - Approve button appears if order_has_confirmed_payment() returns True

5. **Admin Accepts Order** → set_pending_payment() or approve_order()
   - Calls order_has_confirmed_payment()
   - If True (payment confirmed): finalize_order_approval() → status='approved'
   - If False (no payment): status='pending_payment' (waiting for manual proof)

### Critical Function: order_has_confirmed_payment()
```python
def order_has_confirmed_payment(order):
    # Checks if payment is verified (Stripe webhook + intent ID) OR manual proof uploaded
    has_stripe_payment = order.payments.filter(
        payment_method='stripe',
        status='succeeded',
        stripe_payment_intent_id__isnull=False  # WEBHOOK INDICATOR
    ).exists()
    return bool(order.payment_proof) or has_stripe_payment
```

**Why stripe_payment_intent_id check matters:**
- Webhook handler SETS this field
- If it's None, webhook never fired
- This prevents approving orders that show succeeded but weren't actually charged

---

## 2. THE PROBLEM IN THIS SESSION

### Symptom
When user created Stripe orders:
- Admin panel showed **"🧾 Stripe Payment Initiated"** (yellow) instead of **"✅ Stripe Payment Succeeded"** (green)
- When admin clicked Accept, order went to **"Awaiting Payment" table** instead of **"Approved" table**
- Customer couldn't proceed, system treated paid orders as unpaid

### Root Cause Analysis (Discovered Through Investigation)

#### Issue #1: Missing CSRF Exemption (Fixed First)
**Problem**: stripe_webhook() view endpoint was protected by Django's CSRF middleware
**Evidence**: Terminal logs showed `[403] POST http://localhost:8000/stripe/webhook/` - webhook was being SENT but rejected
**Solution Applied**: Added `@csrf_exempt` and `@require_http_methods(['POST'])` decorators

#### Issue #2: Webhook Signature Mismatch (Real Problem - Not Fixed Yet)
**Problem**: Even after @csrf_exempt, Payment records stayed status='pending'
- Webhook was reaching Django (no more 403)
- But signature verification was silently failing
- stripe.Webhook.construct_event() was returning None + error
- Handler never updated Payment record

**Root Cause**: 
- Stripe CLI outputs a TEMPORARY webhook secret: `whsec_test_abc123...`
- User's .env file has a DIFFERENT static secret
- When Stripe sends webhook with signature A, but .env has secret B, verification fails
- Django logs show: "Webhook signature verification failed: Invalid signature"

**Why It's Hard to Debug**:
- Webhook endpoint returns 200 OK either way (good practice)
- No visual error in admin panel - just wrong status
- Payment record never gets updated, so order never moves to approved table

### Timeline of Investigation

1. **Initial Symptom**: Order 17, 18 showing "Payment Initiated" instead of "Succeeded"
2. **First Fix Attempt**: Added @csrf_exempt decorator → 403 errors went away but payments still showed pending
3. **Database Query**: Checked Payment table - all records had stripe_payment_intent_id=NULL
   - Confirmed webhook wasn't updating Payment records
4. **Webhook Handler Testing**: Simulated webhook locally → worked perfectly
   - Proved code logic is correct
   - Proved database update works
   - Proved order_has_confirmed_payment() works
5. **Real Stripe Logs**: Saw webhook events firing but something preventing update
6. **Diagnosis**: STRIPE_WEBHOOK_SECRET mismatch = signature verification failing silently

---

## 3. HOW TO VERIFY AND FIX

### Quick Test (Temporary Solution)
**File**: c:\Users\rusdi\ZarlyHQ\fix_payment.py
```bash
python fix_payment.py
```
This script:
- Finds latest pending Stripe payment
- Simulates webhook by setting: status='succeeded', stripe_payment_intent_id, stripe_charge_id, paid_at
- Admin panel then shows green "Payment Succeeded"
- Order can be approved to "Approved" table

**Use case**: Testing admin approval flow without needing Stripe CLI

### Permanent Fix (Required for Production)

**Step 1: Get the Correct Webhook Secret**
```bash
stripe listen --forward-to localhost:8000/stripe/webhook/
```
Output will show:
```
Ready! Your webhook signing secret is: whsec_test_abc123xyz...
```

**Step 2: Update .env**
Find this line:
```
STRIPE_WEBHOOK_SECRET=whsec_7ee3cb9e88147a5bb0f4e875898fbb2a52bc8bcb4072fdc9ac1b68bb2021ac4f
```
Replace with the one from Step 1:
```
STRIPE_WEBHOOK_SECRET=whsec_test_abc123xyz...
```

**Step 3: Restart Django**
```bash
python manage.py runserver
```

**Step 4: Test Full Flow**
1. Create new order → select Stripe payment
2. Complete checkout in Stripe
3. Webhook fires automatically
4. Admin page shows green "✅ Stripe Payment Succeeded"
5. Admin clicks Approve → order goes to "Approved" table (not "Awaiting Payment")

---

## 4. FILES CRITICAL TO UNDERSTAND THE SYSTEM

### Core Payment Files (READ THESE FIRST)

1. **admins/models.py** - Payment and Order models
   - Define all payment fields
   - Status choices
   - Indexes for performance

2. **customers/stripe_utils.py** - All Stripe API interactions
   - `create_stripe_checkout_session()` - creates session + Payment record
   - `handle_checkout_session_completed()` - processes webhook, updates Payment
   - `verify_webhook_signature()` - validates Stripe signature
   - `handle_payment_intent_failed()` - handles failed payments
   - `handle_charge_refunded()` - handles refunds

3. **customers/views.py** - Customer-facing payment views
   - `submit_order()` - creates order, initiates Stripe checkout
   - `stripe_webhook()` - webhook entry point (must have @csrf_exempt)
   - `stripe_success()` - post-payment success page
   - `stripe_cancel()` - payment cancellation handler

4. **admins/views.py** - Admin approval logic
   - `order_has_confirmed_payment()` - KEY FUNCTION: checks if payment verified
   - `set_pending_payment()` - routes order to approved or pending_payment based on payment status
   - `bulk_accept_orders()` - batch approval with payment checks
   - `admin_order_detail()` - shows payment evidence

5. **customers/urls.py** - URL routing for payments
   - `/stripe/webhook/` - webhook endpoint
   - `/stripe/success/<order_id>/` - after successful payment
   - `/stripe/cancel/<order_id>/` - after cancelled payment

### Template Files

6. **templates/admins/order_detail.html** - What admins see
   - Shows payment status (initiated vs succeeded)
   - Shows "Approve" button only if has_payment=True
   - Displays Stripe transaction IDs for verification

7. **templates/customers/stripe_success.html** - Customer success page
   - Shows payment confirmation
   - "Go to Dashboard" button

### Configuration Files

8. **.env** - CRITICAL for local testing
   - STRIPE_PUBLIC_KEY
   - STRIPE_SECRET_KEY
   - STRIPE_WEBHOOK_SECRET (THE ONE CAUSING ISSUES)
   - STRIPE_CURRENCY

### Test Files

9. **tests/test_stripe_payments.py** - Validation tests
   - `test_create_checkout_session_persists_payment` - verifies session creation works
   - `test_checkout_session_completed_marks_payment_succeeded` - verifies webhook handler works

10. **fix_payment.py** - Emergency workaround script
    - Simulates webhook for testing
    - Temporary solution while webhook secret is wrong

---

## 5. WHAT TO PROVIDE TO OTHER AI AGENT

### Minimum Files for Understanding Full Picture

**Essential (Can't debug without these):**
1. admins/models.py - Payment and Order definitions
2. customers/stripe_utils.py - Webhook handlers
3. customers/views.py - Webhook endpoint + order submission
4. admins/views.py - Admin approval logic + order_has_confirmed_payment()
5. .env - Configuration values (redact sensitive keys but keep structure)
6. customers/urls.py - URL routing

**Highly Recommended:**
7. templates/admins/order_detail.html - How status is displayed
8. tests/test_stripe_payments.py - Test cases showing expected behavior

**Optional But Helpful:**
9. manage.py - Django entry point
10. zarlyOs/settings.py - Django configuration
11. customers/models.py - User model + Product model

### What to Explain to Other Agent

When providing files, tell them:

**Context to include:**
```
PROJECT: Zarly Food Delivery System
FRAMEWORK: Django 6.0.1 + PostgreSQL
PAYMENT: Stripe integration with webhooks

CURRENT ISSUE:
- Stripe-paid orders show "Payment Initiated" instead of "Payment Succeeded"
- After admin accepts, orders go to "Awaiting Payment" instead of "Approved Orders"
- Root cause: STRIPE_WEBHOOK_SECRET in .env doesn't match Stripe CLI output
- Webhook signature verification fails silently
- Payment records never get updated by webhook

WHAT WE KNOW WORKS:
- Order creation code ✓
- Stripe session creation ✓
- Webhook endpoint (@csrf_exempt added) ✓
- Webhook handler logic (tested locally) ✓
- Admin approval logic ✓
- Database queries ✓

WHAT'S BROKEN:
- Webhook signature verification (silent failure)
- Payment record status staying 'pending' instead of 'succeeded'
- order_has_confirmed_payment() finding no confirmed payments

WORKAROUND:
- Created fix_payment.py to manually update payments for testing
- Works: updates status to 'succeeded', sets intent/charge IDs
- Allows testing full approval flow

PERMANENT FIX:
- Update .env STRIPE_WEBHOOK_SECRET to match Stripe CLI output
- Restart Django
- Real webhooks will then auto-update payment records
```

---

## 6. DEPLOYMENT CHECKLIST

Before going live:
- [ ] Update .env STRIPE_WEBHOOK_SECRET with production Stripe webhook secret
- [ ] Set up Stripe webhook in Stripe Dashboard pointing to production domain
- [ ] Test full flow: order → checkout → webhook → admin approval → approved
- [ ] Verify Payment records update correctly when real webhooks fire
- [ ] Check Django logs for "Webhook signature verification failed" errors
- [ ] Confirm order_has_confirmed_payment() returns True after webhook
- [ ] Test both Stripe and manual payment paths

---

## 7. QUICK REFERENCE

**Key Fields to Monitor**
```
Payment record:
- status: pending → succeeded (should change after webhook)
- stripe_payment_intent_id: None → pi_xxx (webhook indicator)
- stripe_charge_id: None → ch_xxx (proof of charge)
- paid_at: None → timestamp (when charge succeeded)

Order record:
- status: pending → approved (should change when admin accepts + payment confirmed)
- payment_proof: None (for Stripe orders)
```

**Logs to Check**
- Django logs: "Webhook signature verification failed" = secret mismatch
- Stripe CLI: "checkout.session.completed" = webhook fired
- Admin panel: green vs yellow box = payment status

**Testing Commands**
```bash
# Simulate webhook
python fix_payment.py

# Check recent payments
python manage.py shell
>>> from admins.models import Payment
>>> Payment.objects.latest('created_at')

# Run tests
python -m pytest tests/test_stripe_payments.py -v
```
