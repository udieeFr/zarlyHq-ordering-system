"""Tests for password-change OTP utilities and view flows."""
import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()
pytestmark = pytest.mark.django_db


def make_user(username, role, email=None, password='Pass123!ZZ'):
    return User.objects.create_user(
        username=username,
        email=email or f'{username}@test.com',
        password=password,
        role=role,
        email_verified=True,
    )


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


class TestPwChangeOtpUtils:

    def test_generate_returns_six_digit_string(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp
        user = make_user('pwgen', 'customer')
        code = generate_and_cache_pw_change_otp(user)
        assert len(code) == 6
        assert code.isdigit()

    def test_generated_code_stored_under_distinct_key(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp
        user = make_user('pwcache', 'customer')
        code = generate_and_cache_pw_change_otp(user)
        assert cache.get(f'pw_change_otp_{user.pk}') == code
        # Must NOT collide with email-verification key
        assert cache.get(f'email_otp_{user.pk}') is None

    def test_verify_ok_on_correct_code(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp, verify_pw_change_otp
        user = make_user('pwok', 'customer')
        code = generate_and_cache_pw_change_otp(user)
        assert verify_pw_change_otp(user, code) == 'ok'

    def test_verify_deletes_cache_on_success(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp, verify_pw_change_otp
        user = make_user('pwdel', 'customer')
        code = generate_and_cache_pw_change_otp(user)
        verify_pw_change_otp(user, code)
        assert cache.get(f'pw_change_otp_{user.pk}') is None

    def test_verify_invalid_on_wrong_code(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp, verify_pw_change_otp
        user = make_user('pwinv', 'customer')
        generate_and_cache_pw_change_otp(user)
        assert verify_pw_change_otp(user, '000000') == 'invalid'

    def test_verify_expired_when_no_cache(self):
        from customers.otp_utils import verify_pw_change_otp
        user = make_user('pwexp', 'customer')
        assert verify_pw_change_otp(user, '123456') == 'expired'

    def test_verify_expired_after_max_attempts(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp, verify_pw_change_otp
        user = make_user('pwmax', 'customer')
        generate_and_cache_pw_change_otp(user)
        for _ in range(4):
            verify_pw_change_otp(user, '000000')
        result = verify_pw_change_otp(user, '000000')  # 5th attempt
        assert result == 'expired'
        assert cache.get(f'pw_change_otp_{user.pk}') is None


class TestAdminProfilePasswordChange:

    def _login(self, client, user, password='Pass123!ZZ'):
        client.login(username=user.username, password=password)

    def test_request_otp_sends_email_and_sets_session(self):
        from unittest.mock import patch
        client = Client()
        user = make_user('adm_otp', 'sales_admin')
        self._login(client, user)
        with patch('customers.otp_utils.send_mail') as mock_mail:
            resp = client.post(reverse('admin_profile'), {
                'action': 'request_pw_change_otp',
            })
        assert resp.status_code == 302
        assert mock_mail.called
        session = client.session
        assert session.get('pw_change_pending') is True

    def test_verify_correct_otp_changes_password(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp
        client = Client()
        user = make_user('adm_chpw', 'sales_admin')
        self._login(client, user)
        code = generate_and_cache_pw_change_otp(user)
        session = client.session
        session['pw_change_pending'] = True
        session.save()
        resp = client.post(reverse('admin_profile'), {
            'action': 'verify_pw_change_otp',
            'otp': code,
            'new_password': 'NewSecure!99',
            'confirm_password': 'NewSecure!99',
        })
        assert resp.status_code == 302
        user.refresh_from_db()
        assert user.check_password('NewSecure!99')
        from admins.models import AuditLog
        assert AuditLog.objects.filter(
            actor=user, action_type='password_changed'
        ).exists()

    def test_verify_wrong_otp_shows_error(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp
        client = Client()
        user = make_user('adm_wrong', 'sales_admin')
        self._login(client, user)
        generate_and_cache_pw_change_otp(user)
        session = client.session
        session['pw_change_pending'] = True
        session.save()
        resp = client.post(reverse('admin_profile'), {
            'action': 'verify_pw_change_otp',
            'otp': '000000',
            'new_password': 'NewSecure!99',
            'confirm_password': 'NewSecure!99',
        })
        assert resp.status_code == 200
        user.refresh_from_db()
        assert not user.check_password('NewSecure!99')

    def test_mismatched_passwords_shows_error(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp
        client = Client()
        user = make_user('adm_mismatch', 'sales_admin')
        self._login(client, user)
        code = generate_and_cache_pw_change_otp(user)
        session = client.session
        session['pw_change_pending'] = True
        session.save()
        resp = client.post(reverse('admin_profile'), {
            'action': 'verify_pw_change_otp',
            'otp': code,
            'new_password': 'NewSecure!99',
            'confirm_password': 'Different!99',
        })
        assert resp.status_code == 200
        user.refresh_from_db()
        assert not user.check_password('NewSecure!99')


class TestManagerProfilePasswordChange:

    def _login(self, client, user, password='Pass123!ZZ'):
        client.login(username=user.username, password=password)

    def test_request_otp_sends_email_and_sets_session(self):
        from unittest.mock import patch
        client = Client()
        user = make_user('mgr_otp', 'manager')
        self._login(client, user)
        with patch('customers.otp_utils.send_mail') as mock_mail:
            resp = client.post(reverse('manager_profile'), {
                'action': 'request_pw_change_otp',
            })
        assert resp.status_code == 302
        assert mock_mail.called
        assert client.session.get('pw_change_pending') is True

    def test_verify_correct_otp_changes_password(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp
        client = Client()
        user = make_user('mgr_chpw', 'manager')
        self._login(client, user)
        code = generate_and_cache_pw_change_otp(user)
        session = client.session
        session['pw_change_pending'] = True
        session.save()
        resp = client.post(reverse('manager_profile'), {
            'action': 'verify_pw_change_otp',
            'otp': code,
            'new_password': 'NewSecure!99',
            'confirm_password': 'NewSecure!99',
        })
        assert resp.status_code == 302
        user.refresh_from_db()
        assert user.check_password('NewSecure!99')
        from admins.models import AuditLog
        assert AuditLog.objects.filter(
            actor=user, action_type='password_changed'
        ).exists()


class TestCustomerProfilePasswordChange:

    def _login(self, client, user, password='Pass123!ZZ'):
        client.login(username=user.username, password=password)

    def test_request_otp_sends_email_and_sets_session(self):
        from unittest.mock import patch
        client = Client()
        user = make_user('cust_otp', 'customer')
        self._login(client, user)
        with patch('customers.otp_utils.send_mail') as mock_mail:
            resp = client.post(reverse('customer_profile'), {
                'action': 'request_pw_change_otp',
            })
        assert resp.status_code == 302
        assert mock_mail.called
        assert client.session.get('pw_change_pending') is True

    def test_verify_correct_otp_changes_password(self):
        from customers.otp_utils import generate_and_cache_pw_change_otp
        client = Client()
        user = make_user('cust_chpw', 'customer')
        self._login(client, user)
        code = generate_and_cache_pw_change_otp(user)
        session = client.session
        session['pw_change_pending'] = True
        session.save()
        resp = client.post(reverse('customer_profile'), {
            'action': 'verify_pw_change_otp',
            'otp': code,
            'new_password': 'NewSecure!99',
            'confirm_password': 'NewSecure!99',
        })
        assert resp.status_code == 302
        user.refresh_from_db()
        assert user.check_password('NewSecure!99')
        from admins.models import AuditLog
        assert AuditLog.objects.filter(
            actor=user, action_type='password_changed'
        ).exists()

    def test_verify_expired_otp_clears_session(self):
        client = Client()
        user = make_user('cust_expd', 'customer')
        self._login(client, user)
        session = client.session
        session['pw_change_pending'] = True
        session.save()
        resp = client.post(reverse('customer_profile'), {
            'action': 'verify_pw_change_otp',
            'otp': '123456',
            'new_password': 'NewSecure!99',
            'confirm_password': 'NewSecure!99',
        })
        assert resp.status_code == 302
        assert not client.session.get('pw_change_pending')
