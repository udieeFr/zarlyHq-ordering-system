from django.contrib import admin
from .models import Order, OrderItem, DigitalSignature, Payment  # Changed SignedDocument to DigitalSignature

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'customer__username')
    inlines = [OrderItemInline]

@admin.register(DigitalSignature)  # Register the new model name
class DigitalSignatureAdmin(admin.ModelAdmin):
    list_display = ('order', 'signature_hash', 'timestamp')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order',
        'payment_method',
        'status',
        'amount',
        'currency',
        'stripe_session_id',
        'created_at',
        'paid_at',
    )
    list_filter = ('payment_method', 'status', 'currency', 'created_at')
    search_fields = ('order__id', 'stripe_session_id', 'stripe_payment_intent_id', 'payment_reference')