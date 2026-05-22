import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout

logger = logging.getLogger(__name__)
from django_ratelimit.decorators import ratelimit
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum, Count, Max, F
from datetime import timedelta
from .models import Order, OrderItem, DigitalSignature, Complaint, PrepGroup, Payment, AuditLog, Notification, OrderEvent, SupportMessage
from .utils import generate_invoice_pdf, sign_pdf_digitally
from .notifications import log_audit, notify, notify_admins
from .sudo import sudo_required, grant_sudo, SUDO_NEXT_KEY, SUDO_DURATION
from customers.auth_utils import (
    sales_admin_required, 
    manager_required, 
    role_required, 
    get_user_dashboard_url
)
import os
from django.conf import settings
from customers.models import Product, Allergy

def is_sales_admin(user):
    """Checks if the user has administrative permissions."""
    return user.is_authenticated and (user.role in ['sales_admin', 'manager'] or user.is_superuser)


def order_has_confirmed_payment(order):
    """
    Returns True when order has verified payment (manual proof or Stripe webhook confirmed).
    For Stripe: checks that webhook has fired (stripe_payment_intent_id set) and payment succeeded.
    For manual: checks that payment proof was uploaded.
    """
    # Check Stripe payment - must have payment_intent_id (set by webhook) and be succeeded
    has_stripe_payment = order.payments.filter(
        payment_method='stripe',
        status='succeeded',
        stripe_payment_intent_id__isnull=False  # Webhook has processed this payment
    ).exists()
    has_manual_proof = order.payments.filter(
        payment_method='manual',
        proof_image__isnull=False,
    ).exclude(proof_image='').exists()
    return has_manual_proof or has_stripe_payment


def log_order_event(order, status, actor=None, note=''):
    """Record a single order state transition to the OrderEvent history table."""
    OrderEvent.objects.create(order=order, status=status, actor=actor, note=note)


@sales_admin_required
@ratelimit(key='user', rate='5/m', method='POST', block=False)
def sudo_confirm(request):
    """Step-up authentication — re-enter password to access sensitive pages."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many attempts. Please wait before trying again.')
            return render(request, 'admins/sudo_confirm.html', {'sudo_duration_minutes': SUDO_DURATION // 60})
        password = request.POST.get('password', '')
        if request.user.check_password(password):
            grant_sudo(request)
            log_audit(request, 'login_success',
                      description=f"{request.user.username} passed step-up authentication")
            next_url = request.session.pop(SUDO_NEXT_KEY, None) or 'sales_admin_dashboard'
            return redirect(next_url)
        log_audit(request, 'login_failed',
                  description=f"{request.user.username} failed step-up authentication")
        messages.error(request, 'Incorrect password. Please try again.')
    return render(request, 'admins/sudo_confirm.html', {
        'sudo_duration_minutes': SUDO_DURATION // 60,
    })


def finalize_order_approval(order, user, request=None):
    """Signs the invoice and marks the order as approved."""
    raw_pdf = generate_invoice_pdf(order, approver=user)
    signed_path, doc_hash, sig_value = sign_pdf_digitally(raw_pdf, order.id)
    sig_record = DigitalSignature.objects.create(
        order=order,
        signature_hash=doc_hash,
        pdf_path=os.path.join('signed_pdfs', os.path.basename(signed_path)),
        signature_value=sig_value,
    )
    order.status = 'approved'
    order.approved_at = timezone.now()
    order.approved_by = user
    order.save()
    log_order_event(order, 'approved', actor=user)

    # Audit + notification + CRM update
    log_audit(request, 'signature_created', target=sig_record,
              description=f"Signed receipt generated for Order #{order.id}",
              metadata={'order_id': order.id, 'sha256': doc_hash}, actor=user)
    log_audit(request, 'order_approved', target=order,
              description=f"Order #{order.id} approved", actor=user)
    if not order.is_walk_in:
        notify(order.customer,
               title="Your order has been approved ✅",
               message=f"Order #{order.id} is now approved and signed. You can download your signed receipt.",
               link=f"/order-details/{order.id}/",
               notification_type='order_update')
    # Update CRM profile
    try:
        from customers.models import CustomerProfile
        profile, _ = CustomerProfile.objects.get_or_create(user=order.customer)
        profile.recalculate()
    except Exception:
        pass

@ratelimit(key='ip', rate='10/m', method='POST', block=False)
def unified_login(request):
    """
    Unified login view that redirects users to appropriate dashboard based on role.
    Serves as the main login endpoint for the system.
    """
    if request.user.is_authenticated:
        # Already logged in, redirect to dashboard
        return redirect(get_user_dashboard_url(request.user))

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            log_audit(request, 'login_rate_limited',
                      description=f"Rate limit hit on login from IP for username '{request.POST.get('username', '')[:50]}'")
            messages.error(request, "Too many login attempts. Please wait a minute before trying again.")
            return render(request, 'registration/login.html', {'form': AuthenticationForm()})

        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            # Preserve anonymous cart before login() flushes the session
            pre_login_cart = dict(request.session.get('cart', {}))
            login(request, user)
            # Merge: pre-login cart quantities added to any existing session cart
            if pre_login_cart and user.role == 'customer':
                merged = dict(request.session.get('cart', {}))
                for pid, qty in pre_login_cart.items():
                    merged[pid] = merged.get(pid, 0) + qty
                request.session['cart'] = merged
                request.session.modified = True
            log_audit(request, 'login_success', target=user,
                      description=f"Login: {user.username}", actor=user)
            # Always redirect by role after login so staff land on the right area.
            # This avoids stale ?next=... values sending sales admins somewhere else.
            dashboard_url = get_user_dashboard_url(user)
            return redirect(dashboard_url)
        else:
            log_audit(request, 'login_failed',
                      description=f"Failed login attempt for username '{request.POST.get('username', '')[:50]}'",
                      metadata={'username': request.POST.get('username', '')[:50]})
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, 'registration/login.html', {'form': form})

def admin_login(request):
    """Legacy admin login - redirects to unified login."""
    if request.user.is_authenticated:
        return redirect('dashboard_home')
    return redirect('login')

def customer_login(request):
    """Legacy customer login - redirects to unified login."""
    if request.user.is_authenticated:
        return redirect('product_list')
    return redirect('login')

def custom_login(request):
    """Legacy login - redirects to unified login."""
    return redirect('login')

@login_required
def logout_view(request):
    """Handles user logout."""
    user_at_logout = request.user
    log_audit(request, 'logout', target=user_at_logout,
              description=f"Logout: {user_at_logout.username}", actor=user_at_logout)
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('product_list')

# --- DASHBOARD ROUTING ---

@login_required
def dashboard_home(request):
    """
    Universal dashboard home that routes to appropriate dashboard based on role.
    This is the main entry point after login.
    """
    if request.user.role == 'customer':
        return redirect('product_list')
    elif request.user.role == 'manager' or request.user.is_superuser:
        return redirect('manager_analytics_view')
    elif request.user.role == 'sales_admin':
        return redirect('sales_admin_dashboard')
    else:
        messages.error(request, "Your role is not configured. Please contact support.")
        return redirect('product_list')

@manager_required
def manager_analytics_view(request):
    """Manager dashboard — revenue, CRM summary, recent audit trail, complaints."""
    import json
    from customers.models import CustomerProfile
    from django.db.models import Count, FloatField
    from django.db.models.functions import TruncDate

    now = timezone.now()
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # --- Revenue ---
    completed_statuses = ['approved', 'delivered']
    all_completed = Order.objects.filter(status__in=completed_statuses)
    revenue_today    = all_completed.filter(approved_at__date=today).aggregate(t=Sum('total_amount'))['t'] or 0
    revenue_week     = all_completed.filter(approved_at__gte=week_ago).aggregate(t=Sum('total_amount'))['t'] or 0
    revenue_month    = all_completed.filter(approved_at__gte=month_ago).aggregate(t=Sum('total_amount'))['t'] or 0
    revenue_all_time = all_completed.aggregate(t=Sum('total_amount'))['t'] or 0

    # --- Daily revenue for last 30 days (Chart.js) ---
    daily_qs = (
        all_completed
        .filter(approved_at__gte=month_ago)
        .annotate(day=TruncDate('approved_at'))
        .values('day')
        .annotate(total=Sum('total_amount'))
        .order_by('day')
    )
    daily_map = {row['day']: float(row['total'] or 0) for row in daily_qs}
    chart_labels = []
    chart_revenue = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        chart_labels.append(d.strftime('%d %b'))
        chart_revenue.append(daily_map.get(d, 0))

    # --- Order volume ---
    orders_today = Order.objects.filter(created_at__date=today).exclude(status='rejected').count()
    orders_week  = Order.objects.filter(created_at__gte=week_ago).exclude(status='rejected').count()
    # Single aggregate query replaces 8 individual count() calls
    _status_rows = (
        Order.objects
        .values('status')
        .annotate(n=Count('id'))
    )
    status_breakdown = {row['status']: row['n'] for row in _status_rows}
    for _s in ('pending', 'pending_payment', 'approved', 'prepared',
               'ready_for_delivery', 'out_for_delivery', 'delivered', 'rejected'):
        status_breakdown.setdefault(_s, 0)
    total_orders = sum(v for k, v in status_breakdown.items() if k != 'rejected')
    delivered_count = status_breakdown['delivered']
    delivery_rate = round((delivered_count / total_orders * 100) if total_orders > 0 else 0, 1)

    # --- Top 5 products by order count ---
    top_products = (
        OrderItem.objects
        .values('product__name')
        .annotate(qty=Sum('quantity'), revenue=Sum('subtotal'))
        .order_by('-qty')[:5]
    )

    # --- CRM summary ---
    tier_counts = CustomerProfile.objects.values('loyalty_tier').annotate(n=Count('id')).order_by('loyalty_tier')
    tier_map = {t['loyalty_tier']: t['n'] for t in tier_counts}
    top_customers = CustomerProfile.objects.select_related('user').order_by('-total_spent')[:5]
    total_customers = CustomerProfile.objects.count()

    # --- Complaints — single aggregate instead of two counts ---
    _complaint_counts = {
        row['status']: row['n']
        for row in Complaint.objects.values('status').annotate(n=Count('id'))
    }
    pending_complaints  = _complaint_counts.get('pending', 0)
    resolved_complaints = _complaint_counts.get('resolved', 0)
    recent_complaints   = Complaint.objects.select_related('order', 'customer').order_by('-created_at')[:5]

    # --- Audit log preview ---
    recent_audit = AuditLog.objects.select_related('actor').order_by('-timestamp')[:10]

    # --- Refunds ---
    from admins.models import Refund
    pending_refunds_count = Refund.objects.filter(status__in=['manual', 'failed']).count()
    recent_refunds = Refund.objects.select_related('order', 'order__customer').order_by('-created_at')[:5]

    # --- Page views ---
    from admins.models import PageView
    pv_today = PageView.objects.filter(timestamp__date=today).count()
    pv_week  = PageView.objects.filter(timestamp__gte=week_ago).count()
    pv_unique_week = (
        PageView.objects.filter(timestamp__gte=week_ago)
        .exclude(session_key='')
        .values('session_key').distinct().count()
    )
    top_pages = (
        PageView.objects.filter(timestamp__gte=week_ago)
        .values('path')
        .annotate(hits=Count('id'))
        .order_by('-hits')[:5]
    )

    # --- Retention & conversion ---
    customers_ever_ordered = CustomerProfile.objects.filter(total_orders__gte=1).count()
    repeat_customers       = CustomerProfile.objects.filter(total_orders__gt=1).count()
    conversion_rate  = round(customers_ever_ordered / total_customers * 100, 1) if total_customers else 0
    repeat_rate      = round(repeat_customers / customers_ever_ordered * 100, 1) if customers_ever_ordered else 0
    new_customers_week = CustomerProfile.objects.filter(created_at__gte=week_ago).count()
    returning_customers_week = (
        Order.objects.filter(created_at__gte=week_ago, status__in=completed_statuses)
        .exclude(is_walk_in=True)
        .values('customer')
        .distinct()
        .filter(customer__customer_profile__total_orders__gt=1)
        .count()
    )

    _threshold = getattr(settings, 'LOW_STOCK_THRESHOLD', 10)
    low_stock_products = list(
        Product.objects.filter(is_unlimited_stock=False, stock__gt=0, stock__lte=_threshold)
        .values('id', 'name', 'stock', 'category').order_by('stock')
    )
    out_of_stock_products = list(
        Product.objects.filter(is_unlimited_stock=False, stock=0, is_available=True)
        .values('id', 'name', 'category')
    )

    return render(request, 'admins/manager_analytics.html', {
        # Revenue
        'revenue_today': revenue_today,
        'revenue_week': revenue_week,
        'revenue_month': revenue_month,
        'revenue_all_time': revenue_all_time,
        # Chart data (JSON-safe)
        'chart_labels': json.dumps(chart_labels),
        'chart_revenue': json.dumps(chart_revenue),
        # Orders
        'orders_today': orders_today,
        'orders_week': orders_week,
        'status_breakdown': status_breakdown,
        'total_orders': total_orders,
        'delivered_count': delivered_count,
        'delivery_rate': delivery_rate,
        # Top products
        'top_products': list(top_products),
        # CRM
        'tier_map': tier_map,
        'top_customers': top_customers,
        'total_customers': total_customers,
        # Complaints
        'pending_complaints': pending_complaints,
        'resolved_complaints': resolved_complaints,
        'recent_complaints': recent_complaints,
        # Audit
        'recent_audit': recent_audit,
        # Refunds
        'pending_refunds_count': pending_refunds_count,
        'recent_refunds': recent_refunds,
        # Page views
        'pv_today': pv_today,
        'pv_week': pv_week,
        'pv_unique_week': pv_unique_week,
        'top_pages': list(top_pages),
        # Retention
        'conversion_rate': conversion_rate,
        'repeat_rate': repeat_rate,
        'new_customers_week': new_customers_week,
        'returning_customers_week': returning_customers_week,
        # Stock alerts
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
        'low_stock_threshold': _threshold,
    })

# --- INVENTORY MANAGEMENT (STAGED CHANGES) ---

@sales_admin_required
def inventory_list(request):
    """View to list all products and manage stock levels with automatic staging."""
    products = Product.objects.all().order_by('category', 'name')
    staging = request.session.get('stock_staging', {})
    
    inventory_data = []
    for p in products:
        staged_val = staging.get(str(p.id))
        inventory_data.append({
            'product': p,
            'staged_stock': staged_val,
            'has_change': staged_val is not None and int(staged_val) != p.stock
        })
        
    return render(request, 'admins/inventory.html', {
        'inventory_data': inventory_data,
        'has_staging': len(staging) > 0,
        'staging_count': len(staging)
    })

@sales_admin_required
@ratelimit(key='user', rate='120/m', method='POST', block=False)
def stage_stock_update(request, product_id):
    """Automatically saves a proposed stock change to the session via AJAX."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            return JsonResponse({'status': 'error', 'message': 'Too many requests.'}, status=429)
        new_stock = request.POST.get('stock')
        staging = request.session.get('stock_staging', {})
        if new_stock is not None:
            staging[str(product_id)] = new_stock
            request.session['stock_staging'] = staging
            # Return JSON for background requests
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'message': 'Staged'})
            messages.info(request, "Change updated in summary.")
    return redirect('inventory_list')

