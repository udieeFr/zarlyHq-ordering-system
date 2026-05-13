from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.http import HttpResponse, JsonResponse  # Required for PDF downloads
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from .models import Product, Category, Allergy
from admins.models import Order, OrderItem, Complaint, Payment, DigitalSignature
from admins.utils import generate_invoice_pdf  # The PDF generation engine
from admins.notifications import log_audit, notify, notify_admins
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
import hashlib
from .payment_utils import validate_payment_proof, get_payment_proof_context, get_all_payment_methods

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
        
    if allergy_id:
        products = products.exclude(allergies__id=allergy_id)

    # 2. Pagination
    paginator = Paginator(products.order_by('name'), 12)
    # Normalize page number: ensure it's a positive integer and handle out-of-range pages
    page_number = request.GET.get('page', 1)
    try:
        page_int = int(page_number)
        if page_int < 1:
            page_int = 1
    except (TypeError, ValueError):
        page_int = 1

    # Use get_page which gracefully handles invalid and out-of-range numbers
    product_page = paginator.get_page(page_int)

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

    context = {
        'products': product_page,
        'page_obj': product_page,
        'paginator': paginator,
        'categories': Category.objects.all(),
        'allergies': Allergy.objects.all(),
        'cart_count': cart_count,
        'user_orders': user_orders,
        'completed_orders': completed_orders,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'customers/partials/product_grid.html', context)

    return render(request, 'customers/product_list.html', context)

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
    Handles payment proof upload from the order detail page with validation.
    Once uploaded, the order status is set to 'pending_payment' for admin verification.
    
    Validates:
    - File exists
    - File size (max 5MB)
    - File type (images and PDF)
    - File integrity
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    
    # Only allow proof upload for pending_payment orders
    if order.status not in ['pending_payment', 'pending']:
        messages.error(request, "Payment proof can only be uploaded for pending orders.")
        return redirect('order_success', order_id=order.id)
    
    if request.method == 'POST':
        proof_file = request.FILES.get('payment_proof')
        
        if not proof_file:
            messages.error(request, "Please select a file to upload.")
            return redirect('order_success', order_id=order.id)
        
        # Validate proof file
        is_valid, error_msg = validate_payment_proof(proof_file, max_size_mb=5)
        if not is_valid:
            messages.error(request, f"Upload failed: {error_msg}")
            return redirect('order_success', order_id=order.id)
        
        try:
            # Save proof to order - order stays in 'pending' status
            # Admin will move it to 'accepted' or 'awaiting_payment' after review
            order.payment_proof = proof_file
            order.save()
            
            # Update or create Payment record
            payment, created = Payment.objects.get_or_create(
                order=order,
                payment_method='manual',
                defaults={
                    'status': 'pending',
                    'amount': order.total_amount,
                    'currency': settings.STRIPE_CURRENCY,
                    'proof_image': proof_file,
                }
            )
            
            if not created:
                # Update existing payment record
                payment.status = 'pending'
                payment.amount = order.total_amount
                payment.currency = settings.STRIPE_CURRENCY
                payment.proof_image = proof_file
                payment.save()
            
            messages.success(
                request,
                "✓ Payment proof uploaded successfully! The admin will review it within 1-2 hours."
            )
            logger.info(f"Payment proof uploaded for Order #{order.id} by {request.user.username}")

            log_audit(request, 'payment_proof_uploaded', target=order,
                      description=f"Customer uploaded payment proof for Order #{order.id}")
            notify_admins(
                title="Payment proof submitted",
                message=f"{request.user.username} uploaded a payment receipt for Order #{order.id}. Please verify.",
                link=f"/dashboard/pending-payment-orders/",
                notification_type='payment',
            )

            return redirect('order_success', order_id=order.id)
            
        except Exception as e:
            messages.error(request, f"Error saving payment proof: {str(e)}")
            logger.error(f"Error uploading payment proof for Order #{order.id}: {str(e)}")
            return redirect('order_success', order_id=order.id)
    
    return redirect('order_success', order_id=order.id)


