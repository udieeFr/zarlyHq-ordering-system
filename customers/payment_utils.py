"""
Payment utilities for handling QR code generation and payment configurations.
"""
import qrcode
import io
import base64
from django.conf import settings
from PIL import Image

# ==============================================================================
# PAYMENT CONFIGURATION
# ==============================================================================

PAYMENT_CONFIG = {
    'duitnow': {
        'name': 'DuitNow',
        'id': '0123456789',  # Replace with actual DuitNow ID
        'reference': 'Zarly Order',
    },
    'bank_transfer': {
        'name': 'Bank Transfer',
        'bank_name': 'Maybank',
        'account_number': '123456789012',
        'account_holder': 'Zarly Co. Sdn. Bhd.',
        'swift_code': 'MBBEMYKL',
        'reference': 'ORDER-{order_id}',
    }
}


def generate_qr_code_base64(data, size=10, border=2):
    """
    Generates a QR code and returns it as a base64-encoded data URI.
    
    Args:
        data (str): The data to encode in the QR code
        size (int): Size of the QR code box
        border (int): Border thickness
        
    Returns:
        str: Base64 data URI string for use in <img src="...">
    """
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Encode to base64
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        print(f"Error generating QR code: {str(e)}")
        return None


def get_duitnow_qr(order_id, amount, merchant_id=None):
    """
    Generate DuitNow QR code data.
    DuitNow format: 00020219 (header) + merchant_id + amount + reference
    
    Args:
        order_id (int): The order ID
        amount (str): Payment amount in MYR
        merchant_id (str): DuitNow merchant ID
        
    Returns:
        dict: Contains 'qr_data', 'qr_image_base64', and 'payment_info'
    """
    merchant_id = merchant_id or PAYMENT_CONFIG['duitnow']['id']
    reference = f"ORDER-{order_id}"
    
    # Simplified DuitNow data format (actual format may vary by provider)
    qr_data = f"00020219{merchant_id}{amount}{reference}"
    
    qr_image = generate_qr_code_base64(qr_data)
    
    return {
        'method': 'duitnow',
        'qr_data': qr_data,
        'qr_image': qr_image,
        'merchant_id': merchant_id,
        'amount': amount,
        'reference': reference,
        'instructions': [
            'Open your banking app (Maybank, CIMB, Affin, etc.)',
            'Select "DuitNow QR" or "Scan QR"',
            'Scan the QR code above',
            f'Confirm payment of RM {amount}',
            f'Use reference: {reference}',
            'Upload the payment receipt screenshot below'
        ]
    }


def get_bank_transfer_qr(order_id, amount):
    """
    Generate Bank Transfer QR code and details.
    Uses SWIFT code format for bank transfers.
    
    Args:
        order_id (int): The order ID
        amount (str): Payment amount in MYR
        
    Returns:
        dict: Contains bank details and QR code
    """
    bank_config = PAYMENT_CONFIG['bank_transfer']
    reference = f"ORDER-{order_id}"
    
    # Build SWIFT payment QR (or use bank-specific format)
    swift_data = (
        f"{bank_config['bank_name']}|"
        f"{bank_config['account_number']}|"
        f"{bank_config['account_holder']}|"
        f"RM {amount}|"
        f"{reference}"
    )
    
    qr_image = generate_qr_code_base64(swift_data)
    
    return {
        'method': 'bank_transfer',
        'qr_image': qr_image,
        'bank_name': bank_config['bank_name'],
        'account_number': bank_config['account_number'],
        'account_holder': bank_config['account_holder'],
        'swift_code': bank_config['swift_code'],
        'amount': amount,
        'reference': reference,
        'instructions': [
            f'Transfer RM {amount} to:',
            f'Bank: {bank_config["bank_name"]}',
            f'Account: {bank_config["account_number"]}',
            f'Holder: {bank_config["account_holder"]}',
            f'Reference: {reference}',
            'Keep the transfer receipt confirmation',
            'Upload a screenshot of the confirmation below'
        ]
    }


def get_all_payment_methods(order_id, amount):
    """
    Get all available manual payment methods with QR codes.
    
    Args:
        order_id (int): The order ID
        amount (str/float): Payment amount in MYR
        
    Returns:
        dict: Dictionary with all payment methods and their QR codes
    """
    amount_str = str(amount)
    
    return {
        'duitnow': get_duitnow_qr(order_id, amount_str),
        'bank_transfer': get_bank_transfer_qr(order_id, amount_str),
    }


def validate_payment_proof(file_obj, max_size_mb=5):
    """
    Validate payment proof image file.
    
    Args:
        file_obj: Django UploadedFile object
        max_size_mb (int): Maximum file size in MB
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not file_obj:
        return False, "No file provided"
    
    # Check file size (with fallback for BytesIO objects in testing)
    try:
        file_size = file_obj.size if hasattr(file_obj, 'size') else len(file_obj.getvalue())
    except:
        file_size = 0
    
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        return False, f"File is too large. Maximum size is {max_size_mb}MB"
    
    # Check file type
    allowed_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf']
    file_ext = file_obj.name.split('.')[-1].lower()
    
    if file_ext not in allowed_extensions:
        return False, f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
    
    # Validate image file integrity
    try:
        if file_ext.lower() != 'pdf':
            img = Image.open(file_obj)
            img.verify()
            file_obj.seek(0)  # Reset file pointer after verify
    except Exception as e:
        return False, f"File appears to be corrupted: {str(e)}"
    
    return True, None


def get_payment_proof_context(order):
    """
    Get context data for payment proof upload template.
    
    Args:
        order: Order object
        
    Returns:
        dict: Context dictionary for template rendering
    """
    payment_methods = get_all_payment_methods(order.id, order.total_amount)
    
    return {
        'order': order,
        'amount': order.total_amount,
        'payment_methods': payment_methods,
        'max_file_size_mb': 5,
        'accepted_formats': 'image/jpeg, image/png, image/gif, image/webp, application/pdf',
    }
