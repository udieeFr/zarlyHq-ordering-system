"""
Database performance and integrity tests — CI/CD gate.

Covers:
  - CustomerProfile.recalculate(): correctness + constant query count (no N+1)
  - PrepGroup.item_summary: N+1 prevention via prefetch_related
  - PrepGroup sequential group_id: lexicographic ordering bug (seq >9)
  - AuditLog hash chain: tamper detection
  - Model Meta.indexes: declared on hot-path tables
  - Notification unread count: composite index path
"""

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.contrib.auth import get_user_model

from admins.models import (
    AuditLog, Complaint, Notification, Order, OrderItem,
    Payment, PrepGroup, Refund,
)
from customers.models import CustomerProfile, Product

User = get_user_model()
pytestmark = pytest.mark.django_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def customer():
    return User.objects.create_user(
        username='perf_customer',
        email='perf_cust@test.com',
        password='pass',
        role='customer',
    )


@pytest.fixture
def admin_user():
    return User.objects.create_user(
        username='perf_admin',
        email='perf_admin@test.com',
        password='pass',
        role='sales_admin',
    )


@pytest.fixture
def product():
    return Product.objects.create(
        name='Perf Product',
        category='Perf Category',
        price=25.00,
        weight_grams=200,
        stock=99,
    )


@pytest.fixture
def profile(customer):
    return CustomerProfile.objects.create(user=customer)


@pytest.fixture
def approved_orders(customer, product):
    """5 approved + 2 pending. recalculate() must only sum the approved ones."""
    orders = []
    for i in range(5):
        o = Order.objects.create(
            customer=customer,
            total_amount=100.00 * (i + 1),
            status='approved',
        )
        OrderItem.objects.create(order=o, product=product, quantity=i + 1, subtotal=o.total_amount)
        orders.append(o)
    for _ in range(2):
        Order.objects.create(customer=customer, total_amount=50.00, status='pending')
    return orders


# ── CustomerProfile.recalculate() ────────────────────────────────────────────

class TestCustomerProfileRecalculate:
    """recalculate() must produce correct totals using aggregate — not Python iteration."""

    def test_totals_correct(self, profile, approved_orders):
        profile.recalculate()
        profile.refresh_from_db()

        expected = sum(o.total_amount for o in approved_orders)
        assert profile.total_orders == 5
        assert float(profile.total_spent) == float(expected)

    def test_excludes_pending_orders(self, profile, approved_orders):
        profile.recalculate()
        profile.refresh_from_db()
        # 5 approved + 2 pending were created — only 5 should count
        assert profile.total_orders == 5

    def test_query_count_is_constant(self, profile, approved_orders):
        """Must use aggregate, not iterate. Query count stays flat regardless of order volume."""
        with CaptureQueriesContext(connection) as ctx:
            profile.recalculate()
        assert len(ctx) <= 3, (
            f"recalculate() fired {len(ctx)} queries — expected ≤3. "
            "Likely still iterating orders in Python instead of using aggregate()."
        )

    def test_last_order_at_is_populated(self, profile, approved_orders):
        profile.recalculate()
        profile.refresh_from_db()
        assert profile.last_order_at is not None

    def test_no_approved_orders_zeroes_profile(self, profile, customer):
        profile.recalculate()
        profile.refresh_from_db()
        assert profile.total_orders == 0
        assert profile.total_spent == 0
        assert profile.last_order_at is None
        assert profile.loyalty_tier == 'bronze'

    @pytest.mark.parametrize('amount,expected_tier', [
        (499,  'bronze'),
        (500,  'silver'),
        (2000, 'gold'),
        (5000, 'platinum'),
    ])
    def test_loyalty_tier_thresholds(self, profile, customer, amount, expected_tier):
        """Each tier boundary must map to the correct label."""
        prod = Product.objects.create(
            name=f'TierProd_{amount}', category=f'TierCat_{amount}', price=amount, weight_grams=100, stock=1
        )
        Order.objects.create(customer=customer, total_amount=amount, status='approved')
        profile.recalculate()
        profile.refresh_from_db()
        assert profile.loyalty_tier == expected_tier, (
            f"RM {amount} → expected '{expected_tier}', got '{profile.loyalty_tier}'"
        )


# ── PrepGroup.item_summary ────────────────────────────────────────────────────

