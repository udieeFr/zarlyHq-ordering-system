from django.urls import path
from . import views

urlpatterns = [
    # Dashboard and Orders
    path('', views.sales_admin_dashboard, name='sales_admin_dashboard'),
    path('analytics/', views.manager_analytics_view, name='manager_analytics_view'),
    path('order/<int:order_id>/detail/', views.admin_order_detail, name='admin_order_detail'),
    path('order/<int:order_id>/approve/', views.approve_order, name='approve_order'),
    path('order/<int:order_id>/reject/', views.reject_order, name='reject_order'),
    path('order/multi-accept/', views.bulk_accept_orders, name='bulk_accept_orders'),
    path('approved-orders/', views.approved_orders_list, name='approved_orders_list'),
    path('prepared-orders/', views.prepared_orders_list, name='prepared_orders_list'),
    path('prep-group/<str:group_id>/', views.prep_group_detail, name='prep_group_detail'),
    path('prep-group/<str:group_id>/ready/', views.mark_prep_group_ready, name='mark_prep_group_ready'),
    path('delivery-orders/', views.delivery_orders_list, name='delivery_orders_list'),
    path('order/<int:order_id>/out-for-delivery/', views.mark_order_out_for_delivery, name='mark_order_out_for_delivery'),
    path('order/<int:order_id>/delivered/', views.mark_order_delivered, name='mark_order_delivered'),
    path('order/<int:order_id>/print-summary/', views.print_order_summary, name='print_order_summary'),
    path('prep-list/', views.print_prep_list, name='print_prep_list'),
    path('mark-prepared/', views.mark_orders_prepared, name='mark_orders_prepared'),
    
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