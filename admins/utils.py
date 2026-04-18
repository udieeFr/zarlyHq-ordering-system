
import os
import hashlib
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from django.conf import settings

# PyHanko Imports
from pyhanko.sign import signers, fields
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

def generate_invoice_pdf(order):
    """Generates a PDF receipt using ReportLab"""
    filename = f"order_{order.id}_receipt.pdf"
    file_path = os.path.join(settings.MEDIA_ROOT, 'temp_pdfs', filename)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Draw PDF Content
    c = canvas.Canvas(file_path, pagesize=A4)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, 800, "ZARLY BIGFOOD SDN BHD")
    
    c.setFont("Helvetica", 12)
    c.drawString(50, 770, f"Order Receipt #{order.id}")
    c.drawString(50, 755, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}")
    c.drawString(50, 740, f"Customer: {order.customer.username}")
    if order.street_address or order.city or order.state or order.postcode:
        c.drawString(50, 725, f"Address: {order.address_summary}")
        y = 705
    else:
        y = 725
    if order.latitude and order.longitude:
        c.drawString(50, y - 15, f"Coordinates: {order.latitude}, {order.longitude}")
        y -= 25
    else:
        y -= 10

    c.line(50, y, 550, y)
    
    y -= 30
    for item in order.items.all():
        c.drawString(50, y, f"{item.product.name} (x{item.quantity})")
        c.drawString(450, y, f"RM {item.subtotal}")
        y -= 20
        
    c.line(50, y-10, 550, y-10)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(350, y-40, f"TOTAL: RM {order.total_amount}")
    
    c.save()
    return file_path

def sign_pdf_digitally(input_pdf_path, order_id):
 
    # 1. Define Paths
    key_path = os.path.join(settings.BASE_DIR, 'secure_keys', 'zarly_key.pem')
    cert_path = os.path.join(settings.BASE_DIR, 'secure_keys', 'zarly_cert.pem')
    
    signed_filename = f"signed_order_{order_id}.pdf"
    signed_path = os.path.join(settings.MEDIA_ROOT, 'signed_pdfs', signed_filename)
    os.makedirs(os.path.dirname(signed_path), exist_ok=True)

    # 2. Load Identity
    # load key daripada certificate
    signer = signers.SimpleSigner.load(
        key_file=key_path,
        cert_file=cert_path
    )

    # 3. Sign the PDF
    # find space untuk embed by creating a container
    with open(input_pdf_path, 'rb') as inf:
        w = IncrementalPdfFileWriter(inf)
        fields.append_signature_field(
            w, sig_field_spec=fields.SigFieldSpec(sig_field_name='Signature1')
        )
        # fill container with hash
        # pyhanko handle : hash -> encrypt dengan private key -> embed
        with open(signed_path, 'wb') as outf:
            signers.sign_pdf(
                w, signers.PdfSignatureMetadata(field_name='Signature1'),
                signer=signer, output=outf,
            )

    # 4. Calculate Hash untuk simpan dalam database & comparison
    sha256_hash = hashlib.sha256()
    with open(signed_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
            
    return signed_path, sha256_hash.hexdigest()