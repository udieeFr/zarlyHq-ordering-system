# Zarly BigFood - Complete Database Schema Documentation

**Last Updated:** 2026-05-19  
**System:** Django 6.0 with PostgreSQL  
**Version:** v1.0

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Entities](#core-entities)
3. [Relationships Map](#relationships-map)
4. [Data Flow](#data-flow)
5. [Table Details](#table-details)
6. [Business Logic](#business-logic)

---

## System Overview

Zarly BigFood is a **food ordering management system** with three distinct user roles:
- **Customers**: Browse products, place orders, make payments, submit complaints
- **Sales Admins**: Process orders, manage payments, handle complaints
- **Managers**: Full system access, inventory management, analytics

The database tracks:
- **Orders & Fulfillment**: Complete lifecycle from placement to delivery
- **Payments**: Multiple methods (Stripe, manual transfers, cash)
- **Inventory**: Product stock and availability
- **Customer Relationships**: Loyalty tiers, preferences, contact history
- **Complaints & Support**: Issue tracking and resolution
- **Audit Trails**: Security and accountability logs
- **Communications**: In-app notifications and support messages

---

## Core Entities

### 1. Users & Authentication

#### `auth_user` (Extended via `User` model)
**Purpose:** Authentication and authorization for all three roles

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | Django auto-increment |
| username | VARCHAR(150) | UNIQUE | Login handle |
| email | VARCHAR(254) | UNIQUE | Contact email |
| password | VARCHAR(128) | - | Hashed password |
| first_name | VARCHAR(150) | - | User's given name |
| last_name | VARCHAR(150) | - | User's family name |
| role | VARCHAR(50) | CHOICES | 'customer', 'sales_admin', 'manager' |
| phone_number | VARCHAR(20) | NULL | Optional contact |
| is_staff | BOOLEAN | - | Django admin access |
| is_superuser | BOOLEAN | - | Full system access |
| is_active | BOOLEAN | - | Account status |
| date_joined | TIMESTAMP | - | Registration date |
| last_login | TIMESTAMP | NULL | Last login time |

**Indexes:**
- `role` (for filtering by user type)

**Relationships:**
- **1→N with Order** (`customer` FK)
- **1→N with CustomerProfile** (OneToOne)
- **1→N with Favourite** (customer FK)
- **1→N with OrderRating** (customer FK)
- **1→N with ProductReview** (customer FK)
- **1→N with SupportMessage** (sender FK)
- **1→N with AuditLog** (actor FK)
- **1→N with Notification** (recipient FK)

---

### 2. Products & Inventory

#### `customers_category`
**Purpose:** Product categories (e.g., Noodles, Rice, Beverages)

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK |
| name | VARCHAR(100) | - |

**Relationships:**
- **1→N with Product** (category FK)

---

#### `customers_product`
**Purpose:** Catalog of food items for sale

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | Product identifier |
| name | VARCHAR(200) | - | Product display name |
| category_id | INTEGER | FK → Category | Required category |
| price | DECIMAL(10,2) | - | Selling price in MYR |
| weight_grams | INTEGER | - | Portion size |
| stock | INTEGER | - | Current inventory count |
| image | VARCHAR(255) | NULL | Product photo path |
| is_available | BOOLEAN | DEFAULT TRUE | Visibility to customers |
| created_at | TIMESTAMP | - | Auto-set |
| updated_at | TIMESTAMP | - | Auto-update |

**Indexes:**
- `is_available` (for product list filtering)

**Relationships:**
- **N→1 with Category** (category_id FK)
- **N→M with Allergy** (via junction table `customers_product_allergies`)
- **1→N with OrderItem** (product FK)
- **1→N with Favourite** (product FK)
- **1→N with ProductReview** (product FK)

---

#### `customers_allergy`
**Purpose:** Known allergens (peanuts, dairy, gluten, etc.)

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK |
| name | VARCHAR(100) | - |

**Relationships:**
- **N→M with Product** (via `customers_product_allergies` junction)

---

#### `customers_product_allergies` (junction)
**Purpose:** Maps allergens to products

| Column | Type |
|--------|------|
| id | INTEGER |
| product_id | INTEGER |
| allergy_id | INTEGER |

---

### 3. Customer Relationship Management

#### `customers_customerprofile`
**Purpose:** Extended customer data for CRM, loyalty, and analytics

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| user_id | INTEGER | FK → User (OneToOne) | Customer reference |
| total_orders | INTEGER | DEFAULT 0 | Count of completed orders |
| total_spent | DECIMAL(12,2) | DEFAULT 0 | Lifetime value in MYR |
| last_order_at | TIMESTAMP | NULL | Most recent order |
| loyalty_tier | VARCHAR(20) | CHOICES | 'bronze', 'silver', 'gold', 'platinum' |
| marketing_opt_in | BOOLEAN | DEFAULT TRUE | Email/SMS consent |
| preferred_payment_method | VARCHAR(50) | - | e.g., 'duitnow', 'bank_transfer' |
| default_phone | VARCHAR(20) | - | Saved contact number |
| default_address | TEXT | - | Saved delivery address |
| admin_notes | TEXT | - | Internal CRM notes (not visible to customer) |
| is_vip | BOOLEAN | DEFAULT FALSE | VIP priority flag |
| created_at | TIMESTAMP | - | Profile creation date |
| updated_at | TIMESTAMP | - | Last profile update |

**Indexes:**
- Composite: `(loyalty_tier, -total_spent)`
- Single: `(-last_order_at)`

**Loyalty Tier Calculation:**
- **Bronze**: < RM 500
- **Silver**: RM 500–1,999
- **Gold**: RM 2,000–4,999
- **Platinum**: ≥ RM 5,000

**Relationships:**
- **1→1 with User** (user_id FK)

---

#### `customers_favourite`
**Purpose:** Customer's wishlist/favorites

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| customer_id | INTEGER | FK → User | Customer |
| product_id | INTEGER | FK → Product | Favorited product |
| added_at | TIMESTAMP | - | When added |

**Unique Constraint:** `(customer_id, product_id)` — prevent duplicates

**Relationships:**
- **N→1 with User** (customer_id FK)
- **N→1 with Product** (product_id FK)

---

### 4. Orders & Fulfillment

#### `admins_order`
**Purpose:** Core order record; tracks fulfillment lifecycle

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | Order identifier |
| customer_id | INTEGER | FK → User | Placed by customer |
| status | VARCHAR(50) | CHOICES | See status flow below |
| full_name | VARCHAR(255) | NULL | Recipient name |
| phone_number | VARCHAR(20) | NULL | Delivery contact |
| street_address | VARCHAR(255) | NULL | Street |
| city | VARCHAR(120) | NULL | City |
| state | VARCHAR(120) | NULL | State/Province |
| postcode | VARCHAR(20) | NULL | Postal code |
| latitude | DECIMAL(9,6) | NULL | Delivery GPS |
| longitude | DECIMAL(9,6) | NULL | Delivery GPS |
| formatted_address | TEXT | - | Full address string |
| total_amount | DECIMAL(10,2) | - | Total in MYR |
| order_notes | TEXT | NULL | Special instructions |
| rejection_reason | TEXT | NULL | Why rejected (if rejected) |
| otp_code | VARCHAR(6) | NULL | Delivery verification |
| created_at | TIMESTAMP | - | Order placed |
| approved_at | TIMESTAMP | NULL | Admin approval time |
| approved_by_id | INTEGER | FK → User | Approving admin |
| prepared_at | TIMESTAMP | NULL | Prep completion |
| prepared_by_id | INTEGER | FK → User | Preparing staff |
| ready_for_delivery_at | TIMESTAMP | NULL | Handoff time |
| ready_for_delivery_by_id | INTEGER | FK → User | Handoff staff |
| delivery_assigned_at | TIMESTAMP | NULL | Courier assignment |
| delivery_assigned_by_id | INTEGER | FK → User | Who assigned |
| courier_name | VARCHAR(50) | NULL | Delivery company name |
| tracking_number | VARCHAR(100) | NULL | Shipment tracking ID |
| delivered_at | TIMESTAMP | NULL | Delivery completion |
| is_walk_in | BOOLEAN | DEFAULT FALSE | Walk-in (no customer account) |
| is_remake | BOOLEAN | DEFAULT FALSE | Remake order flag |
| remake_of_id | INTEGER | FK → Order (self) | Links to original if remake |
| is_priority | BOOLEAN | DEFAULT FALSE | Priority flag |

**Indexes:**
- `status`
- Composite: `(status, -created_at)`
- Composite: `(customer_id, -created_at)`
- Composite: `(is_priority, status)`

**Status Flow:**
```
pending → approved → prepared → ready_for_delivery → out_for_delivery → delivered
                  ↓
              rejected (terminal)
                  ↑
          (can occur at any stage)

pending_payment: Special status when approved but awaiting payment
cancelled: Terminal state when customer cancels
```

**Relationships:**
- **N→1 with User** (customer_id FK)
- **N→1 with User** (approved_by_id, prepared_by_id, etc.)
- **1→N with OrderItem** (order FK)
- **1→N with Payment** (order FK)
- **1→N with Complaint** (order FK)
- **1→N with OrderRating** (order FK)
- **1→N with ProductReview** (order FK)
- **1→1 with DigitalSignature** (order FK)
- **1→1 with RejectedOrder** (order FK, via PROTECT)
- **1→N with OrderEvent** (order FK)
- **N→M with PrepGroup** (via junction table)
- **1→N with Refund** (order FK)

---

#### `admins_orderitem`
**Purpose:** Line items in an order

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| order_id | INTEGER | FK → Order | Parent order |
| product_id | INTEGER | FK → Product (PROTECT) | Product ordered |
| quantity | INTEGER | - | Units ordered |
| subtotal | DECIMAL(10,2) | - | price × quantity |

**Relationships:**
- **N→1 with Order** (order_id FK, CASCADE)
- **N→1 with Product** (product_id FK, PROTECT — prevents product deletion if ordered)

---

### 5. Payments & Financial

#### `admins_payment`
**Purpose:** Payment transaction log; supports multiple payment attempts per order

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| order_id | INTEGER | FK → Order | Which order |
| payment_method | VARCHAR(20) | CHOICES | 'stripe', 'manual', 'cash' |
| status | VARCHAR(20) | CHOICES | 'pending', 'processing', 'succeeded', 'failed', 'cancelled', 'refunded' |
| amount | DECIMAL(10,2) | - | Amount attempted/paid |
| currency | VARCHAR(3) | DEFAULT 'MYR' | Always MYR |
| stripe_session_id | VARCHAR(255) | UNIQUE, NULL | Stripe checkout session |
| stripe_payment_intent_id | VARCHAR(255) | NULL | Stripe payment intent |
| stripe_charge_id | VARCHAR(255) | NULL | Stripe charge ID |
| stripe_customer_id | VARCHAR(255) | NULL | Stripe customer ID |
| payment_reference | VARCHAR(255) | NULL | Bank ref or transaction ID |
| proof_image | VARCHAR(255) | NULL | Upload path (manual proof) |
| created_at | TIMESTAMP | - | Payment initiated |
| paid_at | TIMESTAMP | NULL | Payment success time |
| last_webhook_event | VARCHAR(100) | NULL | Last Stripe webhook event type |
| webhook_event_timestamp | TIMESTAMP | NULL | Webhook timestamp |

**Indexes:**
- Composite: `(order_id, -created_at)`
- Composite: `(status, created_at)`
- `stripe_payment_intent_id`

**Payment Method Flows:**
1. **Stripe**: Customer redirected to Stripe Checkout; webhook confirms
2. **Manual** (DuitNow/Bank Transfer): Customer uploads payment proof; admin verifies
3. **Cash**: Recorded on delivery

**Relationships:**
- **N→1 with Order** (order_id FK, CASCADE)
- **1→N with Refund** (payment FK)

---

#### `admins_refund`
**Purpose:** Refund audit trail for all refund attempts (automatic or manual)

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| order_id | INTEGER | FK → Order | Which order |
| payment_id | INTEGER | FK → Payment, NULL | Original payment |
| complaint_id | INTEGER | FK → Complaint, NULL | If complaint-driven |
| amount | DECIMAL(10,2) | - | Refund amount |
| source | VARCHAR(30) | CHOICES | 'order_rejection', 'complaint', 'customer_cancellation', 'webhook' |
| status | VARCHAR(20) | CHOICES | 'pending', 'succeeded', 'failed', 'manual' |
| stripe_refund_id | VARCHAR(255) | - | Stripe refund ID |
| reason | TEXT | - | Why refunded |
| processed_by_id | INTEGER | FK → User, NULL | Admin who processed |
| created_at | TIMESTAMP | - | Refund initiated |
| processed_at | TIMESTAMP | NULL | Completion time |

**Indexes:**
- Composite: `(order_id, -created_at)`
- Composite: `(status, -created_at)`

**Refund Sources:**
- **order_rejection**: Auto-refund when admin rejects order
- **complaint**: Manual refund from complaint resolution
- **customer_cancellation**: Auto-refund when customer cancels
- **webhook**: From Stripe webhook (dispute, user initiation)

**Relationships:**
- **N→1 with Order** (order_id FK)
- **N→1 with Payment** (payment_id FK, nullable)
- **N→1 with Complaint** (complaint_id FK, nullable)
- **N→1 with User** (processed_by_id FK, nullable)

---

### 6. Digital Signatures & Receipts

#### `admins_digitalsignature`
**Purpose:** Cryptographic proof of receipt for paid/approved orders

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| order_id | INTEGER | FK → Order (OneToOne) | Which order |
| signature_hash | VARCHAR(64) | - | SHA-256 of PDF |
| pdf_path | VARCHAR(255) | - | File path to signed PDF |
| signature_value | TEXT | - | PyHanko embedded signature |
| timestamp | TIMESTAMP | - | When signed |

**Relationships:**
- **1→1 with Order** (order_id FK)

**Usage:**
- Created when order transitions to 'approved' status
- Used for receipt verification at `/menu/order/{id}/verify-receipt/`
- Enables non-repudiation: customer cannot deny receiving receipt

---

### 7. Complaints & Support

#### `admins_complaint`
**Purpose:** Customer complaints for order issues

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| order_id | INTEGER | FK → Order | Which order |
| customer_id | INTEGER | FK → User | Who complained |
| subject | VARCHAR(200) | - | Complaint title |
| message | TEXT | - | Full complaint text |
| evidence_image | VARCHAR(255) | NULL | Attached photo |
| status | VARCHAR(20) | CHOICES | 'pending', 'resolved' |
| action_taken | VARCHAR(50) | CHOICES, NULL | 'refund', 'remake', 'dismissed' |
| resolution_note | TEXT | NULL | Admin's notes |
| created_at | TIMESTAMP | - | Complaint filed |

**Indexes:**
- `status`
- Composite: `(order_id, status)`

**Relationships:**
- **N→1 with Order** (order_id FK)
- **N→1 with User** (customer_id FK)
- **1→N with SupportMessage** (complaint FK, PROTECT)
- **1→N with Refund** (complaint FK, nullable)

---

#### `admins_supportmessage`
**Purpose:** Encrypted thread of messages in a complaint (immutable audit trail)

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| complaint_id | INTEGER | FK → Complaint (PROTECT) | Thread parent |
| sender_id | INTEGER | FK → User | Who sent |
| body | TEXT | - | Fernet-encrypted message body |
| created_at | TIMESTAMP | - | Sent timestamp |
| is_read | BOOLEAN | DEFAULT FALSE | Read status |

**Indexes:**
- `created_at`
- Composite: `(complaint_id, created_at)`

**Special Behavior:**
- Immutable: cannot be deleted (raises PermissionError)
- Stored encrypted in database
- Decrypted on read

**Relationships:**
- **N→1 with Complaint** (complaint_id FK, PROTECT)
- **N→1 with User** (sender_id FK, SET_NULL)

---

### 8. Ratings & Reviews

#### `customers_orderrating`
**Purpose:** Overall satisfaction rating for completed orders

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| order_id | INTEGER | FK → Order (OneToOne) | Which order |
| customer_id | INTEGER | FK → User | Who rated |
| rating | INTEGER | - | 1–5 stars |
| comment | TEXT | - | Optional feedback |
| created_at | TIMESTAMP | - | When rated |

**Indexes:**
- Composite: `(customer_id, -created_at)`

**Relationships:**
- **1→1 with Order** (order_id FK)
- **N→1 with User** (customer_id FK)

---

#### `customers_productreview`
**Purpose:** Per-product reviews after order delivery

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| product_id | INTEGER | FK → Product | Which product |
| customer_id | INTEGER | FK → User | Who reviewed |
| order_id | INTEGER | FK → Order, NULL | Which order purchased in |
| rating | INTEGER | - | 1–5 stars |
| comment | TEXT | - | Optional review text |
| created_at | TIMESTAMP | - | When reviewed |

**Unique Constraint:** `(product_id, customer_id, order_id)` — one review per product per order

**Indexes:**
- Composite: `(product_id, -created_at)`

**Relationships:**
- **N→1 with Product** (product_id FK)
- **N→1 with User** (customer_id FK)
- **N→1 with Order** (order_id FK, SET_NULL)

---

### 9. Order Workflow & History

#### `admins_orderevent`
**Purpose:** Immutable log of every status change on an order

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| order_id | INTEGER | FK → Order | Which order |
| status | VARCHAR(50) | CHOICES | Status transitioned to |
| actor_id | INTEGER | FK → User, NULL | Who made change |
| note | TEXT | - | Optional reason/note |
| timestamp | TIMESTAMP | DEFAULT NOW | When changed |

**Indexes:**
- `timestamp`
- Composite: `(order_id, status)`
- Composite: `(order_id, -timestamp)`

**Example Flow:**
```
OrderEvent 1: pending → [system] → 2024-05-19 10:00
OrderEvent 2: approved → [admin_user] → 2024-05-19 10:15 (note: "Quick approval")
OrderEvent 3: prepared → [staff_user] → 2024-05-19 11:30
OrderEvent 4: ready_for_delivery → [staff_user] → 2024-05-19 12:00
OrderEvent 5: out_for_delivery → [system] → 2024-05-19 13:45
OrderEvent 6: delivered → [system] → 2024-05-19 15:20
```

**Relationships:**
- **N→1 with Order** (order_id FK, CASCADE)
- **N→1 with User** (actor_id FK, SET_NULL)

---

#### `admins_rejectionreason`
**Purpose:** Predefined reasons for order rejection (dropdown options)

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| code | VARCHAR(50) | UNIQUE | e.g., 'OUT_OF_STOCK' |
| reason_text | VARCHAR(200) | - | Display reason |
| category | VARCHAR(20) | CHOICES | 'system', 'customer', 'payment', 'inventory', 'address', 'other' |
| customer_message | TEXT | - | Message shown to customer |
| internal_note | TEXT | - | Admin-only notes |
| is_active | BOOLEAN | DEFAULT TRUE | Available for selection |
| created_at | TIMESTAMP | - | When created |
| updated_at | TIMESTAMP | - | When updated |

**Relationships:**
- **1→N with RejectedOrder** (rejection_reason FK, SET_NULL)

---

#### `admins_rejectedorder`
**Purpose:** Audit trail for rejected orders with snapshots

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| order_id | INTEGER | FK → Order (OneToOne, PROTECT) | Rejected order |
| rejection_reason_id | INTEGER | FK → RejectionReason, NULL | Why rejected |
| custom_reason | TEXT | - | Custom reason if typed |
| rejected_by_id | INTEGER | FK → User, NULL | Who rejected |
| rejected_at | TIMESTAMP | - | When rejected |
| order_total_amount | DECIMAL(10,2) | - | Snapshot of total |
| order_item_count | INTEGER | - | Snapshot of item count |
| customer_name | VARCHAR(255) | - | Snapshot of name |
| customer_email | VARCHAR(254) | - | Snapshot of email |
| customer_notified | BOOLEAN | DEFAULT FALSE | Notification sent? |
| notification_sent_at | TIMESTAMP | NULL | When notified |
| can_appeal | BOOLEAN | DEFAULT TRUE | Appeal allowed? |
| appeal_requested | BOOLEAN | DEFAULT FALSE | Appeal filed? |
| appeal_requested_at | TIMESTAMP | NULL | When appeal filed |
| appeal_notes | TEXT | - | Appeal details |

**Indexes:**
- Composite: `(order_id, -rejected_at)`
- Composite: `(rejection_reason_id, rejected_at)`
- Composite: `(customer_email, -rejected_at)`

**Relationships:**
- **1→1 with Order** (order_id FK, PROTECT)
- **N→1 with RejectionReason** (rejection_reason_id FK, SET_NULL)
- **N→1 with User** (rejected_by_id FK, SET_NULL)

---

#### `admins_prepgroup`
**Purpose:** Groups of orders prepared together (for batch processing)

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| group_id | VARCHAR(20) | UNIQUE | Format: OP-YYMMDD-## |
| created_at | TIMESTAMP | - | When group created |
| created_by_id | INTEGER | FK → User, NULL | Who created |

**Format Example:** `OP-260519-01`, `OP-260519-02`

**Relationships:**
- **N→M with Order** (via junction table `admins_prepgroup_orders`)
- **N→1 with User** (created_by_id FK, SET_NULL)

---

### 10. Audit & Compliance

#### `admins_auditlog`
**Purpose:** Immutable security audit trail with hash chaining for tamper detection

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| actor_id | INTEGER | FK → User, NULL | Who performed action |
| action_type | VARCHAR(50) | CHOICES, INDEX | Type of action |
| target_model | VARCHAR(50) | - | e.g., 'Order', 'Payment' |
| target_id | INTEGER | NULL | Which record affected |
| description | TEXT | - | Human-readable description |
| ip_address | INET | NULL | Client IP |
| user_agent | TEXT | - | Browser/client info |
| metadata | JSONB | DEFAULT {} | Extra JSON context |
| timestamp | TIMESTAMP | INDEX | Action time |
| chain_hash | VARCHAR(64) | INDEX | SHA-256 chained hash |

**Indexes:**
- `action_type`
- `timestamp`
- Composite: `(actor_id, -timestamp)`
- Composite: `(action_type, -timestamp)`
- Composite: `(target_model, target_id)`

**Action Types Tracked:**
- Order lifecycle: `order_created`, `order_approved`, `order_rejected`, etc.
- Payments: `payment_initiated`, `payment_verified`, `payment_rejected`
- Products: `product_added`, `product_edited`, `product_deleted`
- Auth: `login_success`, `login_failed`, `logout`
- Support: `complaint_submitted`, `support_message_sent`
- Inventory: `inventory_updated`
- Financial: `refund_issued`, `refund_failed`

**Hash Chaining:**
Each row's `chain_hash = SHA256(previous_hash | actor_id | action_type | ... | metadata)`  
Enables detection of tampering: any modification breaks the entire chain.

**Relationships:**
- **N→1 with User** (actor_id FK, SET_NULL)

---

#### `admins_notification`
**Purpose:** In-app notifications for users

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| recipient_id | INTEGER | FK → User | Who receives |
| title | VARCHAR(200) | - | Notification title |
| message | TEXT | - | Full message |
| link | VARCHAR(500) | - | Navigation URL |
| notification_type | VARCHAR(30) | CHOICES | Type of alert |
| is_read | BOOLEAN | INDEX, DEFAULT FALSE | Read status |
| created_at | TIMESTAMP | INDEX | When created |
| read_at | TIMESTAMP | NULL | When read |

**Notification Types:**
- `order_update`: Order status changes
- `payment`: Payment status changes
- `delivery`: Delivery updates
- `complaint`: Complaint resolution
- `admin_alert`: System alerts
- `system`: General system messages

**Indexes:**
- Composite: `(recipient_id, is_read, -created_at)` — for notification list

**Relationships:**
- **N→1 with User** (recipient_id FK, CASCADE)

---

### 11. Email & Marketing

#### `admins_emailtemplate`
**Purpose:** Reusable email templates for campaigns

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| name | VARCHAR(200) | - | Template name |
| subject | VARCHAR(500) | - | Email subject |
| body_html | TEXT | - | HTML body (supports template vars) |
| created_by_id | INTEGER | FK → User, NULL | Who created |
| created_at | TIMESTAMP | - | Creation date |
| updated_at | TIMESTAMP | - | Last update |
| is_active | BOOLEAN | DEFAULT TRUE | Available for use |

**Template Variables Supported:**
- `{{customer_name}}`
- `{{loyalty_tier}}`
- `{{last_order_date}}`
- `{{company_name}}`

**Relationships:**
- **N→1 with User** (created_by_id FK, SET_NULL)
- **1→N with EmailCampaign** (template FK)

---

#### `admins_emailcampaign`
**Purpose:** Records of bulk email campaigns sent

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| name | VARCHAR(200) | - | Campaign name |
| template_id | INTEGER | FK → EmailTemplate, NULL | Which template |
| sent_by_id | INTEGER | FK → User, NULL | Who sent |
| sent_at | TIMESTAMP | - | When sent |
| total_recipients | INTEGER | DEFAULT 0 | Targeted count |
| sent_count | INTEGER | DEFAULT 0 | Successfully sent |
| skipped_count | INTEGER | DEFAULT 0 | Skipped (opt-out) |
| failed_count | INTEGER | DEFAULT 0 | Failed |

**Relationships:**
- **N→1 with EmailTemplate** (template_id FK, SET_NULL)
- **N→1 with User** (sent_by_id FK, SET_NULL)
- **1→N with EmailLog** (campaign FK)

---

#### `admins_emaillog`
**Purpose:** One row per email sent/attempted

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| customer_id | INTEGER | FK → User | Recipient |
| campaign_id | INTEGER | FK → EmailCampaign, NULL | Which campaign |
| subject | VARCHAR(500) | - | Email subject |
| status | VARCHAR(10) | CHOICES | 'sent', 'failed', 'skipped' |
| reason | VARCHAR(300) | - | Failure reason |
| sent_at | TIMESTAMP | - | When attempted |

**Indexes:**
- Composite: `(customer_id, -sent_at)`

**Relationships:**
- **N→1 with User** (customer_id FK, CASCADE)
- **N→1 with EmailCampaign** (campaign_id FK, SET_NULL)

---

### 12. Analytics & Monitoring

#### `admins_pageview`
**Purpose:** Analytics log of page visits

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | INTEGER | PK | |
| path | VARCHAR(500) | INDEX | URL path visited |
| user_id | INTEGER | FK → User, NULL | Which user (if logged in) |
| session_key | VARCHAR(40) | INDEX | Session ID |
| ip_address | INET | NULL | Client IP |
| timestamp | TIMESTAMP | INDEX | When visited |

**Indexes:**
- `path`
- `session_key`
- `timestamp`
- Composite: `(path, -timestamp)`
- Composite: `(user_id, -timestamp)`

**Relationships:**
- **N→1 with User** (user_id FK, SET_NULL)

---

## Relationships Map

### One-to-One (1:1)
- **User ↔ CustomerProfile**: One profile per customer
- **Order ↔ DigitalSignature**: One signature per order (approved only)
- **Order ↔ OrderRating**: Customer rates order once (delivered only)
- **Order ↔ RejectedOrder**: One rejection record per order

### One-to-Many (1:N)
- **User → Order**: One customer places many orders
- **User → Favourite**: One customer has many favorites
- **User → OrderRating**: One customer rates many orders
- **User → ProductReview**: One customer reviews many products
- **User → Notification**: One user receives many notifications
- **User → AuditLog**: One actor performs many audit actions
- **Category → Product**: One category has many products
- **Product → OrderItem**: One product appears in many orders
- **Product → ProductReview**: One product gets many reviews
- **Product → Favourite**: One product is favorited by many customers
- **Order → OrderItem**: One order has many items
- **Order → Payment**: One order has multiple payment attempts
- **Order → Complaint**: One order can have multiple complaints
- **Order → OrderEvent**: One order has many status transitions
- **Order → ProductReview**: One order can generate many product reviews
- **Order → Refund**: One order can have multiple refunds
- **Complaint → SupportMessage**: One complaint has many messages
- **EmailTemplate → EmailCampaign**: One template used in many campaigns
- **EmailCampaign → EmailLog**: One campaign sends many emails

### Many-to-Many (N:M)
- **Product ↔ Allergy**: Products have multiple allergens; allergens are in multiple products
- **Order ↔ PrepGroup**: Orders belong to prep groups; groups contain multiple orders

---

## Data Flow

### Order Creation Flow

```
Customer Placement
    ↓
Order (status: 'pending')
    ↓
[Admin Review]
    ├→ Approved: Order → 'approved' + OrderEvent + AuditLog
    │   ↓
    │  [Payment Check]
    │   ├→ Stripe/Manual: Order → 'pending_payment' + Payment
    │   │   ├→ Payment Webhook: Payment → 'succeeded' + DigitalSignature
    │   │   │   ↓
    │   │   │  Order → 'pending' (awaiting staff prep approval)
    │   │   │
    │   │   └→ Manual Proof: Payment stays 'pending' until admin verifies
    │   │
    │   └→ Cash: Order → 'prepared' (skip payment stage)
    │
    └→ Rejected: Order → 'rejected' + RejectedOrder + Refund (if paid) + AuditLog
```

### Fulfillment Flow (After Payment)

```
pending → prepared → ready_for_delivery → out_for_delivery → delivered
  ↓                                                                ↓
OrderEvent (pending)                                       OrderRating (optional)
AuditLog (order_created)                                  ProductReview (per item)
                    ↓
              OrderEvent (prepared)
              AuditLog (order_prepared)
                    ↓
              OrderEvent (ready_for_delivery)
              AuditLog (order_ready_for_delivery)
                    ↓
              OrderEvent (out_for_delivery)
              AuditLog (order_out_for_delivery)
              Tracking → Customer
                    ↓
              OrderEvent (delivered)
              AuditLog (order_delivered)
              DigitalSignature → Verify Receipt
              CustomerProfile → recalculate()
```

### Complaint & Refund Flow

```
Customer Submits Complaint
    ↓
Complaint (status: 'pending')
    ↓
[Messages (encrypted)]
    ├→ SupportMessage (customer → admin)
    └→ SupportMessage (admin → customer)
    ↓
[Admin Decision]
    ├→ Refund: 
    │   ├→ If Stripe: Stripe refund → Payment 'refunded' → Refund 'succeeded'
    │   ├→ If Manual: Refund 'manual' → Marked for manual processing
    │   └→ AuditLog (refund_issued or refund_failed)
    │
    ├→ Remake:
    │   └→ Order (new) with is_remake=True, remake_of=original_order
    │
    └→ Dismissed:
        └→ Complaint 'resolved', AuditLog (complaint_resolved)
```

### Payment Verification Flow (Manual Method)

```
Customer Uploads Proof
    ↓
Payment (status: 'pending', proof_image: uploaded)
    ↓
[Admin Reviews]
    ├→ Verified:
    │   ├→ Payment → 'succeeded', paid_at = now
    │   ├→ Order → 'pending' (moved to prep queue)
    │   ├→ DigitalSignature → Created
    │   ├→ Notification → "Payment approved"
    │   └→ AuditLog (payment_verified)
    │
    └→ Rejected:
        ├→ Payment → 'failed'
        ├→ Notification → "Payment rejected, resubmit"
        └→ AuditLog (payment_rejected)
```

---

## Business Logic

### Loyalty Tier Calculation

**Trigger:** After every delivered order or manual recalculation

```python
total_spent = Sum of all 'approved' or 'delivered' orders

if total_spent >= 5000:
    tier = 'platinum'
elif total_spent >= 2000:
    tier = 'gold'
elif total_spent >= 500:
    tier = 'silver'
else:
    tier = 'bronze'
```

### Payment Status Rules

**Valid Transitions:**
- `pending` → `processing` (after Stripe session created or manual upload)
- `processing` → `succeeded` (webhook or manual verification)
- `processing` → `failed` (webhook or manual rejection)
- `pending` → `cancelled` (customer or system action)
- `succeeded` → `refunded` (refund issued)

### Order Lifecycle Rules

**Immutable Rules:**
- Once `delivered`, order cannot change status
- Once `rejected`, order cannot change status
- Once `cancelled` by customer, order cannot change status

**Conditional Rules:**
- `pending` → `approved` only by sales_admin or manager
- `approved` → `prepared` only if order items still in stock
- Cannot approve if no payment method available
- Cannot deliver without tracking number (for courier deliveries)

### Inventory Management

**Stock Updates:**
- Stock decreases when OrderItem created
- Stock increases when Order rejected or cancelled
- Cannot place order if product out of stock
- Can hide product from customers with `is_available = False`

### Audit Trail Integrity

**Chain Hash Verification:**
```python
for each AuditLog entry in order:
    expected_hash = SHA256(previous_entry.chain_hash | actor_id | action_type | ...)
    if entry.chain_hash != expected_hash:
        # Tampering detected!
        raise IntegrityError()
```

---

## Key Statistics & Queries

### Sample Queries

**Recent Orders by Customer:**
```sql
SELECT * FROM admins_order 
WHERE customer_id = ? 
ORDER BY created_at DESC 
LIMIT 10;
```

**Loyalty Tier Distribution:**
```sql
SELECT loyalty_tier, COUNT(*) 
FROM customers_customerprofile 
GROUP BY loyalty_tier;
```

**Revenue by Day:**
```sql
SELECT DATE(created_at), SUM(total_amount) 
FROM admins_order 
WHERE status IN ('approved', 'delivered') 
GROUP BY DATE(created_at);
```

**Complaints by Status:**
```sql
SELECT status, COUNT(*) 
FROM admins_complaint 
GROUP BY status;
```

**Payment Success Rate (Manual):**
```sql
SELECT 
  status, 
  COUNT(*) as count
FROM admins_payment 
WHERE payment_method = 'manual' 
GROUP BY status;
```

---

## Database Indexing Strategy

### Primary Indexes (Created)
- All foreign keys (automatic in Django)
- `User.role` — user list filtering
- `Product.is_available` — product catalog filtering
- `Order.status` — order dashboard filtering
- `Order.is_priority` — priority queue
- `Payment.stripe_payment_intent_id` — webhook lookups
- `Payment.stripe_session_id` (unique) — checkout recovery
- `Complaint.status` — complaint dashboard
- `AuditLog.action_type` — audit filtering
- `AuditLog.timestamp` — time-range queries
- `Notification.is_read` — unread count
- `SupportMessage.created_at` — message history

### Composite Indexes (Performance Tuning)
- `(Order.status, -Order.created_at)` — dashboard lists
- `(Order.customer_id, -Order.created_at)` — customer order history
- `(Order.is_priority, Order.status)` — priority queue
- `(CustomerProfile.loyalty_tier, -CustomerProfile.total_spent)` — tier reports
- `(Payment.order_id, -Payment.created_at)` — payment history per order
- `(AuditLog.actor_id, -AuditLog.timestamp)` — user activity
- `(AuditLog.action_type, -AuditLog.timestamp)` — action history
- `(PageView.path, -PageView.timestamp)` — analytics

---

## Constraints & Validations

### Unique Constraints
- `User.email` — no duplicate emails
- `User.username` — no duplicate logins
- `Payment.stripe_session_id` — Stripe sessions are unique
- `Favourite(customer_id, product_id)` — one favorite per product per customer
- `ProductReview(product_id, customer_id, order_id)` — one review per product per order
- `RejectionReason.code` — unique reason codes
- `PrepGroup.group_id` — unique prep group ID

### Foreign Key Constraints

**CASCADE (delete child if parent deleted):**
- Order → OrderItem
- Order → Payment
- Order → Complaint
- Complaint → SupportMessage
- User → CustomerProfile
- EmailCampaign → EmailLog
- User → Notification
- Order → OrderEvent
- Order → Refund

**SET_NULL (nullify FK if parent deleted):**
- Order.approved_by_id
- RejectedOrder.rejected_by_id
- EmailCampaign.template_id
- Most "created_by" or "processed_by" fields

**PROTECT (prevent deletion if child exists):**
- Product (if has OrderItem records)
- Order (if has RejectedOrder with PROTECT)
- Complaint → SupportMessage

### Field Validations

**Order Status:**
- Must be one of: pending, approved, prepared, ready_for_delivery, out_for_delivery, delivered, rejected, cancelled, pending_payment
- Status transitions are one-way (mostly)

**Payment Status:**
- Must be one of: pending, processing, succeeded, failed, cancelled, refunded

**Loyalty Tier:**
- Must be one of: bronze, silver, gold, platinum
- Auto-calculated from total_spent

---

## Migration & Backup Strategy

### Critical Tables for Backup
1. **Order** — business-critical; legal requirements for financial records
2. **Payment** — financial audit trail; PCI compliance
3. **AuditLog** — security audit trail; immutable for compliance
4. **User** — authentication and authorization
5. **CustomerProfile** — CRM data; business value
6. **DigitalSignature** — receipt proof; legal/compliance
7. **Complaint** — dispute resolution history

### Non-Critical (Can Be Archived)
- PageView — analytics (can truncate after 1 year)
- EmailLog — campaign history (can truncate after 6 months)
- Notification — in-app messages (can truncate after 3 months)

---

## Notes for ERD & Visualization

### Table Grouping by Domain
1. **Authentication & Users**: User, CustomerProfile
2. **Products**: Category, Product, Allergy
3. **Orders & Fulfillment**: Order, OrderItem, OrderEvent, PrepGroup
4. **Payments**: Payment, DigitalSignature
5. **Customer Service**: Complaint, SupportMessage, OrderRating, ProductReview
6. **Financials**: Refund, RejectedOrder, RejectionReason
7. **Audit & Compliance**: AuditLog, Notification
8. **Marketing**: EmailTemplate, EmailCampaign, EmailLog
9. **Analytics**: PageView
10. **Favorites & Engagement**: Favourite

### Color Coding Suggestions
- **Green**: User-facing (Customers interact)
- **Blue**: Business operations (Admin/Staff only)
- **Red**: Financial & Compliance (Critical)
- **Orange**: Audit & History (Immutable)
- **Purple**: Marketing & Analytics

---

**Document Version:** 1.0  
**Last Generated:** 2026-05-19  
**Database Engine:** PostgreSQL  
**Django Version:** 6.0.1
