from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from customers.auth_utils import customer_required
from django.contrib.auth import logout, login
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse  # Required for PDF downloads
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
from .models import Product, Allergy, Favourite, OrderRating, ProductReview, User
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
import secrets
import logging
import hashlib
from .payment_utils import validate_payment_proof, get_payment_proof_context, get_all_payment_methods

logger = logging.getLogger(__name__)

def customer_signup(request):
    """Customer registration view."""
    if request.user.is_authenticated:
        return redirect('product_list')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        password_confirm = request.POST.get('password_confirm', '').strip()

        errors = {}

        # Validation
        if not username or len(username) < 3:
            errors['username'] = 'Username must be at least 3 characters.'
        if User.objects.filter(username=username).exists():
            errors['username'] = 'Username already taken.'

        if not email or '@' not in email:
            errors['email'] = 'Valid email required.'
        if User.objects.filter(email=email).exists():
            errors['email'] = 'Email already registered.'

        if not password or len(password) < 6:
            errors['password'] = 'Password must be at least 6 characters.'
        if password != password_confirm:
            errors['password_confirm'] = 'Passwords do not match.'

        if errors:
            return render(request, 'registration/signup.html', {'errors': errors, 'username': username, 'email': email})

        # Django built-in password validation (common passwords, complexity, etc.)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(password)
        except DjangoValidationError as e:
            errors['password'] = ' '.join(e.messages)
            return render(request, 'registration/signup.html', {'errors': errors, 'username': username, 'email': email})

        # Create user with customer role
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role='customer'
        )

        # Auto-login, then prompt for email verification (skippable)
        from django.contrib.auth import login as auth_login
        from .otp_utils import generate_and_cache_otp, send_verification_email
        auth_login(request, user)
        otp = generate_and_cache_otp(user)
        send_verification_email(user, otp)
        request.session['verification_context'] = 'signup'
        log_audit(request, 'customer_signup', target=user,
                  description=f"New customer registered: {user.username}", actor=user)
        return redirect('verify_email')

    return render(request, 'registration/signup.html')

def get_cart_from_session(request):
    """
    Retrieves the cart from the session, calculates subtotals and totals,
    and cleans up any 'ghost products' that no longer exist in the database.
    Uses a single batch query instead of one query per cart item.

    Cart keys: "<product_id>" for retail, "<product_id>_b" for bundle.
    """
    cart = request.session.get('cart', {})
    if not cart:
        return [], Decimal('0.00')

    # Extract numeric product IDs from both retail and bundle keys
    raw_ids = set()
    for key in cart.keys():
        raw_ids.add(key.rstrip('_b').split('_b')[0] if key.endswith('_b') else key)

    product_map = {
        str(p.id): p
        for p in Product.objects.filter(id__in=raw_ids)
    }

    cart_items = []
    total_price = Decimal('0.00')
    ids_to_remove = []

    for cart_key, quantity in cart.items():
        is_bundle = cart_key.endswith('_b')
        product_id = cart_key[:-2] if is_bundle else cart_key
        product = product_map.get(str(product_id))
        if product is None:
            ids_to_remove.append(cart_key)
            continue
        unit_price = product.bundle_price if is_bundle and product.bundle_price else product.price
        subtotal = unit_price * quantity
        cart_items.append({
            'product': product,
            'quantity': quantity,
            'is_bundle': is_bundle,
            'unit_price': unit_price,
            'subtotal': subtotal,
            'cart_key': cart_key,
        })
        total_price += subtotal

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
    cat_filter = request.GET.get('category')
    allergy_id = request.GET.get('allergy')

    if cat_filter:
        products = products.filter(category=cat_filter)

    if allergy_id:
        products = products.exclude(allergies__id=allergy_id)

    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(name__icontains=q)

    hide_soldout = request.GET.get('hide_soldout') == '1'
    if hide_soldout:
        products = products.filter(Q(is_unlimited_stock=True) | Q(stock__gt=0))

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
    _, cart_total = get_cart_from_session(request)

    user_orders = []
    completed_orders = []
    favourite_ids = set()
    if request.user.is_authenticated:
        user_orders = Order.objects.filter(customer=request.user).order_by('-created_at')[:5]
        completed_orders = Order.objects.filter(customer=request.user, status='approved')
        favourite_ids = set(Favourite.objects.filter(customer=request.user).values_list('product_id', flat=True))

    context = {
        'products': product_page,
        'page_obj': product_page,
        'paginator': paginator,
        'categories': Product.objects.exclude(category='').values_list('category', flat=True).distinct().order_by('category'),
        'allergies': Allergy.objects.all(),
        'cart_count': cart_count,
        'cart_total': cart_total,
        'user_orders': user_orders,
        'completed_orders': completed_orders,
        'hide_soldout': hide_soldout,
        'favourite_ids': favourite_ids,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'customers/partials/product_grid.html', context)

    return render(request, 'customers/product_list.html', context)

@customer_required
def favourites_list(request):
    fav_ids = set(Favourite.objects.filter(customer=request.user).values_list('product_id', flat=True))
    products = Product.objects.filter(id__in=fav_ids, is_available=True).order_by('name')
    cart = request.session.get('cart', {})
    return render(request, 'customers/favourites.html', {
        'products': products,
        'favourite_ids': fav_ids,
        'cart_count': sum(cart.values()),
    })


@customer_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def toggle_favourite(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'Too many requests. Please slow down.'}, status=429)
    product = get_object_or_404(Product, id=request.POST.get('product_id'))
    fav, created = Favourite.objects.get_or_create(customer=request.user, product=product)
    if not created:
        fav.delete()
        is_fav = False
    else:
        is_fav = True
    return JsonResponse({'is_favourite': is_fav})


@customer_required
@ratelimit(key='user', rate='20/h', block=False)
def download_invoice(request, order_id):
    """
    Generates and downloads an unsigned PDF invoice for 'pending_payment' orders.
    This supports the 'request for payment' stage of the transaction.
    """
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please wait before downloading again.')
        return redirect('customer_orders')
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
        logger.error(f"Invoice generation error for order {order_id}: {e}")
        messages.error(request, "Something went wrong generating the invoice. Please try again or contact support.")

    return redirect('product_list')

