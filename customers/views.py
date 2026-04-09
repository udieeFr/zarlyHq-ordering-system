from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.http import HttpResponse  # Required for PDF downloads
from .models import Product, Category, Allergy
from admins.models import Order, OrderItem, Complaint
from admins.utils import generate_invoice_pdf  # The PDF generation engine
from decimal import Decimal
import os

def get_cart_from_session(request):
    """
    Retrieves the cart from the session, calculates subtotals and totals,
    and cleans up any 'ghost products' that no longer exist in the database.
    """
    cart = request.session.get('cart', {})
    cart_items = []
    total_price = Decimal('0.00')
    ids_to_remove = []
    
    for product_id, quantity in cart.items():
        try:
            # FIX: Prevents Product.DoesNotExist crash if a product is deleted from DB
            product = Product.objects.get(id=product_id)
            subtotal = product.price * quantity
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'subtotal': subtotal
            })
            total_price += subtotal
        except Product.DoesNotExist:
            ids_to_remove.append(product_id)
    
    # Session cleanup for missing products
    if ids_to_remove:
        for pid in ids_to_remove:
            del cart[pid]
        request.session['cart'] = cart
        request.session.modified = True
    
    return cart_items, total_price

def product_list(request):
    """
    Main Catalog View: Handles category/allergy filtering and provides
    data for the sidebar order tracking and cart count.
    """
    products = Product.objects.all()
    
    # 1. Filtering Logic
    cat_id = request.GET.get('category')
    allergy_id = request.GET.get('allergy')

    if cat_id:
        products = products.filter(category_id=cat_id)
        
    if allergy_id == 'none':
        products = products.filter(allergies__isnull=True)
    elif allergy_id:
        products = products.filter(allergies__id=allergy_id).distinct()

    # 2. Sidebar and UI Data
    cart = request.session.get('cart', {})
    cart_count = sum(cart.values())

    user_orders = []
    completed_orders = []
    if request.user.is_authenticated:
        # Display latest status in sidebar
        user_orders = Order.objects.filter(customer=request.user).order_by('-created_at')[:5]
        # Receipt validation: Only orders that were 'approved' can have complaints
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
def download_invoice(request, order_id):
    """
    Generates and downloads an unsigned PDF invoice for 'pending_payment' orders.
    This supports the 'request for payment' stage of the transaction.
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    
    if order.status != 'pending_payment':
        messages.error(request, "Invoice is only available for orders pending payment.")
        return redirect('product_list')

    try:
        # Generate the PDF file using the existing admin engine
        pdf_path = generate_invoice_pdf(order)
        
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="Invoice_Zarly_Order_{order.id}.pdf"'
                return response
        else:
            messages.error(request, "The invoice file could not be found.")
    except Exception as e:
        messages.error(request, f"Error generating invoice: {str(e)}")

    return redirect('product_list')

@login_required
def upload_payment_proof(request, order_id):
    """
    Handles payment proof upload from the order detail page.
    Once uploaded, the order moves to 'pending' for admin verification.
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    
    if request.method == 'POST' and request.FILES.get('payment_proof'):
        order.payment_proof = request.FILES['payment_proof']
        order.status = 'pending'  # Re-queue for admin approval
        order.save()
        messages.success(request, "Payment proof uploaded! The admin will review it shortly.")
        return redirect('order_success', order_id=order.id)
    
    return redirect('order_success', order_id=order.id)

@login_required
def add_to_cart(request):
    """
    Adds a product to the cart session using POST data.
    This version avoids positional argument errors in URLs.
    """
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        
        cart = request.session.get('cart', {})
        
        try:
            product = Product.objects.get(id=product_id)
            # Add or update quantity
            cart[product_id] = cart.get(product_id, 0) + quantity
            
            request.session['cart'] = cart
            request.session.modified = True
            messages.success(request, f'{product.name} added to cart.')
        except Product.DoesNotExist:
            messages.error(request, 'Product not found.')
            
    return redirect('product_list')

@login_required
def cart_view(request):
    """Display cart contents"""
    cart_items, total_price = get_cart_from_session(request)
    return render(request, 'customers/cart.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

@login_required
def update_cart(request):
    """Update item quantities or remove them if quantity is zero"""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 0))
        
        cart = request.session.get('cart', {})
        
        if quantity > 0:
            cart[product_id] = quantity
        else:
            if product_id in cart:
                del cart[product_id]
        
        request.session['cart'] = cart
        request.session.modified = True
        messages.success(request, 'Cart updated!')

    return redirect('cart')

@login_required
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
    """
    Processes the checkout form: captures realistic shipping details,
    creates the Order and OrderItems, and handles immediate payment proof.
    """
    if request.method == 'POST':
        cart_items, total_price = get_cart_from_session(request)
        
        if not cart_items:
            messages.error(request, 'Your cart is empty!')
            return redirect('product_list')
        
        # Capture realistic shipping information
        order = Order.objects.create(
            customer=request.user,
            total_amount=total_price, 
            status='pending',
            full_name=request.POST.get('full_name'),
            phone_number=request.POST.get('phone_number'),
            shipping_address=request.POST.get('shipping_address'),
            order_notes=request.POST.get('order_notes')
        )
        
        # Create order items and update stock
        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                quantity=item['quantity'],
                subtotal=item['subtotal']
            )
            item['product'].stock -= item['quantity']
            item['product'].save()
        
        # Handle payment proof if uploaded during checkout
        payment_method = request.POST.get('payment_method')
        if payment_method == 'now' and request.FILES.get('payment_proof'):
            order.payment_proof = request.FILES['payment_proof']
            order.save()
        
        # Clear cart
        request.session['cart'] = {}
        request.session.modified = True
        
        messages.success(request, f'Order #{order.id} submitted successfully!')
        return redirect('order_success', order_id=order.id)

    return redirect('checkout')

@login_required
def order_success(request, order_id):
    """Order detail/success page"""
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    return render(request, 'customers/order_success.html', {
        'order': order
    })

def logout_view(request):
    """Log user out"""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('product_list')

@login_required
def submit_complaint(request):
    """Handles the complaint submission form"""
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
        messages.success(request, "Your complaint has been submitted successfully.")
    return redirect('product_list')