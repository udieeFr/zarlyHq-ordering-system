from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login
from django.utils import timezone
from django.contrib import messages
from .models import Order, DigitalSignature, Complaint
from .utils import generate_invoice_pdf, sign_pdf_digitally
import os

def is_sales_admin(user):
    return user.is_authenticated and user.role in ['sales_admin', 'manager']

def custom_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.role in ['sales_admin', 'manager']:
                return redirect('sales_admin_dashboard')
            return redirect('product_list')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def sales_admin_dashboard(request):
    return render(request, 'admins/sales_admin_dashboard.html', {
        'pending_orders': Order.objects.filter(status='pending').order_by('-created_at'),
        'pending_payment_orders': Order.objects.filter(status='pending_payment').order_by('-created_at'),
        'accepted_orders': Order.objects.filter(status='approved').order_by('-approved_at')[:10],
    })

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def admin_complaints_list(request):
    complaints = Complaint.objects.all().order_by('-created_at')
    return render(request, 'admins/complaint_list.html', {'complaints': complaints})

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def admin_complaint_detail(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id)
    return render(request, 'admins/complaint_detail.html', {
        'complaint': complaint,
        'order': complaint.order,
        'customer': complaint.customer
    })

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def resolve_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id)
    if request.method == 'POST':
        # Retrieve the specific action chosen from the dropdown
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

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def approve_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not order.payment_proof:
        messages.error(request, "Cannot approve: Payment proof missing.")
        return redirect('sales_admin_dashboard')
    try:
        raw_pdf = generate_invoice_pdf(order)
        signed_path, doc_hash = sign_pdf_digitally(raw_pdf, order.id)
        DigitalSignature.objects.create(
            order=order, signature_hash=doc_hash, pdf_path=os.path.join('signed_pdfs', os.path.basename(signed_path)),
        )
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
    order = get_object_or_404(Order, id=order_id)
    order.status = 'pending_payment'
    order.save()
    messages.success(request, f"Order #{order.id} marked as 'Accepted & Waiting for Payment'")
    return redirect('sales_admin_dashboard')