from decimal import Decimal
from customers.models import Product


def cart_context(request):
    if not hasattr(request, 'user') or not request.user.is_authenticated or getattr(request.user, 'role', None) != 'customer':
        return {}

    cart = request.session.get('cart', {})
    if not cart:
        return {'cart_count': 0, 'cart_total': Decimal('0.00')}

    cart_count = sum(cart.values())
    try:
        product_ids = [int(pid) for pid in cart]
        prices = {
            str(p.id): p.price
            for p in Product.objects.filter(id__in=product_ids).only('id', 'price')
        }
        cart_total = sum(
            prices[pid] * qty
            for pid, qty in cart.items()
            if pid in prices
        )
    except Exception:
        cart_total = Decimal('0.00')

    return {'cart_count': cart_count, 'cart_total': cart_total}
