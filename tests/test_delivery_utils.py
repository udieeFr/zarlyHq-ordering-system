import pytest
from decimal import Decimal
from customers.delivery_utils import calculate_shipping_fee

pytestmark = pytest.mark.django_db


class TestCalculateShippingFee:

    def test_peninsular_500g(self):
        assert calculate_shipping_fee(500, 'Johor') == Decimal('6.00')

    def test_peninsular_1000g_exact(self):
        assert calculate_shipping_fee(1000, 'Selangor') == Decimal('6.00')

    def test_peninsular_1001g(self):
        assert calculate_shipping_fee(1001, 'Kedah') == Decimal('8.00')

    def test_peninsular_2000g_exact(self):
        assert calculate_shipping_fee(2000, 'Penang') == Decimal('8.00')

    def test_peninsular_3000g_exact(self):
        assert calculate_shipping_fee(3000, 'Perak') == Decimal('9.00')

    def test_peninsular_5000g_exact(self):
        assert calculate_shipping_fee(5000, 'Pahang') == Decimal('11.00')

    def test_peninsular_10000g_exact(self):
        assert calculate_shipping_fee(10000, 'Terengganu') == Decimal('16.00')

    def test_peninsular_over_10kg(self):
        # 12kg = 16 + (2 * 1.50) = 19.00
        assert calculate_shipping_fee(12000, 'Kelantan') == Decimal('19.00')

    def test_east_malaysia_sabah_1kg(self):
        assert calculate_shipping_fee(1000, 'Sabah') == Decimal('11.00')

    def test_east_malaysia_sarawak_3kg(self):
        assert calculate_shipping_fee(3000, 'Sarawak') == Decimal('16.00')

    def test_east_malaysia_labuan_over_10kg(self):
        # 11kg = 27 + (1 * 2.50) = 29.50
        assert calculate_shipping_fee(11000, 'Labuan') == Decimal('29.50')

    def test_walkin_empty_state(self):
        assert calculate_shipping_fee(2000, '') == Decimal('0.00')

    def test_walkin_none_state(self):
        assert calculate_shipping_fee(2000, None) == Decimal('0.00')

    def test_zero_weight(self):
        # Products with no weight set — still charge minimum Peninsular
        assert calculate_shipping_fee(0, 'Johor') == Decimal('6.00')

    def test_case_insensitive_state(self):
        assert calculate_shipping_fee(1000, 'sabah') == Decimal('11.00')
        assert calculate_shipping_fee(1000, 'JOHOR') == Decimal('6.00')
