"""
Tests for Stripe payment flow.

These tests cover the smallest useful slice of the Stripe integration:
- Create a Stripe Checkout Session and persist a Payment row
- Process a completed checkout session via the webhook helper
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from admins.models import Order, OrderItem, Payment
from customers.stripe_utils import (
    create_stripe_checkout_session,
    handle_checkout_session_completed,
)


pytestmark = pytest.mark.django_db


class TestStripeCheckoutSession:
    def test_create_checkout_session_persists_payment(self, test_customer, test_product):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('50.00'),
            status='pending',
            full_name='Test Customer',
            phone_number='0123456789',
            street_address='123 Main St',
            city='Kuala Lumpur',
            state='Wilayah Persekutuan',
            postcode='50000',
        )
        OrderItem.objects.create(
            order=order,
            product=test_product,
            quantity=1,
            subtotal=Decimal('50.00'),
        )

        request = RequestFactory().get('/')
        request.user = test_customer

        fake_session = SimpleNamespace(id='cs_test_123', url='https://checkout.stripe.com/pay/cs_test_123')

        with patch('customers.stripe_utils.stripe.checkout.Session.create', return_value=fake_session) as mock_create:
            session_id, error = create_stripe_checkout_session(order, request)

        assert error is None
        assert session_id == 'cs_test_123'
        mock_create.assert_called_once()
        payment = Payment.objects.get(order=order)
        assert payment.payment_method == 'stripe'
        assert payment.status == 'pending'
        assert payment.stripe_session_id == 'cs_test_123'


class TestStripeWebhookHelpers:
    def test_checkout_session_completed_marks_payment_succeeded(self, test_customer, test_product):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=Decimal('50.00'),
            status='pending_payment',
            full_name='Test Customer',
            phone_number='0123456789',
            street_address='123 Main St',
            city='Kuala Lumpur',
            state='Wilayah Persekutuan',
            postcode='50000',
        )
        OrderItem.objects.create(
            order=order,
            product=test_product,
            quantity=1,
            subtotal=Decimal('50.00'),
        )
        payment = Payment.objects.create(
            order=order,
            payment_method='stripe',
            status='pending',
            amount=Decimal('50.00'),
            currency='MYR',
            stripe_session_id='cs_test_123',
        )

        fake_session = SimpleNamespace(
            id='cs_test_123',
            payment_intent='pi_test_123',
            customer='cus_test_123',
        )

        with patch('customers.stripe_utils.stripe.checkout.Session.retrieve', return_value=fake_session):
            success, message = handle_checkout_session_completed('cs_test_123', {'type': 'checkout.session.completed'})

        assert success is True
        assert 'confirmed' in message.lower()
        payment.refresh_from_db()
        order.refresh_from_db()
        assert payment.status == 'succeeded'
        assert payment.stripe_payment_intent_id == 'pi_test_123'
        assert payment.stripe_customer_id == 'cus_test_123'
        assert order.status == 'pending_payment'
