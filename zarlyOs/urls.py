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
from admins.views import admin_login, customer_login, custom_login
from django.conf import settings               # <--- Add this
from django.conf.urls.static import static

def home_redirect(request):
    """Redirect based on user role after accessing root"""
    if request.user.is_authenticated:
        if request.user.role in ['sales_admin', 'manager']:
            return redirect('sales_admin_dashboard')
        else:
            return redirect('product_list')
    else:
        return redirect('login')

urlpatterns = [
    path('admin/', admin.site.urls),  # Django admin stays here
    path('', home_redirect, name='home'),  # Root redirects based on role
    path('login/admin/', admin_login, name='admin_login'),
    path('login/customer/', customer_login, name='customer_login'),
    path('login/', custom_login, name='login'),  # Legacy redirect
    path('dashboard/', include('admins.urls')),  # All admin URLs under /dashboard/
    path('menu/', include('customers.urls')),  # All customer URLs under /menu/
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)