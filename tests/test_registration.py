"""
Tests for customer registration, email OTP verification, and checkout gate.
"""
import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()
pytestmark = pytest.mark.django_db


def make_customer(username='cust1', email=None, password='Pass123!ZZ', verified=False):
    user = User.objects.create_user(
        username=username,
        email=email or f'{username}@test.com',
        password=password,
        role='customer',
    )
    user.email_verified = verified
    user.save(update_fields=['email_verified'])
    return user


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# ── OTP utilities ─────────────────────────────────────────────────────────────

class TestOtpUtils:

    def test_generate_returns_six_digit_string(self):
        from customers.otp_utils import generate_and_cache_otp
        user = make_customer('otp_gen')
        code = generate_and_cache_otp(user)
        assert len(code) == 6
        assert code.isdigit()

    def test_generated_code_stored_in_cache(self):
        from customers.otp_utils import generate_and_cache_otp
        from django.core.cache import cache
        user = make_customer('otp_cache')
        code = generate_and_cache_otp(user)
        assert cache.get(f'email_otp_{user.pk}') == code

    def test_verify_ok_on_correct_code(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        user = make_customer('otp_ok')
        code = generate_and_cache_otp(user)
        assert verify_otp(user, code) == 'ok'

    def test_verify_deletes_cache_on_success(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        from django.core.cache import cache
        user = make_customer('otp_del')
        code = generate_and_cache_otp(user)
        verify_otp(user, code)
        assert cache.get(f'email_otp_{user.pk}') is None

    def test_verify_invalid_on_wrong_code(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        user = make_customer('otp_bad')
        generate_and_cache_otp(user)
        assert verify_otp(user, '000000') == 'invalid'

    def test_verify_expired_when_no_cache_entry(self):
        from customers.otp_utils import verify_otp
        user = make_customer('otp_exp')
        assert verify_otp(user, '123456') == 'expired'

    def test_resend_overwrites_old_code(self):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        user = make_customer('otp_resend')
        old_code = generate_and_cache_otp(user)
        new_code = generate_and_cache_otp(user)
        assert verify_otp(user, old_code) == 'invalid'
        assert verify_otp(user, new_code) == 'ok'

    def test_mask_email_hides_middle_chars(self):
        from customers.otp_utils import mask_email
        assert mask_email('johndoe@gmail.com') == 'j*****e@g****.com'

    def test_mask_email_short_local(self):
        from customers.otp_utils import mask_email
        assert mask_email('ab@test.com') == 'a*@t***.com'


# ── Model field ───────────────────────────────────────────────────────────────

class TestEmailVerifiedField:

    def test_new_user_defaults_to_unverified(self):
        user = make_customer('new_unverified')
        assert user.email_verified is False

    def test_can_set_verified_true(self):
        user = make_customer('set_verified')
        user.email_verified = True
        user.save(update_fields=['email_verified'])
        user.refresh_from_db()
        assert user.email_verified is True
