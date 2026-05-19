# Zarly BigFood - Signature Based Online Ordering System
## Project Context & Implementation Status

**Project Title:** Secure Ordering System for Zarly BigFood SDN BHD  
**Student:** Rusdi Bin Abd Rashid (AI230025)  
**Supervisor:** Dr Sofia Najwa Binti Ramli  
**Academic Year:** 2025/2026 - 01  
**Date:** May 14, 2026

---

This system is created as part of a final year cybersecurity degree project's student. The main purpose is to have a working system, that can be deployed and tested for security. It is important to go through proper design phase when working to complete the system

## 1. Project Overview

### Purpose
A signature-based online ordering system that provides:
- **Authenticity:** OTP-based order verification and digital signatures using Zarly HQ's private key
- **Integrity:** Cryptographic hashing (SHA-256) to ensure orders remain tamper-proof
- **Non-repudiation:** Digital signatures prevent customers and company from denying transactions
- **Legal Compliance:** Cryptographically-verified documents for dispute resolution

### Business Problem Solved
Replacing insecure manual order intake methods (verbal agreements, WhatsApp, Instagram DMs) with:
- Centralized, auditable web platform
- Tamper-proof order records
- Professional, secure customer experience
- Legal proof of transaction for both parties



---

## 2. Technical Architecture

### Framework & Technology Stack
```
Backend:        Django 6.0.1 (Python)
Database:       PostgreSQL (ACID-compliant)
Frontend:       Bootstrap 5 + custom CSS
Authentication: Session-based + custom decorators
Cryptography:   PyHanko (digital signatures), SHA-256 hashing
PDF Generation: ReportLab/fpdf2
Environment:    Windows 11, PyCharm IDE
```

### Project Structure
```
ZarlyHQ/
├── admins/                    # Admin/staff operations app
│   ├── models.py             # Order, Payment, Complaint, AuditLog, Notification, etc.
│   ├── views.py              # Dashboard, order processing, signature verification
│   ├── auth_utils.py         # Role-based decorators (@sales_admin_required, @manager_required)
│   ├── notifications.py      # Audit logging & notification utilities
│   ├── urls.py
│   ├── admin.py
│   └── migrations/
│
├── customers/                 # Customer storefront app
│   ├── models.py             # User (custom), Order, Product, CustomerProfile
│   ├── views.py              # Menu, cart, order submission, notifications
│   ├── auth_utils.py         # Authentication utilities
│   ├── payment_utils.py      # Payment processing
│   ├── stripe_utils.py       # Stripe integration
│   ├── urls.py
│   └── migrations/
│
├── templates/
│   ├── base.html             # Customer base template (orange gradient sidebar)
│   ├── admin_base.html       # Admin base template (dark blue sidebar - unified design)
│   ├── registration/
│   ├── admins/               # Admin-specific templates
│   │   ├── manager_dashboard.html
│   │   ├── manager_analytics.html
│   │   └── sales_admin_dashboard.html
│   └── customers/            # Customer-facing templates
│       ├── menu.html
│       ├── checkout.html
│       ├── orders.html
│       └── notifications.html
│
├── static/
│   └── css/style.css         # Unified sidebar styles for both templates
│
├── zarlyOs/                  # Main project settings
│   ├── settings.py
│   ├── urls.py              # Root URL routing with role-based redirects
│   └── wsgi.py
│
├── manage.py
├── requirements.txt
├── pytest.ini
├── docker-compose.yml
└── secure_keys/             # Private key storage (confidential)
```

---

## 3. User Roles & Access Control

### Three Primary User Roles

**1. Customer (Public User)**
- Register with email/phone verification
- Browse products
- Add items to cart
- Submit orders with OTP verification
- View order status and history
- Access complaint/support interface
- Profile management (loyalty tier, preferences)

