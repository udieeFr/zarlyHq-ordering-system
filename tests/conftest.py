"""
Pytest Configuration & Shared Fixtures
This file is automatically loaded by pytest before any tests run.
It contains reusable test data (fixtures) and Django setup.
"""

import os
import django
from django.conf import settings

# Tell pytest where Django settings are
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zarlyOs.settings')

# Initialize Django (load models, database, apps, etc)
django.setup()

import pytest
from django.contrib.auth import get_user_model
from admins.models import Order, DigitalSignature
from customers.models import Product, Category

User = get_user_model()


# ============================================================================
# FIXTURES - Reusable test data
# ============================================================================

@pytest.fixture
def test_customer():
    """
    Create a test customer user.
    
    Real-world use: Many tests need a customer to test order creation,
                   payments, etc. Instead of creating this in every test,
                   the fixture creates it once and reuses it.
    
    Returns: User object with role='customer'
    """
    user = User.objects.create_user(
        username='testcustomer',
        email='customer1@test.com',
        password='TestPass123!',
        role='customer'
    )
    return user


@pytest.fixture
def test_sales_admin():
    """
    Create a test sales admin user.
    
    Real-world use: Test order approval, menu management, payment viewing.
                   Only admins can access these functions.
    
    Returns: User object with role='sales_admin'
    """
    user = User.objects.create_user(
        username='testadmin',
        email='admin1@test.com',
        password='TestPass123!',
        role='sales_admin'
    )
    return user


@pytest.fixture
def test_manager():
    """
    Create a test manager user.
    
    Real-world use: Test manager dashboard, viewing all orders, analytics.
                   Managers have highest permissions.
    
    Returns: User object with role='manager' (if your system has it)
    """
    user = User.objects.create_user(
        username='testmanager',
        email='manager1@test.com',
        password='TestPass123!',
        role='manager'  # Adjust if your User model uses different role name
    )
    return user


@pytest.fixture
def test_product():
    """
    Create a test product for orders.
    
    Real-world use: Orders need products. Instead of creating products
                   in every test, this fixture provides a ready-to-use product.
    
    Returns: Product object
    """
    category = Category.objects.create(name='Test Category')
    product = Product.objects.create(
        name='Test Product',
        category=category,
        price=50.00,
        weight_grams=500,
        stock=10
    )
    return product


@pytest.fixture
def test_order(test_customer):
    """
    Create a test order.
    
    Real-world use: Test order approval, payment, status tracking.
    
    Dependency: Needs test_customer (shown in function parameter)
                pytest automatically creates test_customer first
    
    Returns: Order object
    """
    order = Order.objects.create(
        customer=test_customer,
        total_amount=100.00,
        status='pending'
    )
    return order


@pytest.fixture
def test_approved_order(test_customer):
    """
    Create a test order that's already approved.
    
    Real-world use: Test order delivery, signature verification, etc.
                   where order must be in 'approved' state.
    
    Returns: Order object with status='approved'
    """
    order = Order.objects.create(
        customer=test_customer,
        total_amount=150.00,
        status='approved'
    )
    return order


@pytest.fixture
def db_with_multiple_orders(test_customer):
    """
    Create multiple test orders for a customer.
    
    Real-world use: Test filtering, sorting, pagination of orders.
                   Testing "show customer's last 5 orders" needs multiple orders.
    
    Returns: Tuple of (customer, list of 5 orders)
    """
    orders = []
    for i in range(5):
        order = Order.objects.create(
            customer=test_customer,
            total_amount=100.00 + (i * 10),
            status='pending'
        )
        orders.append(order)
    
    return test_customer, orders


# ============================================================================
# DECORATOR FOR DATABASE ACCESS
# ============================================================================

pytestmark = pytest.mark.django_db(
    # Access to database in all tests
    # Without this: tests can't write to database
    # With this: pytest creates test database, cleans up after
)


# ============================================================================
# HELPER FUNCTIONS (Optional - for complex test setups)
# ============================================================================

def create_test_order_with_items(customer, products_list):
    """
    Helper function to create order with multiple items.
    
    Real-world use: When many tests need "order with 3 items", 
                   this avoids repeating the setup code.
    
    Args:
        customer: User object
        products_list: List of Product objects
    
    Returns: Order object with all items added
    """
    order = Order.objects.create(
        customer=customer,
        total_amount=sum(p.price for p in products_list),
        status='pending'
    )
    
    # Add items to order (assumes OrderItem model exists)
    # for product in products_list:
    #     OrderItem.objects.create(order=order, product=product)
    
    return order
