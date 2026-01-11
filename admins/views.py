from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login
from django.utils import timezone
from django.contrib import messages
from .models import Order, DigitalSignature
from .utils import generate_invoice_pdf, sign_pdf_digitally  # <--- Our new engine!
import os

def is_sales_admin(user):
    return user.is_authenticated and user.role in ['sales_admin', 'manager']


def custom_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # If the user is a sales admin or manager, always redirect them to the dashboard
            if user.role in ['sales_admin', 'manager']:
                return redirect('sales_admin_dashboard')

            # Otherwise, check for a 'next' URL (e.g., for customers returning to checkout)
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)

            # Default redirect for all other users (e.g., customers)
            return redirect('product_list')
    else:
        form = AuthenticationForm()

    return render(request, 'registration/login.html', {'form': form})

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def sales_admin_dashboard(request):
    pending_orders = Order.objects.filter(status='pending').order_by('-created_at')
    accepted_orders = Order.objects.filter(status='approved').order_by('-approved_at')
    pending_payment_orders = Order.objects.filter(status='pending_payment') 

    return render(request, 'admins/sales_admin_dashboard.html', {
        'pending_orders': pending_orders,
        'accepted_orders': accepted_orders,
        'pending_payment_orders': pending_payment_orders,
    })

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def approve_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    # Check if payment proof exists (Security Requirement)
    if not order.payment_proof:
        messages.error(request, "Cannot approve: Payment proof missing.")
        return redirect('sales_admin_dashboard')

    try:
        # 1. Generate PDF
        raw_pdf = generate_invoice_pdf(order)
        
        # 2. Sign PDF (The Cryptographic Step)
        signed_path, doc_hash = sign_pdf_digitally(raw_pdf, order.id)
        
        # 3. Store the Digital Signature Record
        relative_path = os.path.join('signed_pdfs', os.path.basename(signed_path))
        DigitalSignature.objects.create(
            order=order,
            signature_hash=doc_hash,
            pdf_path=relative_path,
        )
        
        # 4. Update Status
        order.status = 'approved'
        order.approved_at = timezone.now()
        order.approved_by = request.user
        order.save()
        
        messages.success(request, f"Order #{order.id} Approved & Digitally Signed!")
        
    except Exception as e:
        messages.error(request, f"Error signing document: {str(e)}")

    return redirect('sales_admin_dashboard')

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def reject_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = 'rejected'
    order.save()
    messages.warning(request, f"Order #{order.id} Rejected.")
    return redirect('sales_admin_dashboard')

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def admin_order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return render(request, 'admins/order_detail.html', {'order': order})

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def set_pending_payment(request, order_id):
    """
    Moves order from 'Pending' -> 'Accepted but pending payment'
    This tells the customer: "We can make this, please pay now."
    """
    order = get_object_or_404(Order, id=order_id)
    order.status = 'pending_payment'
    order.save()
    messages.success(request, f"Order #{order.id} marked as 'Accepted & Waiting for Payment'")
    return redirect('sales_admin_dashboard')