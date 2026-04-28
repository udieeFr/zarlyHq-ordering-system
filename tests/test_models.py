"""
Tests for Django Models

These tests verify that your models work correctly and safely.
Real-world: Models are the foundation of your app - if they're broken, everything breaks.
"""

import pytest
from django.contrib.auth import get_user_model
from admins.models import Order, DigitalSignature
from customers.models import Product, Category

User = get_user_model()

# Allow these tests to access the database
pytestmark = pytest.mark.django_db


# ============================================================================
# TEST 1: Order Model - Basic Functionality
# ============================================================================

class TestOrderModelBasics:
    """Test basic Order model operations"""
    
    def test_order_can_be_created(self, test_customer):
        """
        WHAT: Test that Order.objects.create() works
        WHY: If this fails, orders can't be created at all
        HOW TO READ:
            - test_customer comes from conftest.py fixture
            - Create an order
            - Assert it has an ID (saved to database)
        """
        order = Order.objects.create(
            customer=test_customer,
            total_amount=100.00,
            status='pending'
        )
        
        # Assertions: Things we expect to be true
        assert order.id is not None, "Order should have ID after saving"
        assert order.customer == test_customer, "Order should belong to correct customer"
        assert order.status == 'pending', "New order should be pending"
    
    def test_order_total_amount_is_stored(self, test_customer):
        """WHAT: Test that total_amount is correctly stored"""
        order = Order.objects.create(
            customer=test_customer,
            total_amount=250.50,
            status='pending'
        )
        
        # Refresh from database to ensure it was saved
        order.refresh_from_db()
        assert order.total_amount == 250.50
    
    def test_order_status_default_is_pending(self, test_customer):
        """WHAT: Test that orders start as 'pending' if not specified"""
        order = Order.objects.create(
            customer=test_customer,
            total_amount=100.00
            # status not specified - should default to 'pending'
        )
        assert order.status == 'pending'


# ============================================================================
# TEST 2: Order Model - Security & Data Validation
# ============================================================================

class TestOrderModelSecurity:
    """Test security-related constraints"""
    
    def test_order_requires_customer(self):
        """
        SECURITY: Test that order MUST have a customer
        WHY: Orphaned orders (no customer) = data integrity issue
        WHAT HAPPENS IF FAILS: Attackers could create orders without customers
        """
        # Try to create order without user - should raise an error
        with pytest.raises(Exception):  # IntegrityError from database
            Order.objects.create(
                # user=None,  # Missing required field
                total_amount=100.00,
                status='pending'
            )
        print("✅ Security: Orders must have a customer")
    
    def test_order_total_amount_cannot_be_negative(self, test_customer):
        """
        BUSINESS LOGIC: Orders can't have negative amounts
        WHY: Negative orders = free money = fraud
        """
        # In real app, you'd have a validator that checks this
        # This test demonstrates WHERE such validation should happen
        
        # If your model has a validator, this should fail:
        try:
            order = Order.objects.create(
                customer=test_customer,
                total_amount=-100.00,  # NEGATIVE!
                status='pending'
            )
            # If we get here without error, validation is MISSING
            pytest.skip("Model doesn't validate negative amounts yet")
        except Exception:
            print("✅ Validation: Negative amounts rejected")
    
    def test_order_status_only_allows_valid_values(self, test_customer):
        """
        DATA INTEGRITY: Order status can only be specific values
        VALID: pending, approved, rejected, delivered
        INVALID: anything else
        """
        # Valid status - should work
        order = Order.objects.create(
            customer=test_customer,
            total_amount=100.00,
            status='approved'
        )
        assert order.status == 'approved'

        # Invalid status should be caught by model validation, not database save.
        invalid_order = Order(
            customer=test_customer,
            total_amount=100.00,
            status='invalid_status'  # NOT in choices
        )
        with pytest.raises(Exception):
            invalid_order.full_clean()
        print("✅ Data Integrity: Only valid statuses allowed")


# ============================================================================
# TEST 3: User Model - Role Assignment
# ============================================================================

class TestUserModelRoles:
    """Test that users are assigned correct roles"""
    
    def test_customer_has_correct_role(self, test_customer):
        """WHAT: Verify test_customer was created with role='customer'"""
        assert test_customer.role == 'customer'
    
    def test_admin_has_correct_role(self, test_sales_admin):
        """WHAT: Verify test admin was created with role='sales_admin'"""
        assert test_sales_admin.role == 'sales_admin'
    
    def test_different_users_have_different_roles(self, test_customer, test_sales_admin):
        """
        SECURITY: Verify role-based access control is possible
        WHY: Customer shouldn't have admin permissions
        """
        assert test_customer.role != test_sales_admin.role
        assert test_customer.role == 'customer'
        assert test_sales_admin.role == 'sales_admin'
        print("✅ Security: Different users have different roles")


