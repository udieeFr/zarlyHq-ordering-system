import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from admins.models import Order, AuditLog, OrderItem
from customers.models import Product
from customers.views import compute_order_commitment_hash
from customers.otp_utils import generate_and_cache_order_otp, verify_order_otp
from django.core.cache import cache

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


class TestCommitmentHash:

    def test_hash_is_64_char_hex(self, test_customer, test_product):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('60.00'),
            shipping_fee=Decimal('10.00'),
            status='pending_confirmation',
            formatted_address='123 Jalan Test, KL',
        )
        OrderItem.objects.create(
            order=order, product=test_product,
            quantity=1, unit_price=Decimal('50.00'),
            is_bundle=False, subtotal=Decimal('50.00'),
        )
        h = compute_order_commitment_hash(order)
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)

    def test_hash_is_deterministic(self, test_customer, test_product):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('60.00'),
            shipping_fee=Decimal('10.00'),
            status='pending_confirmation',
            formatted_address='123 Jalan Test, KL',
        )
        OrderItem.objects.create(
            order=order, product=test_product,
            quantity=2, unit_price=Decimal('25.00'),
            is_bundle=False, subtotal=Decimal('50.00'),
        )
        assert compute_order_commitment_hash(order) == compute_order_commitment_hash(order)

    def test_hash_changes_if_total_changes(self, test_customer, test_product):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('60.00'),
            shipping_fee=Decimal('10.00'),
            status='pending_confirmation',
        )
        OrderItem.objects.create(
            order=order, product=test_product,
            quantity=1, unit_price=Decimal('50.00'),
            is_bundle=False, subtotal=Decimal('50.00'),
        )
        h1 = compute_order_commitment_hash(order)
        order.total_amount = Decimal('70.00')
        order.save(update_fields=['total_amount'])
        h2 = compute_order_commitment_hash(order)
        assert h1 != h2


class TestOrderOtp:

    def test_generate_order_otp_returns_6_digits(self, test_customer):
        otp = generate_and_cache_order_otp(test_customer)
        assert len(otp) == 6
        assert otp.isdigit()

    def test_verify_order_otp_ok(self, test_customer):
        otp = generate_and_cache_order_otp(test_customer)
        assert verify_order_otp(test_customer, otp) == 'ok'

    def test_verify_order_otp_invalid(self, test_customer):
        generate_and_cache_order_otp(test_customer)
        assert verify_order_otp(test_customer, '000000') == 'invalid'

    def test_verify_order_otp_expired_when_not_generated(self, test_customer):
        cache.delete(f'order_confirm_otp_{test_customer.pk}')
        assert verify_order_otp(test_customer, '123456') == 'expired'

    def test_order_otp_does_not_collide_with_email_otp(self, test_customer):
        from customers.otp_utils import generate_and_cache_otp, verify_otp
        email_otp = generate_and_cache_otp(test_customer)
        order_otp = generate_and_cache_order_otp(test_customer)
        assert verify_otp(test_customer, email_otp) == 'ok'
        assert verify_order_otp(test_customer, order_otp) == 'ok'
