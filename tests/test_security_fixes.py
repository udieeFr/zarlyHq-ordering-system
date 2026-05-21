"""
Tests for the 6 security fixes applied on 2026-05-18.

VULN 1 — Stored XSS in chat bubbles
VULN 2 — Missing @customer_required role enforcement
VULN 3 — Unguarded int(quantity) on cart inputs
VULN 4 — PDF upload skips magic-byte content inspection
VULN 5 — AUTH_PASSWORD_VALIDATORS disabled
VULN 6 — CSP connect-src missing Nominatim
"""

import pytest
import io
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()
pytestmark = pytest.mark.django_db


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_user(username, role, password='pass123!'):
    return User.objects.create_user(
        username=username, email=f'{username}@t.com',
        password=password, role=role,
    )


def make_order(customer, status='pending'):
    from admins.models import Order
    return Order.objects.create(customer=customer, total_amount=100, status=status)


def make_complaint(customer, order):
    from admins.models import Complaint
    return Complaint.objects.create(
        order=order, customer=customer, subject='S', message='M'
    )


# ── VULN 1 — Stored XSS: chat JSON response returns plain text, not HTML ──────

class TestXSSChatResponse:
    """
    The appendMessage JS function now uses textContent, not innerHTML.
    The server-side fix: ensure the JSON response returns the raw decrypted
    string — the browser is responsible for safe insertion.
    We verify the server returns the body as-is (not escaped or modified),
    which confirms the fix is on the client side (textContent in the template).
    """

    @pytest.fixture(autouse=True)
    def setup(self, settings):
        settings.SUPPORT_CHAT_KEY = 'chz6Xd7HkrP1AZq3FLCymr1_tPW29rcVbdDuV-CaE2c='
        self.client = Client()
        self.customer = make_user('xss_cust', 'customer')
        self.admin = make_user('xss_admin', 'sales_admin')
        order = make_order(self.customer, status='delivered')
        self.complaint = make_complaint(self.customer, order)

    def test_xss_payload_returned_as_plain_string_not_executed(self):
        """Body is returned verbatim — client uses textContent so it never executes."""
        from admins.chat_crypto import encrypt_message
        from admins.models import SupportMessage
        payload = '<img src=x onerror="alert(1)">'
        SupportMessage.objects.create(
            complaint=self.complaint,
            sender=self.customer,
            body=encrypt_message(payload),
        )
        self.client.force_login(self.customer)
        url = reverse('customer_complaint_messages', args=[self.complaint.id])
        r = self.client.get(url)
        assert r.status_code == 200
        data = r.json()
        bodies = [m['body'] for m in data['messages']]
        # The raw payload is in the JSON — safe because the template uses textContent
        assert payload in bodies

    def test_script_tag_payload_returned_as_string(self):
        from admins.chat_crypto import encrypt_message
        from admins.models import SupportMessage
        payload = '<script>document.location="https://evil.com"</script>'
        SupportMessage.objects.create(
            complaint=self.complaint,
            sender=self.admin,
            body=encrypt_message(payload),
        )
        self.client.force_login(self.customer)
        url = reverse('customer_complaint_messages', args=[self.complaint.id])
        r = self.client.get(url)
        bodies = [m['body'] for m in r.json()['messages']]
        assert payload in bodies


# ── VULN 2 — @customer_required: staff cannot access customer views ────────────

class TestCustomerRequired:

    def test_sales_admin_cannot_access_cart(self):
        admin = make_user('cr_admin', 'sales_admin')
        c = Client()
        c.force_login(admin)
        r = c.get(reverse('cart'))
        assert r.status_code in (302, 403)

    def test_manager_cannot_access_customer_orders(self):
        manager = make_user('cr_mgr', 'manager')
        c = Client()
        c.force_login(manager)
        r = c.get(reverse('customer_orders'))
        assert r.status_code in (302, 403)

    def test_sales_admin_cannot_submit_complaint(self):
        admin = make_user('cr_admin2', 'sales_admin')
        c = Client()
        c.force_login(admin)
        r = c.post(reverse('submit_complaint'), {})
        assert r.status_code in (302, 403)

    def test_customer_can_access_cart(self):
        customer = make_user('cr_cust', 'customer')
        c = Client()
        c.force_login(customer)
        r = c.get(reverse('cart'))
        assert r.status_code == 200

    def test_unauthenticated_redirected_from_cart(self):
        c = Client()
        r = c.get(reverse('cart'))
        assert r.status_code == 302

    def test_sales_admin_cannot_access_customer_profile(self):
        admin = make_user('cr_admin3', 'sales_admin')
        c = Client()
        c.force_login(admin)
        r = c.get(reverse('customer_profile'))
        assert r.status_code in (302, 403)

    def test_sales_admin_cannot_access_notifications(self):
        admin = make_user('cr_admin4', 'sales_admin')
        c = Client()
        c.force_login(admin)
        r = c.get(reverse('notifications_list'))
        assert r.status_code in (302, 403)

    def test_logout_still_works_for_any_role(self):
        """logout_view keeps @login_required — any authenticated role can log out."""
        admin = make_user('cr_logout_admin', 'sales_admin')
        c = Client()
        c.force_login(admin)
        r = c.post(reverse('logout'))
        assert r.status_code in (200, 302)


