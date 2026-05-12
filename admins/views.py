from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum
from datetime import timedelta
from .models import Order, DigitalSignature, Complaint, PrepGroup, Payment
from .utils import generate_invoice_pdf, sign_pdf_digitally
from customers.auth_utils import (
    sales_admin_required, 
    manager_required, 
    role_required, 
    get_user_dashboard_url
)
import os
from customers.models import Product, Category, Allergy

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
    return bool(order.payment_proof) or has_stripe_payment


def finalize_order_approval(order, user):
    """Signs the invoice and marks the order as approved."""
    raw_pdf = generate_invoice_pdf(order)
    signed_path, doc_hash, sig_value = sign_pdf_digitally(raw_pdf, order.id)
    DigitalSignature.objects.create(
        order=order,
        signature_hash=doc_hash,
        pdf_path=os.path.join('signed_pdfs', os.path.basename(signed_path)),
        signature_value=sig_value,
    )
    order.status = 'approved'
    order.approved_at = timezone.now()
    order.approved_by = user
    order.save()

def unified_login(request):
    """
    Unified login view that redirects users to appropriate dashboard based on role.
    Serves as the main login endpoint for the system.
    """
    if request.user.is_authenticated:
        # Already logged in, redirect to dashboard
        return redirect(get_user_dashboard_url(request.user))
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Always redirect by role after login so staff land on the right area.
            # This avoids stale ?next=... values sending sales admins somewhere else.
            dashboard_url = get_user_dashboard_url(user)
            return redirect(dashboard_url)
        else:
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
    elif request.user.role in ['sales_admin', 'manager'] or request.user.is_superuser:
        return redirect('sales_admin_dashboard')
    else:
        messages.error(request, "Your role is not configured. Please contact support.")
        return redirect('product_list')