@customer_required
@ratelimit(key='user', rate='10/h', method='POST', block=False)
def upload_payment_proof(request, order_id):
    """
    Handles payment proof upload from the order detail page with validation.
    Once uploaded, the order status is set to 'pending_payment' for admin verification.

    Validates:
    - File exists
    - File size (max 5MB)
    - File type (images and PDF)
    - File integrity
    - Replay attack: blocks upload if Stripe payment already confirmed
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)

    if request.method == 'POST' and getattr(request, 'limited', False):
        messages.error(request, 'Too many upload attempts. Please wait before trying again.')
        return redirect('order_success', order_id=order.id)

    # Replay attack protection: block manual proof upload if Stripe already confirmed payment
    stripe_confirmed = order.payments.filter(payment_method='stripe', status='succeeded').exists()
    if stripe_confirmed:
        messages.error(request, 'This order has already been paid via card. No manual proof required.')
        return redirect('order_success', order_id=order.id)

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
            # Save proof to the Payment record (single source of truth)
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
                payment.status = 'pending'
                payment.amount = order.total_amount
                payment.currency = settings.STRIPE_CURRENCY
                if payment.proof_image:
                    try:
                        payment.proof_image.delete(save=False)
                    except Exception as del_err:
                        logger.warning(f"Could not delete old proof for Order #{order.id}: {del_err}")
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
            logger.error("Payment proof upload failed for order %s: %s", order.id, e, exc_info=True)
            messages.error(request, "Could not save your payment proof. Please try again or contact support.")
            return redirect('order_success', order_id=order.id)
    
    return redirect('order_success', order_id=order.id)


@customer_required
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


@customer_required
@require_http_methods(['POST'])
@ratelimit(key='user', rate='5/m', method='POST', block=False)
def start_stripe_payment(request, order_id):
    """
    Creates a Stripe Checkout session for an existing order and redirects the
    customer to Stripe.
    """
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please wait before trying again.')
        return redirect('payment_page', order_id=order_id)
    order = get_object_or_404(Order, id=order_id, customer=request.user)

    if order.status not in ['pending', 'pending_payment', 'awaiting_payment']:
        messages.info(request, 'Stripe payment is not available for this order.')
        return redirect('order_success', order_id=order.id)

    if order.payments.filter(payment_method='stripe', status='succeeded').exists():
        messages.info(request, 'This order has already been paid. No action needed.')
        return redirect('order_success', order_id=order.id)

    session_id, error = create_stripe_checkout_session(order, request)
    if error:
        messages.error(request, f'Could not start Stripe payment: {error}')
        return redirect('payment_page', order_id=order.id)

    checkout_url = get_session_url(session_id)
    if not checkout_url:
        messages.error(request, 'Could not open Stripe checkout. Please try again.')
        return redirect('payment_page', order_id=order.id)

    log_audit(request, 'payment_initiated', target=order,
              description=f'Stripe checkout session started for Order #{order.id}',
              metadata={'amount': str(order.total_amount), 'stripe_session_id': session_id})

    return redirect(checkout_url)

@customer_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def add_to_cart(request):
    """
    Adds a product to the cart session using POST data.
    Returns JSON for AJAX requests, redirects otherwise.
    """
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if getattr(request, 'limited', False):
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Too many requests. Please slow down.'}, status=429)
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('product_list')

        product_id = request.POST.get('product_id')
        is_bundle = request.POST.get('is_bundle') == '1'
        try:
            quantity = max(1, min(int(request.POST.get('quantity', 1)), 99))
        except (TypeError, ValueError):
            quantity = 1

        cart = request.session.get('cart', {})
        cart_key = f'{product_id}_b' if is_bundle else product_id

        try:
            product = Product.objects.get(id=product_id)
            if is_bundle and not product.has_bundle:
                if is_ajax:
                    return JsonResponse({'success': False, 'message': 'Bundle not available for this product.'}, status=400)
                messages.error(request, 'Bundle not available for this product.')
                return redirect('product_list')
            cart[cart_key] = cart.get(cart_key, 0) + quantity
            request.session['cart'] = cart
            request.session.modified = True

            label = 'bundle' if is_bundle else 'item'
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f'{product.name} ({label}) added to cart!',
                    'cart_count': sum(cart.values()),
                })
            messages.success(request, f'{product.name} added to cart.')

        except Product.DoesNotExist:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Product not found.'}, status=404)
            messages.error(request, 'Product not found.')

    return redirect('product_list')

@customer_required
def cart_view(request):
    """Display cart contents"""
    cart_items, total_price = get_cart_from_session(request)
    return render(request, 'customers/cart.html', {
        'cart_items': cart_items,
        'total_price': total_price
    })

@customer_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def update_cart(request):
    """Update item quantities or remove them if quantity is zero. Handles clear_cart too."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('cart')
        if request.POST.get('clear_cart'):
            request.session['cart'] = {}
            request.session.modified = True
            return redirect('cart')

        cart_key = request.POST.get('cart_key') or request.POST.get('product_id')
        try:
            quantity = max(0, min(int(request.POST.get('quantity', 0)), 99))
        except (TypeError, ValueError):
            quantity = 0

        cart = request.session.get('cart', {})

        if quantity > 0:
            cart[cart_key] = quantity
        else:
            cart.pop(cart_key, None)

        request.session['cart'] = cart
        request.session.modified = True

    return redirect('cart')

@customer_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def remove_from_cart(request):
    """Remove item from cart"""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('cart')
        cart_key = request.POST.get('cart_key') or request.POST.get('product_id')
        cart = request.session.get('cart', {})

        if cart_key in cart:
            del cart[cart_key]
            request.session['cart'] = cart
            request.session.modified = True
            messages.success(request, 'Item removed from cart!')

    return redirect('cart')