@login_required
def payment_page(request, order_id):
    """
    Simple payment landing page that lets the customer choose between Stripe
    and QR / bank transfer methods.
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)

    if order.status not in ['pending', 'pending_payment', 'awaiting_payment']:
        messages.info(request, 'This order does not need payment right now.')
        return redirect('order_success', order_id=order.id)

    context = get_payment_proof_context(order)
    context.update({
        'payment': order.payments.order_by('-created_at').first(),
    })
    return render(request, 'customers/payment_page.html', context)


@login_required
@require_http_methods(['POST'])
def start_stripe_payment(request, order_id):
    """
    Creates a Stripe Checkout session for an existing order and redirects the
    customer to Stripe.
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)

    if order.status not in ['pending', 'pending_payment', 'awaiting_payment']:
        messages.info(request, 'Stripe payment is not available for this order.')
        return redirect('order_success', order_id=order.id)

    session_id, error = create_stripe_checkout_session(order, request)
    if error:
        messages.error(request, f'Could not start Stripe payment: {error}')
        return redirect('payment_page', order_id=order.id)

    checkout_url = get_session_url(session_id)
    if not checkout_url:
        messages.error(request, 'Could not open Stripe checkout. Please try again.')
        return redirect('payment_page', order_id=order.id)

    return redirect(checkout_url)

@login_required
def add_to_cart(request):
    """
    Adds a product to the cart session using POST data.
    Returns JSON for AJAX requests, redirects otherwise.
    """
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        cart = request.session.get('cart', {})

        try:
            product = Product.objects.get(id=product_id)
            cart[product_id] = cart.get(product_id, 0) + quantity
            request.session['cart'] = cart
            request.session.modified = True

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f'{product.name} added to cart!',
                    'cart_count': sum(cart.values()),
                })
            messages.success(request, f'{product.name} added to cart.')

        except Product.DoesNotExist:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Product not found.'}, status=404)
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
        
        log_audit(request, 'order_created', target=order,
                  description=f"Customer placed Order #{order.id}",
                  metadata={'total': str(total_price), 'items': len(cart_items)})
        notify_admins(
            title="New order received",
            message=f"Customer {request.user.username} placed Order #{order.id} for RM {total_price}.",
            link=f"/dashboard/order/{order.id}/detail/",
            notification_type='admin_alert',
        )

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

            # Keep order in pending review until admin accepts it.
            # Stripe webhook will mark the payment as succeeded when confirmed.
            # Admin acceptance will route paid orders to approved and unpaid to pending_payment.
            
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
        
        elif payment_method == 'manual':
            # Manual payment: customer can choose to pay now or later
            # Order starts as 'pending' (pending request)
            # Admin will approve and set to 'accepted' or 'awaiting_payment'
            manual_timing = request.POST.get('manual_payment_timing', 'now')
            
            if manual_timing == 'now':
                # Pay Now: show payment methods immediately to upload proof
                messages.success(request, f'Order #{order.id} created! Please complete payment below.')
            else:
                # Pay Later: customer pays after admin approval
                messages.success(
                    request, 
                    f'Order #{order.id} created! Once we approve your order, you can pay and upload proof from your dashboard.'
                )
            
            # Create a manual payment record for audit trail
            Payment.objects.create(
                order=order,
                payment_method='manual',
                status='pending',
                amount=order.total_amount,
                currency=settings.STRIPE_CURRENCY,
            )
            
            # Store payment timing in session so order_success knows which UI to show
            request.session[f'payment_timing_{order.id}'] = manual_timing
            
            # Clear cart
            request.session['cart'] = {}
            request.session.modified = True
            
            return redirect('order_success', order_id=order.id)
        
        else:
            messages.error(request, 'Please select a payment method.')
            return redirect('checkout')

    return redirect('checkout')

