from django.test import TestCase
from io import BytesIO
from PIL import Image
from customers.payment_utils import (
    get_duitnow_qr,
    get_bank_transfer_qr,
    validate_payment_proof,
    get_all_payment_methods,
    generate_qr_code_base64,
)


class QRCodeGenerationTest(TestCase):
    """Test QR code generation for all payment methods"""

    def test_duitnow_qr_generation(self):
        """Test DuitNow QR code is generated correctly"""
        qr = get_duitnow_qr(order_id=123, amount='50.00')
        
        self.assertIsNotNone(qr)
        self.assertIn('qr_image', qr)
        self.assertIn('merchant_id', qr)
        self.assertIn('amount', qr)
        self.assertIn('reference', qr)
        self.assertIn('instructions', qr)
        
        # Check QR image is base64 encoded
        self.assertTrue(qr['qr_image'].startswith('data:image/png;base64,'))
        
        # Check reference format
        self.assertEqual(qr['reference'], 'ORDER-123')

    def test_bank_transfer_qr_generation(self):
        """Test Bank Transfer QR code is generated correctly"""
        qr = get_bank_transfer_qr(order_id=456, amount='100.50')
        
        self.assertIsNotNone(qr)
        self.assertIn('qr_image', qr)
        self.assertIn('bank_name', qr)
        self.assertIn('account_number', qr)
        self.assertIn('account_holder', qr)
        self.assertIn('swift_code', qr)
        self.assertIn('amount', qr)
        self.assertIn('reference', qr)
        self.assertIn('instructions', qr)
        
        # Check QR image is base64 encoded
        self.assertTrue(qr['qr_image'].startswith('data:image/png;base64,'))
        
        # Check reference format
        self.assertEqual(qr['reference'], 'ORDER-456')

    def test_all_payment_methods(self):
        """Test that all payment methods can be retrieved together"""
        methods = get_all_payment_methods(order_id=999, amount=125.50)
        
        self.assertIn('duitnow', methods)
        self.assertIn('bank_transfer', methods)
        
        # Each should have QR code
        self.assertTrue(methods['duitnow']['qr_image'].startswith('data:image/png;base64,'))
        self.assertTrue(methods['bank_transfer']['qr_image'].startswith('data:image/png;base64,'))

    def test_qr_code_consistency(self):
        """Test that QR codes with same data are consistent"""
        qr1 = generate_qr_code_base64('test_data_123')
        qr2 = generate_qr_code_base64('test_data_123')
        
        # Same data should produce same QR
        self.assertEqual(qr1, qr2)
        
        # Different data should produce different QR
        qr3 = generate_qr_code_base64('different_data')
        self.assertNotEqual(qr1, qr3)

    def test_different_amounts_produce_different_qrs(self):
        """Test that different amounts produce different QR codes"""
        qr1 = get_duitnow_qr(order_id=100, amount='50.00')
        qr2 = get_duitnow_qr(order_id=100, amount='100.00')
        
        # Different amounts should produce different QR codes
        self.assertNotEqual(qr1['qr_image'], qr2['qr_image'])