@customer_required
def checkout(request):
    """Display checkout page with auto-fill from last order and profile."""
    if not request.user.email_verified:
        from .otp_utils import generate_and_cache_otp, send_verification_email
        otp = generate_and_cache_otp(request.user)
        send_verification_email(request.user, otp)
        request.session['verification_context'] = 'checkout'
        messages.warning(request, 'Please verify your email address to place orders.')
        return redirect('verify_email')

    cart_items, total_price = get_cart_from_session(request)
    if not cart_items:
        messages.warning(request, 'Your cart is empty!')
        return redirect('product_list')

    from customers.models import CustomerProfile
    from admins.models import Order as AdminOrder
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)

    last_order = AdminOrder.objects.filter(
        customer=request.user,
        street_address__isnull=False,
    ).exclude(street_address='').order_by('-created_at').first()

    checkout_key = secrets.token_hex(16)
    request.session['checkout_key'] = checkout_key

    return render(request, 'customers/checkout.html', {
        'cart_items': cart_items,
        'total_price': total_price,
        'profile': profile,
        'last_order': last_order,
        'checkout_key': checkout_key,
    })

def _create_order_atomic(user, total_price, cart_items, **order_fields):
    """
    Creates the Order and OrderItems inside a single DB transaction.
    Uses SELECT FOR UPDATE to lock product rows so concurrent requests
    cannot both decrement the same stock value (prevents overselling).
    Raises ValueError with a user-friendly message if any item is out of stock.
    """
    from django.db import transaction
    with transaction.atomic():
        order = Order.objects.create(
            customer=user,
            total_amount=total_price,
            status='pending',
            **order_fields,
        )
        product_ids = [item['product'].id for item in cart_items]
        locked_products = {
            p.id: p
            for p in Product.objects.select_for_update().filter(id__in=product_ids)
        }
        for item in cart_items:
            product = locked_products[item['product'].id]
            if not product.is_unlimited_stock and product.stock < item['quantity']:
                raise ValueError(
                    f"Sorry, '{product.name}' only has {product.stock} unit(s) left. "
                    "Please update your cart and try again."
                )
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                is_bundle=item['is_bundle'],
                subtotal=item['subtotal'],
            )
            if not product.is_unlimited_stock:
                product.stock -= item['quantity']
                product.save(update_fields=['stock'])
        return order


@customer_required
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def submit_order(request):
    """
    Processes the checkout form: captures realistic shipping details,
    creates the Order and OrderItems, and handles payment method selection.
    For Stripe, redirects to Stripe Checkout. For manual, stores proof and awaits admin.
    """
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many orders submitted. Please wait a moment before trying again.')
            return redirect('checkout')

        if not request.user.email_verified:
            return redirect('checkout')

        # Idempotency guard: one-time key generated on checkout page load, consumed here.
        # Prevents duplicate orders if a POST succeeds server-side but the redirect is lost.
        key = request.POST.get('checkout_key', '')
        session_key = request.session.pop('checkout_key', None)
        if not key or key != session_key:
            messages.warning(request, 'This order was already submitted or the page expired. Check your orders below.')
            return redirect('customer_orders')

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

        # Bounds-check geographic coordinates (M7)
        if latitude is not None and not (-90 <= latitude <= 90):
            latitude = None
        if longitude is not None and not (-180 <= longitude <= 180):
            longitude = None

        # Server-side length limits on free-text fields (M6)
        street_address = request.POST.get('street_address', '').strip()[:255]
        city = request.POST.get('city', '').strip()[:100]
        state = request.POST.get('state', '').strip()[:100]
        postcode = request.POST.get('postcode', '').strip()[:20]
        formatted_address = (request.POST.get('formatted_address', '').strip() or ', '.join(
            part for part in [street_address, city, state, postcode] if part
        ))[:500]

        try:
            order = _create_order_atomic(
                request.user, total_price, cart_items,
                full_name=request.POST.get('full_name', '').strip()[:150],
                phone_number=request.POST.get('phone_number', '').strip()[:20],
                street_address=street_address,
                city=city,
                state=state,
                postcode=postcode,
                latitude=latitude,
                longitude=longitude,
                formatted_address=formatted_address,
                order_notes=request.POST.get('order_notes', '').strip()[:500],
            )
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('checkout')

        from admins.models import OrderEvent
        OrderEvent.objects.create(order=order, status='pending', actor=request.user)
        log_audit(request, 'order_created', target=order,
                  description=f"Customer placed Order #{order.id}",
                  metadata={'total': str(total_price), 'items': len(cart_items)})
        notify_admins(
            title="New order received",
            message=f"Customer {request.user.username} placed Order #{order.id} for RM {total_price}.",
            link=f"/dashboard/order/{order.id}/detail/",
            notification_type='admin_alert',
        )

        # Persist preferred payment method to profile for next auto-fill
        payment_method = request.POST.get('payment_method')
        try:
            from customers.models import CustomerProfile
            profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
            if profile.preferred_payment_method != payment_method:
                profile.preferred_payment_method = payment_method
                profile.save(update_fields=['preferred_payment_method', 'updated_at'])
        except Exception:
            pass

        # Handle payment method selection
        
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

@customer_required
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
    
    try:
        verify_token = order.digital_signature.verify_token
    except Exception:
        verify_token = None

    context = {
        'order': order,
        'payment': payment,
        'verify_token': verify_token,
        **payment_context,
    }

    return render(request, 'customers/order_success.html', context)

@login_required
def logout_view(request):
    """Log user out"""
    log_audit(request, 'logout', target=request.user,
              description=f"Logout: {request.user.username}", actor=request.user)
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('product_list')

