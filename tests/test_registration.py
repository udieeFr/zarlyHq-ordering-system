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


# ── Signup OTP (email-keyed, no user required) ────────────────────────────────

class TestSignupOtpUtils:

    def test_generate_signup_otp_returns_six_digit_string(self):
        from customers.otp_utils import generate_and_cache_signup_otp
        code = generate_and_cache_signup_otp('user@example.com')
        assert len(code) == 6
        assert code.isdigit()

    def test_signup_otp_stored_in_cache_by_email(self):
        from customers.otp_utils import generate_and_cache_signup_otp
        from django.core.cache import cache
        code = generate_and_cache_signup_otp('cache@example.com')
        assert cache.get('signup_otp:cache@example.com') == code

    def test_verify_signup_otp_ok_on_correct_code(self):
        from customers.otp_utils import generate_and_cache_signup_otp, verify_signup_otp
        code = generate_and_cache_signup_otp('ok@example.com')
        assert verify_signup_otp('ok@example.com', code) == 'ok'

    def test_verify_signup_otp_deletes_cache_on_success(self):
        from customers.otp_utils import generate_and_cache_signup_otp, verify_signup_otp
        from django.core.cache import cache
        code = generate_and_cache_signup_otp('del@example.com')
        verify_signup_otp('del@example.com', code)
        assert cache.get('signup_otp:del@example.com') is None

    def test_verify_signup_otp_invalid_on_wrong_code(self):
        from customers.otp_utils import generate_and_cache_signup_otp, verify_signup_otp
        generate_and_cache_signup_otp('wrong@example.com')
        assert verify_signup_otp('wrong@example.com', '000000') == 'invalid'

    def test_verify_signup_otp_expired_when_no_cache(self):
        from customers.otp_utils import verify_signup_otp
        assert verify_signup_otp('ghost@example.com', '123456') == 'expired'

    def test_resend_overwrites_old_signup_otp(self):
        from customers.otp_utils import generate_and_cache_signup_otp, verify_signup_otp
        old = generate_and_cache_signup_otp('resend@example.com')
        new = generate_and_cache_signup_otp('resend@example.com')
        assert verify_signup_otp('resend@example.com', old) == 'invalid'
        assert verify_signup_otp('resend@example.com', new) == 'ok'


# ── Signup view (AJAX, JSON responses) ────────────────────────────────────────

class TestCustomerSignupView:

    def setup_method(self):
        self.client = Client()

    def test_get_renders_signup_page(self):
        res = self.client.get(reverse('customer_signup'))
        assert res.status_code == 200
        assert b'signup' in res.content.lower() or b'Join' in res.content

    def test_post_returns_json_on_validation_error(self):
        res = self.client.post(reverse('customer_signup'), {
            'username': 'ab',
            'email': 'bad',
            'password': '123',
            'password_confirm': '456',
        })
        assert res.status_code == 200
        data = res.json()
        assert data['status'] == 'error'
        assert 'username' in data['errors']

    def test_post_duplicate_username_returns_error(self):
        make_customer('taken')
        res = self.client.post(reverse('customer_signup'), {
            'username': 'taken',
            'email': 'newemail@test.com',
            'password': 'Pass123!',
            'password_confirm': 'Pass123!',
        })
        data = res.json()
        assert data['status'] == 'error'
        assert 'username' in data['errors']

    def test_post_duplicate_email_returns_error(self):
        make_customer('uniqueuser', email='taken@test.com')
        res = self.client.post(reverse('customer_signup'), {
            'username': 'newuser',
            'email': 'taken@test.com',
            'password': 'Pass123!',
            'password_confirm': 'Pass123!',
        })
        data = res.json()
        assert data['status'] == 'error'
        assert 'email' in data['errors']

    def test_valid_post_returns_otp_sent_and_stores_session(self):
        res = self.client.post(reverse('customer_signup'), {
            'username': 'newuser',
            'email': 'newuser@test.com',
            'password': 'Pass123!ZZ',
            'password_confirm': 'Pass123!ZZ',
        })
        data = res.json()
        assert data['status'] == 'otp_sent'
        assert 'masked_email' in data
        assert '*' in data['masked_email']
        # Session should hold pending registration
        session = self.client.session
        assert 'pending_signup' in session
        assert session['pending_signup']['email'] == 'newuser@test.com'

    def test_valid_post_does_not_create_user_yet(self):
        self.client.post(reverse('customer_signup'), {
            'username': 'notcreated',
            'email': 'notcreated@test.com',
            'password': 'Pass123!ZZ',
            'password_confirm': 'Pass123!ZZ',
        })
        assert not User.objects.filter(username='notcreated').exists()

    def test_valid_post_stores_otp_in_cache(self):
        from django.core.cache import cache
        self.client.post(reverse('customer_signup'), {
            'username': 'cacheuser',
            'email': 'cacheuser@test.com',
            'password': 'Pass123!ZZ',
            'password_confirm': 'Pass123!ZZ',
        })
        assert cache.get('signup_otp:cacheuser@test.com') is not None
