"""
Helper utilities for audit logging and in-app notifications.

These wrap AuditLog and Notification creation so views don't repeat boilerplate.
"""
from .models import AuditLog, Notification


def get_client_ip(request):
    """Extract the client's IP address, respecting X-Forwarded-For for proxies."""
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit(request, action_type, target=None, description='', metadata=None, actor=None):
    """
    Record an entry in the immutable audit log.

    Args:
        request: Django request (used for IP + user agent + actor fallback).
                 Can be None for system-triggered events (e.g., Stripe webhook).
        action_type: One of AuditLog.ACTION_CHOICES values.
        target: A model instance (Order, Payment, etc.) — its class name and pk are recorded.
        description: Human-readable description.
        metadata: Optional dict with additional context (saved as JSON).
        actor: Optional explicit actor User. Defaults to request.user if authenticated.
    """
    try:
        if actor is None and request is not None:
            user = getattr(request, 'user', None)
            if user is not None and user.is_authenticated:
                actor = user

        target_model = ''
        target_id = None
        if target is not None:
            target_model = target.__class__.__name__
            target_id = getattr(target, 'pk', None)

        ip = get_client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '') if request else ''

        AuditLog.objects.create(
            actor=actor,
            action_type=action_type,
            target_model=target_model,
            target_id=target_id,
            description=description,
            ip_address=ip,
            user_agent=ua[:1000],
            metadata=metadata or {},
        )
    except Exception:
        # Audit logging must never break the originating action.
        # In production you'd send this to Sentry/logging.
        pass


def notify(recipient, title, message, link='', notification_type='system'):
    """
    Create an in-app notification for a single user.

    Args:
        recipient: User instance to notify.
        title: Short headline shown in the bell dropdown.
        message: Longer body.
        link: Optional URL to navigate to when notification is clicked.
        notification_type: One of Notification.TYPE_CHOICES values.
    """
    if recipient is None:
        return None
    try:
        return Notification.objects.create(
            recipient=recipient,
            title=title[:200],
            message=message,
            link=link[:500] if link else '',
            notification_type=notification_type,
        )
    except Exception:
        return None


def notify_admins(title, message, link='', notification_type='admin_alert'):
    """Send a notification to every active sales_admin and manager."""
    from customers.models import User
    admins = User.objects.filter(
        is_active=True,
        role__in=['sales_admin', 'manager'],
    )
    for admin in admins:
        notify(admin, title, message, link=link, notification_type=notification_type)
