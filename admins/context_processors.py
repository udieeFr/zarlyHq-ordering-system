def unread_notifications(request):
    """Inject unread notification count for authenticated customers into every template."""
    if request.user.is_authenticated and getattr(request.user, 'role', None) == 'customer':
        try:
            from admins.models import Notification
            count = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
            notification_type__in=('order_update', 'payment', 'delivery', 'complaint'),
        ).count()
        except Exception:
            count = 0
    else:
        count = 0
    return {'unread_notification_count': count}
