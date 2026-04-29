from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.http import HttpResponse, JsonResponse  # Required for PDF downloads
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from .models import Product, Category, Allergy
from admins.models import Order, OrderItem, Complaint, Payment
from admins.utils import generate_invoice_pdf  # The PDF generation engine
from .stripe_utils import (
    create_stripe_checkout_session, 
    get_session_url,
    verify_webhook_signature,
    handle_checkout_session_completed,
    handle_payment_intent_failed,
    handle_charge_refunded,
)
from decimal import Decimal
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)

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

    # 2. Pagination
    paginator = Paginator(products.order_by('name'), 12)
    page_number = request.GET.get('page', 1)
    try:
        product_page = paginator.page(page_number)
    except PageNotAnInteger:
        product_page = paginator.page(1)
    except EmptyPage:
        product_page = paginator.page(paginator.num_pages)

    # 3. Sidebar and UI Data
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
        'products': product_page,
        'page_obj': product_page,
        'paginator': paginator,
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
        order.status = 'pending_payment'  # Re-queue for admin approval
        order.save()

        payment, created = Payment.objects.get_or_create(
            order=order,
            payment_method='manual',
            defaults={
                'status': 'pending',
                'amount': order.total_amount,
                'currency': settings.STRIPE_CURRENCY,
                'proof_image': order.payment_proof,
            }
        )
        if not created:
            payment.status = 'pending'
            payment.amount = order.total_amount
            payment.currency = settings.STRIPE_CURRENCY
            payment.proof_image = order.payment_proof
            payment.save()
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
    creates the Order and OrderItems, and handles payment method selection.
    For Stripe, redirects to Stripe Checkout. For manual, stores proof and awaits admin.
    """
    if request.method == 'POST':
        cart_items, total_price = get_cart_from_session(request)
        
        if not cart_items:
            messages.error(request, 'Your cart is empty!')
            return redirect('product_list')
        
        # Capture realistic shipping information
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        try:
            latitude = Decimal(latitude.strip()) if latitude else None
        except Exception:
            latitude = None
        try:
            longitude = Decimal(longitude.strip()) if longitude else None
        except Exception:
            longitude = None

        street_address = request.POST.get('street_address', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        postcode = request.POST.get('postcode', '').strip()
        formatted_address = request.POST.get('formatted_address', '').strip() or ', '.join(
            part for part in [street_address, city, state, postcode] if part
        )

        order = Order.objects.create(
            customer=request.user,
            total_amount=total_price,
            status='pending',
            full_name=request.POST.get('full_name'),
            phone_number=request.POST.get('phone_number'),
            street_address=street_address,
            city=city,
            state=state,
            postcode=postcode,
            latitude=latitude,
            longitude=longitude,
            formatted_address=formatted_address,
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
        
        # Handle payment method selection
        payment_method = request.POST.get('payment_method')
        
        if payment_method == 'stripe':
            # Create Stripe Checkout Session
            session_id, error = create_stripe_checkout_session(order, request)
            if error:
                messages.error(
                    request,
                    f"Could not create Stripe payment session: {error}. Check STRIPE_SECRET_KEY and try again."
                )
                return redirect('checkout')

            order.status = 'pending_payment'
            order.save(update_fields=['status'])
            
            # Get the checkout URL
            checkout_url = get_session_url(session_id)
            if not checkout_url:
                messages.error(request, "Could not retrieve Stripe checkout URL. Please try again.")
                return redirect('checkout')
            
            # Clear cart before redirecting to Stripe
            request.session['cart'] = {}
            request.session.modified = True
            
            messages.success(request, 'Order created! Redirecting to payment...')
            return redirect(checkout_url)
        
        elif payment_method == 'manual' or payment_method == 'later':
            # Manual payment: upload proof now or later
            if request.FILES.get('payment_proof'):
                order.payment_proof = request.FILES['payment_proof']
                order.save()
                # Change to pending so admin can review
                order.status = 'pending_payment'
                order.save(update_fields=['status'])
            
            # Create a manual payment record for audit trail
            Payment.objects.create(
                order=order,
                payment_method='manual',
                status='pending',
                amount=order.total_amount,
                currency=settings.STRIPE_CURRENCY,
            )
            
            # Clear cart
            request.session['cart'] = {}
            request.session.modified = True
            
            messages.success(request, f'Order #{order.id} submitted successfully!')
            return redirect('order_success', order_id=order.id)
        
        else:
            messages.error(request, 'Please select a payment method.')
            return redirect('checkout')

    return redirect('checkout')

@login_required
def order_success(request, order_id):
    """Order detail/success page"""
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    payment = order.payments.order_by('-created_at').first()
    return render(request, 'customers/order_success.html', {
        'order': order,
        'payment': payment,
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


# ============================================================================
# STRIPE PAYMENT CALLBACKS AND WEBHOOK
# ============================================================================

@login_required
def stripe_success(request, order_id):
    """
    Called after successful Stripe Checkout completion (via redirect_url).
    Payment is not confirmed yet; webhook is the real authority.
    This page shows pending status and awaits webhook processing.
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    
    # Get the payment record if it exists
    payment = order.payments.filter(payment_method='stripe').first()
    
    return render(request, 'customers/stripe_success.html', {
        'order': order,
        'payment': payment,
    })


@login_required
def stripe_cancel(request, order_id):
    """
    Called when customer cancels the Stripe Checkout flow.
    Order remains in 'pending' state and can be retried.
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    
    # Mark the pending Stripe payment as cancelled
    payment = order.payments.filter(
        payment_method='stripe',
        status='pending'
    ).first()
    
    if payment:
        payment.status = 'cancelled'
        payment.save()
    
    messages.warning(request, 'Payment was cancelled. You can retry whenever ready.')
    return render(request, 'customers/stripe_cancel.html', {
        'order': order,
        'payment': payment,
    })


@csrf_exempt  # Stripe doesn't use CSRF tokens, they use signature verification
@require_http_methods(['POST'])
def stripe_webhook(request):
    """
    Webhook endpoint for Stripe events.
    Stripe sends payment status updates here.
    
    Important: We verify the signature before processing any event.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    # Verify signature
    event, error = verify_webhook_signature(
        payload,
        sig_header,
        settings.STRIPE_WEBHOOK_SECRET
    )
    
    if error:
        logger.warning(f'Webhook signature verification failed: {error}')
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    # Handle the event
    event_type = event['type']
    event_data = event['data']['object']
    
    try:
        if event_type == 'checkout.session.completed':
            # Payment successful
            success, msg = handle_checkout_session_completed(
                event_data['id'],
                event
            )
            if success:
                logger.info(f'Webhook processed: {msg}')
            else:
                logger.error(f'Webhook error: {msg}')
        
        elif event_type == 'payment_intent.payment_failed':
            # Payment failed
            success, msg = handle_payment_intent_failed(
                event_data['id'],
                event
            )
            if success:
                logger.info(f'Webhook processed: {msg}')
            else:
                logger.error(f'Webhook error: {msg}')
        
        elif event_type == 'charge.refunded':
            # Refund issued
            success, msg = handle_charge_refunded(
                event_data['id'],
                event
            )
            if success:
                logger.info(f'Webhook processed: {msg}')
            else:
                logger.error(f'Webhook error: {msg}')
        
        else:
            # We don't handle this event type yet
            logger.debug(f'Unhandled event type: {event_type}')
    
    except Exception as e:
        logger.error(f'Unexpected error processing webhook: {str(e)}')
    
    # Always return 200 to Stripe so it knows we received the event
    # (even if we couldn't process it; we'll retry on next attempt)
    return JsonResponse({'received': True}, status=200)