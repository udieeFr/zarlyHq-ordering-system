
import io
import os
import json
import hashlib
import base64
import math
from decimal import Decimal
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle
from django.conf import settings

# PyHanko Imports
from pyhanko.sign import signers, fields
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader

# Brand colours
_RED   = colors.HexColor('#CC0000')
_DARK  = colors.HexColor('#1a1a1a')
_GREY  = colors.HexColor('#555555')
_LGREY = colors.HexColor('#f5f5f5')
_GREEN = colors.HexColor('#1a7a1a')

PAGE_W, PAGE_H = A4   # 595.27 x 841.89 pt
MARGIN = 40


def _draw_table(c, table, x, y):
    """Render a platypus Table at (x, y) using the canvas."""
    w, h = table.wrapOn(c, PAGE_W - 2 * MARGIN, PAGE_H)
    table.drawOn(c, x, y - h)
    return h


def compute_order_integrity_hash(order):
    """SHA-256 of canonical order data for non-repudiation. Independent of PDF file format."""
    items = sorted(order.items.all(), key=lambda i: i.id)
    data = {
        'order_id': order.id,
        'customer_id': order.customer_id,
        'total_amount': str(order.total_amount),
        'created_at': order.created_at.isoformat(),
        'items': [
            {'product_id': i.product_id, 'quantity': i.quantity, 'unit_price': str(i.unit_price)}
            for i in items
        ],
    }
    canonical = json.dumps(data, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def generate_invoice_pdf(order, approver=None, sig_hash=None, sig_timestamp=None, approved_at=None):
    filename = f"order_{order.id}_receipt.pdf"
    file_path = os.path.join(settings.MEDIA_ROOT, 'temp_pdfs', filename)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    c = canvas.Canvas(file_path, pagesize=A4)

    # ── HEADER ────────────────────────────────────────────────────────────
    # Left: ZARLY logo text
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(_RED)
    c.drawString(MARGIN, PAGE_H - 50, "ZARLY")
    c.setFont("Helvetica", 10)
    c.setFillColor(_GREY)
    c.drawString(MARGIN, PAGE_H - 63, "by Big Food Industries Sdn. Bhd.")

    # Right: INVOICE label + company block
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(_DARK)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 50, "INVOICE")

    company_lines = [
        "Big Food Industries Sdn. Bhd.",
        "Co. No: 201701001631",
        "Lot 012 Kipmart Masai, Jalan Persiaran Dahlia",
        "81700 Pasir Gudang, Johor",
        "HQ: No 42 Jalan Selasih 15, Taman Pasir Putih",
        "Tel: 012-784 6465 / 012-717 0617",
        "Email: bigfood.zarly@gmail.com",
        "TIN: C24793051020   MSIC: 46329",
    ]
    c.setFont("Helvetica", 8)
    c.setFillColor(_GREY)
    line_y = PAGE_H - 63
    for line in company_lines:
        c.drawRightString(PAGE_W - MARGIN, line_y, line)
        line_y -= 11

    # Horizontal rule under header
    rule_y = PAGE_H - 145
    c.setStrokeColor(_RED)
    c.setLineWidth(1.5)
    c.line(MARGIN, rule_y, PAGE_W - MARGIN, rule_y)
    c.setLineWidth(0.5)
    c.setStrokeColor(_GREY)

    # ── BILL TO / INVOICE DETAILS (two-column) ────────────────────────────
    y_info = rule_y - 15

    # Bill To
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(_GREY)
    c.drawString(MARGIN, y_info, "BILL TO")
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(_DARK)
    c.drawString(MARGIN, y_info - 13, order.full_name or order.customer_label)
    c.setFont("Helvetica", 9)
    c.setFillColor(_GREY)
    addr_y = y_info - 26
    if order.street_address:
        c.drawString(MARGIN, addr_y, order.street_address[:80])
        addr_y -= 12
    city_state = ', '.join(p for p in [order.city, order.state, order.postcode] if p)
    if city_state:
        c.drawString(MARGIN, addr_y, city_state[:80])
        addr_y -= 12
    if order.phone_number:
        c.drawString(MARGIN, addr_y, f"Tel: {order.phone_number}")
        addr_y -= 12
    if order.is_walk_in and approver:
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(MARGIN, addr_y, f"Walk-in — authorized by {approver.get_full_name() or approver.username}")
        addr_y -= 12

    # Invoice details (right column)
    approver_name = (approver.get_full_name() or approver.username) if approver else '—'
    is_paid = order.status in ('approved', 'preparing', 'out_for_delivery', 'delivered')
    detail_rows = [
        ("INV #",          str(order.id)),
        ("Date",           order.created_at.strftime('%d/%m/%Y')),
        ("By",             approver_name),
        ("Status",         "Paid" if is_paid else order.status.replace('_', ' ').title()),
        ("e-Invoice Type", "Consolidate"),
        ("e-Invoice Status", "Pending"),
    ]
    right_x = PAGE_W - MARGIN
    col_label_x = PAGE_W - MARGIN - 180
    dy = y_info
    for label, value in detail_rows:
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(_GREY)
        c.drawString(col_label_x, dy, label + ":")
        c.setFont("Helvetica", 8)
        if label == "Status" and is_paid:
            c.setFillColor(_GREEN)
        else:
            c.setFillColor(_DARK)
        c.drawRightString(right_x, dy, value)
        dy -= 13

    # ── ITEMS TABLE ───────────────────────────────────────────────────────
    table_top = min(addr_y, dy) - 18

    items = list(order.items.all())
    table_data = [["No", "Description", "Unit", "Price (RM)", "Amount (RM)"]]
    total_units = 0
    for i, item in enumerate(items, start=1):
        table_data.append([
            str(i),
            item.product.name,
            str(item.quantity),
            f"{item.unit_price:.2f}",
            f"{item.subtotal:.2f}",
        ])
        total_units += item.quantity
    table_data.append(["", "Total", str(total_units), "", ""])

    col_widths = [25, 230, 45, 70, 70]
    tbl = Table(table_data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        # Header row
        ('BACKGROUND',   (0, 0), (-1, 0), _RED),
        ('TEXTCOLOR',    (0, 0), (-1, 0), colors.white),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 6),
        ('TOPPADDING',   (0, 0), (-1, 0), 6),
        # Body rows
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',     (0, 1), (-1, -1), 8),
        ('TOPPADDING',   (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, _LGREY]),
        # Total row
        ('FONTNAME',     (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND',   (0, -1), (-1, -1), _LGREY),
        # Alignment
        ('ALIGN',        (0, 0), (0, -1), 'CENTER'),
        ('ALIGN',        (2, 0), (-1, -1), 'RIGHT'),
        # Grid
        ('LINEBELOW',    (0, 0), (-1, 0), 0.5, _RED),
        ('LINEBELOW',    (0, -1), (-1, -1), 0.5, _GREY),
        ('LINEAFTER',    (0, 0), (-2, -1), 0.3, colors.HexColor('#dddddd')),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    tbl_height = _draw_table(c, tbl, MARGIN, table_top)

    # ── TOTALS BLOCK ──────────────────────────────────────────────────────
    totals_top = table_top - tbl_height - 12
    shipping_fee = getattr(order, 'shipping_fee', Decimal('0.00')) or Decimal('0.00')
    subtotal = order.total_amount - shipping_fee
    totals_rows = [
        ("Subtotal",    f"RM {subtotal:.2f}",       False),
        ("Shipping",    f"RM {shipping_fee:.2f}",   False),
        ("Total (MYR)", f"RM {order.total_amount:.2f}", True),
        ("Payment",     f"RM {order.total_amount:.2f}", False),
        ("Balance",     "0.00",                     False),
    ]
    tx = PAGE_W - MARGIN
    ty = totals_top
    for label, value, bold in totals_rows:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9 if bold else 8)
        c.setFillColor(_DARK)
        c.drawRightString(tx - 80, ty, label + ":")
        c.setFillColor(_RED if bold else _DARK)
        c.drawRightString(tx, ty, value)
        ty -= 14

    # ── TERMS & CONDITIONS ────────────────────────────────────────────────
    terms_top = ty - 20
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(_DARK)
    c.drawString(MARGIN, terms_top, "Terma & Syarat / Terms & Conditions")
    terms = [
        "1. Barangan yang dijual tidak boleh dikembalikan selepas empat belas (14) hari dari tarikh invois.",
        "2. Semua pembayaran melalui cek hendaklah dipalang dan dibuat memihak kepada BIG FOOD INDUSTRIES SDN BHD.",
        "3. No. akaun bank: BIG FOOD INDUSTRIES SDN BHD (MAYBANK) 551249546253",
        "4. Sebarang pertanyaan boleh hubungi +6012-784 6465 / +6012-717 0617.",
    ]
    c.setFont("Helvetica", 7.5)
    c.setFillColor(_GREY)
    ty2 = terms_top - 13
    for line in terms:
        c.drawString(MARGIN, ty2, line)
        ty2 -= 11

    # ── SIGNATURE LINES ───────────────────────────────────────────────────
    sig_top = ty2 - 25
    mid = PAGE_W / 2
    c.setStrokeColor(_GREY)
    c.setLineWidth(0.5)
    c.line(MARGIN, sig_top, mid - 20, sig_top)
    c.line(mid + 20, sig_top, PAGE_W - MARGIN, sig_top)
    c.setFont("Helvetica", 8)
    c.setFillColor(_GREY)
    c.drawString(MARGIN, sig_top - 12, "Issued by: Zarly BigFood Sdn. Bhd.")
    c.drawString(mid + 20, sig_top - 12, "Accepted by: ______________________")

    # ── DIGITAL SIGNATURE FOOTER (PRESERVED) ─────────────────────────────
    footer_top = sig_top - 40
    c.setStrokeColor(colors.HexColor('#cccccc'))
    c.setDash(3, 3)
    c.line(MARGIN, footer_top, PAGE_W - MARGIN, footer_top)
    c.setDash()

    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(_GREY)
    c.drawString(MARGIN, footer_top - 12, "Cryptographic Integrity Signature")
    c.setFont("Helvetica", 6.5)
    if sig_hash:
        c.setFillColor(_GREY)
        c.drawString(MARGIN, footer_top - 22, f"SHA-256 HASH: {sig_hash}")
        ts_str = sig_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') if sig_timestamp else ''
        if ts_str:
            c.drawString(MARGIN, footer_top - 32, f"Timestamp: {ts_str}")
    else:
        c.setFillColor(colors.HexColor('#cc0000'))
        c.drawString(MARGIN, footer_top - 22, "PENDING SIGNATURE: This document is not yet verified.")

    # Nonrepudiation record (compact, below sig footer)
    nr_y = footer_top - 46
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColor(_GREY)
    c.drawString(MARGIN, nr_y, "NONREPUDIATION RECORD")
    nr_y -= 10
    c.setFont("Helvetica", 6.5)
    if approver:
        _approved_at = approved_at or order.approved_at
        approved_at_str = _approved_at.strftime('%Y-%m-%d %H:%M UTC') if _approved_at else 'pending'
        c.drawString(MARGIN, nr_y, f"Approved by: {approver.username} ({approver.role})  |  Approved at: {approved_at_str}")
        nr_y -= 9
    if order.customer_confirmed_at:
        c.drawString(MARGIN, nr_y, f"Customer confirmed: {order.customer_confirmed_at.strftime('%Y-%m-%d %H:%M UTC')}")
        nr_y -= 9
    if order.customer_commitment_hash:
        c.drawString(MARGIN, nr_y, f"Commitment hash: {order.customer_commitment_hash[:32]}...")

    c.setFillColor(_DARK)
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

    # 4. Calculate SHA-256 hash of signed file for integrity verification
    sha256_hash = hashlib.sha256()
    with open(signed_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)

    # 5. Extract the raw PKCS#7 signature bytes embedded by PyHanko
    # These are the actual cryptographic signature bytes (RSA-encrypted hash),
    # stored separately from the PDF so they can be inspected or re-verified independently.
    signature_value = ''
    try:
        with open(signed_path, 'rb') as f:
            reader = PdfFileReader(f)
            embedded_sigs = list(reader.embedded_signatures)
            if embedded_sigs:
                pkcs7_bytes = embedded_sigs[0].pkcs7_content
                signature_value = base64.b64encode(pkcs7_bytes).decode('utf-8')
    except Exception:
        pass  # Non-fatal: hash is still the primary integrity check

    return signed_path, sha256_hash.hexdigest(), signature_value


def _build_watermark_pdf(verified: bool) -> bytes:
    """
    Returns an A4 PDF (as bytes) containing:
      1. A pantograph-style micro-text security background (tiled, rotated).
      2. A large diagonal stamp — 'AUTHENTIC' (green) or 'VOID' (red).
    Intended to be merged as an overlay onto the signed receipt via pypdf.

    Uses NO alpha/transparency — instead uses light opaque colours that
    render reliably when merged by pypdf (which may drop ExtGState resources).
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # ── Security background: tiled micro-text (pantograph style) ─────────
    # Light grey text on white — no alpha needed, works with any PDF merger.
    micro_color = Color(0.82, 0.82, 0.82)  # light grey, opaque
    c.setFillColor(micro_color)
    c.setFont("Helvetica", 5.5)
    tile_text = "ZARLY BIGFOOD SDN BHD  ●  "
    tile_w = c.stringWidth(tile_text, "Helvetica", 5.5)
    row_gap = 14
    for row in range(-10, int(h / row_gap) + 10):
        y_origin = row * row_gap
        x_origin = -(w * 0.5)
        c.saveState()
        c.translate(x_origin, y_origin)
        c.rotate(35)
        cols = int((w * 2) / tile_w) + 4
        for col in range(cols):
            c.drawString(col * tile_w, 0, tile_text)
        c.restoreState()

    # ── Main diagonal stamp ───────────────────────────────────────────────
    c.saveState()
    c.translate(w / 2, h / 2)
    c.rotate(45)

    if verified:
        # Two-line stamp: "AUTHENTIC" large + "Digitally Signed" smaller
        stamp_text = "AUTHENTIC"
        stamp_color = Color(0.25, 0.65, 0.25)  # medium green, opaque
        font_size = 72
    else:
        stamp_text = "VOID"
        stamp_color = Color(0.85, 0.25, 0.25)  # medium red, opaque
        font_size = 110

    c.setFont("Helvetica-Bold", font_size)
    c.setFillColor(stamp_color)
    text_w = c.stringWidth(stamp_text, "Helvetica-Bold", font_size)
    c.drawString(-text_w / 2, -font_size / 4, stamp_text)

    # Second line for verified stamp — descriptive sub-label
    if verified:
        sub_text = "Digitally Signed · PKCS#7 · Tamper-Proof"
        sub_size = 14
        c.setFont("Helvetica", sub_size)
        sub_color = Color(0.35, 0.55, 0.35)
        c.setFillColor(sub_color)
        sub_w = c.stringWidth(sub_text, "Helvetica", sub_size)
        c.drawString(-sub_w / 2, -font_size / 4 - sub_size - 8, sub_text)
    else:
        sub_text = "Verification Failed · Do Not Accept"
        sub_size = 16
        c.setFont("Helvetica-Bold", sub_size)
        sub_color = Color(0.75, 0.2, 0.2)
        c.setFillColor(sub_color)
        sub_w = c.stringWidth(sub_text, "Helvetica-Bold", sub_size)
        c.drawString(-sub_w / 2, -font_size / 4 - sub_size - 8, sub_text)

    # Border rectangle around the stamp
    effective_h = font_size * 0.85 + (sub_size + 16 if verified else sub_size + 10)
    padding = 14
    rect_x = -text_w / 2 - padding
    rect_y = -font_size / 4 - padding
    rect_w = max(text_w, sub_w if verified else 0) + padding * 2
    rect_h = effective_h + padding * 2
    border_color = Color(
        stamp_color.red * 0.6, stamp_color.green * 0.6, stamp_color.blue * 0.6
    )
    c.setStrokeColor(border_color)
    c.setLineWidth(3)
    c.rect(rect_x, rect_y, rect_w, rect_h)

    # Thinner outer border for seal effect
    outer_pad = 6
    c.setLineWidth(1.2)
    c.rect(rect_x - outer_pad, rect_y - outer_pad,
           rect_w + outer_pad * 2, rect_h + outer_pad * 2)

    c.restoreState()
    c.save()
    buf.seek(0)
    return buf.read()


def stamp_pdf_with_watermark(pdf_path: str, verified: bool) -> bytes:
    """
    Read the signed PDF at pdf_path, merge the pantograph/stamp watermark
    as an OVERLAY on every page, and return the result as bytes.
    The original signed file on disk is not modified.

    The watermark PDF uses opaque light colours (no alpha) so it merges
    reliably regardless of pypdf's ExtGState handling.  Because the
    colours are pale, the invoice content underneath remains fully legible
    while the stamp is clearly visible.
    """
    from pypdf import PdfWriter, PdfReader as PyPdfReader

    watermark_bytes = _build_watermark_pdf(verified)
    wm_reader = PyPdfReader(io.BytesIO(watermark_bytes))
    wm_page = wm_reader.pages[0]

    original_reader = PyPdfReader(pdf_path)
    writer = PdfWriter()

    for page in original_reader.pages:
        # over=True: watermark ON TOP of invoice content.
        # Because the watermark uses pale opaque colours (no alpha),
        # it stamps visibly while the invoice text remains readable.
        page.merge_page(wm_page, over=True)
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()