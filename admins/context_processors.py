def unread_notifications(request):
    """Inject notification counts for authenticated users into every template."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'unread_notification_count': 0}

    role = getattr(request.user, 'role', None)
    try:
        from admins.models import Notification, Complaint
        if role == 'customer':
            count = Notification.objects.filter(
                recipient=request.user,
                is_read=False,
                notification_type__in=('order_update', 'payment', 'delivery', 'complaint'),
            ).count()
            return {'unread_notification_count': count}
        elif role in ('sales_admin', 'manager'):
            from admins.models import SupportMessage
            admin_unread = Notification.objects.filter(
                recipient=request.user,
                is_read=False,
            ).count()
            pending_complaints = Complaint.objects.filter(status='pending').count()
            unread_chats = SupportMessage.objects.filter(
                is_read=False, sender__role='customer',
            ).values('complaint_id').distinct().count()
            return {
                'unread_notification_count': 0,
                'admin_unread_notification_count': admin_unread,
                'pending_complaints_count': pending_complaints,
                'unread_chats_count': unread_chats,
            }
    except Exception:
        pass
    return {'unread_notification_count': 0}