class FileValidationTest(TestCase):
    """Test payment proof file validation"""

    def _create_test_image(self, format='PNG', size=(100, 100)):
        """Helper to create test image"""
        img = Image.new('RGB', size, color='red')
        img_io = BytesIO()
        img.save(img_io, format=format)
        img_io.seek(0)
        return img_io

    def test_valid_png_file(self):
        """Test that valid PNG files are accepted"""
        img_io = self._create_test_image('PNG')
        img_io.name = 'receipt.png'
        img_io.size = img_io.tell()
        
        is_valid, error = validate_payment_proof(img_io)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_valid_jpg_file(self):
        """Test that valid JPG files are accepted"""
        img_io = self._create_test_image('JPEG')
        img_io.name = 'receipt.jpg'
        img_io.size = img_io.tell()
        
        is_valid, error = validate_payment_proof(img_io)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_file_too_large(self):
        """Test that oversized files are rejected"""
        img_io = self._create_test_image()
        img_io.name = 'large.png'
        img_io.size = 6 * 1024 * 1024  # 6MB
        
        is_valid, error = validate_payment_proof(img_io, max_size_mb=5)
        self.assertFalse(is_valid)
        self.assertIn('too large', error.lower())

    def test_invalid_file_type(self):
        """Test that unsupported file types are rejected"""
        file_io = BytesIO(b'not an image')
        file_io.name = 'document.txt'
        file_io.size = 100
        
        is_valid, error = validate_payment_proof(file_io)
        self.assertFalse(is_valid)
        self.assertIn('Invalid file type', error)

    def test_no_file_provided(self):
        """Test that missing file is rejected"""
        is_valid, error = validate_payment_proof(None)
        self.assertFalse(is_valid)
        self.assertIn('No file', error)

    def test_supported_formats(self):
        """Test all supported image formats — gif and webp are no longer accepted."""
        for fmt, ext in [('PNG', 'png'), ('JPEG', 'jpg')]:
            with self.subTest(format=fmt):
                img_io = self._create_test_image(fmt)
                img_io.name = f'receipt.{ext}'
                img_io.size = img_io.tell()
                valid, error = validate_payment_proof(img_io)
                self.assertTrue(valid, f"{fmt} should be valid")
                self.assertIsNone(error)

    def test_case_insensitive_extension(self):
        """Test that file extensions are case-insensitive"""
        img_io = self._create_test_image('PNG')
        img_io.name = 'receipt.PNG'  # uppercase
        img_io.size = img_io.tell()
        
        is_valid, error = validate_payment_proof(img_io)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_max_size_enforcement(self):
        """Test that max_size parameter is respected"""
        img_io = self._create_test_image()
        img_io.name = 'receipt.png'
        img_io.size = 3 * 1024 * 1024  # 3MB

        # Should pass with 5MB limit
        is_valid, error = validate_payment_proof(img_io, max_size_mb=5)
        self.assertTrue(is_valid)

        # Should fail with 2MB limit
        is_valid, error = validate_payment_proof(img_io, max_size_mb=2)
        self.assertFalse(is_valid)

    def test_gif_extension_rejected(self):
        img_io = self._create_test_image('GIF')
        img_io.name = 'receipt.gif'
        img_io.size = 0
        valid, error = validate_payment_proof(img_io)
        self.assertFalse(valid)
        self.assertIn('Invalid file type', error)

    def test_webp_extension_rejected(self):
        img_io = BytesIO(b'RIFF\x00\x00\x00\x00WEBPVP8 ')
        img_io.name = 'receipt.webp'
        img_io.size = 0
        valid, error = validate_payment_proof(img_io)
        self.assertFalse(valid)
        self.assertIn('Invalid file type', error)

    def test_renamed_exe_jpg_rejected_by_magic_bytes(self):
        img_io = BytesIO(b'MZ\x90\x00this is not a jpeg')
        img_io.name = 'proof.jpg'
        img_io.size = 0
        valid, error = validate_payment_proof(img_io)
        self.assertFalse(valid)
        self.assertIn('does not match', error)

    def test_renamed_exe_pdf_rejected_by_magic_bytes(self):
        img_io = BytesIO(b'MZ\x90\x00this is not a pdf')
        img_io.name = 'proof.pdf'
        img_io.size = 0
        valid, error = validate_payment_proof(img_io)
        self.assertFalse(valid)
        self.assertIn('does not match', error)

    def test_valid_pdf_accepted(self):
        pdf_io = BytesIO(b'%PDF-1.4 1 0 obj<</Type /Catalog>> endobj')
        pdf_io.name = 'proof.pdf'
        pdf_io.size = 0
        valid, error = validate_payment_proof(pdf_io)
        self.assertTrue(valid)
        self.assertIsNone(error)


