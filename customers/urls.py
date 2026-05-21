from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('menu/', views.product_list, name='menu'), 
    path('add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/update/', views.update_cart, name='update_cart'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('submit-order/', views.submit_order, name='submit_order'),
    path('order-details/<int:order_id>/', views.order_success, name='order_success'),
    path('order/<int:order_id>/payment/', views.payment_page, name='payment_page'),
    path('order/<int:order_id>/payment/stripe/', views.start_stripe_payment, name='start_stripe_payment'),
    path('stripe/success/<int:order_id>/', views.stripe_success, name='stripe_success'),
    path('stripe/cancel/<int:order_id>/', views.stripe_cancel, name='stripe_cancel'),
    path('stripe/webhook/', views.stripe_webhook, name='stripe_webhook'),
    
    # Document & Payment Paths
    path('order/<int:order_id>/invoice/', views.download_invoice, name='download_invoice'),
    path('order/<int:order_id>/pay/', views.upload_payment_proof, name='upload_payment_proof'),
    
    # Customer Orders Dashboard
    path('orders/', views.customer_orders, name='customer_orders'),

    # Rejected Orders
    path('rejected-orders/', views.rejected_orders, name='rejected_orders'),
    
    # Awaiting Payment Orders
    path('awaiting-payment/', views.awaiting_payment_orders, name='awaiting_payment_orders'),
    
    path('logout/', views.logout_view, name='logout'),
    path('submit-complaint/', views.submit_complaint, name='submit_complaint'),
    path('support/', views.customer_support, name='customer_support'),
    path('support/complaint/<int:complaint_id>/', views.customer_complaint_detail, name='customer_complaint_detail'),
    path('support/complaint/<int:complaint_id>/messages/', views.customer_complaint_messages, name='customer_complaint_messages'),
    path('verify/<uuid:token>/', views.verify_receipt, name='verify_receipt'),

    # Notifications
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/<int:notification_id>/open/', views.notification_open, name='notification_open'),
    path('notifications/mark-all-read/', views.notifications_mark_all_read, name='notifications_mark_all_read'),

    # Reorder
    path('order/<int:order_id>/reorder/', views.reorder, name='reorder'),

    # Profile
    path('profile/', views.customer_profile, name='customer_profile'),
    path('profile/update/', views.update_profile, name='update_profile'),

    # Cancel order
    path('order/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),

    # Favourites
    path('favourites/', views.favourites_list, name='favourites'),
    path('favourites/toggle/', views.toggle_favourite, name='toggle_favourite'),

    # Ratings & Reviews
    path('order/<int:order_id>/rate/', views.rate_order, name='rate_order'),
    path('product/<int:product_id>/review/', views.submit_product_review, name='submit_product_review'),

    # Email Verification
    path('verify-email/', views.verify_email, name='verify_email'),
    path('send-verification/', views.send_verification_otp, name='send_verification_otp'),

    # Account Deletion
    path('account/delete/', views.delete_account, name='delete_account'),
]