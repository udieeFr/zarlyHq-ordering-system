from django.urls import path
from . import views

urlpatterns = [
    path('', views.sales_admin_dashboard, name='sales_admin_dashboard'),  # Now at /dashboard/
    # Later you'll add:
    # path('order/<int:order_id>/', views.order_detail, name='order_detail'),
    # path('order/<int:order_id>/approve/', views.approve_order, name='approve_order'),
    # path('order/<int:order_id>/reject/', views.reject_order, name='reject_order'),
]