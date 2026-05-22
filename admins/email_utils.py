"""
Email sending utilities using SendGrid.

send_campaign_email  — send one personalised campaign email to a single customer.
blast_campaign       — iterate over a queryset of customers, enforcing opt-in and rate limit.
"""
import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone

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
    Send a single HTML email via SendGrid.

    Returns (status: str, reason: str) — status is 'sent', 'failed', or 'skipped'.
    Does NOT check opt-in or rate limits — call blast_campaign for that.
    """
    from admins.models import EmailLog

    api_key = getattr(settings, 'SENDGRID_API_KEY', None)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@zarlybigfood.com')

    if not api_key or api_key == 'your-sendgrid-api-key-here':
        logger.warning(f'SendGrid API key not configured — skipping email to {customer.email}')
        log = EmailLog.objects.create(
            customer=customer, campaign=campaign,
            subject=subject, status='failed',
            reason='SendGrid API key not configured',
        )
        return 'failed', 'SendGrid API key not configured'

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        message = Mail(
            from_email=from_email,
            to_emails=customer.email,
            subject=subject,
            html_content=body_html,
        )
        response = sg.send(message)

        if response.status_code in (200, 202):
            EmailLog.objects.create(
                customer=customer, campaign=campaign,
                subject=subject, status='sent',
            )
            return 'sent', ''
        else:
            reason = f'SendGrid returned status {response.status_code}'
            EmailLog.objects.create(
                customer=customer, campaign=campaign,
                subject=subject, status='failed', reason=reason,
            )
            return 'failed', reason

    except Exception as e:
        reason = str(e)
        logger.error(f'SendGrid error sending to {customer.email}: {reason}')
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
        except Exception:
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
            from django.conf import settings as _settings
            base_url = getattr(_settings, 'SITE_URL', 'https://zarlybigfood.my')
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
