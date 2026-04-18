from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse
from .models import Order, DigitalSignature, Complaint
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
            
            # Redirect based on user role
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and next_url != '/':
                return redirect(next_url)
            
            # Role-based redirect
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
def sales_admin_dashboard(request):
    """Main landing page for admins."""
    return render(request, 'admins/sales_admin_dashboard.html', {
        'pending_orders': Order.objects.filter(status='pending').order_by('-created_at'),
        'pending_payment_orders': Order.objects.filter(status='pending_payment').order_by('-created_at'),
        'accepted_orders': Order.objects.filter(status='approved').order_by('-approved_at')[:10],
    })

@sales_admin_required
def admin_order_detail(request, order_id):
    """View complete order info, shipping, and items."""
    order = get_object_or_404(Order, id=order_id)
    return render(request, 'admins/order_detail.html', {'order': order})

@sales_admin_required
def set_pending_payment(request, order_id):
    """Marks order as accepted and requests payment from customer."""
    order = get_object_or_404(Order, id=order_id)
    order.status = 'pending_payment'
    order.save()
    messages.success(request, f"Order #{order.id} marked as Accepted and Waiting for Payment.")
    return redirect('sales_admin_dashboard')

@sales_admin_required
def approve_order(request, order_id):
    """Generates PDF receipt and applies digital signature upon approval."""
    order = get_object_or_404(Order, id=order_id)
    if not order.payment_proof:
        messages.error(request, "Cannot approve: Payment proof missing.")
        return redirect('admin_order_detail', order_id=order.id)
    try:
        raw_pdf = generate_invoice_pdf(order)
        signed_path, doc_hash = sign_pdf_digitally(raw_pdf, order.id)
        DigitalSignature.objects.create(
            order=order, 
            signature_hash=doc_hash, 
            pdf_path=os.path.join('signed_pdfs', os.path.basename(signed_path)),
        )
        order.status = 'approved'
        order.approved_at = timezone.now()
        order.approved_by = request.user
        order.save()
        messages.success(request, f"Order #{order.id} Approved and Digitally Signed.")
    except Exception as e:
        messages.error(request, f"Error signing document: {str(e)}")
    return redirect('sales_admin_dashboard')

@sales_admin_required
def reject_order(request, order_id):
    """Rejects the order."""
    order = get_object_or_404(Order, id=order_id)
    order.status = 'rejected'
    order.save()
    messages.warning(request, f"Order #{order.id} Rejected.")
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