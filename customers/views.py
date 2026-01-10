from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Product
from admins.models import Order, OrderItem
from decimal import Decimal

def get_cart_from_session(request):
    """Get cart from session and calculate items"""
    cart = request.session.get('cart', {})
    cart_items = []
    total_price = Decimal('0.00')
    
    for product_id, quantity in cart.items():
        try:
            product = Product.objects.get(id=product_id)
            subtotal = product.price * quantity
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'subtotal': subtotal
            })
            total_price += subtotal
        except Product.DoesNotExist:
            continue
    
    return cart_items, total_price

def product_list(request):
    """Display all products"""
    products = Product.objects.all()
    cart = request.session.get('cart', {})
    cart_count = sum(cart.values())
    
    return render(request, 'customers/product_list.html', {
        'products': products,
        'cart_count': cart_count
    })

def add_to_cart(request):
    """Add product to cart (session-based)"""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        
        # Get or initialize cart
        cart = request.session.get('cart', {})
        
        # Validate product exists and has stock
        try:
            product = Product.objects.get(id=product_id)
            if product.stock < quantity:
                messages.error(request, f'Only {product.stock} items available in stock!')
                return redirect('product_list')
        except Product.DoesNotExist:
            messages.error(request, 'Product not found!')
            return redirect('product_list')
        
        # Add or update quantity
        if product_id in cart:
            cart[product_id] += quantity
        else:
            cart[product_id] = quantity
        
        # Ensure we don't exceed stock
        if cart[product_id] > product.stock:
            cart[product_id] = product.stock
        
        request.session['cart'] = cart
        request.session.modified = True
        
        messages.success(request, f'{quantity}x {product.name} added to cart!')
    
    return redirect('product_list')

def cart_view(request):
    """Display cart contents"""
    cart_items, total_price = get_cart_from_session(request)
    
    return render(request, 'customers/cart.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

def update_cart(request):
    """Update quantity in cart"""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 0))
        
        cart = request.session.get('cart', {})
        
        if quantity > 0:
            # Validate stock
            try:
                product = Product.objects.get(id=product_id)
                if quantity > product.stock:
                    messages.warning(request, f'Only {product.stock} items available!')
                    quantity = product.stock
            except Product.DoesNotExist:
                pass
            
            cart[product_id] = quantity
        else:
            # Remove if quantity is 0
            if product_id in cart:
                del cart[product_id]
        
        request.session['cart'] = cart
        request.session.modified = True
        messages.success(request, 'Cart updated!')
    
    return redirect('cart')

def remove_from_cart(request):
    """Remove item from cart"""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        cart = request.session.get('cart', {})
        
        if product_id in cart:
            del cart[product_id]
            request.session['cart'] = cart
            request.session.modified = True
            messages.success(request, 'Item removed from cart!')
    
    return redirect('cart')

@login_required
def checkout(request):
    """Display checkout page"""
    cart_items, total_price = get_cart_from_session(request)
    
    if not cart_items:
        messages.warning(request, 'Your cart is empty!')
        return redirect('product_list')
    
    return render(request, 'customers/checkout.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

@login_required
def submit_order(request):
    """Submit order for approval"""
    if request.method == 'POST':
        cart_items, total_price = get_cart_from_session(request)
        
        if not cart_items:
            messages.error(request, 'Your cart is empty!')
            return redirect('product_list')
        
        
        order = Order.objects.create(
            customer=request.user,
            total_amount=total_price, 
            status='pending'
        )
        
        # Create order items
        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                quantity=item['quantity'],
                subtotal=item['subtotal']
            )
            
            # Update stock
            product = item['product']
            product.stock -= item['quantity']
            product.save()
        
        # Handle payment proof if uploaded
        payment_method = request.POST.get('payment_method')
        if payment_method == 'pay_now' and request.FILES.get('payment_proof'):
            # Save the uploaded file to the model field
            order.payment_proof = request.FILES['payment_proof']
            order.save()
        
        # Clear cart
        request.session['cart'] = {}
        request.session.modified = True
        
        messages.success(request, f'Order #{order.id} submitted successfully! Waiting for admin approval.')
        return redirect('order_success', order_id=order.id)
    
    return redirect('checkout')

@login_required
def order_success(request, order_id):
    """Order success page"""
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    
    return render(request, 'customers/order_success.html', {
        'order': order
    })