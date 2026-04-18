from django.urls import path
from . import views

urlpatterns = [
    # Dashboard and Orders
    path('', views.sales_admin_dashboard, name='sales_admin_dashboard'),
    path('analytics/', views.manager_analytics_view, name='manager_analytics_view'),
    path('order/<int:order_id>/detail/', views.admin_order_detail, name='admin_order_detail'),
    path('order/<int:order_id>/approve/', views.approve_order, name='approve_order'),
    path('order/<int:order_id>/reject/', views.reject_order, name='reject_order'),
    path('order/<int:order_id>/set_pending_payment/', views.set_pending_payment, name='set_pending_payment'),
    
    # Inventory and Product Management
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/add/', views.add_product, name='add_product'),
    path('inventory/stage/<int:product_id>/', views.stage_stock_update, name='stage_stock_update'),
    path('inventory/confirm/', views.confirm_stock_changes, name='confirm_stock_changes'),
    path('inventory/clear/', views.clear_stock_staging, name='clear_stock_staging'),
    
    # Complaints Management
    path('complaints/', views.admin_complaints_list, name='admin_complaints_list'),
    path('complaints/<int:complaint_id>/', views.admin_complaint_detail, name='admin_complaint_detail'),
    path('complaints/<int:complaint_id>/resolve/', views.resolve_complaint, name='resolve_complaint'),
]