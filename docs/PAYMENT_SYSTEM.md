# 💰 Payment System Documentation

## Overview
The Zarly payment system now supports both **Stripe (instant)** and **Manual Payment (bank transfer/DuitNow)** as backup options with dynamic QR code generation.

## Features

### 1. **Stripe Payment** (Primary)
- Instant payment processing
- Multiple payment methods (Card, Online Banking, E-wallet)
- Automatic order confirmation
- Secure webhook verification

### 2. **Manual Payment** (Backup) ✨ NEW
- **DuitNow QR Code** - Scan and pay instantly
- **Bank Transfer** - Direct transfer with account details
- **FPX/Online Banking** - Real-time interbank transfer
- Dynamic QR code generation for all methods
- File upload validation (images & PDF only)
- Admin verification workflow (1-2 hours)

## Customer Payment Flow

### Step 1: Checkout
1. Customer selects payment method:
   - **Stripe** → Go directly to Stripe checkout
   - **Manual** → Place order, then upload proof

### Step 2: Order Success Page (Manual Payment)
1. Customer sees **tabbed payment methods**:
   - 📱 **DuitNow** - Scan QR code with banking app
   - 🏦 **Bank Transfer** - Transfer to business account
   - 🏧 **FPX** - Online banking transfer

2. Each method shows:
   - **Dynamic QR Code** (base64 encoded, no server storage needed)
   - **Bank Details** (account number, holder, SWIFT code)
   - **Clear Instructions** (step-by-step)
   - **Reference Number** (Order-{ID})

3. Upload Receipt:
   - Screenshot or image of payment confirmation
   - Validation: Max 5MB, JPG/PNG/GIF/WebP/PDF only
   - File integrity check
   - Image preview before upload

### Step 3: Admin Verification
1. Admin reviews payment proof
2. Updates order status to `approved`
3. Order fulfillment begins

## Technical Implementation

### New Files Created

#### `customers/payment_utils.py`
Utility module for:
- Dynamic QR code generation (using `qrcode` library)
- Payment configuration (bank details)
- File validation (type, size, integrity)
- Context data for templates

**Key Functions:**
```python
get_duitnow_qr(order_id, amount)          # DuitNow QR
get_bank_transfer_qr(order_id, amount)    # Bank Transfer QR
get_fpx_qr(order_id, amount)              # FPX QR
validate_payment_proof(file_obj, max_size_mb=5)  # Validate upload
get_all_payment_methods(order_id, amount) # All methods at once
```

### Modified Files

#### `customers/views.py`
Updated functions:
- `upload_payment_proof()` - Enhanced validation & error handling
- `order_success()` - Now passes payment methods with QR codes

New imports:
```python
from .payment_utils import validate_payment_proof, get_all_payment_methods
```

#### `templates/customers/checkout.html`
- Better payment method descriptions
- Dynamic info display (no file upload on checkout)
- Improved UX with color-coded options

#### `templates/customers/order_success.html`
- **Tabbed payment methods interface**
- Dynamic QR codes for each method
- Bank account details display
- Step-by-step instructions
- Image file upload with preview
- File validation feedback

## Configuration

### Payment Details (Edit in `customers/payment_utils.py`)

```python
PAYMENT_CONFIG = {
    'duitnow': {
        'name': 'DuitNow',
        'id': '0123456789',  # ← UPDATE with your DuitNow ID
        'reference': 'Zarly Order',
    },
    'bank_transfer': {
        'name': 'Bank Transfer',
        'bank_name': 'Maybank',
        'account_number': '123456789012',  # ← UPDATE
        'account_holder': 'Zarly Co. Sdn. Bhd.',  # ← UPDATE
        'swift_code': 'MBBEMYKL',
        'reference': 'ORDER-{order_id}',
    },
    'fpx': {
        'name': 'FPX (Online Banking)',
        'bank_code': 'MBB0021',  # ← UPDATE if needed
        'merchant_id': '0123456789',  # ← UPDATE
        'reference': 'Zarly Order',
    }
}
```

### Update Required Settings

Before going live, update these in `zarlyOs/settings.py`:

```python
# Email configuration for payment notifications
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # or your email provider
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
DEFAULT_FROM_EMAIL = 'noreply@zarly.co'

# Payment currency (already set)
STRIPE_CURRENCY = 'MYR'  # Malaysian Ringgit
```

## QR Code Generation

### How It Works
1. **No Server Storage** - QR codes are generated on-the-fly
2. **Base64 Encoding** - Embedded directly in `<img src="data:image/png;base64,...">`
3. **Dynamic Data** - Includes amount, reference, account details
4. **Library Used** - `qrcode==8.2` (already in requirements.txt)

### QR Code Data Format

**DuitNow:**
```
00020219{merchant_id}{amount}{reference}
```

**Bank Transfer:**
```
{bank_name}|{account_number}|{account_holder}|RM {amount}|{reference}
```

**FPX:**
```
00020136{bank_code}|{merchant_id}|{amount}|{reference}
```

## File Validation

### Supported Formats
✓ JPG/JPEG  
✓ PNG  
✓ GIF  
✓ WebP  
✓ PDF  

### Validation Rules
- **Max Size**: 5MB
- **Integrity Check**: Image file is verified as valid
- **MIME Type**: Matched against allowed list
- **User Feedback**: Clear error messages

## Testing Checklist

- [ ] Manual payment method selection in checkout
- [ ] QR codes display correctly on order success page
- [ ] All three payment methods show correct details
- [ ] File upload validation works (reject large files)
- [ ] Image preview works before upload
- [ ] Success message shows after upload
- [ ] Admin can see uploaded proofs
- [ ] Order status updates after approval

## Troubleshooting

### QR Code Not Displaying
- Check browser console for errors
- Verify `qrcode` library is installed: `pip install qrcode[pil]`
- Ensure PIL/Pillow is installed

### File Upload Failing
- Check file size (max 5MB)
- Verify file type is in allowed list
- Check server disk space for uploads
- Verify `MEDIA_ROOT` directory is writable

### Payment Methods Not Showing
- Ensure `order.status == 'pending_payment'`
- Check that `payment.payment_method == 'manual'`
- Verify context is passed from view to template

## Future Enhancements

1. **Email Notifications** - Send QR codes via email
2. **Webhook Integration** - Auto-verify DuitNow/FPX payments
3. **Admin Dashboard** - Track payment proofs and approvals
4. **Appeal System** - Customers can request review of rejected proofs
5. **Payment History** - Show past transactions
6. **Auto-Timeout** - Expire unpaid orders after 24 hours

## Security Notes

- ✓ CSRF protection on all forms
- ✓ Authentication required (customers only)
- ✓ File upload validation (type & size)
- ✓ Order ownership verification
- ✓ Admin-only approval workflow
- ⚠️ Consider: HTTPS required in production
- ⚠️ Consider: Add rate limiting to upload endpoint

## Support Contact

For payment-related issues:
- **Email**: support@zarly.co
- **Chat**: In-app support widget
- **Phone**: +60 3-XXXX-XXXX

---

**Last Updated**: May 9, 2026  
**Version**: 1.0  
**Status**: Ready for Testing
