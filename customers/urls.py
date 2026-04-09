from django.urls import path
from . import views
from admins import views as admin_views  # Import your existing login view

urlpatterns = [
    path('', views.product_list, name='product_list'),

    # --- Authentication URLs ---
    # 1. Reuse the logic you already wrote in admins/views.py
    path('login/', admin_views.custom_login, name='login'),

    # 2. Custom Logout view
    path('logout/', views.logout_view, name='logout'),
    # ---------------------------

    path('add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/update/', views.update_cart, name='update_cart'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),

    # These views ALREADY have @login_required in your code,
    # so they will automatically trigger the login prompt.
    path('checkout/', views.checkout, name='checkout'),
    path('submit-order/', views.submit_order, name='submit_order'),

    path('order-success/<int:order_id>/', views.order_success, name='order_success'),
    path('upload-proof/<int:order_id>/', views.upload_payment_proof, name='upload_payment_proof'),

    path('menu/', views.menu, name='menu'),
]