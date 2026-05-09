# Role-Based Login System Implementation

## Overview
A comprehensive role-based access control (RBAC) system has been implemented in the Zarly BigFood application, featuring unified login, automatic dashboard routing, and role-specific permissions.

## System Roles

### 1. **Customer** 
- **Access**: Product menu, shopping cart, order placement
- **Dashboard**: Product list page
- **Capabilities**:
  - Browse and filter products by category/allergies
  - Add items to cart
  - Place orders
  - Track order status
  - Upload payment proof
  - View complaints

### 2. **Sales Administrator**
- **Access**: Order and inventory management
- **Dashboard**: Sales Admin Dashboard
- **Capabilities**:
  - Review pending orders
  - Manage order status (pending → payment → approved)
  - Edit and stage inventory stock changes
  - Manage product inventory
  - Review and resolve customer complaints
  - **Cannot access**: Analytics dashboard, Django admin panel

### 3. **Manager**
- **Access**: All Sales Admin features + analytics & admin panel
- **Dashboard**: Sales Admin Dashboard + Manager Analytics
- **Capabilities**:
  - All Sales Administrator capabilities
  - View Manager Analytics Dashboard (with business metrics)
  - Access Django Administration panel
  - User management (when in Django admin)
  - Full system oversight

### 4. **Superuser**
- **Access**: Complete system access
- **Dashboard**: Sales Admin Dashboard + Manager Analytics + Django Admin
- **Capabilities**:
  - All Manager capabilities
  - Full Django administration
  - User role management
  - System configuration

## Database Changes

### User Model Updates
The `User` model now includes role choices:

```python
ROLE_CHOICES = (
    ('customer', 'Customer'),
    ('sales_admin', 'Sales Administrator'),
    ('manager', 'Manager'),
)

role = models.CharField(
    max_length=50, 
    choices=ROLE_CHOICES, 
    default='customer'
)
```

**Helper Methods** added to User model:
- `is_manager()`: Returns True for managers and superusers
- `is_sales_admin()`: Returns True for sales admins, managers, and superusers
- `is_customer()`: Returns True for customers only

**Migration**: `customers/migrations/0004_alter_user_role.py`

## Authentication System

### Unified Login (`/login/`)
- Single login page for all users
- Accepts username or email
- Automatically redirects based on user role:
  - Customer → Product List
  - Sales Admin → Sales Admin Dashboard
  - Manager → Sales Admin Dashboard (with analytics access)
  - Superuser → Sales Admin Dashboard (with full admin access)

### Login Flow
```
1. User visits /login/
2. Enters credentials
3. System verifies role
4. Auto-redirect to appropriate dashboard
5. If already logged in, redirect to dashboard
```

### Logout (`/logout/`)
- Located in user dropdown menu in navbar
- Clears session and redirects to product list

## Access Control

### Role-Based Decorators
Located in: `customers/auth_utils.py`

**Available Decorators:**
- `@role_required(*roles)`: Allow specific roles
- `@customer_required`: Customers only
- `@sales_admin_required`: Sales admins and managers
- `@manager_required`: Managers and superusers only

**Example Usage:**
```python
@sales_admin_required
def inventory_list(request):
    # Only sales admins, managers, and superusers can access
    ...

@manager_required
def manager_analytics_view(request):
    # Only managers and superusers can access
    ...
```

### View Protection
All protected views automatically:
- Check if user is authenticated
- Verify user role matches requirements
- Allow superusers to bypass role checks
- Display error messages and redirect to home if denied

## URL Structure

### Authentication URLs
```
/login/              → Unified login page
/logout/             → Logout endpoint
/home/               → Dashboard home (auto-redirects based on role)
/login/admin/        → Legacy (redirects to /login/)
/login/customer/     → Legacy (redirects to /login/)
```

### Admin URLs (all require @sales_admin_required or higher)
```
/dashboard/                          → Sales Admin Dashboard
/dashboard/analytics/                → Manager Analytics (managers only)
/dashboard/inventory/                → Inventory Management
/dashboard/inventory/add/            → Add Product
/dashboard/complaints/               → Complaint List
/dashboard/order/<id>/detail/        → Order Details
/admin/                              → Django Admin Panel (superuser/manager)
```

