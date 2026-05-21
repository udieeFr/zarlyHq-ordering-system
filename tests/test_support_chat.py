import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()
pytestmark = pytest.mark.django_db

TEST_KEY = 'chz6Xd7HkrP1AZq3FLCymr1_tPW29rcVbdDuV-CaE2c='


# Apply the test key to every test in this module automatically.
@pytest.fixture(autouse=True)
def set_chat_key(settings):
    settings.SUPPORT_CHAT_KEY = TEST_KEY


# ── Crypto ───────────────────────────────────────────────────────────────────

class TestChatCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        from admins.chat_crypto import encrypt_message, decrypt_message
        plaintext = "Hello, this is a secret message."
        assert decrypt_message(encrypt_message(plaintext)) == plaintext

    def test_encrypted_differs_from_plaintext(self):
        from admins.chat_crypto import encrypt_message
        assert encrypt_message("test") != "test"

    def test_decrypt_invalid_raises(self):
        from admins.chat_crypto import decrypt_message
        with pytest.raises(Exception):
            decrypt_message("notvalidciphertext")


# ── Model ────────────────────────────────────────────────────────────────────

class TestSupportMessageModel:
    def _make_complaint(self):
        from admins.models import Order, Complaint
        customer = User.objects.create_user(
            username='chatcust', email='chatcust@t.com', password='pass', role='customer'
        )
        order = Order.objects.create(customer=customer, total_amount=100, status='delivered')
        return Complaint.objects.create(order=order, customer=customer, subject='Test', message='Msg')

    def test_ordering_oldest_first(self):
        from admins.models import SupportMessage
        complaint = self._make_complaint()
        admin = User.objects.create_user(
            username='chatadmin1', email='ca1@t.com', password='pass', role='sales_admin'
        )
        m1 = SupportMessage.objects.create(complaint=complaint, sender=admin, body='first')
        m2 = SupportMessage.objects.create(complaint=complaint, sender=admin, body='second')
        msgs = list(SupportMessage.objects.filter(complaint=complaint))
        assert msgs[0].pk == m1.pk
        assert msgs[1].pk == m2.pk

    def test_is_read_defaults_false(self):
        from admins.models import SupportMessage
        complaint = self._make_complaint()
        admin = User.objects.create_user(
            username='chatadmin2', email='ca2@t.com', password='pass', role='sales_admin'
        )
        msg = SupportMessage.objects.create(complaint=complaint, sender=admin, body='hi')
        assert msg.is_read is False

    def test_complaint_created_at_index_declared(self):
        from admins.models import SupportMessage
        index_fields = [
            tuple(f.lstrip('-') for f in idx.fields)
            for idx in SupportMessage._meta.indexes
        ]
        assert ('complaint', 'created_at') in index_fields

    def test_support_message_sent_is_valid_audit_action(self):
        from admins.models import AuditLog
        valid_actions = [a[0] for a in AuditLog.ACTION_CHOICES]
        assert 'support_message_sent' in valid_actions


# ── Admin endpoints ───────────────────────────────────────────────────────────

class TestAdminComplaintMessages:
    @pytest.fixture(autouse=True)
    def setup(self):
        from admins.models import Order, Complaint
        self.client = Client()
        self.customer = User.objects.create_user(
            username='acm_cust', email='acm_c@t.com', password='pass', role='customer'
        )
        self.admin = User.objects.create_user(
            username='acm_admin', email='acm_a@t.com', password='pass', role='sales_admin'
        )
        order = Order.objects.create(customer=self.customer, total_amount=100, status='delivered')
        self.complaint = Complaint.objects.create(
            order=order, customer=self.customer, subject='S', message='M'
        )

    def _url(self):
        return reverse('admin_complaint_messages', args=[self.complaint.id])

    def test_unauthenticated_redirects(self):
        r = self.client.get(self._url())
        assert r.status_code == 302

    def test_customer_cannot_access(self):
        self.client.force_login(self.customer)
        r = self.client.get(self._url())
        assert r.status_code in (302, 403)

    def test_admin_get_returns_json(self):
        self.client.force_login(self.admin)
        r = self.client.get(self._url())
        assert r.status_code == 200
        data = r.json()
        assert 'messages' in data
        assert 'locked' in data
        assert data['locked'] is False

    def test_admin_post_creates_message(self):
        from admins.models import SupportMessage
        self.client.force_login(self.admin)
        r = self.client.post(self._url(), {'body': 'Hello customer'})
        assert r.status_code == 200
        assert r.json()['ok'] is True
        assert SupportMessage.objects.filter(complaint=self.complaint).count() == 1

    def test_post_empty_body_returns_400(self):
        self.client.force_login(self.admin)
        r = self.client.post(self._url(), {'body': ''})
        assert r.status_code == 400

    def test_post_locked_when_resolved(self):
        from admins.models import Complaint
        Complaint.objects.filter(pk=self.complaint.pk).update(status='resolved')
        self.client.force_login(self.admin)
        r = self.client.post(self._url(), {'body': 'too late'})
        assert r.status_code == 403

    def test_since_filter_returns_only_new(self):
        from admins.models import SupportMessage
        self.client.force_login(self.admin)
        # Create first message and read its actual DB timestamp
        msg1 = SupportMessage.objects.create(complaint=self.complaint, sender=self.admin, body='msg1')
        msg1.refresh_from_db()
        # Pass as dict so the test client URL-encodes '+' in '+00:00' correctly
        cutoff = msg1.created_at.isoformat()
        # Create second message — will have a later created_at than msg1
        msg2 = SupportMessage.objects.create(complaint=self.complaint, sender=self.admin, body='msg2')
        msg2.refresh_from_db()
        # since=msg1.created_at: msg1 excluded (__gt), msg2 included
        r = self.client.get(self._url(), {'since': cutoff})
        data = r.json()
        returned_ids = [m['id'] for m in data['messages']]
        assert msg1.id not in returned_ids
        assert msg2.id in returned_ids

    def test_audit_log_created_on_send(self):
        from admins.models import AuditLog
        self.client.force_login(self.admin)
        self.client.post(self._url(), {'body': 'audit this'})
        assert AuditLog.objects.filter(action_type='support_message_sent').exists()