@customer_required
@ratelimit(key='user', rate='5/h', method='POST', block=False)
def submit_complaint(request):
    """Handles the complaint submission form"""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many complaints submitted. Please wait before trying again.')
            return redirect('customer_support')

        order_id = request.POST.get('order_id')
        order = get_object_or_404(Order, id=order_id, customer=request.user)

        # Evidence image validation
        evidence_image = request.FILES.get('evidence_image')
        if evidence_image:
            is_valid, error_msg = validate_payment_proof(evidence_image, max_size_mb=5)
            if not is_valid:
                messages.error(request, f'Evidence upload failed: {error_msg}')
                return redirect('customer_support')

        # Receipt hash verification — check if invoice is intact, log result for admins
        receipt_verified = None
        try:
            sig = DigitalSignature.objects.get(order=order)
            pdf_path = os.path.join(settings.MEDIA_ROOT, str(sig.pdf_path))
            if os.path.exists(pdf_path):
                sha256 = hashlib.sha256()
                with open(pdf_path, 'rb') as f:
                    for block in iter(lambda: f.read(4096), b''):
                        sha256.update(block)
                receipt_verified = sha256.hexdigest() == sig.signature_hash
        except DigitalSignature.DoesNotExist:
            pass  # Order doesn't have a signed receipt yet — that's fine

        complaint = Complaint.objects.create(
            order=order,
            customer=request.user,
            subject=request.POST.get('subject'),
            message=request.POST.get('message'),
            evidence_image=evidence_image,
        )
        log_audit(request, 'complaint_submitted', target=complaint,
                  description=f"Complaint filed on Order #{order.id}",
                  metadata={
                      'subject': complaint.subject[:200],
                      'receipt_verified': receipt_verified,
                  })
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

@customer_required
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


@customer_required
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


@customer_required
def customer_orders(request):
    """Order history page with stats, loyalty tier, and per-order detail."""
    from django.db.models import Sum, Count, Avg
    from customers.models import CustomerProfile

    previous_statuses = ['approved', 'delivered', 'rejected', 'cancelled']

    unpaid_orders = Order.objects.filter(
        customer=request.user,
        status='pending_payment',
    ).prefetch_related('items__product').order_by('-created_at')

    upcoming_orders = Order.objects.filter(
        customer=request.user,
        status__in=['pending', 'prepared', 'ready_for_delivery', 'out_for_delivery'],
    ).prefetch_related('items__product').order_by('-created_at')

    previous_orders = Order.objects.filter(
        customer=request.user,
        status__in=previous_statuses
    ).prefetch_related('items__product').order_by('-created_at')[:50]

    completed_orders = Order.objects.filter(
        customer=request.user, status__in=['approved', 'delivered']
    )

    # --- Stats ---
    agg = completed_orders.aggregate(
        total_spent=Sum('total_amount'),
        total_orders=Count('id'),
        avg_order=Avg('total_amount'),
    )
    total_spent  = agg['total_spent'] or 0
    total_orders = agg['total_orders'] or 0
    avg_order    = round(agg['avg_order'] or 0, 2)

    # Most ordered product
    top_item = (
        OrderItem.objects
        .filter(order__customer=request.user, order__status__in=['approved', 'delivered'])
        .values('product__name')
        .annotate(qty=Sum('quantity'))
        .order_by('-qty')
        .first()
    )

    # Loyalty tier + progress to next tier
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    profile.recalculate()
    TIER_THRESHOLDS = {'bronze': 0, 'silver': 500, 'gold': 2000, 'platinum': 5000}
    TIER_ORDER = ['bronze', 'silver', 'gold', 'platinum']
    tier = profile.loyalty_tier
    tier_index = TIER_ORDER.index(tier)
    if tier_index < len(TIER_ORDER) - 1:
        next_tier = TIER_ORDER[tier_index + 1]
        next_threshold = TIER_THRESHOLDS[next_tier]
        progress_pct = min(100, int(float(total_spent) / next_threshold * 100))
        amount_to_next = max(0, next_threshold - float(total_spent))
    else:
        next_tier = None
        next_threshold = None
        progress_pct = 100
        amount_to_next = 0

    cart = request.session.get('cart', {})

    return render(request, 'customers/customer_orders.html', {
        'unpaid_orders': unpaid_orders,
        'upcoming_orders': upcoming_orders,
        'previous_orders': previous_orders,
        'completed_orders': completed_orders,
        'cart_count': sum(cart.values()),
        # Stats
        'total_spent': total_spent,
        'total_orders': total_orders,
        'avg_order': avg_order,
        'top_item': top_item,
        # Loyalty
        'profile': profile,
        'tier': tier,
        'next_tier': next_tier,
        'progress_pct': progress_pct,
        'amount_to_next': amount_to_next,
    })


@customer_required
def customer_support(request):
    complaints = Complaint.objects.filter(
        customer=request.user
    ).select_related('order').order_by('-created_at')[:100]

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


@customer_required
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