### Customer URLs
```
/menu/               → Product List
/menu/cart/          → Shopping Cart
/menu/checkout/      → Checkout
/menu/order/<id>/    → Order Details
```

## User Interface

### Navigation Bar
- **Logo**: Links to home (redirects based on role)
- **Menu Links**: Standard navigation
- **User Dropdown**: 
  - Shows username and role
  - Role-specific dashboard links
  - Logout button

### Role-Aware Dashboards

**Sales Admin Dashboard**: 
- Pending orders section
- Payment verification section
- Accepted orders section
- Quick access to inventory and complaints
- Role indicator showing current permissions

**Manager Analytics Dashboard**:
- Total orders metric
- Approved orders count
- Pending orders count
- Total revenue display
- Placeholder sections for:
  - Sales trend charts
  - Top products ranking
  - Customer activity
  - Inventory status
  - (Ready for future expansion)

## Security Features

1. **Automatic Superuser Access**: Superusers bypass all role checks
2. **Permission Inheritance**: Managers have all sales admin permissions
3. **Session-Based**: Uses Django's session authentication
4. **CSRF Protection**: All forms include CSRF tokens
5. **Message Feedback**: Users receive feedback on denied access attempts
6. **Error Handling**: Graceful redirects on permission violations

## File Structure

### New Files Created
- `customers/auth_utils.py` - Role-based decorators and utilities
- `templates/registration/login.html` - Unified login page (redesigned)
- `templates/admins/manager_analytics.html` - Manager dashboard

### Modified Files
- `customers/models.py` - Added ROLE_CHOICES to User model
- `admins/views.py` - Implemented unified login and new decorators
- `zarlyOs/urls.py` - Updated URL routing with new unified paths
- `templates/base.html` - Added user authentication dropdown
- `templates/admins/sales_admin_dashboard.html` - Enhanced with role-based navigation
- `admins/urls.py` - Added manager analytics route

### Migrations
- `customers/migrations/0004_alter_user_role.py` - User role field update

## Implementation Notes

### For Existing Users
- Existing users will retain their current `role` value if set
- Users without a role will default to `'customer'`
- Superusers automatically have full access regardless of role field

### For New Users
- Must be manually created and assigned a role
- Can only be created via Django admin or custom admin interface
- Default role is `'customer'`

### Feature Expansion
The manager analytics dashboard includes placeholder sections for:
- Sales charts and trends
- Product performance metrics
- Customer activity tracking
- Inventory analytics

These can be populated by adding:
1. Chart libraries (e.g., Chart.js)
2. Analytics calculations in `manager_analytics_view()`
3. Template updates with dynamic data

## Testing the System

### Test Accounts Needed
1. **customer** (role: 'customer')
   - Can access product list, cart, checkout
   - Cannot access dashboard

2. **sales_admin** (role: 'sales_admin')
   - Can access sales dashboard, inventory, complaints
   - Cannot access analytics or admin panel

3. **manager** (role: 'manager')
   - Can access sales dashboard, inventory, complaints, analytics
   - Can access Django admin panel

4. **superuser** (is_superuser: True)
   - Can access everything

### Test Scenarios
```
1. Login as customer → Should redirect to /menu/
2. Login as sales_admin → Should redirect to /dashboard/
3. Login as manager → Should see analytics button
4. Logout → Should redirect to /menu/
5. Visit /dashboard/ as customer → Should be denied
6. Visit /login/ while logged in → Should redirect to dashboard
```

## Future Enhancements

1. **Two-Factor Authentication**: Add 2FA for admin users
2. **Activity Logging**: Log all admin actions
3. **Custom Permissions**: Fine-grained permission system
4. **Role Hierarchy**: More granular role definitions
5. **Analytics Expansion**: Full dashboard analytics
6. **API Authentication**: Token-based auth for mobile apps
