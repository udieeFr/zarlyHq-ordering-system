from decimal import Decimal

EAST_MALAYSIA = {'sabah', 'sarawak', 'labuan'}

# (max_weight_grams, peninsular_fee, east_fee)
RATE_TABLE = [
    (1000,  Decimal('6.00'),  Decimal('11.00')),
    (2000,  Decimal('8.00'),  Decimal('14.00')),
    (3000,  Decimal('9.00'),  Decimal('16.00')),
    (5000,  Decimal('11.00'), Decimal('19.00')),
    (10000, Decimal('16.00'), Decimal('27.00')),
]

PENINSULAR_OVER_BASE = Decimal('16.00')
PENINSULAR_OVER_RATE = Decimal('1.50')
EAST_OVER_BASE = Decimal('27.00')
EAST_OVER_RATE = Decimal('2.50')


def calculate_shipping_fee(total_weight_grams: int, state: str) -> Decimal:
    if not state or not state.strip():
        return Decimal('0.00')

    is_east = state.strip().lower() in EAST_MALAYSIA
    weight = max(total_weight_grams, 1)  # treat 0g as minimum tier

    for max_g, pen_fee, east_fee in RATE_TABLE:
        if weight <= max_g:
            return east_fee if is_east else pen_fee

    # Over 10kg
    kg_over = Decimal(weight - 10000) / Decimal('1000')
    if is_east:
        return EAST_OVER_BASE + (kg_over * EAST_OVER_RATE).quantize(Decimal('0.01'))
    return PENINSULAR_OVER_BASE + (kg_over * PENINSULAR_OVER_RATE).quantize(Decimal('0.01'))
