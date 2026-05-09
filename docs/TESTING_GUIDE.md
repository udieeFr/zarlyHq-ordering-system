# Payment System Unit Testing Guide

## Quick Start

Run all 22 payment tests without creating any orders:

```bash
python manage.py test customers.tests
```

## Test Commands

### Run all tests with verbose output
```bash
python manage.py test customers.tests --verbosity=2
```

### Run specific test class
```bash
# QR Code Generation Tests (4 tests)
python manage.py test customers.tests.QRCodeGenerationTest

# File Validation Tests (8 tests)
python manage.py test customers.tests.FileValidationTest

# Payment Configuration Tests (2 tests)
python manage.py test customers.tests.PaymentConfigTest

# QR Code Data Tests (2 tests)
python manage.py test customers.tests.QRCodeDataTest

# Real-World Scenario Tests (3 tests)
python manage.py test customers.tests.RealWorldScenarioTest
```

### Run single test
```bash
python manage.py test customers.tests.QRCodeGenerationTest.test_duitnow_qr_generation
```

## Test Coverage

### ✅ QR Code Generation (4 tests)
- `test_duitnow_qr_generation` - DuitNow QR with correct format
- `test_bank_transfer_qr_generation` - Bank Transfer QR with account details
- `test_all_payment_methods` - All 2 methods in one call (DuitNow + Bank Transfer)
- `test_qr_code_consistency` - Same data = same QR code

### ✅ File Validation (8 tests)
- `test_valid_png_file` - PNG files accepted
- `test_valid_jpg_file` - JPG files accepted
- `test_file_too_large` - Files >5MB rejected
- `test_invalid_file_type` - Non-image files rejected (.txt, .doc)
- `test_no_file_provided` - Missing file rejected
- `test_supported_formats` - All formats tested (PNG, JPEG, GIF)
- `test_case_insensitive_extension` - .PNG and .png both work
- `test_max_size_enforcement` - Custom size limits respected

### ✅ Payment Configuration (2 tests)
- `test_payment_config_exists` - All 2 payment methods configured (DuitNow, Bank Transfer)
- `test_duitnow_config_has_required_fields` - DuitNow config complete
- `test_bank_transfer_config_has_required_fields` - Bank config complete

### ✅ QR Code Data (2 tests)
- `test_duitnow_qr_contains_reference` - Reference format: ORDER-123
- `test_bank_transfer_contains_account_details` - Account info present

### ✅ Real-World Scenarios (3 tests)
- `test_customer_uploads_payment_proof_workflow` - Complete flow without DB
- `test_large_order_payment` - Works with RM2500 orders
- `test_small_order_payment` - Works with RM0.50 orders

## Current Test Results

```
Found 22 test(s).
Ran 22 tests in 0.315s

OK ✓
```

**Note:** Test count reduced from 25 to 22 after removing FPX payment method (3 tests removed).

## Running Tests in Your IDE

### VS Code
1. Open Terminal (Ctrl+`)
2. Run: `python manage.py test customers.tests`

### PyCharm
1. Right-click `customers/tests.py`
2. Select "Run 'pytest in customers/tests.py'"

## No Database Required

All tests use in-memory data:
- ✓ Creates test images on-the-fly (no file I/O)
- ✓ Tests payment methods: DuitNow and Bank Transfer only
- ✓ Tests QR code generation (no storage)
- ✓ Tests file validation (no disk writes)
- ✓ Uses temporary test database (destroyed after tests)

## Order Approval Behavior

**Unpaid orders can still be approved** — they just follow a different path:

1. **Approved with Payment** → Moves to `approved` status → Appears in "Approved Orders" list → Ready for prep group
2. **Approved without Payment** → Moves to `pending_payment` status → Appears in "Awaiting Payment" list → Customer uploads proof or admin verifies payment → Then approved

This allows flexibility: admins can approve orders immediately (if order details are correct) and let customers upload payment proofs afterward.

## CI/CD Integration

Add to your CI pipeline:

```yaml
# GitHub Actions example
- name: Run Payment Tests
  run: python manage.py test customers.tests
```

## Debugging a Failed Test

Run with traceback:
```bash
python manage.py test customers.tests --debug-mode
```

Run single test with verbose output:
```bash
python manage.py test customers.tests.FileValidationTest.test_file_too_large --verbosity=2
```

## What These Tests Verify

✅ QR codes generate correctly for all payment methods  
✅ QR codes are base64 encoded and ready for HTML  
✅ File validation catches oversized files  
✅ File validation catches unsupported formats  
✅ Payment configuration is complete  
✅ Instructions are clear and step-by-step  
✅ Works with various order amounts (RM0.50 to RM2500)  
✅ No database mutations during tests  

## Next Steps (Manual Testing)

After unit tests pass, test manually:

1. **Checkout Flow**
   - Select "Manual Payment" option
   - Verify payment methods display correctly

2. **Order Success Page**
   - Check tabbed interface loads
   - Verify QR codes display
   - Test file upload validation

3. **Admin Verification**
   - Review uploaded payment proofs
   - Approve/reject orders
   - Verify notifications sent

---

**Status**: All 25 unit tests passing ✓  
**Database**: No database changes needed  
**Coverage**: Complete payment utility testing  