@login_required
def order_success(request, order_id):
    """
    Order detail/success page with payment options for pending orders.
    Shows QR codes and bank details for manual payment methods.
    - If "Pay Now" selected: Shows payment info to upload proof
    - If "Pay Later" selected: Shows message to upload later from dashboard
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    payment = order.payments.order_by('-created_at').first()
    
    # Check payment timing choice from session (only relevant for manual payments)
    payment_timing = request.session.get(f'payment_timing_{order.id}', 'now')
    
    # Get payment methods context if order is pending payment with no proof yet
    payment_context = {}
    show_payment_methods = False
    
    if order.status in ['pending_payment', 'pending']:
        if payment and payment.payment_method == 'manual':
            # Show payment methods ONLY if:
            # 1. Customer chose "Pay Now" timing
            # 2. No proof uploaded yet
            if payment_timing == 'now' and not order.payment_proof:
                show_payment_methods = True
                payment_methods = get_all_payment_methods(order.id, order.total_amount)
                payment_context = {
                    'payment_methods': payment_methods,
                    'max_file_size_mb': 5,
                    'show_payment_methods': True,
                    'payment_timing': 'now',
                }
            elif order.payment_proof:
                # Proof already uploaded, just show confirmation
                payment_context = {
                    'show_payment_methods': False,
                    'payment_proof_submitted': True,
                }
            elif payment_timing == 'later':
                # Customer chose "Pay Later" - show dashboard link message
                payment_context = {
                    'show_payment_methods': False,
                    'payment_timing': 'later',
                }
    
    context = {
        'order': order,
        'payment': payment,
        **payment_context,
    }
    
    return render(request, 'customers/order_success.html', context)

def logout_view(request):
    """Log user out"""
    if request.user.is_authenticated:
        log_audit(request, 'logout', target=request.user,
                  description=f"Logout: {request.user.username}", actor=request.user)
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('product_list')

@login_required
def submit_complaint(request):
    """Handles the complaint submission form"""
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        order = get_object_or_404(Order, id=order_id, customer=request.user)

        complaint = Complaint.objects.create(
            order=order,
            customer=request.user,
            subject=request.POST.get('subject'),
            message=request.POST.get('message'),
            evidence_image=request.FILES.get('evidence_image')
        )
        log_audit(request, 'complaint_submitted', target=complaint,
                  description=f"Complaint filed on Order #{order.id}",
                  metadata={'subject': complaint.subject[:200]})
        notify_admins(
            title="New customer complaint",
            message=f"{request.user.username} filed a complaint on Order #{order.id}: {complaint.subject[:120]}",
            link=f"/dashboard/complaints/{complaint.id}/",
            notification_type='complaint',
        )
        messages.success(request, "Your complaint has been submitted successfully.")
    return redirect('customer_support')


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


@csrf_exempt  # Stripe doesn't use CSRF tokens — they sign payloads instead
@require_http_methods(['POST'])
def stripe_webhook(request):
    """
    Webhook endpoint for Stripe events.
    Stripe sends payment status updates here after checkout.session.completed fires.

    DEBUG CHECKLIST if payments stay 'pending':
    1. Check Django terminal for "[WEBHOOK] Secret prefix in use:" line.
       First 12 chars should match the start of your .env STRIPE_WEBHOOK_SECRET.
    2. Check that Stripe-Signature header is arriving (logged below).
    3. If signature fails: your .env secret doesn't match what Stripe CLI is using.
       Copy the whsec_test_... value from `stripe listen` output and update .env,
       then restart Django.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    # === DEBUG LOGGING: verify which secret Django loaded and whether header arrived ===
    secret_preview = settings.STRIPE_WEBHOOK_SECRET[:12] if settings.STRIPE_WEBHOOK_SECRET else 'NOT SET'
    logger.info(f'[WEBHOOK] Received POST. Secret prefix in use: {secret_preview}...')
    logger.info(f'[WEBHOOK] Stripe-Signature header present: {bool(sig_header)}')
    if sig_header:
        logger.info(f'[WEBHOOK] Signature prefix: {sig_header[:30]}...')
    # ==================================================================================

    if not sig_header:
        logger.error('[WEBHOOK] No Stripe-Signature header — request may not be from Stripe')
        return JsonResponse({'error': 'No signature'}, status=400)

    # Verify signature using webhook secret
    event, error = verify_webhook_signature(
        payload,
        sig_header,
        settings.STRIPE_WEBHOOK_SECRET
    )

    if error:
        logger.error(f'[WEBHOOK] Signature verification FAILED: {error}')
        logger.error('[WEBHOOK] Fix: copy whsec_test_... from `stripe listen` into .env STRIPE_WEBHOOK_SECRET and restart Django')
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    event_type = event['type']
    event_data = event['data']['object']
    logger.info(f'[WEBHOOK] Signature OK. Processing event: {event_type}')

    try:
        if event_type == 'checkout.session.completed':
            success, msg = handle_checkout_session_completed(event_data['id'], event)
            if success:
                logger.info(f'[WEBHOOK] checkout.session.completed OK: {msg}')
            else:
                logger.error(f'[WEBHOOK] checkout.session.completed FAILED: {msg}')

        elif event_type == 'payment_intent.payment_failed':
            success, msg = handle_payment_intent_failed(event_data['id'], event)
            if success:
                logger.info(f'[WEBHOOK] payment_intent.payment_failed handled: {msg}')
            else:
                logger.error(f'[WEBHOOK] payment_intent.payment_failed FAILED: {msg}')

        elif event_type == 'charge.refunded':
            success, msg = handle_charge_refunded(event_data['id'], event)
            if success:
                logger.info(f'[WEBHOOK] charge.refunded handled: {msg}')
            else:
                logger.error(f'[WEBHOOK] charge.refunded FAILED: {msg}')

        else:
            logger.debug(f'[WEBHOOK] Unhandled event type (ignored): {event_type}')

    except Exception as e:
        logger.error(f'[WEBHOOK] Unexpected error processing {event_type}: {str(e)}')

    # Always return 200 — Stripe treats anything else as failure and will retry
    return JsonResponse({'received': True}, status=200)


