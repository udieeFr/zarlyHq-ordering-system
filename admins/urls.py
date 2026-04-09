# admins/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.sales_admin_dashboard, name='sales_admin_dashboard'),
    path('order/<int:order_id>/approve/', views.approve_order, name='approve_order'),
    path('order/<int:order_id>/reject/', views.reject_order, name='reject_order'),
    path('order/<int:order_id>/detail/', views.admin_order_detail, name='admin_order_detail'),
    path('order/<int:order_id>/set_pending_payment/', views.set_pending_payment, name='set_pending_payment'),
    
    # NEW COMPLAINT PATHS
    path('complaints/', views.admin_complaints_list, name='admin_complaints_list'),
    path('complaints/<int:complaint_id>/', views.admin_complaint_detail, name='admin_complaint_detail'),
    path('complaints/<int:complaint_id>/resolve/', views.resolve_complaint, name='resolve_complaint'),
]