class TestPrepGroupItemSummary:
    """item_summary must not fire N+1 queries."""

    def _make_group(self, customer, product, n=4):
        orders = []
        for i in range(n):
            o = Order.objects.create(
                customer=customer,
                total_amount=product.price * (i + 1),
                status='approved',
            )
            OrderItem.objects.create(order=o, product=product, quantity=i + 1, subtotal=product.price * (i + 1))
            orders.append(o)
        pg = PrepGroup.objects.create()
        pg.orders.set(orders)
        return pg, orders

    def test_quantities_aggregated_correctly(self, customer, product):
        pg, orders = self._make_group(customer, product, n=3)
        summary = dict(pg.item_summary)
        assert product.name in summary
        # quantities 1+2+3 = 6
        assert summary[product.name]['quantity'] == 6

    def test_query_count_does_not_scale_with_order_count(self, customer, product):
        """With 5 orders, item_summary must use ≤4 queries (prefetch path), not 11+."""
        pg, _ = self._make_group(customer, product, n=5)

        with CaptureQueriesContext(connection) as ctx:
            _ = pg.item_summary

        assert len(ctx) <= 4, (
            f"item_summary fired {len(ctx)} queries for 5 orders — expected ≤4. "
            "Missing prefetch_related('items__product')."
        )

    def test_empty_group_returns_empty(self, customer):
        pg = PrepGroup.objects.create()
        assert pg.item_summary == []


# ── PrepGroup sequential group_id ────────────────────────────────────────────

class TestPrepGroupSequentialId:
    """group_id seq must be numerically correct past seq 9 (lexicographic sort bug)."""

    def test_sequential_ids_through_12(self, customer):
        orders = [
            Order.objects.create(customer=customer, total_amount=50, status='approved')
            for _ in range(12)
        ]
        groups = []
        for o in orders:
            pg = PrepGroup.objects.create()
            pg.orders.set([o])
            groups.append(pg)

        seqs = [int(pg.group_id.split('-')[-1]) for pg in groups]
        assert seqs == list(range(1, 13)), (
            f"Expected 1-12 but got {seqs}. "
            "String sort on group_id breaks at seq 10 (e.g. '9' > '10' lexicographically)."
        )

    def test_group_id_format_is_op_yymmdd_nn(self, customer):
        o = Order.objects.create(customer=customer, total_amount=50, status='pending')
        pg = PrepGroup.objects.create()
        pg.orders.set([o])
        parts = pg.group_id.split('-')
        assert len(parts) == 3, f"Expected OP-YYMMDD-NN, got '{pg.group_id}'"
        assert parts[0] == 'OP'
        assert len(parts[1]) == 6 and parts[1].isdigit(), f"Date part invalid: '{parts[1]}'"
        assert parts[2].isdigit(), f"Seq part invalid: '{parts[2]}'"


# ── AuditLog hash chain ───────────────────────────────────────────────────────

class TestAuditLogChain:
    """verify_chain() must detect any altered or deleted entry."""

    def _entry(self, actor, action='order_created', target_id=1):
        return AuditLog.objects.create(
            actor=actor,
            action_type=action,
            target_model='Order',
            target_id=target_id,
            description='CI test entry',
            ip_address='127.0.0.1',
        )

    def test_unmodified_chain_is_valid(self, admin_user):
        for i in range(4):
            self._entry(admin_user, target_id=i + 1)
        valid, broken_at = AuditLog.verify_chain()
        assert valid is True
        assert broken_at is None

    def test_tampered_entry_breaks_chain(self, admin_user):
        entries = [self._entry(admin_user, target_id=i + 1) for i in range(3)]
        # Bypass save() so chain_hash stays stale while description changes
        AuditLog.objects.filter(pk=entries[1].pk).update(description='TAMPERED')
        valid, broken_at = AuditLog.verify_chain()
        assert valid is False
        assert broken_at == entries[1].pk

    def test_all_entries_have_unique_hashes(self, admin_user):
        entries = [self._entry(admin_user, target_id=i + 1) for i in range(5)]
        hashes = [e.chain_hash for e in entries]
        assert len(set(hashes)) == len(hashes), "Duplicate or empty chain hashes detected"

    def test_each_entry_has_nonempty_hash(self, admin_user):
        entry = self._entry(admin_user)
        assert entry.chain_hash, "chain_hash must be set on every new AuditLog entry"


# ── Model Meta.indexes declarations ──────────────────────────────────────────