class PaymentConfigTest(TestCase):
    """Test payment configuration"""

    def test_payment_config_exists(self):
        """Test that payment configuration is defined"""
        from customers.payment_utils import PAYMENT_CONFIG
        
        self.assertIn('duitnow', PAYMENT_CONFIG)
        self.assertIn('bank_transfer', PAYMENT_CONFIG)

    def test_duitnow_config_has_required_fields(self):
        """Test DuitNow configuration has all required fields"""
        from customers.payment_utils import PAYMENT_CONFIG
        
        duitnow = PAYMENT_CONFIG['duitnow']
        self.assertIn('name', duitnow)
        self.assertIn('id', duitnow)
        self.assertIn('reference', duitnow)

    def test_bank_transfer_config_has_required_fields(self):
        """Test Bank Transfer configuration has all required fields"""
        from customers.payment_utils import PAYMENT_CONFIG
        
        bank = PAYMENT_CONFIG['bank_transfer']
        self.assertIn('name', bank)
        self.assertIn('bank_name', bank)
        self.assertIn('account_number', bank)
        self.assertIn('account_holder', bank)
        self.assertIn('swift_code', bank)


class QRCodeDataTest(TestCase):
    """Test QR code data content"""

    def test_duitnow_qr_contains_reference(self):
        """Test DuitNow QR code data contains order reference"""
        qr = get_duitnow_qr(order_id=555, amount='99.99')
        
        self.assertIn('reference', qr)
        self.assertEqual(qr['reference'], 'ORDER-555')

    def test_bank_transfer_contains_account_details(self):
        """Test Bank Transfer QR contains account details"""
        qr = get_bank_transfer_qr(order_id=666, amount='150.00')
        
        self.assertIsNotNone(qr['account_number'])
        self.assertIsNotNone(qr['account_holder'])
        self.assertIsNotNone(qr['swift_code'])

    def test_instructions_are_provided(self):
        """Test that step-by-step instructions are provided"""
        qr1 = get_duitnow_qr(order_id=111, amount='50.00')
        qr2 = get_bank_transfer_qr(order_id=222, amount='60.00')
        
        for qr in [qr1, qr2]:
            self.assertIn('instructions', qr)
            self.assertIsInstance(qr['instructions'], list)
            self.assertGreater(len(qr['instructions']), 0)


class RealWorldScenarioTest(TestCase):
    """Test real-world payment scenarios"""

    def test_customer_uploads_payment_proof_workflow(self):
        """Test the complete workflow of uploading a payment proof"""
        # Step 1: Generate QR codes for order
        order_id = 12345
        amount = 89.50
        
        methods = get_all_payment_methods(order_id, amount)
        self.assertEqual(len(methods), 2)
        
        # Step 2: Customer scans QR code and pays (simulated)
        # Step 3: Customer uploads receipt image
        img_io = BytesIO()
        img = Image.new('RGB', (500, 300), color='green')
        img.save(img_io, format='PNG')
        img_io.seek(0)
        img_io.name = 'payment_receipt.png'
        img_io.size = img_io.tell()
        
        # Step 4: Validate uploaded file
        is_valid, error = validate_payment_proof(img_io)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_large_order_payment(self):
        """Test payment for large orders"""
        order_id = 9999
        amount = '2500.00'  # Large amount
        
        qr = get_duitnow_qr(order_id, amount)
        self.assertEqual(qr['amount'], amount)
        # QR code should be generated properly (is base64 encoded)
        self.assertTrue(qr['qr_image'].startswith('data:image/png;base64,'))

    def test_small_order_payment(self):
        """Test payment for small orders"""
        order_id = 1111
        amount = '0.50'  # Small amount
        
        qr = get_duitnow_qr(order_id, amount)
        self.assertEqual(qr['amount'], amount)
        self.assertTrue(len(qr['qr_image']) > 100)  # QR should still be valid