@login_required
def customer_orders(request):
    """
    Dedicated orders page showing upcoming and previous orders.
    Replaces the sidebar order widget from the product list page.
    """
    upcoming_statuses = ['pending', 'pending_payment', 'prepared', 'ready_for_delivery', 'out_for_delivery']
    previous_statuses = ['approved', 'delivered', 'rejected']

    upcoming_orders = Order.objects.filter(
        customer=request.user,
        status__in=upcoming_statuses
    ).prefetch_related('items__product').order_by('-created_at')

    previous_orders = Order.objects.filter(
        customer=request.user,
        status__in=previous_statuses
    ).prefetch_related('items__product').order_by('-created_at')

    completed_orders = Order.objects.filter(
        customer=request.user,
        status__in=['approved', 'delivered']
    )

    cart = request.session.get('cart', {})
    cart_count = sum(cart.values())

    return render(request, 'customers/customer_orders.html', {
        'upcoming_orders': upcoming_orders,
        'previous_orders': previous_orders,
        'completed_orders': completed_orders,
        'cart_count': cart_count,
    })


@login_required
def customer_support(request):
    complaints = Complaint.objects.filter(
        customer=request.user
    ).select_related('order').order_by('-created_at')

    eligible_orders = Order.objects.filter(
        customer=request.user,
        status__in=['approved', 'delivered']
    ).order_by('-created_at')

    cart = request.session.get('cart', {})
    cart_count = sum(cart.values())

    return render(request, 'customers/customer_support.html', {
        'complaints': complaints,
        'eligible_orders': eligible_orders,
        'cart_count': cart_count,
    })


@login_required
def rejected_orders(request):
    """
    Display all rejected orders for the customer with rejection reasons.
    Allows customer to see why orders were rejected.
    """
    from admins.models import RejectedOrder
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    # Get all rejected orders for this customer
    rejected_orders_qs = RejectedOrder.objects.filter(order__customer=request.user).select_related(
        'order', 'rejection_reason', 'rejected_by'
    ).order_by('-rejected_at')
    
    # Pagination
    paginator = Paginator(rejected_orders_qs, 10)
    page_number = request.GET.get('page', 1)
    try:
        page_int = int(page_number)
        if page_int < 1:
            page_int = 1
    except (TypeError, ValueError):
        page_int = 1
    rejected_orders_page = paginator.get_page(page_int)
    
    return render(request, 'customers/rejected_orders.html', {
        'rejected_orders': rejected_orders_page,
        'page_obj': rejected_orders_page,
        'paginator': paginator,
        'total_rejected': rejected_orders_qs.count(),
    })


