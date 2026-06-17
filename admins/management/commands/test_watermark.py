"""
Management command to test and demo the receipt watermarking system.

Usage:
    # Generate a standalone watermark sample (no order needed):
    python manage.py test_watermark --sample

    # Watermark a specific order's signed receipt:
    python manage.py test_watermark --order-id 42

    # Watermark a specific order with forced VOID (tamper simulation):
    python manage.py test_watermark --order-id 42 --void

Output files are written to MEDIA_ROOT/temp_pdfs/ for inspection.
"""

import os
import io
import hashlib
from django.core.management.base import BaseCommand
from django.conf import settings
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from admins.models import Order, DigitalSignature


class Command(BaseCommand):
    help = "Test the receipt watermarking system — generates sample watermarked PDFs."

    def add_arguments(self, parser):
        parser.add_argument('--sample', action='store_true',
                            help='Generate a standalone watermark sample (fake receipt).')
        parser.add_argument('--order-id', type=int,
                            help='Watermark the signed receipt for this order.')
        parser.add_argument('--void', action='store_true',
                            help='Force VOID stamp (simulates tampering).')

    def _make_fake_receipt(self):
        """Generate a minimal fake invoice PDF for demo purposes."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        w, h = A4

        # Header
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(colors.HexColor('#CC0000'))
        c.drawString(40, h - 50, "ZARLY")
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(colors.HexColor('#1a1a1a'))
        c.drawString(40, h - 80, "INVOICE — SAMPLE RECEIPT")
        c.setFont("Helvetica", 10)
        c.drawString(40, h - 100, "Big Food Industries Sdn. Bhd.  |  Lot 012 Kipmart Masai, Pasir Gudang, Johor")

        # Line items
        items = [
            ("1", "Ayam Gunting Cheese Large", "2", "28.00", "56.00"),
            ("2", "Kentang Putar Regular", "1", "12.50", "12.50"),
            ("3", "Burger Daging Special", "1", "15.90", "15.90"),
        ]
        headers = ["No", "Description", "Qty", "Unit (RM)", "Total (RM)"]
        y = h - 150
        col_x = [40, 100, 320, 380, 460]

        c.setFont("Helvetica-Bold", 9)
        for i, hdr in enumerate(headers):
            c.drawString(col_x[i], y, hdr)
        y -= 8
        c.setStrokeColor(colors.HexColor('#CC0000'))
        c.line(40, y, 540, y)
        y -= 18

        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor('#333333'))
        for item in items:
            for i, val in enumerate(item):
                c.drawString(col_x[i], y, val)
            y -= 16

        # Total
        y -= 4
        c.line(40, y, 540, y)
        y -= 18
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor('#CC0000'))
        c.drawString(380, y, "Total (MYR):")
        c.drawString(460, y, "84.40")

        # Digital signature footer
        y -= 50
        c.setStrokeColor(colors.HexColor('#cccccc'))
        c.line(40, y, 540, y)
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(colors.HexColor('#555555'))
        c.drawString(40, y - 12, "Cryptographic Integrity Signature")
        c.setFont("Helvetica", 6.5)
        c.drawString(40, y - 22, "SHA-256 HASH: a1b2c3d4e5f6... (sample)")
        c.drawString(40, y - 32, "Digitally signed via PyHanko PKCS#7 (X.509)")

        c.save()
        buf.seek(0)
        return buf.read()

    def handle(self, *args, **options):
        from admins.utils import stamp_pdf_with_watermark, _build_watermark_pdf
        from pypdf import PdfReader as PyPdfReader, PdfWriter

        out_dir = os.path.join(settings.MEDIA_ROOT, 'temp_pdfs')
        os.makedirs(out_dir, exist_ok=True)

        # ── Sample mode ────────────────────────────────
        if options.get('sample'):
            fake_pdf_bytes = self._make_fake_receipt()
            fake_path = os.path.join(out_dir, '_sample_fake_receipt.pdf')
            with open(fake_path, 'wb') as f:
                f.write(fake_pdf_bytes)

            # Also generate the raw watermark
            wm_bytes = _build_watermark_pdf(verified=True)
            wm_path = os.path.join(out_dir, '_sample_watermark_raw.pdf')
            with open(wm_path, 'wb') as f:
                f.write(wm_bytes)

            # Generate AUTHENTIC version
            verified_bytes = stamp_pdf_with_watermark(fake_path, verified=True)
            verified_path = os.path.join(out_dir, '_sample_AUTHENTIC.pdf')
            with open(verified_path, 'wb') as f:
                f.write(verified_bytes)

            # Generate VOID version
            void_bytes = stamp_pdf_with_watermark(fake_path, verified=False)
            void_path = os.path.join(out_dir, '_sample_VOID.pdf')
            with open(void_path, 'wb') as f:
                f.write(void_bytes)

            self.stdout.write(self.style.SUCCESS(
                f"\n  Sample files written to {out_dir}/:\n"
                f"    _sample_fake_receipt.pdf   — fake invoice (no watermark)\n"
                f"    _sample_watermark_raw.pdf  — watermark layer alone\n"
                f"    _sample_AUTHENTIC.pdf      — receipt + green AUTHENTIC stamp\n"
                f"    _sample_VOID.pdf           — receipt + red VOID stamp\n"
            ))
            return

        # ── Order mode ─────────────────────────────────
        order_id = options.get('order_id')
        if not order_id:
            self.stdout.write(self.style.ERROR(
                "Specify --sample or --order-id <N>.  Use --help for details."
            ))
            return

        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Order #{order_id} not found."))
            return

        try:
            sig = DigitalSignature.objects.get(order=order)
        except DigitalSignature.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"Order #{order_id} has no DigitalSignature record. "
                f"Approve the order first to generate the signed PDF."
            ))
            return

        pdf_path = os.path.join(settings.MEDIA_ROOT, sig.pdf_path.name)
        if not os.path.exists(pdf_path):
            self.stdout.write(self.style.ERROR(
                f"Signed PDF file not found at: {pdf_path}"
            ))
            return

        # Live hash check
        sha256 = hashlib.sha256()
        with open(pdf_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()
        hash_match = file_hash == sig.signature_hash

        self.stdout.write(f"  Order #{order_id}")
        self.stdout.write(f"  Stored hash:  {sig.signature_hash}")
        self.stdout.write(f"  File hash:    {file_hash}")
        self.stdout.write(f"  Hash match:   {'YES' if hash_match else 'NO — TAMPERED!'}")

        force_void = options.get('void', False)
        verified = hash_match and not force_void

        if force_void:
            self.stdout.write(self.style.WARNING("  Forcing VOID stamp (--void flag active)."))

        try:
            pdf_bytes = stamp_pdf_with_watermark(pdf_path, verified)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  stamp_pdf_with_watermark failed: {e}"))
            return

        label = 'AUTHENTIC' if verified else 'VOID'
        out_name = f"order_{order_id}_{label}.pdf"
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, 'wb') as f:
            f.write(pdf_bytes)

        self.stdout.write(self.style.SUCCESS(
            f"  Written: {out_path}  ({len(pdf_bytes):,} bytes)"
        ))
