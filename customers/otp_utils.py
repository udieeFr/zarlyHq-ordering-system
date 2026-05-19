import secrets
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)

OTP_TTL = 300  # 5 minutes


def _cache_key(user_pk):
    return f'email_otp_{user_pk}'


def generate_and_cache_otp(user):
    """Generate a cryptographically random 6-digit code and store it in cache."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_cache_key(user.pk), code, OTP_TTL)
    return code


def verify_otp(user, submitted_code):
    """
    Check a submitted OTP against the cached value.
    Returns: 'ok' | 'invalid' | 'expired'
    Deletes the cache entry immediately on correct submission (single-use).
    """
    key = _cache_key(user.pk)
    stored = cache.get(key)
    if stored is None:
        return 'expired'
    if stored != submitted_code:
        return 'invalid'
    cache.delete(key)
    return 'ok'


def mask_email(email):
    """e.g. johndoe@gmail.com -> j*****e@g****.com"""
    local, domain = email.rsplit('@', 1)
    if len(local) <= 1:
        masked_local = local
    elif len(local) == 2:
        masked_local = local[0] + '*'
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]

    parts = domain.rsplit('.', 1)
    if len(parts) == 2:
        name, tld = parts
        masked_name = name[0] + '*' * max(1, len(name) - 1)
        masked_domain = f"{masked_name}.{tld}"
    else:
        masked_domain = domain

    return f"{masked_local}@{masked_domain}"


def send_verification_email(user, otp):
    """Send the 6-digit OTP to the user's email address."""
    try:
        body = render_to_string('emails/email_verification.html', {
            'username': user.username,
            'otp': otp,
        })
        send_mail(
            subject='Your ZarlyHQ verification code',
            message=f'Your verification code is: {otp}. It expires in 5 minutes.',
            from_email=None,
            recipient_list=[user.email],
            html_message=body,
        )
    except Exception as e:
        logger.warning(f'Could not send verification email to {user.email}: {e}')