@login_required
def awaiting_payment_orders(request):
    """
    Display all orders awaiting payment for the customer.
    Allows customers to upload payment proof from their dashboard.
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    # Get all pending payment orders for this customer
    awaiting_orders_qs = Order.objects.filter(
        customer=request.user, 
        status='pending_payment',
        payment_proof__isnull=True  # No proof uploaded yet
    ).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(awaiting_orders_qs, 10)
    page_number = request.GET.get('page', 1)
    try:
        page_int = int(page_number)
        if page_int < 1:
            page_int = 1
    except (TypeError, ValueError):
        page_int = 1
    awaiting_orders_page = paginator.get_page(page_int)
    
    # Get payment methods for each order
    orders_with_methods = []
    for order in awaiting_orders_page:
        payment_methods = get_all_payment_methods(order.id, order.total_amount)
        orders_with_methods.append({
            'order': order,
            'payment_methods': payment_methods,
        })
    
    return render(request, 'customers/awaiting_payment.html', {
        'orders_with_methods': orders_with_methods,
        'awaiting_orders': awaiting_orders_page,
        'page_obj': awaiting_orders_page,
        'paginator': paginator,
        'total_awaiting': awaiting_orders_qs.count(),
    })


def verify_receipt(request, order_id):
    """
    Public receipt verification endpoint — no login required.
    Verifies that the digitally signed PDF for an order is authentic and unmodified.

    Non-repudiation check:
      1. Retrieve the DigitalSignature record (hash + pdf_path stored at signing time).
      2. Recompute SHA-256 of the signed PDF file on disk.
      3. Compare with the stored hash — mismatch means the file was tampered.
      4. Use PyHanko to validate the embedded PKCS#7 signature (intact + signer identity).
    """
    try:
        sig_record = DigitalSignature.objects.select_related('order__customer').get(order_id=order_id)
    except DigitalSignature.DoesNotExist:
        return render(request, 'customers/verify_receipt.html', {
            'order_id': order_id,
            'status': 'not_found',
        })

    pdf_path = os.path.join(settings.MEDIA_ROOT, str(sig_record.pdf_path))
    result = {
        'order_id': order_id,
        'sig_record': sig_record,
        'signed_at': sig_record.timestamp,
        'signer': 'Zarly BigFood Sdn Bhd',
        'stored_hash': sig_record.signature_hash,
    }

    # Step 1: Check file exists
    if not os.path.exists(pdf_path):
        result['status'] = 'file_missing'
        return render(request, 'customers/verify_receipt.html', result)

    # Step 2: Recompute SHA-256 and compare
    sha256 = hashlib.sha256()
    with open(pdf_path, 'rb') as f:
        for block in iter(lambda: f.read(4096), b''):
            sha256.update(block)
    computed_hash = sha256.hexdigest()
    result['computed_hash'] = computed_hash
    hash_match = computed_hash == sig_record.signature_hash

    if not hash_match:
        result['status'] = 'tampered'
        result['hash_match'] = False
        return render(request, 'customers/verify_receipt.html', result)

    # Step 3: Validate PyHanko embedded signature
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko_certvalidator import ValidationContext

        with open(pdf_path, 'rb') as f:
            reader = PdfFileReader(f)
            embedded_sigs = list(reader.embedded_signatures)

        if not embedded_sigs:
            result['status'] = 'no_signature'
            return render(request, 'customers/verify_receipt.html', result)

        # Use a permissive context — self-signed cert won't have a trusted CA chain
        vc = ValidationContext(allow_fetching=False, retroactive_revinfo=True)
        sig_status = validate_pdf_signature(embedded_sigs[0], vc)

        result['hash_match'] = True
        result['sig_intact'] = sig_status.intact
        result['sig_valid'] = sig_status.valid
        result['cert_subject'] = sig_status.signing_cert.subject.human_friendly if sig_status.signing_cert else 'Unknown'
        result['signing_time'] = getattr(sig_status, 'timestamp', None) or sig_record.timestamp
        result['status'] = 'valid' if sig_status.intact else 'invalid'

    except Exception as e:
        # Signature validation failed — treat as tampered
        result['hash_match'] = True  # Hash was fine; signature layer failed
        result['status'] = 'sig_error'
        result['error_detail'] = str(e)

    log_audit(request, 'receipt_verified', target=sig_record,
              description=f"Receipt verification check on Order #{order_id}",
              metadata={'result_status': result.get('status', 'unknown'),
                        'hash_match': bool(result.get('hash_match', False))})

    return render(request, 'customers/verify_receipt.html', result)


# ============================================================================
# NOTIFICATIONS
# ============================================================================

@login_required
def notifications_list(request):
    """Show all of the current user's notifications, newest first."""
    from admins.models import Notification
    qs = Notification.objects.filter(recipient=request.user)
    unread_count = qs.filter(is_read=False).count()
    cart = request.session.get('cart', {})
    return render(request, 'customers/notifications.html', {
        'notifications': qs[:100],
        'unread_count': unread_count,
        'cart_count': sum(cart.values()),
    })


@login_required
def notification_open(request, notification_id):
    """Mark a single notification as read and redirect to its link."""
    from admins.models import Notification
    notif = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notif.mark_read()
    if notif.link:
        return redirect(notif.link)
    return redirect('notifications_list')


@login_required
def notifications_mark_all_read(request):
    """Mark all notifications for the current user as read."""
    from admins.models import Notification
    from django.utils import timezone as tz
    Notification.objects.filter(recipient=request.user, is_read=False).update(
        is_read=True, read_at=tz.now()
    )
    return redirect('notifications_list')