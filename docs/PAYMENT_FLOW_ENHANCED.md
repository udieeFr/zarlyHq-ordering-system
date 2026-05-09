# Enhanced Manual Payment Flow

## Overview

The payment system now offers flexible payment timing for manual payments (QR code/bank transfer):
- **Pay Now**: Customer pays immediately during checkout and uploads proof
- **Pay Later**: Customer places order, pays within 24 hours, uploads proof from dashboard

## Customer Journey

### Option 1: Pay Now (Immediate Payment)

1. **Checkout Page**
   - Select "Manual Payment (Bank/DuitNow)"
   - Choose "Pay Now"
   - Place order

2. **Order Success Page**
   - Shows payment methods (DuitNow, Bank Transfer, FPX)
   - Customer scans QR code or uses bank details
   - Uploads receipt immediately
   - Admin verifies within 1-2 hours
   - Order moves to fulfillment

### Option 2: Pay Later (Deferred Payment)

1. **Checkout Page**
   - Select "Manual Payment (Bank/DuitNow)"
   - Choose "Pay Later"
   - Place order

2. **Order Success Page**
   - Shows message: "Payment due within 24 hours"
   - Link to Awaiting Payment dashboard
   - No immediate file upload required

3. **Customer Dashboard** (`/awaiting-payment/`)
   - View all orders awaiting payment
   - Payment methods displayed (DuitNow, Bank Transfer, FPX)
   - Upload proof anytime within 24 hours
   - Multiple orders support with pagination

4. **Admin Verification**
   - Reviews uploaded proof
   - Approves payment → Order fulfillment begins
   - Rejects proof → Notifies customer (optional)

## Technical Changes

### Views Updated

**`submit_order()`** - Added logic to:
- Capture `manual_payment_timing` value from form
- Skip proof requirement if "pay later" selected
- Set order status to "pending_payment" for both flows
- Create Payment record immediately

**`order_success()`** - Enhanced to:
- Show payment methods only if no proof uploaded yet
- Show different messages for "pay now" vs "pay later"
- Pass `show_payment_methods` flag to template

**`awaiting_payment_orders()`** - NEW VIEW
- Display pending payment orders for customer
- Generate QR codes and payment methods
- Pagination support (10 orders per page)
- Allow file uploads from dashboard

### Templates Updated

**`checkout.html`** - Added:
- Sub-options for manual payment timing
- Toggle visibility of payment timing options
- Improved payment method descriptions

**`order_success.html`** - Modified:
- Conditional display of payment methods (only if needed)
- Different messaging for "pay now" vs "pay later"
- Success message for submitted proofs
- Link to awaiting payment dashboard

**`awaiting_payment.html`** - NEW TEMPLATE
- Tabbed payment methods interface
- QR codes and bank details
- File upload form for each order
- 24-hour deadline reminder
- Pagination controls

### URLs Added

```python
path('awaiting-payment/', views.awaiting_payment_orders, name='awaiting_payment_orders'),
```

## Order Status Flow

### Pay Now Path
```
pending → pending_payment (with proof) → approved (after verification) → preparing → ...
```

### Pay Later Path
```
pending → pending_payment (no proof) → awaiting payment dashboard → pending_payment (with proof) → approved → preparing → ...
```

## Admin Experience

No changes needed for admin - they already:
1. See pending payment orders in dashboard
2. Can review payment proofs
3. Approve/reject based on proof verification
4. Receive system checks (0 issues)

## File Structure

**New Files:**
- `templates/customers/awaiting_payment.html` - Payment dashboard

**Modified Files:**
- `customers/views.py` - Added `awaiting_payment_orders()`, updated `submit_order()` and `order_success()`
- `customers/urls.py` - Added awaiting payment route
- `templates/customers/checkout.html` - Payment timing options
- `templates/customers/order_success.html` - Conditional payment display

## Key Features

✅ Flexible payment timing (now vs later)  
✅ Customers can view pending orders anytime  
✅ Multiple payment methods (DuitNow, Bank, FPX)  
✅ QR codes dynamically generated  
✅ 24-hour payment window  
✅ Pagination for multiple orders  
✅ File validation (5MB max, image/PDF)  
✅ Clear user messaging  
✅ Admin approval workflow  

## User Experience

### Customer Benefits
- Choose flexible payment timing
- Multiple payment methods with QR codes
- Upload proof from dashboard anytime
- Clear 24-hour deadline
- No payment lost due to forgotten orders

### Admin Benefits
- Existing verification workflow unchanged
- Automatic payment deadline tracking (via created_at)
- All proofs in order detail view
- Batch approval of multiple proofs

## Testing Scenarios

1. **Pay Now Flow**
   - Checkout → Select "Manual Payment" → "Pay Now" → Place order
   - Verify payment methods display
   - Upload proof
   - Verify success message

2. **Pay Later Flow**
   - Checkout → Select "Manual Payment" → "Pay Later" → Place order
   - Verify "24-hour" message
   - Go to Awaiting Payment dashboard
   - Upload proof from there
   - Verify success message

3. **Dashboard Pagination**
   - Create multiple pending orders
   - Navigate awaiting-payment page
   - Verify pagination works
   - Upload proofs for various orders

4. **Multiple Payment Methods**
   - DuitNow QR scanning
   - Bank Transfer account details
   - FPX online banking
   - All should work seamlessly

---

**Status**: Implementation Complete  
**Version**: 2.0 (with flexible payment timing)  
**Database**: No migrations needed (uses existing fields)  
**Testing**: Ready for manual testing
