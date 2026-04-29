"""
Role-based access control decorators and utilities.
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse


def role_required(*roles):
    """
    Decorator to check if user has required role(s).
    Usage: @role_required('manager', 'sales_admin')
    Also allows superusers to access all protected views.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('login')
            
            # Superusers have access to everything
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # Check if user role is in required roles
            if request.user.role in roles:
                return view_func(request, *args, **kwargs)
            
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        
        return wrapper
    return decorator


def customer_required(view_func):
    """Decorator to restrict access to customers only."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to continue.")
            return redirect('customer_login')
        
        if request.user.role != 'customer':
            messages.error(request, "This page is for customers only.")
            return redirect('home')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def sales_admin_required(view_func):
    """Decorator to restrict access to sales admins and managers."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to access this page.")
            return redirect('admin_login')
        
        # Superusers have full access
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        if request.user.role not in ['sales_admin', 'manager']:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def manager_required(view_func):
    """Decorator to restrict access to managers only."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to access this page.")
            return redirect('admin_login')
        
        # Superusers have full access
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        if request.user.role != 'manager':
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def get_user_dashboard_url(user):
    """
    Returns the appropriate dashboard URL based on user role.
    """
    if not user.is_authenticated:
        return 'login'
    
    if not user.role:
        return 'product_list'

    if user.role == 'customer':
        return 'product_list'
    elif user.role in ['sales_admin', 'manager'] or user.is_superuser:
        return 'dashboard_home'
    
    return 'product_list'


def get_user_login_url(user):
    """
    Returns the appropriate login URL based on user role or context.
    """
    if user and user.is_authenticated:
        return get_user_dashboard_url(user)
    
    return 'login'