@customer_required
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
    ).exclude(
        payments__payment_method='manual',
        payments__proof_image__isnull=False,
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


@login_required
def serve_private_media(request, filepath):
    """Authenticated file serving for private media via nginx X-Accel-Redirect."""
    allowed_subdirs = {'payment_proofs', 'signed_pdfs', 'complaint_evidence'}
    parts = filepath.split('/', 1)
    if len(parts) != 2 or parts[0] not in allowed_subdirs:
        raise Http404
    subdir = parts[0]

    if request.user.role in ('sales_admin', 'manager') or request.user.is_superuser:
        response = HttpResponse()
        response['X-Accel-Redirect'] = f'/private-media/{filepath}'
        del response['Content-Type']
        return response

    # Customers: verify ownership before serving
    if subdir == 'payment_proofs':
        get_object_or_404(Payment, proof_image=filepath, order__customer=request.user)
    elif subdir == 'signed_pdfs':
        get_object_or_404(DigitalSignature, pdf_path=filepath, order__customer=request.user)
    elif subdir == 'complaint_evidence':
        get_object_or_404(Complaint, evidence_image=filepath, customer=request.user)

    response = HttpResponse()
    response['X-Accel-Redirect'] = f'/private-media/{filepath}'
    del response['Content-Type']
    return response


@ratelimit(key='ip', rate='20/m', block=False)
def verify_receipt(request, token):
    """
    Public receipt verification endpoint — no login required.
    Verifies that the digitally signed PDF for an order is authentic and unmodified.

    Non-repudiation check:
      1. Retrieve the DigitalSignature record via its unique verify_token (UUID).
      2. Recompute SHA-256 of the signed PDF file on disk.
      3. Compare with the stored hash — mismatch means the file was tampered.
      4. Use PyHanko to validate the embedded PKCS#7 signature (intact + signer identity).

    Result is cached for 24 hours — a signed receipt is immutable.
    Token-based lookup prevents sequential order ID enumeration.
    """
    from django.core.cache import cache

    if getattr(request, 'limited', False):
        return render(request, 'customers/verify_receipt.html', {
            'status': 'rate_limited',
        })

    cache_key = f'receipt_verify:{token}'
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return render(request, 'customers/verify_receipt.html', cached_result)

    try:
        sig_record = DigitalSignature.objects.only(
            'order_id', 'signature_hash', 'timestamp', 'pdf_path', 'verify_token'
        ).get(verify_token=token)
    except DigitalSignature.DoesNotExist:
        return render(request, 'customers/verify_receipt.html', {
            'status': 'not_found',
        })

    pdf_path = os.path.join(settings.MEDIA_ROOT, str(sig_record.pdf_path))
    result = {
        'order_id': sig_record.order_id,
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
        logger.error("PyHanko signature validation failed for order %s: %s", sig_record.order_id, e, exc_info=True)
        result['hash_match'] = True  # Hash was fine; signature layer failed
        result['status'] = 'sig_error'

    # Cache successful (non-error) results — receipt content never changes after signing
    if result.get('status') in ('valid', 'tampered', 'no_signature', 'sig_error'):
        cache.set(cache_key, result, 60 * 60 * 24)

    log_audit(request, 'receipt_verified', target=sig_record,
              description=f"Receipt verification check on Order #{sig_record.order_id}",
              metadata={'result_status': result.get('status', 'unknown'),
                        'hash_match': bool(result.get('hash_match', False))})

    return render(request, 'customers/verify_receipt.html', result)


# ============================================================================
# NOTIFICATIONS
# ============================================================================

@customer_required
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


@customer_required
@ratelimit(key='user', rate='60/m', block=False)
def notification_open(request, notification_id):
    """Mark a single notification as read and redirect to its link."""
    from admins.models import Notification
    from django.utils.http import url_has_allowed_host_and_scheme
    notif = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notif.mark_read()
    if notif.link and url_has_allowed_host_and_scheme(notif.link, allowed_hosts={request.get_host()}):
        return redirect(notif.link)
    return redirect('notifications_list')


@customer_required
@ratelimit(key='user', rate='10/m', block=False)
def notifications_mark_all_read(request):
    """Mark all notifications for the current user as read."""
    from admins.models import Notification
    from django.utils import timezone as tz
    Notification.objects.filter(recipient=request.user, is_read=False).update(
        is_read=True, read_at=tz.now()
    )
    return redirect('notifications_list')


@customer_required
@ratelimit(key='user', rate='5/m', method='POST', block=False)
def cancel_order(request, order_id):
    """
    Let a customer cancel their own order while it is still pending.
    Restores stock, logs the cancellation, and notifies admins.
    Only allowed when status == 'pending'.
    """
    from admins.models import Order as AdminOrder
    from admins.notifications import log_audit, notify, notify_admins

    if request.method != 'POST':
        return redirect('customer_orders')

    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please wait before trying again.')
        return redirect('customer_orders')

    order = get_object_or_404(AdminOrder, id=order_id, customer=request.user)

    if order.status != 'pending':
        messages.error(request, f"Order #{order.id} can no longer be cancelled — it is already {order.get_status_display()}.")
        return redirect('order_success', order_id=order.id)

    reason = (request.POST.get('cancel_reason', '').strip() or 'No reason provided')[:500]

    # Restore stock for each item (skip unlimited-stock products — their stock was never decremented)
    for item in order.items.select_related('product').all():
        if not item.product.is_unlimited_stock:
            item.product.stock += item.quantity
            item.product.save(update_fields=['stock'])

    order.status = 'cancelled'
    order.order_notes = (order.order_notes or '') + f'\n[CANCELLED by customer: {reason}]'
    order.save(update_fields=['status', 'order_notes'])

    from admins.models import OrderEvent
    OrderEvent.objects.create(order=order, status='cancelled', actor=request.user, note=reason)

    log_audit(request, 'order_cancelled', target=order,
              description=f'Customer cancelled Order #{order.id}. Reason: {reason}',
              metadata={'reason': reason, 'amount': str(order.total_amount)})

    notify_admins(
        title='Order cancelled by customer',
        message=f'Customer {request.user.username} cancelled Order #{order.id} (RM {order.total_amount}). Reason: {reason}',
        link=f'/dashboard/order/{order.id}/detail/',
        notification_type='admin_alert',
    )

    # Trigger refund if customer already paid via Stripe
    stripe_payment = order.payments.filter(payment_method='stripe', status='succeeded').first()
    if stripe_payment:
        from admins.refund_utils import process_refund
        process_refund(order, source='customer_cancellation', request=request)

    messages.success(request, f"Order #{order.id} has been cancelled. If you paid, a refund will be processed shortly.")
    return redirect('customer_orders')


@customer_required
@ratelimit(key='user', rate='10/h', method='POST', block=False)
def update_profile(request):
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    if getattr(request, 'limited', False):
        return JsonResponse({'success': False, 'error': 'Too many requests. Please wait before updating your profile again.'}, status=429)
    import json
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    user = request.user
    from customers.models import User as UserModel, CustomerProfile

    email = data.get('email', '').strip()
    email_changed = False
    if email and email != user.email:
        if UserModel.objects.filter(email=email).exclude(pk=user.pk).exists():
            return JsonResponse({'success': False, 'error': 'That email is already in use.'})
        email_changed = True

    user.first_name = data.get('first_name', '').strip()
    user.last_name  = data.get('last_name', '').strip()
    if email:
        user.email = email
        if email_changed:
            user.email_verified = False
    user.phone_number = data.get('phone_number', '').strip()
    user.save()

    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    profile.default_address  = data.get('default_address', '').strip()
    profile.marketing_opt_in = data.get('marketing_opt_in') in (True, 'true', '1', 'on')
    profile.save()

    if email_changed:
        from .otp_utils import generate_and_cache_otp, send_signup_verification_email
        otp = generate_and_cache_otp(user)
        send_signup_verification_email(user.username, email, otp)
        request.session['verification_context'] = 'email_change'
        return JsonResponse({
            'success': True,
            'requires_verification': True,
            'verify_url': '/menu/verify-email/',
        })

    return JsonResponse({'success': True})


@customer_required
@ratelimit(key='user', rate='20/m', block=False)
def reorder(request, order_id):
    """Repopulate the cart from a past order, then go straight to checkout."""
    from admins.models import Order as AdminOrder

    if getattr(request, 'limited', False):
        messages.error(request, 'Too many reorder requests. Please wait a moment.')
        return redirect('customer_orders')

    order = get_object_or_404(AdminOrder, id=order_id, customer=request.user)

    cart = {}
    out_of_stock = []
    for item in order.items.select_related('product').all():
        product = item.product
        if not product.is_unlimited_stock and product.stock < 1:
            out_of_stock.append(product.name)
            continue
        qty = item.quantity if product.is_unlimited_stock else min(item.quantity, product.stock)
        cart[str(product.id)] = cart.get(str(product.id), 0) + qty

    request.session['cart'] = cart
    request.session.modified = True

    if out_of_stock:
        messages.warning(request, f"Some items were out of stock and skipped: {', '.join(out_of_stock)}.")
    if cart:
        messages.success(request, f"Cart loaded from Order #{order.id}. Review and confirm your details.")
        return redirect('checkout')
    else:
        messages.error(request, "None of the items from that order are currently in stock.")
        return redirect('customer_orders')


@customer_required
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def customer_profile(request):
    from customers.models import CustomerProfile, User as UserModel
    from django.contrib.auth import update_session_auth_hash
    from .otp_utils import mask_email

    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        user = request.user

        if action == 'update_info':
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.phone_number = request.POST.get('phone_number', '').strip()
            email = request.POST.get('email', '').strip()
            email_changed = False
            if email and email != user.email:
                if UserModel.objects.filter(email=email).exclude(pk=user.pk).exists():
                    messages.error(request, 'That email is already in use.')
                else:
                    user.email = email
                    user.email_verified = False
                    email_changed = True
            user.save()
            profile.default_address = request.POST.get('default_address', '').strip()
            profile.default_phone = request.POST.get('default_phone', '').strip()
            profile.marketing_opt_in = 'marketing_opt_in' in request.POST
            profile.save()
            if email_changed:
                from .otp_utils import generate_and_cache_otp, send_signup_verification_email
                otp = generate_and_cache_otp(user)
                send_signup_verification_email(user.username, email, otp)
                request.session['verification_context'] = 'email_change'
                messages.info(request, 'Profile saved. Please verify your new email address.')
                return redirect('verify_email')
            messages.success(request, 'Profile updated.')
            return redirect('customer_profile')

        if action == 'request_pw_change_otp':
            from .otp_utils import generate_and_cache_pw_change_otp, send_pw_change_email
            otp = generate_and_cache_pw_change_otp(user)
            send_pw_change_email(user, otp)
            request.session['pw_change_pending'] = True
            messages.info(request, 'A 6-digit code has been sent to your email.')
            return redirect('customer_profile')

        if action == 'verify_pw_change_otp':
            from .otp_utils import verify_pw_change_otp
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as DjangoValidationError
            code = request.POST.get('otp', '').strip()
            new_pw = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_password', '')
            result = verify_pw_change_otp(user, code)
            if result == 'ok':
                if new_pw != confirm_pw:
                    messages.error(request, 'Passwords do not match.')
                else:
                    try:
                        validate_password(new_pw, user)
                    except DjangoValidationError as e:
                        for msg in e.messages:
                            messages.error(request, msg)
                    else:
                        user.set_password(new_pw)
                        user.save()
                        update_session_auth_hash(request, user)
                        request.session.pop('pw_change_pending', None)
                        log_audit(request, 'password_changed', target=user,
                                  description=f'Password changed via OTP for {user.username}')
                        messages.success(request, 'Password changed successfully.')
                        return redirect('customer_profile')
            elif result == 'invalid':
                messages.error(request, 'Incorrect code. Please try again.')
            else:
                messages.error(request, 'Code expired or max attempts reached. Please request a new code.')
                request.session.pop('pw_change_pending', None)
                return redirect('customer_profile')

    TIER_ORDER = ['bronze', 'silver', 'gold', 'platinum']
    TIER_THRESHOLDS = {'bronze': 0, 'silver': 500, 'gold': 2000, 'platinum': 5000}
    tier = profile.loyalty_tier
    tier_index = TIER_ORDER.index(tier)
    if tier_index < len(TIER_ORDER) - 1:
        next_tier = TIER_ORDER[tier_index + 1]
        next_threshold = TIER_THRESHOLDS[next_tier]
        progress_pct = min(100, int(float(profile.total_spent) / next_threshold * 100)) if next_threshold else 0
        amount_to_next = max(0, next_threshold - float(profile.total_spent))
    else:
        next_tier = None
        progress_pct = 100
        amount_to_next = 0

    return render(request, 'customers/customer_profile.html', {
        'profile': profile,
        'tier': tier,
        'next_tier': next_tier,
        'progress_pct': progress_pct,
        'amount_to_next': amount_to_next,
        'pw_change_pending': request.session.get('pw_change_pending', False),
        'pw_change_email_masked': mask_email(request.user.email),
    })


def home(request):
    from django.db.models import Sum
    top_products = list(
        Product.objects
        .filter(is_available=True)
        .annotate(total_sold=Sum('orderitem__quantity'))
        .order_by('-total_sold')[:4]
    )
    if len(top_products) < 4:
        seen = {p.id for p in top_products}
        fill = list(
            Product.objects.filter(is_available=True).exclude(id__in=seen)[:4 - len(top_products)]
        )
        top_products += fill
    return render(request, 'customers/home.html', {'top_products': top_products})


@customer_required
def customer_complaint_detail(request, complaint_id):
    """Customer view of their own complaint with chat thread."""
    from admins.models import Complaint
    complaint = get_object_or_404(Complaint, id=complaint_id, customer=request.user)
    return render(request, 'customers/complaint_detail.html', {
        'complaint': complaint,
        'order': complaint.order,
        'locked': complaint.status == 'resolved',
    })


@customer_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def customer_complaint_messages(request, complaint_id):
    """Poll for or send support chat messages (customer side)."""
    from admins.models import Complaint, SupportMessage
    from admins.chat_crypto import encrypt_message, decrypt_message
    from django.utils.dateparse import parse_datetime

    complaint = get_object_or_404(Complaint, id=complaint_id, customer=request.user)

    if request.method == 'GET':
        since_raw = request.GET.get('since')
        qs = SupportMessage.objects.filter(complaint=complaint).select_related('sender')
        if since_raw:
            since_dt = parse_datetime(since_raw)
            if since_dt:
                qs = qs.filter(created_at__gt=since_dt)
        msgs = []
        for msg in qs:
            try:
                body = decrypt_message(msg.body)
            except Exception:
                body = '[encrypted]'
            msgs.append({
                'id': msg.id,
                'sender': msg.sender.username if msg.sender else 'deleted',
                'body': body,
                'created_at': msg.created_at.isoformat(),
                'is_mine': msg.sender_id == request.user.id,
            })
        return JsonResponse({'messages': msgs, 'locked': complaint.status == 'resolved'})

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            return JsonResponse({'error': 'Too many messages. Please slow down.'}, status=429)
        if complaint.status == 'resolved':
            return JsonResponse({'error': 'Chat is locked'}, status=403)
        body = request.POST.get('body', '').strip()
        if not body:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
        SupportMessage.objects.create(
            complaint=complaint,
            sender=request.user,
            body=encrypt_message(body),
        )
        log_audit(request, 'support_message_sent', target=complaint,
                  description=f'Customer sent support message on Complaint #{complaint.id}')
        return JsonResponse({'ok': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ── Order Rating ──────────────────────────────────────────────────────────────

@customer_required
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def rate_order(request, order_id):
    """Submit a 1–5 star rating + optional comment for a delivered order."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    from admins.models import Order as AdminOrder
    from .models import OrderRating

    order = get_object_or_404(AdminOrder, id=order_id, customer=request.user)

    if order.status != 'delivered':
        return JsonResponse({'error': 'Only delivered orders can be rated.'}, status=400)

    if hasattr(order, 'rating'):
        return JsonResponse({'error': 'This order has already been rated.'}, status=400)

    try:
        rating_val = int(request.POST.get('rating', 0))
    except (TypeError, ValueError):
        rating_val = 0

    if not (1 <= rating_val <= 5):
        return JsonResponse({'error': 'Rating must be between 1 and 5.'}, status=400)

    comment = request.POST.get('comment', '').strip()[:1000]

    OrderRating.objects.create(
        order=order,
        customer=request.user,
        rating=rating_val,
        comment=comment,
    )
    return JsonResponse({'ok': True, 'rating': rating_val})


# ── Product Review ────────────────────────────────────────────────────────────

@customer_required
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def submit_product_review(request, product_id):
    """Submit a review for a product, verified via a delivered order."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    from admins.models import Order as AdminOrder
    from .models import ProductReview

    product = get_object_or_404(Product, id=product_id)

    delivered_order = AdminOrder.objects.filter(
        customer=request.user,
        status='delivered',
        items__product=product,
    ).first()

    if not delivered_order:
        return JsonResponse({'error': 'You can only review products from delivered orders.'}, status=400)

    if ProductReview.objects.filter(product=product, customer=request.user, order=delivered_order).exists():
        return JsonResponse({'error': 'You have already reviewed this product for that order.'}, status=400)

    try:
        rating_val = int(request.POST.get('rating', 0))
    except (TypeError, ValueError):
        rating_val = 0

    if not (1 <= rating_val <= 5):
        return JsonResponse({'error': 'Rating must be between 1 and 5.'}, status=400)

    comment = request.POST.get('comment', '').strip()[:1000]

    ProductReview.objects.create(
        product=product,
        customer=request.user,
        order=delivered_order,
        rating=rating_val,
        comment=comment,
    )
    return JsonResponse({'ok': True, 'rating': rating_val})


# ─────────────────────────────────────────────────────────────────────────────
# Email Verification
# ─────────────────────────────────────────────────────────────────────────────

def _verification_redirect(context):
    from django.urls import reverse
    mapping = {
        'checkout': reverse('checkout'),
        'email_change': reverse('customer_profile'),
        'profile': reverse('customer_profile'),
    }
    return mapping.get(context, reverse('product_list'))


@login_required
@ratelimit(key='user', rate='20/m', method='POST', block=False)
def verify_email(request):
    from .otp_utils import (
        generate_and_cache_otp, verify_otp, mask_email,
        send_verification_email, send_signup_verification_email,
    )
    user = request.user
    context = request.session.get('verification_context', 'profile')

    if user.email_verified and context != 'email_change':
        return redirect(_verification_redirect(context))

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many attempts. Please wait a moment.')
            return redirect('verify_email')

        action = request.POST.get('action', 'verify')

        if action == 'skip' and context == 'signup':
            request.session.pop('verification_context', None)
            messages.info(request, 'You can verify your email anytime from your profile.')
            return redirect('product_list')

        if action == 'resend':
            otp = generate_and_cache_otp(user)
            send_signup_verification_email(user.username, user.email, otp)
            messages.success(request, f'A new code was sent to {mask_email(user.email)}.')
            return redirect('verify_email')

        # action == 'verify'
        code = request.POST.get('otp', '').strip()
        result = verify_otp(user, code)

        if result == 'ok':
            user.email_verified = True
            user.save(update_fields=['email_verified'])
            request.session.pop('verification_context', None)
            log_audit(request, 'email_verified', target=user,
                      description=f'Email verified: {user.email}', actor=user)
            messages.success(request, 'Email verified successfully!')
            return redirect(_verification_redirect(context))

        elif result == 'invalid':
            messages.error(request, 'Incorrect code. Please try again.')
        else:
            messages.error(request, 'Code expired or max attempts reached. Request a new one.')

    return render(request, 'registration/verify_email_otp.html', {
        'masked_email': mask_email(user.email),
        'context': context,
        'can_skip': context == 'signup',
    })


@customer_required
@ratelimit(key='user', rate='5/h', method='POST', block=False)
def send_verification_otp(request):
    """Sends a verification OTP. Used by the profile page 'Verify Now' button."""
    from .otp_utils import generate_and_cache_otp, send_verification_email, mask_email

    if request.method != 'POST':
        return redirect('customer_profile')

    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please wait before requesting another code.')
        return redirect('customer_profile')

    request.session['verification_context'] = request.POST.get('context', 'profile')
    otp = generate_and_cache_otp(request.user)
    send_verification_email(request.user, otp)
    messages.success(request, f'Verification code sent to {mask_email(request.user.email)}.')
    return redirect('verify_email')


# ─────────────────────────────────────────────────────────────────────────────
# Password Reset (public — no login required)
# ─────────────────────────────────────────────────────────────────────────────

@ratelimit(key='ip', rate='5/h', method='POST', block=False)
def request_password_reset(request):
    if request.user.is_authenticated:
        return redirect('customer_profile')

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many attempts. Please try again later.')
            return render(request, 'registration/password_reset_request.html')

        from .otp_utils import generate_and_cache_otp, send_verification_email
        email = request.POST.get('email', '').strip()
        try:
            user = User.objects.get(email__iexact=email, role='customer')
            otp = generate_and_cache_otp(user)
            send_verification_email(user, otp)
            request.session['reset_user_pk'] = user.pk
        except User.DoesNotExist:
            pass  # silent — no email enumeration

        messages.success(request, 'If that email is registered, a reset code has been sent.')
        return redirect('verify_password_reset')

    return render(request, 'registration/password_reset_request.html')


@ratelimit(key='ip', rate='10/h', method='POST', block=False)
def verify_password_reset(request):
    if request.user.is_authenticated:
        return redirect('customer_profile')

    reset_user_pk = request.session.get('reset_user_pk')
    if not reset_user_pk:
        messages.warning(request, 'No active reset session. Please start again.')
        return redirect('request_password_reset')

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many attempts. Please try again later.')
            return render(request, 'registration/password_reset_verify.html')

        from .otp_utils import verify_otp
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        code = request.POST.get('otp', '').strip()
        new_pw = request.POST.get('new_password', '')
        confirm_pw = request.POST.get('confirm_password', '')

        try:
            user = User.objects.get(pk=reset_user_pk, role='customer')
        except User.DoesNotExist:
            request.session.pop('reset_user_pk', None)
            return redirect('request_password_reset')

        result = verify_otp(user, code)

        if result == 'ok':
            if new_pw != confirm_pw:
                messages.error(request, 'Passwords do not match.')
                return render(request, 'registration/password_reset_verify.html')
            try:
                validate_password(new_pw, user)
            except DjangoValidationError as e:
                for msg in e.messages:
                    messages.error(request, msg)
                return render(request, 'registration/password_reset_verify.html')
            user.set_password(new_pw)
            user.save()
            request.session.pop('reset_user_pk', None)
            log_audit(request, 'password_reset', target=user,
                      description=f'Password reset via email OTP for {user.username}', actor=user)
            messages.success(request, 'Password reset successfully. Please log in.')
            return redirect('login')

        elif result == 'invalid':
            messages.error(request, 'Incorrect code. Please try again.')
        else:
            messages.error(request, 'Code expired or max attempts reached. Please start again.')
            request.session.pop('reset_user_pk', None)
            return redirect('request_password_reset')

    return render(request, 'registration/password_reset_verify.html')


# ─────────────────────────────────────────────────────────────────────────────
# Account Deletion
# ─────────────────────────────────────────────────────────────────────────────

@customer_required
@ratelimit(key='user', rate='5/h', method='POST', block=False)
def delete_account(request):
    from .otp_utils import generate_and_cache_otp, send_verification_email, verify_otp, mask_email

    masked = mask_email(request.user.email)

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please try again later.')
            return redirect('delete_account')

        action = request.POST.get('action', '')

        if action == 'send_otp':
            otp = generate_and_cache_otp(request.user)
            send_verification_email(request.user, otp)
            request.session['delete_account_pending'] = True
            return render(request, 'customers/delete_account.html', {
                'show_otp_form': True,
                'masked_email': masked,
            })

        if action == 'confirm_delete':
            if not request.session.get('delete_account_pending'):
                messages.error(request, 'Please request a confirmation code first.')
                return redirect('delete_account')

            code = request.POST.get('otp', '').strip()
            result = verify_otp(request.user, code)

            if result == 'ok':
                user = request.user
                log_audit(request, 'account_deleted', target=user,
                          description=f'Customer account self-deleted: {user.username}', actor=user)
                logout(request)
                user.delete()
                messages.success(request, 'Your account has been permanently deleted.')
                return redirect('customer_home')

            elif result == 'invalid':
                messages.error(request, 'Incorrect code. Please try again.')
                return render(request, 'customers/delete_account.html', {
                    'show_otp_form': True,
                    'masked_email': masked,
                })
            else:
                request.session.pop('delete_account_pending', None)
                messages.error(request, 'Code expired or max attempts reached. Please start again.')
                return redirect('delete_account')

    return render(request, 'customers/delete_account.html', {
        'show_otp_form': False,
        'masked_email': masked,
    })


def unsubscribe_email(request, token):
    from django.core import signing
    from customers.models import CustomerProfile

    try:
        user_pk = signing.loads(token, salt='email-unsubscribe', max_age=60 * 60 * 24 * 90)
    except signing.SignatureExpired:
        return render(request, 'customers/unsubscribed.html', {'status': 'expired'})
    except signing.BadSignature:
        return render(request, 'customers/unsubscribed.html', {'status': 'invalid'})

    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        return render(request, 'customers/unsubscribed.html', {'status': 'invalid'})

    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    profile.marketing_opt_in = False
    profile.save(update_fields=['marketing_opt_in'])

    from admins.notifications import log_audit
    log_audit(request, 'marketing_opt_out', target=user,
              description=f'{user.email} unsubscribed from marketing emails via email link',
              actor=user)

    return render(request, 'customers/unsubscribed.html', {'status': 'success', 'user': user})

