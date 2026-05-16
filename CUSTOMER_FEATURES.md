# Customer Features Reference
> Use this as a build tracker and future user guide base.
> Status: ✅ Built | 📋 Planned (in todo) | ❌ Not yet implemented

---

## 1. Account & Profile

| Feature | Status | Notes |
|---|---|---|
| Login / Logout | ✅ | Standard auth |
| Edit Profile (popup modal) | ✅ | First/last name, email, phone, default address, marketing opt-in. Accessible from the top-right user dropdown → "Edit Profile" |
| Change Password | ❌ | Not yet — needs a separate form or link to Django's built-in password change |
| Marketing email opt-in/out | ✅ | Toggle inside Edit Profile modal |

---

## 2. Menu & Product Discovery

| Feature | Status | Notes |
|---|---|---|
| Browse full menu | ✅ | Product grid with images, price, stock status |
| Filter by category | ✅ | Category pills at top + dropdown in filter bar |
| Filter by allergy | ✅ | Dropdown hides products containing selected allergen |
| Hide Sold Out toggle | ✅ | Button in filter bar; state persists across category/allergy filter changes |
| AJAX grid updates | ✅ | Filters and pagination update the grid without full page reload |
| Pagination | ✅ | Page links inside the AJAX grid |
| Product reviews / ratings | ❌ | Customers cannot rate or review individual products yet |

---

## 3. Cart

| Feature | Status | Notes |
|---|---|---|
| Add to cart | ✅ | AJAX — instant badge update and toast, no page reload |
| View cart | ✅ | Full cart page with item list and order summary sidebar |
| Update item quantity | ✅ | +/- buttons per item |
| Remove item | ✅ | Remove button per item |
| Cart item count badge | ✅ | Live in navbar and sidebar |

---

## 4. Checkout & Order Placement

| Feature | Status | Notes |
|---|---|---|
| Delivery address form | ✅ | Full address fields with interactive map pin |
| Order notes | ✅ | Free-text field for special requests |
| Submit order | ✅ | Creates order in the system |
| Promo / voucher codes | ❌ | No discount code field at checkout yet |
| Saved delivery addresses | 📋 | Auto-fill from previous orders — in todo |
| Estimated delivery time | ❌ | No ETA shown after placing order |

---

## 5. Payment

| Feature | Status | Notes |
|---|---|---|
| Stripe card payment | ✅ | Redirects to Stripe Checkout; webhook auto-confirms payment |
| Manual bank transfer / DuitNow | ✅ | Customer uploads proof image; admin reviews manually |
| Awaiting payment list | ✅ | Dedicated page listing all orders pending payment action |
| Payment proof upload | ✅ | Available from the order detail / awaiting payment page |

---

## 6. Order Management

| Feature | Status | Notes |
|---|---|---|
| Order history | ✅ | Two tabs: Upcoming (active orders) and Previous (completed/rejected) |
| Order statistics | ✅ | Total orders, total spent, average order value, favourite item — shown at top of My Orders |
| Cancel order | ✅ | Allowed only while order status is **Pending** (before admin review). Restores stock automatically. If Stripe payment was made, refund is triggered |
| Re-order | ✅ | One-click button on past orders — repopulates cart with same items (skips out-of-stock items) |
| Order status tracking | ✅ | Status label shown on each order card (Pending, Approved, Being Prepared, etc.) |
| Visual status timeline | ❌ | Step-by-step progress indicator (Placed → Approved → Prepared → Delivered) not yet built |
| Download invoice (PDF) | ✅ | Available once order is approved; digitally signed PDF |
| Receipt verification | ✅ | Customer can verify the digital signature on their receipt at `/verify/<order_id>/` |
| Rejected orders list | ✅ | Separate page listing rejected orders with rejection reason |

---

## 7. Loyalty Program

| Feature | Status | Notes |
|---|---|---|
| Loyalty tier | ✅ | Bronze (default) → Silver (RM 500) → Gold (RM 2,000) → Platinum (RM 5,000). Based on lifetime spend |
| Tier progress bar | ✅ | Shows % progress and RM remaining to reach next tier |
| VIP badge | ✅ | Gold pill badge — assigned by manager, visible on My Orders |
| Lifetime stats | ✅ | Total orders, total spent, avg order value, favourite item |
| Post-delivery rating | 📋 | 1–5 stars + optional comment after order is delivered — in todo |

---

## 8. Notifications

| Feature | Status | Notes |
|---|---|---|
| In-app notification bell | ✅ | Bell icon in navbar with unread count badge |
| Notifications list | ✅ | Full list of system notifications (order updates, approvals, etc.) |
| Mark all as read | ✅ | Button on notifications page |
| Email notifications | ✅ | Sent on key events (order approved, rejected, prepared) |

---

## 9. Support

| Feature | Status | Notes |
|---|---|---|
| Submit complaint | ✅ | Form with subject + message, linked to the customer's account |
| Support page | ✅ | Accessible from sidebar |
| Complaint status tracking | ❌ | Customers cannot see whether their complaint was acknowledged or resolved |

---

## Summary

| Category | Built | Planned | Not Yet |
|---|---|---|---|
| Account & Profile | 3 | 0 | 1 |
| Menu & Discovery | 5 | 0 | 1 |
| Cart | 5 | 0 | 0 |
| Checkout | 3 | 1 | 2 |
| Payment | 4 | 0 | 0 |
| Order Management | 6 | 0 | 1 |
| Loyalty | 4 | 1 | 0 |
| Notifications | 4 | 0 | 0 |
| Support | 2 | 0 | 1 |
| **Total** | **36** | **2** | **6** |

---

## Not Yet Implemented — Quick Reference

- **Change password** — settings/security page for customers
- **Product reviews** — rate and comment on items after delivery
- **Visual order timeline** — step-by-step status progress indicator
- **Promo / voucher codes** — discount code field at checkout
- **Estimated delivery time** — ETA displayed after order approval
- **Complaint status tracking** — let customers see if their complaint was resolved
