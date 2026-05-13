# Critical Files to Share with AI Agent
## For Project Report Update & Code Review

**Last Updated:** May 14, 2026

---

## File Sharing Guide

### Tier 1: MUST HAVE (Core Implementation)

#### 1. admins/models.py
**Why:** Defines ALL data models for order processing, signatures, audit trails, notifications
**Contains:** 
- Order model (status lifecycle)
- Payment model
- Complaint model
- AuditLog model (9 action types, IP tracking)
- Notification model (types, read status)
- OrderDocument (signed PDF storage)
- CustomerProfile (loyalty tiers)

**Critical for:** Chapter 4 (Database Design), Chapter 2 (Data Integrity)

#### 2. customers/models.py  
**Why:** Customer-facing models and data structures
**Contains:**
- Custom User model (role field)
- Product model (categories, allergies)
- Order from customer perspective
- Cart/ordering logic

**Critical for:** User authentication, product catalog design

#### 3. admins/views.py
**Why:** All administrative logic - order processing, signatures, analytics
**Contains:**
- dashboard_home() - role routing
- manager_analytics_view() - executive dashboard
- sales_admin_dashboard() - operations dashboard
- approve_order() / reject_order() - approval logic
- mark_order_delivered() - fulfillment
- audit_log_list() - audit display
- customers_crm_list() - customer management
- customer_crm_detail() - individual customer view

**Critical for:** Chapter 5 (Implementation), workflow documentation

#### 4. customers/views.py
**Why:** Customer-facing operations
**Contains:**
- menu/product browsing
- cart operations
- order submission
- OTP verification
- order status tracking
- notification handling

**Critical for:** Use cases, customer workflow

#### 5. admins/notifications.py
**Why:** Core utilities for audit logging and notifications
**Contains:**
- get_client_ip() - IP extraction
- log_audit() - create audit log entries
- notify() - send individual notifications
- notify_admins() - broadcast to staff

**Critical for:** Understanding audit trail implementation, Chapter 2 (non-repudiation)