@sales_admin_required
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def confirm_stock_changes(request):
    """Applies all staged changes from the session to the actual database."""
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please wait before applying changes.')
        return redirect('inventory_list')
    staging = request.session.get('stock_staging', {})
    if request.method == 'POST' and staging:
        updated_count = 0
        for p_id, new_val in staging.items():
            try:
                product = Product.objects.get(id=p_id)
                product.stock = int(new_val)
                product.save()
                updated_count += 1
            except Product.DoesNotExist:
                continue
        
        request.session['stock_staging'] = {}
        messages.success(request, f"Successfully updated {updated_count} items in the inventory.")
    return redirect('inventory_list')

@sales_admin_required
@ratelimit(key='user', rate='10/m', block=False)
def clear_stock_staging(request):
    """Clears the staging area without saving changes."""
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('inventory_list')
    request.session['stock_staging'] = {}
    messages.info(request, "All pending changes have been cleared.")
    return redirect('inventory_list')

@manager_required
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def add_product(request):
    """Add a new product to the menu. Manager-only."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please wait before adding another product.')
            return redirect('inventory_list')
        name = request.POST.get('name', '').strip()
        price = request.POST.get('price')
        stock = request.POST.get('stock', 0)
        weight_grams = request.POST.get('weight_grams') or None
        category = request.POST.get('category', '').strip()
        is_unlimited_stock = request.POST.get('is_unlimited_stock') == 'on'

        if not name or not price or not category:
            messages.error(request, "Name, price, and category are required.")
            return render(request, 'admins/add_product.html', {
                'categories': Product.objects.exclude(category='').values_list('category', flat=True).distinct().order_by('category'),
                'allergies': Allergy.objects.all(),
            })

        img = request.FILES.get('image') or None
        if img and img.size > 5 * 1024 * 1024:
            messages.error(request, 'Product image must be under 5 MB.')
            return redirect('inventory_list')
        product = Product.objects.create(
            name=name,
            price=price,
            stock=stock,
            weight_grams=weight_grams,
            category=category,
            image=img,
            is_unlimited_stock=is_unlimited_stock,
        )
        product.allergies.set(request.POST.getlist('allergies'))

        log_audit(request, 'product_added', target=product,
                  description=f"Product '{name}' added to menu",
                  metadata={'price': str(price), 'stock': int(stock), 'category': category, 'is_unlimited_stock': is_unlimited_stock})
        messages.success(request, f"Product '{name}' added successfully.")
        return redirect('inventory_list')

    return render(request, 'admins/add_product.html', {
        'categories': Product.objects.exclude(category='').values_list('category', flat=True).distinct().order_by('category'),
        'allergies': Allergy.objects.all(),
    })

@manager_required
@ratelimit(key='user', rate='20/m', method='POST', block=False)
def edit_product(request, product_id):
    """Edit an existing product — price, name, stock, category, allergies. Manager-only."""
    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please wait before editing again.')
            return redirect('inventory_list')
        before = {
            'name': product.name,
            'price': str(product.price),
            'stock': product.stock,
            'category': product.category,
            'is_unlimited_stock': product.is_unlimited_stock,
        }
        product.name = request.POST.get('name', product.name).strip()
        product.price = request.POST.get('price', product.price)
        product.stock = request.POST.get('stock', product.stock)
        product.weight_grams = request.POST.get('weight_grams', product.weight_grams)
        product.is_unlimited_stock = request.POST.get('is_unlimited_stock') == 'on'
        category = request.POST.get('category', '').strip()
        if category:
            product.category = category
        if request.FILES.get('image'):
            img = request.FILES['image']
            if img.size > 5 * 1024 * 1024:
                messages.error(request, 'Product image must be under 5 MB.')
                return redirect('inventory_list')
            product.image = img
        elif request.POST.get('clear_image'):
            product.image = None
        product.save(update_fields=[
            'name', 'price', 'stock', 'weight_grams',
            'is_unlimited_stock', 'category', 'image',
        ])
        product.allergies.set(request.POST.getlist('allergies'))
        after = {
            'name': product.name,
            'price': str(product.price),
            'stock': product.stock,
            'category': product.category,
            'is_unlimited_stock': product.is_unlimited_stock,
        }
        changes = {k: {'before': before[k], 'after': after[k]} for k in before if before[k] != after[k]}
        log_audit(request, 'product_edited', target=product,
                  description=f"Product '{product.name}' edited",
                  metadata={'changes': changes})
        messages.success(request, f"'{product.name}' updated.")
        return redirect('inventory_list')

    return render(request, 'admins/edit_product.html', {
        'product': product,
        'categories': Product.objects.exclude(category='').values_list('category', flat=True).distinct().order_by('category'),
        'allergies': Allergy.objects.all(),
        'selected_allergies': list(product.allergies.values_list('id', flat=True)),
    })


@manager_required
@sudo_required
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def delete_product(request, product_id):
    """Delete a product. POST only, manager-only."""
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please wait before deleting again.')
        return redirect('inventory_list')
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        snapshot = {
            'name': product.name,
            'price': str(product.price),
            'stock': product.stock,
            'category': product.category,
        }
        product.delete()
        log_audit(request, 'product_deleted', target=None,
                  description=f"Product '{snapshot['name']}' permanently deleted from menu",
                  metadata=snapshot)
        messages.success(request, f"'{snapshot['name']}' deleted from the menu.")
    return redirect('inventory_list')


@manager_required
@ratelimit(key='user', rate='20/m', method='POST', block=False)
def manage_categories(request):
    """Rename product categories across all products. Manager-only."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('manage_categories')
        action = request.POST.get('action')
        if action == 'rename':
            old_name = request.POST.get('category_name', '').strip()
            new_name = request.POST.get('name', '').strip()
            if old_name and new_name:
                updated = Product.objects.filter(category=old_name).update(category=new_name)
                messages.success(request, f"Renamed '{old_name}' → '{new_name}' on {updated} product(s).")
        return redirect('manage_categories')

    categories = (
        Product.objects
        .exclude(category='')
        .values('category')
        .annotate(product_count=Count('id'))
        .order_by('category')
    )
    return render(request, 'admins/manage_categories.html', {'categories': categories})


def _get_walkin_user():
    """Return (or lazily create) the shared system user for walk-in orders."""
    from customers.models import User as U
    user, _ = U.objects.get_or_create(
        username='__walkin__',
        defaults={
            'email': 'walkin@internal.zarly',
            'role': 'customer',
            'is_active': False,
        },
    )
    return user