**2. Sales Administrator (Operational Staff)**
- View all pending orders
- Approve/reject orders
- Generate digitally-signed PDF order documents
- Verify order integrity (tamper detection)
- Access secure PDF storage
- View customer CRM data
- Manage inventory
- Generate audit logs

**3. Manager (Executive/Business Oversight)**
- All Sales Admin capabilities
- Business analytics dashboard
- Revenue reports (daily/weekly/monthly)
- Complete customer database access
- Order volume and status breakdown
- Complaint resolution overview
- Full audit log access
- CRM data management

**Special Role:**
- **Superuser:** Full access to all areas (for development/administration)

### Authentication
- Email + Password (customers)
- OTP verification for sensitive operations
- Session-based authentication (shared across browser tabs)
- Role field in custom User model: `['customer', 'sales_admin', 'manager']`

---

## 4. Key Implementation Details

### Digital Signature Workflow

```
Order Submission Flow:
1. Customer creates order → OTP sent to phone
2. Customer enters OTP → Order locked as submitted
3. Sales Admin reviews order
4. Admin approves → System generates PDF of order details
5. PDF signed using Zarly HQ's private key
6. Signature embedded in PDF (PAdES standard-compliant)
7. SHA-256 hash generated for integrity verification
8. Signed PDF stored securely in database
9. Hash stored for future integrity checks
10. Customer receives confirmation with signed document

Integrity Verification:
- Admin can re-verify any signed document
- System recalculates SHA-256 hash
- Compares with stored hash
- Detects any tampering instantly
- Cryptographic proof of transaction
```

### Security Mechanisms

**Cryptographic:**
- **SHA-256:** Order document hashing (one-way, collision-resistant)
- **RSA Asymmetric Encryption:** Digital signatures (Zarly HQ private key)
- **X.509 Certificates:** Self-signed, stored securely
- **PAdES Standard:** PDF signature compliance (legal validity)

**Data Protection:**
- ACID-compliant database (PostgreSQL with MVCC)
- SQL injection prevention (Django ORM auto-escaping)
- CSRF protection (Django middleware)
- Password hashing (Django built-in)
- Session security (secure cookies)
- Encrypted data at rest (when applicable)

**Audit Trail:**
- AuditLog model tracks all actions:
  - Order creation/approval/rejection
  - Payment events
  - Document signatures
  - Login attempts
  - Database modifications
- Metadata includes: IP address, user agent, timestamp, actor
- Indexes for fast querying (actor+timestamp, action_type+timestamp)

### Database Models (Current State)

**Committed Models:**
- `User` (custom) - email, username, role, is_corporate_whitelisted, etc.
- `Product` - menu items with categories, allergies, pricing
- `Order` - customer orders with status (pending, approved, rejected, delivered)
- `Payment` - payment records linked to orders
- `Complaint` - customer support tickets
- `OrderDocument` - digitally signed PDF storage
- `Receipt` - payment receipt records

**Uncommitted Models (Code Complete, Awaiting Migration):**
- `AuditLog` - 9 action types, cryptographic tracking, IP/user-agent capture
- `Notification` - in-app notifications (order updates, payment, delivery, admin alerts)
- `CustomerProfile` - loyalty tier system (bronze/silver/gold/platinum), total spent tracking, admin notes

---

## 5. Recent Changes & Current State

### Sidebar Design (Unified - May 13, 2026)
- **Before:** Inconsistent fonts, sizes, spacing between admin and customer sidebars
- **After:** 
  - Both use Inter font family
  - Consistent font-size (0.8rem menu items, 0.7rem titles)
  - Unified spacing (0.5rem padding, 0.6rem gaps)
  - 32px avatars, 18px icons
  - Same scrollbar styling (6px, transparent track)