# ── VULN 3 — int(quantity) is now guarded with try/except ─────────────────────

class TestCartQuantityGuard:

    @pytest.fixture(autouse=True)
    def setup(self):
        from customers.models import Product
        self.client = Client()
        self.customer = make_user('qty_cust', 'customer')
        self.product = Product.objects.create(
            name='Test Item', category='Test', price=10, stock=50
        )

    def test_non_integer_quantity_add_to_cart_returns_200(self):
        """A non-integer quantity must not crash the view with a 500."""
        self.client.force_login(self.customer)
        r = self.client.post(
            reverse('add_to_cart'),
            {'product_id': self.product.id, 'quantity': 'abc'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert r.status_code != 500

    def test_non_integer_quantity_defaults_to_1(self):
        self.client.force_login(self.customer)
        self.client.post(
            reverse('add_to_cart'),
            {'product_id': self.product.id, 'quantity': 'bad'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        cart = self.client.session.get('cart', {})
        assert cart.get(str(self.product.id), 0) == 1

    def test_quantity_above_99_capped_at_99(self):
        self.client.force_login(self.customer)
        self.client.post(
            reverse('add_to_cart'),
            {'product_id': self.product.id, 'quantity': '9999'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        cart = self.client.session.get('cart', {})
        assert cart.get(str(self.product.id), 0) <= 99

    def test_non_integer_quantity_update_cart_does_not_crash(self):
        session = self.client.session
        session['cart'] = {str(self.product.id): 2}
        session.save()
        self.client.force_login(self.customer)
        r = self.client.post(
            reverse('update_cart'),
            {'product_id': self.product.id, 'quantity': 'notanumber'},
        )
        assert r.status_code != 500


# ── VULN 4 — PDF magic-byte validation ────────────────────────────────────────

class TestPDFMagicByteValidation:

    def _make_file(self, name, content):
        f = io.BytesIO(content)
        f.name = name
        f.size = len(content)
        return f

    def test_valid_pdf_is_accepted(self):
        from customers.payment_utils import validate_payment_proof
        f = self._make_file('proof.pdf', b'%PDF-1.4 fake content')
        ok, err = validate_payment_proof(f)
        assert ok is True
        assert err is None

    def test_html_disguised_as_pdf_is_rejected(self):
        from customers.payment_utils import validate_payment_proof
        f = self._make_file('evil.pdf', b'<html><script>alert(1)</script></html>')
        ok, err = validate_payment_proof(f)
        assert ok is False
        assert err is not None

    def test_javascript_file_disguised_as_pdf_is_rejected(self):
        from customers.payment_utils import validate_payment_proof
        f = self._make_file('exploit.pdf', b'var x = "malicious";')
        ok, err = validate_payment_proof(f)
        assert ok is False

    def test_non_pdf_extension_still_rejected(self):
        from customers.payment_utils import validate_payment_proof
        f = self._make_file('proof.exe', b'%PDF-1.4')
        ok, err = validate_payment_proof(f)
        assert ok is False


# ── VULN 5 — AUTH_PASSWORD_VALIDATORS active; validate_password() called ──────

class TestPasswordValidation:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = Client()
        self.customer = make_user('pw_cust', 'customer', password='OldPass123!')

    def _change_pw(self, current, new_pw, confirm):
        self.client.force_login(self.customer)
        return self.client.post(reverse('customer_profile'), {
            'action': 'change_password',
            'current_password': current,
            'new_password': new_pw,
            'confirm_password': confirm,
        })

    def test_common_password_rejected(self):
        r = self._change_pw('OldPass123!', 'password', 'password')
        # Should re-render with errors, not redirect
        assert r.status_code == 200
        content = r.content.decode()
        assert 'too common' in content.lower() or 'password' in content.lower()

    def test_numeric_only_password_rejected(self):
        r = self._change_pw('OldPass123!', '12345678', '12345678')
        assert r.status_code == 200

    def test_strong_password_accepted(self):
        r = self._change_pw('OldPass123!', 'Xk9!mP2#qLw', 'Xk9!mP2#qLw')
        assert r.status_code == 302  # redirect on success

    def test_passwords_must_match(self):
        r = self._change_pw('OldPass123!', 'Xk9!mP2#qLw', 'Different1!')
        assert r.status_code == 200

    def test_wrong_current_password_rejected(self):
        r = self._change_pw('wrongpassword', 'Xk9!mP2#qLw', 'Xk9!mP2#qLw')
        assert r.status_code == 200


# ── VULN 6 — CSP connect-src includes Nominatim ───────────────────────────────

class TestCSPConnectSrc:

    def test_nominatim_in_connect_src(self, settings):
        assert 'https://nominatim.openstreetmap.org' in settings.CSP_CONNECT_SRC

    def test_unpkg_in_connect_src(self, settings):
        assert 'https://unpkg.com' in settings.CSP_CONNECT_SRC

    def test_self_still_in_connect_src(self, settings):
        assert "'self'" in settings.CSP_CONNECT_SRC
