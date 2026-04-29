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
from django.shortcuts import redirect
from admins.views import unified_login, logout_view, dashboard_home, admin_login, customer_login, custom_login
from django.conf import settings               # <--- Add this
from django.conf.urls.static import static

def home_redirect(request):
    """Redirect based on user role after accessing root"""
    if request.user.is_authenticated:
        if request.user.role == 'customer':
            return redirect('product_list')
        elif request.user.role in ['sales_admin', 'manager'] or request.user.is_superuser:
            return redirect('sales_admin_dashboard')
        else:
            return redirect('product_list')
    else:
        return redirect('login')

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Root redirects based on auth status
    path('', home_redirect, name='home'),
    
    # Unified Authentication (New)
    path('login/', unified_login, name='login'),
    path('logout/', logout_view, name='logout'),
    path('home/', dashboard_home, name='dashboard_home'),
    
    # Legacy login URLs (kept for backwards compatibility)
    path('login/admin/', admin_login, name='admin_login'),
    path('login/customer/', customer_login, name='customer_login'),
    path('login/legacy/', custom_login, name='legacy_login'),
    
    # App URLs
    path('dashboard/', include('admins.urls')),  # All admin URLs under /dashboard/
    path('menu/', include('customers.urls')),    # All customer URLs under /menu/
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)