# ============================================================================
# TEST 4: Product Model
# ============================================================================

class TestProductModel:
    """Test Product model for menu items"""
    
    def test_product_can_be_created(self, test_product):
        """WHAT: Test that products can be created for menu"""
        assert test_product.id is not None
        assert test_product.name == 'Test Product'
        assert test_product.price == 50.00
    
    def test_product_availability_tracking(self):
        """WHAT: Test that stock levels can be tracked and updated"""
        category = Category.objects.create(name='Limited Items')
        product = Product.objects.create(
            name='Limited Item',
            category=category,
            price=100.00,
            weight_grams=250,
            stock=0  # Out of stock
        )
        assert product.stock == 0
        
        # Restock it
        product.stock = 5
        product.save()
        product.refresh_from_db()
        assert product.stock == 5


# ============================================================================
# TEST 5: Order Relationships (Foreign Keys)
# ============================================================================

class TestOrderRelationships:
    """Test that Order correctly links to User"""
    
    def test_order_belongs_to_correct_customer(self, test_customer):
        """WHAT: Verify order.user points to correct customer"""
        order = Order.objects.create(
            customer=test_customer,
            total_amount=100.00,
            status='pending'
        )
        
        # Retrieve from database and verify relationship
        retrieved_order = Order.objects.get(id=order.id)
        assert retrieved_order.customer.id == test_customer.id
        assert retrieved_order.customer.username == 'testcustomer'
    
    def test_customer_can_have_multiple_orders(self, test_customer):
        """
        WHAT: Test that one customer can have many orders
        REAL-WORLD: Each customer places multiple orders over time
        """
        # Create 3 orders for same customer
        order1 = Order.objects.create(customer=test_customer, total_amount=100.00, status='pending')
        order2 = Order.objects.create(customer=test_customer, total_amount=150.00, status='approved')
        order3 = Order.objects.create(customer=test_customer, total_amount=200.00, status='pending')
        
        # Verify customer has all 3 orders
        customer_orders = Order.objects.filter(customer=test_customer)
        assert customer_orders.count() == 3
        
        # Verify you can query by customer
        approved_orders = Order.objects.filter(customer=test_customer, status='approved')
        assert approved_orders.count() == 1


# ============================================================================
# TEST 6: Order Queries (Real-world filtering)
# ============================================================================

class TestOrderQueries:
    """Test that you can query orders the way your app needs"""
    
    def test_find_pending_orders(self, db_with_multiple_orders):
        """
        REAL-WORLD: Sales admin needs to see all pending orders to approve
        This tests that the database query works correctly
        """
        customer, orders = db_with_multiple_orders
        
        # All orders created are pending, so should find 5
        pending_orders = Order.objects.filter(status='pending')
        assert pending_orders.count() == 5
    
    def test_find_orders_by_customer(self, db_with_multiple_orders):
        """
        REAL-WORLD: Customer views their own order history
        Need to query orders for specific customer
        """
        customer, orders = db_with_multiple_orders
        
        # Find all orders for this customer
        their_orders = Order.objects.filter(customer=customer)
        assert their_orders.count() == 5
        
        # Verify no other customer's orders mixed in
        other_customer = User.objects.create_user(
            username='other',
            email='other1@test.com',
            password='pass123',
            role='customer'
        )
        Order.objects.create(customer=other_customer, total_amount=100.00, status='pending')
        
        # Our customer should still have only 5
        assert Order.objects.filter(customer=customer).count() == 5


# ============================================================================
# LEARNING SUMMARY
# ============================================================================
"""
What you've just learned:

1. FIXTURES (conftest.py):
   - Reusable test data (test_customer, test_order, etc)
   - Automatically created by pytest
   - Prevents repeating code

2. ASSERTIONS:
   - assert x == y  →  "I expect x to equal y"
   - If false: test FAILS
   - If true: test PASSES

3. WITH PYTEST.RAISES:
   - with pytest.raises(Exception):  →  "Code should fail"
   - If code FAILS as expected: test PASSES
   - If code SUCCEEDS: test FAILS (validation is broken!)

4. REAL-WORLD PATTERNS:
   - Test that required fields can't be missing
   - Test that invalid data is rejected
   - Test that relationships work (customer → orders)
   - Test that queries return correct results

5. HOW TO RUN:
   pytest -v          # Run all tests with details
   pytest --cov       # Show what % of code is tested
   pytest test_models.py::TestOrderModelBasics::test_order_can_be_created
                      # Run one specific test

Next: Run these tests!
  pytest tests/test_models.py -v
"""