**Files Modified:**
- `admin_base.html` - Admin sidebar CSS (dark blue gradient: #0f172a → #1e293b)
- `style.css` - Customer sidebar CSS (orange gradient: #ff9933 → #b84e10)

### Dashboard Separation (Completed)
- **Managers** → Redirected to manager_analytics_view (executive overview)
- **Sales Admins** → Redirected to sales_admin_dashboard (operations focus)
- **Superusers** → Full access to both

**Files Modified:**
- `admins/views.py` - dashboard_home() routing logic
- `zarlyOs/urls.py` - home_redirect() logic
- `templates/admins/manager_dashboard.html` - New executive-focused layout

---

## 6. Outstanding Work & Known Issues

### Critical (Blocking Project Completion)

1. **Database Migrations Not Applied**
   - [ ] Generate migrations: `python manage.py makemigrations`
   - [ ] Apply migrations: `python manage.py migrate`
   - Affects: AuditLog, Notification, CustomerProfile models

2. **Hardcoded Notification Links**
   - [ ] Notification links missing `/menu/` prefix for customer routes
   - [ ] Need to use Django URL reversing instead of hardcoded paths
   - Example: `customer_orders` should be `/menu/orders/` not `/orders/`

3. **Customer Notifications Template**
   - [ ] `customers/notifications.html` not yet created
   - [ ] Required view: `notifications_list()`, `notification_open()`
   - [ ] Need pagination (100 per page)

### Medium Priority

4. **Audit Logging Integration**
   - [ ] Log all order lifecycle events (creation, approval, rejection, delivery)
   - [ ] Track payment state changes
   - [ ] Log document signature events
   - [ ] Integration needed in `admins/views.py` and `customers/views.py`

5. **Notification Broadcasting**
   - [ ] notify_admins() utility for bulk notifications to staff
   - [ ] Event-driven notifications (order submitted, payment processed, complaint filed)

6. **Test Coverage**
   - [ ] Unit tests for digital signature generation/verification
   - [ ] Integration tests for order workflow
   - [ ] Security tests (SQL injection, CSRF, authentication)
   - [ ] Performance tests for PDF generation at scale

### Low Priority (UX/Polish)

7. **Error Messages**
   - [ ] User-friendly error messages for failed signature operations
   - [ ] Validation messages for order submission

8. **PDF Styling**
   - [ ] Professional invoice template for signed PDFs
   - [ ] Company branding and logo integration

---

## 7. Testing Status

✅ **Completed:**
- All templates pass Django syntax validation
- Admin/customer sidebars render without errors
- Role-based routing works (manager → analytics, sales_admin → dashboard)
- Python files pass linting

❌ **Not Yet Tested:**
- Digital signature generation and verification
- Integrity check functionality
- Notification delivery system
- Audit log creation and querying
- End-to-end order workflow
- Payment integration
- PDF document generation

---

## 8. Compliance with Project Requirements

### Objective 1: Secure System Architecture ✅
- Public Key Infrastructure (PKI) implemented with self-signed certificates
- SHA-256 hashing for data integrity
- Digital signatures for non-repudiation
- ACID-compliant database

### Objective 2: Functional Web Application ✅ (90% Complete)
- Django web framework implemented
- Customer-facing storefront
- Admin dashboard for order processing
- Manager analytics views
- Role-based access control

### Objective 3: Testing & Evaluation ⚠️ (Pending)
- Functional testing framework in place (pytest.ini)
- Security testing required
- User acceptance testing needed
- Performance evaluation pending

---

## 9. Report Requirements Status

### Chapter 1: Introduction & Problem Statement ✅
- Project background clearly defined
- Problem statement addresses insecure order intake methods
- Objectives and scope documented
- Expected outcomes outlined
- Project significance explained

### Chapter 2: Literature Review ✅
- CIA Triad security framework explained
- Cryptographic mechanisms (PKI, hashing, digital signatures) documented
- Technology choices justified (Django, PostgreSQL, PyHanko, ReportLab)
- Comparative analysis of existing solutions (Shopee, Lapasar, Shopify+DocuSign)
- Gap analysis showing why custom system is needed

### Chapter 3: Methodology (To Be Written)
- Research methodology
- Requirements analysis for each user role
- System design approach
- Development tools and frameworks
- Testing strategy

### Chapter 4: System Design & Analysis (Partial)
- Database schema partially documented
- User role requirements defined
- Module descriptions in scope section
- Architecture diagrams needed

### Chapter 5: Implementation & Testing (Partial)
- Core implementation complete
- Integration incomplete
- Testing not yet conducted
- Results to be documented

### Chapter 6: Conclusion & Recommendations (Not Yet Written)

---

## 10. Files Critical for Report Updates

### Priority 1 (Essential Context)
1. **admins/models.py** - All data models, field definitions
2. **customers/models.py** - Customer and product models
3. **admins/views.py** - All business logic for admin operations
4. **customers/views.py** - All customer-facing logic
5. **zarlyOs/urls.py** - URL routing and role-based redirects
6. **admins/notifications.py** - Audit logging and notification utilities

### Priority 2 (Architecture & Design)
7. **templates/admin_base.html** - Admin interface structure
8. **templates/base.html** - Customer interface structure
9. **static/css/style.css** - Complete styling system
10. **admins/auth_utils.py** - Authentication decorators and utilities

### Priority 3 (Supporting)
11. **requirements.txt** - All dependencies and versions
12. **manage.py** - Django configuration
13. **customers/auth_utils.py** - Customer authentication
14. **customers/payment_utils.py** - Payment processing
15. **customers/stripe_utils.py** - Stripe integration

### Priority 4 (Documentation)
16. **docs/PAYMENT_SYSTEM.md** - Any existing documentation
17. **docs/IMPLEMENTATION_COMPLETE.md** - Feature checklist
18. **docs/ROLE_BASED_LOGIN_DOCUMENTATION.md** - Authentication docs

---

## 11. AI Agent Instructions for Report Update

When sharing this context with an AI agent for report fixes/updates:

1. **Focus Areas:**
   - Verify all technical details match current implementation
   - Ensure cryptographic explanations align with actual code (PyHanko, SHA-256)
   - Confirm database model descriptions match models.py
   - Check user role descriptions match decorators and views

2. **Completeness Check:**
   - Chapter 3-6 writing status
   - Missing technical diagrams (architecture, data flow, sequence diagrams)
   - Test results and performance metrics (when available)

3. **Accuracy Verification:**
   - Cross-reference all library versions with requirements.txt
   - Validate all URLs and routing described in scope
   - Confirm table data in Chapter 2 (comparison with existing systems)

4. **Generate Missing Sections:**
   - Architecture diagrams (C4 model or similar)
   - Entity-Relationship Diagram (ERD)
   - Use case diagrams for each user role
   - Sequence diagrams for critical workflows
   - Testing methodology and test cases

---

## 12. Quick Reference

### Key Technical Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Django | Built-in security, ORM, large ecosystem |
| Database | PostgreSQL | ACID compliance, MVCC, reliability |
| Cryptography | PKI + SHA-256 + RSA | Industry standard, legally valid signatures |
| PDF Signing | PyHanko | PAdES compliant, standard-verifiable |
| Frontend | Bootstrap 5 | Responsive, professional, accessible |

### Security Checklist
- [x] CSRF protection (Django middleware)
- [x] SQL injection prevention (ORM)
- [x] Password hashing
- [x] Session security
- [x] Role-based access control
- [ ] Audit logging (code ready, not yet integrated)
- [ ] Encryption at rest (partial)
- [ ] HTTPS enforcement (production)

### Development Checklist
- [x] Database models designed
- [x] Views and logic implemented
- [x] Templates created and unified
- [x] Authentication system
- [ ] Migrations applied
- [ ] Full test coverage
- [ ] Production deployment
- [ ] User documentation

---

**Last Updated:** May 14, 2026  
**Status:** Active Development  
**Next Milestone:** Apply database migrations & complete integration testing
