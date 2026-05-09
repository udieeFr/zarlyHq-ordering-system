"""
Notification utilities for order rejection emails and alerts.
"""
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone


def send_rejection_email(rejected_order):
    """
    Send rejection notification email to customer.
    
    Args:
        rejected_order: RejectedOrder instance
    """
    try:
        order = rejected_order.order
        customer = order.customer
        
        # Prepare email content
        context = {
            'customer_name': rejected_order.customer_name,
            'order_id': order.id,
            'order_date': order.created_at.strftime('%d %b %Y, %H:%M'),
            'order_amount': f"RM {order.total_amount:.2f}",
            'rejection_message': rejected_order.get_customer_message(),
            'support_email': settings.DEFAULT_FROM_EMAIL,
            'order_link': f"{settings.SITE_URL}/customer/orders/{order.id}/" if hasattr(settings, 'SITE_URL') else None,
        }
        
        # Render HTML email
        html_message = render_to_string('admins/emails/order_rejection.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        send_mail(
            subject=f'Order #{order.id} Has Been Rejected',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[customer.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        # Mark as notified
        rejected_order.customer_notified = True
        rejected_order.notification_sent_at = timezone.now()
        rejected_order.save()
        
        return True
        
    except Exception as e:
        print(f"Error sending rejection email for order {rejected_order.order.id}: {str(e)}")
        return False


def notify_rejection_to_customer(rejected_order, send_email=True):
    """
    Main function to notify customer about order rejection.
    Can send email and log notification.
    
    Args:
        rejected_order: RejectedOrder instance
        send_email: Whether to send email (default: True)
    """
    if send_email:
        return send_rejection_email(rejected_order)
    return True