@sales_admin_required
@ratelimit(key='user', rate='20/m', method='POST', block=False)
def admin_create_order(request):
    """Manually enter an order — for a registered customer or a walk-in."""
    from customers.models import User as CustomerUser

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please wait before creating another order.')
            return redirect('admin_create_order')
        is_walk_in = request.POST.get('is_walk_in') == '1'

        if is_walk_in:
            customer = _get_walkin_user()
            customer_label = request.POST.get('walkin_name', '').strip() or 'Walk-in Customer'
        else:
            customer_id = request.POST.get('customer_id')
            if not customer_id:
                messages.error(request, 'Please select a customer or choose Walk-in.')
                return redirect('admin_create_order')
            customer = get_object_or_404(CustomerUser, id=customer_id, role='customer')
            customer_label = customer.username

        # Build items list
        product_ids = request.POST.getlist('product_id[]')
        quantities  = request.POST.getlist('quantity[]')
        items, total, errors = [], 0, []
        for pid, qty_str in zip(product_ids, quantities):
            try:
                qty = int(qty_str)
                if qty < 1:
                    continue
                product = Product.objects.get(id=pid)
                if not product.is_unlimited_stock and product.stock < qty:
                    errors.append(f"'{product.name}' only has {product.stock} in stock.")
                    continue
                subtotal = product.price * qty
                items.append({'product': product, 'quantity': qty, 'subtotal': subtotal})
                total += subtotal
            except (Product.DoesNotExist, ValueError):
                continue

        for e in errors:
            messages.error(request, e)

        if not items:
            messages.error(request, 'No valid items — order not created.')
            return redirect('admin_create_order')

        initial_status = request.POST.get('initial_status', 'pending')
        if initial_status not in ('pending', 'approved', 'pending_payment'):
            initial_status = 'pending'

        full_name = request.POST.get('full_name', '').strip()
        if not full_name:
            full_name = (customer_label if is_walk_in else
                         customer.get_full_name() or customer.username)

        order = Order.objects.create(
            customer=customer,
            is_walk_in=is_walk_in,
            full_name=full_name,
            phone_number=request.POST.get('phone_number', '').strip(),
            street_address=request.POST.get('street_address', '').strip(),
            city=request.POST.get('city', '').strip(),
            state=request.POST.get('state', '').strip(),
            postcode=request.POST.get('postcode', '').strip(),
            order_notes=request.POST.get('order_notes', '').strip(),
            total_amount=total,
            status=initial_status,
        )
        if initial_status == 'approved':
            order.approved_at = timezone.now()
            order.approved_by = request.user
            order.save(update_fields=['approved_at', 'approved_by'])

        for item in items:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                quantity=item['quantity'],
                unit_price=item['product'].price,
                is_bundle=False,
                subtotal=item['subtotal'],
            )
            if not item['product'].is_unlimited_stock:
                item['product'].stock -= item['quantity']
                item['product'].save(update_fields=['stock'])

        log_order_event(order, initial_status, actor=request.user,
                        note=f'Manually created by admin — {"walk-in" if is_walk_in else customer_label}')
        log_audit(request, 'order_created', target=order,
                  description=f"Admin {request.user.username} manually created Order #{order.id} for {customer_label}",
                  metadata={'total': str(total), 'items': len(items),
                            'status': initial_status, 'walk_in': is_walk_in})

        if not is_walk_in:
            notify(customer,
                   title='Your order has been approved ✅' if initial_status == 'approved' else 'New order created for you',
                   message=f'Admin created Order #{order.id} (RM {total}) on your behalf.',
                   link=f'/order-details/{order.id}/',
                   notification_type='order_update')

        messages.success(request, f"Order #{order.id} created for {customer_label} (RM {total}).")
        return redirect('admin_order_detail', order_id=order.id)

    customers = CustomerUser.objects.filter(role='customer').exclude(username='__walkin__').order_by('username')
    products = Product.objects.filter(Q(is_unlimited_stock=True) | Q(stock__gt=0)).order_by('category', 'name')
    return render(request, 'admins/admin_create_order.html', {
        'customers': customers,
        'products': products,
    })


# --- DASHBOARD AND ORDERS ---

