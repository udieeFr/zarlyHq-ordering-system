# customers/urls.py
from django.urls import path
from . import views
from admins import views as admin_views

urlpatterns = [
    # This now handles everything: viewing, filtering, and the product grid
    path('', views.product_list, name='product_list'),
    path('submit-complaint/', views.submit_complaint, name='submit_complaint'),
    path('login/', admin_views.custom_login, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/update/', views.update_cart, name='update_cart'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('submit-order/', views.submit_order, name='submit_order'),
    path('order-success/<int:order_id>/', views.order_success, name='order_success'),
    path('upload-proof/<int:order_id>/', views.upload_payment_proof, name='upload_payment_proof'),
]