#### 6. zarlyOs/urls.py
**Why:** Root URL configuration with role-based routing
**Contains:**
- home_redirect() - redirect customers/admins to correct dashboards
- URL mounting for both apps (/dashboard/*, /menu/*)
- Authentication endpoints

**Critical for:** Architecture overview, authentication flow

---

### Tier 2: ESSENTIAL (Design & Structure)

#### 7. templates/admin_base.html
**Why:** Admin interface structure, unified sidebar design
**Contains:**
- Dark blue gradient sidebar (all admin users)
- Role-based navigation items
- Manager vs Sales Admin menu sections
- CSS for sidebar styling (recently unified)
- User profile section

**Critical for:** UI/UX documentation, design consistency explanation

#### 8. templates/base.html
**Why:** Customer interface structure
**Contains:**
- Orange gradient sidebar (customer users)
- Navigation for store front
- User profile and notifications
- CSS for customer sidebar

**Critical for:** Comparing admin vs customer UX

#### 9. static/css/style.css
**Why:** Complete styling system including unified sidebar design
**Contains:**
- Color scheme and CSS variables
- Sidebar styles for both templates
- Responsive design rules
- Component styling

**Critical for:** Design decisions explanation

#### 10. admins/auth_utils.py
**Why:** Role-based access control decorators
**Contains:**
- @sales_admin_required decorator
- @manager_required decorator
- Authentication checks

**Critical for:** Security architecture, access control

#### 11. customers/auth_utils.py
**Why:** Customer authentication utilities
**Contains:**
- Login/registration logic
- OTP verification
- Session management

**Critical for:** Authentication flow, security measures

#### 12. requirements.txt
**Why:** All project dependencies with versions
**Contains:**
- Django version
- PyHanko (digital signatures)
- ReportLab/fpdf2 (PDF generation)
- PostgreSQL driver
- All other libraries

**Critical for:** Technology stack documentation, reproducibility

---

### Tier 3: IMPORTANT (Feature Implementation)

#### 13. templates/admins/manager_dashboard.html
**Why:** Executive dashboard design and layout
**Contains:**
- Revenue cards (today, week, month, all-time)
- Order statistics
- Customer tier distribution
- Complaint overview
- Audit log preview

**Critical for:** Manager feature documentation

#### 14. templates/admins/sales_admin_dashboard.html
**Why:** Operations dashboard for staff
**Contains:**
- Order approval interface
- Pending orders list
- Order details view
- Action buttons (approve/reject)

**Critical for:** Sales admin workflow

#### 15. customers/payment_utils.py
**Why:** Payment processing logic
**Contains:**
- Payment verification
- Receipt generation
- Transaction handling

**Critical for:** Payment workflow explanation

#### 16. customers/stripe_utils.py
**Why:** Stripe integration
**Contains:**
- Stripe API calls
- Payment initiation
- Webhook handling

**Critical for:** External integration documentation

---

### Tier 4: REFERENCE (Documentation & Configuration)

#### 17. manage.py
**Why:** Django project entry point
**Contains:** Project configuration settings

#### 18. pytest.ini
**Why:** Testing configuration
**Contains:** Test settings and plugins

#### 19. docker-compose.yml
**Why:** Containerization setup
**Contains:** PostgreSQL and application container configuration

#### 20. docs/PAYMENT_SYSTEM.md
**Why:** Existing payment system documentation
**Contains:** Payment workflow details

#### 21. docs/IMPLEMENTATION_COMPLETE.md
**Why:** Feature checklist and completion status
**Contains:** Which features are done vs pending

#### 22. docs/ROLE_BASED_LOGIN_DOCUMENTATION.md
**Why:** Authentication system documentation
**Contains:** User role setup and login flows

---

## How to Organize File Sharing

### Option A: Create a Sharing Directory
```
Create folder: ZarlyHQ/FOR_AI_AGENT/

Tier 1 (Copy All):
- admins/models.py
- customers/models.py
- admins/views.py
- customers/views.py
- admins/notifications.py
- zarlyOs/urls.py

Tier 2 (Copy All):
- templates/admin_base.html
- templates/base.html
- static/css/style.css
- admins/auth_utils.py
- customers/auth_utils.py
- requirements.txt

Tier 3 (Copy As Needed):
- templates/admins/manager_dashboard.html
- templates/admins/sales_admin_dashboard.html
- customers/payment_utils.py
- customers/stripe_utils.py

Tier 4 (Copy As Reference):
- manage.py
- pytest.ini
- docker-compose.yml
- docs/*.md

+ Include this file: PROJECT_CONTEXT.md
```

### Option B: Share as Text Dump
Concatenate all files in order and provide as single text file with section headers.

### Option C: Use Git
```
git bundle create zarly-project.bundle HEAD
# Share the bundle, AI can extract full repo state
```

---

## What to Tell Your AI Agent

### Instruction Template
```
I'm developing a Django-based secure ordering system for a food business. 

Here's the current project context: [include PROJECT_CONTEXT.md]

Here are the core implementation files: [include Tier 1 files]

Critical architectural files: [include Tier 2 files]

Feature implementations: [include Tier 3 files]

Please:
1. Review all code against the project requirements in the report
2. Verify technical accuracy of claims in Chapter 2 (Literature Review)
3. Update Chapter 3 (Methodology) based on actual implementation
4. Complete Chapter 4 (System Design) with architecture diagrams
5. Update Chapter 5 (Implementation) with code snippets
6. Generate Chapter 6 (Conclusion) based on project status
7. Create any missing diagrams (ERD, DFD, sequence diagrams, use cases)
8. Identify any gaps between requirements and implementation
9. Suggest improvements or missing features
10. Fix any technical inaccuracies in the report
```

---

## Key Information to Emphasize to AI Agent

1. **Project Scope:** Signature-based ordering system for SMEs, not a general e-commerce solution
2. **Security Focus:** Non-repudiation and integrity via digital signatures are PRIMARY requirements
3. **Role Separation:** Customer, Sales Admin, and Manager have completely different workflows
4. **Database State:** 3 models not yet migrated (AuditLog, Notification, CustomerProfile)
5. **Current Status:** Code ~90% complete, migrations and testing ~10% complete
6. **Report Status:** Chapters 1-2 complete, Chapters 3-6 need writing/updating
7. **Critical Technologies:** PyHanko (signatures), SHA-256 (integrity), PostgreSQL (ACID), Django (framework)

---

## Verification Checklist for AI Agent

After AI agent reviews code, verify it mentions:

- [ ] Custom User model with role field
- [ ] Three user roles (customer, sales_admin, manager)
- [ ] Digital signature workflow using PyHanko
- [ ] SHA-256 hashing for integrity
- [ ] Self-signed X.509 certificates (PKI)
- [ ] AuditLog model with 9+ action types
- [ ] ACID compliance via PostgreSQL
- [ ] Role-based decorators for access control
- [ ] OTP verification for sensitive operations
- [ ] Unified sidebar design (consistent across both user types)
- [ ] Manager vs Sales Admin dashboard separation
- [ ] Loyalty tier system in CustomerProfile
- [ ] PDF generation and signing workflow

---

## Expected Output from AI Agent

After review, AI should provide:

1. ✅ Updated/completed Chapters 3-6
2. ✅ Corrected/enhanced Chapter 2 with code references
3. ✅ Architecture diagrams (C4, ERD, DFD, sequence)
4. ✅ Use case diagrams for each user role
5. ✅ Identified gaps or inconsistencies
6. ✅ Suggested test cases and validation approach
7. ✅ Recommendations for improvement
8. ✅ Deployment and scalability considerations

---

**TL;DR - Minimum to Share:**
- PROJECT_CONTEXT.md (this project overview)
- All Tier 1 files (6 files - core logic)
- All Tier 2 files (6 files - structure & design)
- requirements.txt (dependencies)

**That's 13 files containing ~95% of the context needed for accurate report updates.**
