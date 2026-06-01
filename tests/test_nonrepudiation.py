import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from admins.models import Order, AuditLog

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestOrderCommitmentFields:

    def test_order_has_pending_confirmation_status(self, test_customer):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
        )
        order.refresh_from_db()
        assert order.status == 'pending_confirmation'

    def test_order_commitment_hash_defaults_empty(self, test_customer):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending',
        )
        assert order.customer_commitment_hash == ''

    def test_order_confirmed_at_defaults_null(self, test_customer):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending',
        )
        assert order.customer_confirmed_at is None

    def test_order_commitment_hash_can_be_stored(self, test_customer):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('100.00'),
            status='pending_confirmation',
            customer_commitment_hash='a' * 64,
        )
        order.refresh_from_db()
        assert order.customer_commitment_hash == 'a' * 64

    def test_audit_log_has_order_confirmed_action(self):
        action_types = [a[0] for a in AuditLog.ACTION_CHOICES]
        assert 'order_confirmed_by_customer' in action_types