@sales_admin_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def save_internal_note(request, order_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    if getattr(request, 'limited', False):
        return JsonResponse({'ok': False, 'error': 'Too many requests.'}, status=429)
    order = get_object_or_404(Order, id=order_id)
    order.internal_note = request.POST.get('note', '').strip()
    order.save(update_fields=['internal_note'])
    return JsonResponse({'ok': True})

@sales_admin_required
def admin_order_detail(request, order_id):
    """View complete order info, shipping, and items."""
    from admins.models import RejectionReason
    
    order = get_object_or_404(Order, id=order_id)
    
    # Get the latest Stripe payment record if it exists so admins can see
    # the transaction evidence even before webhook confirmation finishes.
    stripe_payment = order.payments.filter(payment_method='stripe').order_by('-created_at').first()
    
    has_payment = order_has_confirmed_payment(order)
    
    # Get active rejection reasons for dropdown
    rejection_reasons = RejectionReason.objects.filter(is_active=True).order_by('category', 'reason_text')
    
    return render(request, 'admins/order_detail.html', {
        'order': order,
        'stripe_payment': stripe_payment,
        'has_payment': has_payment,
        'rejection_reasons': rejection_reasons,
    })

@sales_admin_required
def sales_admin_dashboard(request):
    """Main sales admin dashboard with order management and metrics."""
    from admins.models import RejectionReason
    
    search_query = request.GET.get('q', '').strip()

    base_pending = Order.objects.filter(status='pending')
    base_pending_payment = Order.objects.filter(status='pending_payment')

    if search_query:
        search_filter = Q(customer__username__icontains=search_query) | Q(full_name__icontains=search_query) | Q(phone_number__icontains=search_query) | Q(id__exact=search_query)
        pending_orders = base_pending.filter(search_filter)
        pending_payment_orders = base_pending_payment.filter(search_filter).prefetch_related('payments')
    else:
        pending_orders = base_pending
        pending_payment_orders = base_pending_payment.prefetch_related('payments')

    # Enrich awaiting-payment rows with payment source/status text for UI badges and button hover.
    pending_payment_orders = list(pending_payment_orders.order_by('-created_at'))
    for order in pending_payment_orders:
        manual_uploaded = bool(order.payment_proof)
        stripe_confirmed = False
        stripe_seen = False
        for payment in order.payments.all():
            if payment.payment_method == 'stripe':
                stripe_seen = True
                if payment.status == 'succeeded' and payment.stripe_payment_intent_id:
                    stripe_confirmed = True

        if stripe_confirmed:
            order.payment_review_badge = 'Stripe Confirmed'
            order.payment_review_badge_class = 'bg-success'
            order.payment_review_status = 'Ready for approval'
            order.payment_review_status_class = 'text-success'
            order.payment_review_tooltip = 'Stripe webhook confirmed payment. Click to review and sign.'
        elif manual_uploaded:
            order.payment_review_badge = 'Manual Proof Uploaded'
            order.payment_review_badge_class = 'bg-primary'
            order.payment_review_status = 'Ready for review'
            order.payment_review_status_class = 'text-success'
            order.payment_review_tooltip = 'Customer uploaded payment proof. Click to review and sign.'
        elif stripe_seen:
            order.payment_review_badge = 'Stripe Pending'
            order.payment_review_badge_class = 'bg-warning text-dark'
            order.payment_review_status = 'Awaiting Stripe confirmation'
            order.payment_review_status_class = 'text-warning'
            order.payment_review_tooltip = 'Stripe payment started, waiting for webhook confirmation.'
        else:
            order.payment_review_badge = 'Waiting'
            order.payment_review_badge_class = 'bg-secondary'
            order.payment_review_status = 'Awaiting customer'
            order.payment_review_status_class = 'text-muted'
            order.payment_review_tooltip = 'No payment submitted yet.'

    approved_orders_qs = Order.objects.filter(status='approved')
    approved_orders = approved_orders_qs.order_by('-approved_at')[:10]

    urgent_pending_ids = list(base_pending.filter(created_at__gte=timezone.now() - timedelta(hours=1)).values_list('id', flat=True))
    high_value_pending_ids = list(base_pending.filter(total_amount__gte=150).values_list('id', flat=True))

    # Week starts Sunday — reset every Sunday 00:00
    _now = timezone.now()
    _days_since_sunday = (_now.weekday() + 1) % 7  # Mon=1 … Sat=6 … Sun=0
    week_start_dt = (_now - timedelta(days=_days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)

    dashboard_metrics = {
        'pending_count': base_pending.count(),
        'pending_payment_count': base_pending_payment.count(),
        'approved_count': Order.objects.filter(approved_at__gte=week_start_dt).count(),
        'rejected_count': Order.objects.filter(status='rejected', rejection_record__rejected_at__gte=week_start_dt).count(),
        'today_revenue': Order.objects.filter(status='approved', approved_at__date=timezone.now().date()).aggregate(total=Sum('total_amount'))['total'] or 0,
        'urgent_pending_count': len(urgent_pending_ids),
        'high_value_pending_count': len(high_value_pending_ids),
        'overdue_payment_count': base_pending_payment.filter(created_at__lte=timezone.now() - timedelta(hours=24)).count(),
    }

    notifications = []
    if dashboard_metrics['urgent_pending_count']:
        notifications.append(f"{dashboard_metrics['urgent_pending_count']} pending order(s) received in the last hour")
    if dashboard_metrics['high_value_pending_count']:
        notifications.append(f"{dashboard_metrics['high_value_pending_count']} high-value order(s) need quick review")
    if dashboard_metrics['overdue_payment_count']:
        notifications.append(f"{dashboard_metrics['overdue_payment_count']} orders still awaiting payment proof after 24h")

    # Get active rejection reasons for bulk reject modal
    rejection_reasons = RejectionReason.objects.filter(is_active=True).order_by('category', 'reason_text')

    _threshold = getattr(settings, 'LOW_STOCK_THRESHOLD', 10)
    low_stock_products = list(
        Product.objects.filter(is_unlimited_stock=False, stock__gt=0, stock__lte=_threshold)
        .values('id', 'name', 'stock', 'category').order_by('stock')
    )
    out_of_stock_products = list(
        Product.objects.filter(is_unlimited_stock=False, stock=0, is_available=True)
        .values('id', 'name', 'category')
    )

    return render(request, 'admins/sales_admin_dashboard.html', {
        'pending_orders': pending_orders.order_by('-created_at'),
        'pending_payment_orders': pending_payment_orders,
        'accepted_orders': approved_orders,
        'search_query': search_query,
        'dashboard_metrics': dashboard_metrics,
        'notifications': notifications,
        'urgent_pending_ids': urgent_pending_ids,
        'high_value_pending_ids': high_value_pending_ids,
        'rejection_reasons': rejection_reasons,
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
        'low_stock_threshold': _threshold,
    })

@sales_admin_required
def approved_orders_list(request):
    """List all approved orders with filtering and search."""
    queryset = Order.objects.filter(status='approved').select_related('customer', 'approved_by').prefetch_related('items__product', 'payments')

    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(id__exact=search_query) |
            Q(customer__username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )

    # Filters
    days_filter = request.GET.get('days', '')
    if days_filter:
        try:
            days = int(days_filter)
            cutoff_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(approved_at__gte=cutoff_date)
        except ValueError:
            pass

    order_count_filter = request.GET.get('count', '')
    if order_count_filter:
        try:
            count = int(order_count_filter)
            queryset = queryset[:count]
        except ValueError:
            pass

    # Ordering
    order_by = request.GET.get('order_by', '-approved_at')
    if order_by in ['approved_at', '-approved_at', 'total_amount', '-total_amount', 'customer__username']:
        queryset = queryset.order_by(order_by)

    approved_orders = list(queryset)
    unpaid_ids = {o.id for o in approved_orders if not order_has_confirmed_payment(o)}

    return render(request, 'admins/approved_orders.html', {
        'approved_orders': approved_orders,
        'unpaid_ids': unpaid_ids,
        'search_query': search_query,
        'days_filter': days_filter,
        'order_count_filter': order_count_filter,
        'order_by': order_by,
    })

@sales_admin_required
def pending_payment_orders_list(request):
    """List all pending_payment orders waiting for payment proof verification."""
    queryset = Order.objects.filter(status='pending_payment').select_related('customer', 'approved_by').prefetch_related('items__product', 'payments')

    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(id__exact=search_query) |
            Q(customer__username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )

    # Filters
    days_filter = request.GET.get('days', '')
    if days_filter:
        try:
            days = int(days_filter)
            cutoff_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(created_at__gte=cutoff_date)
        except ValueError:
            pass

    # Ordering
    order_by = request.GET.get('order_by', '-created_at')
    if order_by in ['created_at', '-created_at', 'total_amount', '-total_amount', 'customer__username']:
        queryset = queryset.order_by(order_by)

    pending_payment_orders = queryset

    return render(request, 'admins/pending_payment_orders.html', {
        'pending_payment_orders': pending_payment_orders,
        'search_query': search_query,
        'days_filter': days_filter,
        'order_by': order_by,
    })

@sales_admin_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def approve_pending_payment(request, order_id):
    """Approve an awaiting-payment order when payment is confirmed."""
    if request.method != 'POST':
        return redirect('pending_payment_orders_list')
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('pending_payment_orders_list')
    order = get_object_or_404(Order, id=order_id, status='pending_payment')

    if not order_has_confirmed_payment(order):
        messages.error(
            request,
            "Payment is not confirmed yet for this order. Wait for Stripe confirmation or manual proof upload."
        )
        return redirect('pending_payment_orders_list')

    # Finalize approval (signs invoice and moves to 'approved')
    finalize_order_approval(order, request.user, request=request)

    log_audit(request, 'payment_verified', target=order,
              description=f"Payment verified for Order #{order.id}")

    messages.success(request, f"Order #{order.id} payment approved and signed.")
    return redirect('pending_payment_orders_list')

@sales_admin_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def reject_pending_payment(request, order_id):
    """Reject payment proof and move order back to pending for re-upload."""
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('pending_payment_orders_list')
    order = get_object_or_404(Order, id=order_id, status='pending_payment')
    
    rejection_reason = request.POST.get('rejection_reason', '').strip()
    if not rejection_reason:
        messages.error(request, "Please provide a rejection reason.")
        return redirect('pending_payment_orders_list')
    
    # Move back to pending
    order.status = 'pending'
    order.save()

    # Clear proof from Payment record and mark rejected
    for p in order.payments.filter(payment_method='manual'):
        if p.proof_image:
            try:
                p.proof_image.delete(save=False)
            except Exception as del_err:
                logger.warning(f"Could not delete proof image for Payment #{p.id}: {del_err}")
        p.proof_image = None
        p.status = 'rejected'
        p.save(update_fields=['proof_image', 'status'])

    log_audit(request, 'payment_rejected', target=order,
              description=f"Manual payment proof rejected for Order #{order.id}",
              metadata={'reason': rejection_reason})
    if not order.is_walk_in:
        notify(order.customer,
               title="Payment proof rejected ⚠️",
               message=f"Your payment proof for Order #{order.id} was rejected. Reason: {rejection_reason}. "
                       f"Please upload a new proof.",
               link=f"/order-details/{order.id}/",
               notification_type='payment')

        # Send notification email to customer
        try:
            from django.core.mail import send_mail
            from django.template.loader import render_to_string
            from django.urls import reverse

            dashboard_url = request.build_absolute_uri(reverse('order_success', kwargs={'order_id': order.id}))

            email_body = render_to_string('emails/payment_proof_rejected.html', {
                'customer_name': order.customer.first_name or order.customer.username,
                'order_id': order.id,
                'reason': rejection_reason,
                'dashboard_url': dashboard_url,
            })

            send_mail(
                subject=f'Payment Proof Rejected - Order #{order.id}',
                message='',
                from_email=None,
                recipient_list=[order.customer.email],
                html_message=email_body,
                fail_silently=True,
            )
        except Exception as e:
            logger.warning("Rejection email failed for order %s: %s", order.id, e)
    
    messages.success(request, f"Order #{order.id} payment proof rejected. Customer notified.")
    return redirect('pending_payment_orders_list')

@sales_admin_required
def print_order_summary(request, order_id):
    """Generate a printable order summary / proforma invoice PDF."""
    ALLOWED_STATUSES = ['approved', 'pending_payment', 'prepared', 'ready_for_delivery', 'out_for_delivery', 'delivered']
    order = get_object_or_404(Order, id=order_id, status__in=ALLOWED_STATUSES)
    try:
        pdf_path = generate_invoice_pdf(order)
        with open(pdf_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="order_{order.id}_invoice.pdf"'
            return response
    except Exception as e:
        logger.error("Invoice generation failed for order %s: %s", order_id, e, exc_info=True)
        messages.error(request, "Could not generate the invoice. Please try again or contact support.")
        return redirect('admin_order_detail', order_id=order_id)

@sales_admin_required
def print_prep_list(request):
    """Generate a printable prep list for selected orders."""
    order_ids = request.GET.getlist('order_ids')
    if not order_ids:
        messages.error(request, "No orders selected for prep list.")
        return redirect('approved_orders_list')

    orders = Order.objects.filter(id__in=order_ids, status='approved').prefetch_related('items__product')
    if not orders:
        messages.error(request, "No valid approved orders found.")
        return redirect('approved_orders_list')

    # Aggregate items across all orders
    item_summary = {}
    total_amount = 0
    order_count = orders.count()

    for order in orders:
        total_amount += order.total_amount
        for item in order.items.all():
            key = item.product.name
            subtotal = item.product.price * item.quantity
            if key in item_summary:
                item_summary[key]['quantity'] += item.quantity
                item_summary[key]['subtotal'] += subtotal
                item_summary[key]['orders'].append(order.id)
            else:
                item_summary[key] = {
                    'quantity': item.quantity,
                    'price': item.product.price,
                    'subtotal': subtotal,
                    'orders': [order.id]
                }

    # Sort by quantity descending
    sorted_items = sorted(item_summary.items(), key=lambda x: x[1]['quantity'], reverse=True)

    return render(request, 'admins/prep_list.html', {
        'orders': orders,
        'item_summary': sorted_items,
        'total_amount': total_amount,
        'order_count': order_count,
        'group_id': f"GRP{timezone.now().strftime('%Y%m%d%H%M%S')}",
    })

@sales_admin_required
def prepared_orders_list(request):
    """List all prep groups with prepared orders."""
    prep_groups = (
        PrepGroup.objects
        .filter(orders__status='prepared')
        .select_related('created_by')
        .annotate(
            _total_orders=Count('orders', distinct=True),
            _total_amount=Sum('orders__total_amount'),
        )
        .distinct()
        .order_by('-created_at')
    )

    search_query = request.GET.get('q', '').strip()
    if search_query:
        prep_groups = prep_groups.filter(
            Q(group_id__icontains=search_query) |
            Q(created_by__username__icontains=search_query)
        )

    days_filter = request.GET.get('days', '')
    if days_filter:
        try:
            days = int(days_filter)
            cutoff_date = timezone.now() - timedelta(days=days)
            prep_groups = prep_groups.filter(created_at__gte=cutoff_date)
        except ValueError:
            pass

    order_count_filter = request.GET.get('count', '')
    if order_count_filter:
        try:
            count = int(order_count_filter)
            prep_groups = prep_groups[:count]
        except ValueError:
            pass

    order_by = request.GET.get('order_by', '-created_at')
    sort_map = {
        'total_orders': '_total_orders', '-total_orders': '-_total_orders',
        'total_amount': '_total_amount', '-total_amount': '-_total_amount',
    }
    db_order = sort_map.get(order_by, order_by)
    if db_order in ['created_at', '-created_at', '_total_orders', '-_total_orders', '_total_amount', '-_total_amount']:
        prep_groups = prep_groups.order_by(db_order)

    from django.db.models import Prefetch as _Prefetch
    groups_list = list(prep_groups)
    groups_with_orders = PrepGroup.objects.filter(
        pk__in=[g.pk for g in groups_list]
    ).prefetch_related(_Prefetch('orders', queryset=Order.objects.prefetch_related('payments')))
    unpaid_group_ids = set()
    for g in groups_with_orders:
        if any(not order_has_confirmed_payment(o) for o in g.orders.all()):
            unpaid_group_ids.add(g.pk)

    return render(request, 'admins/prepared_orders.html', {
        'prep_groups': groups_list,
        'unpaid_group_ids': unpaid_group_ids,
        'search_query': search_query,
        'days_filter': days_filter,
        'order_count_filter': order_count_filter,
        'order_by': order_by,
    })

@sales_admin_required
def prep_group_detail(request, group_id):
    """View details of a specific prep group."""
    prep_group = get_object_or_404(PrepGroup, group_id=group_id)
    orders = prep_group.orders.all().prefetch_related('items__product', 'payments')
    unpaid_order_ids = {o.id for o in orders if not order_has_confirmed_payment(o)}

    return render(request, 'admins/prep_group_detail.html', {
        'prep_group': prep_group,
        'orders': orders,
        'unpaid_order_ids': unpaid_order_ids,
    })

@sales_admin_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def mark_prep_group_ready(request, group_id):
    """Mark an entire prep group as ready for delivery."""
    prep_group = get_object_or_404(PrepGroup, group_id=group_id)
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('prep_group_detail', group_id=prep_group.group_id)
        courier_name = request.POST.get('courier_name', '').strip() or None
        tracking_number = request.POST.get('tracking_number', '').strip() or None
        orders = prep_group.orders.filter(status='prepared')

        if not orders.exists():
            messages.error(request, 'No prepared orders are available in this order preparation group.')
            return redirect('prep_group_detail', group_id=prep_group.group_id)

        order_list = list(orders)

        orders.update(
            status='ready_for_delivery',
            ready_for_delivery_at=timezone.now(),
            ready_for_delivery_by=request.user,
            courier_name=courier_name,
            tracking_number=tracking_number,
            delivery_assigned_at=timezone.now(),
            delivery_assigned_by=request.user
        )

        for o in order_list:
            log_order_event(o, 'ready_for_delivery', actor=request.user,
                            note=f'courier={courier_name or ""} tracking={tracking_number or ""}')
        log_audit(request, 'order_ready_for_delivery', target=prep_group,
                  description=f"Order Preparation {prep_group.group_id} marked ready for delivery",
                  metadata={'courier': courier_name or '', 'tracking': tracking_number or '',
                            'order_ids': [o.id for o in order_list]})
        for o in order_list:
            if not o.is_walk_in:
                notify(o.customer,
                       title="Your order is ready for delivery 📦",
                       message=f"Order #{o.id} has been packed and assigned to "
                               f"{courier_name or 'a courier'}.",
                       link=f"/order-details/{o.id}/",
                       notification_type='delivery')

        messages.success(request, f'Order Preparation {prep_group.group_id} marked as ready for delivery.')
        return redirect('delivery_orders_list')

    return redirect('prep_group_detail', group_id=prep_group.group_id)

@sales_admin_required
@ratelimit(key='user', rate='60/m', block=False)
def mark_order_out_for_delivery(request, order_id):
    """Move a single order from ready_for_delivery to out_for_delivery."""
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('delivery_orders_list')
    order = get_object_or_404(Order, id=order_id, status='ready_for_delivery')
    order.status = 'out_for_delivery'
    order.save()
    log_order_event(order, 'out_for_delivery', actor=request.user)
    log_audit(request, 'order_out_for_delivery', target=order,
              description=f"Order #{order.id} out for delivery")
    if not order.is_walk_in:
        notify(order.customer,
               title="Your order is on the way 🛵",
               message=f"Order #{order.id} has been dispatched. "
                       f"{'Track it with Citylink: ' + order.tracking_number if order.tracking_number else ''}",
               link=f"/order-details/{order.id}/",
               notification_type='delivery')
    messages.success(request, f"Order #{order.id} marked as Out for Delivery.")
    return redirect('delivery_orders_list')

@sales_admin_required
@ratelimit(key='user', rate='60/m', block=False)
def mark_order_delivered(request, order_id):
    """Mark a single order as delivered."""
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('delivery_orders_list')
    order = get_object_or_404(Order, id=order_id, status='out_for_delivery')
    order.status = 'delivered'
    order.delivered_at = timezone.now()
    order.save()
    log_order_event(order, 'delivered', actor=request.user)
    log_audit(request, 'order_delivered', target=order,
              description=f"Order #{order.id} delivered")
    if not order.is_walk_in:
        notify(order.customer,
               title="Order delivered ✅",
               message=f"Order #{order.id} has been delivered. We hope you enjoyed it!",
               link=f"/order-details/{order.id}/",
               notification_type='delivery')
    # Recalculate CRM stats
    try:
        from customers.models import CustomerProfile
        profile, _ = CustomerProfile.objects.get_or_create(user=order.customer)
        profile.recalculate()
    except Exception:
        pass
    messages.success(request, f"Order #{order.id} marked as Delivered.")
    return redirect('delivery_orders_list')

@sales_admin_required
def delivery_orders_list(request):
    """List orders in the delivery workflow."""
    queryset = Order.objects.filter(status__in=['ready_for_delivery', 'out_for_delivery', 'delivered']).select_related('customer', 'ready_for_delivery_by', 'delivery_assigned_by').prefetch_related('items__product', 'payments')

    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(id__exact=search_query) |
            Q(customer__username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(tracking_number__icontains=search_query)
        )

    # Filters
    status_filter = request.GET.get('status', '')
    if status_filter in ['ready_for_delivery', 'out_for_delivery', 'delivered']:
        queryset = queryset.filter(status=status_filter)

    days_filter = request.GET.get('days', '')
    if days_filter:
        try:
            days = int(days_filter)
            cutoff_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(ready_for_delivery_at__gte=cutoff_date)
        except ValueError:
            pass

    order_count_filter = request.GET.get('count', '')
    if order_count_filter:
        try:
            count = int(order_count_filter)
            queryset = queryset[:count]
        except ValueError:
            pass

    order_by = request.GET.get('order_by', '-ready_for_delivery_at')
    if order_by in ['ready_for_delivery_at', '-ready_for_delivery_at', 'total_amount', '-total_amount', 'customer__username']:
        queryset = queryset.order_by(order_by)

    in_delivery_orders = list(queryset.filter(status__in=['ready_for_delivery', 'out_for_delivery']))
    delivered_orders = list(queryset.filter(status='delivered'))
    unpaid_ids = {o.id for o in in_delivery_orders + delivered_orders if not order_has_confirmed_payment(o)}

    return render(request, 'admins/delivery_orders.html', {
        'in_delivery_orders': in_delivery_orders,
        'delivered_orders': delivered_orders,
        'unpaid_ids': unpaid_ids,
        'search_query': search_query,
        'status_filter': status_filter,
        'days_filter': days_filter,
        'order_count_filter': order_count_filter,
        'order_by': order_by,
    })

@sales_admin_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def update_order_tracking(request, order_id):
    """Update tracking number for an order in delivery."""
    order = get_object_or_404(Order, id=order_id, status__in=['ready_for_delivery', 'out_for_delivery'])

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('delivery_orders_list')
        tracking_number = request.POST.get('tracking_number', '').strip()
        if tracking_number:
            old_tn = order.tracking_number
            order.tracking_number = tracking_number
            order.save()
            log_audit(request, 'tracking_updated', target=order,
                      description=f"Tracking # set on Order #{order.id}",
                      metadata={'old': old_tn or '', 'new': tracking_number})
            messages.success(request, f"Tracking number updated for Order #{order.id}.")
        else:
            messages.warning(request, "Tracking number cannot be empty.")

    return redirect('delivery_orders_list')

@sales_admin_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def mark_orders_prepared(request):
    """Mark selected orders as prepared and create a prep group."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('approved_orders_list')
        order_ids = request.POST.getlist('order_ids')
        if not order_ids:
            messages.error(request, "No orders selected.")
            return redirect('approved_orders_list')

        orders = Order.objects.filter(id__in=order_ids, status__in=['approved', 'pending_payment'])
        if not orders:
            messages.error(request, "No valid approved or pending-payment orders found.")
            return redirect('approved_orders_list')

        # Create prep group
        prep_group = PrepGroup.objects.create(
            created_by=request.user,
        )
        prep_group.orders.set(orders)

        # Snapshot order list BEFORE marking as prepared (update() invalidates queryset)
        order_list = list(orders)
        unpaid_ids = [o.id for o in order_list if not order_has_confirmed_payment(o)]

        # Mark orders as prepared
        orders.update(
            status='prepared',
            prepared_at=timezone.now(),
            prepared_by=request.user
        )

        for o in order_list:
            log_order_event(o, 'prepared', actor=request.user)
        log_audit(request, 'order_prepared', target=prep_group,
                  description=f"Created Order Preparation {prep_group.group_id} with {len(order_list)} orders"
                              + (f" ({len(unpaid_ids)} unpaid)" if unpaid_ids else ""),
                  metadata={'order_ids': [o.id for o in order_list], 'unpaid_order_ids': unpaid_ids})
        for o in order_list:
            if not o.is_walk_in:
                notify(o.customer,
                       title="Your order is being prepared 👨‍🍳",
                       message=f"Order #{o.id} is now being prepared in the kitchen.",
                       link=f"/orders/",
                       notification_type='order_update')

        messages.success(request, f"Created Order Preparation {prep_group.group_id} with {len(order_list)} orders.")
        return redirect('prep_group_detail', group_id=prep_group.group_id)

    return redirect('approved_orders_list')

@sales_admin_required
def set_pending_payment(request, order_id):
    """Marks order as accepted and requests payment from customer."""
    order = get_object_or_404(Order, id=order_id)
    if order_has_confirmed_payment(order):
        finalize_order_approval(order, request.user, request=request)
        messages.success(request, f"Order #{order.id} approved and signed.")
    else:
        order.status = 'pending_payment'
        order.save()
        log_order_event(order, 'pending_payment', actor=request.user)
        messages.success(request, f"Order #{order.id} marked as Accepted and Waiting for Payment.")
    return redirect('sales_admin_dashboard')

@sales_admin_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def force_approve_unpaid(request, order_id):
    """Move a pending_payment order to approved without confirmed payment.
    Order is tagged unpaid — staff must collect payment on delivery.
    """
    if request.method != 'POST':
        return redirect('admin_order_detail', order_id=order_id)
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('admin_order_detail', order_id=order_id)
    order = get_object_or_404(Order, id=order_id, status='pending_payment')
    order.status = 'approved'
    order.approved_at = timezone.now()
    order.approved_by = request.user
    order.save()
    log_order_event(order, 'approved_unpaid', actor=request.user)
    log_audit(request, 'order_approved_unpaid', target=order,
              description=f"Order #{order.id} force-approved without payment — collect on delivery",
              metadata={'order_id': order.id, 'approved_by': request.user.username})
    if not order.is_walk_in:
        notify(order.customer,
               title="Your order has been approved",
               message=f"Order #{order.id} is approved. Payment will be collected on delivery.",
               link="/orders/",
               notification_type='order_update')
    messages.success(request, f"Order #{order.id} moved to Approved (unpaid — collect on delivery).")
    return redirect('approved_orders_list')

@sales_admin_required
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def bulk_accept_orders(request):
    """Accepts multiple pending or awaiting payment orders in one action."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('sales_admin_dashboard')
        order_ids = request.POST.getlist('order_ids')[:20]   # cap: each triggers a PyHanko signing call
        # Accept both pending and pending_payment orders
        pending_orders = Order.objects.filter(id__in=order_ids, status__in=['pending', 'pending_payment'])
        approved_count = 0
        awaiting_payment_count = 0

        for order in pending_orders:
            if order_has_confirmed_payment(order):
                finalize_order_approval(order, request.user, request=request)
                approved_count += 1
            else:
                # If payment isn't confirmed yet, move to pending_payment
                if order.status != 'pending_payment':
                    order.status = 'pending_payment'
                    order.save()
                awaiting_payment_count += 1

        if approved_count or awaiting_payment_count:
            messages.success(
                request,
                f"Accepted {approved_count} paid order(s) and moved {awaiting_payment_count} order(s) to awaiting payment."
            )
        else:
            messages.warning(request, 'No pending orders were selected or eligible for acceptance.')
    return redirect('sales_admin_dashboard')

@sales_admin_required
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def bulk_reject_orders(request):
    """Rejects multiple pending or awaiting payment orders in one action."""
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('sales_admin_dashboard')
        from admins.models import RejectionReason, RejectedOrder
        from admins.notification_utils import notify_rejection_to_customer
        
        order_ids = request.POST.getlist('order_ids')
        rejection_reason_id = request.POST.get('rejection_reason_id')
        custom_reason = request.POST.get('custom_reason', '').strip()
        
        # Reject both pending and pending_payment orders
        eligible_orders = Order.objects.filter(id__in=order_ids, status__in=['pending', 'pending_payment'])
        rejected_count = 0

        for order in eligible_orders:
            # Get the rejection reason
            rejection_reason = None
            if rejection_reason_id:
                try:
                    rejection_reason = RejectionReason.objects.get(id=rejection_reason_id)
                except:
                    pass
            
            # Update order status
            order.status = 'rejected'
            order.save()
            log_order_event(order, 'rejected', actor=request.user)

            # Create rejection record for analytics
            rejected_order_record = RejectedOrder.objects.create(
                order=order,
                rejection_reason=rejection_reason,
                custom_reason=custom_reason,
                rejected_by=request.user,
                order_total_amount=order.total_amount,
                order_item_count=order.items.count(),
                customer_name=order.customer_label,
                customer_email='' if order.is_walk_in else order.customer.email,
            )

            if not order.is_walk_in:
                try:
                    notify_rejection_to_customer(rejected_order_record, send_email=True)
                except Exception as e:
                    logger.warning("Rejection email failed for order %s: %s", order.id, e)
                try:
                    from admins.refund_utils import process_refund
                    process_refund(order, source='order_rejection', request=request)
                except Exception as e:
                    logger.error("Refund processing failed for order %s: %s", order.id, e, exc_info=True)

            rejected_count += 1

        if rejected_count:
            messages.warning(request, f"Rejected {rejected_count} order(s) and sent notification emails.")
        else:
            messages.warning(request, 'No pending orders were selected or eligible for rejection.')
    return redirect('sales_admin_dashboard')

@sales_admin_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def approve_order(request, order_id):
    """
    Approves a pending order. If payment is confirmed, moves to 'approved' status.
    If payment is not yet confirmed, moves to 'pending_payment' (awaiting payment list).
    """
    if request.method != 'POST':
        return redirect('sales_admin_dashboard')
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('sales_admin_dashboard')
    order = get_object_or_404(Order, id=order_id)

    if order_has_confirmed_payment(order):
        # Payment confirmed - approve and sign invoice
        try:
            finalize_order_approval(order, request.user, request=request)
            messages.success(request, f"Order #{order.id} Approved and Digitally Signed.")
        except Exception as e:
            logger.error("Document signing failed for order %s: %s", order_id, e, exc_info=True)
            messages.error(request, "Failed to sign the invoice. Please try again or contact support.")
    else:
        # Payment not yet received - move to awaiting payment list
        order.status = 'pending_payment'
        order.save()
        log_order_event(order, 'pending_payment', actor=request.user)
        messages.success(request, f"Order #{order.id} Approved. Customer will see it in their Awaiting Payment list.")

    return redirect('sales_admin_dashboard')


@sales_admin_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def reject_order(request, order_id):
    """Rejects a single order while saving administrative reasoning."""
    from admins.models import RejectionReason, RejectedOrder
    from admins.notification_utils import notify_rejection_to_customer

    order = get_object_or_404(Order, id=order_id)
    if request.method != 'POST':
        return redirect('admin_order_detail', order_id=order.id)
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('admin_order_detail', order_id=order.id)
    
    rejection_reason_id = request.POST.get('rejection_reason_id')
    custom_reason = request.POST.get('custom_reason', '').strip()
    
    # Get the rejection reason
    rejection_reason = None
    if rejection_reason_id:
        try:
            rejection_reason = RejectionReason.objects.get(id=rejection_reason_id)
        except:
            pass
     
    # Update order status
    order.status = 'rejected'
    order.save()
    log_order_event(order, 'rejected', actor=request.user)

    # Create rejection record for analytics
    rejected_order_record = RejectedOrder.objects.create(
        order=order,
        rejection_reason=rejection_reason,
        custom_reason=custom_reason,
        rejected_by=request.user,
        order_total_amount=order.total_amount,
        order_item_count=order.items.count(),
        customer_name=order.customer_label,
        customer_email='' if order.is_walk_in else order.customer.email,
    )

    if order.is_walk_in:
        messages.warning(request, f"Order #{order.id} Rejected. (Walk-in order — no email sent.)")
    else:
        try:
            notify_rejection_to_customer(rejected_order_record, send_email=True)
            messages.warning(request, f"Order #{order.id} Rejected and customer notified via email.")
        except Exception as e:
            logger.warning("Rejection email failed for order %s: %s", order.id, e)
            messages.warning(request, f"Order #{order.id} Rejected. (Notification email could not be sent.)")

    log_audit(request, 'order_rejected', target=order,
              description=f"Order #{order.id} rejected",
              metadata={'reason': custom_reason or (rejection_reason.reason_text if rejection_reason else '')})
    if not order.is_walk_in:
        notify(order.customer,
               title="Order rejected ❌",
               message=f"Order #{order.id} has been rejected. Reason: "
                       f"{custom_reason or (rejection_reason.customer_message if rejection_reason else 'Please contact support.')}",
               link=f"/rejected-orders/",
               notification_type='order_update')

    # Auto-refund if the customer had already paid via Stripe
    from admins.refund_utils import process_refund
    process_refund(order, source='order_rejection', request=request)

    return redirect('sales_admin_dashboard')


STEP_BACK_MAP = {
    'pending_payment': ('pending',               ['approved_at', 'approved_by_id']),
    'approved':        ('pending',               ['approved_at', 'approved_by_id']),
    'prepared':        ('approved',              ['prepared_at', 'prepared_by_id']),
    'ready_for_delivery': ('prepared',           ['ready_for_delivery_at', 'ready_for_delivery_by_id']),
    'out_for_delivery':   ('ready_for_delivery', ['delivery_assigned_at', 'delivery_assigned_by_id']),
}


@sales_admin_required
@ratelimit(key='user', rate='20/m', method='POST', block=False)
def step_back_order(request, order_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)
    if getattr(request, 'limited', False):
        return JsonResponse({'ok': False, 'error': 'Too many requests.'}, status=429)

    order = get_object_or_404(Order, id=order_id)
    reason = request.POST.get('reason', '').strip()

    if not reason:
        return JsonResponse({'ok': False, 'error': 'A reason is required.'}, status=400)

    if order.status not in STEP_BACK_MAP:
        return JsonResponse({'ok': False, 'error': f'Cannot step back a {order.get_status_display()} order.'}, status=400)

    previous_status, fields_to_clear = STEP_BACK_MAP[order.status]
    old_status = order.status

    order.status = previous_status
    order.step_back_reason = reason
    order.stepped_back_at = timezone.now()
    order.stepped_back_by = request.user

    for field in fields_to_clear:
        setattr(order, field, None)

    update_fields = ['status', 'step_back_reason', 'stepped_back_at', 'stepped_back_by'] + fields_to_clear
    order.save(update_fields=update_fields)

    log_audit(request, 'order_stepped_back', target=order,
              description=f'Order #{order.id} stepped back from {old_status} to {previous_status}: {reason}',
              metadata={'from_status': old_status, 'to_status': previous_status, 'reason': reason})

    notify(order.customer,
           title='Order update',
           message=f'Your Order #{order.id} status has been updated.',
           link=f'/menu/order-details/{order.id}/',
           notification_type='order_update')

    return JsonResponse({'ok': True, 'new_status': previous_status})


# --- COMPLAINTS ---

@sales_admin_required
def admin_complaints_list(request):
    """Lists all customer complaints."""
    Notification.objects.filter(
        recipient=request.user,
        is_read=False,
        notification_type='complaint',
    ).update(is_read=True)
    complaints = Complaint.objects.all().order_by('-created_at')
    return render(request, 'admins/complaint_list.html', {'complaints': complaints})

@sales_admin_required
def admin_support_chats(request):
    """Lists all complaints with chat activity for the support inbox."""
    from admins.chat_crypto import decrypt_message

    complaints = (
        Complaint.objects
        .select_related('order', 'customer')
        .prefetch_related('messages__sender')
        .annotate(
            unread_count=Count(
                'messages',
                filter=Q(messages__is_read=False, messages__sender__role='customer'),
            ),
            last_msg_at=Max('messages__created_at'),
        )
        .order_by(F('last_msg_at').desc(nulls_last=True), '-created_at')
    )

    # Build one entry per order — keep the complaint with most recent activity
    seen_orders = {}
    for c in complaints:
        msgs = list(c.messages.all())
        last_msg = msgs[-1] if msgs else None
        preview = None
        if last_msg:
            try:
                raw = decrypt_message(last_msg.body)
                preview = raw[:80] + ('…' if len(raw) > 80 else '')
            except Exception:
                preview = None
        entry = {
            'complaint': c,
            'preview': preview,
            'last_at': last_msg.created_at if last_msg else None,
            'unread_count': c.unread_count,
            'msg_count': len(msgs),
        }
        order_id = c.order_id
        if order_id not in seen_orders:
            seen_orders[order_id] = entry
        else:
            existing = seen_orders[order_id]
            # Prefer the entry with more recent activity; fall back to higher complaint id
            existing_at = existing['last_at'] or existing['complaint'].created_at
            this_at = entry['last_at'] or c.created_at
            if this_at > existing_at:
                seen_orders[order_id] = entry

    chat_list = list(seen_orders.values())

    return render(request, 'admins/support_chats.html', {'chat_list': chat_list})


@sales_admin_required
def admin_complaint_detail(request, complaint_id):
    """Detailed view for specific complaint validation."""
    from admins.chat_crypto import decrypt_message
    complaint = get_object_or_404(Complaint, id=complaint_id)
    # Mark unread customer messages as read when admin opens the thread
    SupportMessage.objects.filter(
        complaint=complaint, is_read=False, sender__role='customer',
    ).update(is_read=True)
    raw_msgs = SupportMessage.objects.filter(complaint=complaint).select_related('sender')
    initial_messages = []
    for msg in raw_msgs:
        try:
            body = decrypt_message(msg.body)
        except Exception:
            body = '[encrypted]'
        initial_messages.append({
            'sender': msg.sender.username if msg.sender else 'deleted',
            'body': body,
            'created_at': msg.created_at.strftime('%d %b %Y, %H:%M'),
            'is_mine': msg.sender_id == request.user.id,
        })
    return render(request, 'admins/complaint_detail.html', {
        'complaint': complaint,
        'order': complaint.order,
        'customer': complaint.customer,
        'initial_messages': initial_messages,
    })

@sales_admin_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def resolve_complaint(request, complaint_id):
    """Applies resolution action to a complaint."""
    complaint = get_object_or_404(Complaint, id=complaint_id)
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('admin_complaint_detail', complaint_id=complaint.id)
        action = request.POST.get('action_taken')
        if action:
            complaint.action_taken = action
            complaint.status = 'resolved'
            note = request.POST.get('resolution_note', '').strip()
            if note:
                complaint.resolution_note = note
            complaint.save()
            log_audit(request, 'complaint_resolved', target=complaint,
                      description=f"Complaint #{complaint.id} resolved",
                      metadata={'action_taken': action})

            if action == 'refund':
                from admins.refund_utils import process_refund
                process_refund(complaint.order, source='complaint',
                               request=request, complaint=complaint)
                messages.success(request, f"Complaint resolved — refund initiated for Order #{complaint.order.id}.")

            elif action == 'remake':
                from admins.refund_utils import remake_order
                new_order = remake_order(complaint.order, resolved_by=request.user, request=request)
                messages.success(request, f"Complaint resolved — remake Order #{new_order.id} created with priority.")

            else:
                # dismissed
                notify(complaint.customer,
                       title="Complaint reviewed",
                       message=f"Your complaint on Order #{complaint.order.id} has been reviewed. "
                               f"Outcome: {complaint.get_action_taken_display()}.",
                       link="/support/",
                       notification_type='complaint')
                messages.success(request, f"Complaint resolved: {complaint.get_action_taken_display()}")
        else:
            messages.error(request, "Please select an action before resolving.")
        return redirect('admin_complaints_list')
    return redirect('admin_complaint_detail', complaint_id=complaint.id)


@sales_admin_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def admin_complaint_messages(request, complaint_id):
    """Poll for or send support chat messages (admin side)."""
    from admins.chat_crypto import encrypt_message, decrypt_message
    from django.utils.dateparse import parse_datetime

    complaint = get_object_or_404(Complaint, id=complaint_id)

    if request.method == 'GET':
        since_raw = request.GET.get('since')
        qs = SupportMessage.objects.filter(complaint=complaint).select_related('sender')
        if since_raw:
            since_dt = parse_datetime(since_raw)
            if since_dt:
                qs = qs.filter(created_at__gt=since_dt)
        # Mark any fetched customer messages as read
        qs.filter(is_read=False, sender__role='customer').update(is_read=True)
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
                  description=f'Admin sent support message on Complaint #{complaint.id}')
        return JsonResponse({'ok': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# --- AUDIT LOG ---

@manager_required
@sudo_required
def audit_log_list(request):
    """Filterable view of the security audit trail."""
    logs = AuditLog.objects.select_related('actor').all()

    action_filter = request.GET.get('action', '').strip()
    if action_filter:
        logs = logs.filter(action_type=action_filter)

    actor_filter = request.GET.get('actor', '').strip()
    if actor_filter:
        logs = logs.filter(actor__username__icontains=actor_filter)

    target_filter = request.GET.get('target_model', '').strip()
    if target_filter:
        logs = logs.filter(target_model__iexact=target_filter)

    days_filter = request.GET.get('days', '').strip()
    if days_filter:
        try:
            cutoff = timezone.now() - timedelta(days=int(days_filter))
            logs = logs.filter(timestamp__gte=cutoff)
        except ValueError:
            pass

    search_query = request.GET.get('q', '').strip()
    if search_query:
        logs = logs.filter(
            Q(description__icontains=search_query) |
            Q(ip_address__icontains=search_query) |
            Q(actor__username__icontains=search_query) |
            Q(target_id__iexact=search_query) |
            Q(metadata__customer__icontains=search_query)
        )

    try:
        page_size = int(request.GET.get('count', '200'))
        page_size = max(1, min(page_size, 1000))
    except ValueError:
        page_size = 200

    logs = logs.order_by('-timestamp')
    paginator = Paginator(logs, page_size)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    chain_valid, chain_broken_at = AuditLog.verify_chain()

    return render(request, 'admins/audit_log.html', {
        'logs': page_obj,
        'page_obj': page_obj,
        'action_choices': AuditLog.ACTION_CHOICES,
        'action_filter': action_filter,
        'actor_filter': actor_filter,
        'target_filter': target_filter,
        'days_filter': days_filter,
        'search_query': search_query,
        'count_limit': page_size,
        'total_count': AuditLog.objects.count(),
        'chain_valid': chain_valid,
        'chain_broken_at': chain_broken_at,
    })


# --- REFUND MANAGEMENT ---

@manager_required
@sudo_required
def refund_list(request):
    """Manager view — lists all refund records filterable by status."""
    from admins.models import Refund

    status_filter = request.GET.get('status', '').strip()
    refunds = Refund.objects.select_related('order', 'order__customer', 'processed_by', 'complaint')

    if status_filter:
        refunds = refunds.filter(status=status_filter)

    pending_manual_count = Refund.objects.filter(status__in=['manual', 'failed']).count()

    return render(request, 'admins/refund_list.html', {
        'refunds': refunds,
        'status_filter': status_filter,
        'pending_manual_count': pending_manual_count,
        'status_choices': Refund.STATUS_CHOICES,
    })


@manager_required
@sudo_required
@ratelimit(key='user', rate='20/m', method='POST', block=False)
def mark_refund_processed(request, refund_id):
    """Mark a manual/failed refund as completed after the manager does the bank transfer."""
    from admins.models import Refund

    if request.method != 'POST':
        return redirect('refund_list')
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many requests. Please slow down.')
        return redirect('refund_list')

    refund = get_object_or_404(Refund, id=refund_id)

    if refund.status not in ('manual', 'failed', 'pending'):
        messages.warning(request, f"Refund #{refund.id} is already {refund.get_status_display()}.")
        return redirect('refund_list')

    bank_reference = request.POST.get('bank_reference', '').strip()
    notes = request.POST.get('notes', '').strip()

    refund.status = 'succeeded'
    refund.processed_by = request.user
    refund.processed_at = timezone.now()
    extra = f' | Bank ref: {bank_reference}' if bank_reference else ''
    extra += f' | Notes: {notes}' if notes else ''
    refund.reason = (refund.reason or '') + f' | Manually processed by {request.user.username}{extra}'
    refund.save(update_fields=['status', 'processed_by', 'processed_at', 'reason'])

    log_audit(request, 'refund_processed', target=refund,
              description=f'Manual refund #{refund.id} processed for Order #{refund.order.id} — RM {refund.amount}',
              metadata={'bank_reference': bank_reference, 'notes': notes, 'amount': str(refund.amount)})

    if not refund.order.is_walk_in:
        notify(refund.order.customer,
               title='Refund completed',
               message=f'Your refund of RM {refund.amount} for Order #{refund.order.id} '
                       f'has been transferred to your account. Please allow 1–3 business days.',
               link=f'/order-details/{refund.order.id}/',
               notification_type='payment')

    messages.success(request, f"Refund #{refund.id} marked as processed (RM {refund.amount}).")
    return redirect('refund_list')


# --- CUSTOMER CRM ---

@manager_required
def customers_crm_list(request):
    """List all customers with CRM-relevant data: lifetime value, loyalty tier, order count."""
    from customers.models import CustomerProfile, User

    # Make sure every customer has a profile (lazy provisioning)
    customers_qs = User.objects.filter(role='customer')
    for u in customers_qs:
        CustomerProfile.objects.get_or_create(user=u)

    profiles = CustomerProfile.objects.select_related('user').all()

    search_query = request.GET.get('q', '').strip()
    if search_query:
        profiles = profiles.filter(
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )

    tier_filter = request.GET.get('tier', '').strip()
    if tier_filter:
        profiles = profiles.filter(loyalty_tier=tier_filter)

    order_by = request.GET.get('order_by', '-total_spent')
    if order_by in ['-total_spent', 'total_spent', '-total_orders', 'total_orders',
                    '-last_order_at', 'user__username', '-created_at']:
        profiles = profiles.order_by(order_by)

    return render(request, 'admins/customers_crm.html', {
        'profiles': profiles,
        'tier_choices': CustomerProfile.LOYALTY_TIER_CHOICES,
        'search_query': search_query,
        'tier_filter': tier_filter,
        'order_by': order_by,
    })


@manager_required
@ratelimit(key='user', rate='20/m', method='POST', block=False)
def customer_crm_detail(request, user_id):
    """Detail view of a single customer for CRM purposes."""
    from customers.models import CustomerProfile, User
    customer = get_object_or_404(User, id=user_id, role='customer')
    profile, _ = CustomerProfile.objects.get_or_create(user=customer)
    profile.recalculate()

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('customer_crm_detail', user_id=customer.id)
        profile.admin_notes = request.POST.get('admin_notes', '').strip()
        profile.save(update_fields=['admin_notes', 'updated_at'])
        messages.success(request, "Customer notes saved.")
        return redirect('customer_crm_detail', user_id=customer.id)

    orders = Order.objects.filter(customer=customer).order_by('-created_at')[:20]
    complaints = Complaint.objects.filter(customer=customer).order_by('-created_at')[:20]

    return render(request, 'admins/customer_crm_detail.html', {
        'customer': customer,
        'profile': profile,
        'orders': orders,
        'complaints': complaints,
    })


# --- PRODUCT RATINGS DASHBOARD ---

@manager_required
def ratings_dashboard(request):
    from django.db.models import Avg, Count
    from customers.models import ProductReview

    LOW_RATING_THRESHOLD = 3.5

    products_with_ratings = (
        Product.objects
        .annotate(
            avg_rating=Avg('reviews__rating'),
            review_count=Count('reviews__id'),
        )
        .filter(review_count__gt=0)
        .order_by('avg_rating')
    )

    recent_reviews = (
        ProductReview.objects
        .select_related('product', 'customer')
        .order_by('-created_at')[:20]
    )

    return render(request, 'admins/ratings_dashboard.html', {
        'products': products_with_ratings,
        'recent_reviews': recent_reviews,
        'low_rating_threshold': LOW_RATING_THRESHOLD,
    })


# --- EMAIL CAMPAIGNS ---

@manager_required
def email_template_list(request):
    """Manager: list and create email templates."""
    from admins.models import EmailTemplate
    templates = EmailTemplate.objects.select_related('created_by').all()
    return render(request, 'admins/email_template_list.html', {'templates': templates})


@manager_required
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def email_template_create(request):
    """Manager: create a new email template."""
    from admins.models import EmailTemplate
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please wait before creating another template.')
            return redirect('email_template_list')
        name      = request.POST.get('name', '').strip()
        subject   = request.POST.get('subject', '').strip()
        body_html = request.POST.get('body_html', '').strip()
        if name and subject and body_html:
            if '{{unsubscribe_url}}' not in body_html:
                messages.error(request, 'Template must include {{unsubscribe_url}} for PDPA compliance.')
                return render(request, 'admins/email_template_form.html', {
                    'editing': False,
                    'form_data': {'name': name, 'subject': subject, 'body_html': body_html},
                })
            t = EmailTemplate.objects.create(
                name=name, subject=subject, body_html=body_html,
                created_by=request.user,
            )
            log_audit(request, 'email_template_created', target=t,
                      description=f'Email template "{t.name}" created')
            messages.success(request, f'Template "{t.name}" created.')
            return redirect('email_template_list')
        messages.error(request, 'All fields are required.')
    return render(request, 'admins/email_template_form.html', {'editing': False})


@manager_required
@ratelimit(key='user', rate='20/m', method='POST', block=False)
def email_template_edit(request, template_id):
    """Manager: edit an existing email template."""
    from admins.models import EmailTemplate
    tmpl = get_object_or_404(EmailTemplate, id=template_id)
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('email_template_list')
        name      = request.POST.get('name', tmpl.name).strip()
        subject   = request.POST.get('subject', tmpl.subject).strip()
        body_html = request.POST.get('body_html', tmpl.body_html).strip()
        if '{{unsubscribe_url}}' not in body_html:
            messages.error(request, 'Template must include {{unsubscribe_url}} for PDPA compliance.')
            return render(request, 'admins/email_template_form.html', {
                'editing': True,
                'tmpl': tmpl,
                'form_data': {'name': name, 'subject': subject, 'body_html': body_html},
            })
        tmpl.name      = name
        tmpl.subject   = subject
        tmpl.body_html = body_html
        tmpl.save(update_fields=['name', 'subject', 'body_html', 'updated_at'])
        messages.success(request, f'Template "{tmpl.name}" updated.')
        return redirect('email_template_list')
    return render(request, 'admins/email_template_form.html', {'editing': True, 'tmpl': tmpl})


@manager_required
@ratelimit(key='user', rate='10/m', method='POST', block=False)
def email_template_delete(request, template_id):
    """Manager: delete an email template."""
    from admins.models import EmailTemplate
    tmpl = get_object_or_404(EmailTemplate, id=template_id)
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please slow down.')
            return redirect('email_template_list')
        name = tmpl.name
        tmpl.delete()
        messages.success(request, f'Template "{name}" deleted.')
    return redirect('email_template_list')


@sales_admin_required
@ratelimit(key='user', rate='3/h', method='POST', block=False)
def campaign_compose(request):
    """
    Sales admin: select customers and a template, then preview before sending.
    GET  — show form with pre-selected customer IDs (from CRM list checkboxes).
    POST — confirm and fire blast_campaign.
    """
    from admins.models import EmailTemplate, EmailCampaign
    from admins.email_utils import blast_campaign
    from customers.models import CustomerProfile, User as CustomerUser

    templates = EmailTemplate.objects.filter(is_active=True)

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many campaign sends. Please wait before sending another campaign.')
            return redirect('campaign_compose')
        customer_ids  = request.POST.getlist('customer_ids')
        template_id   = request.POST.get('template_id')
        campaign_name = request.POST.get('campaign_name', '').strip()

        if not customer_ids or not template_id or not campaign_name:
            messages.error(request, 'Campaign name, template, and at least one recipient are required.')
            return redirect('campaign_compose')

        tmpl = get_object_or_404(EmailTemplate, id=template_id, is_active=True)
        customers_qs = CustomerUser.objects.filter(id__in=customer_ids, role='customer')

        campaign = EmailCampaign.objects.create(
            name=campaign_name,
            template=tmpl,
            sent_by=request.user,
            total_recipients=customers_qs.count(),
        )

        results = blast_campaign(customers_qs, tmpl, campaign, sender=request.user, request=request)

        log_audit(request, 'campaign_sent', target=campaign,
                  description=f'Campaign "{campaign_name}" sent — {campaign.sent_count} sent, '
                              f'{campaign.skipped_count} skipped, {campaign.failed_count} failed',
                  metadata={'sent': campaign.sent_count, 'skipped': campaign.skipped_count,
                            'failed': campaign.failed_count})

        return render(request, 'admins/campaign_result.html', {
            'campaign': campaign,
            'results': results,
        })

    # GET — pre-load selected customers from query param
    customer_ids = request.GET.getlist('ids')
    selected_customers = []
    if customer_ids:
        from customers.models import User as CustomerUser
        selected_customers = CustomerUser.objects.filter(id__in=customer_ids, role='customer')

    from admins.email_utils import MONTHLY_CAMPAIGN_LIMIT
    return render(request, 'admins/campaign_compose.html', {
        'templates': templates,
        'selected_customers': selected_customers,
        'customer_ids': customer_ids,
        'monthly_limit': MONTHLY_CAMPAIGN_LIMIT,
    })


@manager_required
def campaign_history(request):
    """Manager: view all past campaigns."""
    from admins.models import EmailCampaign
    campaigns = EmailCampaign.objects.select_related('sent_by', 'template').all()
    return render(request, 'admins/campaign_history.html', {'campaigns': campaigns})


# ---------------------------------------------------------------------------
# SALES REPORT
# ---------------------------------------------------------------------------

@manager_required
def sales_report(request):
    """Detailed revenue, refund, and product sales analytics with date range filter."""
    import json
    from django.db.models import Sum, Count, Avg, F
    from django.db.models.functions import TruncDate, TruncMonth
    from admins.models import Refund
    from customers.models import CustomerProfile

    # --- Date range ---
    from datetime import date as date_type
    now = timezone.now()
    today = now.date()

    single_date = request.GET.get('date', '').strip()
    date_from   = request.GET.get('date_from', '').strip()
    date_to     = request.GET.get('date_to', '').strip()
    period      = request.GET.get('period', '').strip()

    # Resolve mode: single day > custom range > preset period > default 30d
    mode = 'preset'
    if single_date:
        try:
            single_date_obj = date_type.fromisoformat(single_date)
            since_date = single_date_obj
            until_date = single_date_obj
            mode = 'single'
        except ValueError:
            single_date = ''
    if mode != 'single' and date_from and date_to:
        try:
            since_date = date_type.fromisoformat(date_from)
            until_date = date_type.fromisoformat(date_to)
            if since_date > until_date:
                since_date, until_date = until_date, since_date
            mode = 'range'
        except ValueError:
            date_from = date_to = ''
    if mode == 'preset':
        try:
            days = int(period) if period else 30
        except ValueError:
            days = 30
        since_date = today - timedelta(days=days - 1)
        until_date = today

    since = timezone.make_aware(
        timezone.datetime.combine(since_date, timezone.datetime.min.time())
    )
    until = timezone.make_aware(
        timezone.datetime.combine(until_date, timezone.datetime.max.time())
    )
    days = (until_date - since_date).days + 1

    completed = Order.objects.filter(status__in=['approved', 'delivered'])
    in_range  = completed.filter(approved_at__gte=since, approved_at__lte=until)

    # --- Revenue summary ---
    rev = in_range.aggregate(
        total=Sum('total_amount'),
        count=Count('id'),
        avg=Avg('total_amount'),
    )
    revenue_total  = rev['total'] or 0
    orders_count   = rev['count'] or 0
    avg_order_val  = round(rev['avg'] or 0, 2)

    # --- Daily revenue chart ---
    daily_qs = (
        in_range
        .annotate(day=TruncDate('approved_at'))
        .values('day')
        .annotate(total=Sum('total_amount'), orders=Count('id'))
        .order_by('day')
    )
    daily_map = {row['day']: {'rev': float(row['total'] or 0), 'orders': row['orders']} for row in daily_qs}
    chart_labels, chart_revenue, chart_orders = [], [], []
    for i in range(days):
        d = since_date + timedelta(days=i)
        chart_labels.append(d.strftime('%d %b'))
        chart_revenue.append(daily_map.get(d, {}).get('rev', 0))
        chart_orders.append(daily_map.get(d, {}).get('orders', 0))

    # --- Top products ---
    top_products = (
        OrderItem.objects
        .filter(order__approved_at__gte=since, order__approved_at__lte=until, order__status__in=['approved', 'delivered'])
        .values('product__name', 'product__category')
        .annotate(qty=Sum('quantity'), revenue=Sum('subtotal'))
        .order_by('-revenue')[:10]
    )

    # --- Category breakdown ---
    category_revenue = (
        OrderItem.objects
        .filter(order__approved_at__gte=since, order__approved_at__lte=until, order__status__in=['approved', 'delivered'])
        .values('product__category')
        .annotate(revenue=Sum('subtotal'), qty=Sum('quantity'))
        .order_by('-revenue')
    )

    # --- Refund analytics ---
    refunds_qs = Refund.objects.filter(created_at__gte=since, created_at__lte=until)
    refund_total  = refunds_qs.filter(status='succeeded').aggregate(t=Sum('amount'))['t'] or 0
    refund_count  = refunds_qs.filter(status='succeeded').count()
    refund_rate   = round((refund_count / orders_count * 100) if orders_count else 0, 1)
    refunds_by_source = (
        refunds_qs.filter(status='succeeded')
        .values('source')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')
    )
    pending_refunds = Refund.objects.filter(status__in=['manual', 'pending', 'failed']).count()

    # --- Order status funnel (all time) ---
    status_counts = {s: Order.objects.filter(status=s).count() for s in
                     ['pending', 'approved', 'prepared', 'out_for_delivery', 'delivered', 'rejected', 'cancelled']}

    # --- Loyalty tier breakdown ---
    tier_counts = (
        CustomerProfile.objects.values('loyalty_tier')
        .annotate(n=Count('id'))
        .order_by('loyalty_tier')
    )
    tier_map = {t['loyalty_tier']: t['n'] for t in tier_counts}

    period_choices = {'7 days': 7, '30 days': 30, '90 days': 90, '1 year': 365}

    return render(request, 'admins/sales_report.html', {
        'period': days if mode == 'preset' else None,
        'period_choices': period_choices,
        'since': since_date,
        'until': until_date,
        'today': today,
        'mode': mode,
        'single_date': single_date if mode == 'single' else '',
        'date_from': date_from if mode == 'range' else '',
        'date_to': date_to if mode == 'range' else '',
        # Revenue
        'revenue_total': revenue_total,
        'orders_count': orders_count,
        'avg_order_val': avg_order_val,
        # Charts (JSON)
        'chart_labels': json.dumps(chart_labels),
        'chart_revenue': json.dumps(chart_revenue),
        'chart_orders': json.dumps(chart_orders),
        # Products
        'top_products': list(top_products),
        'category_revenue': list(category_revenue),
        # Refunds
        'refund_total': refund_total,
        'refund_count': refund_count,
        'refund_rate': refund_rate,
        'refunds_by_source': list(refunds_by_source),
        'pending_refunds': pending_refunds,
        # Funnel
        'status_counts': status_counts,
        # CRM
        'tier_map': tier_map,
    })


# ---------------------------------------------------------------------------
# AVAILABILITY TOGGLE
# ---------------------------------------------------------------------------

@manager_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def toggle_product_availability(request, product_id):
    """AJAX POST — flip a product's is_available flag."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'Too many requests.'}, status=429)
    product = get_object_or_404(Product, id=product_id)
    product.is_available = not product.is_available
    product.save(update_fields=['is_available'])
    log_audit(request, 'product_availability_toggled', target=product,
              description=f"Product '{product.name}' {'listed' if product.is_available else 'hidden'} from menu",
              metadata={'is_available': product.is_available})
    return JsonResponse({'is_available': product.is_available, 'name': product.name})


# ---------------------------------------------------------------------------
# PRIORITY TAGGING
# ---------------------------------------------------------------------------

@sales_admin_required
@ratelimit(key='user', rate='60/m', method='POST', block=False)
def toggle_order_priority(request, order_id):
    """AJAX POST — flip an order's is_priority flag."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'Too many requests.'}, status=429)
    order = get_object_or_404(Order, id=order_id)
    order.is_priority = not order.is_priority
    order.save(update_fields=['is_priority'])
    log_audit(request, 'order_approved', target=order,
              description=f"Order #{order.id} priority {'enabled' if order.is_priority else 'disabled'} by {request.user.username}")
    return JsonResponse({'is_priority': order.is_priority})


@manager_required
@ratelimit(key='user', rate='30/m', method='POST', block=False)
def toggle_customer_vip(request, user_id):
    """AJAX POST — flip a customer profile's is_vip flag."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'Too many requests.'}, status=429)
    from customers.models import CustomerProfile
    from customers.models import User as CustomerUser
    customer = get_object_or_404(CustomerUser, id=user_id)
    profile, _ = CustomerProfile.objects.get_or_create(user=customer)
    profile.is_vip = not profile.is_vip
    profile.save(update_fields=['is_vip'])
    log_audit(request, 'order_approved', target=profile,
              description=f"Customer '{customer.username}' VIP status set to {profile.is_vip} by {request.user.username}")
    return JsonResponse({'is_vip': profile.is_vip})


# ---------------------------------------------------------------------------
# ADMIN PROFILE
# ---------------------------------------------------------------------------

@sales_admin_required
@ratelimit(key='user', rate='10/h', method='POST', block=False)
def admin_profile(request):
    from django.contrib.auth import update_session_auth_hash
    from .models import RejectedOrder
    from customers.otp_utils import mask_email

    user = request.user
    week_ago = timezone.now() - timedelta(days=7)

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please wait before updating your profile again.')
            return redirect('admin_profile')
        action = request.POST.get('action')

        if action == 'update_profile':
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.phone_number = request.POST.get('phone_number', '').strip()
            user.save(update_fields=['first_name', 'last_name', 'phone_number'])
            messages.success(request, 'Profile updated.')
            return redirect('admin_profile')

        if action == 'request_pw_change_otp':
            from customers.otp_utils import generate_and_cache_pw_change_otp, send_pw_change_email
            otp = generate_and_cache_pw_change_otp(user)
            send_pw_change_email(user, otp)
            request.session['pw_change_pending'] = True
            messages.info(request, 'A 6-digit code has been sent to your email.')
            return redirect('admin_profile')

        if action == 'verify_pw_change_otp':
            from customers.otp_utils import verify_pw_change_otp
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
                    except DjangoValidationError as ve:
                        for msg in ve.messages:
                            messages.error(request, msg)
                    else:
                        user.set_password(new_pw)
                        user.save()
                        update_session_auth_hash(request, user)
                        request.session.pop('pw_change_pending', None)
                        log_audit(request, 'password_changed', target=user,
                                  description=f'Password changed via OTP for {user.username}')
                        messages.success(request, 'Password changed successfully.')
                        return redirect('admin_profile')
            elif result == 'invalid':
                messages.error(request, 'Incorrect code. Please try again.')
            else:
                messages.error(request, 'Code expired or max attempts reached. Please request a new code.')
                request.session.pop('pw_change_pending', None)
                return redirect('admin_profile')

    approved_total = user.approved_orders.count()
    approved_week = user.approved_orders.filter(approved_at__gte=week_ago).count()
    rejected_total = RejectedOrder.objects.filter(rejected_by=user).count()
    rejected_week = RejectedOrder.objects.filter(rejected_by=user, rejected_at__gte=week_ago).count()
    recent_approved = user.approved_orders.select_related('customer').order_by('-approved_at')[:6]

    return render(request, 'admins/admin_profile.html', {
        'approved_total': approved_total,
        'approved_week': approved_week,
        'rejected_total': rejected_total,
        'rejected_week': rejected_week,
        'recent_approved': recent_approved,
        'pw_change_pending': request.session.get('pw_change_pending', False),
        'pw_change_email_masked': mask_email(user.email),
    })


@manager_required
@ratelimit(key='user', rate='10/h', method='POST', block=False)
def manager_profile(request):
    from django.contrib.auth import update_session_auth_hash
    from .models import RejectedOrder, EmailCampaign
    from customers.otp_utils import mask_email

    user = request.user
    week_ago = timezone.now() - timedelta(days=7)

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            messages.error(request, 'Too many requests. Please wait before updating your profile again.')
            return redirect('manager_profile')
        action = request.POST.get('action')

        if action == 'update_profile':
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.phone_number = request.POST.get('phone_number', '').strip()
            user.save(update_fields=['first_name', 'last_name', 'phone_number'])
            messages.success(request, 'Profile updated.')
            return redirect('manager_profile')

        if action == 'request_pw_change_otp':
            from customers.otp_utils import generate_and_cache_pw_change_otp, send_pw_change_email
            otp = generate_and_cache_pw_change_otp(user)
            send_pw_change_email(user, otp)
            request.session['pw_change_pending'] = True
            messages.info(request, 'A 6-digit code has been sent to your email.')
            return redirect('manager_profile')

        if action == 'verify_pw_change_otp':
            from customers.otp_utils import verify_pw_change_otp
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
                    except DjangoValidationError as ve:
                        for msg in ve.messages:
                            messages.error(request, msg)
                    else:
                        user.set_password(new_pw)
                        user.save()
                        update_session_auth_hash(request, user)
                        request.session.pop('pw_change_pending', None)
                        log_audit(request, 'password_changed', target=user,
                                  description=f'Password changed via OTP for {user.username}')
                        messages.success(request, 'Password changed successfully.')
                        return redirect('manager_profile')
            elif result == 'invalid':
                messages.error(request, 'Incorrect code. Please try again.')
            else:
                messages.error(request, 'Code expired or max attempts reached. Please request a new code.')
                request.session.pop('pw_change_pending', None)
                return redirect('manager_profile')

    approved_total = user.approved_orders.count()
    approved_week = user.approved_orders.filter(approved_at__gte=week_ago).count()
    rejected_total = RejectedOrder.objects.filter(rejected_by=user).count()
    rejected_week = RejectedOrder.objects.filter(rejected_by=user, rejected_at__gte=week_ago).count()
    campaigns_total = EmailCampaign.objects.filter(sent_by=user).count()
    campaigns_week = EmailCampaign.objects.filter(sent_by=user, sent_at__gte=week_ago).count()
    total_recipients = EmailCampaign.objects.filter(sent_by=user).aggregate(
        total=Sum('sent_count'))['total'] or 0
    recent_approved = user.approved_orders.select_related('customer').order_by('-approved_at')[:5]
    recent_campaigns = EmailCampaign.objects.filter(sent_by=user).order_by('-sent_at')[:5]

    return render(request, 'admins/manager_profile.html', {
        'approved_total': approved_total,
        'approved_week': approved_week,
        'rejected_total': rejected_total,
        'rejected_week': rejected_week,
        'campaigns_total': campaigns_total,
        'campaigns_week': campaigns_week,
        'total_recipients': total_recipients,
        'recent_approved': recent_approved,
        'recent_campaigns': recent_campaigns,
        'pw_change_pending': request.session.get('pw_change_pending', False),
        'pw_change_email_masked': mask_email(user.email),
    })
    return JsonResponse({'is_vip': profile.is_vip})