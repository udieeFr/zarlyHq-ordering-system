from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login  # ADD THIS IMPORT
from .models import Order
from customers.models import User

def is_sales_admin(user):
    return user.is_authenticated and user.role in ['sales_admin', 'manager']

def custom_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Role-based redirection after login
            if user.role in ['sales_admin', 'manager']:
                return redirect('sales_admin_dashboard')
            else:
                return redirect('product_list')
    else:
        form = AuthenticationForm()

    return render(request, 'registration/login.html', {'form': form})

@login_required
@user_passes_test(is_sales_admin, login_url='/')
def sales_admin_dashboard(request):
    pending_orders = Order.objects.filter(status='pending').order_by('-created_at')
    accepted_orders = Order.objects.filter(status='approved').order_by('-approved_at')
    pending_payment_orders = []

    context = {
        'pending_orders': pending_orders,
        'accepted_orders': accepted_orders,
        'pending_payment_orders': pending_payment_orders,
    }
    return render(request, 'admins/sales_admin_dashboard.html', context)