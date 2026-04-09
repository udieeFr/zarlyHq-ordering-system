# customers/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Main Catalog
    path('', views.product_list, name='product_list'),
    path('menu/', views.product_list, name='menu'), 

    # Shopping Cart logic
    path('add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/update/', views.update_cart, name='update_cart'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    
    # Order & Checkout
    path('checkout/', views.checkout, name='checkout'),
    path('submit-order/', views.submit_order, name='submit_order'),
    path('order-success/<int:order_id>/', views.order_success, name='order_success'),
    
    # Account & Complaints
    path('logout/', views.logout_view, name='logout'),
    path('submit-complaint/', views.submit_complaint, name='submit_complaint'),
]