@login_required
@role_required('manager', 'sales_admin')
def manager_analytics_view(request):
    """
    Manager analytics dashboard showing business metrics.
    Accessible to: Manager, Superuser
    """
    # TODO: Implement manager analytics with charts and metrics
    total_orders = Order.objects.count()
    approved_orders = Order.objects.filter(status='approved').count()
    pending_orders = Order.objects.filter(status='pending').count()
    total_revenue = sum(o.total_amount for o in Order.objects.filter(status='approved'))
    
    return render(request, 'admins/manager_analytics.html', {
        'total_orders': total_orders,
        'approved_orders': approved_orders,
        'pending_orders': pending_orders,
        'total_revenue': total_revenue,
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
def stage_stock_update(request, product_id):
    """Automatically saves a proposed stock change to the session via AJAX."""
    if request.method == 'POST':
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
def confirm_stock_changes(request):
    """Applies all staged changes from the session to the actual database."""
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
def clear_stock_staging(request):
    """Clears the staging area without saving changes."""
    request.session['stock_staging'] = {}
    messages.info(request, "All pending changes have been cleared.")
    return redirect('inventory_list')

@sales_admin_required
def add_product(request):
    """Form and logic to add a new item to the inventory."""
    if request.method == 'POST':
        name = request.POST.get('name')
        price = request.POST.get('price')
        stock = request.POST.get('stock')
        category_id = request.POST.get('category')
        
        product = Product.objects.create(
            name=name,
            price=price,
            stock=stock,
            category_id=category_id
        )
        
        allergy_ids = request.POST.getlist('allergies')
        if allergy_ids:
            product.allergies.set(allergy_ids)
        
        messages.success(request, f"Product '{name}' added successfully.")
        return redirect('inventory_list')

    return render(request, 'admins/add_product.html', {
        'categories': Category.objects.all(),
        'allergies': Allergy.objects.all()
    })

# --- DASHBOARD AND ORDERS ---

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

    dashboard_metrics = {
        'pending_count': base_pending.count(),
        'pending_payment_count': base_pending_payment.count(),
        'approved_count': approved_orders_qs.count(),
        'rejected_count': Order.objects.filter(status='rejected').count(),
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
    })

@sales_admin_required
def approved_orders_list(request):
    """List all approved orders with filtering and search."""
    queryset = Order.objects.filter(status='approved').select_related('customer', 'approved_by').prefetch_related('items__product')

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

    approved_orders = queryset

    return render(request, 'admins/approved_orders.html', {
        'approved_orders': approved_orders,
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
def approve_pending_payment(request, order_id):
    """Approve an awaiting-payment order when payment is confirmed."""
    order = get_object_or_404(Order, id=order_id, status='pending_payment')

    if not order_has_confirmed_payment(order):
        messages.error(
            request,
            "Payment is not confirmed yet for this order. Wait for Stripe confirmation or manual proof upload."
        )
        return redirect('pending_payment_orders_list')

    # Finalize approval (signs invoice and moves to 'approved')
    finalize_order_approval(order, request.user)

    messages.success(request, f"Order #{order.id} payment approved and signed.")
    return redirect('pending_payment_orders_list')

@sales_admin_required
def reject_pending_payment(request, order_id):
    """Reject payment proof and move order back to pending for re-upload."""
    order = get_object_or_404(Order, id=order_id, status='pending_payment')
    
    rejection_reason = request.POST.get('rejection_reason', '').strip()
    if not rejection_reason:
        messages.error(request, "Please provide a rejection reason.")
        return redirect('pending_payment_orders_list')
    
    # Move back to pending
    order.status = 'pending'
    order.payment_proof = None  # Clear the rejected proof
    order.save()
    
    # Update Payment record status
    Payment.objects.filter(order=order, payment_method='manual').update(status='rejected')
    
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
            from_email=None,  # Uses DEFAULT_FROM_EMAIL
            recipient_list=[order.customer.email],
            html_message=email_body,
            fail_silently=True,
        )
    except Exception as e:
        print(f"Error sending rejection email: {e}")
    
    messages.success(request, f"Order #{order.id} payment proof rejected. Customer notified.")
    return redirect('pending_payment_orders_list')

@sales_admin_required
def print_order_summary(request, order_id):
    """Generate a printable order summary PDF."""
    order = get_object_or_404(Order, id=order_id, status='approved')
    # Reuse existing PDF generation logic
    try:
        pdf_path = generate_invoice_pdf(order)
        with open(pdf_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="order_{order.id}_summary.pdf"'
            return response
    except Exception as e:
        messages.error(request, f"Error generating PDF: {str(e)}")
        return redirect('approved_orders_list')

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
    # Show only active prep groups that still have at least one order in prepared state.
    # Once a group is marked ready_for_delivery, it drops out of this list.
    prep_groups = (
        PrepGroup.objects
        .filter(orders__status='prepared')
        .select_related('created_by')
        .distinct()
        .order_by('-created_at')
    )

    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        prep_groups = prep_groups.filter(
            Q(group_id__icontains=search_query) |
            Q(created_by__username__icontains=search_query)
        )

    # Filters
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

    # Ordering
    order_by = request.GET.get('order_by', '-created_at')
    if order_by in ['created_at', '-created_at', 'total_orders', '-total_orders', 'total_amount', '-total_amount']:
        prep_groups = prep_groups.order_by(order_by)

    return render(request, 'admins/prepared_orders.html', {
        'prep_groups': prep_groups,
        'search_query': search_query,
        'days_filter': days_filter,
        'order_count_filter': order_count_filter,
        'order_by': order_by,
    })

@sales_admin_required
def prep_group_detail(request, group_id):
    """View details of a specific prep group."""
    prep_group = get_object_or_404(PrepGroup, group_id=group_id)
    orders = prep_group.orders.all().prefetch_related('items__product')

    return render(request, 'admins/prep_group_detail.html', {
        'prep_group': prep_group,
        'orders': orders,
    })

@sales_admin_required
def mark_prep_group_ready(request, group_id):
    """Mark an entire prep group as ready for delivery."""
    prep_group = get_object_or_404(PrepGroup, group_id=group_id)
    if request.method == 'POST':
        courier_name = request.POST.get('courier_name', '').strip() or None
        tracking_number = request.POST.get('tracking_number', '').strip() or None
        orders = prep_group.orders.filter(status='prepared')

        if not orders.exists():
            messages.error(request, 'No prepared orders are available in this prep group.')
            return redirect('prep_group_detail', group_id=prep_group.group_id)

        orders.update(
            status='ready_for_delivery',
            ready_for_delivery_at=timezone.now(),
            ready_for_delivery_by=request.user,
            courier_name=courier_name,
            tracking_number=tracking_number,
            delivery_assigned_at=timezone.now(),
            delivery_assigned_by=request.user
        )

        messages.success(request, f'Prep group {prep_group.group_id} marked as ready for delivery.')
        return redirect('delivery_orders_list')

    return redirect('prep_group_detail', group_id=prep_group.group_id)

@sales_admin_required
def mark_order_out_for_delivery(request, order_id):
    """Move a single order from ready_for_delivery to out_for_delivery."""
    order = get_object_or_404(Order, id=order_id, status='ready_for_delivery')
    order.status = 'out_for_delivery'
    order.save()
    messages.success(request, f"Order #{order.id} marked as Out for Delivery.")
    return redirect('delivery_orders_list')

@sales_admin_required
def mark_order_delivered(request, order_id):
    """Mark a single order as delivered."""
    order = get_object_or_404(Order, id=order_id, status='out_for_delivery')
    order.status = 'delivered'
    order.delivered_at = timezone.now()
    order.save()
    messages.success(request, f"Order #{order.id} marked as Delivered.")
    return redirect('delivery_orders_list')

@sales_admin_required
def delivery_orders_list(request):
    """List orders in the delivery workflow."""
    queryset = Order.objects.filter(status__in=['ready_for_delivery', 'out_for_delivery', 'delivered']).select_related('customer', 'ready_for_delivery_by', 'delivery_assigned_by').prefetch_related('items__product')

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

    in_delivery_orders = queryset.filter(status__in=['ready_for_delivery', 'out_for_delivery'])
    delivered_orders = queryset.filter(status='delivered')

    return render(request, 'admins/delivery_orders.html', {
        'in_delivery_orders': in_delivery_orders,
        'delivered_orders': delivered_orders,
        'search_query': search_query,
        'status_filter': status_filter,
        'days_filter': days_filter,
        'order_count_filter': order_count_filter,
        'order_by': order_by,
    })

@sales_admin_required
def update_order_tracking(request, order_id):
    """Update tracking number for an order in delivery."""
    order = get_object_or_404(Order, id=order_id, status__in=['ready_for_delivery', 'out_for_delivery'])
    
    if request.method == 'POST':
        tracking_number = request.POST.get('tracking_number', '').strip()
        if tracking_number:
            order.tracking_number = tracking_number
            order.save()
            messages.success(request, f"Tracking number updated for Order #{order.id}.")
        else:
            messages.warning(request, "Tracking number cannot be empty.")
    
    return redirect('delivery_orders_list')

@sales_admin_required
def mark_orders_prepared(request):
    """Mark selected orders as prepared and create a prep group."""
    if request.method == 'POST':
        order_ids = request.POST.getlist('order_ids')
        if not order_ids:
            messages.error(request, "No orders selected.")
            return redirect('approved_orders_list')

        orders = Order.objects.filter(id__in=order_ids, status='approved')
        if not orders:
            messages.error(request, "No valid approved orders found.")
            return redirect('approved_orders_list')

        # Create prep group
        prep_group = PrepGroup.objects.create(
            created_by=request.user,
            total_orders=orders.count(),
            total_amount=sum(order.total_amount for order in orders)
        )
        prep_group.orders.set(orders)

        # Mark orders as prepared
        orders.update(
            status='prepared',
            prepared_at=timezone.now(),
            prepared_by=request.user
        )

        messages.success(request, f"Created prep group {prep_group.group_id} with {prep_group.total_orders} orders.")
        return redirect('prep_group_detail', group_id=prep_group.group_id)

    return redirect('approved_orders_list')

@sales_admin_required
def set_pending_payment(request, order_id):
    """Marks order as accepted and requests payment from customer."""
    order = get_object_or_404(Order, id=order_id)
    if order_has_confirmed_payment(order):
        finalize_order_approval(order, request.user)
        messages.success(request, f"Order #{order.id} approved and signed.")
    else:
        order.status = 'pending_payment'
        order.save()
        messages.success(request, f"Order #{order.id} marked as Accepted and Waiting for Payment.")
    return redirect('sales_admin_dashboard')

@sales_admin_required
def bulk_accept_orders(request):
    """Accepts multiple pending or awaiting payment orders in one action."""
    if request.method == 'POST':
        order_ids = request.POST.getlist('order_ids')
        # Accept both pending and pending_payment orders
        pending_orders = Order.objects.filter(id__in=order_ids, status__in=['pending', 'pending_payment'])
        approved_count = 0
        awaiting_payment_count = 0

        for order in pending_orders:
            if order_has_confirmed_payment(order):
                finalize_order_approval(order, request.user)
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
def bulk_reject_orders(request):
    """Rejects multiple pending or awaiting payment orders in one action."""
    if request.method == 'POST':
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
            
            # Create rejection record for analytics
            rejected_order_record = RejectedOrder.objects.create(
                order=order,
                rejection_reason=rejection_reason,
                custom_reason=custom_reason,
                rejected_by=request.user,
                order_total_amount=order.total_amount,
                order_item_count=order.items.count(),
                customer_name=order.customer.first_name or order.customer.username,
                customer_email=order.customer.email,
            )
            
            # Send rejection email to customer
            try:
                notify_rejection_to_customer(rejected_order_record, send_email=True)
            except Exception as e:
                # Log error but don't block rejection
                print(f"Error notifying customer for order {order.id}: {str(e)}")
            
            rejected_count += 1

        if rejected_count:
            messages.warning(request, f"Rejected {rejected_count} order(s) and sent notification emails.")
        else:
            messages.warning(request, 'No pending orders were selected or eligible for rejection.')
    return redirect('sales_admin_dashboard')

@sales_admin_required
def approve_order(request, order_id):
    """
    Approves a pending order. If payment is confirmed, moves to 'approved' status.
    If payment is not yet confirmed, moves to 'pending_payment' (awaiting payment list).
    """
    order = get_object_or_404(Order, id=order_id)

    if order_has_confirmed_payment(order):
        # Payment confirmed - approve and sign invoice
        try:
            finalize_order_approval(order, request.user)
            messages.success(request, f"Order #{order.id} Approved and Digitally Signed.")
        except Exception as e:
            messages.error(request, f"Error signing document: {str(e)}")
    else:
        # Payment not yet received - move to awaiting payment list
        order.status = 'pending_payment'
        order.save()
        messages.success(request, f"Order #{order.id} Approved. Customer will see it in their Awaiting Payment list.")
    
    return redirect('sales_admin_dashboard')


@sales_admin_required
def reject_order(request, order_id):
    """Rejects a single order while saving administrative reasoning."""
    from admins.models import RejectionReason, RejectedOrder
    from admins.notification_utils import notify_rejection_to_customer
    
    order = get_object_or_404(Order, id=order_id)
    if request.method != 'POST':
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
    
    # Create rejection record for analytics
    rejected_order_record = RejectedOrder.objects.create(
        order=order,
        rejection_reason=rejection_reason,
        custom_reason=custom_reason,
        rejected_by=request.user,
        order_total_amount=order.total_amount,
        order_item_count=order.items.count(),
        customer_name=order.customer.first_name or order.customer.username,
        customer_email=order.customer.email,
    )
    
    # Send rejection email to customer
    try:
        notify_rejection_to_customer(rejected_order_record, send_email=True)
        messages.warning(request, f"Order #{order.id} Rejected and customer notified via email.")
    except Exception as e:
        messages.warning(request, f"Order #{order.id} Rejected but failed to send email: {str(e)}")
    
    return redirect('sales_admin_dashboard')

# --- COMPLAINTS ---

@sales_admin_required
def admin_complaints_list(request):
    """Lists all customer complaints."""
    complaints = Complaint.objects.all().order_by('-created_at')
    return render(request, 'admins/complaint_list.html', {'complaints': complaints})

@sales_admin_required
def admin_complaint_detail(request, complaint_id):
    """Detailed view for specific complaint validation."""
    complaint = get_object_or_404(Complaint, id=complaint_id)
    return render(request, 'admins/complaint_detail.html', {
        'complaint': complaint,
        'order': complaint.order,
        'customer': complaint.customer
    })

@sales_admin_required
def resolve_complaint(request, complaint_id):
    """Applies resolution action to a complaint."""
    complaint = get_object_or_404(Complaint, id=complaint_id)
    if request.method == 'POST':
        action = request.POST.get('action_taken')
        if action:
            complaint.action_taken = action
            complaint.status = 'resolved'
            complaint.save()
            messages.success(request, f"Complaint resolved: {complaint.get_action_taken_display()}")
        else:
            messages.error(request, "Please select an action before resolving.")
        return redirect('admin_complaints_list')
    return redirect('admin_complaint_detail', complaint_id=complaint.id)