class TestIndexDeclarations:
    """
    Verify that Meta.indexes are declared on every hot-path model.
    Tests the model definition — runs without hitting the database.
    """

    @staticmethod
    def _field_tuples(model):
        """Return a list of (field, ...) tuples stripping the '-' sort prefix."""
        return [
            tuple(f.lstrip('-') for f in idx.fields)
            for idx in model._meta.indexes
        ]

    def test_order_has_status_index(self):
        assert ('status',) in self._field_tuples(Order), \
            "Order missing index on status — every dashboard query will seq-scan"

    def test_order_has_status_created_at_index(self):
        assert ('status', 'created_at') in self._field_tuples(Order), \
            "Order missing composite index on (status, created_at)"

    def test_order_has_customer_created_at_index(self):
        assert ('customer', 'created_at') in self._field_tuples(Order), \
            "Order missing composite index on (customer, created_at)"

    def test_order_has_priority_status_index(self):
        assert ('is_priority', 'status') in self._field_tuples(Order), \
            "Order missing composite index on (is_priority, status)"

    def test_complaint_has_status_index(self):
        assert ('status',) in self._field_tuples(Complaint), \
            "Complaint missing index on status"

    def test_refund_has_status_index(self):
        assert ('status', 'created_at') in self._field_tuples(Refund), \
            "Refund missing index on (status, created_at)"

    def test_refund_has_order_index(self):
        assert ('order', 'created_at') in self._field_tuples(Refund), \
            "Refund missing index on (order, created_at)"

    def test_notification_has_composite_index(self):
        assert ('recipient', 'is_read', 'created_at') in self._field_tuples(Notification), \
            "Notification missing composite index on (recipient, is_read, created_at)"

    def test_payment_does_not_have_redundant_stripe_session_index(self):
        """stripe_session_id has unique=True which already creates an index."""
        index_fields = self._field_tuples(Payment)
        assert ('stripe_session_id',) not in index_fields, \
            "Payment has redundant explicit index on stripe_session_id — unique=True already covers it"

    def test_audit_log_has_actor_timestamp_index(self):
        assert ('actor', 'timestamp') in self._field_tuples(AuditLog), \
            "AuditLog missing composite index on (actor, timestamp)"


# ── Notification unread count ─────────────────────────────────────────────────

class TestNotificationQueries:
    """Unread notification count is queried on every page load — must be correct."""

    def test_unread_count_correct(self, customer):
        for i in range(6):
            Notification.objects.create(
                recipient=customer,
                title=f'Notif {i}',
                message='Test',
                is_read=(i % 2 == 0),  # 0,2,4 read → 1,3,5 unread
            )
        count = Notification.objects.filter(recipient=customer, is_read=False).count()
        assert count == 3

    def test_mark_read_fires_single_query(self, customer):
        notif = Notification.objects.create(
            recipient=customer,
            title='Test',
            message='Hello',
            is_read=False,
        )
        with CaptureQueriesContext(connection) as ctx:
            notif.mark_read()
        assert len(ctx) == 1, f"mark_read() fired {len(ctx)} queries — expected 1 UPDATE"

    def test_mark_read_is_idempotent(self, customer):
        notif = Notification.objects.create(
            recipient=customer, title='X', message='Y', is_read=False
        )
        notif.mark_read()
        with CaptureQueriesContext(connection) as ctx:
            notif.mark_read()  # already read — should be a no-op
        assert len(ctx) == 0, "mark_read() on already-read notification should not fire a query"


# ── Order status filtering ────────────────────────────────────────────────────

class TestOrderStatusFiltering:
    """Basic status filter correctness — regression guard for dashboard queries."""

    @pytest.fixture(autouse=True)
    def seed_orders(self, customer):
        statuses = ['pending', 'pending', 'approved', 'delivered', 'rejected', 'cancelled']
        for s in statuses:
            Order.objects.create(customer=customer, total_amount=100, status=s)

    def test_pending_filter(self):
        assert Order.objects.filter(status='pending').count() == 2

    def test_approved_filter(self):
        assert Order.objects.filter(status='approved').count() == 1

    def test_active_orders_filter(self):
        active = Order.objects.filter(status__in=['pending', 'approved', 'prepared']).count()
        assert active == 3

    def test_is_priority_filter(self, customer):
        Order.objects.create(customer=customer, total_amount=200, status='pending', is_priority=True)
        assert Order.objects.filter(is_priority=True, status='pending').count() == 1
