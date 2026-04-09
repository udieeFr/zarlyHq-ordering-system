from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from .models import Product, Category, Allergy
from admins.models import Order, OrderItem, Complaint
from decimal import Decimal

# Helper to manage cart data safely
def get_cart_from_session(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total_price = Decimal('0.00')
    ids_to_remove = []
    
    for product_id, quantity in cart.items():
        try:
            product = Product.objects.get(id=product_id)
            subtotal = product.price * quantity
            cart_items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
            total_price += subtotal
        except Product.DoesNotExist:
            ids_to_remove.append(product_id)
    
    if ids_to_remove:
        for pid in ids_to_remove:
            del cart[pid]
        request.session['cart'] = cart
        request.session.modified = True
    
    return cart_items, total_price

def product_list(request):
    """Main Catalog: Handles Filtering and Recent User Activity"""
    products = Product.objects.all()
    
    # English Filtering Logic
    cat_id = request.GET.get('category')
    allergy_id = request.GET.get('allergy')

    if cat_id:
        products = products.filter(category_id=cat_id)
    if allergy_id == 'none':
        products = products.filter(allergies__isnull=True)
    elif allergy_id:
        products = products.filter(allergies__id=allergy_id).distinct()

    # Get Cart Count for the UI button
    cart = request.session.get('cart', {})
    cart_count = sum(cart.values())

    user_orders = []
    completed_orders = []
    if request.user.is_authenticated:
        user_orders = Order.objects.filter(customer=request.user).order_by('-created_at')[:5]
        # Only orders with 'approved' status can have complaints (receipt validation)
        completed_orders = Order.objects.filter(customer=request.user, status='approved')

    return render(request, 'customers/product_list.html', {
        'products': products,
        'categories': Category.objects.all(),
        'allergies': Allergy.objects.all(),
        'cart_count': cart_count,
        'user_orders': user_orders,
        'completed_orders': completed_orders,
    })

@login_required
def add_to_cart(request):
    """The missing function. Adds product to session using POST data."""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        
        cart = request.session.get('cart', {})
        cart[product_id] = cart.get(product_id, 0) + quantity
        
        request.session['cart'] = cart
        request.session.modified = True
        messages.success(request, "Product added to cart.")
        
    return redirect('product_list')

@login_required
def cart_view(request):
    """Display the user's cart"""
    cart_items, total_price = get_cart_from_session(request)
    return render(request, 'customers/cart.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

@login_required
def update_cart(request):
    """Increase or decrease quantity in cart"""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        action = request.POST.get('action')
        cart = request.session.get('cart', {})
        
        if product_id in cart:
            if action == 'increase':
                cart[product_id] += 1
            elif action == 'decrease':
                cart[product_id] -= 1
                if cart[product_id] <= 0:
                    del cart[product_id]
        
        request.session['cart'] = cart
        request.session.modified = True
    return redirect('cart')

@login_required
def remove_from_cart(request):
    """Remove item from cart entirely"""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        cart = request.session.get('cart', {})
        if product_id in cart:
            del cart[product_id]
        request.session['cart'] = cart
        request.session.modified = True
    return redirect('cart')

@login_required
def checkout(request):
    """Checkout summary page"""
    cart_items, total_price = get_cart_from_session(request)
    if not cart_items:
        return redirect('product_list')
    return render(request, 'customers/checkout.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

@login_required
def submit_order(request):
    """Submit the order to the database"""
    if request.method == 'POST':
        cart_items, total_price = get_cart_from_session(request)
        if not cart_items:
            return redirect('product_list')
        
        # Matches 'total_amount' from your Order model
        order = Order.objects.create(
            customer=request.user,
            total_amount=total_price,
            status='pending',
            # PULLING FROM THE NEW FORM FIELDS
            full_name=request.POST.get('full_name'),
            phone_number=request.POST.get('phone_number'),
            shipping_address=request.POST.get('shipping_address'),
            order_notes=request.POST.get('order_notes')
        )
        
        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                quantity=item['quantity'],
                subtotal=item['subtotal']
            )
            # Update physical stock
            item['product'].stock -= item['quantity']
            item['product'].save()
        
        # Check payment method and proof
        payment_method = request.POST.get('payment_method')
        if payment_method == 'now' and request.FILES.get('payment_proof'):
            order.payment_proof = request.FILES['payment_proof']
            order.save()
            
        request.session['cart'] = {}
        request.session.modified = True
        return redirect('order_success', order_id=order.id)
    
    return redirect('checkout')
@login_required
def order_success(request, order_id):
    """Success confirmation page"""
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    return render(request, 'customers/order_success.html', {'order': order})

@login_required
def submit_complaint(request):
    """Processes the complaint modal data"""
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        order = get_object_or_404(Order, id=order_id, customer=request.user)
        
        Complaint.objects.create(
            order=order,
            customer=request.user,
            subject=request.POST.get('subject'),
            message=request.POST.get('message'),
            evidence_image=request.FILES.get('evidence_image')
        )
        messages.success(request, "Your complaint has been submitted.")
    return redirect('product_list')

def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect('product_list')