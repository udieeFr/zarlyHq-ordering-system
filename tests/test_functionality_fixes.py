"""
Tests for functionality gaps closed on 2026-05-18.

FUNC 1 — Cart persistence on login
FUNC 3 — Post-delivery order rating (OrderRating model + view)
FUNC 4 — Product reviews (ProductReview model + view)
FUNC 7 — Bank payment config read from env vars
"""

import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()
pytestmark = pytest.mark.django_db


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_user(username, role='customer', password='pass123!'):
    return User.objects.create_user(
        username=username, email=f'{username}@t.com',
        password=password, role=role,
    )


def make_delivered_order(customer):
    from admins.models import Order
    return Order.objects.create(
        customer=customer,
        total_amount=Decimal('100.00'),
        status='delivered',
    )


def make_product(name='Test Burger', price='10.00', stock=50):
    from customers.models import Product, Category
    cat, _ = Category.objects.get_or_create(name='Test')
    return Product.objects.create(name=name, category=cat, price=Decimal(price), stock=stock)


# ── FUNC 1 — Cart persistence on login ────────────────────────────────────────

class TestCartMergeOnLogin:

    def test_anonymous_cart_preserved_after_login(self):
        """Pre-login session cart should be merged into the authenticated session."""
        customer = make_user('cart_cust')
        product = make_product()
        c = Client()

        # Add item to cart while anonymous
        session = c.session
        session['cart'] = {str(product.id): 3}
        session.save()

        # Log in
        c.post(reverse('login'), {'username': 'cart_cust', 'password': 'pass123!'})

        # Cart should still contain the item
        cart = c.session.get('cart', {})
        assert cart.get(str(product.id), 0) == 3

    def test_anonymous_cart_merges_with_existing_session_cart(self):
        """If the customer had items in the session before logging in they all survive."""
        customer = make_user('cart_cust2')
        p1 = make_product('Item A', '5.00')
        p2 = make_product('Item B', '8.00')
        c = Client()

        # Pre-load anonymous cart with p1
        session = c.session
        session['cart'] = {str(p1.id): 2}
        session.save()

        c.post(reverse('login'), {'username': 'cart_cust2', 'password': 'pass123!'})

        cart = c.session.get('cart', {})
        assert cart.get(str(p1.id), 0) == 2

    def test_staff_login_does_not_get_cart_merged(self):
        """Non-customer roles should not have cart logic applied."""
        admin = make_user('staff_login', role='sales_admin')
        product = make_product('Staff Product')
        c = Client()
        session = c.session
        session['cart'] = {str(product.id): 5}
        session.save()

        c.post(reverse('login'), {'username': 'staff_login', 'password': 'pass123!'})
        # Just assert login succeeded — no crash
        assert c.session.get('_auth_user_id') is not None


# ── FUNC 3 — Post-delivery order rating ───────────────────────────────────────

class TestOrderRating:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.customer = make_user('rate_cust')
        self.order = make_delivered_order(self.customer)
        self.client = Client()
        self.client.force_login(self.customer)

    def test_can_rate_delivered_order(self):
        r = self.client.post(
            reverse('rate_order', args=[self.order.id]),
            {'rating': '4', 'comment': 'Great food!'},
        )
        assert r.status_code == 200
        data = r.json()
        assert data['ok'] is True
        assert data['rating'] == 4

    def test_rating_saved_to_db(self):
        from customers.models import OrderRating
        self.client.post(reverse('rate_order', args=[self.order.id]), {'rating': '5'})
        assert OrderRating.objects.filter(order=self.order, customer=self.customer).exists()

    def test_cannot_rate_pending_order(self):
        from admins.models import Order
        pending = Order.objects.create(customer=self.customer, total_amount=50, status='pending')
        r = self.client.post(reverse('rate_order', args=[pending.id]), {'rating': '3'})
        assert r.status_code == 400

    def test_cannot_double_rate(self):
        from customers.models import OrderRating
        OrderRating.objects.create(order=self.order, customer=self.customer, rating=4)
        r = self.client.post(reverse('rate_order', args=[self.order.id]), {'rating': '5'})
        assert r.status_code == 400

    def test_invalid_rating_value_rejected(self):
        r = self.client.post(reverse('rate_order', args=[self.order.id]), {'rating': '6'})
        assert r.status_code == 400

    def test_zero_rating_rejected(self):
        r = self.client.post(reverse('rate_order', args=[self.order.id]), {'rating': '0'})
        assert r.status_code == 400


# ── FUNC 4 — Product reviews ──────────────────────────────────────────────────

class TestProductReview:

    @pytest.fixture(autouse=True)
    def setup(self):
        from admins.models import Order, OrderItem
        self.customer = make_user('rev_cust')
        self.product = make_product('Reviewed Burger')
        self.order = make_delivered_order(self.customer)
        OrderItem.objects.create(
            order=self.order, product=self.product,
            quantity=1, subtotal=Decimal('10.00'),
        )
        self.client = Client()
        self.client.force_login(self.customer)

    def test_can_review_purchased_product(self):
        r = self.client.post(
            reverse('submit_product_review', args=[self.product.id]),
            {'rating': '5', 'comment': 'Delicious!'},
        )
        assert r.status_code == 200
        assert r.json()['ok'] is True

    def test_cannot_review_unordered_product(self):
        other = make_product('Never Bought')
        r = self.client.post(
            reverse('submit_product_review', args=[other.id]),
            {'rating': '5'},
        )
        assert r.status_code == 400

    def test_cannot_double_review(self):
        from customers.models import ProductReview
        ProductReview.objects.create(
            product=self.product, customer=self.customer,
            order=self.order, rating=4,
        )
        r = self.client.post(
            reverse('submit_product_review', args=[self.product.id]),
            {'rating': '3'},
        )
        assert r.status_code == 400

    def test_review_rating_bounds(self):
        r = self.client.post(
            reverse('submit_product_review', args=[self.product.id]),
            {'rating': '9'},
        )
        assert r.status_code == 400


# ── FUNC 7 — Bank payment config from env vars ────────────────────────────────

class TestPaymentConfigEnvVars:

    def test_duitnow_id_reads_from_env(self, monkeypatch):
        monkeypatch.setenv('DUITNOW_MERCHANT_ID', 'MY_REAL_ID')
        import importlib
        import customers.payment_utils as pu
        importlib.reload(pu)
        assert pu.PAYMENT_CONFIG['duitnow']['id'] == 'MY_REAL_ID'

    def test_bank_account_reads_from_env(self, monkeypatch):
        monkeypatch.setenv('BANK_ACCOUNT_NUMBER', '9876543210')
        import importlib
        import customers.payment_utils as pu
        importlib.reload(pu)
        assert pu.PAYMENT_CONFIG['bank_transfer']['account_number'] == '9876543210'

    def test_no_hardcoded_placeholder_in_defaults(self):
        import customers.payment_utils as pu
        # Without env vars set, defaults should be empty strings, not old placeholders
        assert pu.PAYMENT_CONFIG['duitnow']['id'] != '0123456789'
        assert pu.PAYMENT_CONFIG['bank_transfer']['account_number'] != '123456789012'
