"""
Tests for stock race condition fix in _create_order_atomic.

The key behaviour under test:
  - SELECT FOR UPDATE locks product rows during the transaction so two
    concurrent requests cannot both read stock=1 and both succeed.
  - If stock is insufficient the whole transaction rolls back (no orphan Order).
  - Normal single-request ordering still works correctly.
"""

import threading
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from customers.models import Product
from customers.views import _create_order_atomic
from admins.models import Order, OrderItem

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def customer(db):
    return User.objects.create_user(
        username='race_customer',
        email='race@test.com',
        password='TestPass123!',
        role='customer',
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        name='Last Nasi Lemak',
        category='Race Category',
        price=Decimal('12.00'),
        stock=5,
    )


def _cart_items(product, quantity=1):
    """Build a minimal cart_items list matching what get_cart_from_session returns."""
    return [{
        'product': product,
        'quantity': quantity,
        'subtotal': product.price * quantity,
    }]


def _order_fields():
    return dict(
        full_name='Test User',
        phone_number='0123456789',
        street_address='1 Test St',
        city='KL',
        state='WP',
        postcode='50000',
        latitude=None,
        longitude=None,
        formatted_address='1 Test St, KL',
        order_notes='',
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestCreateOrderAtomicHappyPath:

    def test_order_is_created_in_db(self, customer, product):
        order = _create_order_atomic(
            customer, Decimal('12.00'), _cart_items(product), **_order_fields()
        )
        assert Order.objects.filter(id=order.id).exists()

    def test_order_item_is_created(self, customer, product):
        order = _create_order_atomic(
            customer, Decimal('12.00'), _cart_items(product), **_order_fields()
        )
        assert OrderItem.objects.filter(order=order, product=product, quantity=1).exists()

    def test_stock_is_decremented(self, customer, product):
        initial_stock = product.stock
        _create_order_atomic(
            customer, Decimal('12.00'), _cart_items(product, quantity=2), **_order_fields()
        )
        product.refresh_from_db()
        assert product.stock == initial_stock - 2

    def test_order_total_matches(self, customer, product):
        total = Decimal('24.00')
        order = _create_order_atomic(
            customer, total, _cart_items(product, quantity=2), **_order_fields()
        )
        assert order.total_amount == total

    def test_order_status_is_pending(self, customer, product):
        order = _create_order_atomic(
            customer, Decimal('12.00'), _cart_items(product), **_order_fields()
        )
        assert order.status == 'pending'


# ---------------------------------------------------------------------------
# Stock validation
# ---------------------------------------------------------------------------

class TestStockValidation:

    def test_raises_value_error_when_insufficient_stock(self, customer, product):
        product.stock = 1
        product.save()
        with pytest.raises(ValueError, match="Last Nasi Lemak"):
            _create_order_atomic(
                customer, Decimal('24.00'), _cart_items(product, quantity=2), **_order_fields()
            )

    def test_error_message_mentions_available_stock(self, customer, product):
        product.stock = 3
        product.save()
        with pytest.raises(ValueError, match="3"):
            _create_order_atomic(
                customer, Decimal('60.00'), _cart_items(product, quantity=5), **_order_fields()
            )

    def test_order_row_is_rolled_back_on_stock_failure(self, customer, product):
        """No orphan Order should exist when stock check fails."""
        product.stock = 0
        product.save()
        orders_before = Order.objects.count()
        with pytest.raises(ValueError):
            _create_order_atomic(
                customer, Decimal('12.00'), _cart_items(product, quantity=1), **_order_fields()
            )
        assert Order.objects.count() == orders_before

    def test_exact_stock_quantity_succeeds(self, customer, product):
        product.stock = 3
        product.save()
        order = _create_order_atomic(
            customer, Decimal('36.00'), _cart_items(product, quantity=3), **_order_fields()
        )
        product.refresh_from_db()
        assert product.stock == 0
        assert order.id is not None

    def test_zero_stock_always_fails(self, customer, product):
        product.stock = 0
        product.save()
        with pytest.raises(ValueError):
            _create_order_atomic(
                customer, Decimal('12.00'), _cart_items(product, quantity=1), **_order_fields()
            )


# ---------------------------------------------------------------------------
# Concurrency — the actual race condition test
# Requires transaction=True so each thread gets a real DB transaction and
# SELECT FOR UPDATE can actually block between threads.
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestConcurrentOrders:

    def test_only_one_succeeds_when_stock_is_one(self):
        """
        Two threads both try to buy the last unit at the same time.
        SELECT FOR UPDATE ensures only one wins; the other gets ValueError.
        """
        product = Product.objects.create(
            name='Limited Item',
            category='Concurrent Cat',
            price=Decimal('10.00'),
            stock=1,
        )
        user1 = User.objects.create_user(
            username='buyer1', email='b1@test.com', password='x', role='customer'
        )
        user2 = User.objects.create_user(
            username='buyer2', email='b2@test.com', password='x', role='customer'
        )

        results = []
        barrier = threading.Barrier(2)  # both threads start at the same instant

        def attempt(user):
            barrier.wait()
            try:
                _create_order_atomic(
                    user, Decimal('10.00'),
                    [{'product': product, 'quantity': 1, 'subtotal': Decimal('10.00')}],
                    **_order_fields()
                )
                results.append('ok')
            except ValueError:
                results.append('fail')

        t1 = threading.Thread(target=attempt, args=(user1,))
        t2 = threading.Thread(target=attempt, args=(user2,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        product.refresh_from_db()
        assert results.count('ok') == 1, "Exactly one order should succeed"
        assert results.count('fail') == 1, "Exactly one order should be rejected"
        assert product.stock == 0, "Stock must reach 0, not go negative"

    def test_stock_never_goes_negative_under_concurrency(self):
        """
        Three threads compete for 2 units. Stock must never go below 0.
        """
        product = Product.objects.create(
            name='Scarce Item',
            category='Concurrent Cat 2',
            price=Decimal('20.00'),
            stock=2,
        )
        users = [
            User.objects.create_user(
                username=f'buyer_c{i}', email=f'bc{i}@test.com',
                password='x', role='customer'
            )
            for i in range(3)
        ]

        results = []
        barrier = threading.Barrier(3)

        def attempt(user):
            barrier.wait()
            try:
                _create_order_atomic(
                    user, Decimal('20.00'),
                    [{'product': product, 'quantity': 1, 'subtotal': Decimal('20.00')}],
                    **_order_fields()
                )
                results.append('ok')
            except ValueError:
                results.append('fail')

        threads = [threading.Thread(target=attempt, args=(u,)) for u in users]
        for t in threads: t.start()
        for t in threads: t.join()

        product.refresh_from_db()
        assert product.stock >= 0, "Stock must never go negative"
        assert results.count('ok') == 2, "Exactly 2 of 3 orders should succeed"
        assert results.count('fail') == 1, "Exactly 1 of 3 orders should be rejected"
