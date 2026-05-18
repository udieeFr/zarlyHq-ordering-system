import re
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()
pytestmark = pytest.mark.django_db


def _parse_csp(response):
    """Return CSP directives as dict: {'script-src': ["'self'", "https://..."], ...}"""
    header = response.get('Content-Security-Policy', '')
    result = {}
    for chunk in header.split(';'):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split()
        if not parts:
            continue
        result[parts[0]] = parts[1:]
    return result


def _get_nonce(response):
    """Extract the nonce value from the CSP header's script-src directive."""
    csp = response.get('Content-Security-Policy', '')
    m = re.search(r"'nonce-([^']+)'", csp)
    return m.group(1) if m else None


class TestCSPHeader:
    def setup_method(self):
        self.client = Client()
        self.r = self.client.get(reverse('login'))

    def test_csp_header_present(self):
        assert 'Content-Security-Policy' in self.r

    def test_script_src_no_unsafe_inline(self):
        d = _parse_csp(self.r)
        assert "'unsafe-inline'" not in d.get('script-src', [])

    def test_script_src_has_nonce(self):
        nonce = _get_nonce(self.r)
        assert nonce is not None, "No nonce found in script-src"

    def test_script_src_has_jsdelivr(self):
        d = _parse_csp(self.r)
        assert 'https://cdn.jsdelivr.net' in d.get('script-src', [])

    def test_script_src_has_unpkg(self):
        d = _parse_csp(self.r)
        assert 'https://unpkg.com' in d.get('script-src', [])

    def test_style_src_has_google_fonts(self):
        d = _parse_csp(self.r)
        assert 'https://fonts.googleapis.com' in d.get('style-src', [])

    def test_font_src_has_gstatic(self):
        d = _parse_csp(self.r)
        assert 'https://fonts.gstatic.com' in d.get('font-src', [])

    def test_object_src_none(self):
        d = _parse_csp(self.r)
        assert "'none'" in d.get('object-src', [])

    def test_frame_ancestors_none(self):
        d = _parse_csp(self.r)
        assert "'none'" in d.get('frame-ancestors', [])

    def test_base_uri_self(self):
        d = _parse_csp(self.r)
        assert "'self'" in d.get('base-uri', [])

    def test_form_action_self(self):
        d = _parse_csp(self.r)
        assert "'self'" in d.get('form-action', [])

    def test_nonce_unique_per_request(self):
        r1 = self.client.get(reverse('login'))
        r2 = self.client.get(reverse('login'))
        n1 = _get_nonce(r1)
        n2 = _get_nonce(r2)
        assert n1 is not None
        assert n2 is not None
        assert n1 != n2

    def test_nonce_in_rendered_html_matches_header(self):
        user = User.objects.create_user(
            username='csp_test', password='pass', role='customer'
        )
        self.client.force_login(user)
        r = self.client.get(reverse('customer_home'))
        nonce = _get_nonce(r)
        assert nonce is not None
        assert f'nonce="{nonce}"' in r.content.decode(), \
            "Nonce from CSP header not found in rendered script tags"
