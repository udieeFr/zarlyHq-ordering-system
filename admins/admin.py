from django.contrib import admin
from .models import (
    Order, OrderItem, DigitalSignature, Payment,
    Complaint, SupportMessage, PrepGroup, OrderEvent,
    RejectionReason, RejectedOrder, AuditLog, Notification,
    Refund, EmailTemplate, EmailCampaign, EmailLog,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'customer__username')
    inlines = [OrderItemInline]


@admin.register(DigitalSignature)
class DigitalSignatureAdmin(admin.ModelAdmin):
    list_display = ('order', 'signature_hash', 'timestamp')
    search_fields = ('order__id',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'payment_method', 'status', 'amount', 'currency', 'created_at', 'paid_at')
    list_filter = ('payment_method', 'status', 'currency')
    search_fields = ('order__id', 'stripe_session_id', 'stripe_payment_intent_id', 'payment_reference')


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'order', 'subject', 'status', 'action_taken', 'created_at')
    list_filter = ('status', 'action_taken')
    search_fields = ('customer__username', 'subject', 'order__id')


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'complaint', 'sender', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('complaint__id', 'sender__username')


@admin.register(PrepGroup)
class PrepGroupAdmin(admin.ModelAdmin):
    list_display = ('group_id', 'created_at', 'created_by')
    search_fields = ('group_id',)


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ('order', 'status', 'actor', 'timestamp')
    list_filter = ('status',)
    search_fields = ('order__id', 'actor__username')


@admin.register(RejectionReason)
class RejectionReasonAdmin(admin.ModelAdmin):
    list_display = ('code', 'reason_text', 'category', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'reason_text')


@admin.register(RejectedOrder)
class RejectedOrderAdmin(admin.ModelAdmin):
    list_display = ('order', 'rejected_by', 'rejected_at', 'customer_notified')
    list_filter = ('customer_notified',)
    search_fields = ('order__id', 'rejected_by__username')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'actor', 'action_type', 'target_model', 'target_id', 'timestamp')
    list_filter = ('action_type', 'target_model')
    search_fields = ('actor__username', 'action_type', 'description')
    readonly_fields = ('chain_hash',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('recipient__username', 'title')


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'amount', 'status', 'source', 'created_at')
    list_filter = ('status', 'source')
    search_fields = ('order__id',)


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'subject')


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'template', 'sent_by', 'total_recipients', 'sent_count', 'sent_at')
    list_filter = ('sent_at',)
    search_fields = ('name', 'template__name', 'sent_by__username')


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'customer', 'status', 'sent_at')
    list_filter = ('status',)
    search_fields = ('customer__username', 'customer__email')
