"""
URL configuration for zarlyOs project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect, render
from admins.views import unified_login, logout_view, dashboard_home, admin_login, customer_login, custom_login
from customers.views import stripe_webhook, home as customer_home_view
from django.conf import settings
from django.conf.urls.static import static


def error_400(request, exception=None):
    return render(request, 'error_pages/400.html', status=400)

def error_403(request, exception=None):
    return render(request, 'error_pages/403.html', status=403)

def error_404(request, exception=None):
    return render(request, 'error_pages/404.html', status=404)

def error_500(request):
    return render(request, 'error_pages/500.html', status=500)

handler400 = error_400
handler403 = error_403
handler404 = error_404
handler500 = error_500

def home_redirect(request):
    """Redirect based on user role after accessing root"""
    if request.user.is_authenticated:
        if request.user.role == 'customer':
            return redirect('customer_home')
        elif request.user.role == 'manager' or request.user.is_superuser:
            return redirect('manager_analytics_view')
        elif request.user.role == 'sales_admin':
            return redirect('sales_admin_dashboard')
        else:
            return redirect('customer_home')
    else:
        return redirect('customer_home')

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Root redirects based on auth status
    path('', home_redirect, name='home'),
    
    # Unified Authentication (New)
    path('login/', unified_login, name='login'),
    path('logout/', logout_view, name='logout'),
    path('home/', dashboard_home, name='dashboard_home'),

    # Customer landing page (public)
    path('start/', customer_home_view, name='customer_home'),
    
    # Legacy login URLs (kept for backwards compatibility)
    path('login/admin/', admin_login, name='admin_login'),
    path('login/customer/', customer_login, name='customer_login'),
    path('login/legacy/', custom_login, name='legacy_login'),
    
    # App URLs
    path('dashboard/', include('admins.urls')),  # All admin URLs under /dashboard/
    path('menu/', include('customers.urls')),    # All customer URLs under /menu/

    # Stripe webhook alias for Stripe CLI forwarding
    path('stripe/webhook/', stripe_webhook, name='stripe_webhook_root'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)