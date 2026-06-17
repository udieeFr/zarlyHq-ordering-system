"""
Email sending utilities using Django's built-in SMTP backend.

send_campaign_email  — send one personalised campaign email to a single customer.
blast_campaign       — iterate over a queryset of customers, enforcing opt-in and rate limit.
"""
import logging
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

MONTHLY_CAMPAIGN_LIMIT = 2  # max campaign emails per customer per rolling 30 days


def _render_body(body_html, customer, profile, unsubscribe_url=''):
    """Replace template placeholders with customer-specific values."""
    from django.utils.dateformat import format as date_format

    last_order = date_format(profile.last_order_at, 'j M Y') if profile.last_order_at else 'N/A'
    replacements = {
        '{{customer_name}}':  customer.first_name or customer.username,
        '{{loyalty_tier}}':   profile.get_loyalty_tier_display() if profile else '',
        '{{last_order_date}}': last_order,
        '{{company_name}}':   getattr(settings, 'COMPANY_NAME', 'Zarly BigFood'),
        '{{unsubscribe_url}}': unsubscribe_url,
    }
    result = body_html
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value))
    return result


def send_campaign_email(customer, subject, body_html, campaign=None):
    """
    Send a single HTML email via Django's SMTP backend.

    Returns (status: str, reason: str) — status is 'sent', 'failed', or 'skipped'.
    Does NOT check opt-in or rate limits — call blast_campaign for that.
    """
    from admins.models import EmailLog

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@zarlybigfood.com')
    email_host_user = getattr(settings, 'EMAIL_HOST_USER', None)

    if not email_host_user:
        logger.warning(f'EMAIL_HOST_USER not configured — skipping email to {customer.email}')
        EmailLog.objects.create(
            customer=customer, campaign=campaign,
            subject=subject, status='failed',
            reason='Email host not configured (EMAIL_HOST_USER is empty)',
        )
        return 'failed', 'Email host not configured'

    try:
        plain_body = strip_tags(body_html)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=[customer.email],
        )
        msg.attach_alternative(body_html, 'text/html')
        msg.send(fail_silently=False)

        EmailLog.objects.create(
            customer=customer, campaign=campaign,
            subject=subject, status='sent',
        )
        return 'sent', ''

    except Exception as e:
        reason = str(e)
        logger.error(f'SMTP error sending to {customer.email}: {reason}')
        EmailLog.objects.create(
            customer=customer, campaign=campaign,
            subject=subject, status='failed', reason=reason[:300],
        )
        return 'failed', reason


def blast_campaign(customers_qs, template, campaign, sender, request=None):
    """
    Send a campaign email to a queryset of customers.

    Enforces:
    - marketing_opt_in == True
    - max MONTHLY_CAMPAIGN_LIMIT emails in the past 30 days

    Updates campaign.sent_count / skipped_count / failed_count in place.
    Returns list of dicts: [{customer, status, reason}]
    """
    from customers.models import CustomerProfile
    from admins.models import EmailLog

    results = []
    cutoff  = timezone.now() - timedelta(days=30)

    for customer in customers_qs:
        # Opt-in check
        try:
            profile = customer.customer_profile
        except CustomerProfile.DoesNotExist:
            profile, _ = CustomerProfile.objects.get_or_create(user=customer)

        if not profile.marketing_opt_in:
            EmailLog.objects.create(
                customer=customer, campaign=campaign,
                subject=template.subject, status='skipped',
                reason='Customer opted out of marketing',
            )
            campaign.skipped_count += 1
            results.append({'customer': customer, 'status': 'skipped', 'reason': 'Opted out'})
            continue

        # Rate limit check
        recent_count = EmailLog.objects.filter(
            customer=customer,
            status='sent',
            sent_at__gte=cutoff,
        ).count()

        if recent_count >= MONTHLY_CAMPAIGN_LIMIT:
            EmailLog.objects.create(
                customer=customer, campaign=campaign,
                subject=template.subject, status='skipped',
                reason=f'Monthly limit reached ({recent_count}/{MONTHLY_CAMPAIGN_LIMIT})',
            )
            campaign.skipped_count += 1
            results.append({'customer': customer, 'status': 'skipped', 'reason': 'Monthly limit reached'})
            continue

        # Generate per-recipient unsubscribe URL
        from django.core import signing
        from django.urls import reverse

        token = signing.dumps(customer.pk, salt='email-unsubscribe')
        if request is not None:
            unsubscribe_url = request.build_absolute_uri(
                reverse('unsubscribe_email', args=[token])
            )
        else:
            base_url = getattr(settings, 'SITE_URL', 'https://zarlybigfood.my')
            unsubscribe_url = f"{base_url}{reverse('unsubscribe_email', args=[token])}"

        # Render personalised body
        body = _render_body(template.body_html, customer, profile, unsubscribe_url=unsubscribe_url)

        status, reason = send_campaign_email(
            customer=customer,
            subject=template.subject,
            body_html=body,
            campaign=campaign,
        )

        if status == 'sent':
            campaign.sent_count += 1
        else:
            campaign.failed_count += 1

        results.append({'customer': customer, 'status': status, 'reason': reason})

    campaign.save(update_fields=['sent_count', 'skipped_count', 'failed_count'])
    return results