# ── Customer endpoints ────────────────────────────────────────────────────────

class TestCustomerComplaintMessages:
    @pytest.fixture(autouse=True)
    def setup(self):
        from admins.models import Order, Complaint
        self.client = Client()
        self.customer = User.objects.create_user(
            username='ccm_cust', email='ccm_c@t.com', password='pass', role='customer'
        )
        self.other = User.objects.create_user(
            username='ccm_other', email='ccm_o@t.com', password='pass', role='customer'
        )
        self.admin = User.objects.create_user(
            username='ccm_admin', email='ccm_a@t.com', password='pass', role='sales_admin'
        )
        order = Order.objects.create(customer=self.customer, total_amount=100, status='delivered')
        self.complaint = Complaint.objects.create(
            order=order, customer=self.customer, subject='S', message='M'
        )

    def _detail_url(self):
        return reverse('customer_complaint_detail', args=[self.complaint.id])

    def _msg_url(self):
        return reverse('customer_complaint_messages', args=[self.complaint.id])

    def test_detail_unauthenticated_redirects(self):
        r = self.client.get(self._detail_url())
        assert r.status_code == 302

    def test_detail_other_customer_gets_404(self):
        self.client.force_login(self.other)
        r = self.client.get(self._detail_url())
        assert r.status_code == 404

    def test_detail_owner_gets_200(self):
        self.client.force_login(self.customer)
        r = self.client.get(self._detail_url())
        assert r.status_code == 200

    def test_messages_other_customer_gets_404(self):
        self.client.force_login(self.other)
        r = self.client.get(self._msg_url())
        assert r.status_code == 404

    def test_messages_owner_get_returns_json(self):
        self.client.force_login(self.customer)
        r = self.client.get(self._msg_url())
        assert r.status_code == 200
        data = r.json()
        assert 'messages' in data
        assert 'locked' in data

    def test_customer_post_creates_message(self):
        from admins.models import SupportMessage
        self.client.force_login(self.customer)
        r = self.client.post(self._msg_url(), {'body': 'Please help!'})
        assert r.status_code == 200
        assert r.json()['ok'] is True
        assert SupportMessage.objects.filter(complaint=self.complaint).count() == 1

    def test_post_empty_body_returns_400(self):
        self.client.force_login(self.customer)
        r = self.client.post(self._msg_url(), {'body': ''})
        assert r.status_code == 400

    def test_post_locked_when_resolved(self):
        from admins.models import Complaint
        Complaint.objects.filter(pk=self.complaint.pk).update(status='resolved')
        self.client.force_login(self.customer)
        r = self.client.post(self._msg_url(), {'body': 'too late'})
        assert r.status_code == 403

    def test_audit_log_created_on_send(self):
        from admins.models import AuditLog
        self.client.force_login(self.customer)
        self.client.post(self._msg_url(), {'body': 'audit this'})
        assert AuditLog.objects.filter(action_type='support_message_sent').exists()

    def test_messages_decrypted_in_response(self):
        from admins.models import SupportMessage
        from admins.chat_crypto import encrypt_message
        SupportMessage.objects.create(
            complaint=self.complaint,
            sender=self.customer,
            body=encrypt_message('decrypted text'),
        )
        self.client.force_login(self.customer)
        r = self.client.get(self._msg_url())
        bodies = [m['body'] for m in r.json()['messages']]
        assert 'decrypted text' in bodies
